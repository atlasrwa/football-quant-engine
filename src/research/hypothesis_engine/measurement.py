"""Deterministic measurement executor (`hypothesis_measurement_v1`).

    The deterministic engine measures it. Sonnet does not generate these values.

This module is where every number in the research record is produced. It takes a compiled
`QueryPlan` and returns a `MeasurementResult`: sample sizes, coverage, conditional and
baseline statistics, their difference, a shrunk difference and an uncertainty estimate.

It reads history through an injected `HistoryProvider` protocol rather than touching the
corpus directly, for three reasons: the leakage boundary stays in one testable place, the
whole module runs against frozen fixtures with no I/O, and the production corpus loader can
be swapped without touching the statistics.

SHRINKAGE
---------
`n / (n + K)` with `K = 6`, matching `cohorts.SHRINK_K` and the matchup layer, so a
candidate feature produced here is on the same footing as the existing evidence engine's
estimates rather than a differently-regularized quantity.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
No probability, no calibration, no market comparison, no edge. A difference in corners per
match is a football measurement; converting it into a probability is the quant engine's
job and happens far downstream, behind the walk-forward gate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Optional, Protocol, Sequence

from . import lifecycle
from .query_plan import QueryPlan

MEASUREMENT_VERSION = "hypothesis_measurement_v1"

#: Empirical-Bayes shrinkage strength. Matches cohorts.SHRINK_K.
SHRINK_K = 6.0

#: Below this the cohort is reported INSUFFICIENT_DATA rather than estimated.
MIN_CONDITIONAL_N = 4
MIN_BASELINE_N = 8


@dataclass(frozen=True)
class Observation:
    """One historical match contributing to a cohort."""

    fixture_id: str
    kickoff_unix: int
    value: Optional[float]
    #: dimension -> value, as recorded for THIS match (venue, formation family, ...)
    dimensions: dict = field(default_factory=dict)


class HistoryProvider(Protocol):
    """Supplies prior observations for a subject. Implementations MUST filter on cutoff."""

    def observations(
        self, *, subject_team: str, metric: str, side: str, period: str,
        provider: str, cutoff_unix: int,
    ) -> Sequence[Observation]:
        ...


@dataclass
class CohortStats:
    n: int
    usable_n: int
    missing_n: int
    mean: Optional[float]
    median: Optional[float]
    sd: Optional[float]

    @property
    def coverage_rate(self) -> float:
        return (self.usable_n / self.n) if self.n else 0.0

    def to_dict(self) -> dict:
        return {
            "n": self.n, "usable_n": self.usable_n, "missing_n": self.missing_n,
            "coverage_rate": round(self.coverage_rate, 4),
            "mean": self.mean, "median": self.median, "sd": self.sd,
        }


@dataclass
class MeasurementResult:
    plan_hash: str
    metric: str
    provider: str
    cutoff_unix: int
    conditional: CohortStats
    baseline: CohortStats
    difference: Optional[float] = None
    shrunk_difference: Optional[float] = None
    shrinkage_weight: Optional[float] = None
    se: Optional[float] = None
    status: str = lifecycle.HISTORICAL_RESULT
    failure: Optional[str] = None
    notes: list[str] = field(default_factory=list)
    #: Per-dimension coverage, always reported for formation-conditioned queries (§7).
    dimension_coverage: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "measurement_version": MEASUREMENT_VERSION,
            "plan_hash": self.plan_hash,
            "metric": self.metric,
            "provider": self.provider,
            "cutoff_unix": self.cutoff_unix,
            "conditional": self.conditional.to_dict(),
            "baseline": self.baseline.to_dict(),
            "difference": self.difference,
            "shrunk_difference": self.shrunk_difference,
            "shrinkage_weight": self.shrinkage_weight,
            "se": self.se,
            "status": self.status,
            "failure": self.failure,
            "notes": list(self.notes),
            "dimension_coverage": dict(self.dimension_coverage),
        }


def _stats(values: Sequence[Optional[float]]) -> CohortStats:
    n = len(values)
    usable = [v for v in values if v is not None]
    k = len(usable)
    if k == 0:
        return CohortStats(n, 0, n, None, None, None)
    s = sorted(usable)
    mean = sum(s) / k
    mid = k // 2
    median = s[mid] if k % 2 else (s[mid - 1] + s[mid]) / 2
    sd = math.sqrt(sum((v - mean) ** 2 for v in s) / (k - 1)) if k > 1 else 0.0
    return CohortStats(n, k, n - k, mean, median, sd)


def _matches_conditions(obs: Observation, plan: QueryPlan) -> Optional[bool]:
    """True/False if the match's dimensions decide it; None when a required dimension is
    NOT RECORDED for this match.

    None is distinct from False on purpose. A match with no recorded formation is not
    evidence that the formation differed -- it is missing data, and counting it as a
    non-member would silently bias every formation-conditioned result.
    """
    for cond in plan.conditions:
        if cond.dimension == "period":
            continue
        if cond.value == "ANY":
            continue
        recorded = obs.dimensions.get(cond.dimension)
        if recorded is None:
            return None
        if recorded != cond.value:
            return False
    return True


def _window_slice(obs: Sequence[Observation], window: str) -> Sequence[Observation]:
    ordered = sorted(obs, key=lambda o: o.kickoff_unix)
    if window == "W5":
        return ordered[-5:]
    if window == "W10":
        return ordered[-10:]
    return ordered      # SEASON_TO_DATE / ALL_PRIOR are pre-filtered by the provider


def execute(plan: QueryPlan, *, subject_team: str, history: HistoryProvider
            ) -> MeasurementResult:
    """Run one compiled plan. Every value in the result is computed here, never supplied."""
    raw = list(history.observations(
        subject_team=subject_team, metric=plan.metric, side=plan.side,
        period=plan.period, provider=plan.provider, cutoff_unix=plan.cutoff_unix))

    # Leakage backstop: the provider is contractually required to filter, but a research
    # record is not the place to trust a contract.
    leaked = [o for o in raw if o.kickoff_unix >= plan.cutoff_unix]
    if leaked:
        return MeasurementResult(
            plan.plan_hash(), plan.metric, plan.provider, plan.cutoff_unix,
            _stats([]), _stats([]),
            status=lifecycle.LEAKAGE_REJECTED, failure=lifecycle.LEAKAGE_REJECTED,
            notes=[f"history provider returned {len(leaked)} observation(s) at or after "
                   f"cutoff_unix={plan.cutoff_unix}; refusing to measure"])

    baseline_obs = _window_slice(raw, plan.window)

    conditional_obs: list[Observation] = []
    undetermined = 0
    for o in baseline_obs:
        m = _matches_conditions(o, plan)
        if m is None:
            undetermined += 1
        elif m:
            conditional_obs.append(o)

    cond = _stats([o.value for o in conditional_obs])
    base = _stats([o.value for o in baseline_obs])

    # Per-dimension coverage, always reported (mandate §7).
    dim_cov: dict[str, dict] = {}
    for c in plan.conditions:
        if c.dimension == "period" or c.value == "ANY":
            continue
        recorded = sum(1 for o in baseline_obs if o.dimensions.get(c.dimension) is not None)
        dim_cov[c.dimension] = {
            "candidate_n": len(baseline_obs),
            "usable_n": recorded,
            "missing_n": len(baseline_obs) - recorded,
            "coverage_rate": round(recorded / len(baseline_obs), 4) if baseline_obs else 0.0,
        }

    notes: list[str] = []
    if undetermined:
        notes.append(
            f"{undetermined} match(es) had no recorded value for a conditioned dimension "
            f"and were excluded from the conditional cohort WITHOUT being counted as "
            f"non-members (missing data is not evidence of difference)")

    result = MeasurementResult(
        plan.plan_hash(), plan.metric, plan.provider, plan.cutoff_unix,
        cond, base, notes=notes, dimension_coverage=dim_cov)

    if cond.usable_n < MIN_CONDITIONAL_N or base.usable_n < MIN_BASELINE_N:
        result.status = lifecycle.INSUFFICIENT_DATA
        result.failure = lifecycle.INSUFFICIENT_DATA
        result.notes.append(
            f"conditional usable_n={cond.usable_n} (min {MIN_CONDITIONAL_N}), "
            f"baseline usable_n={base.usable_n} (min {MIN_BASELINE_N}); reported as "
            f"INSUFFICIENT_DATA rather than as a null effect")
        return result

    result.difference = cond.mean - base.mean
    w = cond.usable_n / (cond.usable_n + SHRINK_K)
    result.shrinkage_weight = round(w, 6)
    result.shrunk_difference = w * result.difference

    if cond.sd is not None and base.sd is not None and cond.usable_n and base.usable_n:
        result.se = math.sqrt((cond.sd ** 2) / cond.usable_n + (base.sd ** 2) / base.usable_n)

    return result


def execute_all(plans: Iterable[QueryPlan], *, subject_resolver, history: HistoryProvider
                ) -> list[MeasurementResult]:
    """Run many plans. `subject_resolver(plan) -> team name` maps HOME_TEAM/AWAY_TEAM to
    the actual club for the fixture, keeping identity resolution out of the statistics."""
    return [execute(p, subject_team=subject_resolver(p), history=history) for p in plans]
