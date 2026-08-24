"""Builder templates API — serves pre-built benchmark strategies.

Provides 10 production-grade benchmark strategies using proprietary
xC, xB, and xO models targeting high-volume European leagues.
"""

from __future__ import annotations

import logging
from typing import List

logger = logging.getLogger(__name__)

# 10 pre-built benchmark strategies
BENCHMARK_STRATEGIES: List[dict] = [
    # --- 4× xC (Corner Pressure) ---
    {
        "name": "EPL Corner Pressure Over",
        "description": "High dangerous-attack ratio + opponent concedes corners frequently in Premier League matches.",
        "metric": "xC",
        "market": "corners_over_under",
        "conditions": [
            {"field": "home_xC", "op": ">", "value": 2.8},
            {"field": "away_xC", "op": ">", "value": 2.2},
        ],
        "logic": "and",
        "direction": "OVER",
        "min_odds": 1.75,
        "target_leagues": [1625],
    },
    {
        "name": "La Liga Wing Attack Corners",
        "description": "La Liga teams with extreme wing penetration generating corner pressure.",
        "metric": "xC",
        "market": "corners_over_under",
        "conditions": [
            {"field": "home_xC", "op": ">=", "value": 3.0},
        ],
        "logic": "and",
        "direction": "OVER",
        "min_odds": 1.80,
        "target_leagues": [1635],
    },
    {
        "name": "Bundesliga Deep Penetration Corners",
        "description": "High-tempo Bundesliga matches with both teams generating dangerous attacks.",
        "metric": "xC",
        "market": "corners_over_under",
        "conditions": [
            {"field": "home_xC", "op": ">", "value": 2.5},
            {"field": "away_xC", "op": ">", "value": 2.5},
        ],
        "logic": "and",
        "direction": "OVER",
        "min_odds": 1.70,
        "target_leagues": [1645],
    },
    {
        "name": "Serie A Defensive Corners Under",
        "description": "Low corner pressure when both teams lack attacking penetration in Serie A.",
        "metric": "xC",
        "market": "corners_over_under",
        "conditions": [
            {"field": "home_xC", "op": "<", "value": 1.8},
            {"field": "away_xC", "op": "<", "value": 1.8},
        ],
        "logic": "and",
        "direction": "UNDER",
        "min_odds": 1.80,
        "target_leagues": [1640],
    },
    # --- 3× xB (Booking Friction) ---
    {
        "name": "EPL Card Intensity Over",
        "description": "High-foul Premier League matches with strict referees produce card-heavy games.",
        "metric": "xB",
        "market": "cards_over_under",
        "conditions": [
            {"field": "home_xB", "op": ">", "value": 9.0},
            {"field": "away_xB", "op": ">", "value": 8.5},
        ],
        "logic": "and",
        "direction": "OVER",
        "min_odds": 1.75,
        "target_leagues": [1625],
    },
    {
        "name": "La Liga Referee Friction Cards",
        "description": "La Liga fixtures with high referee card rates and possession imbalance.",
        "metric": "xB",
        "market": "cards_over_under",
        "conditions": [
            {"field": "home_xB", "op": ">=", "value": 10.0},
        ],
        "logic": "and",
        "direction": "OVER",
        "min_odds": 1.80,
        "target_leagues": [1635],
    },
    {
        "name": "Ligue 1 Low Foul Pressure Under",
        "description": "Technical Ligue 1 matches with low defensive friction and lenient officials.",
        "metric": "xB",
        "market": "cards_over_under",
        "conditions": [
            {"field": "home_xB", "op": "<", "value": 5.5},
            {"field": "away_xB", "op": "<", "value": 5.5},
        ],
        "logic": "and",
        "direction": "UNDER",
        "min_odds": 1.85,
        "target_leagues": [1632],
    },
    # --- 3× xO (High-Line Offside) ---
    {
        "name": "EPL High Line Offside Trap Over",
        "description": "Counter-attacking teams vs aggressive high-line defences in the Premier League.",
        "metric": "xO",
        "market": "offsides_over_under",
        "conditions": [
            {"field": "home_xO", "op": ">", "value": 3.5},
            {"field": "away_xO", "op": ">", "value": 2.5},
        ],
        "logic": "or",
        "direction": "OVER",
        "min_odds": 1.80,
        "target_leagues": [1625],
    },
    {
        "name": "Bundesliga Counter Offside",
        "description": "Bundesliga high-press teams with direct long-ball attacks triggering offside traps.",
        "metric": "xO",
        "market": "offsides_over_under",
        "conditions": [
            {"field": "home_xO", "op": ">=", "value": 4.0},
        ],
        "logic": "and",
        "direction": "OVER",
        "min_odds": 1.75,
        "target_leagues": [1645],
    },
    {
        "name": "Serie A Direct Attack Offsides",
        "description": "Serie A teams with high through-ball rates against compact defensive blocks.",
        "metric": "xO",
        "market": "offsides_over_under",
        "conditions": [
            {"field": "home_xO", "op": ">", "value": 3.0},
            {"field": "away_xO", "op": ">", "value": 3.0},
        ],
        "logic": "and",
        "direction": "OVER",
        "min_odds": 1.70,
        "target_leagues": [1640],
    },
]


def get_templates() -> List[dict]:
    """Return all 10 benchmark strategy templates.

    Returns:
        List of strategy template dicts compatible with StrategyBuilder.from_dict().
    """
    return list(BENCHMARK_STRATEGIES)


def get_template_by_metric(metric: str) -> List[dict]:
    """Filter templates by metric type.

    Args:
        metric: One of "xC", "xB", "xO".

    Returns:
        List of matching strategy templates.
    """
    return [s for s in BENCHMARK_STRATEGIES if s["metric"] == metric]


def get_template_by_name(name: str) -> dict | None:
    """Find a template by exact name.

    Args:
        name: Strategy name.

    Returns:
        Matching template dict or None.
    """
    for s in BENCHMARK_STRATEGIES:
        if s["name"] == name:
            return dict(s)
    return None
