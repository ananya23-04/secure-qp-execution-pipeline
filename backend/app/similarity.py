"""Stage 2b helper - dependency-free TF-IDF (unigram+bigram) cosine similarity.
Swap `NearDupIndex` for a sentence-embedding backend later without touching the pipeline."""
import math
import re
from collections import Counter

_TOKEN = re.compile(r"\\[a-zA-Z]+|[a-zA-Z0-9]+")


def tokenize(text: str) -> list[str]:
    words = [t.lower() for t in _TOKEN.findall(text)]
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]


def build_idf(docs: list[list[str]]) -> dict[str, float]:
    n = len(docs)
    df: Counter = Counter()
    for d in docs:
        df.update(set(d))
    return {t: math.log((1 + n) / (1 + c)) + 1 for t, c in df.items()}


def vectorize(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    vec = {t: c * idf.get(t, 1.0) for t, c in Counter(tokens).items()}
    norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
    return {t: v / norm for t, v in vec.items()}


def cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(v * b.get(t, 0.0) for t, v in a.items())


class NearDupIndex:
    """Compares only within a group (the subject) to cut cost and false positives."""

    def __init__(self, idf: dict[str, float]):
        self.idf = idf
        self._groups: dict[str, list[tuple[str, dict[str, float]]]] = {}

    def add(self, group: str, key: str, text: str) -> None:
        self._groups.setdefault(group, []).append((key, vectorize(tokenize(text), self.idf)))

    def best_match(self, group: str, text: str) -> tuple[str | None, float]:
        vec = vectorize(tokenize(text), self.idf)
        best_key, best = None, 0.0
        for key, other in self._groups.get(group, []):
            score = cosine(vec, other)
            if score > best:
                best_key, best = key, score
        return best_key, best
