"""Reusable research evaluation workflows."""

from src.research.evaluation.laliga_corners import (
    protocol_definition as laliga_corners_protocol,
    summarize_confirmation as summarize_laliga_corners,
)
from src.research.evaluation.league_count import (
    ALL_EVALUATED_ARMS,
    CLIMATOLOGY_ARM,
    DEFAULT_CONTRASTS,
    Contrast,
    LeagueCountEvaluationConfig,
    LeagueCountEvaluationReport,
    LeagueCountEvaluator,
    build_broad_count_rows,
    default_count_markets,
)

__all__ = [
    "ALL_EVALUATED_ARMS",
    "CLIMATOLOGY_ARM",
    "DEFAULT_CONTRASTS",
    "Contrast",
    "LeagueCountEvaluationConfig",
    "LeagueCountEvaluationReport",
    "LeagueCountEvaluator",
    "build_broad_count_rows",
    "default_count_markets",
    "laliga_corners_protocol",
    "summarize_laliga_corners",
]
