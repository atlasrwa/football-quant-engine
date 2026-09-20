"""Deterministic historical measurement — descriptive only, computed by code.

Runs ONLY after validation succeeds. Produces cohort and baseline descriptives and a
deterministic contrast. It never converts them into a match probability, an edge, an EV or a
stake: those are not this layer's output and `firewall.assert_outbound_clean` enforces it on
the record that carries these numbers.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from src.research.matchup.corpus import MatchRecord, season_of
from src.research.llm_matchup import cohorts as CH
from src.research.hypothesis_bridge.canonical import CanonicalHypothesis
from src.research.hypothesis_bridge.versions import (MEASUREMENT_VERSION,
                                                     CAPABILITY_REGISTRY_VERSION)

#: The support floor. Deliberately the SAME constant the evidence layer already enforces --
#: this bridge must not create a second, weaker threshold so that more hypotheses pass.
MIN_SUPPORT = CH.MIN_HISTORY


class MeasurementFailed(RuntimeError):
    pass


@dataclass
class Sample:
    records: list[MatchRecord] = field(default_factory=list)
    values: list[float] = field(default_factory=list)

    @property
    def raw_n(self) -> int:
        return len(self.records)

    @property
    def effective_n(self) -> int:
        return len(self.values)

    @property
    def coverage(self) -> Optional[float]:
        return (self.effective_n / self.raw_n) if self.raw_n else None

    @property
    def mean(self) -> Optional[float]:
        return (sum(self.values) / len(self.values)) if self.values else None


def team_id_for(target: MatchRecord, subject: str) -> str:
    return target.home_id if subject == "home_team" else target.away_id


def _collect(records, team, metric, side, period) -> Sample:
    """Values for `team` over `records`. NULL means NOT RECORDED and is dropped, never 0."""
    s = Sample(records=list(records))
    for r in s.records:
        v = CH.team_metric(r, team, metric, side, period)
        if v is not None:
            s.values.append(float(v))
    return s


def cohort_sample(idx: CH.HistoryIndex, target: MatchRecord, ir: CanonicalHypothesis) -> Sample:
    team = team_id_for(target, ir.subject)
    season = CH.HistoryIndex.target_season(target)
    venue = None if ir.venue == "any" else ir.venue
    recs = idx.prior_records(team, target.kickoff_unix, season, venue)
    if ir.window_mode == "last_n":
        recs = sorted(recs, key=lambda r: r.kickoff_unix)[-ir.window_n:]
    return _collect(recs, team, ir.metric, ir.perspective, ir.period)


def baseline_sample(idx: CH.HistoryIndex, target: MatchRecord, ir: CanonicalHypothesis) -> Sample:
    """`team_season_baseline` drops the venue condition; `league_season_baseline` is the
    competition-season's prior matches, both sides pooled."""
    season = CH.HistoryIndex.target_season(target)
    if ir.comparator == "team_season_baseline":
        team = team_id_for(target, ir.subject)
        recs = idx.prior_records(team, target.kickoff_unix, season, None)
        return _collect(recs, team, ir.metric, ir.perspective, ir.period)

    sample = Sample()
    for r in idx.recs:
        if r.kickoff_unix >= target.kickoff_unix:          # STRICT: never <=
            continue
        if season_of(r) != season or r.competition != target.competition:
            continue
        sample.records.append(r)
        for side_team in (r.home_id, r.away_id):
            v = CH.team_metric(r, side_team, ir.metric, ir.perspective, ir.period)
            if v is not None:
                sample.values.append(float(v))
    return sample


def cohort_identity(target: MatchRecord, ir: CanonicalHypothesis, cohort: Sample) -> str:
    """MEMBERSHIP/STRUCTURE identity: which rows, in which order, for which hypothesis.

    This deliberately does NOT bind the measured VALUES -- `source_hash` does that. Keeping
    them separate lets a reader tell "a different set of matches was selected" from "the same
    matches, with a stat that has since changed".

    Order is bound, not sorted away: a `last_n` window selects by chronological position, so
    two identical id sets in different orders are not the same cohort.
    """
    payload = {
        "measurement_version": MEASUREMENT_VERSION,
        "hypothesis": ir.to_dict(),
        "target_fixture": target.fixture_id,
        "target_kickoff": target.kickoff_unix,
        "season": CH.HistoryIndex.target_season(target),
        "fixtures_ordered": [r.fixture_id for r in
                             sorted(cohort.records, key=lambda r: (r.kickoff_unix, r.fixture_id))],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def capability_identity(capability) -> dict[str, Any]:
    """The provider-identity block bound into every measurement hash.

    A capability is REQUIRED. There is no "unknown provider" default: a measurement whose
    provenance cannot be named must not produce a provenance hash at all, because a
    placeholder would collide across providers -- the exact failure this binding exists to
    prevent.
    """
    if capability is None:
        raise MeasurementFailed("no_resolved_provider_capability")
    return {
        "provider": capability.provider,
        "provider_capability_id": capability.capability_id,
        "provider_source_field": capability.provider_source_field,
        "capability_registry_version": CAPABILITY_REGISTRY_VERSION,
    }


def source_hash(target: MatchRecord, ir: CanonicalHypothesis, sample: Sample,
                team: Optional[str], role: str, capability) -> str:
    """VALUE identity: the exact deterministic inputs the measurement consumed.

    PROVIDER-BOUND. The same numeric value read from a different provider is a different
    observation, so `capability` -- provider, capability id and the provider's own source
    field -- is bound into every row AND into the payload header. Without it, FootyStats
    `team_a_corners` = 5 and TheStatsAPI `overview.corner_kicks` = 5 would be indistinguishable
    in provenance, and a provider substitution would leave no trace.

    Binding fixture ids, timestamps and membership is not enough for reproducibility: a
    historical stat can be corrected while ids, kickoffs, season and cohort membership all
    stay identical, and the measurement would then change with no provenance identity
    changing. This binds the measured value itself, per row.

    A NULL is bound as an explicit marker rather than skipped, so "not recorded" and "absent
    from the cohort" are distinguishable. Rows are canonically ordered by (kickoff, fixture
    id) so an input list in a different order yields the same hash where order is not
    semantically meaningful.
    """
    cap = capability_identity(capability)
    rows = []
    for r in sorted(sample.records, key=lambda r: (r.kickoff_unix, r.fixture_id)):
        subjects = [team] if team is not None else [r.home_id, r.away_id]
        for t in subjects:
            v = CH.team_metric(r, t, ir.metric, ir.perspective, ir.period)
            rows.append({
                "fixture_id": r.fixture_id,
                "kickoff_unix": r.kickoff_unix,
                "competition": r.competition,
                "season_id": r.season_id,
                "team": t,
                "metric": ir.metric,
                "perspective": ir.perspective,
                "period": ir.period,
                "venue": ir.venue,
                "provider": cap["provider"],
                "provider_source_field": cap["provider_source_field"],
                "value": ("__NULL__" if v is None else float(v)),
            })
    payload = {"measurement_version": MEASUREMENT_VERSION, "role": role,
               "target_fixture": target.fixture_id, "target_kickoff": target.kickoff_unix,
               "provider_identity": cap, "rows": rows}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def target_bounded_vintage(idx: CH.HistoryIndex, target: MatchRecord,
                           ir: CanonicalHypothesis) -> str:
    """Data-vintage identity bounded by the TARGET.

    Covers the historical surface available to this measurement at T -- the target's own
    competition-season, strictly before T -- rather than the whole corpus. A row appended
    after T cannot change it, which is the property that makes a shadow record for T stable
    as the corpus grows forward.
    """
    season = CH.HistoryIndex.target_season(target)
    rows = []
    for r in sorted(idx.recs, key=lambda r: (r.kickoff_unix, r.fixture_id)):
        if r.kickoff_unix >= target.kickoff_unix:            # STRICT
            continue
        if season_of(r) != season or r.competition != target.competition:
            continue
        for t in (r.home_id, r.away_id):
            v = CH.team_metric(r, t, ir.metric, ir.perspective, ir.period)
            rows.append([r.fixture_id, r.kickoff_unix, t,
                         "__NULL__" if v is None else float(v)])
    payload = {"measurement_version": MEASUREMENT_VERSION, "scope": "target_bounded",
               "target_fixture": target.fixture_id, "target_kickoff": target.kickoff_unix,
               "season": season, "metric": ir.metric, "perspective": ir.perspective,
               "period": ir.period, "rows": rows}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def measure(idx: CH.HistoryIndex, target: MatchRecord, ir: CanonicalHypothesis,
            *, capability) -> dict[str, Any]:
    """Descriptive measurement payload. No probability, no edge, no EV, no stake.

    `capability` is the ALREADY-RESOLVED `(provider, metric)` capability. It is keyword-only
    and mandatory so no caller can measure without naming the provider it measured.
    """
    cohort = cohort_sample(idx, target, ir)
    baseline = baseline_sample(idx, target, ir)
    if cohort.mean is None:
        raise MeasurementFailed("cohort has no non-null values")

    contrast = None
    if baseline.mean is not None:
        contrast = cohort.mean - baseline.mean

    team = team_id_for(target, ir.subject)
    baseline_team = team if ir.comparator == "team_season_baseline" else None
    cohort_sh = source_hash(target, ir, cohort, team, "cohort", capability)
    baseline_sh = source_hash(target, ir, baseline, baseline_team, "baseline", capability)
    cap = capability_identity(capability)

    return {
        "measurement_version": MEASUREMENT_VERSION,
        # The provider ACTUALLY used, resolved from the context's frozen policy -- never
        # inferred from a field name and never a default.
        "measurement_provider": cap["provider"],
        "provider_capability_id": cap["provider_capability_id"],
        "provider_source_field": cap["provider_source_field"],
        "cohort": {"raw_n": cohort.raw_n, "effective_n": cohort.effective_n,
                   "coverage": cohort.coverage, "mean": cohort.mean},
        "baseline": {"comparator": ir.comparator, "raw_n": baseline.raw_n,
                     "effective_n": baseline.effective_n, "coverage": baseline.coverage,
                     "mean": baseline.mean},
        "deterministic_contrast": {"kind": "cohort_mean_minus_baseline_mean",
                                   "value": contrast},
        # Membership/structure identity (which rows), kept distinct from value identity.
        "cohort_identity_hash": cohort_identity(target, ir, cohort),
        # Value identities: these change when a measured historical value changes, even
        # though ids, kickoffs, season and membership are all unchanged.
        "cohort_source_hash": cohort_sh,
        "baseline_source_hash": baseline_sh,
        "measurement_input_hash": hashlib.sha256(
            json.dumps({"cohort": cohort_sh, "baseline": baseline_sh,
                        "hypothesis": ir.to_dict(), "provider_identity": cap},
                       sort_keys=True).encode()).hexdigest(),
    }
