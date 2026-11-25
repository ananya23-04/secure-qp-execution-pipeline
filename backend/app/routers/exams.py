from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import exam_service as svc
from ..db import get_db
from ..deps import require_admin
from ..models import Exam, Faculty

router = APIRouter(prefix="/exams", tags=["exams (QP generator, admin)"], dependencies=[Depends(require_admin)])


@router.post("", status_code=201)
def create(body: svc.ExamCreate, admin: Faculty = Depends(require_admin), db: Session = Depends(get_db)):
    """Create an exam from a blueprint. Needs enough approved questions in the bank."""
    return svc.create_exam(db, body, admin)


@router.get("")
def list_exams(db: Session = Depends(get_db)):
    return [{"id": e.id, "title": e.title, "status": e.status} for e in db.scalars(select(Exam))]


@router.get("/{exam_id}")
def get(exam_id: str, db: Session = Depends(get_db)):
    return svc.describe(db, exam_id)


@router.post("/{exam_id}/commit")
def commit(exam_id: str, body: svc.CommitIn, admin: Faculty = Depends(require_admin), db: Session = Depends(get_db)):
    """Custodian posts sha256(secret). All commitments must be in before anyone can reveal."""
    return svc.commit(db, exam_id, admin, body)


@router.post("/{exam_id}/reveal")
def reveal(exam_id: str, body: svc.RevealIn, admin: Faculty = Depends(require_admin), db: Session = Depends(get_db)):
    return svc.reveal(db, exam_id, admin, body)


@router.post("/{exam_id}/generate")
def generate(exam_id: str, admin: Faculty = Depends(require_admin), db: Session = Depends(get_db)):
    """Run the CP-SAT solver with the commit-reveal seed to build Sets A/B/C."""
    return svc.generate(db, exam_id, admin)


@router.get("/{exam_id}/verify")
def verify(exam_id: str, db: Session = Depends(get_db)):
    """Check seed derivation, re-audit every constraint, and re-run the solver to confirm reproducibility."""
    return svc.verify(db, exam_id)


@router.post("/{exam_id}/release")
def release(exam_id: str, admin: Faculty = Depends(require_admin), db: Session = Depends(get_db)):
    """Custodian approves release. Rendering unlocks only when every custodian has approved."""
    return svc.release(db, exam_id, admin)


@router.post("/{exam_id}/papers/{label}/render")
def render_paper(exam_id: str, label: str, admin: Faculty = Depends(require_admin), db: Session = Depends(get_db)):
    """Canonical JSON -> LaTeX -> PDF (deterministic, hash-recorded, stored encrypted). Needs release."""
    return svc.render_paper(db, exam_id, label, admin)


@router.get("/{exam_id}/papers/{label}/pdf")
def download(exam_id: str, label: str, admin: Faculty = Depends(require_admin), db: Session = Depends(get_db)):
    pdf = svc.download_pdf(db, exam_id, label, admin)       # every download is audited
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="exam-{exam_id[:8]}-set-{label.upper()}.pdf"',
        "Cache-Control": "no-store"})


@router.get("/{exam_id}/papers/{label}/render-verify")
def render_verify(exam_id: str, label: str, db: Session = Depends(get_db)):
    """Re-render from the encrypted bank and compare canonical/LaTeX/PDF hashes with the stored ones."""
    return svc.verify_render(db, exam_id, label)
