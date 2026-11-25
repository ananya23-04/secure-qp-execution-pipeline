"""Canonical question schema: the single format every later stage consumes
(dedup, validation, review, ILP solver, LaTeX renderer)."""
import hashlib
import re
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class Bloom(str, Enum):
    REMEMBER = "remember"
    UNDERSTAND = "understand"
    APPLY = "apply"
    ANALYZE = "analyze"
    EVALUATE = "evaluate"
    CREATE = "create"


class QType(str, Enum):
    MCQ = "mcq"
    SHORT = "short"
    LONG = "long"


class Question(BaseModel):
    qtype: QType
    stem: str = Field(min_length=10, description="Question text; may contain LaTeX in $...$")
    options: list[str] | None = None
    correct_option: int | None = None
    solution_latex: str | None = None
    subject: str = Field(min_length=2)
    unit: int = Field(ge=1, description="Syllabus unit number")
    bloom: Bloom
    difficulty: float = Field(ge=0.0, le=1.0)
    marks: int = Field(gt=0)

    @model_validator(mode="after")
    def _check_mcq(self):
        if self.qtype == QType.MCQ:
            if not self.options or not 2 <= len(self.options) <= 6:
                raise ValueError("MCQ needs 2-6 options")
            if self.correct_option is None or not 0 <= self.correct_option < len(self.options):
                raise ValueError("MCQ needs a valid correct_option index")
        return self

    def fingerprint(self) -> str:
        """SHA-256 of normalised content -> exact-duplicate detection (stage 2)."""
        norm = lambda s: re.sub(r"\s+", " ", s.strip().lower())
        parts = [norm(self.stem)] + [norm(o) for o in (self.options or [])]
        return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


class SubmissionIn(BaseModel):
    questions: list[Question] = Field(min_length=1, max_length=500)
    rights_declared: bool = Field(description="Faculty confirms origin and rights")

    @model_validator(mode="after")
    def _need_rights(self):
        if not self.rights_declared:
            raise ValueError("Origin & rights declaration must be signed")
        return self
