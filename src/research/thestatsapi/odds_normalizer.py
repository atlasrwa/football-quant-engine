"""Odds normalization — TheStatsAPI odds payloads to canonical OddsSnapshot.

Separate from the match normalizer and from de-vigging (kept in
``src/research/reconciliation/devig.py``). This module only converts raw
bookmaker prices into immutable ``OddsSnapshot`` observations, preserving the
distinction between the provider's ``opening`` and ``last_seen`` prices.

Input shape (data/thestatsapi/championship/cma_odds_mt_*.json):
    {"data": {"match_id": "mt_...", "bookmakers": [
        {"bookmaker": "Bet365", "markets": {
            "match_odds": {"home": {"opening": "1.615", "last_seen": "1.550"},
                           "draw": {...}, "away": {...}},
            "total_goals": {"2.5": {"over": {"opening": "1.725", "last_seen": "1.800"},
                                    "under": {...}}, ...},
            "btts": {"yes": {...}, "no": {...}},
            ...}}]}}

Odds values are STRING decimals; we coerce with NULL != ZERO semantics
(invalid / < 1.0 / unparseable -> skipped, never fabricated).

TEMPORAL SEMANTICS (critical):
- ``opening`` is a genuine pre-match observation -> odds_type=PRE_MATCH.
- ``last_seen`` is the LAST price the provider saw. It is NOT proven to be a
  genuine market close. We therefore surface it as PRE_MATCH by default and it
  is the caller's job (odds_provider / closing_provider) to decide, based on
  observation timestamps, whether it qualifies as LAST_BEFORE_KICKOFF. This
  module never stamps something as "closing"; that determination requires a
  timestamp and is made explicitly elsewhere.

Because the ``cma_odds`` payload carries no capture timestamp, snapshots
produced from it have ``snapshot_timestamp``/``source_timestamp`` supplied by
the caller (e.g. estimated pre-match). The time-series ``research_odds`` files
DO carry capture times and are handled by the odds_provider.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from src.research.forward.odds import OddsSelection, OddsSnapshot, OddsType

logger = logging.getLogger(__name__)

# The over/under total-goals lines we surface as canonical GOALS_TOTAL markets.
# Others are preserved verbatim from the payload keys.
_GOALS_MARKET = "GOALS_TOTAL"
_MATCH_RESULT_MARKET = "MATCH_RESULT_1X2"
_BTTS_MARKET = "BTTS"

_1X2_SELECTION = {
    "home": OddsSelection.HOME,
    "draw": OddsSelection.DRAW,
    "away": OddsSelection.AWAY,
}
_BTTS_SELECTION = {
    "yes": OddsSelection.YES,
    "no": OddsSelection.NO,
}


def safe_decimal_odds(value: Any) -> Optional[float]:
    """Coerce a decimal-odds value (possibly a string) to float.

    NULL != ZERO: None, non-numeric, <= 0, or < 1.0 all return None (not 0).
    Valid decimal odds are >= 1.0.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if v < 1.0:
        return None
    return v


def _price_of(node: Any, key: str) -> Optional[float]:
    """Extract node[key] as decimal odds, tolerating absence."""
    if not isinstance(node, dict):
        return None
    return safe_decimal_odds(node.get(key))


class TheStatsAPIOddsNormalizer:
    """Converts a TheStatsAPI odds payload into OddsSnapshot observations."""

    def normalize_payload(
        self,
        payload: dict[str, Any],
        *,
        fixture_id: str,
        snapshot_timestamp: float,
        source_timestamp: Optional[float] = None,
        retrieval_timestamp: float = 0.0,
        odds_type: OddsType = OddsType.PRE_MATCH,
        price_key: str = "opening",
        source: str = "thestatsapi",
    ) -> list[OddsSnapshot]:
        """Normalize one odds payload into snapshots for a single price_key.

        Args:
            payload: Parsed ``cma_odds`` payload (has ``data.bookmakers``).
            fixture_id: Canonical fixture id these odds attach to.
            snapshot_timestamp: Our observation time for this price.
            source_timestamp: Provider-reported publish time, if known.
            retrieval_timestamp: When we fetched the data.
            odds_type: Classification for the produced snapshots.
            price_key: Which nested price to read ("opening" or "last_seen").
            source: Source tag stamped on each snapshot.

        Returns:
            List of OddsSnapshot (one per bookmaker/market/selection/line).
        """
        data = (payload or {}).get("data", {}) if isinstance(payload, dict) else {}
        bookmakers = data.get("bookmakers") or []
        snapshots: list[OddsSnapshot] = []

        for bk in bookmakers:
            if not isinstance(bk, dict):
                continue
            bookmaker = str(bk.get("bookmaker", "")) or "unknown"
            markets = bk.get("markets") or {}
            if not isinstance(markets, dict):
                continue

            snapshots.extend(self._extract_total_goals(
                markets.get("total_goals"), fixture_id, bookmaker, price_key,
                snapshot_timestamp, source_timestamp, retrieval_timestamp,
                odds_type, source,
            ))
            snapshots.extend(self._extract_1x2(
                markets.get("match_odds"), fixture_id, bookmaker, price_key,
                snapshot_timestamp, source_timestamp, retrieval_timestamp,
                odds_type, source,
            ))
            snapshots.extend(self._extract_btts(
                markets.get("btts"), fixture_id, bookmaker, price_key,
                snapshot_timestamp, source_timestamp, retrieval_timestamp,
                odds_type, source,
            ))

        return snapshots

    def _mk(self, *, fixture_id, market, selection, line, odds, bookmaker,
            price_key, snapshot_timestamp, source_timestamp, retrieval_timestamp,
            odds_type, source) -> Optional[OddsSnapshot]:
        if odds is None:
            return None
        try:
            return OddsSnapshot(
                fixture_id=fixture_id,
                market=market,
                selection=selection,
                line=float(line),
                decimal_odds=odds,
                source=source,
                bookmaker=f"{bookmaker}:{price_key}",
                snapshot_timestamp=snapshot_timestamp,
                source_timestamp=source_timestamp,
                retrieval_timestamp=retrieval_timestamp,
                odds_type=odds_type,
            )
        except ValueError:
            # OddsSnapshot enforces decimal_odds >= 1.0; safe_decimal_odds
            # already filters, so this is defensive only.
            return None

    def _extract_total_goals(self, node, fixture_id, bookmaker, price_key,
                             sts, src_ts, ret_ts, odds_type, source):
        out: list[OddsSnapshot] = []
        if not isinstance(node, dict):
            return out
        for line_key, sides in node.items():
            try:
                line = float(line_key)
            except (TypeError, ValueError):
                continue
            if not isinstance(sides, dict):
                continue
            over = _price_of(sides.get("over"), price_key)
            under = _price_of(sides.get("under"), price_key)
            for sel, odds in ((OddsSelection.OVER, over), (OddsSelection.UNDER, under)):
                snap = self._mk(
                    fixture_id=fixture_id, market=_GOALS_MARKET, selection=sel,
                    line=line, odds=odds, bookmaker=bookmaker, price_key=price_key,
                    snapshot_timestamp=sts, source_timestamp=src_ts,
                    retrieval_timestamp=ret_ts, odds_type=odds_type, source=source,
                )
                if snap is not None:
                    out.append(snap)
        return out

    def _extract_1x2(self, node, fixture_id, bookmaker, price_key,
                     sts, src_ts, ret_ts, odds_type, source):
        out: list[OddsSnapshot] = []
        if not isinstance(node, dict):
            return out
        for key, sel in _1X2_SELECTION.items():
            odds = _price_of(node.get(key), price_key)
            snap = self._mk(
                fixture_id=fixture_id, market=_MATCH_RESULT_MARKET, selection=sel,
                line=0.0, odds=odds, bookmaker=bookmaker, price_key=price_key,
                snapshot_timestamp=sts, source_timestamp=src_ts,
                retrieval_timestamp=ret_ts, odds_type=odds_type, source=source,
            )
            if snap is not None:
                out.append(snap)
        return out

    def _extract_btts(self, node, fixture_id, bookmaker, price_key,
                      sts, src_ts, ret_ts, odds_type, source):
        out: list[OddsSnapshot] = []
        if not isinstance(node, dict):
            return out
        for key, sel in _BTTS_SELECTION.items():
            odds = _price_of(node.get(key), price_key)
            snap = self._mk(
                fixture_id=fixture_id, market=_BTTS_MARKET, selection=sel,
                line=0.0, odds=odds, bookmaker=bookmaker, price_key=price_key,
                snapshot_timestamp=sts, source_timestamp=src_ts,
                retrieval_timestamp=ret_ts, odds_type=odds_type, source=source,
            )
            if snap is not None:
                out.append(snap)
        return out
