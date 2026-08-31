"""XMetric integration adapter for the research laboratory.

Bridges the existing XMetricEngine (xC, xB, xO) into the research
laboratory's feature system WITHOUT modifying the engine itself.

Architecture:
    XMetricEngine (FROZEN)
        ↓ adapter
    FeatureRegistry
        ↓
    Research Laboratory

This adapter:
- Converts ResearchMatch data → DataFrame for XMetricEngine
- Runs XMetricEngine.compute_all()
- Extracts xC, xB, xO as registered research features
- Maintains provenance: each XMetric has a FeatureDefinition with
  source_fields, version, temporal_class, and content_hash

The adapter does NOT modify XMetricEngine internals.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.engine.analysis.xmetrics import XMetricCoefficients, XMetricEngine
from src.research.data_source import ResearchMatch
from src.research.feature_registry import (
    FeatureDefinition,
    FeatureRegistry,
    TemporalClass,
    TransformType,
)


# ═══════════════════════════════════════════════════════════════
# XMETRIC FEATURE FAMILY
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class XMetricProvenance:
    """Provenance record for an XMetric computation."""

    metric_name: str  # e.g. "xC", "xB", "xO"
    version: str
    coefficients: dict[str, float]
    timestamp_semantics: str  # Describes temporal guarantees
    input_fields: tuple[str, ...]

    @property
    def content_hash(self) -> str:
        canonical = json.dumps({
            "metric": self.metric_name,
            "version": self.version,
            "coefficients": self.coefficients,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# XMetric provenance definitions
_XC_PROVENANCE = XMetricProvenance(
    metric_name="xC",
    version="1.0.0",
    coefficients={"alpha": 0.45, "beta": 0.30, "gamma": 0.25},
    timestamp_semantics="POST_MATCH: computed from match statistics available after kickoff",
    input_fields=(
        "attacks_home", "attacks_away",
        "dangerous_attacks_home", "dangerous_attacks_away",
        "shots_off_target_home", "shots_off_target_away",
        "corners_avg_against_home", "corners_avg_against_away",
    ),
)

_XB_PROVENANCE = XMetricProvenance(
    metric_name="xB",
    version="1.0.0",
    coefficients={"delta": 0.02},
    timestamp_semantics="POST_MATCH: uses fouls, possession, referee stats from completed matches",
    input_fields=(
        "fouls_home", "fouls_away",
        "possession_home", "possession_away",
        "referee_cards_per_match",
        "xg_against_home", "xg_against_away",
    ),
)

_XO_PROVENANCE = XMetricProvenance(
    metric_name="xO",
    version="1.1.0",
    coefficients={"eta": 1.0},
    timestamp_semantics="POST_MATCH: uses offsides and corners_avg_against; expanding-window baseline is temporal-leak-free",
    input_fields=(
        "offsides_home", "offsides_away",
        "corners_avg_against_home", "corners_avg_against_away",
    ),
)


# ═══════════════════════════════════════════════════════════════
# ADAPTER
# ═══════════════════════════════════════════════════════════════


class XMetricAdapter:
    """Adapts XMetricEngine output into the research feature system.

    Usage:
        adapter = XMetricAdapter()
        adapter.register_features(registry)
        xmetric_values = adapter.compute(matches)
        # xmetric_values is a list[dict[str, float]] aligned with matches
    """

    # Feature definitions for XMetrics in the research system
    XMETRIC_FEATURES: list[FeatureDefinition] = [
        FeatureDefinition(
            name="home_xC",
            source_fields=_XC_PROVENANCE.input_fields,
            transform=TransformType.RAW,
            temporal_class=TemporalClass.POST_MATCH,
            market_applicability=("CORNERS_TOTAL",),
            description="XMetric Corner Pressure (home): α·(DA/A) + β·SOT_off + γ·opp_corners_avg",
        ),
        FeatureDefinition(
            name="away_xC",
            source_fields=_XC_PROVENANCE.input_fields,
            transform=TransformType.RAW,
            temporal_class=TemporalClass.POST_MATCH,
            market_applicability=("CORNERS_TOTAL",),
            description="XMetric Corner Pressure (away): α·(DA/A) + β·SOT_off + γ·opp_corners_avg",
        ),
        FeatureDefinition(
            name="home_xB",
            source_fields=_XB_PROVENANCE.input_fields,
            transform=TransformType.RAW,
            temporal_class=TemporalClass.POST_MATCH,
            market_applicability=("CARDS_TOTAL",),
            description="XMetric Booking Intensity (home): fouls × ref_cpf + δ·(100-poss)·opp_dribbles",
        ),
        FeatureDefinition(
            name="away_xB",
            source_fields=_XB_PROVENANCE.input_fields,
            transform=TransformType.RAW,
            temporal_class=TemporalClass.POST_MATCH,
            market_applicability=("CARDS_TOTAL",),
            description="XMetric Booking Intensity (away): fouls × ref_cpf + δ·(100-poss)·opp_dribbles",
        ),
        FeatureDefinition(
            name="home_xO",
            source_fields=_XO_PROVENANCE.input_fields,
            transform=TransformType.RAW,
            temporal_class=TemporalClass.POST_MATCH,
            market_applicability=("OFFSIDES_TOTAL",),
            description="XMetric Offsides Trap (home): η·offsides × (opp_HLI/baseline)",
        ),
        FeatureDefinition(
            name="away_xO",
            source_fields=_XO_PROVENANCE.input_fields,
            transform=TransformType.RAW,
            temporal_class=TemporalClass.POST_MATCH,
            market_applicability=("OFFSIDES_TOTAL",),
            description="XMetric Offsides Trap (away): η·offsides × (opp_HLI/baseline)",
        ),
    ]

    def __init__(self, coefficients: Optional[XMetricCoefficients] = None) -> None:
        self._engine = XMetricEngine(coefficients)
        self._coefficients = coefficients or XMetricCoefficients()

    @property
    def provenance(self) -> dict[str, XMetricProvenance]:
        """Return provenance records for all XMetrics."""
        return {
            "xC": _XC_PROVENANCE,
            "xB": _XB_PROVENANCE,
            "xO": _XO_PROVENANCE,
        }

    def register_features(self, registry: FeatureRegistry) -> list[str]:
        """Register all XMetric features in the research registry.

        Returns list of registered feature IDs.
        """
        return registry.register_many(self.XMETRIC_FEATURES)

    def compute(self, matches: list[ResearchMatch]) -> list[dict[str, float]]:
        """Compute XMetrics for research matches.

        Converts ResearchMatch records to a DataFrame, runs XMetricEngine,
        and returns feature values aligned with the input list.

        Args:
            matches: List of ResearchMatch records.

        Returns:
            List of dicts (one per match) with feature_id → value.
            Indices align with input matches.
        """
        if not matches:
            return []

        # Convert to DataFrame
        df = self._matches_to_dataframe(matches)

        # Run XMetricEngine
        df = self._engine.compute_all(df)

        # Extract results as feature dicts
        return self._extract_feature_values(df)

    def compute_from_dicts(self, match_dicts: list[dict[str, Any]]) -> list[dict[str, float]]:
        """Compute XMetrics from raw match dicts (convenience method).

        Same as compute() but accepts dict representations.
        """
        if not match_dicts:
            return []

        df = pd.DataFrame(match_dicts)
        df = self._engine.compute_all(df)
        return self._extract_feature_values(df)

    def _matches_to_dataframe(self, matches: list[ResearchMatch]) -> pd.DataFrame:
        """Convert ResearchMatch records to a pandas DataFrame.

        Maps ResearchMatch fields to the column names XMetricEngine expects.
        """
        records = []
        for m in matches:
            record = {
                "date_unix": m.date_unix,
                "attacks_home": m.attacks_home,
                "attacks_away": m.attacks_away,
                "dangerous_attacks_home": m.dangerous_attacks_home,
                "dangerous_attacks_away": m.dangerous_attacks_away,
                "shots_off_target_home": m.shots_off_target_home,
                "shots_off_target_away": m.shots_off_target_away,
                "fouls_home": m.fouls_home,
                "fouls_away": m.fouls_away,
                "possession_home": m.possession_home,
                "possession_away": m.possession_away,
                "offsides_home": m.offsides_home,
                "offsides_away": m.offsides_away,
            }
            records.append(record)

        return pd.DataFrame(records)

    def _extract_feature_values(self, df: pd.DataFrame) -> list[dict[str, float]]:
        """Extract computed XMetric columns as feature value dicts."""
        xmetric_cols = ["home_xC", "away_xC", "home_xB", "away_xB", "home_xO", "away_xO"]
        feature_id_map = {feat.name: feat.feature_id for feat in self.XMETRIC_FEATURES}

        results: list[dict[str, float]] = []
        for i in range(len(df)):
            row: dict[str, float] = {}
            for col in xmetric_cols:
                if col in df.columns:
                    val = df[col].iloc[i]
                    if val is not None and not np.isnan(val):
                        fid = feature_id_map.get(col)
                        if fid:
                            row[fid] = float(val)
            results.append(row)

        return results


# ═══════════════════════════════════════════════════════════════
# DERIVED XMETRIC FEATURES
# ═══════════════════════════════════════════════════════════════

def create_xmetric_rolling_features(
    windows: tuple[int, ...] = (3, 5, 10),
) -> list[FeatureDefinition]:
    """Create rolling mean features from XMetric outputs.

    These are DERIVED features — they use historical XMetric values
    (from prior matches) to compute a team-level rolling average.
    This is the correct way to use XMetrics as pre-match features.

    Example: home_xC_avg_5 = rolling 5-match mean of home_xC for the home team.
    """
    features: list[FeatureDefinition] = []
    xmetric_fields = [
        ("home_xC", ("CORNERS_TOTAL",)),
        ("away_xC", ("CORNERS_TOTAL",)),
        ("home_xB", ("CARDS_TOTAL",)),
        ("away_xB", ("CARDS_TOTAL",)),
        ("home_xO", ("OFFSIDES_TOTAL",)),
        ("away_xO", ("OFFSIDES_TOTAL",)),
    ]

    for field_name, markets in xmetric_fields:
        side = "home" if field_name.startswith("home") else "away"
        team_field = f"{side}_team"

        for window in windows:
            features.append(FeatureDefinition(
                name=f"{field_name}_avg_{window}",
                source_fields=(field_name,),
                transform=TransformType.ROLLING_MEAN,
                params={"window": window, "team_field": team_field, "min_periods": 3},
                temporal_class=TemporalClass.DERIVED,
                market_applicability=markets,
                description=(
                    f"Rolling {window}-match mean of {field_name}. "
                    f"Derived from historical XMetric values (no leakage)."
                ),
            ))

    return features
