"""Immutable market definitions and price observations with capture provenance."""

from __future__ import annotations

import hashlib
import json
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class MarketType(Enum):
    """Supported betting market types."""

    OVER_UNDER = "OVER_UNDER"
    MATCH_RESULT = "MATCH_RESULT"
    BOTH_TEAMS_TO_SCORE = "BTTS"
    ASIAN_HANDICAP = "ASIAN_HANDICAP"
    CORNERS_OVER_UNDER = "CORNERS_OVER_UNDER"
    CARDS_OVER_UNDER = "CARDS_OVER_UNDER"


class PriceSide(Enum):
    """Which side of the market this price represents."""

    OVER = "OVER"
    UNDER = "UNDER"
    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"
    YES = "YES"
    NO = "NO"


class PriceType(Enum):
    """Role of an immutable quote in the price timeline."""

    OPENING = "OPENING"
    SNAPSHOT = "SNAPSHOT"
    ENTRY = "ENTRY"
    CLOSING = "CLOSING"
    LIVE = "LIVE"


class QuoteStatus(Enum):
    """Provider-reported availability of a captured quote."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    CLOSED = "CLOSED"
    UNAVAILABLE = "UNAVAILABLE"
    UNKNOWN = "UNKNOWN"


class TimestampSemantics(Enum):
    """Meaning of ``timestamp``/``observed_at`` for a quote."""

    PROVIDER_SOURCE_TIME = "PROVIDER_SOURCE_TIME"
    RETRIEVAL_TIME = "RETRIEVAL_TIME"
    EXACT_CLOSE = "EXACT_CLOSE"
    LAST_BEFORE_KICKOFF = "LAST_BEFORE_KICKOFF"
    PROVIDER_ESTIMATED = "PROVIDER_ESTIMATED"


def _enum_value(value: Enum | str | None) -> str | None:
    return value.value if isinstance(value, Enum) else value


def _timestamp_microseconds(value: datetime | int | float) -> int:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Quote timestamps must be timezone-aware")
        utc = value.astimezone(timezone.utc)
        epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
        delta = utc - epoch
        return (
            delta.days * 86_400_000_000
            + delta.seconds * 1_000_000
            + delta.microseconds
        )
    if isinstance(value, int):
        return value * 1_000_000
    return round(value * 1_000_000)


def _hash_text(value: str | None) -> bytes:
    if value is None:
        return struct.pack("!i", -1)
    encoded = value.encode()
    return struct.pack("!i", len(encoded)) + encoded


def compute_raw_payload_hash(raw_payload: Any) -> str:
    """Return a deterministic SHA-256 hash for a JSON-compatible payload."""
    canonical = json.dumps(
        raw_payload, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def compute_quote_hash(
    *,
    match_id: int,
    market_type: MarketType | str,
    line: float | None,
    side: PriceSide | str,
    odds: float,
    timestamp: datetime | int | float,
    source: str | None,
    bookmaker: str | None = None,
    provider_source_time: datetime | int | float | None = None,
    provider_quote_id: str | None = None,
) -> str:
    """Compute the idempotent identity of one provider quote.

    Classification fields such as ``price_type`` are deliberately excluded: a
    quote's identity must not change when it is later recognized as opening,
    entry, or the last eligible quote before kickoff.
    """
    payload = bytearray(b"market-price-quote-v1")
    payload.extend(struct.pack("!q", match_id))
    payload.extend(_hash_text(_enum_value(market_type)))
    if line is None:
        payload.extend(b"\x00")
    else:
        payload.extend(b"\x01" + struct.pack("!d", line))
    payload.extend(_hash_text(_enum_value(side)))
    payload.extend(struct.pack("!d", odds))
    payload.extend(struct.pack("!q", _timestamp_microseconds(timestamp)))
    payload.extend(_hash_text(source))
    payload.extend(_hash_text(bookmaker or source))
    if provider_source_time is None:
        payload.extend(b"\x00")
    else:
        payload.extend(
            b"\x01"
            + struct.pack("!q", _timestamp_microseconds(provider_source_time))
        )
    payload.extend(_hash_text(provider_quote_id))
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class MarketDefinition:
    """The abstract market (type + exact line), independent of a quote."""

    market_type: MarketType
    line: float | None
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_type": self.market_type.value,
            "line": self.line,
            "description": self.description,
        }

    @property
    def content_hash(self) -> str:
        canonical = json.dumps(
            {"market_type": self.market_type.value, "line": self.line},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class MarketPrice:
    """A captured market quote with deterministic identity and provenance.

    The original positional fields remain unchanged. New provenance fields have
    defaults so existing construction and serialization consumers continue to
    work while new capture paths can supply complete audit metadata.
    """

    match_id: int
    market_type: MarketType
    line: float | None
    side: PriceSide
    price_type: PriceType
    odds: float
    timestamp: int
    source: str | None
    bookmaker: str | None = None
    provider_source_time: int | None = None
    retrieved_at: int | None = None
    quote_status: QuoteStatus = QuoteStatus.ACTIVE
    kickoff_at: int | None = None
    raw_payload_hash: str | None = None
    quote_hash: str | None = None
    capture_run_id: str | None = None
    provider_quote_id: str | None = None
    timestamp_semantics: TimestampSemantics = TimestampSemantics.RETRIEVAL_TIME

    def __post_init__(self) -> None:
        if self.bookmaker is None and self.source is not None:
            object.__setattr__(self, "bookmaker", self.source)
        if self.retrieved_at is None:
            object.__setattr__(self, "retrieved_at", self.timestamp)

        if self.odds <= 1.0:
            raise ValueError(f"Odds must be > 1.0, got {self.odds}")
        if self.provider_source_time is not None:
            if self.provider_source_time > self.retrieved_at:
                raise ValueError("provider_source_time must not be after retrieved_at")
        if self.timestamp > self.retrieved_at:
            raise ValueError("timestamp must not be after retrieved_at")
        if self.kickoff_at is not None:
            if self.price_type == PriceType.LIVE and self.timestamp < self.kickoff_at:
                raise ValueError("LIVE quote must be at or after kickoff")
            if self.price_type != PriceType.LIVE and self.timestamp >= self.kickoff_at:
                raise ValueError("Pre-match quote must be strictly before kickoff")
        if (
            self.timestamp_semantics == TimestampSemantics.PROVIDER_SOURCE_TIME
            and self.provider_source_time is None
        ):
            raise ValueError("PROVIDER_SOURCE_TIME requires provider_source_time")
        if self.raw_payload_hash is not None and len(self.raw_payload_hash) != 64:
            raise ValueError("raw_payload_hash must be a SHA-256 hex digest")

        expected_hash = compute_quote_hash(
            match_id=self.match_id,
            market_type=self.market_type,
            line=self.line,
            side=self.side,
            odds=self.odds,
            timestamp=self.timestamp,
            source=self.source,
            bookmaker=self.bookmaker,
            provider_source_time=self.provider_source_time,
            provider_quote_id=self.provider_quote_id,
        )
        if self.quote_hash is not None and self.quote_hash != expected_hash:
            raise ValueError("quote_hash does not match quote identity")
        object.__setattr__(self, "quote_hash", expected_hash)

    def to_dict(self) -> dict[str, Any]:
        return {
            "match_id": self.match_id,
            "market_type": self.market_type.value,
            "line": self.line,
            "side": self.side.value,
            "price_type": self.price_type.value,
            "odds": self.odds,
            "timestamp": self.timestamp,
            "source": self.source,
            "bookmaker": self.bookmaker,
            "provider_source_time": self.provider_source_time,
            "retrieved_at": self.retrieved_at,
            "quote_status": self.quote_status.value,
            "kickoff_at": self.kickoff_at,
            "raw_payload_hash": self.raw_payload_hash,
            "quote_hash": self.quote_hash,
            "capture_run_id": self.capture_run_id,
            "provider_quote_id": self.provider_quote_id,
            "timestamp_semantics": self.timestamp_semantics.value,
        }

    @property
    def is_valid(self) -> bool:
        return self.odds > 1.0 and self.quote_status == QuoteStatus.ACTIVE

    @property
    def implied_probability(self) -> float:
        return 1.0 / self.odds
