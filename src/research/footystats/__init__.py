"""Batch 6 — FootyStats Real-Data Integration.

Provides a ResearchDataSource implementation backed by the FootyStats API.
Does NOT modify the research engine — only provides data.

Architecture:
    FootyStats API → FootyStatsClient → Normalizer → ResearchDataSource

Key guarantees:
- Null preservation (missing ≠ zero, sentinel -1 = NULL)
- Temporal integrity (pre-match vs post-match distinction)
- Credential security (env-based, never serialized)
- Deterministic deduplication (source_match_id)
- Data provenance tracking
- Schema validation
"""

from src.research.footystats.adapter import FootyStatsDataSource
from src.research.footystats.client import FootyStatsResearchClient
from src.research.footystats.normalizer import MatchNormalizer
from src.research.footystats.quality import DataQualityStatus, QualityReport, RecordValidator
from src.research.footystats.provenance import DataProvenance

__all__ = [
    "FootyStatsDataSource",
    "FootyStatsResearchClient",
    "MatchNormalizer",
    "DataQualityStatus",
    "QualityReport",
    "RecordValidator",
    "DataProvenance",
]
