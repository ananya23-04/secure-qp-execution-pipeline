from . import security
from .models import QuestionRecord
from .question_schema import Question


def load(rec: QuestionRecord) -> Question:
    return Question.model_validate_json(security.decrypt(rec.nonce, rec.ciphertext, rec.id.encode()))


def store(rec: QuestionRecord, q: Question) -> None:
    rec.nonce, rec.ciphertext = security.encrypt(q.model_dump_json().encode(), rec.id.encode())
