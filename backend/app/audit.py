"""Hash-chained audit log. Each event commits to the previous one, so any edit or
deletion in the middle is detectable. Swap for Hyperledger Fabric later behind append()/verify()."""
import hashlib
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import AuditEvent, AuditHead

GENESIS = "0" * 64


def _digest(prev: str, ts: str, actor: str, etype: str, subject: str, detail: str) -> str:
    return hashlib.sha256("\x1f".join([prev, ts, actor, etype, subject, detail]).encode()).hexdigest()


def _lock(db: Session) -> None:
    """Take the head-row write lock (held until this transaction commits/rolls back)."""
    bump = update(AuditHead).where(AuditHead.id == 1).values(counter=AuditHead.counter + 1)
    if db.execute(bump).rowcount == 0:
        try:
            with db.begin_nested():
                db.add(AuditHead(id=1, counter=1))
                db.flush()
        except IntegrityError:          # another writer created it first
            db.execute(bump)


def append(db: Session, actor: str, event_type: str, subject: str, detail: str = "") -> AuditEvent:
    _lock(db)                           # serialise writers BEFORE reading the previous hash
    last = db.scalar(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(1))
    prev = last.hash if last else GENESIS
    ts = datetime.now(timezone.utc).isoformat()
    ev = AuditEvent(ts=ts, actor=actor, event_type=event_type, subject=subject, detail=detail,
                    prev_hash=prev, hash=_digest(prev, ts, actor, event_type, subject, detail))
    db.add(ev)
    db.flush()          # sessions run with autoflush off; keep the chain order correct
    return ev


def verify(db: Session) -> dict:
    prev, n = GENESIS, 0
    for ev in db.scalars(select(AuditEvent).order_by(AuditEvent.id)):
        n += 1
        if ev.prev_hash != prev or ev.hash != _digest(prev, ev.ts, ev.actor, ev.event_type, ev.subject, ev.detail):
            return {"ok": False, "length": n, "broken_at": ev.id}
        prev = ev.hash
    return {"ok": True, "length": n, "broken_at": None}
