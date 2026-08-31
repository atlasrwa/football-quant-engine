"""Data provider abstraction layer.

Provides a provider-agnostic interface for loading match data into
the canonical MatchRecord schema consumed by the x-Metric engine.
"""

from src.engine.analysis.data.base import BaseDataLoader, MATCH_RECORD_SCHEMA
from src.engine.analysis.data.footystats import FootyStatsAdapter
from src.engine.analysis.data.synthetic import SyntheticDataLoader

__all__ = [
    "BaseDataLoader",
    "FootyStatsAdapter",
    "MATCH_RECORD_SCHEMA",
    "SyntheticDataLoader",
]
