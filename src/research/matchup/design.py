"""Assemble named feature FAMILIES per fixture for chronological OOS experiments.

Each family is a dict {feature_name: value|None}. Families are combined additively by
the experiment harness. All values are PIT-safe (see features.py). Provenance for each
feature is recorded in feature_provenance().

Outcome labels mirror the champion exactly (goals/corners/cards/btts over lines).
Corners outcome uses TheStatsAPI corner_kicks (the only corner source in this corpus).
"""
from __future__ import annotations
import math
from typing import Any, Optional
import numpy as np

from src.research.matchup.corpus import MatchRecord, season_of
from src.research.matchup import features as F

WINDOWS = [5, 10, None]  # w5, w10, std  (mirror champion)
WLBL = {5: "w5", 10: "w10", None: "std"}

# Stat pools per market family (mechanism-valid, mirrors champion + rich extensions)
POOLS = {
    "goals":   ["sot", "xg", "np_expected_goals", "total_shots", "shots_inside_box",
                "big_chances", "touches_in_penalty_area", "possession"],
    "corners": ["corner_kicks", "total_shots", "shots_off_target", "blocked_shots",
                "accurate_crosses", "touches_in_penalty_area", "final_third_entries",
                "throw_ins", "possession"],
    "cards":   ["cards", "yellow_cards", "fouls", "tackles"],
    "btts":    ["sot", "xg", "np_expected_goals", "big_chances"],
}
# champion-parity minimal pool (what the champion actually uses, TSA-available subset)
CHAMP_POOL = {
    "goals":   ["total_shots", "sot", "xg", "possession"],
    "corners": ["corner_kicks", "total_shots", "shots_off_target", "possession"],
    "cards":   ["yellow_cards", "fouls", "possession"],
    "btts":    ["sot", "xg"],
}


def outcome(rec: MatchRecord, market: str, line: Optional[float]) -> Optional[float]:
    if market == "goals":
        t = rec.base.get("overallGoalCount")
        return 1.0 if (t is not None and t > line) else (0.0 if t is not None else None)
    if market == "corners":
        pair = rec.rich.get("corner_kicks")
        if not pair or pair[0] is None or pair[1] is None:
            return None
        return 1.0 if (pair[0] + pair[1]) > line else 0.0
    if market == "cards":
        yh, ya = rec.base.get("team_a_yellow_cards"), rec.base.get("team_b_yellow_cards")
        if yh is None or ya is None:
            return None
        tot = yh + ya + (rec.base.get("team_a_red_cards") or 0) + (rec.base.get("team_b_red_cards") or 0)
        return 1.0 if tot > line else 0.0
    if market == "btts":
        hg, ag = rec.base.get("homeGoalCount"), rec.base.get("awayGoalCount")
        if hg is None or ag is None:
            return None
        return 1.0 if (hg >= 1 and ag >= 1) else 0.0
    return None


class DesignBuilder:
    def __init__(self, recs: list[MatchRecord]):
        self.recs = recs
        self.idx = F.HistoryIndex(recs)
        self.env = F.LeagueEnvironment(recs)
        self._ratings: dict[str, F.StrengthRatings] = {}

    def ratings(self, stat: str) -> F.StrengthRatings:
        if stat not in self._ratings:
            self._ratings[stat] = F.StrengthRatings(self.recs, stat)
        return self._ratings[stat]

    # ---- family: champion-parity team state (F0 baseline) ----
    def f_champ(self, rec: MatchRecord, market: str) -> dict:
        return self._team_state(rec, CHAMP_POOL[market], prefix="champ")

    # ---- family F1: direct outcome state (goals for/against etc.) ----
    def f_direct(self, rec: MatchRecord, market: str) -> dict:
        stats = {"goals": ["goals"], "corners": ["corner_kicks"],
                 "cards": ["cards"], "btts": ["goals"]}[market]
        return self._team_state(rec, stats, prefix="direct")

    # ---- family F2: league environment ----
    def f_league_env(self, rec: MatchRecord, market: str) -> dict:
        stat = {"goals": "goals", "corners": "corner_kicks", "cards": "cards", "btts": "goals"}[market]
        e = self.env.env(rec, stat)
        return {f"leagueenv_{stat}": e}

    # ---- family F3: home/away venue-conditioned state ----
    def f_home_away(self, rec: MatchRecord, market: str) -> dict:
        stats = {"goals": ["sot", "xg"], "corners": ["corner_kicks"],
                 "cards": ["cards"], "btts": ["sot"]}[market]
        # The TARGET fixture's own season-instance, not the season each team last played
        # in. `current_season()` returns the latter, which for a fixture early in a new
        # season silently yields PRIOR-season form labelled as current-season and lets the
        # cold-start floor be met by stale data. Both teams are in the fixture's season by
        # definition, so one value serves both sides.
        h_season = a_season = F.HistoryIndex.target_season(rec)
        out = {}
        for stat in stats:
            # home team's HOME form (for/against); away team's AWAY form
            if h_season:
                out[f"ha_h_{stat}_for"] = F._roll(self.idx, rec.home_id, stat, "for", None, rec.kickoff_unix, h_season, venue="home")
                out[f"ha_h_{stat}_against"] = F._roll(self.idx, rec.home_id, stat, "against", None, rec.kickoff_unix, h_season, venue="home")
            if a_season:
                out[f"ha_a_{stat}_for"] = F._roll(self.idx, rec.away_id, stat, "for", None, rec.kickoff_unix, a_season, venue="away")
                out[f"ha_a_{stat}_against"] = F._roll(self.idx, rec.away_id, stat, "against", None, rec.kickoff_unix, a_season, venue="away")
        return out

    # ---- family F4: explicit attack x defense matchup ----
    def f_matchup(self, rec: MatchRecord, market: str) -> dict:
        stats = POOLS[market]
        # The TARGET fixture's own season-instance, not the season each team last played
        # in. `current_season()` returns the latter, which for a fixture early in a new
        # season silently yields PRIOR-season form labelled as current-season and lets the
        # cold-start floor be met by stale data. Both teams are in the fixture's season by
        # definition, so one value serves both sides.
        h_season = a_season = F.HistoryIndex.target_season(rec)
        out = {}
        for stat in stats:
            if not (h_season and a_season):
                continue
            # A produces (home for) vs B concedes (away against)
            a_att = F._roll(self.idx, rec.home_id, stat, "for", None, rec.kickoff_unix, h_season)
            b_def = F._roll(self.idx, rec.away_id, stat, "against", None, rec.kickoff_unix, a_season)
            b_att = F._roll(self.idx, rec.away_id, stat, "for", None, rec.kickoff_unix, a_season)
            a_def = F._roll(self.idx, rec.home_id, stat, "against", None, rec.kickoff_unix, h_season)
            # matchup forms: expected A-side and B-side state = mean(prod, concede)
            if a_att is not None and b_def is not None:
                out[f"mu_A_{stat}"] = 0.5 * (a_att + b_def)          # arithmetic matchup (A side)
                out[f"mu_A_{stat}_gm"] = math.sqrt(max(a_att, 0) * max(b_def, 0)) if a_att >= 0 and b_def >= 0 else None
            if b_att is not None and a_def is not None:
                out[f"mu_B_{stat}"] = 0.5 * (b_att + a_def)          # B side
            if a_att is not None and b_def is not None and b_att is not None and a_def is not None:
                out[f"mu_total_{stat}"] = 0.5 * (a_att + b_def) + 0.5 * (b_att + a_def)  # match total expectation
        return out

    # ---- family F5: opponent-quality-adjusted strength ----
    def f_oppquality(self, rec: MatchRecord, market: str) -> dict:
        stat = {"goals": "xg", "corners": "corner_kicks", "cards": "cards", "btts": "xg"}[market]
        R = self.ratings(stat)
        out = {
            f"oq_{stat}_A_att": R.attack(rec.fixture_id, rec.home_id),
            f"oq_{stat}_A_def": R.defense(rec.fixture_id, rec.home_id),
            f"oq_{stat}_B_att": R.attack(rec.fixture_id, rec.away_id),
            f"oq_{stat}_B_def": R.defense(rec.fixture_id, rec.away_id),
        }
        # matchup of ratings: A attack x B defense, B attack x A defense
        aa, bd = out[f"oq_{stat}_A_att"], out[f"oq_{stat}_B_def"]
        ba, ad = out[f"oq_{stat}_B_att"], out[f"oq_{stat}_A_def"]
        out[f"oq_{stat}_A_expect"] = (aa * bd) if (aa is not None and bd is not None) else None
        out[f"oq_{stat}_B_expect"] = (ba * ad) if (ba is not None and ad is not None) else None
        return out

    # ---- family F6: rich TSA pressure stats (mechanism, for/against) ----
    def f_rich(self, rec: MatchRecord, market: str) -> dict:
        stats = {
            "goals": ["big_chances", "np_expected_goals", "shots_inside_box", "touches_in_penalty_area"],
            "corners": ["blocked_shots", "accurate_crosses", "touches_in_penalty_area", "final_third_entries", "throw_ins"],
            "cards": ["tackles", "fouls"],
            "btts": ["big_chances", "np_expected_goals"],
        }[market]
        return self._team_state(rec, stats, prefix="rich")

    def _team_state(self, rec: MatchRecord, stats: list[str], prefix: str) -> dict:
        # The TARGET fixture's own season-instance, not the season each team last played
        # in. `current_season()` returns the latter, which for a fixture early in a new
        # season silently yields PRIOR-season form labelled as current-season and lets the
        # cold-start floor be met by stale data. Both teams are in the fixture's season by
        # definition, so one value serves both sides.
        h_season = a_season = F.HistoryIndex.target_season(rec)
        out = {}
        for stat in stats:
            for w in WINDOWS:
                wl = WLBL[w]
                if h_season:
                    out[f"{prefix}_h_{stat}_for_{wl}"] = F._roll(self.idx, rec.home_id, stat, "for", w, rec.kickoff_unix, h_season)
                    out[f"{prefix}_h_{stat}_against_{wl}"] = F._roll(self.idx, rec.home_id, stat, "against", w, rec.kickoff_unix, h_season)
                if a_season:
                    out[f"{prefix}_a_{stat}_for_{wl}"] = F._roll(self.idx, rec.away_id, stat, "for", w, rec.kickoff_unix, a_season)
                    out[f"{prefix}_a_{stat}_against_{wl}"] = F._roll(self.idx, rec.away_id, stat, "against", w, rec.kickoff_unix, a_season)
        return out


# math imported at module top
