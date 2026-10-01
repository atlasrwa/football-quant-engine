"""TheStatsAPI evidence-provider package for QFE V2.

Historical/cached football payloads are normalized into odds-blind
``ResearchMatch`` records before model code sees them. Live prospective HTTP
requests use the separately verified contract in ``src.research.prospective``.
NULL != ZERO is preserved throughout.

Modules retained here are deterministic provider primitives: id parsing,
normalization, provenance, cached corpus loading, the research adapter and
fixture conversion.
"""

from __future__ import annotations

SOURCE_NAME = "THESTATSAPI"

__all__ = ["SOURCE_NAME"]
