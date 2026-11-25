"""Review stage: random set generator -> blind review -> SME moderation."""
import json
import random
from statistics import mean

from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import audit, config, qstore
from .models import Faculty, QuestionRecord, QuestionStatus, Review, ReviewItem, _id
from .question_schema import Question
from .validate import validate_and_normalize

_KEPT = (QuestionStatus.UNIQUE, QuestionStatus.NEAR_DUPLICATE)


class Blueprint(BaseModel):
    subject: str
    units: dict[int, int] = Field(description="unit number -> how many questions to sample")
    seed: int | None = Field(default=None, description="set only for reproducible tests/demos")

    @field_validator("units")
    @classmethod
    def _units(cls, v):
        if not v or any(n < 1 for n in v.values()) or sum(v.values()) > 500:
            raise ValueError("units must be non-empty, counts >= 1, total <= 500")
        return v


class ReviewIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    quality: int = Field(ge=1, le=5)
    difficulty: float = Field(ge=0.0, le=1.0, description="reviewer's own difficulty rating")
    comment: str = Field(default="", max_length=1000)


class CorrectionIn(BaseModel):
    stem: str | None = None
    options: list[str] | None = None
    correct_option: int | None = None
    solution_latex: str | None = None


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    difficulty: float | None = Field(default=None, ge=0.0, le=1.0)


def _payload(rec: QuestionRecord, *, hide_difficulty: bool = True) -> dict:
    q = qstore.load(rec)
    out = {
        "question_id": rec.id, "qtype": q.qtype.value, "stem": q.stem, "options": q.options,
        "correct_option": q.correct_option, "solution_latex": q.solution_latex,
        "subject": q.subject, "unit": q.unit, "bloom": q.bloom.value, "marks": q.marks,
        "near_duplicate": rec.status == QuestionStatus.NEAR_DUPLICATE,
    }
    if not hide_difficulty:
        out["difficulty"] = rec.difficulty
    return out


# ---- Random Set Generator -------------------------------------------------
def build_pool(db: Session, bp: Blueprint, admin: Faculty) -> dict:
    pool_id = _id()
    rng = random.Random(bp.seed) if bp.seed is not None else random.SystemRandom()
    chosen: dict[int, int] = {}
    shortfall: dict[int, int] = {}
    already = select(ReviewItem.question_id)
    for unit, want in sorted(bp.units.items()):
        cands = db.scalars(
            select(QuestionRecord).where(
                QuestionRecord.status.in_(_KEPT),
                func.lower(QuestionRecord.subject) == bp.subject.strip().lower(),
                QuestionRecord.unit == unit,
                QuestionRecord.id.not_in(already),
            ).order_by(QuestionRecord.id)
        ).all()
        picked = rng.sample(cands, min(want, len(cands)))
        for rec in picked:
            db.add(ReviewItem(question_id=rec.id, pool_id=pool_id, status="in_pool"))
        chosen[unit] = len(picked)
        if len(picked) < want:
            shortfall[unit] = want - len(picked)
    db.flush()
    audit.append(db, admin.pseudonym, "pool_built", pool_id,
                 json.dumps({"subject": bp.subject, "selected": chosen}, sort_keys=True))
    db.commit()
    return {"pool_id": pool_id, "selected": sum(chosen.values()), "by_unit": chosen, "shortfall": shortfall}


# ---- Blind reviewer panel -------------------------------------------------
def queue_for(db: Session, reviewer: Faculty, limit: int) -> list[dict]:
    done = select(Review.question_id).where(Review.reviewer == reviewer.pseudonym)
    rows = db.scalars(
        select(QuestionRecord).join(ReviewItem, ReviewItem.question_id == QuestionRecord.id).where(
            ReviewItem.status == "in_pool",
            QuestionRecord.pseudonym != reviewer.pseudonym,     # no reviewing your own questions
            QuestionRecord.id.not_in(done),
        )
    ).all()
    random.SystemRandom().shuffle(rows)
    return [_payload(r) for r in rows[:limit]]


def _open_item(db: Session, question_id: str, states: tuple[str, ...]) -> tuple[ReviewItem, QuestionRecord]:
    item, rec = db.get(ReviewItem, question_id), db.get(QuestionRecord, question_id)
    if not item or not rec:
        raise HTTPException(404, "Question not in review")
    if item.status not in states:
        raise HTTPException(409, f"Question is {item.status}")
    return item, rec


def submit_review(db: Session, question_id: str, reviewer: Faculty, body: ReviewIn) -> dict:
    item, rec = _open_item(db, question_id, ("in_pool",))
    if rec.pseudonym == reviewer.pseudonym:
        raise HTTPException(403, "Cannot review your own question")
    if db.scalar(select(Review.id).where(Review.question_id == question_id, Review.reviewer == reviewer.pseudonym)):
        raise HTTPException(409, "Already reviewed")
    db.add(Review(question_id=question_id, reviewer=reviewer.pseudonym, decision=body.decision,
                  quality=body.quality, difficulty=body.difficulty, comment=body.comment))
    db.flush()
    audit.append(db, reviewer.pseudonym, "review_submitted", question_id, body.decision)
    _evaluate(db, item, rec)
    db.commit()
    return {"status": item.status}


def _evaluate(db: Session, item: ReviewItem, rec: QuestionRecord) -> None:
    reviews = db.scalars(select(Review).where(Review.question_id == item.question_id)).all()
    if len(reviews) < config.REVIEWS_REQUIRED:
        return
    rejects = [r for r in reviews if r.decision == "reject"]
    if len(rejects) > len(reviews) / 2:
        new = "rejected"
    elif not rejects and mean(r.quality for r in reviews) >= config.MIN_QUALITY:
        new = "approved"
    else:
        new = "moderation"          # disagreement or weak scores -> SME decides
    _set_status(db, item, rec, new, "system", reviews)


def _set_status(db, item, rec, new, actor, reviews, difficulty: float | None = None) -> None:
    item.status = new
    if new == "approved":           # re-rate: reviewers' difficulty replaces the author's claim
        rec.difficulty = difficulty if difficulty is not None else round(mean(r.difficulty for r in reviews), 3)
    audit.append(db, actor, "status_change", item.question_id, new)


# ---- Correction interface (LaTeX typos / solution fixes) ------------------
def apply_correction(db: Session, question_id: str, actor: Faculty, body: CorrectionIn) -> dict:
    _, rec = _open_item(db, question_id, ("in_pool", "moderation"))
    data = qstore.load(rec).model_dump()
    changed = []
    for f in ("stem", "options", "correct_option", "solution_latex"):
        v = getattr(body, f)
        if v is not None:
            data[f] = v
            changed.append(f)
    if not changed:
        raise HTTPException(422, "Nothing to correct")
    try:
        nq, issues = validate_and_normalize(Question.model_validate(data))
    except ValidationError as e:
        raise HTTPException(422, {"errors": [x["msg"] for x in e.errors()]})
    if issues:
        raise HTTPException(422, {"issues": issues})
    fp = nq.fingerprint()
    clash = db.scalar(select(QuestionRecord.id).where(
        QuestionRecord.fingerprint == fp, QuestionRecord.id != rec.id, QuestionRecord.status.in_(_KEPT)))
    if clash:
        raise HTTPException(409, "Correction would duplicate an existing question")
    qstore.store(rec, nq)
    rec.fingerprint = fp
    audit.append(db, actor.pseudonym, "correction", question_id, ",".join(changed))
    db.commit()
    return {"corrected": changed}


# ---- SME moderation -------------------------------------------------------
def moderation_queue(db: Session) -> list[dict]:
    items = db.scalars(select(ReviewItem).where(ReviewItem.status == "moderation")).all()
    out = []
    for it in items:
        rec = db.get(QuestionRecord, it.question_id)
        reviews = db.scalars(select(Review).where(Review.question_id == it.question_id).order_by(Review.created_at)).all()
        out.append({**_payload(rec, hide_difficulty=False),
                    "reviews": [{"reviewer": f"R{i + 1}", "decision": r.decision, "quality": r.quality,
                                 "difficulty": r.difficulty, "comment": r.comment}
                                for i, r in enumerate(reviews)]})
    return out


def moderate(db: Session, question_id: str, admin: Faculty, body: DecisionIn) -> dict:
    item, rec = _open_item(db, question_id, ("moderation",))
    reviews = db.scalars(select(Review).where(Review.question_id == question_id)).all()
    _set_status(db, item, rec, "approved" if body.decision == "approve" else "rejected",
                admin.pseudonym, reviews, body.difficulty)
    db.commit()
    return {"status": item.status}
