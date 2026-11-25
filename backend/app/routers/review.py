from collections import Counter

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import audit, review_service as svc
from ..db import get_db
from ..deps import require_admin, require_reviewer, require_reviewer_or_admin
from ..models import Faculty, Review, ReviewItem

router = APIRouter(prefix="/review", tags=["review (blind panel)"])
moderation = APIRouter(prefix="/moderation", tags=["moderation (admin / SME)"],
                       dependencies=[Depends(require_admin)])


# ---- reviewers --------------------------------------------------------------
@router.get("/queue")
def queue(limit: int = Query(5, ge=1, le=20), reviewer: Faculty = Depends(require_reviewer),
          db: Session = Depends(get_db)):
    """Anonymous items to review: no author, no author-claimed difficulty, no other scores."""
    return svc.queue_for(db, reviewer, limit)


@router.post("/{question_id}")
def review(question_id: str, body: svc.ReviewIn, reviewer: Faculty = Depends(require_reviewer),
           db: Session = Depends(get_db)):
    return svc.submit_review(db, question_id, reviewer, body)


@router.post("/{question_id}/correction")
def correction(question_id: str, body: svc.CorrectionIn, actor: Faculty = Depends(require_reviewer_or_admin),
               db: Session = Depends(get_db)):
    return svc.apply_correction(db, question_id, actor, body)


@router.get("/mine/history")
def history(reviewer: Faculty = Depends(require_reviewer), db: Session = Depends(get_db)):
    rows = db.scalars(select(Review).where(Review.reviewer == reviewer.pseudonym)).all()
    return [{"question_id": r.question_id, "decision": r.decision, "quality": r.quality} for r in rows]


# ---- moderators (admin) -----------------------------------------------------
@moderation.post("/pool/build")
def build_pool(bp: svc.Blueprint, admin: Faculty = Depends(require_admin), db: Session = Depends(get_db)):
    """Random Set Generator: stratified-by-unit random sample into the anonymous review pool."""
    return svc.build_pool(db, bp, admin)


@moderation.get("/queue")
def mod_queue(db: Session = Depends(get_db)):
    return svc.moderation_queue(db)


@moderation.post("/{question_id}/decide")
def decide(question_id: str, body: svc.DecisionIn, admin: Faculty = Depends(require_admin),
           db: Session = Depends(get_db)):
    return svc.moderate(db, question_id, admin, body)


@moderation.get("/stats")
def stats(db: Session = Depends(get_db)):
    return dict(Counter(db.scalars(select(ReviewItem.status))))


@moderation.get("/audit/verify")
def verify_audit(db: Session = Depends(get_db)):
    return audit.verify(db)
