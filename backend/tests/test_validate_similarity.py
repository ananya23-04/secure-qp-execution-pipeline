from app.question_schema import Question
from app.similarity import NearDupIndex, build_idf, tokenize
from app.validate import check_latex, validate_and_normalize
from conftest import sample_question


def test_latex_ok():
    assert check_latex(r"Find $\frac{a}{b}$ and \textbf{note}") == []
    assert check_latex(r"Cost is \$5 and set \{1,2\}") == []


def test_latex_problems():
    assert "UNBALANCED_MATH" in check_latex(r"Evaluate $\int_0^1 x dx")
    assert "UNBALANCED_BRACES" in check_latex(r"\frac{a}{b")
    assert "MISMATCHED_ENV" in check_latex(r"\begin{tabular} x \end{array}")
    assert "MISMATCHED_ENV" in check_latex(r"\begin{tabular} x")


def test_latex_forbidden_commands():
    for bad in [r"\input{/etc/passwd}", r"\write18{ls}", r"\def\x{y}", r"\usepackage{x}"]:
        assert "FORBIDDEN_LATEX" in check_latex(bad)
    assert check_latex(r"\define is not a primitive") == []


def test_normalization_and_option_checks():
    q = Question(**sample_question(subject="  data   structures ", stem="  Define   a   stack ADT clearly.  ",
                                   options=["A", "a", "B"], correct_option=0))
    nq, issues = validate_and_normalize(q)
    assert nq.subject == "Data Structures" and nq.stem == "Define a stack ADT clearly."
    assert "DUPLICATE_OPTIONS" in issues


def test_similarity_flags_reworded_but_not_unrelated():
    a = "Explain the working of the TCP three-way handshake in detail."
    b = "Explain the working of the TCP three way handshake in detail"
    c = "Compare TCP with UDP for real-time streaming applications."
    idf = build_idf([tokenize(a), tokenize(b), tokenize(c)])
    idx = NearDupIndex(idf)
    idx.add("net", "A", a)
    assert idx.best_match("net", b)[1] > 0.95
    assert idx.best_match("net", c)[1] < 0.6
    assert idx.best_match("other-subject", b) == (None, 0.0)
