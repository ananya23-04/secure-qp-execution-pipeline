from conftest import make_headers, sample_question

TCP = dict(qtype="short", options=None, correct_option=None, subject="Networks", unit=3,
           stem="Explain the working of the TCP three-way handshake in detail with a neat diagram.")


def submit(client, headers, questions):
    r = client.post("/submissions", json={"questions": questions, "rights_declared": True}, headers=headers)
    assert r.status_code == 201
    return r.json()["id"]


def report(client, headers, sid):
    return client.get(f"/submissions/{sid}/report", headers=headers).json()


def test_unique_question_flows_through(client, auth_headers):
    sid = submit(client, auth_headers, [sample_question()])
    rep = report(client, auth_headers, sid)
    assert rep["submission_status"] == "deduplicated"
    assert rep["summary"] == {"unique": 1}


def test_exact_duplicate_across_faculty_is_eliminated(client, auth_headers):
    other = make_headers(client, "b@juit.ac.in")
    submit(client, auth_headers, [sample_question()])
    sid = submit(client, other, [sample_question(stem="WHAT is the   derivative of $x^2$?")])
    assert report(client, other, sid)["summary"] == {"duplicate": 1}


def test_duplicate_inside_one_batch(client, auth_headers):
    sid = submit(client, auth_headers, [sample_question(), sample_question()])
    assert report(client, auth_headers, sid)["summary"] == {"unique": 1, "duplicate": 1}


def test_near_duplicate_tagged_not_eliminated(client, auth_headers):
    other = make_headers(client, "b@juit.ac.in")
    submit(client, auth_headers, [sample_question(**TCP)])
    sid = submit(client, other, [sample_question(**{**TCP, "stem": "Explain the working of the TCP three way handshake in detail, with a neat diagram"})])
    assert report(client, other, sid)["summary"] == {"near_duplicate": 1}


def test_unrelated_question_same_subject_is_unique(client, auth_headers):
    submit(client, auth_headers, [sample_question(**TCP)])
    sid = submit(client, auth_headers, [sample_question(**{**TCP, "stem": "Compare TCP with UDP for real-time streaming applications."})])
    assert report(client, auth_headers, sid)["summary"] == {"unique": 1}


def test_invalid_latex_rejected_with_codes(client, auth_headers):
    sid = submit(client, auth_headers, [
        sample_question(stem=r"Evaluate $\int_0^1 x dx and report."),
        sample_question(stem=r"Compute $\input{/etc/passwd}$ right now."),
    ])
    rep = report(client, auth_headers, sid)
    assert rep["summary"] == {"invalid": 2}
    assert "UNBALANCED_MATH" in rep["questions"][0]["issues"]
    assert "FORBIDDEN_LATEX" in rep["questions"][1]["issues"]


def test_report_is_private_and_hides_match_ids(client, auth_headers):
    other = make_headers(client, "b@juit.ac.in")
    sid = submit(client, auth_headers, [sample_question()])
    assert client.get(f"/submissions/{sid}/report", headers=other).status_code == 404
    assert "duplicate_of" not in str(report(client, auth_headers, sid))


def test_questions_encrypted_at_rest(client, auth_headers):
    from app.db import SessionLocal
    from app.models import QuestionRecord
    submit(client, auth_headers, [sample_question()])
    with SessionLocal() as db:
        rec = db.query(QuestionRecord).one()
        assert b"derivative" not in rec.ciphertext and rec.unit == 1 and rec.bloom == "remember"


def test_admin_endpoints(client, auth_headers, admin_headers):
    other = make_headers(client, "b@juit.ac.in")
    submit(client, auth_headers, [sample_question(**TCP)])
    submit(client, other, [sample_question(**{**TCP, "stem": "Explain the working of the TCP three way handshake in detail, with a neat diagram"})])
    assert client.get("/pipeline/stats", headers=auth_headers).status_code == 403
    st = client.get("/pipeline/stats", headers=admin_headers).json()
    assert st["questions"] == {"unique": 1, "near_duplicate": 1}
    dups = client.get("/pipeline/duplicates", headers=admin_headers).json()
    assert len(dups) == 1 and dups[0]["similarity"] > 0.95 and "stem" not in dups[0]


def test_admin_run_is_idempotent(client, auth_headers, admin_headers):
    sid = submit(client, auth_headers, [sample_question()])
    r = client.post(f"/pipeline/run/{sid}", headers=admin_headers)
    assert r.status_code == 200 and r.json()["summary"] == {"unique": 1}
    assert client.post("/pipeline/run/nope", headers=admin_headers).status_code == 404
