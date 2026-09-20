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
from src.research.hypothesis_bridge.versions import MEASUREMENT_VERSION

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
    """Identity of the exact historical rows measured, so a record is reproducible."""
    payload = {
        "measurement_version": MEASUREMENT_VERSION,
        "hypothesis": ir.to_dict(),
        "target_fixture": target.fixture_id,
        "target_kickoff": target.kickoff_unix,
        "season": CH.HistoryIndex.target_season(target),
        "fixtures": sorted(r.fixture_id for r in cohort.records),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def measure(idx: CH.HistoryIndex, target: MatchRecord, ir: CanonicalHypothesis) -> dict[str, Any]:
    """Descriptive measurement payload. No probability, no edge, no EV, no stake."""
    cohort = cohort_sample(idx, target, ir)
    baseline = baseline_sample(idx, target, ir)
    if cohort.mean is None:
        raise MeasurementFailed("cohort has no non-null values")

    contrast = None
    if baseline.mean is not None:
        contrast = cohort.mean - baseline.mean

    return {
        "measurement_version": MEASUREMENT_VERSION,
        "cohort": {"raw_n": cohort.raw_n, "effective_n": cohort.effective_n,
                   "coverage": cohort.coverage, "mean": cohort.mean},
        "baseline": {"comparator": ir.comparator, "raw_n": baseline.raw_n,
                     "effective_n": baseline.effective_n, "coverage": baseline.coverage,
                     "mean": baseline.mean},
        "deterministic_contrast": {"kind": "cohort_mean_minus_baseline_mean",
                                   "value": contrast},
        "cohort_identity_hash": cohort_identity(target, ir, cohort),
    }
