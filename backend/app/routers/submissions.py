from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, pipeline, security
from ..db import get_db
from ..deps import current_faculty
from ..models import Faculty, Submission, _id
from ..question_schema import SubmissionIn

router = APIRouter(prefix="/submissions", tags=["submissions"])


@router.post("", status_code=201)
def submit(body: SubmissionIn, bg: BackgroundTasks, faculty: Faculty = Depends(current_faculty),
           db: Session = Depends(get_db)):
    sid = _id()
    nonce, ct = security.encrypt(body.model_dump_json().encode(), aad=sid.encode())
    db.add(Submission(id=sid, pseudonym=faculty.pseudonym, nonce=nonce, ciphertext=ct,
                      question_count=len(body.questions)))
    audit.append(db, faculty.pseudonym, "submission_received", sid, f"questions={len(body.questions)}")
    db.commit()
    bg.add_task(pipeline.run_pipeline_task, sid)   # validate + dedup right after ingest
    return {"id": sid, "status": "raw_ingested", "question_count": len(body.questions)}


@router.get("/mine")
def mine(faculty: Faculty = Depends(current_faculty), db: Session = Depends(get_db)):
    rows = db.scalars(select(Submission).where(Submission.pseudonym == faculty.pseudonym)).all()
    return [
        {"id": r.id, "status": r.status.value, "question_count": r.question_count,
         "created_at": r.created_at.isoformat()}
        for r in rows
    ]


@router.get("/{submission_id}/report")
def report(submission_id: str, faculty: Faculty = Depends(current_faculty), db: Session = Depends(get_db)):
    """Per-question outcome for the owner. Never reveals which other question matched."""
    sub = db.get(Submission, submission_id)
    if not sub or sub.pseudonym != faculty.pseudonym:
        raise HTTPException(404, "Submission not found")
    return pipeline.summarize(db, submission_id)
