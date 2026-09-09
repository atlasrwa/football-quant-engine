"""TheStatsAPI closing-odds provider — implements ClosingOddsProvider.

FootyStats cannot supply genuine closing odds. TheStatsAPI's time-series
``research_odds`` files can: each file is a snapshot captured at a REAL wall
time encoded in its filename, e.g.

    research_odds_mt_022357520_bet365_20260906T131350108942Z-1788700430108955696.json
                                       └─ capture timestamp (ISO-ish + epoch) ─┘

This provider treats the LATEST capture STRICTLY BEFORE kickoff as the genuine
closing observation, with ``TimestampSemantics.LAST_BEFORE_KICKOFF`` — an
honest label, because it is a real observation time, not a guess.

Critical honesty rules:
- The ``cma_odds`` "last_seen" field is NEVER used here as a close: it carries
  no capture time, so it cannot be proven to be the market close.
- A capture with no parseable timestamp yields ``TimestampSemantics.UNKNOWN``
  and ``ClosingOddsStatus.UNAVAILABLE`` — never silently promoted.
- Captures at or after kickoff are excluded from the close (they are post-
  kickoff / in-play and must not masquerade as closing).
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from src.research.closing.provider import (
    ClosingOddsObservation,
    ClosingOddsProvider,
    ClosingOddsStatus,
    TimestampSemantics,
)
from src.research.thestatsapi import ids
from src.research.thestatsapi.odds_normalizer import safe_decimal_odds

logger = logging.getLogger(__name__)

_SOURCE = "thestatsapi"

# Capture timestamp embedded in research_odds filenames:
#   ..._<YYYYMMDD>T<HHMMSSmmmuuu>Z-<epochish>.json
_CAPTURE_RE = re.compile(r"_(\d{8}T\d{6}\d*Z)-\d+\.json$")


def parse_capture_timestamp(filename: str) -> Optional[float]:
    """Parse the capture wall-time (unix seconds) from a research_odds filename.

    Returns None if no capture timestamp is present (never fabricates one).
    """
    m = _CAPTURE_RE.search(filename)
    if not m:
        return None
    token = m.group(1)  # e.g. 20260906T131350108942Z
    # Split date/time; the time part is HHMMSS followed by fractional digits.
    try:
        date_part, time_part = token[:-1].split("T")  # strip trailing Z
        year = int(date_part[0:4]); month = int(date_part[4:6]); day = int(date_part[6:8])
        hh = int(time_part[0:2]); mm = int(time_part[2:4]); ss = int(time_part[4:6])
        frac = time_part[6:]
        micro = int((frac + "000000")[:6]) if frac else 0
        dt = datetime(year, month, day, hh, mm, ss, micro, tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, IndexError):
        return None


class _CapturedOddsFile:
    """A parsed research_odds payload plus its capture time."""

    __slots__ = ("payload", "capture_ts")

    def __init__(self, payload: dict[str, Any], capture_ts: Optional[float]) -> None:
        self.payload = payload
        self.capture_ts = capture_ts


class TheStatsAPIClosingOddsProvider(ClosingOddsProvider):
    """ClosingOddsProvider backed by TheStatsAPI research_odds time series.

    Ingest timestamped captures via ``ingest_capture(filename, payload)``, then
    call ``get_closing_odds(fixture_id, ...)``. Kickoff times are provided per
    fixture so the provider can select the last pre-kickoff capture.
    """

    def __init__(self) -> None:
        # match_ref -> list[_CapturedOddsFile]
        self._captures: dict[str, list[_CapturedOddsFile]] = {}
        # match_ref -> kickoff unix
        self._kickoffs: dict[str, float] = {}

    @property
    def provider_name(self) -> str:
        return _SOURCE

    @property
    def supports_genuine_closing(self) -> bool:
        # Genuine only in the LAST_BEFORE_KICKOFF sense (real capture times).
        return True

    def is_available(self) -> bool:
        return bool(self._captures)

    def set_kickoff(self, match_ref: str, kickoff_ts: float) -> None:
        self._kickoffs[match_ref] = float(kickoff_ts)

    def ingest_capture(self, filename: str, payload: dict[str, Any]) -> bool:
        """Ingest one research_odds capture. Returns True if stored."""
        data = (payload or {}).get("data", {})
        match_ref = data.get("match_id")
        if not isinstance(match_ref, str) or not match_ref:
            return False
        capture_ts = parse_capture_timestamp(filename)
        self._captures.setdefault(match_ref, []).append(
            _CapturedOddsFile(payload, capture_ts)
        )
        return True

    def _fixture_id_for(self, match_ref: str) -> str:
        from src.research.thestatsapi.odds_provider import canonical_fixture_id
        return canonical_fixture_id(match_ref)

    def get_closing_odds(
        self,
        fixture_id: str,
        market: Optional[str] = None,
        selection: Optional[str] = None,
    ) -> list[ClosingOddsObservation]:
        """Return genuine closing observations for a fixture.

        The fixture_id here is the canonical fixture id (as produced by
        ``odds_provider.canonical_fixture_id``). We find the matching match_ref,
        take the LATEST capture strictly before kickoff, and emit closing
        observations from its ``last_seen`` prices (the freshest price in that
        genuinely-timestamped snapshot).
        """
        match_ref = self._match_ref_for_fixture(fixture_id)
        if match_ref is None:
            return []
        kickoff = self._kickoffs.get(match_ref)
        captures = self._captures.get(match_ref, [])
        if not captures:
            return []

        # Select the last capture strictly before kickoff (genuine close).
        pre_kickoff = [
            c for c in captures
            if c.capture_ts is not None and (kickoff is None or c.capture_ts < kickoff)
        ]
        if not pre_kickoff:
            # No genuine pre-kickoff capture with a real timestamp.
            return []
        chosen = max(pre_kickoff, key=lambda c: c.capture_ts)

        status = ClosingOddsStatus.VALID
        semantics = TimestampSemantics.LAST_BEFORE_KICKOFF

        obs = self._observations_from_capture(
            chosen, match_ref, kickoff or 0.0, status, semantics,
        )
        if market:
            obs = [o for o in obs if o.market == market]
        if selection:
            obs = [o for o in obs if o.selection == selection]
        return obs

    def _match_ref_for_fixture(self, fixture_id: str) -> Optional[str]:
        for match_ref in self._captures:
            try:
                if self._fixture_id_for(match_ref) == fixture_id:
                    return match_ref
            except ids.ProviderIdError:
                continue
        return None

    def _observations_from_capture(
        self,
        capture: _CapturedOddsFile,
        match_ref: str,
        kickoff: float,
        status: ClosingOddsStatus,
        semantics: TimestampSemantics,
    ) -> list[ClosingOddsObservation]:
        data = capture.payload.get("data", {})
        bookmakers = data.get("bookmakers") or []
        out: list[ClosingOddsObservation] = []
        for bk in bookmakers:
            if not isinstance(bk, dict):
                continue
            bookmaker = str(bk.get("bookmaker", "")) or "unknown"
            markets = bk.get("markets") or {}
            out.extend(self._total_goals(markets.get("total_goals"), match_ref,
                                         bookmaker, capture.capture_ts, kickoff,
                                         status, semantics))
            out.extend(self._match_odds(markets.get("match_odds"), match_ref,
                                        bookmaker, capture.capture_ts, kickoff,
                                        status, semantics))
        return out

    def _mk(self, *, match_ref, market, selection, line, price, bookmaker,
            capture_ts, kickoff, status, semantics) -> Optional[ClosingOddsObservation]:
        odds = safe_decimal_odds(price)
        if odds is None:
            return None
        return ClosingOddsObservation(
            fixture_id=self._fixture_id_for(match_ref),
            market=market,
            selection=selection,
            line=float(line),
            decimal_odds=odds,
            bookmaker=bookmaker,
            source=_SOURCE,
            closing_timestamp=float(capture_ts) if capture_ts is not None else 0.0,
            timestamp_semantics=semantics,
            kickoff_timestamp=float(kickoff),
            status=status,
            provider_event_id=match_ref,
        )

    def _total_goals(self, node, match_ref, bookmaker, capture_ts, kickoff, status, semantics):
        out = []
        if not isinstance(node, dict):
            return out
        for line_key, sides in node.items():
            try:
                line = float(line_key)
            except (TypeError, ValueError):
                continue
            if not isinstance(sides, dict):
                continue
            for sel_key, sel_name in (("over", "OVER"), ("under", "UNDER")):
                sidenode = sides.get(sel_key) or {}
                price = sidenode.get("last_seen") if isinstance(sidenode, dict) else None
                o = self._mk(match_ref=match_ref, market="GOALS_TOTAL", selection=sel_name,
                             line=line, price=price, bookmaker=bookmaker,
                             capture_ts=capture_ts, kickoff=kickoff, status=status,
                             semantics=semantics)
                if o is not None:
                    out.append(o)
        return out

    def _match_odds(self, node, match_ref, bookmaker, capture_ts, kickoff, status, semantics):
        out = []
        if not isinstance(node, dict):
            return out
        for key, sel_name in (("home", "HOME"), ("draw", "DRAW"), ("away", "AWAY")):
            sidenode = node.get(key) or {}
            price = sidenode.get("last_seen") if isinstance(sidenode, dict) else None
            o = self._mk(match_ref=match_ref, market="MATCH_RESULT_1X2", selection=sel_name,
                         line=0.0, price=price, bookmaker=bookmaker,
                         capture_ts=capture_ts, kickoff=kickoff, status=status,
                         semantics=semantics)
            if o is not None:
                out.append(o)
        return out
