"""TheStatsAPI provider package.

A clean, point-in-time-safe integration of TheStatsAPI as a SECOND data
provider alongside FootyStats. This package is *additive* infrastructure:
it implements the existing research abstractions (``ResearchDataSource``,
``FutureFixtureProvider``, ``OddsProvider``) without modifying them and
without coupling the statistical models to TheStatsAPI HTTP responses.

Design rules (enforced across the package):
- API credentials are read only from environment/configuration, never hard
  coded and never committed.
- Raw provider payloads are normalized into the canonical ``ResearchMatch`` /
  ``OddsSnapshot`` types before they can reach any model code.
- NULL != ZERO: a field absent from the source stays ``None``; a genuine 0
  stays 0.
- Deterministic normalization: the same payload always yields the same
  normalized record and the same content hash.
- Caching is only ever content/identity keyed and never used to satisfy an
  as-of query with data observed after the requested cutoff.

Modules:
- ``ids``            provider-id parsing/formatting (mt_/tm_/comp_/sn_ prefixes)
- ``exceptions``     provider-specific exception hierarchy
- ``normalizer``     raw payload -> ResearchMatch / OddsSnapshot (NULL-safe)
- ``provenance``     DataProvenance for source="THESTATSAPI"
- ``client``         HTTP client (timeouts, backoff, 429 handling, key redaction)
- ``adapter``        TheStatsAPIDataSource(ResearchDataSource)
- ``fixture_provider`` TheStatsAPIFixtureProvider(FutureFixtureProvider)
- ``odds_provider``  TheStatsAPIOddsProvider(OddsProvider)
"""

from __future__ import annotations

SOURCE_NAME = "THESTATSAPI"

__all__ = ["SOURCE_NAME"]
