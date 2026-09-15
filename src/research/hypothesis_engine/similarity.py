"""Deterministic opponent-similarity interface (`opponent_similarity_v1_pending`).

    The LLM may PROPOSE which similarity dimensions matter.
    It may NOT calculate or invent a similarity score.

STATUS: INTERFACE IMPLEMENTED, METRIC PENDING SCIENTIFIC VALIDATION
-------------------------------------------------------------------
Mandate §10 is explicit: "If the best distance/embedding/clustering methodology is not yet
scientifically defined, implement the interface and mark the similarity metric as pending
validation rather than inventing an arbitrary one."

So this module ships:
  * the full typed interface the query compiler and measurement layer call;
  * a LEAK-FREE cohort resolver based on within-competition BANDING, which is a ranking
    operation, not a distance metric -- it makes no claim about how far apart two teams
    are, only which third of the distribution each fell in before the fixture;
  * an explicit `PENDING_VALIDATION` status on anything that would be a distance.

`rank_band` is safe to use now because it asserts nothing beyond "this opponent was in the
top/middle/bottom third of the competition on this measured axis, using only matches
played strictly before the cohort fixture's kickoff". A Euclidean/Mahalanobis/embedding
distance over a hand-picked feature set would assert far more, and nothing in the
repository yet justifies a particular choice.

LEAKAGE RULE
------------
At fixture time T, every feature used to band an opponent must come from matches with
kickoff strictly < T. `resolve_band` takes the cutoff as a REQUIRED argument and filters on
it; there is no code path that bands an opponent from its full-season record.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Optional, Sequence

from . import vocabulary

SIMILARITY_VERSION = "opponent_similarity_v1_pending"

#: Methodologies this module could expose, and their scientific status.
METHOD_STATUS = {
    "RANK_BAND": "AVAILABLE",
    "EUCLIDEAN_DISTANCE": "PENDING_VALIDATION",
    "MAHALANOBIS_DISTANCE": "PENDING_VALIDATION",
    "LEARNED_EMBEDDING": "PENDING_VALIDATION",
    "CLUSTER_ASSIGNMENT": "PENDING_VALIDATION",
}

PENDING_VALIDATION = "PENDING_VALIDATION"
AVAILABLE = "AVAILABLE"


class SimilarityMethodPending(NotImplementedError):
    """Raised when a caller asks for a distance the repository has not yet validated.

    Deliberately an exception rather than a silent fallback to RANK_BAND: a research
    result computed with an unvalidated distance, labelled as if it were validated, is
    worse than no result.
    """


@dataclass(frozen=True)
class BandAssignment:
    """Which band an opponent fell into on one measured axis, and the evidence for it."""

    opponent: str
    axis: str
    band: str                  # LOW | MID | HIGH
    value: float
    sample_n: int
    cutoff_unix: int
    method: str = "RANK_BAND"
    status: str = AVAILABLE

    def to_dict(self) -> dict:
        return {
            "opponent": self.opponent, "axis": self.axis, "band": self.band,
            "value": self.value, "sample_n": self.sample_n,
            "cutoff_unix": self.cutoff_unix, "method": self.method,
            "status": self.status, "similarity_version": SIMILARITY_VERSION,
        }


@dataclass
class CohortResolution:
    """The set of historical opponents matching a requested profile band."""

    axis: str
    requested_band: str
    cutoff_unix: int
    members: tuple[str, ...] = ()
    assignments: tuple[BandAssignment, ...] = ()
    candidate_n: int = 0
    usable_n: int = 0
    missing_n: int = 0
    notes: tuple[str, ...] = ()

    @property
    def coverage_rate(self) -> float:
        return (self.usable_n / self.candidate_n) if self.candidate_n else 0.0

    def to_dict(self) -> dict:
        return {
            "similarity_version": SIMILARITY_VERSION,
            "method": "RANK_BAND",
            "status": AVAILABLE,
            "axis": self.axis,
            "requested_band": self.requested_band,
            "cutoff_unix": self.cutoff_unix,
            "members": list(self.members),
            "candidate_n": self.candidate_n,
            "usable_n": self.usable_n,
            "missing_n": self.missing_n,
            "coverage_rate": round(self.coverage_rate, 4),
            "assignments": [a.to_dict() for a in self.assignments],
            "notes": list(self.notes),
        }


#: Minimum prior matches before an opponent can be banded at all. Below this the opponent
#: is counted in `missing_n`, never guessed into a band.
MIN_PRIOR_MATCHES = 4

#: Tercile cut points. A ranking, not a distance.
_LOW_Q, _HIGH_Q = 1 / 3, 2 / 3


def _quantile(sorted_vals: Sequence[float], q: float) -> float:
    if not sorted_vals:
        raise ValueError("empty")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def resolve_band(
    *,
    axis: str,
    requested_band: str,
    cutoff_unix: int,
    candidates: Iterable[str],
    axis_value_fn: Callable[[str, int], Optional[tuple[float, int]]],
    method: str = "RANK_BAND",
) -> CohortResolution:
    """Resolve "opponents whose <axis> profile is <band>" into a concrete opponent set.

    Parameters
    ----------
    axis
        One of `vocabulary.PROFILE_AXES`.
    requested_band
        LOW / MID / HIGH / ANY.
    cutoff_unix
        Hard leakage boundary. `axis_value_fn` MUST use only matches before this.
    candidates
        The historical opponents in scope.
    axis_value_fn
        (opponent, cutoff_unix) -> (value, sample_n) or None when unavailable. Supplied by
        the measurement layer so this module never reads data directly and stays testable
        with frozen fixtures.
    """
    status = METHOD_STATUS.get(method)
    if status is None:
        raise SimilarityMethodPending(f"unknown similarity method {method!r}")
    if status == PENDING_VALIDATION:
        raise SimilarityMethodPending(
            f"similarity method {method!r} is {PENDING_VALIDATION}: no study in this "
            f"repository justifies its parameters, so it may not produce a research "
            f"result. Available now: "
            f"{[m for m, s in METHOD_STATUS.items() if s == AVAILABLE]}")

    if axis not in vocabulary.PROFILE_AXES:
        raise ValueError(f"axis {axis!r} not in {list(vocabulary.PROFILE_AXES)}")
    if requested_band not in vocabulary.PROFILE_BANDS:
        raise ValueError(f"band {requested_band!r} not in {list(vocabulary.PROFILE_BANDS)}")

    cands = list(candidates)
    measured: list[tuple[str, float, int]] = []
    missing = 0

    for opp in cands:
        got = axis_value_fn(opp, cutoff_unix)
        if got is None:
            missing += 1
            continue
        value, n = got
        if value is None or n is None or n < MIN_PRIOR_MATCHES:
            missing += 1
            continue
        measured.append((opp, float(value), int(n)))

    notes: list[str] = []
    if requested_band == "ANY":
        assignments = tuple(
            BandAssignment(o, axis, "ANY", v, n, cutoff_unix) for o, v, n in measured)
        return CohortResolution(axis, requested_band, cutoff_unix,
                                tuple(o for o, _, _ in measured), assignments,
                                len(cands), len(measured), missing,
                                ("band=ANY: no banding applied",))

    if len(measured) < 3:
        notes.append(f"only {len(measured)} bandable opponents (< 3); cannot form terciles "
                     f"without asserting more than the data supports")
        return CohortResolution(axis, requested_band, cutoff_unix, (), (),
                                len(cands), 0, missing + len(measured), tuple(notes))

    vals = sorted(v for _, v, _ in measured)
    lo_cut, hi_cut = _quantile(vals, _LOW_Q), _quantile(vals, _HIGH_Q)

    assignments: list[BandAssignment] = []
    members: list[str] = []
    for opp, v, n in measured:
        band = "LOW" if v <= lo_cut else ("HIGH" if v >= hi_cut else "MID")
        assignments.append(BandAssignment(opp, axis, band, v, n, cutoff_unix))
        if band == requested_band:
            members.append(opp)

    notes.append(f"terciles from {len(measured)} opponents banded strictly before "
                 f"cutoff_unix={cutoff_unix}; cuts lo<={lo_cut:.4g}, hi>={hi_cut:.4g}")

    return CohortResolution(axis, requested_band, cutoff_unix, tuple(sorted(members)),
                            tuple(assignments), len(cands), len(measured), missing,
                            tuple(notes))


def reject_llm_supplied_similarity(hypothesis: dict) -> list[str]:
    """Return reasons if a hypothesis tries to supply a similarity score itself.

    The schema already makes this structurally impossible (no numeric field exists), so
    this is a defence-in-depth check used by tests and by any future looser input path.
    """
    reasons: list[str] = []

    def walk(o, path):
        if isinstance(o, dict):
            for k, v in o.items():
                kl = k.lower()
                if any(t in kl for t in ("similarity", "distance", "closeness",
                                         "resemblance", "match_score")):
                    reasons.append(
                        f"{path}.{k}: the LLM may name a similarity DIMENSION but may not "
                        f"supply a similarity value; similarity is computed "
                        f"deterministically by {SIMILARITY_VERSION}")
                walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]")

    walk(hypothesis, "$")
    return reasons
