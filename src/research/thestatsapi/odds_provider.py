"""TheStatsAPI odds provider — implements OddsProvider.

Surfaces TheStatsAPI bookmaker prices as canonical ``OddsSnapshot``
observations. This is the market-benchmark path FootyStats cannot provide
(per-bookmaker granularity, opening vs last-seen, and — from the time-series
``research_odds`` files — genuinely timestamped observations).

Two payload kinds are supported:
1. ``cma_odds`` snapshots: carry ``opening`` and ``last_seen`` per market but
   NO capture timestamp. We surface ``opening`` as PRE_MATCH and ``last_seen``
   as PRE_MATCH by default; ``last_seen`` is NOT called "closing" because we
   cannot prove it was the market close from this payload alone.
2. ``research_odds`` time-series files: carry a real capture timestamp encoded
   in the filename / payload. These are the honest as-of / closing source; the
   caller supplies the observation timestamps.

TEMPORAL SAFETY:
- ``get_odds_snapshot`` returns only PRE_MATCH snapshots.
- ``get_closing_odds`` returns snapshots explicitly marked CLOSING; nothing is
  auto-promoted to CLOSING here. Genuine closing determination (with
  timestamp semantics) is the ClosingOddsProvider's job.
- All snapshots are preserved (append-only); we never overwrite history.

Fixture id: to line up with the forward pipeline, odds are keyed by the SAME
deterministic fixture id scheme as ``FutureFixture`` — a hash of
(source, source_fixture_id). Use ``canonical_fixture_id(match_ref)``.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

from src.research.forward.odds import OddsSnapshot, OddsType
from src.research.forward.providers import OddsProvider
from src.research.thestatsapi import ids
from src.research.thestatsapi.odds_normalizer import TheStatsAPIOddsNormalizer

logger = logging.getLogger(__name__)

_SOURCE = "thestatsapi"


def canonical_fixture_id(match_ref: str) -> str:
    """Deterministic fixture id matching FutureFixture's identity scheme.

    FutureFixture identity = sha256({"source", "source_fixture_id"})[:16].
    For TheStatsAPI, source_fixture_id is the numeric suffix of the match ref.
    """
    source_fixture_id = ids.parse_match_id(match_ref)
    canonical = json.dumps(
        {"source": _SOURCE, "source_fixture_id": source_fixture_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class TheStatsAPIOddsProvider(OddsProvider):
    """OddsProvider backed by TheStatsAPI odds payloads.

    Snapshots must be loaded explicitly (from cma_odds or research_odds
    payloads) via ``ingest_cma_odds`` / ``add_snapshots``. This keeps the
    provider deterministic and free of hidden network access.
    """

    def __init__(self, normalizer: Optional[TheStatsAPIOddsNormalizer] = None) -> None:
        self._normalizer = normalizer or TheStatsAPIOddsNormalizer()
        # fixture_id -> list of snapshots (append-only; deduped by content hash)
        self._by_fixture: dict[str, list[OddsSnapshot]] = {}
        self._seen_hashes: set[str] = set()

    @property
    def provider_name(self) -> str:
        return _SOURCE

    # -- ingestion ----------------------------------------------------------

    def add_snapshots(self, snapshots: list[OddsSnapshot]) -> int:
        """Append snapshots, skipping exact duplicates (by content hash)."""
        added = 0
        for snap in snapshots:
            h = snap.content_hash
            if h in self._seen_hashes:
                continue
            self._seen_hashes.add(h)
            self._by_fixture.setdefault(snap.fixture_id, []).append(snap)
            added += 1
        return added

    def ingest_cma_odds(
        self,
        payload: dict[str, Any],
        *,
        opening_timestamp: float,
        last_seen_timestamp: Optional[float] = None,
        retrieval_timestamp: float = 0.0,
    ) -> int:
        """Ingest a ``cma_odds`` payload as PRE_MATCH snapshots.

        Args:
            payload: Parsed cma_odds payload (has data.match_id, data.bookmakers).
            opening_timestamp: Observation time to stamp on ``opening`` prices.
            last_seen_timestamp: Observation time for ``last_seen`` prices. If
                None, last_seen prices are skipped (we do not invent a time).
            retrieval_timestamp: When the payload was fetched.

        Returns:
            Number of snapshots added.
        """
        data = (payload or {}).get("data", {})
        match_ref = data.get("match_id")
        if not isinstance(match_ref, str) or not match_ref:
            return 0
        try:
            fixture_id = canonical_fixture_id(match_ref)
        except ids.ProviderIdError:
            logger.warning("Skipping odds payload with bad match id %r", match_ref)
            return 0

        added = 0
        opening = self._normalizer.normalize_payload(
            payload,
            fixture_id=fixture_id,
            snapshot_timestamp=opening_timestamp,
            source_timestamp=None,
            retrieval_timestamp=retrieval_timestamp,
            odds_type=OddsType.PRE_MATCH,
            price_key="opening",
            source=_SOURCE,
        )
        added += self.add_snapshots(opening)

        if last_seen_timestamp is not None:
            last_seen = self._normalizer.normalize_payload(
                payload,
                fixture_id=fixture_id,
                snapshot_timestamp=last_seen_timestamp,
                source_timestamp=None,
                retrieval_timestamp=retrieval_timestamp,
                odds_type=OddsType.PRE_MATCH,
                price_key="last_seen",
                source=_SOURCE,
            )
            added += self.add_snapshots(last_seen)
        return added

    # -- OddsProvider interface --------------------------------------------

    def get_odds_snapshot(
        self,
        fixture_id: str,
        market: Optional[str] = None,
        bookmaker: Optional[str] = None,
    ) -> list[OddsSnapshot]:
        results = [s for s in self._by_fixture.get(fixture_id, []) if s.odds_type == OddsType.PRE_MATCH]
        if market:
            results = [s for s in results if s.market == market]
        if bookmaker:
            results = [s for s in results if s.bookmaker == bookmaker]
        results.sort(key=lambda s: s.snapshot_timestamp, reverse=True)
        return results

    def get_closing_odds(
        self,
        fixture_id: str,
        market: Optional[str] = None,
    ) -> list[OddsSnapshot]:
        """Return only snapshots explicitly marked CLOSING.

        Nothing is auto-promoted to CLOSING. If no CLOSING snapshots were
        ingested, this returns [] rather than fabricating a close.
        """
        results = [s for s in self._by_fixture.get(fixture_id, []) if s.odds_type == OddsType.CLOSING]
        if market:
            results = [s for s in results if s.market == market]
        return results

    def get_odds_history(
        self,
        fixture_id: str,
        market: Optional[str] = None,
    ) -> list[OddsSnapshot]:
        results = list(self._by_fixture.get(fixture_id, []))
        if market:
            results = [s for s in results if s.market == market]
        results.sort(key=lambda s: s.snapshot_timestamp)
        return results
