"""Market domain types.

MarketDefinition = the abstract betting market (e.g., "Over/Under 2.5 Goals")
MarketPrice = a specific price observation at a point in time

These separate the WHAT (market type + line) from the WHEN (specific odds snapshot).
This is critical for CLV: we need to compare entry price vs closing price
for the SAME market definition.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
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
    """When this price was observed."""

    OPENING = "OPENING"
    ENTRY = "ENTRY"
    CLOSING = "CLOSING"
    LIVE = "LIVE"


@dataclass(frozen=True, slots=True)
class MarketDefinition:
    """Immutable definition of a betting market.

    Represents the abstract market (type + line) independent of any
    specific match or price observation.

    Attributes:
        market_type: Type of market (OVER_UNDER, MATCH_RESULT, etc.).
        line: The market line (e.g., 2.5 for Over/Under 2.5 Goals).
                None for markets without lines (e.g., BTTS).
        description: Human-readable market description.
    """

    market_type: MarketType
    line: float | None
    description: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "market_type": self.market_type.value,
            "line": self.line,
            "description": self.description,
        }

    @property
    def content_hash(self) -> str:
        """Deterministic hash of market definition."""
        canonical = json.dumps({
            "market_type": self.market_type.value,
            "line": self.line,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class MarketPrice:
    """A specific price observation for a market at a point in time.

    Attributes:
        match_id: The match this price is for.
        market_type: Type of market.
        line: Market line (if applicable).
        side: Which side of the market (OVER/UNDER/HOME/etc.).
        price_type: When observed (OPENING/ENTRY/CLOSING/LIVE).
        odds: Decimal odds (must be > 1.0).
        timestamp: Unix timestamp of the price observation.
        source: Where the price came from (e.g., "pinnacle", "bet365").
    """

    match_id: int
    market_type: MarketType
    line: float | None
    side: PriceSide
    price_type: PriceType
    odds: float
    timestamp: int
    source: str | None

    def __post_init__(self) -> None:
        """Validate price invariants."""
        if self.odds <= 1.0:
            raise ValueError(
                f"Odds must be > 1.0, got {self.odds}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "match_id": self.match_id,
            "market_type": self.market_type.value,
            "line": self.line,
            "side": self.side.value,
            "price_type": self.price_type.value,
            "odds": self.odds,
            "timestamp": self.timestamp,
            "source": self.source,
        }

    @property
    def is_valid(self) -> bool:
        """Whether this price is valid for use in calculations."""
        return self.odds > 1.0

    @property
    def implied_probability(self) -> float:
        """Implied probability from the decimal odds (1/odds)."""
        return 1.0 / self.odds
