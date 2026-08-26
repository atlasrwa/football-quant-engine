"""Pre-Match Feature Snapshot — immutable record of features at prediction time.

Temporal Contract:
    Every feature in the snapshot must satisfy:
    feature_information_timestamp < prediction_timestamp <= kickoff_timestamp

Once created, a snapshot is NEVER updated with later information.
If information changes before kickoff, create a NEW snapshot.

Immutability:
    PreMatchSnapshot is a frozen dataclass. It cannot be mutated after creation.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class TimestampConfidence(Enum):
    """Confidence in the information timestamp of a feature value."""
    EXACT = "EXACT"        # Provider gave exact publication timestamp
    ESTIMATED = "ESTIMATED"  # Timestamp estimated from retrieval/match time
    UNKNOWN = "UNKNOWN"     # No timestamp information available


@dataclass(frozen=True)
class FeatureProvenance:
    """Provenance record for a single feature value.

    Tracks when and how the information was available.
    """
    feature_id: str
    value: Optional[float]  # None = missing/unavailable (NOT zero)
    information_timestamp: float  # When this info became available (Unix)
    timestamp_confidence: TimestampConfidence = TimestampConfidence.ESTIMATED
    source_match_id: Optional[int] = None  # Which match generated this stat
    source_dataset_version: str = ""
    estimation_method: str = ""  # How timestamp was estimated if not EXACT

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "value": self.value,
            "information_timestamp": self.information_timestamp,
            "timestamp_confidence": self.timestamp_confidence.value,
            "source_match_id": self.source_match_id,
            "source_dataset_version": self.source_dataset_version,
            "estimation_method": self.estimation_method,
        }


@dataclass(frozen=True)
class PreMatchSnapshot:
    """Immutable snapshot of pre-match features for a prediction.

    This captures ALL information used to generate a prediction.
    It is frozen at prediction time and NEVER modified afterward.

    Temporal rules:
    - All feature information_timestamps must be < prediction_timestamp
    - prediction_timestamp must be <= kickoff_timestamp
    - No post-match features from this fixture can appear
    - No future match features can appear

    Attributes:
        snapshot_id: Deterministic identity (content hash).
        fixture_id: Which fixture this snapshot is for.
        prediction_timestamp: When the prediction was generated (Unix).
        temporal_cutoff: Latest allowed information time (== prediction_timestamp).
        features: Mapping of feature_id → value (None = unavailable, NOT zero).
        feature_provenance: Per-feature provenance records.
        source_dataset_id: Identity of the historical dataset used.
        source_data_version: Version/hash of the source data.
        hypothesis_id: Which hypothesis/strategy generated this prediction.
        model_id: Which model was used.
        research_run_id: Parent research run.
        kickoff_timestamp: Fixture kickoff time (for validation).
    """
    fixture_id: str
    prediction_timestamp: float
    kickoff_timestamp: float
    features: dict[str, Optional[float]] = field(default_factory=dict)
    feature_provenance: tuple[FeatureProvenance, ...] = ()
    source_dataset_id: str = ""
    source_data_version: str = ""
    hypothesis_id: str = ""
    model_id: str = ""
    research_run_id: str = ""

    def __post_init__(self) -> None:
        """Validate temporal constraints and freeze mutable internals."""
        if self.prediction_timestamp > self.kickoff_timestamp:
            raise ValueError(
                f"prediction_timestamp ({self.prediction_timestamp}) must be "
                f"<= kickoff_timestamp ({self.kickoff_timestamp})"
            )
        # Validate feature provenance timestamps
        for prov in self.feature_provenance:
            if prov.information_timestamp >= self.prediction_timestamp:
                raise ValueError(
                    f"Feature '{prov.feature_id}' information_timestamp "
                    f"({prov.information_timestamp}) must be < "
                    f"prediction_timestamp ({self.prediction_timestamp})"
                )
        # Freeze the features dict to prevent mutation of frozen dataclass internals
        # Use types.MappingProxyType for true immutability
        from types import MappingProxyType
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))

    @property
    def snapshot_id(self) -> str:
        """Deterministic identity based on content."""
        canonical = json.dumps({
            "fixture_id": self.fixture_id,
            "prediction_timestamp": self.prediction_timestamp,
            "hypothesis_id": self.hypothesis_id,
            "model_id": self.model_id,
            "features": {k: v for k, v in sorted(self.features.items())},
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def content_hash(self) -> str:
        """Full content hash for change detection."""
        canonical = json.dumps({
            "fixture_id": self.fixture_id,
            "prediction_timestamp": self.prediction_timestamp,
            "kickoff_timestamp": self.kickoff_timestamp,
            "features": {k: v for k, v in sorted(self.features.items())},
            "source_dataset_id": self.source_dataset_id,
            "hypothesis_id": self.hypothesis_id,
            "model_id": self.model_id,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def temporal_cutoff(self) -> float:
        """Information time boundary. Same as prediction_timestamp."""
        return self.prediction_timestamp

    @property
    def feature_count(self) -> int:
        """Number of non-None features."""
        return sum(1 for v in self.features.values() if v is not None)

    @property
    def missing_count(self) -> int:
        """Number of None (missing) features."""
        return sum(1 for v in self.features.values() if v is None)

    def get_feature(self, feature_id: str) -> Optional[float]:
        """Get a feature value. Returns None if missing (NOT zero)."""
        return self.features.get(feature_id)

    def validate_temporal_integrity(self) -> list[str]:
        """Explicitly validate all temporal constraints.

        Returns list of violations (empty = valid).
        """
        violations: list[str] = []

        if self.prediction_timestamp > self.kickoff_timestamp:
            violations.append(
                f"prediction_timestamp ({self.prediction_timestamp}) > "
                f"kickoff_timestamp ({self.kickoff_timestamp})"
            )

        for prov in self.feature_provenance:
            if prov.information_timestamp >= self.prediction_timestamp:
                violations.append(
                    f"Feature '{prov.feature_id}' info_time "
                    f"({prov.information_timestamp}) >= "
                    f"prediction_time ({self.prediction_timestamp})"
                )

        return violations

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "fixture_id": self.fixture_id,
            "prediction_timestamp": self.prediction_timestamp,
            "kickoff_timestamp": self.kickoff_timestamp,
            "temporal_cutoff": self.temporal_cutoff,
            "features": dict(self.features),
            "feature_count": self.feature_count,
            "missing_count": self.missing_count,
            "source_dataset_id": self.source_dataset_id,
            "source_data_version": self.source_data_version,
            "hypothesis_id": self.hypothesis_id,
            "model_id": self.model_id,
            "research_run_id": self.research_run_id,
            "content_hash": self.content_hash,
        }
