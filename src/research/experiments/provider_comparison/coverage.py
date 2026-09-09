"""Coverage & disagreement study (Phase 3).

Measures data quality per provider/concept BEFORE any predictive comparison:
availability, missing rate, zero rate, support, and — where both providers
report a concept — disagreement statistics (mean signed/abs difference, median
abs difference, correlation, quantiles, large-disagreement rate).

Only the genuinely-overlapping concepts from ``fields.OVERLAPPING_CONCEPTS`` are
compared. NULL != ZERO is respected: a missing value is missing, a genuine 0 is
0, and the two are counted separately (missing_rate vs zero_rate).

Timestamp availability is reported honestly: for this dataset, stat
observations have no capture timestamp (see pit.py), so timestamp availability
is 0.0 for both providers' stats.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Optional

from src.research.experiments.provider_comparison.dataset import PairedFixture


def _quantile(sorted_vals: list[float], q: float) -> Optional[float]:
    if not sorted_vals:
        return None
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    pos = q * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return sorted_vals[lo]
    frac = pos - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _pearson(xs: list[float], ys: list[float]) -> Optional[float]:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    if sxx == 0 or syy == 0:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)


@dataclass
class ProviderConceptCoverage:
    provider: str
    concept: str
    n_fixtures: int
    n_present: int
    n_zero: int

    @property
    def availability(self) -> float:
        return self.n_present / self.n_fixtures if self.n_fixtures else 0.0

    @property
    def missing_rate(self) -> float:
        return 1.0 - self.availability

    @property
    def zero_rate(self) -> float:
        return self.n_zero / self.n_present if self.n_present else 0.0

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "concept": self.concept,
            "n_fixtures": self.n_fixtures,
            "n_present": self.n_present,
            "availability": round(self.availability, 4),
            "missing_rate": round(self.missing_rate, 4),
            "zero_rate": round(self.zero_rate, 4),
            "timestamp_availability": 0.0,  # stats carry no capture time (pit.py)
        }


@dataclass
class ConceptDisagreement:
    concept: str
    n_both_present: int
    mean_signed_diff: Optional[float] = None      # footystats - thestatsapi
    mean_abs_diff: Optional[float] = None
    median_abs_diff: Optional[float] = None
    correlation: Optional[float] = None
    q90_abs_diff: Optional[float] = None
    max_abs_diff: Optional[float] = None
    large_disagreement_rate: Optional[float] = None  # frac |diff| > threshold
    large_threshold: Optional[float] = None
    fs_only: int = 0
    tsa_only: int = 0

    def to_dict(self) -> dict:
        return {
            "concept": self.concept,
            "n_both_present": self.n_both_present,
            "fs_only": self.fs_only,
            "tsa_only": self.tsa_only,
            "mean_signed_diff_fs_minus_tsa": _r(self.mean_signed_diff),
            "mean_abs_diff": _r(self.mean_abs_diff),
            "median_abs_diff": _r(self.median_abs_diff),
            "correlation": _r(self.correlation),
            "q90_abs_diff": _r(self.q90_abs_diff),
            "max_abs_diff": _r(self.max_abs_diff),
            "large_disagreement_rate": _r(self.large_disagreement_rate),
            "large_threshold": self.large_threshold,
        }


def _r(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(x, 4)


# Per-concept "large disagreement" thresholds (absolute units of the concept).
_LARGE_THRESHOLDS = {
    "total_goals": 0.5,
    "total_corners": 1.5,
    "total_cards": 1.5,
    "shots": 3.0,
    "shots_on_target": 2.0,
    "xg": 0.5,
    "possession": 5.0,
}


def concept_coverage(
    fixtures: list[PairedFixture], concept: str, provider: str
) -> ProviderConceptCoverage:
    n = len(fixtures)
    present = 0
    zeros = 0
    for f in fixtures:
        v = f.value(provider, concept)
        if v is not None:
            present += 1
            if v == 0:
                zeros += 1
    return ProviderConceptCoverage(provider, concept, n, present, zeros)


def concept_disagreement(fixtures: list[PairedFixture], concept: str) -> ConceptDisagreement:
    both_fs: list[float] = []
    both_tsa: list[float] = []
    fs_only = 0
    tsa_only = 0
    for f in fixtures:
        obs = f.concepts.get(concept)
        if obs is None:
            continue
        fs, tsa = obs.footystats, obs.thestatsapi
        if fs is not None and tsa is not None:
            both_fs.append(fs)
            both_tsa.append(tsa)
        elif fs is not None:
            fs_only += 1
        elif tsa is not None:
            tsa_only += 1

    d = ConceptDisagreement(concept=concept, n_both_present=len(both_fs),
                            fs_only=fs_only, tsa_only=tsa_only)
    if not both_fs:
        return d
    diffs = [a - b for a, b in zip(both_fs, both_tsa)]
    abs_diffs = sorted(abs(x) for x in diffs)
    thr = _LARGE_THRESHOLDS.get(concept, 1.0)
    d.mean_signed_diff = sum(diffs) / len(diffs)
    d.mean_abs_diff = sum(abs_diffs) / len(abs_diffs)
    d.median_abs_diff = statistics.median(abs_diffs)
    d.correlation = _pearson(both_fs, both_tsa)
    d.q90_abs_diff = _quantile(abs_diffs, 0.90)
    d.max_abs_diff = abs_diffs[-1]
    d.large_disagreement_rate = sum(1 for x in abs_diffs if x > thr) / len(abs_diffs)
    d.large_threshold = thr
    return d


@dataclass
class CoverageReport:
    league: str
    n_fixtures: int
    coverage: list[dict] = field(default_factory=list)
    disagreement: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "league": self.league,
            "n_fixtures": self.n_fixtures,
            "coverage": self.coverage,
            "disagreement": self.disagreement,
        }


def build_coverage_report(
    fixtures: list[PairedFixture], concepts: list[str], *, league: str
) -> CoverageReport:
    rep = CoverageReport(league=league, n_fixtures=len(fixtures))
    for c in concepts:
        for prov in ("footystats", "thestatsapi"):
            rep.coverage.append(concept_coverage(fixtures, c, prov).to_dict())
        rep.disagreement.append(concept_disagreement(fixtures, c).to_dict())
    return rep
