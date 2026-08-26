"""FootyStats Odds Provider — extracts odds from FootyStats match records.

FootyStats embeds pre-match odds directly in match records.
This provider extracts them as properly-typed OddsSnapshot objects.

Supported markets (from FootyStats data):
- GOALS_TOTAL (over/under 2.5)
- CORNERS_TOTAL (over/under 9.5)
- MATCH_RESULT_1X2 (home/draw/away)

Temporal Rules:
- Pre-match odds are estimated to be available 1 hour before kickoff
  (FootyStats does not provide exact odds publication timestamps)
- Closing odds are NOT available through FootyStats
  (CLV marked as UNAVAILABLE when using FootyStats alone)
- odds_type is always PRE_MATCH or UNAVAILABLE — never falsely labeled CLOSING

Limitations:
- FootyStats provides a single pre-match odds snapshot per match
- No live/in-play odds
- No genuine closing odds
- No bookmaker-level granularity (market average only)
- timestamp_confidence = ESTIMATED (not EXACT)
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

from src.research.footystats.client import FootyStatsResearchClient
from src.research.forward.odds import OddsSelection, OddsSnapshot, OddsType
from src.research.forward.providers import OddsProvider

logger = logging.getLogger(__name__)


class FootyStatsOddsProvider(OddsProvider):
    """Odds provider extracting pre-match odds from FootyStats match data.

    FootyStats embeds odds in match records. This provider fetches
    match details and extracts structured OddsSnapshot objects.

    IMPORTANT: FootyStats does NOT provide:
    - Genuine closing odds (odds at exact kickoff)
    - Live/in-play odds
    - Per-bookmaker odds (only market averages)
    - Exact odds publication timestamps

    All timestamps are ESTIMATED (1 hour before kickoff).
    CLV calculation requires a separate closing odds source.
    """

    def __init__(
        self,
        season_ids: Optional[list[int]] = None,
        api_key: Optional[str] = None,
        cache_dir: Optional[Path] = None,
        client: Optional[FootyStatsResearchClient] = None,
    ) -> None:
        self._season_ids = season_ids or []
        self._client = client or FootyStatsResearchClient(
            api_key=api_key, cache_dir=cache_dir,
        )
        # Cache of extracted odds by fixture_id
        self._odds_cache: dict[str, list[OddsSnapshot]] = {}

    @property
    def provider_name(self) -> str:
        return "footystats"

    def get_odds_snapshot(
        self,
        fixture_id: str,
        market: Optional[str] = None,
        bookmaker: Optional[str] = None,
    ) -> list[OddsSnapshot]:
        """Get pre-match odds for a fixture.

        Returns only PRE_MATCH odds. FootyStats has no closing odds.
        """
        snapshots = self._odds_cache.get(fixture_id, [])
        if market:
            snapshots = [s for s in snapshots if s.market == market]
        if bookmaker:
            snapshots = [s for s in snapshots if s.bookmaker == bookmaker]
        # Only pre-match
        return [s for s in snapshots if s.odds_type == OddsType.PRE_MATCH]

    def get_closing_odds(
        self,
        fixture_id: str,
        market: Optional[str] = None,
    ) -> list[OddsSnapshot]:
        """Get closing odds — NOT AVAILABLE from FootyStats.

        FootyStats does not provide genuine closing odds.
        Returns empty list. CLV requires a different source.
        """
        # FootyStats CANNOT provide closing odds
        # Never fake closing odds
        return []

    def get_odds_history(
        self,
        fixture_id: str,
        market: Optional[str] = None,
    ) -> list[OddsSnapshot]:
        """Get all odds history — FootyStats provides only a single pre-match snapshot."""
        snapshots = self._odds_cache.get(fixture_id, [])
        if market:
            snapshots = [s for s in snapshots if s.market == market]
        return sorted(snapshots, key=lambda s: s.snapshot_timestamp)

    def load_odds_for_season(self, season_id: int) -> int:
        """Load odds for all matches in a season.

        Fetches season matches and extracts odds from each record.
        Returns number of odds snapshots extracted.
        """
        count = 0
        try:
            raw_matches = self._client.fetch_season_matches(season_id)
            for raw in raw_matches:
                snapshots = self._extract_odds(raw)
                if snapshots:
                    # Use the same fixture_id scheme as FootyStatsFixtureProvider
                    fixture_id = snapshots[0].fixture_id
                    if fixture_id not in self._odds_cache:
                        self._odds_cache[fixture_id] = []
                    for snap in snapshots:
                        # Dedup by content hash
                        existing_ids = {s.odds_snapshot_id for s in self._odds_cache[fixture_id]}
                        if snap.odds_snapshot_id not in existing_ids:
                            self._odds_cache[fixture_id].append(snap)
                            count += 1
        except Exception as e:
            logger.warning("Failed to load odds for season %d: %s", season_id, type(e).__name__)

        return count

    def load_odds_for_match(self, match_id: int) -> list[OddsSnapshot]:
        """Load odds from a specific match detail.

        Fetches match detail and extracts odds snapshots.
        """
        try:
            raw = self._client.fetch_match_detail(match_id)
            return self._extract_odds(raw)
        except Exception as e:
            logger.warning("Failed to load odds for match %d: %s", match_id, type(e).__name__)
            return []

    def _extract_odds(self, raw: dict[str, Any]) -> list[OddsSnapshot]:
        """Extract OddsSnapshot records from a raw FootyStats match record.

        Supported markets:
        - GOALS_TOTAL: odds_ft_over25 / odds_ft_under25 (line 2.5)
        - CORNERS_TOTAL: odds_corners_over_95 / odds_corners_under_95 (line 9.5)
        - MATCH_RESULT_1X2: odds_ft_1 / odds_ft_x / odds_ft_2
        """
        match_id = raw.get("id")
        if not match_id:
            return []

        date_unix = raw.get("date_unix")
        if not date_unix:
            return []

        # Build fixture_id matching FootyStatsFixtureProvider scheme
        import hashlib, json
        canonical = json.dumps({
            "source": "footystats",
            "source_fixture_id": int(match_id),
        }, sort_keys=True, separators=(",", ":"))
        fixture_id = hashlib.sha256(canonical.encode()).hexdigest()[:16]

        # Estimated odds timestamp: 1 hour before kickoff
        # FootyStats does NOT provide exact odds publication time
        odds_timestamp = float(date_unix) - 3600.0
        retrieval_time = time.time()

        snapshots: list[OddsSnapshot] = []

        # GOALS_TOTAL (line 2.5)
        over_goals = self._safe_odds(raw.get("odds_ft_over25"))
        under_goals = self._safe_odds(raw.get("odds_ft_under25"))
        if over_goals:
            snapshots.append(OddsSnapshot(
                fixture_id=fixture_id,
                market="GOALS_TOTAL",
                selection=OddsSelection.OVER,
                line=2.5,
                decimal_odds=over_goals,
                source="footystats",
                bookmaker="market_average",
                snapshot_timestamp=odds_timestamp,
                source_timestamp=None,  # Not provided by FootyStats
                retrieval_timestamp=retrieval_time,
                odds_type=OddsType.PRE_MATCH,
            ))
        if under_goals:
            snapshots.append(OddsSnapshot(
                fixture_id=fixture_id,
                market="GOALS_TOTAL",
                selection=OddsSelection.UNDER,
                line=2.5,
                decimal_odds=under_goals,
                source="footystats",
                bookmaker="market_average",
                snapshot_timestamp=odds_timestamp,
                source_timestamp=None,
                retrieval_timestamp=retrieval_time,
                odds_type=OddsType.PRE_MATCH,
            ))

        # CORNERS_TOTAL (line 9.5)
        over_corners = self._safe_odds(raw.get("odds_corners_over_95"))
        under_corners = self._safe_odds(raw.get("odds_corners_under_95"))
        if over_corners:
            snapshots.append(OddsSnapshot(
                fixture_id=fixture_id,
                market="CORNERS_TOTAL",
                selection=OddsSelection.OVER,
                line=9.5,
                decimal_odds=over_corners,
                source="footystats",
                bookmaker="market_average",
                snapshot_timestamp=odds_timestamp,
                source_timestamp=None,
                retrieval_timestamp=retrieval_time,
                odds_type=OddsType.PRE_MATCH,
            ))
        if under_corners:
            snapshots.append(OddsSnapshot(
                fixture_id=fixture_id,
                market="CORNERS_TOTAL",
                selection=OddsSelection.UNDER,
                line=9.5,
                decimal_odds=under_corners,
                source="footystats",
                bookmaker="market_average",
                snapshot_timestamp=odds_timestamp,
                source_timestamp=None,
                retrieval_timestamp=retrieval_time,
                odds_type=OddsType.PRE_MATCH,
            ))

        # MATCH_RESULT_1X2
        odds_home = self._safe_odds(raw.get("odds_ft_1"))
        odds_draw = self._safe_odds(raw.get("odds_ft_x"))
        odds_away = self._safe_odds(raw.get("odds_ft_2"))
        if odds_home:
            snapshots.append(OddsSnapshot(
                fixture_id=fixture_id,
                market="MATCH_RESULT_1X2",
                selection=OddsSelection.HOME,
                line=0.0,
                decimal_odds=odds_home,
                source="footystats",
                bookmaker="market_average",
                snapshot_timestamp=odds_timestamp,
                source_timestamp=None,
                retrieval_timestamp=retrieval_time,
                odds_type=OddsType.PRE_MATCH,
            ))
        if odds_draw:
            snapshots.append(OddsSnapshot(
                fixture_id=fixture_id,
                market="MATCH_RESULT_1X2",
                selection=OddsSelection.DRAW,
                line=0.0,
                decimal_odds=odds_draw,
                source="footystats",
                bookmaker="market_average",
                snapshot_timestamp=odds_timestamp,
                source_timestamp=None,
                retrieval_timestamp=retrieval_time,
                odds_type=OddsType.PRE_MATCH,
            ))
        if odds_away:
            snapshots.append(OddsSnapshot(
                fixture_id=fixture_id,
                market="MATCH_RESULT_1X2",
                selection=OddsSelection.AWAY,
                line=0.0,
                decimal_odds=odds_away,
                source="footystats",
                bookmaker="market_average",
                snapshot_timestamp=odds_timestamp,
                source_timestamp=None,
                retrieval_timestamp=retrieval_time,
                odds_type=OddsType.PRE_MATCH,
            ))

        return snapshots

    @staticmethod
    def _safe_odds(value: Any) -> Optional[float]:
        """Safely extract odds value. Returns None for invalid/missing.

        Rejects: None, 0, negative, <1.0, non-numeric.
        Does NOT convert missing to zero.
        """
        if value is None:
            return None
        try:
            odds = float(value)
        except (TypeError, ValueError):
            return None
        if odds < 1.0:
            return None
        return odds
