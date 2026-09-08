"""Temporal Feature Engine — builds features with strict information-time enforcement.

CRITICAL RULE:
    For every feature used by a prediction:
        historical_match_timestamp < prediction_timestamp

    This engine does NOT rely on data being sorted.
    It EXPLICITLY filters by information time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from src.research.data_source import ResearchMatch
from src.research.forward.snapshot import (
    FeatureProvenance,
    PreMatchSnapshot,
    TimestampConfidence,
)

logger = logging.getLogger(__name__)

_POST_MATCH_FEATURES = frozenset({
    "home_goals", "away_goals", "total_goals",
    "ht_home_goals", "ht_away_goals",
    "shots_home", "shots_away",
    "shots_on_target_home", "shots_on_target_away",
    "shots_off_target_home", "shots_off_target_away",
    "corners_home", "corners_away", "total_corners",
    "yellow_cards_home", "yellow_cards_away",
    "red_cards_home", "red_cards_away", "total_cards",
    "offsides_home", "offsides_away", "total_offsides",
    "fouls_home", "fouls_away",
    "attacks_home", "attacks_away",
    "dangerous_attacks_home", "dangerous_attacks_away",
    "possession_home", "possession_away",
    "home_xg", "away_xg",
    "result",
})

_PRE_MATCH_FEATURE_PREFIXES = frozenset({
    "avg_", "form_", "h2h_", "league_pos_", "home_avg_", "away_avg_",
    "last_n_", "rolling_", "elo_", "rank_",
})


@dataclass
class TemporalFeatureEngine:
    """Build pre-match feature snapshots with strict temporal enforcement."""

    historical_matches: list[ResearchMatch] = field(default_factory=list)
    lookback_matches: int = 20
    strict_mode: bool = True

    def build_snapshot(
        self,
        fixture_id: str,
        home_team_id: int,
        away_team_id: int,
        prediction_timestamp: float,
        kickoff_timestamp: float,
        hypothesis_id: str = "",
        model_id: str = "",
        research_run_id: str = "",
        feature_list: Optional[list[str]] = None,
    ) -> PreMatchSnapshot:
        if prediction_timestamp > kickoff_timestamp:
            raise ValueError(
                f"prediction_timestamp ({prediction_timestamp}) must be "
                f"<= kickoff_timestamp ({kickoff_timestamp})"
            )

        eligible_matches = self._filter_eligible_matches(prediction_timestamp)
        features: dict[str, Optional[float]] = {}
        provenance: list[FeatureProvenance] = []

        home_matches = self._get_team_matches(
            eligible_matches, home_team_id, limit=self.lookback_matches
        )
        home_features, home_prov = self._compute_team_features(
            home_matches, home_team_id, "home", prediction_timestamp
        )
        features.update(home_features)
        provenance.extend(home_prov)

        away_matches = self._get_team_matches(
            eligible_matches, away_team_id, limit=self.lookback_matches
        )
        away_features, away_prov = self._compute_team_features(
            away_matches, away_team_id, "away", prediction_timestamp
        )
        features.update(away_features)
        provenance.extend(away_prov)

        h2h_matches = self._get_h2h_matches(
            eligible_matches, home_team_id, away_team_id, limit=10
        )
        h2h_features, h2h_prov = self._compute_h2h_features(
            h2h_matches, prediction_timestamp
        )
        features.update(h2h_features)
        provenance.extend(h2h_prov)

        if feature_list:
            features = {k: v for k, v in features.items() if k in feature_list}
            provenance = tuple(p for p in provenance if p.feature_id in feature_list)
        else:
            provenance = tuple(provenance)

        return PreMatchSnapshot(
            fixture_id=fixture_id,
            prediction_timestamp=prediction_timestamp,
            kickoff_timestamp=kickoff_timestamp,
            features=features,
            feature_provenance=provenance,
            hypothesis_id=hypothesis_id,
            model_id=model_id,
            research_run_id=research_run_id,
        )

    def _filter_eligible_matches(self, prediction_timestamp: float) -> list[ResearchMatch]:
        eligible = []
        for match in self.historical_matches:
            if match.date_unix < prediction_timestamp:
                eligible.append(match)
            elif match.date_unix == prediction_timestamp and self.strict_mode:
                logger.debug(
                    "Excluding same-timestamp match %d (strict mode)", match.match_id
                )
        return eligible

    def _get_team_matches(
        self, matches: list[ResearchMatch], team_id: int, limit: int = 20
    ) -> list[ResearchMatch]:
        team_str = str(team_id)
        team_matches = [
            m for m in matches
            if m.home_team == team_str or m.away_team == team_str
        ]
        team_matches.sort(key=lambda m: m.date_unix, reverse=True)
        return team_matches[:limit]

    def _get_h2h_matches(
        self,
        matches: list[ResearchMatch],
        home_team_id: int,
        away_team_id: int,
        limit: int = 10,
    ) -> list[ResearchMatch]:
        h2h = []
        home_str, away_str = str(home_team_id), str(away_team_id)
        for match in matches:
            if (
                (match.home_team == home_str and match.away_team == away_str)
                or (match.home_team == away_str and match.away_team == home_str)
            ):
                h2h.append(match)
        h2h.sort(key=lambda m: m.date_unix, reverse=True)
        return h2h[:limit]

    @staticmethod
    def _team_side(match: ResearchMatch, team_id: int) -> str:
        """Return the historical fixture side occupied by ``team_id``.

        Output labels (``home``/``away`` in the target fixture) are deliberately
        kept separate from historical team identity. A team may have played on
        either side in any prior fixture.
        """
        team_str = str(team_id)
        if match.home_team == team_str:
            return "home"
        if match.away_team == team_str:
            return "away"
        raise ValueError(
            f"team {team_id} is not part of historical match {match.match_id}"
        )

    def _compute_team_features(
        self,
        matches: list[ResearchMatch],
        team_id: int,
        output_side: str,
        prediction_timestamp: float,
    ) -> tuple[dict[str, Optional[float]], list[FeatureProvenance]]:
        """Compute team-specific aggregates from strictly prior fixtures.

        ``team_id`` determines which side of each historical fixture belongs to
        the team. ``output_side`` only names the feature for the target fixture.
        Keeping those concepts separate prevents historical away performances
        from being accidentally attributed as home performances (and vice versa).
        """
        del prediction_timestamp  # filtering is enforced before this method

        feature_names = (
            "avg_goals",
            "avg_corners",
            "avg_cards",
            "avg_shots",
            "avg_dangerous_attacks",
            "form_points",
            "matches_played",
        )

        if not matches:
            return (
                {f"{name}_{output_side}": None for name in feature_names},
                [],
            )

        latest_match_time = max(match.date_unix for match in matches)
        goals_values: list[float] = []
        corners_values: list[float] = []
        cards_values: list[float] = []
        shots_values: list[float] = []
        da_values: list[float] = []
        points_values: list[float] = []

        for match in matches:
            historical_side = self._team_side(match, team_id)
            is_home = historical_side == "home"

            team_goals = match.home_goals if is_home else match.away_goals
            opp_goals = match.away_goals if is_home else match.home_goals
            if team_goals is not None:
                goals_values.append(float(team_goals))
            if team_goals is not None and opp_goals is not None:
                points_values.append(
                    3.0 if team_goals > opp_goals else 1.0 if team_goals == opp_goals else 0.0
                )

            corners = match.corners_home if is_home else match.corners_away
            if corners is not None:
                corners_values.append(float(corners))

            yellow = match.yellow_cards_home if is_home else match.yellow_cards_away
            red = match.red_cards_home if is_home else match.red_cards_away
            if yellow is not None or red is not None:
                cards_values.append(float((yellow or 0) + (red or 0)))

            shots = match.shots_home if is_home else match.shots_away
            if shots is not None:
                shots_values.append(float(shots))

            dangerous_attacks = (
                match.dangerous_attacks_home if is_home else match.dangerous_attacks_away
            )
            if dangerous_attacks is not None:
                da_values.append(float(dangerous_attacks))

        def average(values: list[float]) -> Optional[float]:
            return sum(values) / len(values) if values else None

        features: dict[str, Optional[float]] = {
            f"avg_goals_{output_side}": average(goals_values),
            f"avg_corners_{output_side}": average(corners_values),
            f"avg_cards_{output_side}": average(cards_values),
            f"avg_shots_{output_side}": average(shots_values),
            f"avg_dangerous_attacks_{output_side}": average(da_values),
            f"form_points_{output_side}": average(points_values),
            f"matches_played_{output_side}": float(len(matches)),
        }

        provenance = [
            FeatureProvenance(
                feature_id=feature_id,
                value=value,
                information_timestamp=float(latest_match_time),
                timestamp_confidence=TimestampConfidence.ESTIMATED,
                estimation_method="latest_historical_match_completion_time",
            )
            for feature_id, value in features.items()
        ]
        return features, provenance

    def _compute_h2h_features(
        self, matches: list[ResearchMatch], prediction_timestamp: float
    ) -> tuple[dict[str, Optional[float]], list[FeatureProvenance]]:
        del prediction_timestamp
        features: dict[str, Optional[float]] = {
            "h2h_matches": float(len(matches)) if matches else None,
            "h2h_avg_goals": None,
        }
        provenance: list[FeatureProvenance] = []

        if matches:
            goals = [match.total_goals for match in matches if match.total_goals is not None]
            if goals:
                features["h2h_avg_goals"] = sum(goals) / len(goals)

            latest_time = max(match.date_unix for match in matches)
            provenance = [
                FeatureProvenance(
                    feature_id=feature_id,
                    value=value,
                    information_timestamp=float(latest_time),
                    timestamp_confidence=TimestampConfidence.ESTIMATED,
                    estimation_method="latest_h2h_match_completion_time",
                )
                for feature_id, value in features.items()
            ]

        return features, provenance

    @staticmethod
    def is_post_match_feature(feature_id: str) -> bool:
        return feature_id in _POST_MATCH_FEATURES

    @staticmethod
    def is_pre_match_feature(feature_id: str) -> bool:
        return any(feature_id.startswith(prefix) for prefix in _PRE_MATCH_FEATURE_PREFIXES)
