"""Deterministic historical cohort measurement (`cohort_measurement_v1`).

    The LLM proposed what to measure. This module measures it. Nothing here reads a
    model response, an outcome, a price or a probability.

This is the first DOWNSTREAM stage after the frozen V3 hypothesis battery: it turns a
compiled `query_plan.QueryPlan` into a fully-resolved `MeasurementSpec`, executes it
against the real dual-provider corpus, and reports descriptive statistics for the
conditional cohort and for the EXACT comparison cohort the plan encodes.

WHY THIS IS NOT `measurement.py`
--------------------------------
`measurement.py` (`hypothesis_measurement_v1`) is the V1-era executor. It ignores
`plan.comparison` entirely -- its baseline is unconditionally the window slice, i.e. only
`SUBJECT_OVERALL_BASELINE`. Four of the five frozen comparisons have no implementation
there. Rather than edit a module the V3 battery ran beside, this one is added alongside
it: `query_plan.py` is in the V3 frozen module-hash manifest and must compile exactly as
it did during the paid run.

Three-valued condition logic, the cutoff backstop, the shrinkage constant and the sample
floors are all carried over from `measurement.py` / `cohorts.py` deliberately, so a number
produced here sits on the same footing as the existing evidence engine's estimates.

WHAT THIS DELIBERATELY DOES NOT DO
----------------------------------
No probability, no calibration, no market comparison, no edge, no feature promotion, no
significance test. A conditional-minus-comparison difference is a DESCRIPTIVE_ASSOCIATION
and is labelled as one; turning it into a predictive claim requires the later preregistered
confounder-aware and walk-forward stages.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from . import capability, similarity, vocabulary
from .query_plan import QueryPlan

COHORT_MEASUREMENT_VERSION = "cohort_measurement_v1"

# ---- canonical project conventions, reused verbatim (never re-derived here) -----------
#: src/research/llm_matchup/cohorts.py:28 and src/research/hypothesis_engine/measurement.py:38
SHRINK_K = 6.0
#: src/research/hypothesis_engine/measurement.py:41-42
MIN_CONDITIONAL_N = 4
MIN_COMPARISON_N = 8
#: src/research/hypothesis_engine/similarity.py:122
MIN_PRIOR_MATCHES = similarity.MIN_PRIOR_MATCHES
#: src/research/llm_matchup/cohorts.py:27
MIN_HISTORY = 4

CANONICAL_CONVENTION_SOURCES = {
    "SHRINK_K": "src/research/llm_matchup/cohorts.py:28 (= measurement.py:38)",
    "MIN_CONDITIONAL_N": "src/research/hypothesis_engine/measurement.py:41",
    "MIN_COMPARISON_N": "src/research/hypothesis_engine/measurement.py:42",
    "MIN_PRIOR_MATCHES": "src/research/hypothesis_engine/similarity.py:122",
    "MIN_HISTORY": "src/research/llm_matchup/cohorts.py:27",
    "reliability_bands": "src/research/hypothesis_engine/context_packet.py:70 "
                         "(LOW <8, MEDIUM 8-19, HIGH >=20)",
}

# ---- typed outcomes -------------------------------------------------------------------
MEASURED = "MEASURED"
UNSUPPORTED_METRIC = "UNSUPPORTED_METRIC"
UNSUPPORTED_DIMENSION = "UNSUPPORTED_DIMENSION"
UNSUPPORTED_PROFILE_AXIS = "UNSUPPORTED_PROFILE_AXIS"
UNSUPPORTED_COMPARISON = "UNSUPPORTED_COMPARISON"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
NOT_DISTINCT = "NOT_DISTINCT"
LEAKAGE_REJECTED = "LEAKAGE_REJECTED"

#: Outcomes that mean "the corpus cannot answer this question", as distinct from
#: INSUFFICIENT_DATA, which means "the corpus can answer it but has too few matches".
UNSUPPORTED_OUTCOMES = frozenset({
    UNSUPPORTED_METRIC, UNSUPPORTED_DIMENSION, UNSUPPORTED_PROFILE_AXIS,
    UNSUPPORTED_COMPARISON})

#: Profile-band semantics. Bands are resolved ONCE, at the target fixture cutoff, using
#: `similarity.resolve_band` exactly as designed. The alternative -- re-banding at each
#: cohort match's own kickoff -- shifts the tercile reference population per match, so two
#: members of the same "HIGH" cohort would not be HIGH against the same distribution. That
#: is a different estimand and no module in this repository validates it. Recorded here
#: and carried into the confounder inventory as a limitation for the next stage.
PROFILE_BAND_SEMANTICS = "AS_OF_TARGET_CUTOFF"

#: Which (metric, side) a profile axis resolves to. Suffix-driven, not a lookup table, so
#: a new axis cannot silently resolve to nothing.
_AXIS_SUFFIXES = (("_for", "FOR"), ("_against", "AGAINST"))


def axis_to_metric_side(axis: str) -> Optional[tuple[str, str]]:
    for suffix, side in _AXIS_SUFFIXES:
        if axis.endswith(suffix):
            metric = axis[: -len(suffix)]
            if capability.is_supported_metric(metric):
                return metric, side
            return None
    return None


# --------------------------------------------------------------------------------------
# Observations
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Obs:
    """One historical match contributing to a cohort. `opponent` is required because
    opponent-profile bands are resolved on club identity, not on a recorded field."""

    fixture_id: str
    kickoff_unix: int
    competition: str
    opponent: str
    value: Optional[float]
    dimensions: dict = field(default_factory=dict)


# --------------------------------------------------------------------------------------
# Specification
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class MeasurementSpec:
    """A fully-resolved historical measurement request, derived only from a compiled
    QueryPlan plus deterministic fixture resolution."""

    spec_version: str
    hypothesis_id: str
    fixture_id: str
    subject_label: str                 # HOME_TEAM | AWAY_TEAM
    subject_team: str                  # resolved club
    target_metric: str
    side: str
    window: str
    period: str
    granularity: str
    venue_condition: Optional[str]
    competition_condition: Optional[str]
    own_formation_condition: Optional[str]
    opponent_formation_condition: Optional[str]
    opponent_profile_band: Optional[str]
    opponent_profile_axis: Optional[str]
    profile_band_semantics: Optional[str]
    comparison_cohort: str
    target_competition: str
    cutoff_unix: int
    provider: str
    required_fields: tuple[str, ...]
    plan_hash: str

    def to_dict(self) -> dict:
        return {
            "spec_version": self.spec_version,
            "hypothesis_id": self.hypothesis_id,
            "fixture_id": self.fixture_id,
            "subject_label": self.subject_label,
            "subject_team": self.subject_team,
            "target_metric": self.target_metric,
            "side": self.side,
            "window": self.window,
            "period": self.period,
            "granularity": self.granularity,
            "venue": self.venue_condition,
            "competition": self.competition_condition,
            "own_formation_family": self.own_formation_condition,
            "opponent_formation_family": self.opponent_formation_condition,
            "opponent_profile_band": self.opponent_profile_band,
            "opponent_profile_axis": self.opponent_profile_axis,
            "profile_band_semantics": self.profile_band_semantics,
            "comparison_cohort": self.comparison_cohort,
            "target_competition": self.target_competition,
            "cutoff_unix": self.cutoff_unix,
            "provider": self.provider,
            "required_fields": list(self.required_fields),
            "plan_hash": self.plan_hash,
        }


def build_spec(plan: QueryPlan, *, subject_team: str, target_competition: str,
               required_fields: Sequence[str]) -> MeasurementSpec:
    """Project a compiled plan onto an executable specification. Pure; reads no data."""
    by_dim = {c.dimension: c for c in plan.conditions}
    prof = by_dim.get("opponent_profile")
    return MeasurementSpec(
        spec_version=COHORT_MEASUREMENT_VERSION,
        hypothesis_id=plan.hypothesis_id,
        fixture_id=plan.fixture_id,
        subject_label=plan.subject,
        subject_team=subject_team,
        target_metric=plan.metric,
        side=plan.side,
        window=plan.window,
        period=plan.period,
        granularity=plan.required_granularity,
        venue_condition=by_dim["venue"].value if "venue" in by_dim else None,
        competition_condition=(by_dim["competition"].value
                               if "competition" in by_dim else None),
        own_formation_condition=(by_dim["own_formation_family"].value
                                 if "own_formation_family" in by_dim else None),
        opponent_formation_condition=(by_dim["opponent_formation_family"].value
                                      if "opponent_formation_family" in by_dim else None),
        opponent_profile_band=prof.value if prof else None,
        opponent_profile_axis=prof.axis if prof else None,
        profile_band_semantics=PROFILE_BAND_SEMANTICS if prof else None,
        comparison_cohort=plan.comparison,
        target_competition=target_competition,
        cutoff_unix=plan.cutoff_unix,
        provider=plan.provider,
        required_fields=tuple(required_fields),
        plan_hash=plan.plan_hash(),
    )


# --------------------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------------------
def _quantile(s: Sequence[float], q: float) -> float:
    if len(s) == 1:
        return s[0]
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] * (1 - (pos - lo)) + s[hi] * (pos - lo)


@dataclass
class CohortStats:
    n: int
    usable_n: int
    missing_n: int
    mean: Optional[float] = None
    median: Optional[float] = None
    sd: Optional[float] = None
    variance: Optional[float] = None
    p25: Optional[float] = None
    p75: Optional[float] = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None

    @property
    def coverage_rate(self) -> float:
        return (self.usable_n / self.n) if self.n else 0.0

    @property
    def missingness_rate(self) -> float:
        return (self.missing_n / self.n) if self.n else 0.0

    @property
    def reliability(self) -> str:
        # context_packet.reliability_for, reused rather than re-derived.
        return "HIGH" if self.usable_n >= 20 else ("MEDIUM" if self.usable_n >= 8 else "LOW")

    def to_dict(self) -> dict:
        return {
            "n": self.n, "usable_n": self.usable_n, "missing_n": self.missing_n,
            "coverage_rate": round(self.coverage_rate, 4),
            "missingness_rate": round(self.missingness_rate, 4),
            "reliability": self.reliability,
            "mean": self.mean, "median": self.median, "sd": self.sd,
            "variance": self.variance, "p25": self.p25, "p75": self.p75,
            "min": self.minimum, "max": self.maximum,
        }


def summarize(values: Sequence[Optional[float]]) -> CohortStats:
    n = len(values)
    usable = sorted(v for v in values if v is not None)
    k = len(usable)
    if k == 0:
        return CohortStats(n, 0, n)
    mean = sum(usable) / k
    mid = k // 2
    median = usable[mid] if k % 2 else (usable[mid - 1] + usable[mid]) / 2
    var = (sum((v - mean) ** 2 for v in usable) / (k - 1)) if k > 1 else 0.0
    return CohortStats(
        n, k, n - k,
        mean=round(mean, 6), median=round(median, 6),
        sd=round(math.sqrt(var), 6), variance=round(var, 6),
        p25=round(_quantile(usable, 0.25), 6), p75=round(_quantile(usable, 0.75), 6),
        minimum=usable[0], maximum=usable[-1])


# --------------------------------------------------------------------------------------
# Condition matching -- three-valued, carried over from measurement._matches_conditions
# --------------------------------------------------------------------------------------
def _matches(obs: Obs, spec: MeasurementSpec,
             profile_members: Optional[frozenset],
             profile_bandable: Optional[frozenset]) -> Optional[bool]:
    """True / False / None. None means a conditioned dimension is NOT RECORDED for this
    match; it is excluded from the conditional cohort WITHOUT being counted as a
    non-member, because missing data is not evidence of difference."""
    checks = (
        (spec.venue_condition, obs.dimensions.get("venue")),
        (spec.own_formation_condition, obs.dimensions.get("own_formation_family")),
        (spec.opponent_formation_condition,
         obs.dimensions.get("opponent_formation_family")),
    )
    for want, recorded in checks:
        if want is None or want == "ANY":
            continue
        if recorded is None:
            return None
        if recorded != want:
            return False

    if spec.competition_condition not in (None, "ANY"):
        # "SAME" == the target fixture's competition. Unlike venue and formation this
        # returns False rather than None for a mismatch: `competition` is populated on
        # every corpus record by construction, so a mismatch is genuinely a non-member
        # and never missing data.
        if obs.competition != spec.target_competition:
            return False

    if spec.opponent_profile_band not in (None, "ANY"):
        if profile_bandable is None or obs.opponent not in profile_bandable:
            return None                      # opponent could not be banded: missing data
        return obs.opponent in (profile_members or frozenset())

    return True


# --------------------------------------------------------------------------------------
# Result
# --------------------------------------------------------------------------------------
@dataclass
class CohortMeasurement:
    spec: MeasurementSpec
    outcome: str
    conditional: Optional[CohortStats] = None
    comparison: Optional[CohortStats] = None
    difference: Optional[float] = None
    shrunk_difference: Optional[float] = None
    shrinkage_weight: Optional[float] = None
    se: Optional[float] = None
    undetermined_n: int = 0
    distinct: Optional[bool] = None
    overlap_rate: Optional[float] = None
    profile_resolution: Optional[dict] = None
    dimension_coverage: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cohort_measurement_version": COHORT_MEASUREMENT_VERSION,
            "association_type": "DESCRIPTIVE_ASSOCIATION",
            "spec": self.spec.to_dict(),
            "outcome": self.outcome,
            "conditional": self.conditional.to_dict() if self.conditional else None,
            "comparison": self.comparison.to_dict() if self.comparison else None,
            "difference": self.difference,
            "shrunk_difference": self.shrunk_difference,
            "shrinkage_weight": self.shrinkage_weight,
            "se": self.se,
            "undetermined_n": self.undetermined_n,
            "distinct": self.distinct,
            "overlap_rate": self.overlap_rate,
            "profile_resolution": self.profile_resolution,
            "dimension_coverage": dict(self.dimension_coverage),
            "provenance": dict(self.provenance),
            "notes": list(self.notes),
        }


def _window_slice(obs: Sequence[Obs], window: str) -> list:
    ordered = sorted(obs, key=lambda o: o.kickoff_unix)
    if window == "W5":
        return ordered[-5:]
    if window == "W10":
        return ordered[-10:]
    return ordered


def execute(
    spec: MeasurementSpec,
    *,
    subject_history: Sequence[Obs],
    league_values: Optional[Sequence[Optional[float]]] = None,
    band_resolver: Optional[Callable[[str, str, int], similarity.CohortResolution]] = None,
) -> CohortMeasurement:
    """Measure one specification.

    `subject_history` must already be filtered to kickoff_unix < cutoff; this function
    re-checks independently, because a research record is not the place to trust a
    contract. `league_values` supplies the competition-wide team-match values used by
    LEAGUE_ENVIRONMENT_BASELINE. `band_resolver(axis, band, cutoff) -> CohortResolution`
    resolves opponent-profile bands through `similarity.resolve_band`.
    """
    prov = {
        "provider": spec.provider,
        "required_fields": list(spec.required_fields),
        "corpus": "src.research.matchup.corpus",
        "profile_band_semantics": spec.profile_band_semantics,
        "similarity_version": similarity.SIMILARITY_VERSION,
    }

    leaked = [o for o in subject_history if o.kickoff_unix >= spec.cutoff_unix]
    if leaked:
        return CohortMeasurement(
            spec, LEAKAGE_REJECTED, provenance=prov,
            notes=[f"history contained {len(leaked)} observation(s) at or after "
                   f"cutoff_unix={spec.cutoff_unix}; refusing to measure"])

    # ---- profile bands ----------------------------------------------------------------
    members = bandable = None
    if spec.opponent_profile_band not in (None, "ANY"):
        ms = axis_to_metric_side(spec.opponent_profile_axis or "")
        if ms is None:
            return CohortMeasurement(
                spec, UNSUPPORTED_PROFILE_AXIS, provenance=prov,
                notes=[f"profile axis {spec.opponent_profile_axis!r} does not resolve to "
                       f"a metric supported by the capability inventory"])
        if band_resolver is None:
            return CohortMeasurement(spec, UNSUPPORTED_PROFILE_AXIS, provenance=prov,
                                     notes=["no band resolver supplied"])
        res = band_resolver(spec.opponent_profile_axis, spec.opponent_profile_band,
                            spec.cutoff_unix)
        members = frozenset(res.members)
        bandable = frozenset(a.opponent for a in res.assignments)
        prof = res.to_dict()
        prof["resolved_metric"], prof["resolved_side"] = ms
    else:
        prof = None

    # ---- cohorts ----------------------------------------------------------------------
    windowed = _window_slice(subject_history, spec.window)

    conditional: list = []
    undetermined = 0
    for o in windowed:
        m = _matches(o, spec, members, bandable)
        if m is None:
            undetermined += 1
        elif m:
            conditional.append(o)

    comp_obs, comp_values, comp_note = _comparison_cohort(
        spec, subject_history, windowed, league_values,
        match_fn=lambda o: _matches(o, spec, members, bandable))
    if comp_obs is None and comp_values is None:
        return CohortMeasurement(spec, UNSUPPORTED_COMPARISON, provenance=prov,
                                 notes=[comp_note])

    cond_stats = summarize([o.value for o in conditional])
    comp_stats = (summarize(comp_values) if comp_values is not None
                  else summarize([o.value for o in comp_obs]))

    # ---- distinctness -----------------------------------------------------------------
    if comp_obs is not None:
        cond_ids = {o.fixture_id for o in conditional}
        comp_ids = {o.fixture_id for o in comp_obs}
        distinct = cond_ids != comp_ids
        overlap = (len(cond_ids & comp_ids) / len(cond_ids)) if cond_ids else 0.0
    else:
        distinct, overlap = True, None       # league environment is a different population

    # ---- per-dimension coverage -------------------------------------------------------
    dim_cov: dict = {}
    for dim, want in (("venue", spec.venue_condition),
                      ("own_formation_family", spec.own_formation_condition),
                      ("opponent_formation_family", spec.opponent_formation_condition)):
        if want in (None, "ANY"):
            continue
        rec = sum(1 for o in windowed if o.dimensions.get(dim) is not None)
        dim_cov[dim] = {"candidate_n": len(windowed), "usable_n": rec,
                        "missing_n": len(windowed) - rec,
                        "coverage_rate": round(rec / len(windowed), 4) if windowed else 0.0}
    if spec.opponent_profile_band not in (None, "ANY"):
        rec = sum(1 for o in windowed if bandable and o.opponent in bandable)
        dim_cov["opponent_profile"] = {
            "candidate_n": len(windowed), "usable_n": rec,
            "missing_n": len(windowed) - rec,
            "coverage_rate": round(rec / len(windowed), 4) if windowed else 0.0}

    notes: list = []
    if comp_note:
        notes.append(comp_note)
    if undetermined:
        notes.append(
            f"{undetermined} match(es) had no recorded value for a conditioned dimension "
            f"and were excluded from the conditional cohort WITHOUT being counted as "
            f"non-members (missing data is not evidence of difference)")

    out = CohortMeasurement(
        spec, MEASURED, conditional=cond_stats, comparison=comp_stats,
        undetermined_n=undetermined, distinct=distinct, overlap_rate=overlap,
        profile_resolution=prof, dimension_coverage=dim_cov, provenance=prov, notes=notes)

    if not distinct:
        out.outcome = NOT_DISTINCT
        out.notes.append(
            "the conditional cohort is the identical match set as the comparison cohort; "
            "the question compiles and is measurable but encodes no contrast")
        return out

    if (cond_stats.usable_n < MIN_CONDITIONAL_N
            or comp_stats.usable_n < MIN_COMPARISON_N):
        out.outcome = INSUFFICIENT_DATA
        out.notes.append(
            f"conditional usable_n={cond_stats.usable_n} (floor {MIN_CONDITIONAL_N}), "
            f"comparison usable_n={comp_stats.usable_n} (floor {MIN_COMPARISON_N}); "
            f"reported as INSUFFICIENT_DATA rather than as a null effect")
        return out

    out.difference = round(cond_stats.mean - comp_stats.mean, 6)
    w = cond_stats.usable_n / (cond_stats.usable_n + SHRINK_K)
    out.shrinkage_weight = round(w, 6)
    out.shrunk_difference = round(w * out.difference, 6)
    if cond_stats.sd is not None and comp_stats.sd is not None:
        out.se = round(math.sqrt(cond_stats.sd ** 2 / cond_stats.usable_n
                                 + comp_stats.sd ** 2 / comp_stats.usable_n), 6)
    return out


def _comparison_cohort(spec, full_history, windowed, league_values, *, match_fn):
    """Build the EXACT comparison the plan encodes. Returns (observations, values, note).

    Exactly one of observations / values is non-None: LEAGUE_ENVIRONMENT_BASELINE is a
    competition-wide population, not a slice of the subject's own matches.
    """
    c = spec.comparison_cohort
    if c == "SUBJECT_OVERALL_BASELINE":
        return windowed, None, ""
    if c == "SUBJECT_VENUE_BASELINE":
        # The venue of the UPCOMING fixture: HOME_TEAM plays home, AWAY_TEAM plays away.
        venue = "HOME" if spec.subject_label == "HOME_TEAM" else "AWAY"
        return ([o for o in windowed if o.dimensions.get("venue") == venue], None,
                f"comparison restricted to the subject's {venue} matches (the venue of the "
                f"upcoming fixture)")
    if c == "SUBJECT_COMPETITION_BASELINE":
        return ([o for o in windowed if o.competition == spec.target_competition], None,
                f"comparison restricted to competition {spec.target_competition!r}")
    if c == "LEAGUE_ENVIRONMENT_BASELINE":
        if league_values is None:
            return None, None, ("LEAGUE_ENVIRONMENT_BASELINE requires competition-wide "
                                "values, which were not supplied")
        return (None, list(league_values),
                f"comparison is the competition-wide team-match population for "
                f"{spec.target_competition!r} strictly before the cutoff")
    if c == "SUBJECT_RECENT_VS_LONG_BASELINE":
        # A window-vs-window contrast, not a condition contrast: the SAME conditions are
        # applied to ALL_PRIOR so that only the window differs between the two cohorts.
        return ([o for o in full_history if match_fn(o) is True], None,
                "comparison is the subject's ALL_PRIOR history under the same conditions; "
                "the contrast is the window, not the condition set")
    return None, None, f"comparison {c!r} is not a known comparison cohort"
