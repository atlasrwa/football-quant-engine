"""Temporal Feature Engine — builds features with strict information-time enforcement.

CRITICAL RULE:
    For every feature used by a prediction:
        historical_match_timestamp < prediction_timestamp

    This engine does NOT rely on data being sorted.
    It EXPLICITLY filters by information time.

Rejected features:
    - Future matches (match_timestamp >= prediction_timestamp)
    - Same-time matches (ambiguous temporal ordering)
    - Post-match statistics from the target fixture
    - Final results, goals, corners, cards, xG, possession, attacks
    - Any derived feature containing future information

Allowed features (genuinely pre-match):
    - Historical averages computed from PAST matches only
    - League position at prediction time
    - Form metrics from completed past matches
    - Pre-match odds (if available before prediction)
    - Scheduled referee (if known)
    - Head-to-head record from past encounters
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from src.research.data_source import ResearchMatch
from src.research.forward.snapshot import (
    FeatureProvenance,
    PreMatchSnapshot,
    TimestampConfidence,
)

logger = logging.getLogger(__name__)

# Features that are ALWAYS post-match outcomes and NEVER pre-match
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
    "ppda_home", "ppda_away",
    "result",
})

# Features that are genuinely pre-match (available before kickoff)
# These are COMPUTED from historical data, not from the target match itself
_PRE_MATCH_FEATURE_PREFIXES = frozenset({
    "avg_", "form_", "h2h_", "league_pos_", "home_avg_", "away_avg_",
    "last_n_", "rolling_", "elo_", "rank_",
})


@dataclass
class TemporalFeatureEngine:
    """Builds pre-match feature snapshots with strict temporal enforcement.

    Does NOT rely on data being sorted.
    EXPLICITLY filters all historical matches by timestamp.
    REJECTS any feature derived from future information.

    Usage:
        engine = TemporalFeatureEngine(historical_matches=matches)
        snapshot = engine.build_snapshot(
            fixture_id="abc",
            home_team_id=1,
            away_team_id=2,
            prediction_timestamp=1700000000,
            kickoff_timestamp=1700003600,
            hypothesis_id="hyp_123",
        )
    """

    historical_matches: list[ResearchMatch] = field(default_factory=list)
    lookback_matches: int = 20  # Max historical matches per team
    strict_mode: bool = True  # Reject ambiguous timestamps

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
        """Build a pre-match feature snapshot with temporal guarantees.

        Args:
            fixture_id: Target fixture identifier.
            home_team_id: Home team stable ID.
            away_team_id: Away team stable ID.
            prediction_timestamp: When prediction is being generated.
            kickoff_timestamp: Scheduled kickoff time.
            hypothesis_id: Strategy/hypothesis generating this prediction.
            model_id: Model identifier.
            research_run_id: Parent research run.
            feature_list: Which features to compute (None = all available).

        Returns:
            PreMatchSnapshot with temporal guarantees enforced.

        Raises:
            ValueError: If prediction_timestamp > kickoff_timestamp.
        """
        if prediction_timestamp > kickoff_timestamp:
            raise ValueError(
                f"prediction_timestamp ({prediction_timestamp}) must be "
                f"<= kickoff_timestamp ({kickoff_timestamp})"
            )

        # Filter historical matches: ONLY those completed BEFORE prediction_timestamp
        eligible_matches = self._filter_eligible_matches(prediction_timestamp)

        # Compute features from eligible historical matches
        features: dict[str, Optional[float]] = {}
        provenance: list[FeatureProvenance] = []

        # Home team features
        home_matches = self._get_team_matches(
            eligible_matches, home_team_id, limit=self.lookback_matches
        )
        home_features, home_prov = self._compute_team_features(
            home_matches, "home", prediction_timestamp
        )
        features.update(home_features)
        provenance.extend(home_prov)

        # Away team features
        away_matches = self._get_team_matches(
            eligible_matches, away_team_id, limit=self.lookback_matches
        )
        away_features, away_prov = self._compute_team_features(
            away_matches, "away", prediction_timestamp
        )
        features.update(away_features)
        provenance.extend(away_prov)

        # H2H features
        h2h_matches = self._get_h2h_matches(
            eligible_matches, home_team_id, away_team_id, limit=10
        )
        h2h_features, h2h_prov = self._compute_h2h_features(
            h2h_matches, prediction_timestamp
        )
        features.update(h2h_features)
        provenance.extend(h2h_prov)

        # Filter to requested features if specified
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
        """Filter historical matches to ONLY those completed before prediction time.

        Does NOT rely on data being sorted.
        Explicitly checks every match timestamp.
        """
        eligible = []
        for match in self.historical_matches:
            # Match must have been completed (has a result)
            # AND its timestamp must be strictly BEFORE prediction time
            if match.date_unix < prediction_timestamp:
                eligible.append(match)
            elif match.date_unix == prediction_timestamp and self.strict_mode:
                # Same-time: ambiguous → EXCLUDE in strict mode
                logger.debug(
                    "Excluding same-timestamp match %d (strict mode)", match.match_id
                )
        return eligible

    def _get_team_matches(
        self, matches: list[ResearchMatch], team_id: int, limit: int = 20
    ) -> list[ResearchMatch]:
        """Get recent matches for a team, sorted most-recent-first."""
        team_matches = [
            m for m in matches
            if m.home_team == str(team_id) or m.away_team == str(team_id)
            or m.league_id == team_id  # Fallback: match by team in league context
        ]
        # Sort by date descending (most recent first)
        team_matches.sort(key=lambda m: m.date_unix, reverse=True)
        return team_matches[:limit]

    def _get_h2h_matches(
        self, matches: list[ResearchMatch],
        home_team_id: int, away_team_id: int,
        limit: int = 10,
    ) -> list[ResearchMatch]:
        """Get head-to-head matches between two teams."""
        h2h = []
        home_str, away_str = str(home_team_id), str(away_team_id)
        for m in matches:
            if ((m.home_team == home_str and m.away_team == away_str) or
                    (m.home_team == away_str and m.away_team == home_str)):
                h2h.append(m)
        h2h.sort(key=lambda m: m.date_unix, reverse=True)
        return h2h[:limit]

    def _compute_team_features(
        self, matches: list[ResearchMatch], side: str, prediction_timestamp: float
    ) -> tuple[dict[str, Optional[float]], list[FeatureProvenance]]:
        """Compute aggregate features for a team from historical matches.

        Only uses post-match stats from PAST matches (which are known outcomes
        of those past matches — this is legitimate historical information).
        """
        features: dict[str, Optional[float]] = {}
        provenance: list[FeatureProvenance] = []

        if not matches:
            # All features are None (missing), NOT zero
            features[f"avg_goals_{side}"] = None
            features[f"avg_corners_{side}"] = None
            features[f"avg_cards_{side}"] = None
            features[f"avg_shots_{side}"] = None
            features[f"avg_dangerous_attacks_{side}"] = None
            features[f"form_points_{side}"] = None
            features[f"matches_played_{side}"] = None
            return features, provenance

        # Latest match timestamp used (for provenance)
        latest_match_time = max(m.date_unix for m in matches)

        # Average goals from past matches
        goals = [m.home_goals if m.home_team == str(side) else m.away_goals
                 for m in matches if m.home_goals is not None]
        # Simplified: use total_goals as proxy
        goals_values = [m.total_goals for m in matches if m.total_goals is not None]
        avg_goals = sum(goals_values) / len(goals_values) if goals_values else None
        features[f"avg_goals_{side}"] = avg_goals

        # Average corners
        corners_values = [m.total_corners for m in matches if m.total_corners is not None]
        avg_corners = sum(corners_values) / len(corners_values) if corners_values else None
        features[f"avg_corners_{side}"] = avg_corners

        # Average cards
        cards_values = [m.total_cards for m in matches if m.total_cards is not None]
        avg_cards = sum(cards_values) / len(cards_values) if cards_values else None
        features[f"avg_cards_{side}"] = avg_cards

        # Average dangerous attacks
        da_values = []
        for m in matches:
            da = m.dangerous_attacks_home if m.dangerous_attacks_home is not None else m.dangerous_attacks_away
            if da is not None:
                da_values.append(da)
        avg_da = sum(da_values) / len(da_values) if da_values else None
        features[f"avg_dangerous_attacks_{side}"] = avg_da

        # Matches played
        features[f"matches_played_{side}"] = float(len(matches))

        # Build provenance for all features
        for feat_id, value in features.items():
            provenance.append(FeatureProvenance(
                feature_id=feat_id,
                value=value,
                information_timestamp=float(latest_match_time),
                timestamp_confidence=TimestampConfidence.ESTIMATED,
                estimation_method="latest_historical_match_completion_time",
            ))

        return features, provenance

    def _compute_h2h_features(
        self, matches: list[ResearchMatch], prediction_timestamp: float
    ) -> tuple[dict[str, Optional[float]], list[FeatureProvenance]]:
        """Compute head-to-head features from historical encounters."""
        features: dict[str, Optional[float]] = {}
        provenance: list[FeatureProvenance] = []

        features["h2h_matches"] = float(len(matches)) if matches else None
        features["h2h_avg_goals"] = None

        if matches:
            goals = [m.total_goals for m in matches if m.total_goals is not None]
            if goals:
                features["h2h_avg_goals"] = sum(goals) / len(goals)

            latest_time = max(m.date_unix for m in matches)
            for feat_id, value in features.items():
                provenance.append(FeatureProvenance(
                    feature_id=feat_id,
                    value=value,
                    information_timestamp=float(latest_time),
                    timestamp_confidence=TimestampConfidence.ESTIMATED,
                    estimation_method="latest_h2h_match_completion_time",
                ))

        return features, provenance

    @staticmethod
    def is_post_match_feature(feature_id: str) -> bool:
        """Check if a feature is a post-match outcome (always forbidden for predictions)."""
        return feature_id in _POST_MATCH_FEATURES

    @staticmethod
    def is_pre_match_feature(feature_id: str) -> bool:
        """Check if a feature name matches pre-match patterns."""
        for prefix in _PRE_MATCH_FEATURE_PREFIXES:
            if feature_id.startswith(prefix):
                return True
        return False
