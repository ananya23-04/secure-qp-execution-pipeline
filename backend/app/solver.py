"""Random QP Generator: CP-SAT builds N parallel paper sets from the approved bank.

Hard constraints per set: exact total marks, exact marks per unit, difficulty-class marks
inside a tolerance window, optional minimum higher-order (Bloom) share, optional exact marks
per question type. Across sets: identical difficulty profile and bounded pairwise overlap.
Randomness comes only from the commit-reveal seed (random objective weights), and the solver
runs single-threaded with a deterministic time limit, so the same inputs reproduce the same sets."""
import hashlib
import math
from dataclasses import dataclass

from ortools.sat.python import cp_model
from pydantic import BaseModel, Field, field_validator, model_validator

HIGHER_ORDER = {"analyze", "evaluate", "create"}
QTYPE_RANK = {"mcq": 0, "short": 1, "long": 2}


class InfeasibleError(Exception):
    pass


class ExamBlueprint(BaseModel):
    subject: str = Field(min_length=2)
    num_sets: int = Field(default=3, ge=1, le=6)
    total_marks: int = Field(gt=0, le=500)
    units: dict[int, int] = Field(description="unit number -> marks required from that unit")
    difficulty_mix: dict[str, float] = Field(default={"easy": 0.3, "medium": 0.5, "hard": 0.2})
    difficulty_tolerance: float = Field(default=0.10, ge=0.0, le=0.5,
                                        description="allowed deviation as a fraction of total marks")
    min_higher_order_pct: float = Field(default=0.0, ge=0.0, le=100.0,
                                        description="min % of marks from analyze/evaluate/create")
    qtype_marks: dict[str, int] | None = Field(default=None, description="exact marks per qtype")
    max_overlap_pct: float = Field(default=30.0, ge=0.0, le=100.0,
                                   description="max % of total marks shared by any two sets")

    @field_validator("difficulty_mix")
    @classmethod
    def _mix(cls, v):
        if not set(v) <= {"easy", "medium", "hard"}:
            raise ValueError("difficulty_mix keys must be easy/medium/hard")
        if abs(sum(v.values()) - 1.0) > 0.01:
            raise ValueError("difficulty_mix must sum to 1")
        return {k: v.get(k, 0.0) for k in ("easy", "medium", "hard")}

    @model_validator(mode="after")
    def _sums(self):
        if not self.units or any(m < 1 for m in self.units.values()):
            raise ValueError("units must be non-empty with marks >= 1")
        if sum(self.units.values()) != self.total_marks:
            raise ValueError("unit marks must sum to total_marks")
        if self.qtype_marks is not None:
            if not set(self.qtype_marks) <= set(QTYPE_RANK):
                raise ValueError("qtype_marks keys must be mcq/short/long")
            if sum(self.qtype_marks.values()) != self.total_marks:
                raise ValueError("qtype_marks must sum to total_marks")
        return self


@dataclass(frozen=True)
class Candidate:
    id: str
    unit: int
    marks: int
    difficulty: float
    bloom: str
    qtype: str
    fingerprint: str


def diff_class(d: float) -> str:
    return "easy" if d < 1 / 3 else "medium" if d < 2 / 3 else "hard"


def _weight(seed: str, s: int, cid: str) -> int:
    return int(hashlib.sha256(f"{seed}|{s}|{cid}".encode()).hexdigest()[:8], 16) % 1000


def _order_key(seed: str, s: int, c: Candidate):
    return (QTYPE_RANK.get(c.qtype, 9), c.unit, _weight(seed, s + 100, c.id), c.id)


def _range(model, terms, lo, hi, why):
    """lo <= sum(terms) <= hi, handling the empty-sum case explicitly."""
    if not terms:
        if lo > 0:
            raise InfeasibleError(why)
        return
    expr = sum(terms)
    model.Add(expr >= lo)
    model.Add(expr <= hi)


def generate_sets(cands: list[Candidate], bp: ExamBlueprint, seed: str) -> list[list[Candidate]]:
    cands = sorted(cands, key=lambda c: c.id)
    n, S, T = len(cands), bp.num_sets, bp.total_marks
    model = cp_model.CpModel()
    x = [[model.NewBoolVar(f"x{s}_{i}") for i in range(n)] for s in range(S)]
    tol = math.ceil(bp.difficulty_tolerance * T)
    profile: list[dict[str, list]] = []

    for s in range(S):
        _range(model, [c.marks * x[s][i] for i, c in enumerate(cands)], T, T, "no candidates")
        for unit, m in bp.units.items():
            _range(model, [c.marks * x[s][i] for i, c in enumerate(cands) if c.unit == unit], m, m,
                   f"no approved questions for unit {unit}")
        prof = {}
        for cls, share in bp.difficulty_mix.items():
            target = round(share * T)
            terms = [c.marks * x[s][i] for i, c in enumerate(cands) if diff_class(c.difficulty) == cls]
            _range(model, terms, max(0, target - tol), target + tol, f"no {cls} questions available")
            prof[cls] = terms
        profile.append(prof)
        if s > 0:                                   # parity: same difficulty profile in every set
            for cls in prof:
                if prof[cls] and profile[0][cls]:
                    model.Add(sum(prof[cls]) == sum(profile[0][cls]))
        if bp.min_higher_order_pct > 0:
            need = math.ceil(bp.min_higher_order_pct / 100 * T)
            _range(model, [c.marks * x[s][i] for i, c in enumerate(cands) if c.bloom in HIGHER_ORDER],
                   need, T, "not enough higher-order (analyze/evaluate/create) questions")
        if bp.qtype_marks:
            for qt, m in bp.qtype_marks.items():
                _range(model, [c.marks * x[s][i] for i, c in enumerate(cands) if c.qtype == qt], m, m,
                       f"no '{qt}' questions available")

    if S > 1 and bp.max_overlap_pct < 100:
        max_shared = math.floor(bp.max_overlap_pct / 100 * T)
        for a in range(S):
            for b in range(a + 1, S):
                shared = []
                for i, c in enumerate(cands):
                    y = model.NewBoolVar(f"y{a}_{b}_{i}")
                    model.Add(y >= x[a][i] + x[b][i] - 1)
                    shared.append(c.marks * y)
                if shared:
                    model.Add(sum(shared) <= max_shared)

    model.Maximize(sum(_weight(seed, s, c.id) * x[s][i] for s in range(S) for i, c in enumerate(cands)))

    solver = cp_model.CpSolver()
    p = solver.parameters
    try:
        p.num_workers = 1
    except AttributeError:                      # older OR-Tools
        p.num_search_workers = 1
    p.random_seed = int(seed[:8], 16) % (2**31 - 1)
    p.relative_gap_limit = 0.03                 # random weights: near-best is plenty, no need to prove optimal
    p.max_deterministic_time = 2.0              # deterministic budget -> reproducible output
    p.max_time_in_seconds = 180.0               # wall-clock safety net only
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise InfeasibleError(
            "No set of papers satisfies all constraints with the current approved bank. "
            "Add approved questions, relax difficulty_tolerance / max_overlap_pct, or adjust the blueprint."
            if status == cp_model.INFEASIBLE else "Solver found no solution within its budget.")

    return [
        sorted((c for i, c in enumerate(cands) if solver.Value(x[s][i])), key=lambda c, s=s: _order_key(seed, s, c))
        for s in range(S)
    ]


def paper_hash(paper: list[Candidate]) -> str:
    return hashlib.sha256("\n".join(c.fingerprint for c in paper).encode()).hexdigest()


def summarize(paper: list[Candidate]) -> dict:
    by_unit: dict[int, int] = {}
    by_diff = {"easy": 0, "medium": 0, "hard": 0}
    by_qtype: dict[str, int] = {}
    higher = 0
    for c in paper:
        by_unit[c.unit] = by_unit.get(c.unit, 0) + c.marks
        by_diff[diff_class(c.difficulty)] += c.marks
        by_qtype[c.qtype] = by_qtype.get(c.qtype, 0) + c.marks
        higher += c.marks if c.bloom in HIGHER_ORDER else 0
    return {"questions": len(paper), "total_marks": sum(c.marks for c in paper),
            "marks_by_unit": dict(sorted(by_unit.items())), "marks_by_difficulty": by_diff,
            "marks_by_qtype": by_qtype, "higher_order_marks": higher, "paper_hash": paper_hash(paper)}


def check_constraints(sets: list[list[Candidate]], bp: ExamBlueprint) -> list[str]:
    """Independent audit of finished papers against the blueprint (used by /verify)."""
    bad: list[str] = []
    T, tol = bp.total_marks, math.ceil(bp.difficulty_tolerance * bp.total_marks)
    sums = [summarize(p) for p in sets]
    for k, (p, sm) in enumerate(zip(sets, sums)):
        tag = f"set {chr(65 + k)}"
        if len({c.id for c in p}) != len(p):
            bad.append(f"{tag}: repeated question")
        if sm["total_marks"] != T:
            bad.append(f"{tag}: total marks {sm['total_marks']} != {T}")
        for u, m in bp.units.items():
            if sm["marks_by_unit"].get(u, 0) != m:
                bad.append(f"{tag}: unit {u} marks mismatch")
        for cls, share in bp.difficulty_mix.items():
            if abs(sm["marks_by_difficulty"][cls] - round(share * T)) > tol:
                bad.append(f"{tag}: {cls} marks outside tolerance")
        if sm["marks_by_difficulty"] != sums[0]["marks_by_difficulty"]:
            bad.append(f"{tag}: difficulty profile differs from set A")
        if sm["higher_order_marks"] < math.ceil(bp.min_higher_order_pct / 100 * T):
            bad.append(f"{tag}: higher-order share too low")
        if bp.qtype_marks:
            for qt, m in bp.qtype_marks.items():
                if sm["marks_by_qtype"].get(qt, 0) != m:
                    bad.append(f"{tag}: {qt} marks mismatch")
    max_shared = math.floor(bp.max_overlap_pct / 100 * T)
    for a in range(len(sets)):
        for b in range(a + 1, len(sets)):
            shared = sum(c.marks for c in sets[a] if c.id in {d.id for d in sets[b]})
            if shared > max_shared:
                bad.append(f"sets {chr(65 + a)}/{chr(65 + b)}: overlap {shared} marks > {max_shared}")
    return bad
