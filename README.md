# SafeExam — Zero-Trust Question Paper Delivery Framework

**Group RG93 · Major Project (AY 2026-27) · Dept. of CSE & IT, Jaypee University of Information Technology**

SafeExam (internally RG93 / AegisExam) is an exposure-limited, zero-trust architecture for
generating, distributing, and printing examination question papers while minimizing the number
of people or systems that ever see a final paper before the exam starts.

## Team

| Roll No. | Name | Role |
|---|---|---|
| 231032008 | Aaditya Thakur | Full-Stack Security, Neural Architecture & System Developer |
| 231032018 | Ananya Gupta | Full-Stack Security, Neural Architecture & System Developer |
| 231032040 | Priyanshu Gautam | Full-Stack Security, Neural Architecture & System Developer |

**Supervisor:** Ms. Seema Rani, Assistant Professor (Grade-I)

## Problem Statement

Conventional exam-paper pipelines rely on physical transport, centralized servers, or files
stored locally on test-center hardware ahead of time — all of which create windows for leaks,
unauthorized access, and tampering. SafeExam fetches, verifies, and reconstructs the final paper
on-site only moments before the exam, requires simultaneous multi-custodian approval to unlock
content, and logs every step in a tamper-proof audit trail.

## Core Ideas

- **Federated / half-encoder pipeline** — question content is compressed into encrypted model
  weights + calibrated differential-privacy noise rather than shipped as plaintext.
- **Constraint-based form builder** — a solver (not pure randomness) assembles blueprint-valid
  question sets, seeded via a commit-reveal scheme so no single party can bias the draw.
- **Threshold release** — a 3-of-5 (or similar) custodian quorum, backed by hardware key
  storage, is required to unlock a center's decryption key; no single person can leak on their own.
- **Just-in-time rendering** — the final PDF is deterministically rebuilt from a signed manifest
  only inside an attested appliance at the print center, minutes before the exam.
- **Immutable audit trail** — every sensitive action (submission, review, build, release, print)
  is signed and chained so incidents can be traced without exposing question content.

## Repository Structure

```
SafeExam/
├── docs/                     # Project proposals, patent-oriented write-up, architecture diagram
├── src/
│   ├── ai-paper-generation/  # Central federated/half-encoder model + constraint-based solver
│   ├── submission-portal/    # Multi-institution question submission & partitioned review
│   ├── crypto-release/       # AEAD capsule encryption, key wrapping, threshold release logic
│   └── audit-blockchain/     # Immutable audit log / fingerprinting
└── README.md
```

## Documents

- [`docs/Major_Project_Proposal.pdf`](docs/Major_Project_Proposal.pdf) — official JUIT project
  proposal (title, team, objectives, timeline).
- [`docs/RG93_Secure_Examination_Proposal.pdf`](docs/RG93_Secure_Examination_Proposal.pdf) —
  detailed technical/patent-oriented design proposal.
- [`docs/architecture-diagram.png`](docs/architecture-diagram.png) — end-to-end system diagram
  (collection → pre-processing → review → distribution → local center execution → printing).

## Tech Stack

- **AI/ML:** Python, PyTorch / TensorFlow
- **Rendering:** pdfLaTeX / XeLaTeX, JSON/XML → LaTeX pipeline
- **Security:** AEAD encryption, PKCS#11 key management, Shamir's Secret Sharing / threshold release
- **Audit:** Hyperledger Fabric (immutable ledger)
- **Services:** REST API microservices

## Status

Planning / early implementation. The collection, pre-processing, review, set-generation, release and rendering stages are implemented (see below).

## License

MIT — see [LICENSE](LICENSE).

---

# Implementation: Collection to Rendering

Backend for stages 1-2 of the pipeline.

**Collection:** faculty portal API, canonical question schema, AES-256-GCM encrypted
raw storage, faculty identity decoupled via pseudonyms.

**Pre-processing (runs automatically after every submission):**
1. *Convert & Validate* - whitespace/metadata normalisation, MCQ option checks, LaTeX
   syntax checks (balanced `$`, braces, environments) and a blocklist of dangerous
   primitives (`\input`, `\write`, `\def`, ...).
2. *Deduplicate* - SHA-256 fingerprint for exact duplicates (eliminated); TF-IDF
   cosine similarity (>= 0.85, same subject) for near-duplicates (tagged, kept for review).

Question text is encrypted at rest; only solver metadata (unit, Bloom level, difficulty,
marks) is stored in the clear. Faculty see per-question status for their own submissions
only; they are never told which other question matched.

**Review (blind human gate):**
- *Random Set Generator* - admin posts a blueprint (subject + questions per unit); a random,
  unit-stratified sample is placed in an anonymous review pool (shortfalls are reported).
- *Blind panel* - reviewers (`SAFEEXAM_REVIEWER_EMAILS`) get anonymous items with no author and no
  author-claimed difficulty, never their own questions, one review each. Each review gives
  approve/reject, quality 1-5 and their own difficulty rating (the re-rate).
- *Decision rule* - after `SAFEEXAM_REVIEWS_REQUIRED` reviews: all approve and mean quality >= pass mark
  -> approved (difficulty becomes the reviewers' mean); majority reject -> rejected; otherwise -> SME moderation.
- *Correction interface* - fix LaTeX typos / solutions; re-validated, re-fingerprinted, audited.
- *Audit log* - hash-chained, tamper-evident (`GET /moderation/audit/verify`); Fabric adapter later.

**Random QP Generator (admin / custodians):**
- *Blueprint* - subject, number of sets (A/B/C...), total marks, marks per unit, difficulty mix
  (easy/medium/hard share + tolerance), optional minimum higher-order Bloom share, optional marks per
  question type, and maximum overlap between any two sets.
- *CP-SAT solver* (OR-Tools) - every set hits exact total marks and exact unit marks, stays inside the
  difficulty window, and all sets share the same difficulty profile; pairwise overlap is capped.
- *Commit-reveal seed* - each custodian (admin) commits `sha256(secret)`; only after all commitments are in
  can secrets be revealed; seed = sha256(exam id + sorted secrets). No single custodian can steer the result.
  The solver is single-threaded with a deterministic budget, so `GET /exams/{id}/verify` re-derives the seed,
  re-audits every constraint, and re-runs the solver to prove the sets are reproducible.
- Responses contain metadata and hashes only - question text stays encrypted until the print stage.
- Limitation: a custodian who never reveals blocks generation; a timeout/replacement policy is future work.

**Release gate + deterministic renderer (JIT paper rendering):**
- *Release gate* - after generation, every custodian of the exam must call `POST /exams/{id}/release`
  before any plaintext paper can exist (k-of-n; stand-in for the Shamir key release).
- *Canonical JSON* holds only what students see - never correct answers or solutions - and is hashed.
- *LaTeX* - text is escaped, re-checked for dangerous primitives, then compiled with shell-escape off,
  paranoid file access, a timeout and a throw-away directory. Sets are integrity-checked first: every
  question's content must match its recorded fingerprint and the set must match its generation hash.
- *Deterministic PDFs* - no dates embedded, so re-rendering gives byte-identical output.
  `GET /exams/{id}/papers/{A}/render-verify` re-renders and compares the canonical, LaTeX and PDF hashes.
- PDFs are stored AES-256-GCM encrypted; the LaTeX source is never stored; each download is audited.
  `/pdf` is a stand-in for the print appliance and exposes plaintext to custodians once released.
- Footer carries a per-set reference hash so a printed copy traces back to its set.

## Web portal (React)
Open **http://localhost:8000/app/** after `.\run.ps1`. One sign-in, screens appear by role:
- *Faculty* - **Submit questions** (live KaTeX preview, LaTeX problems flagged as you type, batch + rights declaration)
  and **My submissions** (per-question outcome: unique / near-duplicate / duplicate / invalid).
- *Reviewer* (`SAFEEXAM_REVIEWER_EMAILS`) - **Review**: blind queue (no author, no author difficulty), approve/reject,
  quality 1-5, own difficulty rating, anonymous comment, inline typo/solution correction.
- *Admin* (`SAFEEXAM_ADMIN_EMAILS`) - **Moderation** (pool builder, disputed questions, duplicates, audit check) and
  **Exams** (blueprint form; commit-reveal runs in the browser - the secret is generated and hashed locally;
  generate sets, approve release, render, download and verify PDFs).
Each browser tab keeps its own session, so open one tab per custodian for a multi-custodian exam.
Design: light, warm-paper theme (ink text, burnt-orange accent, Fraunces serif headings, Inter UI text, JetBrains Mono for hashes),
bundled fonts so it works offline, sidebar navigation by role, toasts, keyboard-visible focus states, responsive down to phones.
The compiled bundle is checked in (`backend/app/static`), so Node is NOT needed to run it. To change the UI:
    cd frontend && npm install && npm run dev      # hot reload, proxies the API on :8000
    npm test                                       # 17 unit tests
    npm run build                                  # rebuilds backend/app/static
    SAFEEXAM_LIVE_URL=http://localhost:8000 npx vitest run src/__tests__/live.test.jsx   # drives the real UI vs a live API

## Run
    cp .env.example .env        # (Windows: copy)  fill in keys + SAFEEXAM_ADMIN_EMAILS
    docker compose up --build   # http://localhost:8000/docs  (not 0.0.0.0)
    .\run.ps1                   # Windows: start in background and open the docs page

## Demo seeder (see the whole pipeline work in ~1 minute)
    docker compose exec api python -m app.demo_seed
Registers the admin/custodian and reviewer accounts from `.env` plus 3 faculty (all with password
`DemoPass12345`), submits 60 maths questions, runs validate -> dedup -> random review pool -> blind review,
then a full commit-reveal exam, the custodian release, and real PDFs of Sets A/B/C written to `./output` (opens on your machine). For a clean demo database:
`docker compose down -v` first (this wipes all data).

## Test
    cd backend && pip install -r requirements.txt && pytest -q

## Endpoints
- `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- `POST /submissions`, `GET /submissions/mine`, `GET /submissions/{id}/report`
- Admin (`SAFEEXAM_ADMIN_EMAILS`): `POST /pipeline/run/{id}`, `GET /pipeline/stats`, `GET /pipeline/duplicates`
- Review: `GET /review/queue`, `POST /review/{id}`, `POST /review/{id}/correction`, `GET /review/mine/history`
- Release/render (admin): `POST /exams/{id}/release`, `POST /exams/{id}/papers/{label}/render`, `GET /exams/{id}/papers/{label}/pdf`, `GET /exams/{id}/papers/{label}/render-verify`
- Exams (admin): `POST /exams`, `GET /exams/{id}`, `POST /exams/{id}/commit`, `POST /exams/{id}/reveal`, `POST /exams/{id}/generate`, `GET /exams/{id}/verify`
- Moderation (admin): `POST /moderation/pool/build`, `GET /moderation/queue`, `POST /moderation/{id}/decide`, `GET /moderation/stats`, `GET /moderation/audit/verify`

## Next
Hyperledger Fabric audit adapter and Shamir key release (teammates' modules); production hardening (Alembic migrations, HTTPS, CSP headers, token refresh).

## Making a commitment (PowerShell / any terminal with Python)
    python -c "import hashlib;print(hashlib.sha256(b'my-long-secret-phrase-1').hexdigest())"
Post that hash to `/exams/{id}/commit`; later post the same phrase (16+ characters) to `/exams/{id}/reveal`.
Each custodian must be a different admin account listed in `SAFEEXAM_ADMIN_EMAILS`.
