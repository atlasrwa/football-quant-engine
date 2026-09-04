"""Pure cadence, quote-role, and CLV comparison policy.

This module intentionally has no provider, filesystem, scheduler, or database
imports. Orchestrators may use it through dependency injection; the file watcher
must not acquire a direct PostgreSQL dependency merely to consume this policy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Sequence

from src.domain.market import PriceType, QuoteStatus


class CaptureCadence(Enum):
    DAILY = "DAILY"
    EVERY_30_MINUTES = "EVERY_30_MINUTES"
    EVERY_5_TO_10_MINUTES = "EVERY_5_TO_10_MINUTES"
    EVERY_1_TO_2_MINUTES = "EVERY_1_TO_2_MINUTES"
    STOPPED = "STOPPED"


@dataclass(frozen=True, slots=True)
class CaptureWindow:
    cadence: CaptureCadence
    minimum_interval: timedelta
    maximum_interval: timedelta


DAILY_WINDOW = CaptureWindow(CaptureCadence.DAILY, timedelta(days=1), timedelta(days=1))
THIRTY_MINUTE_WINDOW = CaptureWindow(
    CaptureCadence.EVERY_30_MINUTES, timedelta(minutes=30), timedelta(minutes=30)
)
FIVE_TO_TEN_MINUTE_WINDOW = CaptureWindow(
    CaptureCadence.EVERY_5_TO_10_MINUTES, timedelta(minutes=5), timedelta(minutes=10)
)
ONE_TO_TWO_MINUTE_WINDOW = CaptureWindow(
    CaptureCadence.EVERY_1_TO_2_MINUTES, timedelta(minutes=1), timedelta(minutes=2)
)
STOPPED_WINDOW = CaptureWindow(CaptureCadence.STOPPED, timedelta(0), timedelta(0))


def _aware(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value.astimezone(timezone.utc)


def capture_window_for(now: datetime, kickoff_at: datetime) -> CaptureWindow:
    """Return the escalation window for a fixture.

    More than 24h out captures daily; 6-24h uses 30m; 1-6h uses 5-10m;
    the final hour uses 1-2m. Capture scheduling stops at kickoff.
    """
    remaining = _aware(kickoff_at, "kickoff_at") - _aware(now, "now")
    if remaining <= timedelta(0):
        return STOPPED_WINDOW
    if remaining > timedelta(hours=24):
        return DAILY_WINDOW
    if remaining > timedelta(hours=6):
        return THIRTY_MINUTE_WINDOW
    if remaining > timedelta(hours=1):
        return FIVE_TO_TEN_MINUTE_WINDOW
    return ONE_TO_TWO_MINUTE_WINDOW


@dataclass(frozen=True, slots=True)
class QuoteForClassification:
    """Minimal immutable input needed to classify a retained quote."""

    quote_hash: str
    observed_at: datetime
    bookmaker: str
    odds: float
    quote_status: QuoteStatus = QuoteStatus.ACTIVE

    @property
    def eligible(self) -> bool:
        return self.quote_status == QuoteStatus.ACTIVE and self.odds > 1.0


@dataclass(frozen=True, slots=True)
class QuoteClassification:
    quote: QuoteForClassification
    price_type: PriceType
    roles: tuple[PriceType, ...]
    clv_eligible: bool


def classify_quote_series(
    quotes: Sequence[QuoteForClassification],
    kickoff_at: datetime,
    *,
    entry_quote_hash: str | None = None,
) -> tuple[QuoteClassification, ...]:
    """Classify every retained quote without mutating or dropping observations.

    The first eligible pre-match quote is OPENING, a selected decision quote is
    ENTRY, and the final eligible quote strictly before kickoff is CLOSING.
    Intermediate retained quotes are SNAPSHOT. Quotes at/after kickoff are LIVE
    and never CLV-eligible. ``roles`` preserves overlapping roles (for example a
    single pre-match quote can be both opening and closing).
    """
    cutoff = _aware(kickoff_at, "kickoff_at")
    eligible_pre = sorted(
        (
            quote
            for quote in quotes
            if _aware(quote.observed_at, "observed_at") < cutoff and quote.eligible
        ),
        key=lambda quote: (_aware(quote.observed_at, "observed_at"), quote.quote_hash),
    )
    opening_hash = eligible_pre[0].quote_hash if eligible_pre else None
    closing_hash = eligible_pre[-1].quote_hash if eligible_pre else None

    results: list[QuoteClassification] = []
    for quote in quotes:
        observed = _aware(quote.observed_at, "observed_at")
        if observed >= cutoff:
            results.append(QuoteClassification(quote, PriceType.LIVE, (PriceType.LIVE,), False))
            continue

        roles: list[PriceType] = []
        if quote.eligible and quote.quote_hash == opening_hash:
            roles.append(PriceType.OPENING)
        if quote.eligible and entry_quote_hash is not None and quote.quote_hash == entry_quote_hash:
            roles.append(PriceType.ENTRY)
        if quote.eligible and quote.quote_hash == closing_hash:
            roles.append(PriceType.CLOSING)

        if PriceType.ENTRY in roles:
            primary = PriceType.ENTRY
        elif PriceType.CLOSING in roles and opening_hash != closing_hash:
            primary = PriceType.CLOSING
        elif PriceType.OPENING in roles:
            primary = PriceType.OPENING
        else:
            primary = PriceType.SNAPSHOT
        results.append(QuoteClassification(quote, primary, tuple(roles) or (primary,), quote.eligible))
    return tuple(results)


class CLVComparisonLabel(Enum):
    SAME_BOOK_CLV = "SAME_BOOK_CLV"
    CROSS_BOOK_CLV = "CROSS_BOOK_CLV"


def clv_comparison_label(
    entry_bookmaker: str, closing_bookmaker: str
) -> CLVComparisonLabel:
    """Label CLV explicitly; cross-book movement must not masquerade as same-book."""
    if not entry_bookmaker or not closing_bookmaker:
        raise ValueError("Both entry and closing bookmakers are required")
    if entry_bookmaker.casefold() == closing_bookmaker.casefold():
        return CLVComparisonLabel.SAME_BOOK_CLV
    return CLVComparisonLabel.CROSS_BOOK_CLV
