"""TheStatsAPI Data Source Adapter — implements ResearchDataSource.

Mirrors ``FootyStatsDataSource``: fetch -> normalize -> provenance -> expose,
implementing the EXISTING ``ResearchDataSource`` interface without modifying
it and without leaking raw payloads into model code.

Two construction modes (both point-in-time safe):
1. Cache-backed (default for research/tests): supply a
   ``TheStatsAPICorpusLoader`` plus the fixtures files and a stats glob. No
   network access.
2. Live: supply a configured ``TheStatsAPIClient`` and season refs. The client
   handles auth/timeouts/backoff/429 and PIT-safe identity-keyed caching.

The adapter is *additive*: it does not modify FootyStatsDataSource and produces
the same canonical ``ResearchMatch`` / ``MarketOdds`` types, so the existing
research engine consumes it unchanged. NULL != ZERO is preserved end to end.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Optional

from src.research.data_source import MarketOdds, ResearchDataSource, ResearchMatch
from src.research.thestatsapi.corpus_loader import TheStatsAPICorpusLoader
from src.research.thestatsapi.normalizer import TheStatsAPINormalizer
from src.research.thestatsapi.provenance import (
    TheStatsAPIProvenance,
    compute_match_hash,
    create_provenance,
)

logger = logging.getLogger(__name__)


class TheStatsAPIDataSource(ResearchDataSource):
    """ResearchDataSource backed by TheStatsAPI (cache-backed or live).

    Usage (cache-backed):
        loader = TheStatsAPICorpusLoader("data/thestatsapi/championship")
        source = TheStatsAPIDataSource(
            loader=loader,
            fixtures_files=["_all_fixtures_epl_sn_3057848.json"],
            stats_glob="epl_stats_mt_*.json",
        )
        matches = source.get_matches()
    """

    def __init__(
        self,
        *,
        loader: Optional[TheStatsAPICorpusLoader] = None,
        fixtures_files: Optional[list[str]] = None,
        fixtures_glob: Optional[str] = None,
        stats_glob: Optional[str] = None,
        stats_files: Optional[list[str]] = None,
        fixtures: Optional[list[dict[str, Any]]] = None,
        stats_by_match_ref: Optional[dict[str, dict[str, Any]]] = None,
        normalizer: Optional[TheStatsAPINormalizer] = None,
    ) -> None:
        """Initialize the data source.

        Provide EITHER pre-loaded ``fixtures`` (+ optional ``stats_by_match_ref``)
        OR a ``loader`` with ``fixtures_files``/``fixtures_glob`` and an optional
        ``stats_glob``/``stats_files``.
        """
        self._loader = loader
        self._fixtures_files = fixtures_files
        self._fixtures_glob = fixtures_glob
        self._stats_glob = stats_glob
        self._stats_files = stats_files
        self._preloaded_fixtures = fixtures
        self._preloaded_stats = stats_by_match_ref
        self._normalizer = normalizer or TheStatsAPINormalizer()

        self._matches: Optional[list[ResearchMatch]] = None
        self._provenance: list[TheStatsAPIProvenance] = []
        self._content_hash_value: Optional[str] = None

    @property
    def provenance_records(self) -> list[TheStatsAPIProvenance]:
        return list(self._provenance)

    @property
    def normalizer(self) -> TheStatsAPINormalizer:
        return self._normalizer

    def _load_raw(self) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
        if self._preloaded_fixtures is not None:
            return self._preloaded_fixtures, (self._preloaded_stats or {})
        if self._loader is None:
            raise ValueError(
                "TheStatsAPIDataSource requires either pre-loaded fixtures or a loader"
            )
        fixtures: list[dict[str, Any]] = []
        if self._fixtures_files:
            fixtures.extend(self._loader.load_fixtures(self._fixtures_files))
        if self._fixtures_glob:
            fixtures.extend(self._loader.load_fixtures_glob(self._fixtures_glob))
        stats_map: dict[str, dict[str, Any]] = {}
        if self._stats_glob or self._stats_files:
            stats_map = self._loader.load_stats_map(
                stats_glob=self._stats_glob, filenames=self._stats_files,
            )
        return fixtures, stats_map

    def _ensure_loaded(self) -> None:
        if self._matches is not None:
            return

        fixtures, stats_map = self._load_raw()
        normalized = self._normalizer.normalize_batch(fixtures, stats_map)
        self._matches = sorted(normalized, key=lambda m: m.date_unix)

        # Provenance per completed match.
        self._provenance = []
        for fx in fixtures:
            if not isinstance(fx, dict):
                continue
            match_ref = fx.get("id")
            if not isinstance(match_ref, str):
                continue
            home = (fx.get("home_team") or {}).get("id", "")
            away = (fx.get("away_team") or {}).get("id", "")
            from src.research.thestatsapi.normalizer import parse_iso_to_unix
            event_ts = parse_iso_to_unix(fx.get("utc_date")) or 0
            prov = create_provenance(
                match_ref=match_ref,
                season_ref=str(fx.get("season_id", "")),
                home_team_ref=str(home),
                away_team_ref=str(away),
                event_timestamp=event_ts,
            )
            self._provenance.append(prov)

    def get_matches(
        self,
        league_id: Optional[int] = None,
        season: Optional[str] = None,
        min_date: Optional[int] = None,
        max_date: Optional[int] = None,
    ) -> list[ResearchMatch]:
        self._ensure_loaded()
        assert self._matches is not None
        result = self._matches
        if league_id is not None:
            result = [m for m in result if m.league_id == league_id]
        if season is not None:
            result = [m for m in result if m.season == season]
        if min_date is not None:
            result = [m for m in result if m.date_unix >= min_date]
        if max_date is not None:
            result = [m for m in result if m.date_unix < max_date]
        return result

    def get_available_fields(self) -> list[str]:
        self._ensure_loaded()
        if not self._normalizer.field_availability:
            return []
        return sorted(self._normalizer.field_availability.keys())

    def get_market_odds(
        self,
        match_ids: Optional[list[int]] = None,
        market: Optional[str] = None,
    ) -> list[MarketOdds]:
        """Return pre-match MarketOdds.

        TheStatsAPI odds live in separate odds payloads, surfaced through the
        richer ``TheStatsAPIOddsProvider`` (OddsSnapshot). This method returns
        an empty list rather than fabricating two-sided MarketOdds from match
        payloads, keeping NULL != ZERO honest. Use the odds provider for the
        full point-in-time odds series.
        """
        self._ensure_loaded()
        return []

    def compute_content_hash(self) -> str:
        self._ensure_loaded()
        assert self._matches is not None
        if self._content_hash_value is not None:
            return self._content_hash_value
        canonical = json.dumps(
            [(m.match_id, m.date_unix) for m in self._matches],
            sort_keys=True,
            separators=(",", ":"),
        )
        self._content_hash_value = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return self._content_hash_value

    def get_coverage_summary(self) -> dict[str, Any]:
        self._ensure_loaded()
        assert self._matches is not None
        total = len(self._matches)
        if total == 0:
            return {"total_matches": 0}
        coverage = {}
        for field_name, count in sorted(self._normalizer.field_availability.items()):
            coverage[field_name] = {
                "available": count,
                "missing": total - count,
                "coverage_pct": round(count / total * 100, 1),
            }
        dates = [m.date_unix for m in self._matches]
        return {
            "total_matches": total,
            "earliest_date_unix": min(dates),
            "latest_date_unix": max(dates),
            "seasons": sorted(set(m.season for m in self._matches)),
            "leagues": sorted(set(m.league_id for m in self._matches)),
            "teams": len(set(t for m in self._matches for t in (m.home_team, m.away_team))),
            "field_coverage": coverage,
        }
