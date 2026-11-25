from sqlalchemy import select

from app import security
from app.db import SessionLocal
from app.models import Faculty, Submission
from app.question_schema import Question
from conftest import sample_question


def test_register_login_and_pseudonym(client):
    r = client.post("/auth/register", json={"email": "x@juit.ac.in", "password": "supersecret123", "institution": "JUIT"})
    assert r.status_code == 201 and r.json()["pseudonym"].startswith("FAC-")
    assert client.post("/auth/register", json={"email": "x@juit.ac.in", "password": "supersecret123", "institution": "JUIT"}).status_code == 409
    assert client.post("/auth/login", json={"email": "x@juit.ac.in", "password": "wrongpassword!"}).status_code == 401


def test_submission_requires_auth(client):
    assert client.post("/submissions", json={}).status_code in (401, 403)


def test_submission_encrypted_at_rest_and_roundtrips(client, auth_headers):
    body = {"questions": [sample_question()], "rights_declared": True}
    r = client.post("/submissions", json=body, headers=auth_headers)
    assert r.status_code == 201
    sid = r.json()["id"]
    with SessionLocal() as db:
        sub = db.get(Submission, sid)
        assert b"derivative" not in sub.ciphertext          # no plaintext stored
        plain = security.decrypt(sub.nonce, sub.ciphertext, sid.encode())
        assert b"derivative" in plain
        # content record carries only the pseudonym, never the email
        fac = db.scalar(select(Faculty))
        assert sub.pseudonym == fac.pseudonym
        assert fac.email.encode() not in sub.ciphertext


def test_ciphertext_bound_to_record_id(client, auth_headers):
    sid = client.post("/submissions", json={"questions": [sample_question()], "rights_declared": True},
                      headers=auth_headers).json()["id"]
    with SessionLocal() as db:
        sub = db.get(Submission, sid)
        try:
            security.decrypt(sub.nonce, sub.ciphertext, b"other-id")
            assert False, "AAD mismatch should fail"
        except Exception:
            pass


def test_rights_declaration_required(client, auth_headers):
    r = client.post("/submissions", json={"questions": [sample_question()], "rights_declared": False}, headers=auth_headers)
    assert r.status_code == 422


def test_mcq_validation(client, auth_headers):
    bad = sample_question(correct_option=9)
    r = client.post("/submissions", json={"questions": [bad], "rights_declared": True}, headers=auth_headers)
    assert r.status_code == 422


def test_mine_lists_only_metadata(client, auth_headers):
    client.post("/submissions", json={"questions": [sample_question()], "rights_declared": True}, headers=auth_headers)
    rows = client.get("/submissions/mine", headers=auth_headers).json()
    assert len(rows) == 1 and rows[0]["status"] == "deduplicated" and "ciphertext" not in rows[0]


def test_fingerprint_ignores_case_and_whitespace():
    a = Question(**sample_question(stem="What is  the derivative of $x^2$?"))
    b = Question(**sample_question(stem="what is the DERIVATIVE of $x^2$?"))
    c = Question(**sample_question(stem="What is the integral of $x^2$?"))
    assert a.fingerprint() == b.fingerprint() != c.fingerprint()


def test_me_reports_roles(client, auth_headers, admin_headers):
    from conftest import make_headers
    me = client.get("/auth/me", headers=auth_headers).json()
    assert me["email"] == "a@juit.ac.in" and me["roles"] == ["faculty"] and me["pseudonym"].startswith("FAC-")
    assert client.get("/auth/me", headers=admin_headers).json()["roles"] == ["faculty", "admin"]
    rv = make_headers(client, "r1@juit.ac.in")
    assert client.get("/auth/me", headers=rv).json()["roles"] == ["faculty", "reviewer"]
    assert client.get("/auth/me").status_code in (401, 403)
