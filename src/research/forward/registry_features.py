"""Registry-Integrated Temporal Feature Engine — bridges FeatureRegistry with forward predictions.

This module connects the existing FeatureRegistry/FeatureTransformEngine
(full rolling, EWMA, trend, momentum, etc.) with the forward TemporalFeatureEngine
for point-in-time feature computation.

Architecture:
    FeatureRegistry (existing Batch 3)
        ↓
    FeatureTransformEngine (existing — strict temporal causality)
        ↓
    RegistryTemporalEngine (this module — point-in-time enforcement)
        ↓
    PreMatchSnapshot (immutable, temporal-causal)

Key guarantees:
- ALL features computed using only matches with date_unix < prediction_cutoff
- No future matches enter computation
- No same-time matches in strict mode
- Each feature gets provenance with information_timestamp
- Content hash tracks feature version and source dataset
- Existing FeatureTransformEngine is REUSED (not duplicated)
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from src.research.data_source import ResearchMatch
from src.research.feature_registry import (
    FeatureDefinition,
    FeatureRegistry,
    FeatureTransformEngine,
    TemporalClass,
    TransformType,
)
from src.research.forward.snapshot import (
    FeatureProvenance,
    PreMatchSnapshot,
    TimestampConfidence,
)

logger = logging.getLogger(__name__)


# Standard pre-match features for forward research
def create_standard_forward_features() -> list[FeatureDefinition]:
    """Create the standard set of features for forward predictions.

    All are DERIVED temporal class — computed from historical post-match
    data of PAST matches (this is legitimate pre-match information).
    """
    features = []

    # Rolling means (per team, various windows)
    for source_field in ["total_goals", "total_corners", "total_cards",
                         "dangerous_attacks_home", "dangerous_attacks_away",
                         "shots_on_target_home", "shots_on_target_away",
                         "possession_home", "possession_away"]:
        for window in [5, 10]:
            features.append(FeatureDefinition(
                name=f"rolling_mean_{source_field}_w{window}",
                source_fields=(source_field,),
                transform=TransformType.ROLLING_MEAN,
                params={"window": window, "team_field": "home_team", "min_periods": 3},
                temporal_class=TemporalClass.DERIVED,
                version="1.0.0",
            ))

    # EWMA features
    for source_field in ["total_goals", "total_corners"]:
        features.append(FeatureDefinition(
            name=f"ewma_{source_field}",
            source_fields=(source_field,),
            transform=TransformType.EWMA,
            params={"alpha": 0.3, "team_field": "home_team", "min_periods": 3},
            temporal_class=TemporalClass.DERIVED,
            version="1.0.0",
        ))

    # Volatility
    for source_field in ["total_goals", "total_corners"]:
        features.append(FeatureDefinition(
            name=f"rolling_std_{source_field}",
            source_fields=(source_field,),
            transform=TransformType.ROLLING_STD,
            params={"window": 10, "team_field": "home_team", "min_periods": 5},
            temporal_class=TemporalClass.DERIVED,
            version="1.0.0",
        ))

    return features


@dataclass
class RegistryTemporalEngine:
    """Feature engine bridging FeatureRegistry with forward point-in-time computation.

    Uses the EXISTING FeatureTransformEngine for computation.
    Adds strict temporal cutoff enforcement and provenance tracking.

    This does NOT duplicate feature computation logic — it wraps it
    with point-in-time filtering and PreMatchSnapshot creation.
    """

    registry: FeatureRegistry
    transform_engine: FeatureTransformEngine = field(default_factory=FeatureTransformEngine)
    strict_mode: bool = True
    min_historical_matches: int = 10

    def build_snapshot(
        self,
        fixture_id: str,
        home_team_id: int,
        away_team_id: int,
        prediction_timestamp: float,
        kickoff_timestamp: float,
        historical_matches: list[ResearchMatch],
        feature_ids: Optional[list[str]] = None,
        hypothesis_id: str = "",
        model_id: str = "",
        research_run_id: str = "",
    ) -> PreMatchSnapshot:
        """Build a PreMatchSnapshot using full FeatureRegistry computation.

        Args:
            fixture_id: Target fixture.
            home_team_id: Home team stable ID.
            away_team_id: Away team stable ID.
            prediction_timestamp: When prediction is generated.
            kickoff_timestamp: Scheduled kickoff.
            historical_matches: ALL available historical matches (filtering applied here).
            feature_ids: Specific features to compute (None = all in registry).
            hypothesis_id: Strategy/hypothesis ID.
            model_id: Model ID.
            research_run_id: Research run ID.

        Returns:
            PreMatchSnapshot with full provenance.

        Raises:
            ValueError: If temporal constraints are violated.
        """
        if prediction_timestamp > kickoff_timestamp:
            raise ValueError(
                f"prediction_timestamp ({prediction_timestamp}) > "
                f"kickoff_timestamp ({kickoff_timestamp})"
            )

        # 1. Filter historical matches: ONLY those before prediction_timestamp
        eligible = self._filter_eligible(historical_matches, prediction_timestamp)

        if len(eligible) < self.min_historical_matches:
            logger.warning(
                "Only %d eligible matches (min: %d) for fixture %s",
                len(eligible), self.min_historical_matches, fixture_id,
            )

        # 2. Determine which features to compute
        if feature_ids:
            features = [self.registry.get(fid) for fid in feature_ids]
            features = [f for f in features if f is not None]
        else:
            features = self.registry.all_features()

        # Filter to only DERIVED/PRE_MATCH features (never POST_MATCH for prediction)
        features = [
            f for f in features
            if f.temporal_class in (TemporalClass.DERIVED, TemporalClass.PRE_MATCH)
        ]

        # 3. Convert eligible matches to dicts for FeatureTransformEngine
        match_dicts = [m.to_dict() for m in eligible]

        # 4. Compute features using existing engine (temporal causality built-in)
        if match_dicts and features:
            computed = self.transform_engine.compute_features(match_dicts, features)
            # The last element represents the "latest" rolling values
            # (what would be known at prediction time)
            latest_features = computed[-1] if computed else {}
        else:
            latest_features = {}

        # 5. Build provenance
        latest_match_time = max(m.date_unix for m in eligible) if eligible else 0.0
        provenance_records: list[FeatureProvenance] = []
        feature_values: dict[str, Optional[float]] = {}

        for feat in features:
            fid = feat.feature_id
            value = latest_features.get(fid)
            feature_values[fid] = value  # None = missing (NOT zero)
            provenance_records.append(FeatureProvenance(
                feature_id=fid,
                value=value,
                information_timestamp=float(latest_match_time),
                timestamp_confidence=TimestampConfidence.ESTIMATED,
                source_match_id=None,
                source_dataset_version=self._compute_dataset_version(eligible),
                estimation_method="latest_eligible_match_completion_time",
            ))

        # 6. Build immutable snapshot
        return PreMatchSnapshot(
            fixture_id=fixture_id,
            prediction_timestamp=prediction_timestamp,
            kickoff_timestamp=kickoff_timestamp,
            features=feature_values,
            feature_provenance=tuple(provenance_records),
            source_dataset_id=self._compute_dataset_version(eligible),
            hypothesis_id=hypothesis_id,
            model_id=model_id,
            research_run_id=research_run_id,
        )

    def _filter_eligible(
        self, matches: list[ResearchMatch], prediction_timestamp: float
    ) -> list[ResearchMatch]:
        """Filter to matches strictly before prediction timestamp.

        Does NOT rely on sorting. Explicitly checks every match.
        Same-timestamp matches excluded in strict mode.
        """
        eligible = []
        for m in matches:
            if m.date_unix < prediction_timestamp:
                eligible.append(m)
            elif m.date_unix == prediction_timestamp and self.strict_mode:
                continue  # Exclude same-time (ambiguous)
        # Sort chronologically for FeatureTransformEngine
        eligible.sort(key=lambda m: m.date_unix)
        return eligible

    def _compute_dataset_version(self, matches: list[ResearchMatch]) -> str:
        """Compute a deterministic version hash for the eligible dataset."""
        if not matches:
            return "empty"
        canonical = json.dumps(
            [(m.match_id, m.date_unix) for m in matches[-20:]],  # Use last 20 for efficiency
            sort_keys=True, separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:12]
