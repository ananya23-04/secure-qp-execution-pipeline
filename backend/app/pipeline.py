"""Pre-processing pipeline: Convert & Validate -> Deduplicate -> ready for review."""
import logging
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import audit, config, security
from .db import SessionLocal
from .models import QuestionRecord, QuestionStatus, Submission, SubmissionStatus, _id
from .question_schema import Question, SubmissionIn
from .similarity import NearDupIndex, build_idf, tokenize
from .validate import validate_and_normalize

log = logging.getLogger("safeexam.pipeline")
_KEPT = (QuestionStatus.UNIQUE, QuestionStatus.NEAR_DUPLICATE)


def _text(q: Question) -> str:
    return q.stem + " " + " ".join(q.options or [])


def process_submission(db: Session, submission_id: str) -> dict:
    sub = db.get(Submission, submission_id)
    if sub is None:
        raise LookupError(submission_id)
    if sub.status != SubmissionStatus.RAW_INGESTED:      # already processed: idempotent
        return summarize(db, submission_id)

    payload = SubmissionIn.model_validate_json(
        security.decrypt(sub.nonce, sub.ciphertext, submission_id.encode())
    )

    # ---- stage 2a: convert & validate ------------------------------------
    checked = [(i, *validate_and_normalize(q)) for i, q in enumerate(payload.questions)]
    sub.status = SubmissionStatus.VALIDATED
    db.flush()

    # ---- stage 2b: deduplicate -------------------------------------------
    valid = [(i, q) for i, q, issues in checked if not issues]
    batch_fps = {q.fingerprint() for _, q in valid}
    seen_fp: dict[str, str] = {}
    if batch_fps:
        rows = db.execute(
            select(QuestionRecord.fingerprint, QuestionRecord.id)
            .where(QuestionRecord.status.in_(_KEPT), QuestionRecord.fingerprint.in_(batch_fps))
        ).all()
        seen_fp = {fp: qid for fp, qid in rows}

    subjects = {q.subject for _, q in valid}
    existing = []
    if subjects:
        existing = db.scalars(
            select(QuestionRecord).where(
                QuestionRecord.status.in_(_KEPT), QuestionRecord.subject.in_(subjects)
            )
        ).all()
    existing_q = [
        (r, Question.model_validate_json(security.decrypt(r.nonce, r.ciphertext, r.id.encode())))
        for r in existing
    ]
    idf = build_idf([tokenize(_text(q)) for _, q in existing_q] + [tokenize(_text(q)) for _, q in valid])
    index = NearDupIndex(idf)
    for r, q in existing_q:
        index.add(r.subject, r.id, _text(q))

    counts: Counter = Counter()
    for i, q, issues in checked:
        qid = _id()
        status, fp, dup_of, sim = QuestionStatus.INVALID, None, None, None
        if not issues:
            fp = q.fingerprint()
            if fp in seen_fp:
                status, dup_of, sim = QuestionStatus.DUPLICATE, seen_fp[fp], 1.0
            else:
                seen_fp[fp] = qid
                match, score = index.best_match(q.subject, _text(q))
                if match and score >= config.NEARDUP_THRESHOLD:
                    status, dup_of, sim = QuestionStatus.NEAR_DUPLICATE, match, round(score, 4)
                else:
                    status = QuestionStatus.UNIQUE
                index.add(q.subject, qid, _text(q))
        counts[status.value] += 1
        nonce, ct = security.encrypt(q.model_dump_json().encode(), aad=qid.encode())
        db.add(QuestionRecord(
            id=qid, submission_id=submission_id, idx=i, pseudonym=sub.pseudonym,
            status=status, issues=",".join(issues), fingerprint=fp, duplicate_of=dup_of,
            similarity=sim, qtype=q.qtype.value, subject=q.subject, unit=q.unit,
            bloom=q.bloom.value, difficulty=q.difficulty, marks=q.marks,
            nonce=nonce, ciphertext=ct,
        ))

    sub.status = SubmissionStatus.DEDUPLICATED
    audit.append(db, "system", "pipeline_processed", submission_id, str(sorted(counts.items())))
    db.commit()
    return summarize(db, submission_id)


def summarize(db: Session, submission_id: str) -> dict:
    sub = db.get(Submission, submission_id)
    rows = db.scalars(
        select(QuestionRecord).where(QuestionRecord.submission_id == submission_id)
        .order_by(QuestionRecord.idx)
    ).all()
    return {
        "submission_status": sub.status.value,
        "summary": dict(Counter(r.status.value for r in rows)),
        "questions": [
            {"index": r.idx, "status": r.status.value,
             "issues": [c for c in r.issues.split(",") if c]}
            for r in rows
        ],
    }


def run_pipeline_task(submission_id: str) -> None:
    """Background entry point (own DB session)."""
    with SessionLocal() as db:
        try:
            process_submission(db, submission_id)
        except Exception:
            db.rollback()
            log.exception("pipeline failed for submission %s", submission_id)
