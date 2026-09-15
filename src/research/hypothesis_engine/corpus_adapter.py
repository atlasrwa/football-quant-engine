"""Bridge from the real dual-provider corpus to the hypothesis layer
(`corpus_adapter_v1`).

Supplies two things and nothing else:

  * `build_packet()`  -- a real `FixtureContextPacket` for an upcoming fixture, built from
    PIT-safe history and carrying a real capability manifest and real formation coverage;
  * `CorpusHistoryProvider` -- the `measurement.HistoryProvider` implementation.

ISOLATION
---------
This module deliberately imports only `src.research.matchup.corpus`, which is a
DETERMINISTIC corpus loader on the quant side of the house. It imports nothing from
`llm_matchup` (the legacy latent-state experiment) and nothing from the prediction,
prospective, forward or broadcast layers. The import-graph test enforces this.

LEAKAGE
-------
Every read is filtered on `kickoff_unix < cutoff_unix` in ONE place (`_prior`). The
measurement layer re-checks independently, so a mistake here is caught rather than
silently producing a leaked research result.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional, Sequence

sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import capability, context_packet as CP, measurement as M
from src.research.matchup import corpus as MC

CORPUS_ADAPTER_VERSION = "corpus_adapter_v1"

LINEUP_DIR = "/home/ubuntu/data/thestatsapi/championship"

#: Canonical metric -> how to read it from a MatchRecord.
#: ("rich"|"extra", key) reads the (home, away) pair; ("base", home_field, away_field).
_METRIC_SOURCE: dict[str, tuple] = {
    "corners": ("rich", "corner_kicks"),
    "accurate_crosses": ("rich", "accurate_crosses"),
    "shots_on_target": ("rich", "shots_on_target"),
    "shots_inside_box": ("rich", "shots_inside_box"),
    "shots_outside_box": ("rich", "shots_outside_box"),
    "blocked_shots": ("rich", "blocked_shots"),
    "touches_in_box": ("rich", "touches_in_penalty_area"),
    "final_third_entries": ("rich", "final_third_entries"),
    "tackles": ("rich", "tackles"),
    "interceptions": ("rich", "interceptions"),
    "clearances": ("rich", "clearances"),
    "big_chances": ("rich", "big_chances"),
    "npxg": ("rich", "np_expected_goals"),
    "saves": ("rich", "saves"),
    "fouls": ("rich", "fouls"),
    "total_shots": ("extra", "total_shots"),
    "shots_off_target": ("extra", "shots_off_target"),
    "possession": ("extra", "possession"),
    "throw_ins": ("extra", "throw_ins"),
    "offsides": ("extra", "offsides"),
    "goals": ("base", "homeGoalCount", "awayGoalCount"),
    "yellow_cards": ("base", "team_a_yellow_cards", "team_b_yellow_cards"),
}


def _pair(rec: MC.MatchRecord, metric: str) -> Optional[tuple]:
    src = _METRIC_SOURCE.get(metric)
    if not src:
        return None
    if src[0] == "base":
        h, a = rec.base.get(src[1]), rec.base.get(src[2])
        return (h, a) if (h is not None and a is not None) else None
    block = rec.rich if src[0] == "rich" else rec.extra
    return block.get(src[1])


def team_value(rec: MC.MatchRecord, team: str, metric: str, side: str) -> Optional[float]:
    """The team's own value (FOR) or its opponent's (AGAINST) for this match."""
    pair = _pair(rec, metric)
    if not pair:
        return None
    is_home = rec.home == team
    own, opp = (pair[0], pair[1]) if is_home else (pair[1], pair[0])
    v = own if side == "FOR" else opp
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------------------
# Formation (recorded, historical -- no announcement timestamp needed)
# --------------------------------------------------------------------------------------
_formation_cache: dict[str, Optional[tuple]] = {}


def recorded_formations(fixture_id: str) -> Optional[tuple[str, str]]:
    """(home_formation, away_formation) for a COMPLETED fixture, or None."""
    if fixture_id in _formation_cache:
        return _formation_cache[fixture_id]
    path = os.path.join(LINEUP_DIR, f"lineups_{fixture_id}.json")
    out = None
    if os.path.exists(path):
        try:
            d = (json.load(open(path)) or {}).get("data", {}) or {}
            h = (d.get("home") or {}).get("formation")
            a = (d.get("away") or {}).get("formation")
            if h and a:
                out = (h, a)
        except (ValueError, OSError):
            out = None
    _formation_cache[fixture_id] = out
    return out


def team_formation_family(rec: MC.MatchRecord, team: str, *, opponent: bool = False) -> Optional[str]:
    f = recorded_formations(rec.fixture_id)
    if not f:
        return None
    is_home = rec.home == team
    own, opp = (f[0], f[1]) if is_home else (f[1], f[0])
    return CP.formation_family(opp if opponent else own)


def half_score_state(rec: MC.MatchRecord, team: str) -> Optional[str]:
    """LEADING/LEVEL/TRAILING at half time, from half-time goals. No event feed needed."""
    ha, hb = rec.base.get("ht_goals_team_a"), rec.base.get("ht_goals_team_b")
    if ha is None or hb is None:
        return None
    try:
        ha, hb = int(ha), int(hb)
    except (TypeError, ValueError):
        return None
    own, opp = (ha, hb) if rec.home == team else (hb, ha)
    if own > opp:
        return "LEADING_AT_HT"
    if own < opp:
        return "TRAILING_AT_HT"
    return "LEVEL_AT_HT"


# --------------------------------------------------------------------------------------
# History index
# --------------------------------------------------------------------------------------
class HistoryIndex:
    """Per-team chronological match index over the loaded corpus."""

    def __init__(self, records: Sequence[MC.MatchRecord]):
        self.records = list(records)
        self.by_team: dict[str, list[MC.MatchRecord]] = defaultdict(list)
        for r in self.records:
            self.by_team[r.home].append(r)
            self.by_team[r.away].append(r)
        for team in self.by_team:
            self.by_team[team].sort(key=lambda r: r.kickoff_unix)

    def prior(self, team: str, cutoff_unix: int) -> list[MC.MatchRecord]:
        """THE leakage boundary: strictly before the cutoff, one place only."""
        return [r for r in self.by_team.get(team, []) if r.kickoff_unix < cutoff_unix]

    def teams(self) -> list[str]:
        return sorted(self.by_team)


@dataclass
class CorpusHistoryProvider:
    """`measurement.HistoryProvider` over the real corpus."""

    index: HistoryIndex

    def observations(self, *, subject_team, metric, side, period, provider, cutoff_unix):
        out: list[M.Observation] = []
        for r in self.index.prior(subject_team, cutoff_unix):
            out.append(M.Observation(
                fixture_id=r.fixture_id,
                kickoff_unix=r.kickoff_unix,
                value=team_value(r, subject_team, metric, side),
                dimensions={
                    "venue": "HOME" if r.home == subject_team else "AWAY",
                    "competition": r.competition,
                    "own_formation_family": team_formation_family(r, subject_team),
                    "opponent_formation_family": team_formation_family(
                        r, subject_team, opponent=True),
                    "half_score_state": half_score_state(r, subject_team),
                },
            ))
        return out


# --------------------------------------------------------------------------------------
# Packet construction
# --------------------------------------------------------------------------------------
SHRINK_K = 6.0


def _shrunk_mean(values: Sequence[Optional[float]], parent: Optional[float]
                 ) -> tuple[Optional[float], int]:
    usable = [v for v in values if v is not None]
    n = len(usable)
    if n == 0:
        return None, 0
    m = sum(usable) / n
    if parent is None:
        return m, n
    w = n / (n + SHRINK_K)
    return w * m + (1 - w) * parent, n


_PACKET_METRICS = (
    "corners", "accurate_crosses", "total_shots", "shots_on_target", "shots_off_target",
    "blocked_shots", "shots_inside_box", "touches_in_box", "final_third_entries",
    "possession", "tackles", "fouls", "yellow_cards", "clearances", "interceptions",
    "goals", "throw_ins", "big_chances", "saves",
)


def _league_mean(index: HistoryIndex, competition: str, metric: str,
                 cutoff_unix: int) -> Optional[float]:
    vals: list[float] = []
    for r in index.records:
        if r.competition != competition or r.kickoff_unix >= cutoff_unix:
            continue
        pair = _pair(r, metric)
        if not pair:
            continue
        for v in pair:
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                pass
    return sum(vals) / len(vals) if vals else None


def build_packet(
    target: MC.MatchRecord,
    index: HistoryIndex,
    *,
    min_history: int = 6,
) -> Optional[CP.FixtureContextPacket]:
    """Build a real, PIT-safe fixture context packet for `target`.

    Returns None when either side has too little prior history for the packet to be worth
    sending -- fail closed rather than ship a packet of nulls.
    """
    cutoff = int(target.kickoff_unix)
    home_hist = index.prior(target.home, cutoff)
    away_hist = index.prior(target.away, cutoff)
    if len(home_hist) < min_history or len(away_hist) < min_history:
        return None

    evidence: list[CP.EvidenceItem] = []
    available: set[str] = set()

    for subj_label, team, hist in (("HOME", target.home, home_hist),
                                   ("AWAY", target.away, away_hist)):
        for metric in _PACKET_METRICS:
            if not capability.is_supported_metric(metric):
                continue
            parent = _league_mean(index, target.competition, metric, cutoff)
            for side, family in (("FOR", "ATK"), ("AGAINST", "DEF")):
                vals = [team_value(r, team, metric, side) for r in hist]
                value, n = _shrunk_mean(vals, parent)
                if value is None:
                    continue
                available.add(metric)
                scope = {"subject": subj_label, "side": side, "venue": "ALL",
                         "window": "ALL_PRIOR", "metric": metric}
                evidence.append(CP.EvidenceItem(
                    id=CP.evidence_id(subj_label, family, metric, scope),
                    metric=f"{metric}_{side.lower()}",
                    value=round(value, 4),
                    sample_n=n,
                    scope=scope,
                    reliability=CP.reliability_for(n),
                    shrinkage_level="SHRUNK" if parent is not None else "DIRECT",
                    source_provider=capability.THESTATSAPI,
                    source_field=str(_METRIC_SOURCE.get(metric)),
                    cutoff_unix=cutoff,
                    temporal_status="PIT_SAFE",
                    max_source_time_unix=max(r.kickoff_unix for r in hist),
                ))

    # --- formation coverage, reported not assumed ------------------------------------
    recorded = [recorded_formations(r.fixture_id) for r in (home_hist + away_hist)]
    cov = CP.formation_coverage([f[0] if f else None for f in recorded])

    # --- observed recent formation distribution (the UPCOMING one is unknown) ---------
    dist: dict[str, dict] = {}
    for subj_label, team, hist in (("HOME_TEAM", target.home, home_hist),
                                   ("AWAY_TEAM", target.away, away_hist)):
        counts: dict[str, int] = defaultdict(int)
        for r in hist[-15:]:
            fam = team_formation_family(r, team)
            if fam:
                counts[fam] += 1
        dist[subj_label] = dict(sorted(counts.items()))

    # --- half-level availability ------------------------------------------------------
    half_ok = sum(1 for r in home_hist[-20:] if half_score_state(r, target.home)) >= 8

    manifest = CP.build_capability_manifest(
        fixture_id=target.fixture_id,
        available_metrics=sorted(available),
        formation_coverage_report=cov,
        half_level_available=half_ok,
        referee_available=False,          # FootyStats-only; this corpus is TheStatsAPI
    )

    return CP.FixtureContextPacket(
        fixture_id=target.fixture_id,
        information_cutoff_unix=cutoff,
        home_label="HOME_TEAM",           # identity-neutral by default
        away_label="AWAY_TEAM",
        competition_label="COMPETITION",
        evidence=evidence,
        manifest=manifest,
        formation_distribution=dist,
        notes=[f"corpus_adapter={CORPUS_ADAPTER_VERSION}",
               f"home_prior_n={len(home_hist)}", f"away_prior_n={len(away_hist)}"],
    )


def load_index(leagues: Optional[list[str]] = None) -> HistoryIndex:
    return HistoryIndex(MC.load_corpus(leagues))
