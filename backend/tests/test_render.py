import hashlib
import shutil
import time

import pytest

from app import render
from app.db import SessionLocal
from app.models import QuestionRecord, RenderedPaper
from app.question_schema import Question
from conftest import sample_question
from test_exams import BLUEPRINT, admins, bank, run_exam, sha  # noqa: F401  (bank is a fixture)

needs_tex = pytest.mark.skipif(not shutil.which("pdflatex"), reason="pdflatex not installed")


def q(**kw):
    return Question(**sample_question(**kw))


def canon(items, label="A"):
    return render.build_canonical({"id": "e" * 32, "title": "Term Exam", "subject": "Maths"}, label, "f" * 64,
                                  [(x.fingerprint(), x) for x in items])


# ---- pure unit tests (no LaTeX needed) --------------------------------------------------------
def test_tex_escaping_outside_and_inside_math():
    assert render.tex_text(r"50% of x_1 & y #2 costs \$5") == r"50\% of x\_1 \& y \#2 costs \$5"
    assert render.tex_text("keep $a_b & c$ but escape 5% here") == r"keep $a_b & c$ but escape 5\% here"
    assert render.tex_text("$p\\%$") == "$p\\%$"            # already-escaped stays escaped


def test_unicode_mapping_and_unsupported_warning():
    w: list[str] = []
    assert r"$\leq$" in render.tex_text("x ≤ 3", w) and "--" in render.tex_text("a – b")
    assert render.tex_text("$x ≤ 3$").count("$") == 2        # no nested math
    assert render.tex_text("名前", w) == "??" and w == ["unsupported_characters"]


def test_canonical_excludes_answers_and_is_stable():
    item = q(solution_latex="SECRET-SOLUTION-TEXT", correct_option=1)
    c = canon([item])
    j = render.canonical_json(c)
    assert "SECRET-SOLUTION-TEXT" not in j and "correct_option" not in j
    assert render.canonical_json({"b": 1, "a": 2}) == render.canonical_json({"a": 2, "b": 1})
    tex, _ = render.to_latex(c)
    assert "SECRET-SOLUTION-TEXT" not in tex


def test_unsafe_latex_is_refused_even_if_it_reached_the_bank():
    c = canon([q()])
    c["sections"][0]["questions"][0]["stem"] = r"Evaluate \write18{rm -rf /} now"
    with pytest.raises(render.RenderError, match="unsafe"):
        render.to_latex(c)


# ---- real compilation -------------------------------------------------------------------------
@needs_tex
def test_compiles_awkward_text_and_is_byte_identical():
    items = [q(stem="Show that 50% of x_1 & y #2 satisfies $x^2 \\leq 4$ — and explain ≥ cases fully."),
             q(qtype="short", options=None, correct_option=None, stem="Define the term 'limit' with an example.", marks=2),
             q(qtype="long", options=None, correct_option=None, stem="Derive $\\int_0^1 x\\,dx$ in full detail.", marks=5)]
    tex, _ = render.to_latex(canon(items))
    a = render.compile_pdf(tex, 1_700_000_000)
    time.sleep(1.2)
    b = render.compile_pdf(tex, 1_700_000_000)
    assert a.startswith(b"%PDF") and a == b
    assert render.compile_pdf(tex, 1_700_000_999) == a        # no dates embedded: output is clock-independent
    assert render.compile_pdf(tex.replace('Derive', 'Prove'), 1_700_000_000) != a   # but any content change shows


@needs_tex
def test_bad_latex_reports_failure_cleanly():
    with pytest.raises(render.RenderError, match="compilation failed"):
        render.compile_pdf("\\documentclass{article}\\begin{document}\\undefinedcommand\\end{document}", 1)


# ---- end to end via the API -------------------------------------------------------------------
def generated(client, hs):
    eid = run_exam(client, hs)
    assert client.post(f"/exams/{eid}/generate", headers=hs[0]).status_code == 200
    return eid


def test_release_gate_rules(client, bank):
    hs = admins(client)
    eid = client.post("/exams", json={"title": "Gate", "blueprint": BLUEPRINT, "required_commits": 2}, headers=hs[0]).json()["id"]
    for h, s in zip(hs[:2], ("gate-secret-aaaaaaaa", "gate-secret-bbbbbbbb")):
        client.post(f"/exams/{eid}/commit", json={"commitment": sha(s)}, headers=h)
    for h, s in zip(hs[:2], ("gate-secret-aaaaaaaa", "gate-secret-bbbbbbbb")):
        client.post(f"/exams/{eid}/reveal", json={"secret": s}, headers=h)
    assert client.post(f"/exams/{eid}/release", headers=hs[0]).status_code == 409         # not generated yet
    client.post(f"/exams/{eid}/generate", headers=hs[0])
    assert client.post(f"/exams/{eid}/papers/A/render", headers=hs[0]).status_code == 409  # not released
    assert client.post(f"/exams/{eid}/release", headers=hs[2]).status_code == 403          # not a custodian
    assert client.post(f"/exams/{eid}/release", headers=hs[0]).json() == {"status": "generated", "approvals": 1, "required": 2}
    assert client.get(f"/exams/{eid}", headers=hs[0]).json()["release_approvals"] == 1
    assert client.post(f"/exams/{eid}/release", headers=hs[0]).status_code == 409          # twice
    assert client.post(f"/exams/{eid}/papers/A/render", headers=hs[0]).status_code == 409  # still gated
    assert client.post(f"/exams/{eid}/release", headers=hs[1]).json()["status"] == "released"
    assert client.post(f"/exams/{eid}/release", headers=hs[1]).status_code == 409


@needs_tex
def test_render_download_and_verify_flow(client, bank):
    hs = admins(client)
    eid = generated(client, hs)
    for h in hs:
        client.post(f"/exams/{eid}/release", headers=h)
    r = client.post(f"/exams/{eid}/papers/A/render", headers=hs[0])
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["already_rendered"] is False and all(len(m[k]) == 64 for k in ("canonical_hash", "tex_hash", "pdf_hash"))
    assert client.post(f"/exams/{eid}/papers/A/render", headers=hs[1]).json()["already_rendered"] is True
    pdf = client.get(f"/exams/{eid}/papers/A/pdf", headers=hs[0])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert hashlib.sha256(pdf.content).hexdigest() == m["pdf_hash"]
    v = client.get(f"/exams/{eid}/papers/A/render-verify", headers=hs[0]).json()
    assert v["reproducible"] and v["engine_same"], v
    with SessionLocal() as db:                                    # ciphertext at rest, not a readable PDF
        assert not db.query(RenderedPaper).one().ciphertext.startswith(b"%PDF")
    ev = client.get("/moderation/audit/verify", headers=hs[0]).json()
    assert ev["ok"]


@needs_tex
def test_tampering_is_detected(client, bank):
    hs = admins(client)
    eid = generated(client, hs)
    for h in hs:
        client.post(f"/exams/{eid}/release", headers=h)
    client.post(f"/exams/{eid}/papers/A/render", headers=hs[0])
    # 1) stored PDF hash altered -> download refuses, verify flags it
    with SessionLocal() as db:
        rp = db.query(RenderedPaper).one()
        good = rp.pdf_hash
        rp.pdf_hash = "0" * 64
        db.commit()
    assert client.get(f"/exams/{eid}/papers/A/pdf", headers=hs[0]).status_code == 500
    v = client.get(f"/exams/{eid}/papers/A/render-verify", headers=hs[0]).json()
    assert v["stored_pdf_intact"] is False and v["reproducible"] is False
    with SessionLocal() as db:
        db.query(RenderedPaper).one().pdf_hash = good
        db.commit()
    # 2) a question's recorded fingerprint altered -> rendering a fresh set is refused
    qid = client.get(f"/exams/{eid}", headers=hs[0]).json()["sets"]["B"]["question_ids"][0]
    with SessionLocal() as db:
        db.get(QuestionRecord, qid).fingerprint = "1" * 64
        db.commit()
    r = client.post(f"/exams/{eid}/papers/B/render", headers=hs[0])
    assert r.status_code == 422 and "integrity" in str(r.json())
