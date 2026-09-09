"""Odds capture semantics and de-vigging (collection kept independent).

The live ``/odds`` endpoint returns, per bookmaker, a nested markets object.
Every price object carries ``opening`` (nullable) and ``last_seen`` — and
crucially NO timestamp. Therefore:

- ``opening`` may be used AS AN OPENING PRICE only.
- ``last_seen`` is NOT a genuine closing line and must never be labelled one.
- A genuine research close is derived ONLY from our own timestamped snapshots
  with ``observed_at < kickoff`` (i.e. the latest prospective snapshot before
  kickoff). See :func:`genuine_close`.

De-vigging is deliberately kept separate from collection: we store raw decimal
odds per (bookmaker, market, selection, line) and de-vig on demand using the
existing multiplicative / Shin methods in
``src.research.reconciliation.devig``. We never pick the most favourable
bookmaker price; a preregistered benchmark hierarchy is used instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping, Optional

from src.research.prospective.api_contract import (
    OVER_UNDER_MARKET_KEYS,
    THREE_WAY_MARKET_KEYS,
    YES_NO_MARKET_KEYS,
)
from src.research.reconciliation.devig import DevigResult, devig


class OddsSemantics(str, Enum):
    """How a captured price relates to time. Never conflate these."""

    #: The API's own ``opening`` field: first pre-match sighting. Use as opening.
    API_OPENING = "API_OPENING"
    #: The API's own ``last_seen`` field: latest sighting, NO timestamp.
    #: NOT a genuine close.
    API_LAST_SEEN = "API_LAST_SEEN"
    #: A snapshot we captured at a known ``observed_at`` (our own timestamp).
    PROSPECTIVE_SNAPSHOT = "PROSPECTIVE_SNAPSHOT"
    #: The latest of OUR snapshots with observed_at < kickoff: a genuine close.
    PROSPECTIVE_LAST_BEFORE_KICKOFF = "PROSPECTIVE_LAST_BEFORE_KICKOFF"


#: Preregistered benchmark hierarchy for research de-vig. Sharpest first.
#: Availability is NOT hard-coded: we fall through this order and take the
#: first bookmaker that actually priced the market. This is fixed in advance
#: to prevent best-price cherry-picking.
BENCHMARK_HIERARCHY: tuple[str, ...] = ("pinnacle", "bet365", "betmgm-uk", "paddy-power")


@dataclass(frozen=True)
class CapturedPrice:
    """One raw decimal price for a (bookmaker, market, selection, line)."""

    bookmaker: str
    market: str
    selection: str
    line: Optional[float]
    decimal_odds: float
    semantics: OddsSemantics
    observed_at: Optional[float]
    provider_payload_hash: str

    @property
    def concept(self) -> str:
        """Stable concept string used as the observation concept."""
        line = "" if self.line is None else f":{self.line}"
        return f"odds:{self.market}:{self.selection}{line}"


def _bookmaker_slug(name: str) -> str:
    """Normalize a provider bookmaker display name to its slug."""
    return name.strip().lower().replace(" ", "-")


def _price_from_value(value: Mapping[str, Any], field: str) -> Optional[float]:
    """Parse a decimal-odds string (or number) from an OddsValue field.

    Returns None when absent/null — NEVER coerced to zero.
    """
    raw = value.get(field)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def iter_over_under_prices(
    bookmaker: str,
    market: str,
    lines: Mapping[str, Any],
    *,
    payload_hash: str,
    field: str = "last_seen",
    semantics: OddsSemantics = OddsSemantics.API_LAST_SEEN,
    observed_at: Optional[float] = None,
) -> Iterable[CapturedPrice]:
    """Yield over/under prices for a ``Map<line, OverUnderOdds>`` market.

    ``field`` selects which native price to read (``opening`` or ``last_seen``)
    and MUST be paired with the matching ``semantics``. Missing sides are
    skipped (never zero-filled).
    """
    for line_key, ou in lines.items():
        if not isinstance(ou, Mapping):
            continue
        try:
            line_val: Optional[float] = float(line_key)
        except (TypeError, ValueError):
            line_val = None
        for sel in ("over", "under"):
            val = ou.get(sel)
            if not isinstance(val, Mapping):
                continue
            price = _price_from_value(val, field)
            if price is None:
                continue
            yield CapturedPrice(
                bookmaker=_bookmaker_slug(bookmaker),
                market=market,
                selection=sel,
                line=line_val,
                decimal_odds=price,
                semantics=semantics,
                observed_at=observed_at,
                provider_payload_hash=payload_hash,
            )


def extract_prices(
    odds_payload: Mapping[str, Any],
    *,
    payload_hash: str,
    field: str = "last_seen",
    semantics: OddsSemantics = OddsSemantics.API_LAST_SEEN,
    observed_at: Optional[float] = None,
    markets: Iterable[str] = OVER_UNDER_MARKET_KEYS,
) -> list[CapturedPrice]:
    """Extract per-selection prices from a verified ``/odds`` payload.

    Stores each bookmaker/market/selection/line separately. Only the over/under
    markets are extracted by default (goals/corners/cards/shots), which is the
    scope this research plane evaluates. The extraction is defensive: unknown
    or absent shapes are skipped, never guessed.
    """
    data = odds_payload.get("data", odds_payload)
    out: list[CapturedPrice] = []
    if not isinstance(data, Mapping):
        return out
    for bm in data.get("bookmakers", []):
        if not isinstance(bm, Mapping):
            continue
        name = bm.get("bookmaker", "")
        market_obj = bm.get("markets", {})
        if not isinstance(market_obj, Mapping):
            continue
        for market in markets:
            lines = market_obj.get(market)
            if not isinstance(lines, Mapping):
                continue
            out.extend(
                iter_over_under_prices(
                    name,
                    market,
                    lines,
                    payload_hash=payload_hash,
                    field=field,
                    semantics=semantics,
                    observed_at=observed_at,
                )
            )
    return out


@dataclass(frozen=True)
class GenuineClose:
    """The genuine research close for a (market, selection, line, bookmaker)."""

    price: CapturedPrice
    kickoff_ts: float

    @property
    def observed_at(self) -> Optional[float]:
        return self.price.observed_at


def genuine_close(
    snapshots: Iterable[CapturedPrice],
    *,
    kickoff_ts: float,
) -> Optional[GenuineClose]:
    """Derive a genuine close from OUR OWN timestamped snapshots.

    Requires:
    - a known kickoff time, and
    - at least one snapshot with ``observed_at`` strictly before kickoff.

    Returns the latest such snapshot (max observed_at < kickoff), relabelled
    ``PROSPECTIVE_LAST_BEFORE_KICKOFF``. Returns None if no snapshot qualifies —
    we never fall back to ``last_seen``.
    """
    eligible = [
        s
        for s in snapshots
        if s.observed_at is not None
        and s.semantics
        in (OddsSemantics.PROSPECTIVE_SNAPSHOT, OddsSemantics.PROSPECTIVE_LAST_BEFORE_KICKOFF)
        and s.observed_at < kickoff_ts
    ]
    if not eligible:
        return None
    latest = max(eligible, key=lambda s: s.observed_at)  # type: ignore[arg-type]
    relabelled = CapturedPrice(
        bookmaker=latest.bookmaker,
        market=latest.market,
        selection=latest.selection,
        line=latest.line,
        decimal_odds=latest.decimal_odds,
        semantics=OddsSemantics.PROSPECTIVE_LAST_BEFORE_KICKOFF,
        observed_at=latest.observed_at,
        provider_payload_hash=latest.provider_payload_hash,
    )
    return GenuineClose(price=relabelled, kickoff_ts=kickoff_ts)


class CloseStatus(str, Enum):
    """Outcome of attempting to construct a genuine research close."""

    GENUINE_CLOSE = "GENUINE_CLOSE"
    NO_GENUINE_CLOSE = "NO_GENUINE_CLOSE"


@dataclass(frozen=True)
class CloseResult:
    """Explicit result of a genuine-close attempt (reason on failure)."""

    status: CloseStatus
    close: Optional[GenuineClose]
    reason: Optional[str]


def resolve_genuine_close(
    snapshots: Iterable[CapturedPrice],
    *,
    kickoff_ts: Optional[float],
    bookmaker: str,
    market: str,
    selection: str,
    line: Optional[float],
) -> CloseResult:
    """Resolve a genuine close for one (book, market, selection, line) key.

    Returns an EXPLICIT status. A genuine close requires: a known kickoff, at
    least one of OUR prospective snapshots for the EXACT key with
    ``observed_at < kickoff``. Never falls back to the provider ``last_seen``.

    Failure reasons are surfaced (never silently None-with-no-context):
    - unknown kickoff              -> NO_GENUINE_CLOSE
    - no matching-key snapshot     -> NO_GENUINE_CLOSE
    - no pre-kickoff snapshot      -> NO_GENUINE_CLOSE
    """
    if kickoff_ts is None:
        return CloseResult(CloseStatus.NO_GENUINE_CLOSE, None, "unknown_kickoff")

    book = _bookmaker_slug(bookmaker)
    keyed = [
        s
        for s in snapshots
        if _bookmaker_slug(s.bookmaker) == book
        and s.market == market
        and s.selection == selection
        and s.line == line
    ]
    if not keyed:
        return CloseResult(CloseStatus.NO_GENUINE_CLOSE, None, "no_matching_key_snapshot")

    close = genuine_close(keyed, kickoff_ts=kickoff_ts)
    if close is None:
        return CloseResult(CloseStatus.NO_GENUINE_CLOSE, None, "no_pre_kickoff_snapshot")
    return CloseResult(CloseStatus.GENUINE_CLOSE, close, None)


def select_benchmark_bookmaker(
    available: Iterable[str],
    *,
    hierarchy: tuple[str, ...] = BENCHMARK_HIERARCHY,
) -> Optional[str]:
    """Pick the benchmark bookmaker by the preregistered hierarchy.

    Returns the first hierarchy entry present in ``available`` — NEVER the most
    favourable price. Returns None if none of the ranked books are available.
    """
    present = {_bookmaker_slug(b) for b in available}
    for book in hierarchy:
        if book in present:
            return book
    return None


def devig_two_way(
    over_odds: float,
    under_odds: float,
    *,
    method: str = "multiplicative",
) -> DevigResult:
    """De-vig an over/under pair using the existing devig engine.

    De-vigging is independent of collection: it operates on stored decimal
    odds and does not mutate them.
    """
    return devig({"OVER": over_odds, "UNDER": under_odds}, method=method)


def market_over_probability(
    over_odds: float,
    under_odds: float,
    *,
    method: str = "multiplicative",
) -> float:
    """Fair (no-vig) probability of OVER for an over/under pair."""
    return devig_two_way(over_odds, under_odds, method=method).fair_probabilities["OVER"]
