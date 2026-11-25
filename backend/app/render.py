"""Deterministic paper rendering: canonical JSON -> LaTeX -> PDF, with a hash at every step.

* Canonical JSON holds only what students see (no correct answers, no solutions).
* LaTeX text is escaped, re-checked for dangerous primitives, and compiled with shell-escape off,
  paranoid file access and a timeout, in a throw-away directory.
* SOURCE_DATE_EPOCH + pdfTeX flags make the PDF byte-for-byte reproducible, so a re-render must
  hash identically to the stored one."""
import functools
import hashlib
import json
import os
import shutil
import subprocess
import tempfile

from .question_schema import Question
from .validate import check_latex

ENGINE = "pdflatex"
SCHEMA = "safeexam.paper/1"
TITLES = {"mcq": "Multiple Choice Questions", "short": "Short Answer Questions", "long": "Long Answer Questions"}
ORDER = ("mcq", "short", "long")


class RenderError(Exception):
    pass


class EngineMissing(RenderError):
    pass


def sha256(data: str | bytes) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def canonical_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


@functools.lru_cache(maxsize=1)
def engine_version() -> str:
    if not shutil.which(ENGINE):
        return "none"
    out = subprocess.run([ENGINE, "--version"], capture_output=True, text=True, timeout=20).stdout
    return out.splitlines()[0].strip() if out else ENGINE


# ---- canonical paper ---------------------------------------------------------
def build_canonical(exam: dict, label: str, paper_hash: str, items: list[tuple[str, Question]]) -> dict:
    """items: ordered (fingerprint, Question). Correct options / solutions are deliberately excluded."""
    sections, no = [], 0
    for qt in ORDER:
        qs = []
        for fp, q in items:
            if q.qtype.value == qt:
                no += 1
                qs.append({"no": no, "marks": q.marks, "stem": q.stem, "options": q.options, "fp": fp})
        if qs:
            sections.append({"qtype": qt, "title": TITLES[qt], "marks": sum(x["marks"] for x in qs), "questions": qs})
    return {"schema": SCHEMA, "exam": exam, "set": label, "paper_hash": paper_hash,
            "total_marks": sum(s["marks"] for s in sections), "sections": sections}


# ---- LaTeX text escaping -------------------------------------------------------
_MATH_SYM = {"≤": r"\leq", "≥": r"\geq", "≠": r"\neq", "×": r"\times", "÷": r"\div", "±": r"\pm",
             "→": r"\to", "←": r"\leftarrow", "∞": r"\infty", "π": r"\pi", "√": r"\surd", "∑": r"\sum",
             "∫": r"\int", "∂": r"\partial", "∈": r"\in", "∪": r"\cup", "∩": r"\cap", "≈": r"\approx",
             "α": r"\alpha", "β": r"\beta", "γ": r"\gamma", "δ": r"\delta", "θ": r"\theta", "λ": r"\lambda",
             "μ": r"\mu", "σ": r"\sigma", "ω": r"\omega", "Σ": r"\Sigma", "Δ": r"\Delta", "Ω": r"\Omega"}
_TEXT_SYM = {"–": "--", "—": "---", "‘": "'", "’": "'", "“": "``", "”": "''", "…": r"\ldots{}", "\u00a0": "~"}


def tex_text(s: str, warnings: list[str] | None = None) -> str:
    """Escape plain text but keep inline math ($...$) and intentional LaTeX markup intact."""
    out, math, i = [], False, 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):          # keep escapes (\$, \%, \alpha ...) verbatim
            out.append(c + s[i + 1])
            i += 2
            continue
        if c == "$":
            math = not math
            out.append(c)
        elif c in "%#":
            out.append("\\" + c)
        elif c in "&_" and not math:
            out.append("\\" + c)
        elif c == "~" and not math:
            out.append(r"\textasciitilde{}")
        elif c == "^" and not math:
            out.append(r"\^{}")
        elif c in _MATH_SYM:
            out.append((_MATH_SYM[c] + " ") if math else "$" + _MATH_SYM[c] + "$")
        elif c in _TEXT_SYM:
            out.append(_TEXT_SYM[c])
        elif ord(c) > 0x17F:
            out.append("?")
            if warnings is not None and "unsupported_characters" not in warnings:
                warnings.append("unsupported_characters")
        else:
            out.append(c)
        i += 1
    return "".join(out)


_PREAMBLE = r"""\pdfinfoomitdate=1
\pdfsuppressptexinfo=-1
\pdftrailerid{}
\documentclass[11pt,a4paper]{article}
\usepackage[T1]{fontenc}
\usepackage{lmodern}
\usepackage[margin=2.2cm,headheight=14pt]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{fancyhdr}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small @SUBJECT@}
\fancyhead[R]{\small Set @LABEL@}
\fancyfoot[L]{\scriptsize Ref: @REF@}
\fancyfoot[C]{\small Page \thepage}
\setlength{\parindent}{0pt}
\setlength{\parskip}{5pt}
\begin{document}
"""


def to_latex(canon: dict) -> tuple[str, list[str]]:
    warnings: list[str] = []
    for sec in canon["sections"]:                  # defence in depth: never trust stored text
        for q in sec["questions"]:
            for field in [q["stem"], *(q["options"] or [])]:
                bad = check_latex(field)
                if bad:
                    raise RenderError(f"unsafe or malformed LaTeX in question {q['no']}: {', '.join(bad)}")
    ex, label = canon["exam"], canon["set"]
    ref = f"{ex['id'][:8]}-{label}-{canon['paper_hash'][:12]}"
    t = lambda x: tex_text(x, warnings)
    head = (_PREAMBLE.replace("@SUBJECT@", t(ex["subject"])).replace("@LABEL@", label).replace("@REF@", ref))
    body = [
        r"\begin{center}",
        r"{\LARGE\bfseries " + t(ex["title"]) + r"}\\[4pt]",
        r"{\large " + t(ex["subject"]) + f" --- Set {label}" + r"}\\[2pt]",
        f"Maximum Marks: {canon['total_marks']}",
        r"\end{center}",
        r"\hrule",
        r"\vspace{6pt}",
        r"\textbf{Instructions:} Answer all questions. Marks for each question are shown in brackets at the right margin.",
        r"\vspace{4pt}",
    ]
    for k, sec in enumerate(canon["sections"]):
        body.append(r"\section*{Section " + chr(65 + k) + ": " + t(sec["title"]) +
                    r" \hfill [" + str(sec["marks"]) + r" marks]}")
        for q in sec["questions"]:
            body.append(r"\textbf{Q" + str(q["no"]) + r".} " + t(q["stem"]) +
                        r" \hfill \textbf{[" + str(q["marks"]) + r"]}\par")
            if q["options"]:
                body.append(r"\begin{enumerate}\setlength{\itemsep}{0pt}\renewcommand{\labelenumi}{(\alph{enumi})}")
                body.extend(r"\item " + t(o) for o in q["options"])
                body.append(r"\end{enumerate}")
    body.append(r"\end{document}")
    return head + "\n".join(body) + "\n", warnings


# ---- compile -------------------------------------------------------------------
def compile_pdf(tex: str, epoch: int) -> bytes:
    if not shutil.which(ENGINE):
        raise EngineMissing("LaTeX engine (pdflatex) is not installed on this server")
    with tempfile.TemporaryDirectory(prefix="safeexam-render-") as d:
        with open(os.path.join(d, "paper.tex"), "w", encoding="utf-8") as f:
            f.write(tex)
        env = {"PATH": os.environ.get("PATH", ""), "HOME": d, "TEXMFVAR": d, "TEXMFCONFIG": d,
               "SOURCE_DATE_EPOCH": str(epoch), "FORCE_SOURCE_DATE": "1",
               "openin_any": "p", "openout_any": "p"}              # paranoid file access
        try:
            r = subprocess.run([ENGINE, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error",
                                "paper.tex"], cwd=d, env=env, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            raise RenderError("LaTeX compilation timed out")
        pdf = os.path.join(d, "paper.pdf")
        if r.returncode != 0 or not os.path.exists(pdf):
            tail = ""
            log = os.path.join(d, "paper.log")
            if os.path.exists(log):
                tail = "\n".join(open(log, encoding="utf-8", errors="replace").read().splitlines()[-20:])
            raise RenderError("LaTeX compilation failed:\n" + tail)
        return open(pdf, "rb").read()
