"""Feature registry and transform engine for the research laboratory.

Provides dynamic feature definition, registration, versioning, and
computation with strict temporal causality enforcement.

Every feature has:
- Unique identity (name + version + content hash)
- Source fields it depends on
- Temporal contract (pre-match vs post-match)
- Transformation definition
- Market applicability
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

import numpy as np


class TemporalClass(Enum):
    """When information becomes available."""
    PRE_MATCH = "PRE_MATCH"    # Available before kickoff (odds, team history)
    POST_MATCH = "POST_MATCH"  # Available after kickoff (goals, corners, etc.)
    DERIVED = "DERIVED"        # Computed from historical post-match data (rolling means)


class TransformType(Enum):
    """Types of feature transformations."""
    RAW = "RAW"
    ROLLING_MEAN = "ROLLING_MEAN"
    ROLLING_STD = "ROLLING_STD"
    ROLLING_MEDIAN = "ROLLING_MEDIAN"
    EWMA = "EWMA"
    DIFFERENCE = "DIFFERENCE"
    RATIO = "RATIO"
    Z_SCORE = "Z_SCORE"
    LEAGUE_NORMALIZE = "LEAGUE_NORMALIZE"
    HOME_AWAY_NORMALIZE = "HOME_AWAY_NORMALIZE"
    TREND = "TREND"
    MOMENTUM = "MOMENTUM"
    VOLATILITY = "VOLATILITY"
    INTERACTION = "INTERACTION"


@dataclass(frozen=True)
class FeatureDefinition:
    """A registered feature definition.

    Immutable after creation. Content hash provides identity.
    """
    name: str
    source_fields: tuple[str, ...]
    transform: TransformType
    params: dict[str, Any] = field(default_factory=dict)
    temporal_class: TemporalClass = TemporalClass.DERIVED
    market_applicability: tuple[str, ...] = ()  # empty = all markets
    version: str = "1.0.0"
    description: str = ""

    @property
    def content_hash(self) -> str:
        """Compute deterministic content hash for this definition."""
        canonical = json.dumps({
            "name": self.name,
            "source_fields": list(self.source_fields),
            "transform": self.transform.value,
            "params": self.params,
            "temporal_class": self.temporal_class.value,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @property
    def feature_id(self) -> str:
        """Unique feature identifier."""
        return f"{self.name}_{self.content_hash}"


class FeatureRegistry:
    """Dynamic feature definition registry.

    Stores immutable feature definitions. Supports registration,
    lookup, and iteration.
    """

    def __init__(self) -> None:
        self._features: dict[str, FeatureDefinition] = {}

    def register(self, feature: FeatureDefinition) -> str:
        """Register a feature definition. Returns feature_id."""
        fid = feature.feature_id
        if fid in self._features:
            return fid  # Idempotent
        self._features[fid] = feature
        return fid

    def register_many(self, features: list[FeatureDefinition]) -> list[str]:
        """Register multiple features. Returns their IDs."""
        return [self.register(f) for f in features]

    def get(self, feature_id: str) -> Optional[FeatureDefinition]:
        """Get a feature definition by ID."""
        return self._features.get(feature_id)

    def get_by_name(self, name: str) -> list[FeatureDefinition]:
        """Get all feature definitions matching a name."""
        return [f for f in self._features.values() if f.name == name]

    def all_features(self) -> list[FeatureDefinition]:
        """Get all registered features."""
        return list(self._features.values())

    def features_for_market(self, market: str) -> list[FeatureDefinition]:
        """Get features applicable to a specific market."""
        return [
            f for f in self._features.values()
            if not f.market_applicability or market in f.market_applicability
        ]

    @property
    def count(self) -> int:
        return len(self._features)

    def content_hash(self) -> str:
        """Hash of the entire registry (for versioning)."""
        ids = sorted(self._features.keys())
        canonical = json.dumps(ids, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class FeatureTransformEngine:
    """Computes feature values from raw match data.

    Strictly enforces temporal causality: rolling features at time T
    use only data from matches BEFORE T. Never includes the current match.
    """

    def compute_features(
        self,
        matches: list[dict[str, Any]],
        features: list[FeatureDefinition],
    ) -> list[dict[str, float]]:
        """Compute feature values for each match.

        Args:
            matches: List of match dicts sorted by date_unix.
            features: Feature definitions to compute.

        Returns:
            List of dicts, one per match, with feature_id → value.
            Index i corresponds to matches[i].
        """
        n = len(matches)
        results: list[dict[str, float]] = [{} for _ in range(n)]

        for feat in features:
            values = self._compute_single(matches, feat)
            for i, val in enumerate(values):
                if val is not None and not np.isnan(val):
                    results[i][feat.feature_id] = val

        return results

    def _compute_single(
        self,
        matches: list[dict[str, Any]],
        feat: FeatureDefinition,
    ) -> list[Optional[float]]:
        """Compute a single feature across all matches."""
        transform = feat.transform
        params = feat.params

        if transform == TransformType.RAW:
            return self._compute_raw(matches, feat)
        elif transform == TransformType.ROLLING_MEAN:
            return self._compute_rolling(matches, feat, np.mean)
        elif transform == TransformType.ROLLING_STD:
            return self._compute_rolling(matches, feat, np.std)
        elif transform == TransformType.ROLLING_MEDIAN:
            return self._compute_rolling(matches, feat, np.median)
        elif transform == TransformType.EWMA:
            return self._compute_ewma(matches, feat)
        elif transform == TransformType.DIFFERENCE:
            return self._compute_difference(matches, feat)
        elif transform == TransformType.RATIO:
            return self._compute_ratio(matches, feat)
        elif transform == TransformType.Z_SCORE:
            return self._compute_zscore(matches, feat)
        elif transform == TransformType.LEAGUE_NORMALIZE:
            return self._compute_league_normalize(matches, feat)
        elif transform == TransformType.HOME_AWAY_NORMALIZE:
            return self._compute_home_away_normalize(matches, feat)
        elif transform == TransformType.INTERACTION:
            return self._compute_interaction(matches, feat)
        elif transform == TransformType.TREND:
            return self._compute_trend(matches, feat)
        elif transform == TransformType.MOMENTUM:
            return self._compute_momentum(matches, feat)
        elif transform == TransformType.VOLATILITY:
            return self._compute_volatility(matches, feat)
        else:
            return [None] * len(matches)

    def _compute_raw(
        self, matches: list[dict], feat: FeatureDefinition
    ) -> list[Optional[float]]:
        """Extract raw field value (no transformation)."""
        field_name = feat.source_fields[0]
        return [
            float(m.get(field_name)) if m.get(field_name) is not None else None
            for m in matches
        ]

    def _compute_rolling(
        self,
        matches: list[dict],
        feat: FeatureDefinition,
        agg_fn: Callable,
    ) -> list[Optional[float]]:
        """Compute rolling aggregate with strict temporal causality.

        For team-level features: builds per-team history and computes
        rolling stats using only PRIOR matches (not current).
        """
        field_name = feat.source_fields[0]
        window = feat.params.get("window", 5)
        team_field = feat.params.get("team_field", "home_team")
        min_periods = feat.params.get("min_periods", 3)

        # Build per-team history
        team_history: dict[str, list[float]] = {}
        results: list[Optional[float]] = []

        for m in matches:
            team = m.get(team_field, "")
            val = m.get(field_name)

            # Compute BEFORE adding current match (temporal causality)
            history = team_history.get(team, [])
            if len(history) >= min_periods:
                recent = history[-window:] if window else history
                results.append(float(agg_fn(recent)))
            else:
                results.append(None)

            # NOW add current match to history
            if val is not None:
                if team not in team_history:
                    team_history[team] = []
                team_history[team].append(float(val))

        return results

    def _compute_ewma(
        self, matches: list[dict], feat: FeatureDefinition
    ) -> list[Optional[float]]:
        """Exponentially weighted moving average with causality."""
        field_name = feat.source_fields[0]
        alpha = feat.params.get("alpha", 0.3)
        team_field = feat.params.get("team_field", "home_team")
        min_periods = feat.params.get("min_periods", 3)

        team_ewma: dict[str, float] = {}
        team_count: dict[str, int] = {}
        results: list[Optional[float]] = []

        for m in matches:
            team = m.get(team_field, "")
            val = m.get(field_name)

            # Read BEFORE update
            count = team_count.get(team, 0)
            if count >= min_periods:
                results.append(team_ewma.get(team))
            else:
                results.append(None)

            # Update
            if val is not None:
                v = float(val)
                if team in team_ewma:
                    team_ewma[team] = alpha * v + (1 - alpha) * team_ewma[team]
                else:
                    team_ewma[team] = v
                team_count[team] = count + 1

        return results

    def _compute_difference(
        self, matches: list[dict], feat: FeatureDefinition
    ) -> list[Optional[float]]:
        """Compute difference between two fields: field_a - field_b."""
        field_a, field_b = feat.source_fields[0], feat.source_fields[1]
        results = []
        for m in matches:
            a, b = m.get(field_a), m.get(field_b)
            if a is not None and b is not None:
                results.append(float(a) - float(b))
            else:
                results.append(None)
        return results

    def _compute_ratio(
        self, matches: list[dict], feat: FeatureDefinition
    ) -> list[Optional[float]]:
        """Compute ratio: field_a / field_b (safe division)."""
        field_a, field_b = feat.source_fields[0], feat.source_fields[1]
        results = []
        for m in matches:
            a, b = m.get(field_a), m.get(field_b)
            if a is not None and b is not None and float(b) != 0:
                results.append(float(a) / float(b))
            else:
                results.append(None)
        return results

    def _compute_zscore(
        self, matches: list[dict], feat: FeatureDefinition
    ) -> list[Optional[float]]:
        """Z-score relative to expanding history (before current match)."""
        field_name = feat.source_fields[0]
        min_periods = feat.params.get("min_periods", 10)

        history: list[float] = []
        results: list[Optional[float]] = []

        for m in matches:
            val = m.get(field_name)

            # Compute BEFORE adding current
            if len(history) >= min_periods:
                mean = np.mean(history)
                std = np.std(history)
                if std > 0 and val is not None:
                    results.append((float(val) - mean) / std)
                else:
                    results.append(None)
            else:
                results.append(None)

            # Add current
            if val is not None:
                history.append(float(val))

        return results

    def _compute_interaction(
        self, matches: list[dict], feat: FeatureDefinition
    ) -> list[Optional[float]]:
        """Compute interaction: field_a * field_b."""
        field_a, field_b = feat.source_fields[0], feat.source_fields[1]
        results = []
        for m in matches:
            a, b = m.get(field_a), m.get(field_b)
            if a is not None and b is not None:
                results.append(float(a) * float(b))
            else:
                results.append(None)
        return results

    def _compute_trend(
        self, matches: list[dict], feat: FeatureDefinition
    ) -> list[Optional[float]]:
        """Linear trend (slope) over rolling window."""
        field_name = feat.source_fields[0]
        window = feat.params.get("window", 5)
        team_field = feat.params.get("team_field", "home_team")
        min_periods = feat.params.get("min_periods", 4)

        team_history: dict[str, list[float]] = {}
        results: list[Optional[float]] = []

        for m in matches:
            team = m.get(team_field, "")
            val = m.get(field_name)

            history = team_history.get(team, [])
            if len(history) >= min_periods:
                recent = history[-window:]
                x = np.arange(len(recent))
                slope = float(np.polyfit(x, recent, 1)[0])
                results.append(slope)
            else:
                results.append(None)

            if val is not None:
                if team not in team_history:
                    team_history[team] = []
                team_history[team].append(float(val))

        return results

    def _compute_momentum(
        self, matches: list[dict], feat: FeatureDefinition
    ) -> list[Optional[float]]:
        """Momentum: difference between recent mean and longer-term mean."""
        field_name = feat.source_fields[0]
        short_window = feat.params.get("short_window", 3)
        long_window = feat.params.get("long_window", 10)
        team_field = feat.params.get("team_field", "home_team")

        team_history: dict[str, list[float]] = {}
        results: list[Optional[float]] = []

        for m in matches:
            team = m.get(team_field, "")
            val = m.get(field_name)

            history = team_history.get(team, [])
            if len(history) >= long_window:
                short_mean = np.mean(history[-short_window:])
                long_mean = np.mean(history[-long_window:])
                results.append(float(short_mean - long_mean))
            else:
                results.append(None)

            if val is not None:
                if team not in team_history:
                    team_history[team] = []
                team_history[team].append(float(val))

        return results


    def _compute_league_normalize(
        self, matches: list[dict], feat: FeatureDefinition
    ) -> list[Optional[float]]:
        """Normalize a field relative to the expanding league average.

        For each match, computes (value - league_mean) / league_std using
        only data from PRIOR matches in the same league.

        Params:
            min_periods: minimum league-level observations before normalizing.
            league_field: field identifying the league (default: "league_id").
        """
        field_name = feat.source_fields[0]
        min_periods = feat.params.get("min_periods", 20)
        league_field = feat.params.get("league_field", "league_id")

        league_history: dict[str, list[float]] = {}
        results: list[Optional[float]] = []

        for m in matches:
            league = str(m.get(league_field, "default"))
            val = m.get(field_name)

            # Compute BEFORE adding current match
            history = league_history.get(league, [])
            if len(history) >= min_periods and val is not None:
                mean = np.mean(history)
                std = np.std(history)
                if std > 0:
                    results.append((float(val) - mean) / std)
                else:
                    results.append(0.0)
            else:
                results.append(None)

            # Add current value to league history
            if val is not None:
                if league not in league_history:
                    league_history[league] = []
                league_history[league].append(float(val))

        return results

    def _compute_home_away_normalize(
        self, matches: list[dict], feat: FeatureDefinition
    ) -> list[Optional[float]]:
        """Normalize a field relative to expanding home/away averages.

        Computes (value - venue_mean) / venue_std where venue_mean is the
        mean of the same field across all prior matches at the same venue
        (home or away) in the dataset.

        This isolates whether a value is unusually high/low for a home or
        away team, controlling for the known home/away bias.

        Params:
            min_periods: minimum observations before normalizing.
            venue_field: field identifying venue ("home_team" or "away_team").
                         If "home_team", normalizes relative to home averages.
        """
        field_name = feat.source_fields[0]
        min_periods = feat.params.get("min_periods", 20)
        venue_field = feat.params.get("venue_field", "home_team")

        # Track separate histories for home and away context
        # "home" history = all values observed when a team was at home
        # "away" history = all values observed when a team was away
        venue_history: dict[str, list[float]] = {}  # venue_key → values
        results: list[Optional[float]] = []

        for m in matches:
            # Determine venue context: we use the venue_field to decide
            # whether this match contributes to "home" or "away" pool
            venue_key = "home" if venue_field == "home_team" else "away"
            val = m.get(field_name)

            # Compute BEFORE adding current
            history = venue_history.get(venue_key, [])
            if len(history) >= min_periods and val is not None:
                mean = np.mean(history)
                std = np.std(history)
                if std > 0:
                    results.append((float(val) - mean) / std)
                else:
                    results.append(0.0)
            else:
                results.append(None)

            # Add current value to venue history
            if val is not None:
                if venue_key not in venue_history:
                    venue_history[venue_key] = []
                venue_history[venue_key].append(float(val))

        return results

    def _compute_volatility(
        self, matches: list[dict], feat: FeatureDefinition
    ) -> list[Optional[float]]:
        """Rolling standard deviation of a field for a team (volatility).

        Measures how variable a metric is over the rolling window.
        High volatility = unpredictable team. Uses only PRIOR matches.

        Params:
            window: lookback window (default 5).
            team_field: which team to track (default "home_team").
            min_periods: minimum observations (default 4).
        """
        field_name = feat.source_fields[0]
        window = feat.params.get("window", 5)
        team_field = feat.params.get("team_field", "home_team")
        min_periods = feat.params.get("min_periods", 4)

        team_history: dict[str, list[float]] = {}
        results: list[Optional[float]] = []

        for m in matches:
            team = m.get(team_field, "")
            val = m.get(field_name)

            # Compute BEFORE adding current match
            history = team_history.get(team, [])
            if len(history) >= min_periods:
                recent = history[-window:]
                results.append(float(np.std(recent, ddof=1)))
            else:
                results.append(None)

            # Add current value
            if val is not None:
                if team not in team_history:
                    team_history[team] = []
                team_history[team].append(float(val))

        return results
