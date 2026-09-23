"""Point-in-time team-match history for the direct-hypothesis measurements.

Every accessor takes `before` and returns only matches with kickoff STRICTLY before it. The
history itself only admits matches strictly before the global cutoff (the target fixture's
kickoff), so the target match and anything later can never be read.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from src.research.dual_provider_llm import packet as P
from src.research.dual_provider_llm.measurement import support as S

#: Concepts the measurement layer may read (the packet's concepts). Anything else fails closed.
SUPPORTED_METRICS = frozenset(c for c, _, _, _ in P.CONCEPTS)
#: Metrics whose semantics are unresolved for a defensive interpretation.
FORBIDDEN_METRICS = frozenset({"blocked_shots"})


class PITViolation(RuntimeError):
    pass


class UnsupportedMetric(ValueError):
    pass


@dataclass(frozen=True)
class TeamMatch:
    match_id: str
    kickoff_unix: int
    competition_id: str
    season_id: str
    team_id: str
    opponent_id: str
    venue: str                      # HOME | AWAY | NEUTRAL
    own: Tuple[Tuple[str, Optional[float]], ...]       # FOR values
    opp: Tuple[Tuple[str, Optional[float]], ...]       # AGAINST values

    def get(self, metric: str, perspective: str) -> Optional[float]:
        check_metric(metric)
        src = self.own if perspective == "FOR" else self.opp
        for k, v in src:
            if k == metric:
                return None if v is None else float(v)
        return None


def check_metric(metric: str) -> None:
    if metric in FORBIDDEN_METRICS:
        raise UnsupportedMetric(f"{metric} is excluded (unresolved provider semantics)")
    if metric not in SUPPORTED_METRICS:
        raise UnsupportedMetric(f"{metric} is not a supported TheStatsAPI concept")


def team_matches_from_history(history: Dict[str, "P.HistoryMatch"]) -> List[TeamMatch]:
    rows = []
    for h in history.values():
        home, away = h.fixture.get("home_team") or {}, h.fixture.get("away_team") or {}
        for team, opp, fs, ag, venue in ((home, away, "home", "away", "HOME"),
                                         (away, home, "away", "home", "AWAY")):
            if h.fixture.get("is_neutral"):
                venue = "NEUTRAL"
            rows.append(TeamMatch(
                h.match_id, h.kickoff_unix, str(h.fixture.get("competition_id")),
                str(h.fixture.get("season_id")), str(team.get("id")), str(opp.get("id")), venue,
                tuple((c, h.values[c][fs]) for c in sorted(h.values)),
                tuple((c, h.values[c][ag]) for c in sorted(h.values))))
    return sorted(rows, key=lambda r: (r.kickoff_unix, r.match_id, r.team_id))


class PITHistory:
    def __init__(self, rows: Sequence[TeamMatch], global_cutoff_unix: int,
                 excluded_match_ids: Sequence[str] = ()):
        self.cutoff = int(global_cutoff_unix)
        ex = set(excluded_match_ids)
        self.rows = [r for r in rows if r.kickoff_unix < self.cutoff and r.match_id not in ex]
        self.n_dropped_at_or_after_cutoff = sum(1 for r in rows if r.kickoff_unix >= self.cutoff)
        self._by_team: Dict[str, List[TeamMatch]] = {}
        self._by_comp: Dict[Tuple[str, Optional[str]], List[TeamMatch]] = {}
        for r in self.rows:
            self._by_team.setdefault(r.team_id, []).append(r)
            self._by_comp.setdefault((r.competition_id, None), []).append(r)
            self._by_comp.setdefault((r.competition_id, r.venue), []).append(r)
        self._ref_cache: Dict[tuple, Optional[Tuple[float, float, int]]] = {}

    def _guard(self, before: int) -> None:
        if before > self.cutoff:
            raise PITViolation(f"query time {before} is after the global cutoff {self.cutoff}")

    def team_rows(self, team_id: str, before: int, venue: Optional[str] = None,
                  competition_id: Optional[str] = None, n: Optional[int] = None
                  ) -> List[TeamMatch]:
        """Team's matches strictly before `before`, oldest first; last n if given."""
        self._guard(before)
        out = [r for r in self._by_team.get(team_id, []) if r.kickoff_unix < before
               and (venue is None or r.venue == venue)
               and (competition_id is None or r.competition_id == competition_id)]
        return out[-n:] if n else out

    def reference(self, metric: str, competition_id: str, before: int,
                  venue: Optional[str] = None) -> Optional[Tuple[float, float, int]]:
        """Robust (median, scale, n) of the metric's team-match values in the competition
        (optionally a venue) over matches strictly before `before`; None if unsupported."""
        self._guard(before)
        check_metric(metric)
        key = (metric, competition_id, before, venue)
        if key in self._ref_cache:
            return self._ref_cache[key]
        vals = np.array([v for r in self._by_comp.get((competition_id, venue), [])
                         if r.kickoff_unix < before
                         for v in [r.get(metric, "FOR")] if v is not None], float)
        res = None
        if len(vals) >= S.value("MIN_REFERENCE_OBS"):
            med = float(np.median(vals))
            scale = float(np.median(np.abs(vals - med))) * S.value("MAD_TO_SD")
            if scale <= 0:
                q1, q3 = np.percentile(vals, [25, 75])
                scale = float(q3 - q1) / S.value("IQR_TO_SD")
            if scale > 0:
                res = (med, scale, int(len(vals)))
        self._ref_cache[key] = res
        return res

    def z(self, row: TeamMatch, metric: str, perspective: str, before: int,
          by_venue: bool = False) -> Optional[float]:
        """Competition-relative robust z of one observation, scaled with the reference as of
        `before`. A conceded (AGAINST) value is scaled against the metric's distribution for
        the side that produced it (the opponent's venue when by_venue)."""
        v = row.get(metric, perspective)
        if v is None:
            return None
        venue = None
        if by_venue:
            venue = row.venue if perspective == "FOR" else {"HOME": "AWAY", "AWAY": "HOME"}.get(
                row.venue, row.venue)
        ref = self.reference(metric, row.competition_id, before, venue)
        if ref is None:
            return None
        return (v - ref[0]) / ref[1]

    def strength(self, team_id: str, competition_id: str, before: int) -> Optional[float]:
        """Mean goal difference over the last STRENGTH_WINDOW same-competition matches; None if
        fewer than MIN_STRENGTH_MATCHES (never used to gate eligibility)."""
        rows = self.team_rows(team_id, before, competition_id=competition_id,
                              n=int(S.value("STRENGTH_WINDOW_MATCHES")))
        gd = [r.get("goals", "FOR") - r.get("goals", "AGAINST") for r in rows
              if r.get("goals", "FOR") is not None and r.get("goals", "AGAINST") is not None]
        if len(gd) < S.value("MIN_STRENGTH_MATCHES"):
            return None
        return float(np.mean(gd))
