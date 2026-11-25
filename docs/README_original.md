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

Planning / early implementation — see the project timeline in the proposal PDF (Literature
Review → Analysis → Design → Implementation → Testing → Documentation, Jul 2026–May 2027).

## License

MIT — see [LICENSE](LICENSE).
