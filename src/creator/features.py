"""Creator-facing feature catalog.

Exposes the REAL feature set from the research pipeline — does not
hardcode a subset. Every feature available to internal models is
available to creators.

Features are derived from raw FootyStats match data. Only PRE_MATCH
and DERIVED (from historical post-match data) features are usable in
live prediction — POST_MATCH features can be used for backtesting but
the creator is warned they cannot be used pre-kickoff.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from src.research.feature_registry import (
    FeatureDefinition,
    FeatureRegistry,
    TemporalClass,
    TransformType,
)
from src.research.xmetric_adapter import XMetricAdapter, create_xmetric_rolling_features


class FeatureCategory(str, Enum):
    """Human-readable feature categories for the creator UI."""
    CORNERS = "corners"
    CARDS = "cards"
    GOALS = "goals"
    SHOTS = "shots"
    POSSESSION = "possession"
    DISCIPLINE = "discipline"
    SET_PIECES = "set_pieces"
    FORM = "form"
    XMETRICS = "xmetrics"


@dataclass(frozen=True)
class CreatorFeature:
    """A feature as presented to creators — enriched with UI metadata."""
    feature_id: str
    name: str
    display_name: str
    description: str
    category: FeatureCategory
    temporal_class: str
    transform: str
    market_applicability: list[str]
    usable_pre_kickoff: bool
    source_fields: list[str]
    params: dict[str, Any]


# ═══════════════════════════════════════════════════════════════
# RAW STATISTICAL FEATURES (from FootyStats match data)
# These are the confirmed fields available from the data source.
# ═══════════════════════════════════════════════════════════════

RAW_STAT_FEATURES: list[dict[str, Any]] = [
    # Corners
    {"name": "home_corners", "source": "team_a_corners", "category": FeatureCategory.CORNERS,
     "display": "Home Corners", "desc": "Total corners taken by home team"},
    {"name": "away_corners", "source": "team_b_corners", "category": FeatureCategory.CORNERS,
     "display": "Away Corners", "desc": "Total corners taken by away team"},
    {"name": "home_fh_corners", "source": "team_a_fh_corners", "category": FeatureCategory.CORNERS,
     "display": "Home First-Half Corners", "desc": "Corners taken by home team in first half"},
    {"name": "away_fh_corners", "source": "team_b_fh_corners", "category": FeatureCategory.CORNERS,
     "display": "Away First-Half Corners", "desc": "Corners taken by away team in first half"},
    # Cards
    {"name": "home_yellow_cards", "source": "team_a_yellow_cards", "category": FeatureCategory.CARDS,
     "display": "Home Yellow Cards", "desc": "Yellow cards received by home team"},
    {"name": "away_yellow_cards", "source": "team_b_yellow_cards", "category": FeatureCategory.CARDS,
     "display": "Away Yellow Cards", "desc": "Yellow cards received by away team"},
    {"name": "home_red_cards", "source": "team_a_red_cards", "category": FeatureCategory.CARDS,
     "display": "Home Red Cards", "desc": "Red cards received by home team"},
    {"name": "away_red_cards", "source": "team_b_red_cards", "category": FeatureCategory.CARDS,
     "display": "Away Red Cards", "desc": "Red cards received by away team"},
    {"name": "home_total_cards", "source": "team_a_cards_num", "category": FeatureCategory.CARDS,
     "display": "Home Total Cards", "desc": "Total bookings (yellow + red) for home team"},
    {"name": "away_total_cards", "source": "team_b_cards_num", "category": FeatureCategory.CARDS,
     "display": "Away Total Cards", "desc": "Total bookings (yellow + red) for away team"},
    # Goals
    {"name": "home_goals", "source": "homeGoalCount", "category": FeatureCategory.GOALS,
     "display": "Home Goals", "desc": "Goals scored by home team"},
    {"name": "away_goals", "source": "awayGoalCount", "category": FeatureCategory.GOALS,
     "display": "Away Goals", "desc": "Goals scored by away team"},
    {"name": "total_goals", "source": "overallGoalCount", "category": FeatureCategory.GOALS,
     "display": "Total Goals", "desc": "Total goals in the match"},
    # Shots
    {"name": "home_shots", "source": "team_a_shots", "category": FeatureCategory.SHOTS,
     "display": "Home Shots", "desc": "Total shots by home team"},
    {"name": "away_shots", "source": "team_b_shots", "category": FeatureCategory.SHOTS,
     "display": "Away Shots", "desc": "Total shots by away team"},
    {"name": "home_shots_on_target", "source": "team_a_shotsOnTarget", "category": FeatureCategory.SHOTS,
     "display": "Home Shots on Target", "desc": "Shots on target by home team"},
    {"name": "away_shots_on_target", "source": "team_b_shotsOnTarget", "category": FeatureCategory.SHOTS,
     "display": "Away Shots on Target", "desc": "Shots on target by away team"},
    {"name": "home_xg", "source": "team_a_xg", "category": FeatureCategory.SHOTS,
     "display": "Home xG", "desc": "Expected goals (post-match) for home team"},
    {"name": "away_xg", "source": "team_b_xg", "category": FeatureCategory.SHOTS,
     "display": "Away xG", "desc": "Expected goals (post-match) for away team"},
    # Possession & Attacks
    {"name": "home_possession", "source": "team_a_possession", "category": FeatureCategory.POSSESSION,
     "display": "Home Possession %", "desc": "Ball possession percentage for home team"},
    {"name": "away_possession", "source": "team_b_possession", "category": FeatureCategory.POSSESSION,
     "display": "Away Possession %", "desc": "Ball possession percentage for away team"},
    {"name": "home_attacks", "source": "team_a_attacks", "category": FeatureCategory.POSSESSION,
     "display": "Home Attacks", "desc": "Total attacks by home team"},
    {"name": "away_attacks", "source": "team_b_attacks", "category": FeatureCategory.POSSESSION,
     "display": "Away Attacks", "desc": "Total attacks by away team"},
    {"name": "home_dangerous_attacks", "source": "team_a_dangerous_attacks", "category": FeatureCategory.POSSESSION,
     "display": "Home Dangerous Attacks", "desc": "Dangerous attacks by home team"},
    {"name": "away_dangerous_attacks", "source": "team_b_dangerous_attacks", "category": FeatureCategory.POSSESSION,
     "display": "Away Dangerous Attacks", "desc": "Dangerous attacks by away team"},
    # Discipline
    {"name": "home_fouls", "source": "team_a_fouls", "category": FeatureCategory.DISCIPLINE,
     "display": "Home Fouls", "desc": "Fouls committed by home team"},
    {"name": "away_fouls", "source": "team_b_fouls", "category": FeatureCategory.DISCIPLINE,
     "display": "Away Fouls", "desc": "Fouls committed by away team"},
    {"name": "home_offsides", "source": "team_a_offsides", "category": FeatureCategory.DISCIPLINE,
     "display": "Home Offsides", "desc": "Offsides by home team"},
    {"name": "away_offsides", "source": "team_b_offsides", "category": FeatureCategory.DISCIPLINE,
     "display": "Away Offsides", "desc": "Offsides by away team"},
    # Set Pieces
    {"name": "home_freekicks", "source": "team_a_freekicks", "category": FeatureCategory.SET_PIECES,
     "display": "Home Free Kicks", "desc": "Free kicks won by home team"},
    {"name": "away_freekicks", "source": "team_b_freekicks", "category": FeatureCategory.SET_PIECES,
     "display": "Away Free Kicks", "desc": "Free kicks won by away team"},
    {"name": "home_throwins", "source": "team_a_throwins", "category": FeatureCategory.SET_PIECES,
     "display": "Home Throw-ins", "desc": "Throw-ins taken by home team"},
    {"name": "away_throwins", "source": "team_b_throwins", "category": FeatureCategory.SET_PIECES,
     "display": "Away Throw-ins", "desc": "Throw-ins taken by away team"},
    # Form (pre-match)
    {"name": "home_ppg", "source": "pre_match_home_ppg", "category": FeatureCategory.FORM,
     "display": "Home Points Per Game (pre-match)", "desc": "Home team average PPG entering the match"},
    {"name": "away_ppg", "source": "pre_match_away_ppg", "category": FeatureCategory.FORM,
     "display": "Away Points Per Game (pre-match)", "desc": "Away team average PPG entering the match"},
    {"name": "home_xg_prematch", "source": "team_a_xg_prematch", "category": FeatureCategory.FORM,
     "display": "Home xG (pre-match model)", "desc": "Pre-match expected goals estimate for home team"},
    {"name": "away_xg_prematch", "source": "team_b_xg_prematch", "category": FeatureCategory.FORM,
     "display": "Away xG (pre-match model)", "desc": "Pre-match expected goals estimate for away team"},
]

# Rolling windows available for derived features
ROLLING_WINDOWS = (3, 5, 10)


def build_creator_feature_catalog() -> list[CreatorFeature]:
    """Build the full feature catalog exposed to creators.

    Includes:
    1. xMetric features (6 base + 18 rolling)
    2. Raw statistical features from FootyStats
    3. Rolling averages of raw stats (at windows 3, 5, 10)

    This is the REAL feature set. If internal models can use it, creators
    can too.
    """
    catalog: list[CreatorFeature] = []

    # ─── xMetric features ───
    registry = FeatureRegistry()
    adapter = XMetricAdapter()
    adapter.register_features(registry)
    rolling_defs = create_xmetric_rolling_features()
    registry.register_many(rolling_defs)

    for feat in registry.all_features():
        catalog.append(CreatorFeature(
            feature_id=feat.feature_id,
            name=feat.name,
            display_name=_xmetric_display_name(feat.name),
            description=feat.description or f"xMetric: {feat.name}",
            category=FeatureCategory.XMETRICS,
            temporal_class=feat.temporal_class.value,
            transform=feat.transform.value,
            market_applicability=list(feat.market_applicability),
            usable_pre_kickoff=feat.temporal_class in (TemporalClass.PRE_MATCH, TemporalClass.DERIVED),
            source_fields=list(feat.source_fields),
            params=feat.params,
        ))

    # ─── Raw stat features + rolling derivations ───
    for raw in RAW_STAT_FEATURES:
        # Base feature (post-match value, usable in backtests and rolling derivations)
        base_id = f"raw_{raw['name']}"
        is_prematch = "prematch" in raw["source"] or "pre_match" in raw["source"]
        catalog.append(CreatorFeature(
            feature_id=base_id,
            name=raw["name"],
            display_name=raw["display"],
            description=raw["desc"],
            category=raw["category"],
            temporal_class="PRE_MATCH" if is_prematch else "POST_MATCH",
            transform="RAW",
            market_applicability=[],  # All markets
            usable_pre_kickoff=is_prematch,
            source_fields=[raw["source"]],
            params={},
        ))

        # Rolling averages (DERIVED from historical data — usable pre-kickoff)
        if not is_prematch:  # Only compute rolling for post-match stats
            for window in ROLLING_WINDOWS:
                rolling_id = f"rolling_{raw['name']}_avg_{window}"
                catalog.append(CreatorFeature(
                    feature_id=rolling_id,
                    name=f"{raw['name']}_avg_{window}",
                    display_name=f"{raw['display']} (last {window} avg)",
                    description=f"Rolling average of {raw['desc'].lower()} over last {window} matches",
                    category=raw["category"],
                    temporal_class="DERIVED",
                    transform="ROLLING_MEAN",
                    market_applicability=[],
                    usable_pre_kickoff=True,
                    source_fields=[raw["source"]],
                    params={"window": window},
                ))

    return catalog


def _xmetric_display_name(name: str) -> str:
    """Human-readable name for xMetric features."""
    parts = name.split("_")
    if "avg" in parts:
        window = parts[-1]
        side = parts[0].title()
        metric = parts[1]
        return f"{side} {metric} (last {window} avg)"
    side = parts[0].title()
    metric = parts[1] if len(parts) > 1 else name
    return f"{side} {metric}"


def get_feature_catalog_summary() -> dict:
    """Summary for API responses."""
    catalog = build_creator_feature_catalog()
    by_category = {}
    for f in catalog:
        cat = f.category.value
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append({
            "feature_id": f.feature_id,
            "name": f.name,
            "display_name": f.display_name,
            "description": f.description,
            "temporal_class": f.temporal_class,
            "transform": f.transform,
            "usable_pre_kickoff": f.usable_pre_kickoff,
        })

    return {
        "total_features": len(catalog),
        "total_usable_pre_kickoff": sum(1 for f in catalog if f.usable_pre_kickoff),
        "categories": by_category,
        "note": (
            "All features available to internal models are available to creators. "
            "Features marked 'usable_pre_kickoff=true' can be used in live predictions. "
            "POST_MATCH features can be used in backtesting but cannot inform pre-kickoff "
            "predictions (they'd require knowing the match result before it happens)."
        ),
    }
