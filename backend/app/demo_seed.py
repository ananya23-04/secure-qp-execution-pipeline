"""Demo seeder: drives the REAL API end to end so you can see every stage working.

    docker compose exec api python -m app.demo_seed

Creates demo accounts (admins/custodians + reviewers from your .env, plus 3 faculty), submits 60
Engineering Mathematics questions, runs them through validate -> dedup -> random pool -> blind review,
then runs a full commit-reveal exam and prints the generated Sets A/B/C and the verification result.
All demo accounts use the password below. Safe to re-run (duplicates are eliminated by the dedup engine).
"""
import argparse
import hashlib
import os
import sys
import time

import httpx

from . import config

PASSWORD = "DemoPass12345"
SUBJECT = "Engineering Mathematics"
FACULTY = [f"faculty{i}@juit.ac.in" for i in (1, 2, 3)]
TOPICS = {
    1: ["limits of rational functions", "continuity at a point", "the chain rule", "the product rule",
        "implicit differentiation", "Rolle's theorem", "the mean value theorem", "Taylor series expansion",
        "the Maclaurin series of e^x", "definite integrals", "integration by parts", "improper integrals",
        "area between curves", "volumes of solids of revolution", "partial derivatives",
        "maxima and minima of two variables", "Lagrange multipliers", "double integrals",
        "Jacobians", "the gradient and directional derivative"],
    2: ["matrix rank", "the inverse of a matrix", "properties of determinants", "Cramer's rule",
        "Gaussian elimination", "linear independence", "basis and dimension", "vector subspaces",
        "linear transformations", "kernel and image", "eigenvalues", "eigenvectors", "diagonalisation",
        "the Cayley-Hamilton theorem", "orthogonal vectors", "the Gram-Schmidt process",
        "symmetric matrices", "quadratic forms", "LU decomposition", "singular value decomposition"],
    3: ["conditional probability", "Bayes theorem", "independent events", "random variables",
        "expectation and variance", "the binomial distribution", "the Poisson distribution",
        "the normal distribution", "the exponential distribution", "the uniform distribution",
        "joint distributions", "covariance and correlation", "the law of large numbers",
        "the central limit theorem", "moment generating functions", "Markov chains",
        "hypothesis testing", "confidence intervals", "maximum likelihood estimation", "Chebyshev's inequality"],
}
BLOOM = ["remember", "understand", "apply", "analyze", "evaluate", "create"]
BLUEPRINT = {
    "subject": SUBJECT, "num_sets": 3, "total_marks": 30, "units": {"1": 10, "2": 10, "3": 10},
    "difficulty_mix": {"easy": 0.3, "medium": 0.5, "hard": 0.2}, "difficulty_tolerance": 0.2,
    "qtype_marks": {"mcq": 5, "short": 10, "long": 15}, "min_higher_order_pct": 10, "max_overlap_pct": 40,
}


def build_questions() -> list[dict]:
    qs = []
    for unit, topics in TOPICS.items():
        for j, t in enumerate(topics):
            base = {"subject": SUBJECT, "unit": unit, "bloom": BLOOM[j % 6], "difficulty": 0.5}
            if j < 8:
                cap = t[0].upper() + t[1:]
                qs.append({**base, "qtype": "mcq", "marks": 1,
                           "stem": f"Which of the following statements about {t} is correct?",
                           "options": [f"{cap} always holds with no conditions",
                                       f"{cap} holds only when its conditions are satisfied",
                                       f"{cap} never applies to real-valued problems",
                                       f"{cap} is unrelated to unit {unit}"],
                           "correct_option": 1})
            elif j < 14:
                qs.append({**base, "qtype": "short", "marks": 2,
                           "stem": f"State and briefly explain {t}, with one example."})
            else:
                qs.append({**base, "qtype": "long", "marks": 5,
                           "stem": f"Derive the main results for {t} and solve a complete worked problem."})
    return qs


class Api:
    def __init__(self, url: str):
        self.c = httpx.Client(base_url=url, timeout=120)

    def call(self, method, path, token=None, ok=(200, 201), **kw):
        h = {"Authorization": f"Bearer {token}"} if token else {}
        r = self.c.request(method, path, headers=h, **kw)
        if r.status_code not in ok:
            raise SystemExit(f"\nFAILED {method} {path} -> {r.status_code}: {r.text[:400]}")
        return r.json() if r.content else None

    def raw(self, path, token):
        return self.c.get(path, headers={"Authorization": f"Bearer {token}"})

    def user(self, email) -> str:
        self.call("POST", "/auth/register", ok=(201, 409),
                  json={"email": email, "password": PASSWORD, "institution": "JUIT (demo)"})
        return self.call("POST", "/auth/login", json={"email": email, "password": PASSWORD})["access_token"]


def step(msg):
    print(f"\n== {msg}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8000")
    args = ap.parse_args()
    admins, reviewers = sorted(config.ADMIN_EMAILS), sorted(config.REVIEWER_EMAILS)
    if not admins or len(reviewers) < config.REVIEWS_REQUIRED:
        sys.exit(f"Need >=1 admin email and >={config.REVIEWS_REQUIRED} reviewer emails in .env "
                 "(SAFEEXAM_ADMIN_EMAILS / SAFEEXAM_REVIEWER_EMAILS).")
    api = Api(args.url)
    for _ in range(30):
        try:
            api.c.get("/health").raise_for_status()
            break
        except Exception:
            time.sleep(1)

    step("1. Accounts")
    adm = {e: api.user(e) for e in admins}
    rev = {e: api.user(e) for e in reviewers}
    fac = {e: api.user(e) for e in FACULTY}
    print(f"admins/custodians: {', '.join(admins)}\nreviewers: {', '.join(reviewers)}\nfaculty: {', '.join(FACULTY)}")
    print(f"(every demo account's password: {PASSWORD})")

    step("2. Faculty submit 60 questions (validate -> dedup run automatically)")
    qs = build_questions()
    for k, (email, tok) in enumerate(fac.items()):
        mine = qs[k::3]
        r = api.call("POST", "/submissions", tok, json={"questions": mine, "rights_declared": True})
        print(f"{email}: submitted {r['question_count']} questions")
    for email, tok in fac.items():
        for _ in range(60):
            rows = api.call("GET", "/submissions/mine", tok)
            if all(r["status"] == "deduplicated" for r in rows):
                break
            time.sleep(1)
    summ: dict[str, int] = {}
    for email, tok in fac.items():
        for row in api.call("GET", "/submissions/mine", tok):
            for q in api.call("GET", f"/submissions/{row['id']}/report", tok)["questions"]:
                summ[q["status"]] = summ.get(q["status"], 0) + 1
    print("pre-processing outcome:", summ)

    step("3. Random Set Generator builds the anonymous review pool")
    pool = api.call("POST", "/moderation/pool/build", adm[admins[0]],
                    json={"subject": SUBJECT, "units": {"1": 20, "2": 20, "3": 20}})
    print(f"pool of {pool['selected']} questions, by unit {pool['by_unit']}, shortfall {pool['shortfall']}")

    step("4. Blind review panel")
    for k, (email, tok) in enumerate(rev.items()):
        done = 0
        while True:
            items = api.call("GET", "/review/queue?limit=20", tok)
            if not items:
                break
            for it in items:
                base = (int(it["question_id"][:6], 16) % 1000) / 1000        # reviewers' own difficulty rating
                d = min(1.0, max(0.0, base + (0.03 if k % 2 else -0.03)))
                api.call("POST", f"/review/{it['question_id']}", tok,
                         json={"decision": "approve", "quality": 4, "difficulty": round(d, 3), "comment": ""})
                done += 1
        print(f"{email}: reviewed {done} questions")
    print("review states:", api.call("GET", "/moderation/stats", adm[admins[0]]))

    step("5. Exam: commit -> reveal -> CP-SAT generation -> verify")
    ex = api.call("POST", "/exams", adm[admins[0]],
                  json={"title": "Demo End-Term", "blueprint": BLUEPRINT, "required_commits": len(admins)})
    eid = ex["id"]
    secrets = {e: f"demo-secret-{e}-{int(time.time())}" for e in admins}
    for e in admins:
        api.call("POST", f"/exams/{eid}/commit", adm[e],
                 json={"commitment": hashlib.sha256(secrets[e].encode()).hexdigest()})
    print(f"{len(admins)} custodian(s) committed")
    for e in admins:
        api.call("POST", f"/exams/{eid}/reveal", adm[e], json={"secret": secrets[e]})
    t0 = time.time()
    res = api.call("POST", f"/exams/{eid}/generate", adm[admins[0]])
    print(f"seed: {res['seed'][:24]}...   solver time: {time.time() - t0:.1f}s")
    for label, s in res["sets"].items():
        print(f"Set {label}: {s['questions']} questions, {s['total_marks']} marks | units {s['marks_by_unit']} | "
              f"difficulty {s['marks_by_difficulty']} | types {s['marks_by_qtype']} | hash {s['paper_hash'][:12]}")
    v = api.call("GET", f"/exams/{eid}/verify", adm[admins[0]])
    print("verify:", v)

    step("6. Custodians approve release, then each set is rendered to a PDF")
    for e in admins:
        r = api.call("POST", f"/exams/{eid}/release", adm[e])
        print(f"{e}: approved release ({r['approvals']}/{r['required']}) -> exam {r['status']}")
    out = os.environ.get("SAFEEXAM_OUTPUT_DIR", "output")
    os.makedirs(out, exist_ok=True)
    for label in res["sets"]:
        r = api.c.post(f"/exams/{eid}/papers/{label}/render", headers={"Authorization": f"Bearer {adm[admins[0]]}"})
        if r.status_code == 503:
            print("LaTeX engine not installed in this environment - skipping PDF rendering.")
            break
        if r.status_code != 200:
            raise SystemExit(f"\nFAILED render {label}: {r.status_code} {r.text[:400]}")
        meta = r.json()
        v = api.call("GET", f"/exams/{eid}/papers/{label}/render-verify", adm[admins[0]])
        pdf = api.raw(f"/exams/{eid}/papers/{label}/pdf", adm[admins[0]]).content
        path = os.path.join(out, f"SafeExam_Set_{label}.pdf")
        with open(path, "wb") as f:
            f.write(pdf)
        print(f"Set {label}: {len(pdf)//1024} KB -> {path} | pdf sha256 {meta['pdf_hash'][:16]}... | re-render identical: {v['reproducible']}")
    print("audit chain:", api.call("GET", "/moderation/audit/verify", adm[admins[0]]))
    print(f"\nDone. Open the portal at {args.url}/app/  (API docs: {args.url}/docs, exam id: {eid})")
    print(f"Sign in as faculty1@juit.ac.in (author), {reviewers[0]} (reviewer) or {admins[0]} (admin), password {PASSWORD}.")


if __name__ == "__main__":
    main()
