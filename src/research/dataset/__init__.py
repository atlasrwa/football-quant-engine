"""Point-in-time dataset and immutable artifact primitives for QFE V2."""

from src.research.dataset.audit import (
    CachedCorpusAuditReport,
    CachedCorpusSpec,
    CachedSeasonDiscovery,
    audit_cached_corpus,
    discover_cached_seasons,
)
from src.research.dataset.foundation_report import (
    FoundationAuditBundle,
    build_foundation_audit_bundle,
    write_frozen_foundation_audit,
)

from src.research.dataset.multiseason import (
    MULTISEASON_CORPUS_VERSION,
    MultiSeasonCorpusManifest,
    MultiSeasonPITCorpus,
    build_multiseason_pit_corpus,
)

from src.research.dataset.manifest import (
    PITDatasetManifest,
    verify_immutable_dataset,
    write_immutable_dataset,
)
from src.research.dataset.pit import (
    DEFAULT_HISTORY_METRICS,
    DatasetIntegrityError,
    HistoryLineage,
    PITDatasetArtifact,
    PITDatasetBuilder,
    PITDatasetSpec,
    PITFeatureRow,
)

__all__ = [
    "MULTISEASON_CORPUS_VERSION",
    "MultiSeasonCorpusManifest",
    "MultiSeasonPITCorpus",
    "build_multiseason_pit_corpus",
    "CachedCorpusAuditReport",
    "CachedCorpusSpec",
    "CachedSeasonDiscovery",
    "audit_cached_corpus",
    "discover_cached_seasons",
    "FoundationAuditBundle",
    "build_foundation_audit_bundle",
    "write_frozen_foundation_audit",
    "PITDatasetManifest",
    "verify_immutable_dataset",
    "write_immutable_dataset",
    "DEFAULT_HISTORY_METRICS",
    "DatasetIntegrityError",
    "HistoryLineage",
    "PITDatasetArtifact",
    "PITDatasetBuilder",
    "PITDatasetSpec",
    "PITFeatureRow",
]
