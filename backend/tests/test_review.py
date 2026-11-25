from app import audit
from app.db import SessionLocal
from app.models import AuditEvent, QuestionRecord
from conftest import make_headers, sample_question

TOPICS = ["derivative of a polynomial", "limit of a rational function", "definite integral of sine",
          "partial derivative of two variables", "Taylor series of exponential", "gradient of a scalar field"]


def seed(client, headers, units=(1, 1, 2, 2)):
    qs = [sample_question(stem=f"Explain how to compute the {TOPICS[i]} with one worked example.",
                          qtype="short", options=None, correct_option=None, unit=u)
          for i, u in enumerate(units)]
    r = client.post("/submissions", json={"questions": qs, "rights_declared": True}, headers=headers)
    assert r.status_code == 201


def build(client, admin, units=None, seed_=1):
    return client.post("/moderation/pool/build", headers=admin,
                       json={"subject": "maths", "units": units or {"1": 1, "2": 2}, "seed": seed_})


def rv(decision="approve", quality=4, difficulty=0.5, comment=""):
    return {"decision": decision, "quality": quality, "difficulty": difficulty, "comment": comment}


def setup(client, auth_headers, admin_headers):
    seed(client, auth_headers)
    assert build(client, admin_headers).status_code == 200
    r2, r3 = make_headers(client, "r2@juit.ac.in"), make_headers(client, "r3@juit.ac.in")
    qid = client.get("/review/queue", headers=r2).json()[0]["question_id"]
    return qid, r2, r3


def test_pool_is_stratified_and_reports_shortfall(client, auth_headers, admin_headers):
    seed(client, auth_headers)
    r = build(client, admin_headers).json()
    assert r["selected"] == 3 and r["by_unit"] == {"1": 1, "2": 2} and r["shortfall"] == {}
    r2 = build(client, admin_headers, {"1": 5, "3": 2}).json()      # only 1 unit-1 left, no unit 3
    assert r2["by_unit"] == {"1": 1, "3": 0} and r2["shortfall"] == {"1": 4, "3": 2}


def test_pool_build_admin_only(client, auth_headers):
    assert build(client, auth_headers).status_code == 403


def test_queue_is_blind_and_excludes_own_questions(client, admin_headers):
    r1 = make_headers(client, "r1@juit.ac.in")
    seed(client, r1)
    build(client, admin_headers, {"1": 2, "2": 2})
    assert client.get("/review/queue", headers=r1).json() == []          # all authored by r1
    r2 = make_headers(client, "r2@juit.ac.in")
    items = client.get("/review/queue", headers=r2).json()
    assert len(items) == 4
    blob = str(items)
    assert "difficulty" not in blob and "pseudonym" not in blob and "FAC-" not in blob
    assert "stem" in items[0]


def test_non_reviewer_blocked(client, auth_headers):
    assert client.get("/review/queue", headers=auth_headers).status_code == 403


def test_two_approvals_approve_and_rerate_difficulty(client, auth_headers, admin_headers):
    qid, r2, r3 = setup(client, auth_headers, admin_headers)
    assert client.post(f"/review/{qid}", json=rv(difficulty=0.4), headers=r2).json()["status"] == "in_pool"
    assert client.post(f"/review/{qid}", json=rv(difficulty=0.6), headers=r3).json()["status"] == "approved"
    with SessionLocal() as db:
        assert abs(db.get(QuestionRecord, qid).difficulty - 0.5) < 1e-9
    assert client.post(f"/review/{qid}", json=rv(), headers=r2).status_code == 409   # closed


def test_two_rejections_reject(client, auth_headers, admin_headers):
    qid, r2, r3 = setup(client, auth_headers, admin_headers)
    client.post(f"/review/{qid}", json=rv("reject", 1), headers=r2)
    assert client.post(f"/review/{qid}", json=rv("reject", 2), headers=r3).json()["status"] == "rejected"
    assert all(i["question_id"] != qid for i in client.get("/review/queue", headers=r2).json())


def test_disagreement_goes_to_moderation_and_sme_decides(client, auth_headers, admin_headers):
    qid, r2, r3 = setup(client, auth_headers, admin_headers)
    client.post(f"/review/{qid}", json=rv("approve", 5, comment="good"), headers=r2)
    assert client.post(f"/review/{qid}", json=rv("reject", 2, comment="ambiguous"), headers=r3).json()["status"] == "moderation"
    q = [x for x in client.get("/moderation/queue", headers=admin_headers).json() if x["question_id"] == qid][0]
    assert {r["reviewer"] for r in q["reviews"]} == {"R1", "R2"} and "FAC-" not in str(q)
    assert client.post(f"/moderation/{qid}/decide", json={"decision": "approve", "difficulty": 0.7}, headers=auth_headers).status_code == 403
    assert client.post(f"/moderation/{qid}/decide", json={"decision": "approve", "difficulty": 0.7}, headers=admin_headers).json()["status"] == "approved"
    with SessionLocal() as db:
        assert db.get(QuestionRecord, qid).difficulty == 0.7
    assert client.post(f"/moderation/{qid}/decide", json={"decision": "reject"}, headers=admin_headers).status_code == 409


def test_cannot_review_own_or_twice(client, admin_headers):
    r1 = make_headers(client, "r1@juit.ac.in")
    seed(client, r1)
    build(client, admin_headers, {"1": 2, "2": 2})
    with SessionLocal() as db:
        qid = db.query(QuestionRecord).first().id
    assert client.post(f"/review/{qid}", json=rv(), headers=r1).status_code == 403
    r2 = make_headers(client, "r2@juit.ac.in")
    assert client.post(f"/review/{qid}", json=rv(), headers=r2).status_code == 200
    assert client.post(f"/review/{qid}", json=rv(), headers=r2).status_code == 409


def test_low_scores_even_if_approved_go_to_moderation(client, auth_headers, admin_headers):
    qid, r2, r3 = setup(client, auth_headers, admin_headers)
    client.post(f"/review/{qid}", json=rv("approve", 2), headers=r2)
    assert client.post(f"/review/{qid}", json=rv("approve", 3), headers=r3).json()["status"] == "moderation"


def test_correction_interface(client, auth_headers, admin_headers):
    qid, r2, _ = setup(client, auth_headers, admin_headers)
    ok = client.post(f"/review/{qid}/correction", json={"stem": "Fixed stem: explain $x^2$ differentiation clearly."}, headers=r2)
    assert ok.status_code == 200 and ok.json()["corrected"] == ["stem"]
    shown = [i for i in client.get("/review/queue", headers=r2).json() if i["question_id"] == qid][0]
    assert shown["stem"].startswith("Fixed stem")
    bad = client.post(f"/review/{qid}/correction", json={"stem": r"Broken $math never closed here."}, headers=r2)
    assert bad.status_code == 422 and "UNBALANCED_MATH" in str(bad.json())
    assert client.post(f"/review/{qid}/correction", json={}, headers=r2).status_code == 422
    assert client.post(f"/review/{qid}/correction", json={"stem": "anything at all here"}, headers=auth_headers).status_code == 403


def test_audit_chain_detects_tampering(client, auth_headers, admin_headers):
    qid, r2, r3 = setup(client, auth_headers, admin_headers)
    client.post(f"/review/{qid}", json=rv(), headers=r2)
    v = client.get("/moderation/audit/verify", headers=admin_headers).json()
    assert v["ok"] and v["length"] >= 4
    with SessionLocal() as db:
        ev = db.query(AuditEvent).filter(AuditEvent.event_type == "review_submitted").first()
        ev.detail = "reject"           # rewrite history
        db.commit()
        assert audit.verify(db)["ok"] is False
    assert client.get("/moderation/audit/verify", headers=admin_headers).json()["broken_at"] is not None
