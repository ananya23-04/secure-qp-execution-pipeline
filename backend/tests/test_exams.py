import hashlib

import pytest

from app import exam_service, solver
from app.db import SessionLocal
from app.models import QuestionRecord, ReviewItem
from conftest import make_headers, sample_question

BLUEPRINT = {
    "subject": "Maths", "num_sets": 3, "total_marks": 30,
    "units": {"1": 10, "2": 10, "3": 10},
    "difficulty_mix": {"easy": 0.3, "medium": 0.5, "hard": 0.2}, "difficulty_tolerance": 0.2,
    "qtype_marks": {"mcq": 5, "short": 10, "long": 15},
    "min_higher_order_pct": 10, "max_overlap_pct": 40,
}


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


@pytest.fixture()
def bank(client, auth_headers):
    """60 faculty questions, all pushed straight to 'approved' (review stage is tested elsewhere)."""
    bloom = ["remember", "understand", "apply", "analyze", "evaluate", "create"]
    qs = []
    for i in range(60):
        marks = [1, 2, 5][(i // 3) % 3]
        qt = {1: "mcq", 2: "short", 5: "long"}[marks]
        kw = dict(qtype=qt, unit=1 + i % 3, marks=marks, difficulty=((i * 37) % 100) / 100,
                  bloom=bloom[i % 6], stem=f"Item {i}: discuss concept number {i * 7} of the syllabus in depth.")
        if qt != "mcq":
            kw.update(options=None, correct_option=None)
        qs.append(sample_question(**kw))
    r = client.post("/submissions", json={"questions": qs, "rights_declared": True}, headers=auth_headers)
    assert r.status_code == 201
    with SessionLocal() as db:
        for rec in db.query(QuestionRecord).filter(QuestionRecord.status.in_(["unique", "near_duplicate"])):
            db.add(ReviewItem(question_id=rec.id, pool_id="test", status="approved"))
        db.commit()


def admins(client):
    return [make_headers(client, e) for e in ("admin@juit.ac.in", "admin2@juit.ac.in", "admin3@juit.ac.in")]


def run_exam(client, hs, blueprint=BLUEPRINT, secrets=("alpha-secret-0001xx", "bravo-secret-0002xx", "charlie-secret-03xxx")):
    ex = client.post("/exams", json={"title": "Term Exam", "blueprint": blueprint, "required_commits": len(hs)}, headers=hs[0])
    assert ex.status_code == 201, ex.text
    eid = ex.json()["id"]
    for h, s in zip(hs, secrets):
        assert client.post(f"/exams/{eid}/commit", json={"commitment": sha(s)}, headers=h).status_code == 200
    for h, s in zip(hs, secrets):
        assert client.post(f"/exams/{eid}/reveal", json={"secret": s}, headers=h).status_code == 200
    return eid


def test_blueprint_validation(client, bank):
    h = admins(client)[0]
    bad = {**BLUEPRINT, "units": {"1": 10, "2": 10, "3": 5}}
    assert client.post("/exams", json={"title": "x y z", "blueprint": bad}, headers=h).status_code == 422
    bad = {**BLUEPRINT, "difficulty_mix": {"easy": 0.5, "hard": 0.1}}
    assert client.post("/exams", json={"title": "x y z", "blueprint": bad}, headers=h).status_code == 422
    bad = {**BLUEPRINT, "qtype_marks": {"mcq": 5, "short": 5, "long": 5}}
    assert client.post("/exams", json={"title": "x y z", "blueprint": bad}, headers=h).status_code == 422


def test_requires_admin_and_enough_questions(client, bank, auth_headers):
    assert client.post("/exams", json={"title": "abc", "blueprint": BLUEPRINT}, headers=auth_headers).status_code == 403
    h = admins(client)[0]
    big = {**BLUEPRINT, "units": {"1": 10, "2": 10, "3": 480}, "total_marks": 500, "qtype_marks": None}
    r = client.post("/exams", json={"title": "abc", "blueprint": big}, headers=h)
    assert r.status_code == 409 and "3" in str(r.json())


def test_full_flow_sets_satisfy_every_constraint(client, bank):
    hs = admins(client)
    eid = run_exam(client, hs)
    gen = client.post(f"/exams/{eid}/generate", headers=hs[0])
    assert gen.status_code == 200, gen.text
    ex = gen.json()
    assert ex["status"] == "generated" and set(ex["sets"]) == {"A", "B", "C"}
    for lab, s in ex["sets"].items():
        assert s["total_marks"] == 30
        assert s["marks_by_unit"] == {"1": 10, "2": 10, "3": 10}
        assert s["marks_by_qtype"] == {"mcq": 5, "short": 10, "long": 15}
        assert s["higher_order_marks"] >= 3
    prof = [tuple(s["marks_by_difficulty"].values()) for s in ex["sets"].values()]
    assert len(set(prof)) == 1                                         # identical difficulty profile
    ids = {k: set(v["question_ids"]) for k, v in ex["sets"].items()}
    assert len(ids["A"] & ids["B"]) < len(ids["A"]) and ids["A"] != ids["B"]
    v = client.get(f"/exams/{eid}/verify", headers=hs[0]).json()
    assert v == {"seed_ok": True, "constraints_ok": True, "violations": [], "reproducible": True}
    assert "stem" not in str(ex)                                       # metadata only, no plaintext


def test_same_secrets_same_papers_different_secrets_different_papers(client, bank):
    hs = admins(client)
    e1 = run_exam(client, hs)
    p1 = client.post(f"/exams/{e1}/generate", headers=hs[0]).json()["sets"]
    e2 = run_exam(client, hs)
    p2 = client.post(f"/exams/{e2}/generate", headers=hs[0]).json()["sets"]
    # different exam ids -> different seeds even with the same secrets
    assert p1["A"]["question_ids"] != p2["A"]["question_ids"]
    # but the solver itself is deterministic for a fixed seed
    with SessionLocal() as db:
        bp = solver.ExamBlueprint(**BLUEPRINT)
        cands = exam_service.load_candidates(db, bp)
    a = solver.generate_sets(cands, bp, "ab" * 32)
    b = solver.generate_sets(cands, bp, "ab" * 32)
    c = solver.generate_sets(cands, bp, "cd" * 32)
    assert [[x.id for x in s] for s in a] == [[x.id for x in s] for s in b]
    assert [[x.id for x in s] for s in a] != [[x.id for x in s] for s in c]


def test_commit_reveal_protocol_rules(client, bank):
    hs = admins(client)
    eid = client.post("/exams", json={"title": "Protocol", "blueprint": BLUEPRINT, "required_commits": 2}, headers=hs[0]).json()["id"]
    s1, s2 = "first-secret-value-1", "second-secret-value-2"
    assert client.post(f"/exams/{eid}/reveal", json={"secret": s1}, headers=hs[0]).status_code == 409     # too early
    assert client.post(f"/exams/{eid}/generate", headers=hs[0]).status_code == 409
    assert client.post(f"/exams/{eid}/commit", json={"commitment": sha(s1)}, headers=hs[0]).status_code == 200
    assert client.post(f"/exams/{eid}/commit", json={"commitment": sha(s1)}, headers=hs[0]).status_code == 409  # twice
    assert client.post(f"/exams/{eid}/commit", json={"commitment": "zz"}, headers=hs[1]).status_code == 422
    assert client.post(f"/exams/{eid}/reveal", json={"secret": s1}, headers=hs[0]).status_code == 409     # others not committed
    client.post(f"/exams/{eid}/commit", json={"commitment": sha(s2)}, headers=hs[1])
    assert client.post(f"/exams/{eid}/commit", json={"commitment": sha(s2)}, headers=hs[2]).status_code == 409  # closed
    assert client.post(f"/exams/{eid}/reveal", json={"secret": s1}, headers=hs[2]).status_code == 403     # never committed
    assert client.post(f"/exams/{eid}/reveal", json={"secret": "wrong-secret-value-9"}, headers=hs[0]).status_code == 422
    assert client.post(f"/exams/{eid}/reveal", json={"secret": s1}, headers=hs[0]).status_code == 200
    assert client.post(f"/exams/{eid}/reveal", json={"secret": s1}, headers=hs[0]).status_code == 409     # twice
    assert client.get(f"/exams/{eid}", headers=hs[0]).json()["seed"] is None       # not all revealed yet
    client.post(f"/exams/{eid}/reveal", json={"secret": s2}, headers=hs[1])
    d = client.get(f"/exams/{eid}", headers=hs[0]).json()
    assert d["status"] == "ready" and d["seed"] == exam_service.derive_seed(eid, [s1, s2])


def test_infeasible_blueprint_reports_reason(client, bank):
    hs = admins(client)
    tight = {**BLUEPRINT, "max_overlap_pct": 0, "num_sets": 6, "difficulty_tolerance": 0.0,
             "units": {"1": 25, "2": 3, "3": 2}, "qtype_marks": {"mcq": 10, "short": 10, "long": 10}}
    eid = run_exam(client, hs, tight)
    r = client.post(f"/exams/{eid}/generate", headers=hs[0])
    assert r.status_code == 422 and r.json()["detail"]["error"] == "infeasible"


def test_exam_flow_is_audited(client, bank):
    hs = admins(client)
    eid = run_exam(client, hs)
    client.post(f"/exams/{eid}/generate", headers=hs[0])
    v = client.get("/moderation/audit/verify", headers=hs[0]).json()
    assert v["ok"] and v["length"] >= 10
