"""Dataset, Feature, and Model provenance types.

These types establish the reproducibility chain:
    DatasetVersion → FeatureVersion → ModelVersion

Each captures exactly what data/config was used so that any result
can be reproduced from first principles.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class DatasetVersion:
    """Immutable snapshot of a dataset used for computation.

    Captures the identity of input data so results can be traced
    back to exactly which matches/observations were used.

    Attributes:
        dataset_id: Unique identifier for this dataset snapshot.
        source: Origin of the data (e.g., "footystats", "synthetic", "mock").
        league_id: League identifier (e.g., 4759 for Premier League).
        season: Season string (e.g., "2023", "2023-24").
        n_matches: Number of matches in the dataset.
        date_range_start: Earliest match date_unix in the dataset.
        date_range_end: Latest match date_unix in the dataset.
        content_hash: SHA-256 hash of the dataset content.
        created_at: ISO 8601 timestamp when this version was created.
    """

    dataset_id: str
    source: str
    league_id: int
    season: str
    n_matches: int
    date_range_start: int
    date_range_end: int
    content_hash: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "dataset_id": self.dataset_id,
            "source": self.source,
            "league_id": self.league_id,
            "season": self.season,
            "n_matches": self.n_matches,
            "date_range_start": self.date_range_start,
            "date_range_end": self.date_range_end,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
        }

    @staticmethod
    def compute_content_hash(match_ids: list[int]) -> str:
        """Compute deterministic hash from sorted match IDs.

        Args:
            match_ids: List of match identifiers in the dataset.

        Returns:
            SHA-256 hex digest of the sorted, JSON-encoded match ID list.
        """
        canonical = json.dumps(sorted(match_ids), separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class FeatureVersion:
    """Immutable record of feature computation configuration.

    Captures which feature calculators and parameters were used,
    enabling exact reproduction of feature vectors from raw data.

    Attributes:
        feature_version_id: Unique identifier for this feature config.
        dataset_id: The DatasetVersion this was computed from.
        xg_rolling_window: Window size for xG efficiency calculator.
        form_rolling_window: Window size for rolling form calculator.
        referee_min_matches: Minimum matches before referee gets own stats.
        xmetric_coefficients: XMetricEngine coefficient values (if xMetrics used).
        content_hash: SHA-256 of the feature configuration.
        created_at: ISO 8601 timestamp.
    """

    feature_version_id: str
    dataset_id: str
    xg_rolling_window: int
    form_rolling_window: int
    referee_min_matches: int
    xmetric_coefficients: dict[str, float] | None
    content_hash: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "feature_version_id": self.feature_version_id,
            "dataset_id": self.dataset_id,
            "xg_rolling_window": self.xg_rolling_window,
            "form_rolling_window": self.form_rolling_window,
            "referee_min_matches": self.referee_min_matches,
            "xmetric_coefficients": self.xmetric_coefficients,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
        }

    @staticmethod
    def compute_content_hash(
        dataset_id: str,
        xg_rolling_window: int,
        form_rolling_window: int,
        referee_min_matches: int,
        xmetric_coefficients: dict[str, float] | None = None,
    ) -> str:
        """Compute deterministic hash of feature configuration.

        Args:
            dataset_id: Parent dataset identifier.
            xg_rolling_window: xG rolling window size.
            form_rolling_window: Form rolling window size.
            referee_min_matches: Referee minimum match threshold.
            xmetric_coefficients: Optional xMetric coefficient dict.

        Returns:
            SHA-256 hex digest of the canonical JSON representation.
        """
        canonical = json.dumps({
            "dataset_id": dataset_id,
            "xg_rolling_window": xg_rolling_window,
            "form_rolling_window": form_rolling_window,
            "referee_min_matches": referee_min_matches,
            "xmetric_coefficients": xmetric_coefficients,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ModelVersion:
    """Immutable record of the model/strategy evaluation configuration.

    In the current system, the "model" is the strategy evaluation logic
    (condition matching + walk-forward parameters). This type captures
    the full evaluation context for reproducibility.

    Attributes:
        model_version_id: Unique identifier.
        strategy_id: Parent strategy identifier (from StrategyIdentity).
        strategy_version: Strategy version number.
        strategy_content_hash: SHA-256 of the strategy definition.
        feature_version_id: The FeatureVersion this model was evaluated against.
        train_window: Walk-forward training window size.
        test_window: Walk-forward test window size.
        step_size: Walk-forward step size.
        min_odds: Minimum acceptable odds filter.
        max_odds: Maximum acceptable odds filter.
        content_hash: SHA-256 of the full model configuration.
        created_at: ISO 8601 timestamp.
    """

    model_version_id: str
    strategy_id: str
    strategy_version: int
    strategy_content_hash: str
    feature_version_id: str
    train_window: int
    test_window: int
    step_size: int
    min_odds: float
    max_odds: float
    content_hash: str
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "model_version_id": self.model_version_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "strategy_content_hash": self.strategy_content_hash,
            "feature_version_id": self.feature_version_id,
            "train_window": self.train_window,
            "test_window": self.test_window,
            "step_size": self.step_size,
            "min_odds": self.min_odds,
            "max_odds": self.max_odds,
            "content_hash": self.content_hash,
            "created_at": self.created_at,
        }

    @staticmethod
    def compute_content_hash(
        strategy_content_hash: str,
        feature_version_id: str,
        train_window: int,
        test_window: int,
        step_size: int,
        min_odds: float,
        max_odds: float,
    ) -> str:
        """Compute deterministic hash of model configuration.

        Returns:
            SHA-256 hex digest.
        """
        canonical = json.dumps({
            "strategy_content_hash": strategy_content_hash,
            "feature_version_id": feature_version_id,
            "train_window": train_window,
            "test_window": test_window,
            "step_size": step_size,
            "min_odds": min_odds,
            "max_odds": max_odds,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
