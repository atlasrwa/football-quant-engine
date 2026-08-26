"""Synthetic research data source.

Generates deterministic football match data for proving the research
laboratory architecture. Uses a fixed seed for reproducibility.

The synthetic data includes a deliberately embedded relationship:
- corners outcome is partially correlated with dangerous_attacks,
  corner_differential, and possession_differential
- This allows the discovery engine to independently find the relationship

IMPORTANT: Synthetic data MUST NOT be used to claim real-world edge.
It exists only to prove the machinery works.
"""

from __future__ import annotations

import hashlib
import json
from typing import Optional

import numpy as np

from src.research.data_source import MarketOdds, ResearchDataSource, ResearchMatch


# Fixed seed for reproducibility
_SEED = 42
_NUM_TEAMS = 12
_MATCHES_PER_SEASON = 132  # 12 teams, each plays 11 others home+away = 132
_SEASONS = ["2020", "2021", "2022", "2023"]


class SyntheticResearchDataSource(ResearchDataSource):
    """Generates deterministic synthetic football data.

    Contains an embedded relationship between:
    - dangerous_attacks + possession + historical corners → actual corners

    The discovery engine must find this independently.
    """

    def __init__(self, seed: int = _SEED, num_seasons: int = 4) -> None:
        self._seed = seed
        self._num_seasons = num_seasons
        self._rng = np.random.default_rng(seed)
        self._matches: list[ResearchMatch] = []
        self._odds: list[MarketOdds] = []
        self._generate()

    def _generate(self) -> None:
        """Generate the complete synthetic dataset."""
        teams = [f"Team_{chr(65 + i)}" for i in range(_NUM_TEAMS)]
        seasons = _SEASONS[: self._num_seasons]
        match_id = 1000

        # Team strength parameters (fixed per team across dataset)
        team_attack = self._rng.uniform(0.8, 1.5, _NUM_TEAMS)
        team_defense = self._rng.uniform(0.7, 1.3, _NUM_TEAMS)
        team_corner_tendency = self._rng.uniform(4.0, 7.0, _NUM_TEAMS)
        team_card_tendency = self._rng.uniform(1.5, 3.5, _NUM_TEAMS)

        base_date = 1577836800  # 2020-01-01 UTC

        for season_idx, season in enumerate(seasons):
            season_start = base_date + season_idx * 365 * 86400
            match_day = 0

            for home_idx in range(_NUM_TEAMS):
                for away_idx in range(_NUM_TEAMS):
                    if home_idx == away_idx:
                        continue

                    match_day += 1
                    date_unix = season_start + match_day * 3 * 86400  # ~3 days apart

                    # Generate match statistics with embedded relationships
                    match = self._generate_match(
                        match_id=match_id,
                        date_unix=date_unix,
                        season=season,
                        home_team=teams[home_idx],
                        away_team=teams[away_idx],
                        home_attack=team_attack[home_idx],
                        away_attack=team_attack[away_idx],
                        home_defense=team_defense[home_idx],
                        away_defense=team_defense[away_idx],
                        home_corner_tend=team_corner_tendency[home_idx],
                        away_corner_tend=team_corner_tendency[away_idx],
                        home_card_tend=team_card_tendency[home_idx],
                        away_card_tend=team_card_tendency[away_idx],
                    )
                    self._matches.append(match)

                    # Generate market odds
                    self._generate_odds(match)
                    match_id += 1

    def _generate_match(
        self,
        match_id: int,
        date_unix: int,
        season: str,
        home_team: str,
        away_team: str,
        home_attack: float,
        away_attack: float,
        home_defense: float,
        away_defense: float,
        home_corner_tend: float,
        away_corner_tend: float,
        home_card_tend: float,
        away_card_tend: float,
    ) -> ResearchMatch:
        """Generate a single match with embedded statistical relationships."""
        rng = self._rng

        # Goals: Poisson based on attack vs defense
        home_lambda = home_attack / away_defense * 1.3  # home advantage
        away_lambda = away_attack / home_defense * 1.0
        home_goals = int(rng.poisson(home_lambda))
        away_goals = int(rng.poisson(away_lambda))

        # Possession: team-strength-related + noise
        home_poss = 45 + (home_attack - away_attack) * 8 + rng.normal(0, 5)
        home_poss = float(np.clip(home_poss, 25, 75))
        away_poss = 100 - home_poss

        # Attacks: related to possession + randomness
        attacks_home = int(max(30, home_poss * 1.2 + rng.normal(0, 10)))
        attacks_away = int(max(30, away_poss * 1.2 + rng.normal(0, 10)))
        dangerous_attacks_home = int(max(10, attacks_home * 0.4 + rng.normal(0, 5)))
        dangerous_attacks_away = int(max(10, attacks_away * 0.4 + rng.normal(0, 5)))

        # Shots
        shots_home = int(max(2, home_attack * 8 + rng.normal(0, 3)))
        shots_away = int(max(2, away_attack * 8 + rng.normal(0, 3)))
        shots_on_target_home = int(max(1, shots_home * 0.4 + rng.normal(0, 1)))
        shots_on_target_away = int(max(1, shots_away * 0.4 + rng.normal(0, 1)))

        # ═══════════════════════════════════════════════════════════
        # EMBEDDED RELATIONSHIP: Corners partially predicted by
        # dangerous_attacks + possession + team corner tendency
        # ═══════════════════════════════════════════════════════════
        corner_signal_home = (
            0.3 * dangerous_attacks_home / 20.0
            + 0.2 * (home_poss - 50) / 25.0
            + 0.5 * home_corner_tend / 7.0
        )
        corner_signal_away = (
            0.3 * dangerous_attacks_away / 20.0
            + 0.2 * (away_poss - 50) / 25.0
            + 0.5 * away_corner_tend / 7.0
        )
        corners_home = int(max(0, corner_signal_home * 7 + rng.normal(0, 1.5)))
        corners_away = int(max(0, corner_signal_away * 7 + rng.normal(0, 1.5)))
        total_corners = corners_home + corners_away

        # Cards: related to fouls + referee tendency
        fouls_home = int(max(5, 12 + rng.normal(0, 3)))
        fouls_away = int(max(5, 12 + rng.normal(0, 3)))
        yellow_home = int(max(0, min(fouls_home // 5, int(home_card_tend + rng.normal(0, 0.8)))))
        yellow_away = int(max(0, min(fouls_away // 5, int(away_card_tend + rng.normal(0, 0.8)))))

        # Offsides
        offsides_home = int(max(0, rng.poisson(1.8)))
        offsides_away = int(max(0, rng.poisson(1.8)))
        total_offsides = offsides_home + offsides_away

        # xG
        home_xg = float(max(0, home_lambda + rng.normal(0, 0.3)))
        away_xg = float(max(0, away_lambda + rng.normal(0, 0.3)))

        # PPDA
        ppda_home = float(max(5, 11 + rng.normal(0, 2)))
        ppda_away = float(max(5, 11 + rng.normal(0, 2)))

        return ResearchMatch(
            match_id=match_id,
            date_unix=date_unix,
            league_id=1001,
            season=season,
            home_team=home_team,
            away_team=away_team,
            home_goals=home_goals,
            away_goals=away_goals,
            total_goals=home_goals + away_goals,
            shots_home=shots_home,
            shots_away=shots_away,
            shots_on_target_home=shots_on_target_home,
            shots_on_target_away=shots_on_target_away,
            shots_off_target_home=max(0, shots_home - shots_on_target_home),
            shots_off_target_away=max(0, shots_away - shots_on_target_away),
            corners_home=corners_home,
            corners_away=corners_away,
            total_corners=total_corners,
            yellow_cards_home=yellow_home,
            yellow_cards_away=yellow_away,
            red_cards_home=0,
            red_cards_away=0,
            total_cards=yellow_home + yellow_away,
            offsides_home=offsides_home,
            offsides_away=offsides_away,
            total_offsides=total_offsides,
            fouls_home=fouls_home,
            fouls_away=fouls_away,
            attacks_home=attacks_home,
            attacks_away=attacks_away,
            dangerous_attacks_home=dangerous_attacks_home,
            dangerous_attacks_away=dangerous_attacks_away,
            possession_home=home_poss,
            possession_away=away_poss,
            home_xg=home_xg,
            away_xg=away_xg,
            ppda_home=ppda_home,
            ppda_away=ppda_away,
            referee=f"Referee_{rng.integers(1, 10)}",
        )

    def _generate_odds(self, match: ResearchMatch) -> None:
        """Generate synthetic market odds with embedded margin."""
        rng = self._rng
        total_corners = match.total_corners or 10

        # Goals market (line 2.5)
        goals_line = 2.5
        # True probability of over based on actual total goals distribution
        p_over_goals = 0.52 + rng.normal(0, 0.05)
        p_over_goals = float(np.clip(p_over_goals, 0.3, 0.7))
        margin = 1.05  # 5% overround
        over_odds_goals = float(margin / p_over_goals)
        under_odds_goals = float(margin / (1 - p_over_goals))

        # Corners market (line 9.5)
        corners_line = 9.5
        # True probability influenced by actual corners
        p_over_corners = 0.5 + (total_corners - 9.5) * 0.03 + rng.normal(0, 0.04)
        p_over_corners = float(np.clip(p_over_corners, 0.3, 0.7))
        over_odds_corners = float(margin / p_over_corners)
        under_odds_corners = float(margin / (1 - p_over_corners))

        # Cards market (line 3.5)
        cards_line = 3.5
        total_cards = match.total_cards or 3
        p_over_cards = 0.5 + (total_cards - 3.5) * 0.05 + rng.normal(0, 0.05)
        p_over_cards = float(np.clip(p_over_cards, 0.3, 0.7))
        over_odds_cards = float(margin / p_over_cards)
        under_odds_cards = float(margin / (1 - p_over_cards))

        # Offsides market (line 4.5)
        offsides_line = 4.5
        total_offsides = match.total_offsides or 3
        p_over_offsides = 0.5 + (total_offsides - 4.5) * 0.04 + rng.normal(0, 0.05)
        p_over_offsides = float(np.clip(p_over_offsides, 0.3, 0.7))
        over_odds_offsides = float(margin / p_over_offsides)
        under_odds_offsides = float(margin / (1 - p_over_offsides))

        # Store odds on match (update via new match with odds)
        # We store odds as MarketOdds records
        self._odds.append(MarketOdds(
            match_id=match.match_id,
            market="GOALS_TOTAL",
            line=goals_line,
            over_odds=over_odds_goals,
            under_odds=under_odds_goals,
            timestamp=match.date_unix - 3600,  # 1h before kickoff
        ))
        self._odds.append(MarketOdds(
            match_id=match.match_id,
            market="CORNERS_TOTAL",
            line=corners_line,
            over_odds=over_odds_corners,
            under_odds=under_odds_corners,
            timestamp=match.date_unix - 3600,
        ))
        self._odds.append(MarketOdds(
            match_id=match.match_id,
            market="CARDS_TOTAL",
            line=cards_line,
            over_odds=over_odds_cards,
            under_odds=under_odds_cards,
            timestamp=match.date_unix - 3600,
        ))
        self._odds.append(MarketOdds(
            match_id=match.match_id,
            market="OFFSIDES_TOTAL",
            line=offsides_line,
            over_odds=over_odds_offsides,
            under_odds=under_odds_offsides,
            timestamp=match.date_unix - 3600,
        ))

        # Update the match object with odds fields
        # (We reconstruct to add odds since ResearchMatch is frozen)
        idx = len(self._matches) - 1
        if idx >= 0 and self._matches[idx].match_id == match.match_id:
            old = self._matches[idx]
            self._matches[idx] = ResearchMatch(
                **{
                    **old.to_dict(),
                    "odds_over_goals": over_odds_goals,
                    "odds_under_goals": under_odds_goals,
                    "line_goals": goals_line,
                    "odds_over_corners": over_odds_corners,
                    "odds_under_corners": under_odds_corners,
                    "line_corners": corners_line,
                    "odds_over_cards": over_odds_cards,
                    "odds_under_cards": under_odds_cards,
                    "line_cards": cards_line,
                    "odds_over_offsides": over_odds_offsides,
                    "odds_under_offsides": under_odds_offsides,
                    "line_offsides": offsides_line,
                }
            )

    # ═══════════════════════════════════════════════════════════════
    # ResearchDataSource interface
    # ═══════════════════════════════════════════════════════════════

    def get_matches(
        self,
        league_id: Optional[int] = None,
        season: Optional[str] = None,
        min_date: Optional[int] = None,
        max_date: Optional[int] = None,
    ) -> list[ResearchMatch]:
        """Get synthetic matches with optional filters."""
        result = self._matches
        if league_id is not None:
            result = [m for m in result if m.league_id == league_id]
        if season is not None:
            result = [m for m in result if m.season == season]
        if min_date is not None:
            result = [m for m in result if m.date_unix >= min_date]
        if max_date is not None:
            result = [m for m in result if m.date_unix < max_date]
        return sorted(result, key=lambda m: m.date_unix)

    def get_available_fields(self) -> list[str]:
        """All fields are available in synthetic data."""
        if not self._matches:
            return []
        return self._matches[0].available_fields

    def get_market_odds(
        self,
        match_ids: Optional[list[int]] = None,
        market: Optional[str] = None,
    ) -> list[MarketOdds]:
        """Get synthetic market odds."""
        result = self._odds
        if match_ids is not None:
            ids_set = set(match_ids)
            result = [o for o in result if o.match_id in ids_set]
        if market is not None:
            result = [o for o in result if o.market == market]
        return result
