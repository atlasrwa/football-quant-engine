"""Feature family system for the research laboratory.

Organizes features into logical families for bounded candidate generation.
Feature families are organizational categories, NOT assumptions about
predictive power. They enable:

- Market-specific candidate search (prioritize relevant families)
- Combinatorial explosion prevention (limit cross-family interactions)
- Discovery structure (what to combine with what)

The system does NOT assume any family is predictive.
Discovery must independently determine predictive value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from src.research.feature_registry import FeatureDefinition, FeatureRegistry


class FeatureFamily(Enum):
    """Organizational categories for research features."""

    ATTACKING = "ATTACKING"
    SHOOTING = "SHOOTING"
    CORNERS = "CORNERS"
    CARDS = "CARDS"
    OFFSIDES = "OFFSIDES"
    POSSESSION = "POSSESSION"
    DISCIPLINE = "DISCIPLINE"
    TEMPO = "TEMPO"
    FORM = "FORM"
    HOME_AWAY = "HOME_AWAY"
    OPPONENT = "OPPONENT"
    LEAGUE = "LEAGUE"
    XMETRICS = "XMETRICS"
    GENERAL = "GENERAL"


# Default mapping: source field prefix → family
_FIELD_FAMILY_MAP: dict[str, FeatureFamily] = {
    "dangerous_attacks": FeatureFamily.ATTACKING,
    "attacks": FeatureFamily.ATTACKING,
    "shots": FeatureFamily.SHOOTING,
    "shots_on_target": FeatureFamily.SHOOTING,
    "shots_off_target": FeatureFamily.SHOOTING,
    "corners": FeatureFamily.CORNERS,
    "yellow_cards": FeatureFamily.CARDS,
    "red_cards": FeatureFamily.CARDS,
    "total_cards": FeatureFamily.CARDS,
    "offsides": FeatureFamily.OFFSIDES,
    "possession": FeatureFamily.POSSESSION,
    "fouls": FeatureFamily.DISCIPLINE,
    "ppda": FeatureFamily.TEMPO,
    "xg": FeatureFamily.FORM,
    "xC": FeatureFamily.XMETRICS,
    "xB": FeatureFamily.XMETRICS,
    "xO": FeatureFamily.XMETRICS,
}

# Default market → prioritized families
_MARKET_FAMILY_PRIORITY: dict[str, list[FeatureFamily]] = {
    "GOALS_TOTAL": [
        FeatureFamily.ATTACKING, FeatureFamily.SHOOTING,
        FeatureFamily.FORM, FeatureFamily.XMETRICS,
    ],
    "HOME_GOALS": [
        FeatureFamily.ATTACKING, FeatureFamily.SHOOTING,
        FeatureFamily.FORM, FeatureFamily.HOME_AWAY,
    ],
    "AWAY_GOALS": [
        FeatureFamily.ATTACKING, FeatureFamily.SHOOTING,
        FeatureFamily.FORM, FeatureFamily.OPPONENT,
    ],
    "CORNERS_TOTAL": [
        FeatureFamily.CORNERS, FeatureFamily.ATTACKING,
        FeatureFamily.SHOOTING, FeatureFamily.POSSESSION,
        FeatureFamily.XMETRICS,
    ],
    "HOME_CORNERS": [
        FeatureFamily.CORNERS, FeatureFamily.ATTACKING,
        FeatureFamily.POSSESSION, FeatureFamily.XMETRICS,
    ],
    "AWAY_CORNERS": [
        FeatureFamily.CORNERS, FeatureFamily.ATTACKING,
        FeatureFamily.POSSESSION, FeatureFamily.XMETRICS,
    ],
    "CARDS_TOTAL": [
        FeatureFamily.CARDS, FeatureFamily.DISCIPLINE,
        FeatureFamily.TEMPO, FeatureFamily.XMETRICS,
    ],
    "HOME_CARDS": [
        FeatureFamily.CARDS, FeatureFamily.DISCIPLINE,
        FeatureFamily.TEMPO,
    ],
    "AWAY_CARDS": [
        FeatureFamily.CARDS, FeatureFamily.DISCIPLINE,
        FeatureFamily.TEMPO,
    ],
    "OFFSIDES_TOTAL": [
        FeatureFamily.OFFSIDES, FeatureFamily.TEMPO,
        FeatureFamily.ATTACKING, FeatureFamily.XMETRICS,
    ],
    "BTTS": [
        FeatureFamily.ATTACKING, FeatureFamily.SHOOTING,
        FeatureFamily.FORM, FeatureFamily.HOME_AWAY,
    ],
    "MATCH_RESULT_1X2": [
        FeatureFamily.FORM, FeatureFamily.ATTACKING,
        FeatureFamily.HOME_AWAY, FeatureFamily.OPPONENT,
    ],
}


@dataclass(frozen=True, slots=True)
class FeatureFamilyAssignment:
    """Assignment of a feature to a family."""

    feature_id: str
    family: FeatureFamily


class FeatureFamilyRegistry:
    """Maps features to families and provides market-aware feature selection.

    Feature families are configurable. The default mapping uses source
    field name heuristics. Custom assignments override defaults.
    """

    def __init__(self) -> None:
        self._assignments: dict[str, FeatureFamily] = {}
        self._market_priorities: dict[str, list[FeatureFamily]] = dict(_MARKET_FAMILY_PRIORITY)

    def assign(self, feature_id: str, family: FeatureFamily) -> None:
        """Assign a feature to a family (overrides auto-detection)."""
        self._assignments[feature_id] = family

    def assign_many(self, assignments: list[FeatureFamilyAssignment]) -> None:
        """Assign multiple features."""
        for a in assignments:
            self._assignments[a.feature_id] = a.family

    def get_family(self, feature: FeatureDefinition) -> FeatureFamily:
        """Get the family for a feature definition.

        Priority:
        1. Explicit assignment by feature_id
        2. Source field name heuristic
        3. GENERAL fallback
        """
        fid = feature.feature_id
        if fid in self._assignments:
            return self._assignments[fid]

        # Heuristic: match source field names
        for source_field in feature.source_fields:
            for prefix, family in _FIELD_FAMILY_MAP.items():
                if prefix in source_field:
                    return family

        # Check feature name
        for prefix, family in _FIELD_FAMILY_MAP.items():
            if prefix in feature.name:
                return family

        return FeatureFamily.GENERAL

    def get_features_by_family(
        self,
        registry: FeatureRegistry,
        family: FeatureFamily,
    ) -> list[FeatureDefinition]:
        """Get all features belonging to a family."""
        return [f for f in registry.all_features() if self.get_family(f) == family]

    def get_market_families(self, market_type: str) -> list[FeatureFamily]:
        """Get prioritized families for a market.

        Returns priority families if configured, otherwise all families.
        """
        return self._market_priorities.get(market_type, list(FeatureFamily))

    def set_market_priority(
        self, market_type: str, families: list[FeatureFamily]
    ) -> None:
        """Set custom family priorities for a market."""
        self._market_priorities[market_type] = families

    def get_market_features(
        self,
        registry: FeatureRegistry,
        market_type: str,
    ) -> list[FeatureDefinition]:
        """Get features prioritized for a specific market.

        Returns features from priority families first, then others.
        """
        priority_families = self.get_market_families(market_type)
        priority_features: list[FeatureDefinition] = []
        other_features: list[FeatureDefinition] = []

        for feat in registry.all_features():
            family = self.get_family(feat)
            if family in priority_families:
                priority_features.append(feat)
            else:
                other_features.append(feat)

        return priority_features + other_features
