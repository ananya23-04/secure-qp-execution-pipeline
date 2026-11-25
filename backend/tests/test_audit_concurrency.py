import threading

from app import audit
from app.db import SessionLocal


def test_concurrent_appends_keep_chain_intact(client):
    errors = []

    def worker(k):
        try:
            for j in range(5):
                with SessionLocal() as db:
                    audit.append(db, f"actor{k}", "evt", f"s{k}-{j}", "x")
                    db.commit()
        except Exception as e:           # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert not errors, errors
    with SessionLocal() as db:
        v = audit.verify(db)
    assert v["ok"] and v["length"] == 40, v
