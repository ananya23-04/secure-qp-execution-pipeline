import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import UniqueConstraint, DateTime, Enum, Float, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SubmissionStatus(str, enum.Enum):
    RAW_INGESTED = "raw_ingested"
    VALIDATED = "validated"
    DEDUPLICATED = "deduplicated"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"


class Faculty(Base):
    """Identity table. Only the auth layer touches this; content tables never join to it."""
    __tablename__ = "faculty"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    institution: Mapped[str] = mapped_column(String(120))
    pseudonym: Mapped[str] = mapped_column(String(20), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Submission(Base):
    """Raw question bank storage: AES-256-GCM ciphertext + pseudonym only."""
    __tablename__ = "submissions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    pseudonym: Mapped[str] = mapped_column(ForeignKey("faculty.pseudonym"), index=True)
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.RAW_INGESTED
    )
    nonce: Mapped[bytes] = mapped_column(LargeBinary(12))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    question_count: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class QuestionStatus(str, enum.Enum):
    UNIQUE = "unique"
    NEAR_DUPLICATE = "near_duplicate"   # kept, tagged for reviewers
    DUPLICATE = "duplicate"             # exact match: eliminated
    INVALID = "invalid"                 # failed convert & validate


class QuestionRecord(Base):
    """One processed question. Text is AES-256-GCM encrypted; only metadata the
    solver needs (unit/bloom/difficulty/marks) is stored in the clear."""
    __tablename__ = "questions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    submission_id: Mapped[str] = mapped_column(ForeignKey("submissions.id"), index=True)
    idx: Mapped[int] = mapped_column(Integer)
    pseudonym: Mapped[str] = mapped_column(String(20), index=True)
    status: Mapped[QuestionStatus] = mapped_column(Enum(QuestionStatus), index=True)
    issues: Mapped[str] = mapped_column(Text, default="")          # comma-separated issue codes
    fingerprint: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    duplicate_of: Mapped[str | None] = mapped_column(String(32), nullable=True)
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    qtype: Mapped[str] = mapped_column(String(10))
    subject: Mapped[str] = mapped_column(String(120), index=True)
    unit: Mapped[int] = mapped_column(Integer)
    bloom: Mapped[str] = mapped_column(String(16))
    difficulty: Mapped[float] = mapped_column(Float)
    marks: Mapped[int] = mapped_column(Integer)
    nonce: Mapped[bytes] = mapped_column(LargeBinary(12))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ReviewItem(Base):
    """Review state per question. String status (no native enum) so it needs no migration:
    in_pool -> approved | rejected | moderation -> approved | rejected."""
    __tablename__ = "review_items"
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), primary_key=True)
    pool_id: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), index=True, default="in_pool")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("question_id", "reviewer", name="one_review_per_reviewer"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    question_id: Mapped[str] = mapped_column(ForeignKey("questions.id"), index=True)
    reviewer: Mapped[str] = mapped_column(String(20))      # pseudonym; never shown to moderators
    decision: Mapped[str] = mapped_column(String(8))
    quality: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[float] = mapped_column(Float)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AuditEvent(Base):
    """Append-only, hash-chained log (stand-in for the Hyperledger Fabric adapter)."""
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(20))
    event_type: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str] = mapped_column(Text, default="")
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64))


class Exam(Base):
    """One exam-generation run: blueprint -> commit-reveal seed -> Sets A/B/C."""
    __tablename__ = "exams"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    title: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(120))
    blueprint: Mapped[str] = mapped_column(Text)                       # ExamBlueprint JSON
    required_commits: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="committing")  # committing|revealing|ready|generated
    seed_hex: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pool_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)  # candidate ids used (JSON)
    created_by: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ExamCommit(Base):
    __tablename__ = "exam_commits"
    __table_args__ = (UniqueConstraint("exam_id", "party", name="one_commit_per_party"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id"), index=True)
    party: Mapped[str] = mapped_column(String(20))
    commitment: Mapped[str] = mapped_column(String(64))
    secret: Mapped[str | None] = mapped_column(String(200), nullable=True)   # filled on reveal
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ExamPaper(Base):
    """A generated set. Stores question ids + a content hash only - never plaintext."""
    __tablename__ = "exam_papers"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id"), index=True)
    label: Mapped[str] = mapped_column(String(2))
    question_ids: Mapped[str] = mapped_column(Text)     # ordered JSON list
    total_marks: Mapped[int] = mapped_column(Integer)
    paper_hash: Mapped[str] = mapped_column(String(64))


class AuditHead(Base):
    """Single row every audit append updates first. The row lock serialises concurrent writers until
    their transaction commits, so two events can never claim the same previous hash."""
    __tablename__ = "audit_heads"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    counter: Mapped[int] = mapped_column(Integer, default=0)


class ExamRelease(Base):
    """Custodian approvals needed before any plaintext paper can be rendered (k-of-n release gate)."""
    __tablename__ = "exam_releases"
    __table_args__ = (UniqueConstraint("exam_id", "party", name="one_release_per_party"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id"), index=True)
    party: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RenderedPaper(Base):
    """Rendered PDF, AES-256-GCM encrypted at rest, plus the hashes that make it verifiable.
    The LaTeX source is never stored - only its hash."""
    __tablename__ = "rendered_papers"
    __table_args__ = (UniqueConstraint("exam_id", "label", name="one_render_per_set"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_id)
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id"), index=True)
    label: Mapped[str] = mapped_column(String(2))
    canonical_hash: Mapped[str] = mapped_column(String(64))
    tex_hash: Mapped[str] = mapped_column(String(64))
    pdf_hash: Mapped[str] = mapped_column(String(64))
    engine: Mapped[str] = mapped_column(String(160))
    nonce: Mapped[bytes] = mapped_column(LargeBinary(12))
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
