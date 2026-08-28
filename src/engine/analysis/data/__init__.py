"""Data provider abstraction layer.

Provides a provider-agnostic interface for loading match data into
the canonical MatchRecord schema consumed by the x-Metric engine.
"""

from src.engine.data.base import BaseDataLoader, MATCH_RECORD_SCHEMA
from src.engine.data.footystats import FootyStatsAdapter
from src.engine.data.synthetic import SyntheticDataLoader

__all__ = [
    "BaseDataLoader",
    "FootyStatsAdapter",
    "MATCH_RECORD_SCHEMA",
    "SyntheticDataLoader",
]
