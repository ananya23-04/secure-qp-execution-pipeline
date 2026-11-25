"""Exam generation flow: create -> commit -> reveal -> (seed) -> generate -> verify."""
import hashlib
import json

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from datetime import timezone

from . import audit, qstore, render, security, solver
from .models import (Exam, ExamCommit, ExamPaper, ExamRelease, Faculty, QuestionRecord, RenderedPaper,
                     ReviewItem)
from .solver import Candidate, ExamBlueprint, InfeasibleError


class ExamCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    blueprint: ExamBlueprint
    required_commits: int = Field(default=3, ge=1, le=10,
                                  description="how many custodians must commit before reveal")


class CommitIn(BaseModel):
    commitment: str = Field(pattern="^[0-9a-fA-F]{64}$", description="sha256 hex of your secret")


class RevealIn(BaseModel):
    secret: str = Field(min_length=16, max_length=200)


def commitment_of(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def derive_seed(exam_id: str, secrets: list[str]) -> str:
    """Order-independent: nobody can steer the seed without knowing all other secrets."""
    return hashlib.sha256((exam_id + "|" + "|".join(sorted(secrets))).encode()).hexdigest()


def _exam(db: Session, exam_id: str) -> Exam:
    exam = db.get(Exam, exam_id)
    if not exam:
        raise HTTPException(404, "Exam not found")
    return exam


def _bp(exam: Exam) -> ExamBlueprint:
    return ExamBlueprint.model_validate_json(exam.blueprint)


def _to_candidate(r: QuestionRecord) -> Candidate:
    return Candidate(r.id, r.unit, r.marks, r.difficulty, r.bloom, r.qtype, r.fingerprint or "")


def load_candidates(db: Session, bp: ExamBlueprint) -> list[Candidate]:
    rows = db.scalars(
        select(QuestionRecord).join(ReviewItem, ReviewItem.question_id == QuestionRecord.id).where(
            ReviewItem.status == "approved",
            func.lower(QuestionRecord.subject) == bp.subject.strip().lower(),
            QuestionRecord.unit.in_(list(bp.units)),
        )
    ).all()
    return sorted((_to_candidate(r) for r in rows), key=lambda c: c.id)


def _shortfall(cands: list[Candidate], bp: ExamBlueprint) -> dict[int, int]:
    have: dict[int, int] = {}
    for c in cands:
        have[c.unit] = have.get(c.unit, 0) + c.marks
    return {u: need - have.get(u, 0) for u, need in bp.units.items() if have.get(u, 0) < need}


def create_exam(db: Session, body: ExamCreate, admin: Faculty) -> dict:
    bp = body.blueprint
    short = _shortfall(load_candidates(db, bp), bp)
    if short:
        raise HTTPException(409, {"error": "not enough approved questions", "shortfall_marks_by_unit": short})
    exam = Exam(title=body.title, subject=bp.subject, blueprint=bp.model_dump_json(),
                required_commits=body.required_commits, created_by=admin.pseudonym)
    db.add(exam)
    db.flush()
    audit.append(db, admin.pseudonym, "exam_created", exam.id, body.title)
    db.commit()
    return {"id": exam.id, "status": exam.status, "required_commits": exam.required_commits}


def commit(db: Session, exam_id: str, admin: Faculty, body: CommitIn) -> dict:
    exam = _exam(db, exam_id)
    if exam.status != "committing":
        raise HTTPException(409, f"Exam is {exam.status}; commitments are closed")
    if db.scalar(select(ExamCommit.id).where(ExamCommit.exam_id == exam_id, ExamCommit.party == admin.pseudonym)):
        raise HTTPException(409, "You already committed")
    db.add(ExamCommit(exam_id=exam_id, party=admin.pseudonym, commitment=body.commitment.lower()))
    db.flush()
    n = db.scalar(select(func.count()).select_from(ExamCommit).where(ExamCommit.exam_id == exam_id))
    audit.append(db, admin.pseudonym, "seed_commit", exam_id, body.commitment.lower())
    if n >= exam.required_commits:
        exam.status = "revealing"
        audit.append(db, "system", "reveal_phase_open", exam_id, f"commits={n}")
    db.commit()
    return {"status": exam.status, "commits": n, "required": exam.required_commits}


def reveal(db: Session, exam_id: str, admin: Faculty, body: RevealIn) -> dict:
    exam = _exam(db, exam_id)
    if exam.status != "revealing":
        raise HTTPException(409, f"Exam is {exam.status}; reveals are not open")
    row = db.scalar(select(ExamCommit).where(ExamCommit.exam_id == exam_id, ExamCommit.party == admin.pseudonym))
    if not row:
        raise HTTPException(403, "You did not commit to this exam")
    if row.secret is not None:
        raise HTTPException(409, "You already revealed")
    if commitment_of(body.secret) != row.commitment:
        raise HTTPException(422, "Secret does not match your commitment")
    row.secret = body.secret
    db.flush()
    audit.append(db, admin.pseudonym, "seed_reveal", exam_id, "ok")
    rows = db.scalars(select(ExamCommit).where(ExamCommit.exam_id == exam_id)).all()
    revealed = sum(1 for r in rows if r.secret is not None)
    if revealed == len(rows):
        exam.seed_hex = derive_seed(exam_id, [r.secret for r in rows])
        exam.status = "ready"
        audit.append(db, "system", "seed_derived", exam_id, exam.seed_hex)
    db.commit()
    return {"status": exam.status, "revealed": revealed, "of": len(rows)}


def generate(db: Session, exam_id: str, admin: Faculty) -> dict:
    exam = _exam(db, exam_id)
    if exam.status != "ready":
        raise HTTPException(409, f"Exam is {exam.status}; need status 'ready' (all secrets revealed)")
    bp = _bp(exam)
    cands = load_candidates(db, bp)
    short = _shortfall(cands, bp)
    if short:
        raise HTTPException(409, {"error": "not enough approved questions", "shortfall_marks_by_unit": short})
    try:
        sets = solver.generate_sets(cands, bp, exam.seed_hex)
    except InfeasibleError as e:
        raise HTTPException(422, {"error": "infeasible", "reason": str(e)})
    exam.pool_snapshot = json.dumps([c.id for c in cands])
    for k, paper in enumerate(sets):
        db.add(ExamPaper(exam_id=exam_id, label=chr(65 + k), question_ids=json.dumps([c.id for c in paper]),
                         total_marks=sum(c.marks for c in paper), paper_hash=solver.paper_hash(paper)))
    exam.status = "generated"
    audit.append(db, admin.pseudonym, "papers_generated", exam_id,
                 json.dumps({chr(65 + k): solver.paper_hash(p)[:16] for k, p in enumerate(sets)}))
    db.commit()
    return describe(db, exam_id)


def _papers(db: Session, exam_id: str) -> list[tuple[ExamPaper, list[Candidate]]]:
    out = []
    for p in db.scalars(select(ExamPaper).where(ExamPaper.exam_id == exam_id).order_by(ExamPaper.label)):
        ids = json.loads(p.question_ids)
        recs = {r.id: r for r in db.scalars(select(QuestionRecord).where(QuestionRecord.id.in_(ids)))}
        out.append((p, [_to_candidate(recs[i]) for i in ids]))
    return out


def describe(db: Session, exam_id: str) -> dict:
    """Metadata only - question text never leaves the bank before the print stage."""
    exam = _exam(db, exam_id)
    commits = db.scalars(select(ExamCommit).where(ExamCommit.exam_id == exam_id)).all()
    return {
        "id": exam.id, "title": exam.title, "subject": exam.subject, "status": exam.status,
        "required_commits": exam.required_commits, "commits": len(commits),
        "revealed": sum(1 for c in commits if c.secret is not None), "seed": exam.seed_hex,
        "release_approvals": db.scalar(select(func.count()).select_from(ExamRelease).where(ExamRelease.exam_id == exam_id)),
        "blueprint": json.loads(exam.blueprint),
        "sets": {p.label: {"question_ids": json.loads(p.question_ids), **solver.summarize(c)}
                 for p, c in _papers(db, exam_id)},
    }


def verify(db: Session, exam_id: str) -> dict:
    exam = _exam(db, exam_id)
    if exam.status not in ("generated", "released"):
        raise HTTPException(409, "Nothing to verify yet")
    commits = db.scalars(select(ExamCommit).where(ExamCommit.exam_id == exam_id)).all()
    seed_ok = (all(c.secret is not None and commitment_of(c.secret) == c.commitment for c in commits)
               and derive_seed(exam_id, [c.secret for c in commits]) == exam.seed_hex)
    bp = _bp(exam)
    papers = _papers(db, exam_id)
    violations = solver.check_constraints([c for _, c in papers], bp)
    snap = json.loads(exam.pool_snapshot)
    recs = db.scalars(select(QuestionRecord).where(QuestionRecord.id.in_(snap))).all()
    try:
        again = solver.generate_sets(sorted((_to_candidate(r) for r in recs), key=lambda c: c.id), bp, exam.seed_hex)
        reproducible = [[c.id for c in a] for a in again] == [[c.id for c in paper] for _, paper in papers]
    except InfeasibleError:
        reproducible = False
    return {"seed_ok": seed_ok, "constraints_ok": not violations, "violations": violations,
            "reproducible": reproducible}


# ---- release gate: k-of-n custodians must approve before any plaintext paper exists -------------
def release(db: Session, exam_id: str, admin: Faculty) -> dict:
    exam = _exam(db, exam_id)
    if exam.status == "released":
        raise HTTPException(409, "Already released")
    if exam.status != "generated":
        raise HTTPException(409, f"Exam is {exam.status}; papers must be generated first")
    if not db.scalar(select(ExamCommit.id).where(ExamCommit.exam_id == exam_id, ExamCommit.party == admin.pseudonym)):
        raise HTTPException(403, "Only this exam's custodians can approve release")
    if db.scalar(select(ExamRelease.id).where(ExamRelease.exam_id == exam_id, ExamRelease.party == admin.pseudonym)):
        raise HTTPException(409, "You already approved release")
    db.add(ExamRelease(exam_id=exam_id, party=admin.pseudonym))
    db.flush()
    n = db.scalar(select(func.count()).select_from(ExamRelease).where(ExamRelease.exam_id == exam_id))
    audit.append(db, admin.pseudonym, "release_approval", exam_id, f"{n}/{exam.required_commits}")
    if n >= exam.required_commits:
        exam.status = "released"
        audit.append(db, "system", "exam_released", exam_id, f"approvals={n}")
    db.commit()
    return {"status": exam.status, "approvals": n, "required": exam.required_commits}


# ---- rendering ---------------------------------------------------------------------------------
def _epoch(exam: Exam) -> int:
    ts = exam.created_at if exam.created_at.tzinfo else exam.created_at.replace(tzinfo=timezone.utc)
    return int(ts.timestamp())


def _paper(db: Session, exam_id: str, label: str) -> ExamPaper:
    p = db.scalar(select(ExamPaper).where(ExamPaper.exam_id == exam_id, ExamPaper.label == label.upper()))
    if not p:
        raise HTTPException(404, "No such set")
    return p


def _build(db: Session, exam: Exam, paper: ExamPaper) -> dict:
    """Decrypt, integrity-check, and render one set. Returns hashes + the PDF bytes."""
    ids = json.loads(paper.question_ids)
    recs = {r.id: r for r in db.scalars(select(QuestionRecord).where(QuestionRecord.id.in_(ids)))}
    items = []
    for qid in ids:
        rec = recs.get(qid)
        if rec is None:
            raise render.RenderError("integrity: a question of this set is missing")
        q = qstore.load(rec)
        if q.fingerprint() != rec.fingerprint:
            raise render.RenderError("integrity: question content does not match its recorded fingerprint")
        items.append((rec.fingerprint, q))
    if render.sha256("\n".join(fp for fp, _ in items)) != paper.paper_hash:
        raise render.RenderError("integrity: set composition does not match the hash recorded at generation")
    canon = render.build_canonical({"id": exam.id, "title": exam.title, "subject": exam.subject},
                                   paper.label, paper.paper_hash, items)
    tex, warnings = render.to_latex(canon)
    pdf = render.compile_pdf(tex, _epoch(exam))
    return {"canonical_hash": render.sha256(render.canonical_json(canon)), "tex_hash": render.sha256(tex),
            "pdf_hash": render.sha256(pdf), "pdf": pdf, "warnings": warnings}


def _wrap(fn):
    try:
        return fn()
    except render.EngineMissing as e:
        raise HTTPException(503, str(e))
    except render.RenderError as e:
        raise HTTPException(422, {"error": "render_failed", "reason": str(e)})


def _meta(rp: RenderedPaper, **extra) -> dict:
    return {"set": rp.label, "canonical_hash": rp.canonical_hash, "tex_hash": rp.tex_hash,
            "pdf_hash": rp.pdf_hash, "engine": rp.engine, **extra}


def render_paper(db: Session, exam_id: str, label: str, admin: Faculty) -> dict:
    exam = _exam(db, exam_id)
    if exam.status != "released":
        raise HTTPException(409, f"Exam is {exam.status}; custodians must approve release first")
    paper = _paper(db, exam_id, label)
    existing = db.scalar(select(RenderedPaper).where(RenderedPaper.exam_id == exam_id, RenderedPaper.label == paper.label))
    if existing:
        return _meta(existing, already_rendered=True)
    built = _wrap(lambda: _build(db, exam, paper))
    rp = RenderedPaper(exam_id=exam_id, label=paper.label, canonical_hash=built["canonical_hash"],
                       tex_hash=built["tex_hash"], pdf_hash=built["pdf_hash"], engine=render.engine_version(),
                       nonce=b"", ciphertext=b"")
    db.add(rp)
    db.flush()
    rp.nonce, rp.ciphertext = security.encrypt(built["pdf"], aad=f"render:{rp.id}".encode())
    audit.append(db, admin.pseudonym, "paper_rendered", exam_id, f"{paper.label}:{rp.pdf_hash[:16]}")
    db.commit()
    return _meta(rp, already_rendered=False, warnings=built["warnings"], bytes=len(built["pdf"]))


def _stored(db: Session, exam_id: str, label: str) -> tuple[RenderedPaper, bytes]:
    rp = db.scalar(select(RenderedPaper).where(RenderedPaper.exam_id == exam_id, RenderedPaper.label == label.upper()))
    if not rp:
        raise HTTPException(404, "Set has not been rendered")
    return rp, security.decrypt(rp.nonce, rp.ciphertext, f"render:{rp.id}".encode())


def download_pdf(db: Session, exam_id: str, label: str, admin: Faculty) -> bytes:
    rp, pdf = _stored(db, exam_id, label)
    if render.sha256(pdf) != rp.pdf_hash:
        raise HTTPException(500, "Stored PDF failed its integrity check - do not print")
    audit.append(db, admin.pseudonym, "paper_downloaded", exam_id, rp.label)
    db.commit()
    return pdf


def verify_render(db: Session, exam_id: str, label: str) -> dict:
    exam = _exam(db, exam_id)
    rp, pdf = _stored(db, exam_id, label)
    built = _wrap(lambda: _build(db, exam, _paper(db, exam_id, label)))
    same_engine = rp.engine == render.engine_version()
    res = {"stored_pdf_intact": render.sha256(pdf) == rp.pdf_hash,
           "canonical_ok": built["canonical_hash"] == rp.canonical_hash,
           "tex_ok": built["tex_hash"] == rp.tex_hash,
           "pdf_ok": built["pdf_hash"] == rp.pdf_hash, "engine_same": same_engine}
    res["reproducible"] = all(res[k] for k in ("stored_pdf_intact", "canonical_ok", "tex_ok", "pdf_ok"))
    return res
