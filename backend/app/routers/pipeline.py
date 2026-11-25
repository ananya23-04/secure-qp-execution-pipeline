from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import pipeline
from ..db import get_db
from ..deps import require_admin
from ..models import QuestionRecord, QuestionStatus, Submission

router = APIRouter(prefix="/pipeline", tags=["pipeline (admin)"], dependencies=[Depends(require_admin)])


@router.post("/run/{submission_id}")
def run(submission_id: str, db: Session = Depends(get_db)):
    """Re-run processing for a submission still in raw_ingested (e.g. after a crash)."""
    try:
        return pipeline.process_submission(db, submission_id)
    except LookupError:
        raise HTTPException(404, "Submission not found")


@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    q = Counter(s.value for s in db.scalars(select(QuestionRecord.status)))
    s = Counter(x.value for x in db.scalars(select(Submission.status)))
    return {"questions": dict(q), "submissions": dict(s)}


@router.get("/duplicates")
def duplicates(db: Session = Depends(get_db)):
    """IDs only - admins see links between records, never question text or authors."""
    rows = db.scalars(select(QuestionRecord).where(
        QuestionRecord.status.in_([QuestionStatus.DUPLICATE, QuestionStatus.NEAR_DUPLICATE])
    )).all()
    return [{"question_id": r.id, "status": r.status.value, "duplicate_of": r.duplicate_of,
             "similarity": r.similarity} for r in rows]
