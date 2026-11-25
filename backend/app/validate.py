"""Stage 2a - Convert & Validate: syntax checks, LaTeX safety, metadata normalisation."""
import re
import unicodedata

from .question_schema import Question

# LaTeX primitives that read files, run code, or define macros (DoS / file-leak risk
# once the renderer compiles this text).
_FORBIDDEN = re.compile(
    r"\\(input|include|includeonly|write|openin|openout|read|immediate|catcode|usepackage|"
    r"documentclass|csname|directlua|verbatiminput|special|def|edef|gdef|xdef|let|"
    r"newcommand|renewcommand|providecommand)(?![A-Za-z])"
)
_ENV = re.compile(r"\\(begin|end)\{([^}]*)\}")


def check_latex(text: str) -> list[str]:
    """Return issue codes for one text field (empty list = OK)."""
    issues: list[str] = []
    if _FORBIDDEN.search(text):
        issues.append("FORBIDDEN_LATEX")
    if len(re.findall(r"(?<!\\)\$", text)) % 2:
        issues.append("UNBALANCED_MATH")
    depth = 0
    i = 0
    while i < len(text):
        c = text[i]
        if c == "\\":
            i += 2          # skip escaped char (\{ \} \\ ...)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth < 0:
                break
        i += 1
    if depth != 0:
        issues.append("UNBALANCED_BRACES")
    stack: list[str] = []
    for kind, name in _ENV.findall(text):
        if kind == "begin":
            stack.append(name)
        elif not stack or stack.pop() != name:
            issues.append("MISMATCHED_ENV")
            break
    else:
        if stack:
            issues.append("MISMATCHED_ENV")
    return issues


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s)).strip()


def validate_and_normalize(q: Question) -> tuple[Question, list[str]]:
    """Normalise metadata/whitespace, then run structural + LaTeX checks."""
    subject = _clean(q.subject)
    if subject.islower():
        subject = subject.title()
    options = [_clean(o) for o in q.options] if q.options else q.options
    nq = q.model_copy(update={
        "stem": _clean(q.stem),
        "subject": subject,
        "options": options,
        "solution_latex": q.solution_latex.strip() if q.solution_latex else None,
    })

    issues: list[str] = []
    if options is not None:
        if any(not o for o in options):
            issues.append("EMPTY_OPTION")
        if len({o.lower() for o in options}) != len(options):
            issues.append("DUPLICATE_OPTIONS")
    for field in [nq.stem, *(options or []), nq.solution_latex or ""]:
        for code in check_latex(field):
            if code not in issues:
                issues.append(code)
    return nq, issues
