"""Normalization — TheStatsAPI payloads to canonical ResearchMatch.

CRITICAL RULES (identical philosophy to the FootyStats normalizer):
1. NULL != ZERO: a field absent from the payload stays None; a genuine 0 is 0.
2. Deterministic: same payload -> same ResearchMatch -> same content hash.
3. RAW only: no computed model features here, only source values.
4. Temporal integrity: only post-match stats populate post-match fields;
   pre-match odds are handled by the odds normalizer, not here.

Input shape (see data/thestatsapi/championship/):
    fixture = {
        "id": "mt_...", "competition_id": "comp_...", "season_id": "sn_...",
        "status": "finished", "utc_date": "2025-05-25T15:00:00.000Z",
        "home_team": {"id": "tm_...", "name": ...},
        "away_team": {"id": "tm_...", "name": ...},
        "score": {"home": int|None, "away": int|None, ...},
    }
    stats = {"data": {"match_id": "mt_...",
        "overview": {stat: {"all": {"home": v, "away": v}, ...}},
        "shots": {...}, "attack": {...}, "passes": {...},
        "duels": {...}, "defending": {...}, "goalkeeping": {...},
        "np_expected_goals": {"all": {"home": v, "away": v}}}}

A completed match requires a fixture with a resolvable kickoff, both team
names, and both goal counts (the minimum for a research record). Stats are
optional: a fixture with no stats still yields a valid ResearchMatch with all
stat fields None (NULL != ZERO).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.research.data_source import ResearchMatch
from src.research.thestatsapi import ids
from src.research.thestatsapi.exceptions import TheStatsAPIResponseError

logger = logging.getLogger(__name__)

_FINISHED_STATUSES = frozenset({"finished", "complete", "played"})


# ---------------------------------------------------------------------------
# NULL-safe coercion helpers (NULL != ZERO)
# ---------------------------------------------------------------------------

def _safe_int(value: Any) -> Optional[int]:
    """Coerce to int; None and non-numeric stay None. A genuine 0 stays 0."""
    if value is None:
        return None
    if isinstance(value, bool):  # guard: bool is a subclass of int
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    """Coerce to float; None and non-numeric stay None. A genuine 0.0 stays 0.0."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_possession(value: Any) -> Optional[float]:
    """Coerce possession to float in [0, 100]; out-of-range or None -> None."""
    v = _safe_float(value)
    if v is None:
        return None
    if v < 0 or v > 100:
        return None
    return v


def parse_iso_to_unix(iso: Any) -> Optional[int]:
    """Parse an ISO-8601 UTC timestamp (e.g. '2025-05-25T15:00:00.000Z') to unix.

    Returns None if the value is missing or unparseable (never fabricates 0).
    """
    if not isinstance(iso, str) or not iso:
        return None
    text = iso.strip()
    # Python's fromisoformat handles offsets but not a trailing 'Z' before 3.11
    # in all builds; normalize 'Z' -> '+00:00'.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _cell(stats_data: dict[str, Any], group: str, stat: Optional[str],
          period: str, side: str) -> Any:
    """Read stats_data[group][stat][period][side], tolerating absence.

    For the ``np_expected_goals`` group the stat level is skipped (the group is
    itself the stat node), matching the provider shape and the reference
    ``scripts/championship_adapter._cell``.

    Returns None if any level is missing (NULL != ZERO preserved).
    """
    if not isinstance(stats_data, dict):
        return None
    if group == "np_expected_goals":
        node = stats_data.get("np_expected_goals") or {}
    else:
        grp = stats_data.get(group) or {}
        if not isinstance(grp, dict):
            return None
        node = grp.get(stat) or {}
    if not isinstance(node, dict):
        return None
    per = node.get(period)
    if not isinstance(per, dict):
        return None
    return per.get(side)


class TheStatsAPINormalizer:
    """Normalizes TheStatsAPI fixture+stats payloads to ResearchMatch.

    Preserves NULL semantics; never fabricates values. Tracks field
    availability for coverage auditing (parallel to MatchNormalizer).
    """

    def __init__(self) -> None:
        self._normalized_count = 0
        self._skipped_count = 0
        self._field_availability: dict[str, int] = {}

    @property
    def normalized_count(self) -> int:
        return self._normalized_count

    @property
    def skipped_count(self) -> int:
        return self._skipped_count

    @property
    def field_availability(self) -> dict[str, int]:
        return dict(self._field_availability)

    def normalize(
        self,
        fixture: dict[str, Any],
        stats: Optional[dict[str, Any]] = None,
    ) -> Optional[ResearchMatch]:
        """Normalize one fixture (+ optional stats) into a ResearchMatch.

        Args:
            fixture: Fixture dict from a TheStatsAPI fixtures payload.
            stats: Optional parsed /stats response for the same match.

        Returns:
            ResearchMatch, or None if the fixture is not a usable completed
            match (missing identity, kickoff, teams, or goals).
        """
        if not isinstance(fixture, dict):
            self._skipped_count += 1
            return None

        match_ref = fixture.get("id")
        if not isinstance(match_ref, str) or not match_ref:
            self._skipped_count += 1
            return None

        status = str(fixture.get("status", "")).lower()
        if status not in _FINISHED_STATUSES:
            self._skipped_count += 1
            return None

        event_ts = parse_iso_to_unix(fixture.get("utc_date"))
        if event_ts is None:
            self._skipped_count += 1
            return None

        home_team = fixture.get("home_team") or {}
        away_team = fixture.get("away_team") or {}
        home_name = home_team.get("name") if isinstance(home_team, dict) else None
        away_name = away_team.get("name") if isinstance(away_team, dict) else None
        if not home_name or not away_name:
            self._skipped_count += 1
            return None

        score = fixture.get("score") or {}
        home_goals = _safe_int(score.get("home"))
        away_goals = _safe_int(score.get("away"))
        if home_goals is None or away_goals is None:
            self._skipped_count += 1
            return None

        try:
            match_id = ids.parse_match_id(match_ref)
        except ids.ProviderIdError as exc:
            logger.warning("Skipping match with unparseable id %r: %s", match_ref, exc)
            self._skipped_count += 1
            return None

        comp_ref = fixture.get("competition_id") or ""
        try:
            league_id = ids.parse_competition_id(comp_ref) if comp_ref else 0
        except ids.ProviderIdError:
            league_id = 0

        season = str(fixture.get("season_id", ""))

        sd = (stats or {}).get("data", {}) if isinstance(stats, dict) else {}

        def ov(stat: str, side: str, period: str = "all") -> Any:
            return _cell(sd, "overview", stat, period, side)

        # Corners
        corners_home = _safe_int(ov("corner_kicks", "home"))
        corners_away = _safe_int(ov("corner_kicks", "away"))
        total_corners = (
            (corners_home + corners_away)
            if corners_home is not None and corners_away is not None
            else None
        )

        # Cards: yellow + red per side. red_cards may be null (NULL != ZERO):
        # if red is null we do NOT coerce it to 0 for the per-side card counts.
        yellow_home = _safe_int(ov("yellow_cards", "home"))
        yellow_away = _safe_int(ov("yellow_cards", "away"))
        red_home = _safe_int(ov("red_cards", "home"))
        red_away = _safe_int(ov("red_cards", "away"))

        total_cards = self._compute_total_cards(yellow_home, yellow_away, red_home, red_away)

        match = ResearchMatch(
            match_id=match_id,
            date_unix=event_ts,
            league_id=league_id,
            season=season,
            home_team=str(home_name),
            away_team=str(away_name),
            # Results
            home_goals=home_goals,
            away_goals=away_goals,
            total_goals=home_goals + away_goals,
            # Shots
            shots_home=_safe_int(ov("total_shots", "home")),
            shots_away=_safe_int(ov("total_shots", "away")),
            shots_on_target_home=_safe_int(ov("shots_on_target", "home")),
            shots_on_target_away=_safe_int(ov("shots_on_target", "away")),
            # Corners
            corners_home=corners_home,
            corners_away=corners_away,
            total_corners=total_corners,
            # Cards
            yellow_cards_home=yellow_home,
            yellow_cards_away=yellow_away,
            red_cards_home=red_home,
            red_cards_away=red_away,
            total_cards=total_cards,
            # Fouls
            fouls_home=_safe_int(ov("fouls", "home")),
            fouls_away=_safe_int(ov("fouls", "away")),
            # Possession
            possession_home=_safe_possession(ov("ball_possession", "home")),
            possession_away=_safe_possession(ov("ball_possession", "away")),
            # xG
            home_xg=_safe_float(ov("expected_goals", "home")),
            away_xg=_safe_float(ov("expected_goals", "away")),
            # Rich per-side fields (additive; already declared on ResearchMatch)
            shots_inside_box_home=_safe_int(_cell(sd, "shots", "shots_inside_box", "all", "home")),
            shots_inside_box_away=_safe_int(_cell(sd, "shots", "shots_inside_box", "all", "away")),
            shots_outside_box_home=_safe_int(_cell(sd, "shots", "shots_outside_box", "all", "home")),
            shots_outside_box_away=_safe_int(_cell(sd, "shots", "shots_outside_box", "all", "away")),
            blocked_shots_home=_safe_int(_cell(sd, "shots", "blocked_shots", "all", "home")),
            blocked_shots_away=_safe_int(_cell(sd, "shots", "blocked_shots", "all", "away")),
            big_chances_home=_safe_int(ov("big_chances", "home")),
            big_chances_away=_safe_int(ov("big_chances", "away")),
            npxg_home=_safe_float(_cell(sd, "np_expected_goals", None, "all", "home")),
            npxg_away=_safe_float(_cell(sd, "np_expected_goals", None, "all", "away")),
            touches_in_box_home=_safe_int(_cell(sd, "attack", "touches_in_penalty_area", "all", "home")),
            touches_in_box_away=_safe_int(_cell(sd, "attack", "touches_in_penalty_area", "all", "away")),
            final_third_entries_home=_safe_int(_cell(sd, "passes", "final_third_entries", "all", "home")),
            final_third_entries_away=_safe_int(_cell(sd, "passes", "final_third_entries", "all", "away")),
            fouled_in_final_third_home=_safe_int(_cell(sd, "attack", "fouled_in_final_third", "all", "home")),
            fouled_in_final_third_away=_safe_int(_cell(sd, "attack", "fouled_in_final_third", "all", "away")),
            accurate_crosses_home=_safe_int(_cell(sd, "passes", "accurate_crosses", "all", "home")),
            accurate_crosses_away=_safe_int(_cell(sd, "passes", "accurate_crosses", "all", "away")),
            accurate_long_balls_home=_safe_int(_cell(sd, "passes", "accurate_long_balls", "all", "home")),
            accurate_long_balls_away=_safe_int(_cell(sd, "passes", "accurate_long_balls", "all", "away")),
            aerial_duel_pct_home=_safe_float(_cell(sd, "duels", "aerial_duels_percentage", "all", "home")),
            aerial_duel_pct_away=_safe_float(_cell(sd, "duels", "aerial_duels_percentage", "all", "away")),
            ground_duel_pct_home=_safe_float(_cell(sd, "duels", "ground_duels_percentage", "all", "home")),
            ground_duel_pct_away=_safe_float(_cell(sd, "duels", "ground_duels_percentage", "all", "away")),
            tackles_home=_safe_int(_cell(sd, "defending", "tackles", "all", "home")),
            tackles_away=_safe_int(_cell(sd, "defending", "tackles", "all", "away")),
            tackles_won_pct_home=_safe_float(_cell(sd, "defending", "tackles_won_percentage", "all", "home")),
            tackles_won_pct_away=_safe_float(_cell(sd, "defending", "tackles_won_percentage", "all", "away")),
            interceptions_home=_safe_int(_cell(sd, "defending", "interceptions", "all", "home")),
            interceptions_away=_safe_int(_cell(sd, "defending", "interceptions", "all", "away")),
            clearances_home=_safe_int(_cell(sd, "defending", "clearances", "all", "home")),
            clearances_away=_safe_int(_cell(sd, "defending", "clearances", "all", "away")),
            saves_home=_safe_int(_cell(sd, "goalkeeping", "saves", "all", "home")),
            saves_away=_safe_int(_cell(sd, "goalkeeping", "saves", "all", "away")),
            high_claims_home=_safe_int(_cell(sd, "goalkeeping", "high_claims", "all", "home")),
            high_claims_away=_safe_int(_cell(sd, "goalkeeping", "high_claims", "all", "away")),
            goals_prevented_home=_safe_float(_cell(sd, "goalkeeping", "goals_prevented", "all", "home")),
            goals_prevented_away=_safe_float(_cell(sd, "goalkeeping", "goals_prevented", "all", "away")),
        )

        self._normalized_count += 1
        self._track_field_availability(match)
        return match

    def normalize_batch(
        self,
        fixtures: list[dict[str, Any]],
        stats_by_match_ref: Optional[dict[str, dict[str, Any]]] = None,
    ) -> list[ResearchMatch]:
        """Normalize a batch of fixtures, joining stats by match ref if given."""
        stats_by_match_ref = stats_by_match_ref or {}
        results: list[ResearchMatch] = []
        for fx in fixtures:
            ref = fx.get("id") if isinstance(fx, dict) else None
            stats = stats_by_match_ref.get(ref) if ref else None
            match = self.normalize(fx, stats)
            if match is not None:
                results.append(match)
        return results

    @staticmethod
    def _compute_total_cards(
        yellow_home: Optional[int],
        yellow_away: Optional[int],
        red_home: Optional[int],
        red_away: Optional[int],
    ) -> Optional[int]:
        """Sum available card components; None if ALL components are missing.

        NULL != ZERO: if every component is None the total is None (unknown),
        not 0. If at least one component is present, missing components are not
        invented — only present components are summed.
        """
        parts = [x for x in (yellow_home, yellow_away, red_home, red_away) if x is not None]
        if not parts:
            return None
        return sum(parts)

    def _track_field_availability(self, match: ResearchMatch) -> None:
        for key, val in match.to_dict().items():
            if val is not None:
                self._field_availability[key] = self._field_availability.get(key, 0) + 1
