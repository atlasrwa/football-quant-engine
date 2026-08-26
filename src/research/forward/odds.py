"""Odds Snapshot Model — immutable odds observations for forward research.

Temporal Rule:
    If odds are used for a prediction:
        odds_timestamp <= prediction_timestamp < kickoff_timestamp

    Closing odds are captured AFTER kickoff for CLV analysis only.
    Closing odds must NEVER influence predictions or original EV calculations.

Multiple snapshots are preserved — never overwritten.
Multiple bookmakers/sources supported.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class OddsSelection(Enum):
    """Market selection types."""
    OVER = "OVER"
    UNDER = "UNDER"
    HOME = "HOME"
    DRAW = "DRAW"
    AWAY = "AWAY"
    YES = "YES"
    NO = "NO"


class OddsType(Enum):
    """Classification of when odds were captured."""
    PRE_MATCH = "PRE_MATCH"      # Available before kickoff
    CLOSING = "CLOSING"          # Final odds at/near kickoff
    IN_PLAY = "IN_PLAY"          # During match (not used for predictions)


@dataclass(frozen=True)
class OddsSnapshot:
    """Immutable odds observation at a point in time.

    Multiple snapshots per fixture are preserved:
        10:00 → 2.05
        12:00 → 2.10
        14:00 → 2.08
        15:30 → 2.02  (closing)
        16:00 kickoff

    Never overwrite historical snapshots.

    Attributes:
        fixture_id: Which fixture these odds are for.
        market: Market type (e.g., "CORNERS_TOTAL", "GOALS_TOTAL").
        selection: Market selection (OVER, UNDER, HOME, etc.).
        line: Market line (e.g., 9.5 for over/under corners).
        decimal_odds: Decimal odds value (must be >= 1.0).
        source: Odds source/provider identifier.
        bookmaker: Specific bookmaker (if known).
        snapshot_timestamp: When this observation was recorded (our system time).
        source_timestamp: When the source reports these odds were published.
        retrieval_timestamp: When we retrieved this data from the API.
        odds_type: Classification (PRE_MATCH, CLOSING).
    """
    fixture_id: str
    market: str
    selection: OddsSelection
    line: float
    decimal_odds: float
    source: str = ""
    bookmaker: str = ""
    snapshot_timestamp: float = 0.0
    source_timestamp: Optional[float] = None
    retrieval_timestamp: float = 0.0
    odds_type: OddsType = OddsType.PRE_MATCH

    def __post_init__(self) -> None:
        """Validate odds constraints."""
        if self.decimal_odds < 1.0:
            raise ValueError(
                f"Decimal odds must be >= 1.0, got {self.decimal_odds}"
            )

    @property
    def odds_snapshot_id(self) -> str:
        """Deterministic identity for this snapshot."""
        canonical = json.dumps({
            "fixture_id": self.fixture_id,
            "market": self.market,
            "selection": self.selection.value,
            "line": self.line,
            "decimal_odds": self.decimal_odds,
            "source": self.source,
            "bookmaker": self.bookmaker,
            "snapshot_timestamp": self.snapshot_timestamp,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]

    @property
    def content_hash(self) -> str:
        """Full content hash."""
        return self.odds_snapshot_id

    @property
    def implied_probability(self) -> float:
        """Implied probability from decimal odds (1/odds)."""
        if self.decimal_odds <= 0:
            return 0.0
        return 1.0 / self.decimal_odds

    @property
    def is_closing(self) -> bool:
        """Whether this is a closing odds snapshot."""
        return self.odds_type == OddsType.CLOSING

    def is_valid_for_prediction(self, prediction_timestamp: float) -> bool:
        """Check if these odds can be used for a prediction at the given time.

        Rule: odds must have been available BEFORE or AT prediction time.
        Uses snapshot_timestamp (our observation time) as the reference.
        """
        effective_time = self.source_timestamp or self.snapshot_timestamp
        return effective_time <= prediction_timestamp

    def to_dict(self) -> dict[str, Any]:
        return {
            "odds_snapshot_id": self.odds_snapshot_id,
            "fixture_id": self.fixture_id,
            "market": self.market,
            "selection": self.selection.value,
            "line": self.line,
            "decimal_odds": self.decimal_odds,
            "implied_probability": round(self.implied_probability, 6),
            "source": self.source,
            "bookmaker": self.bookmaker,
            "snapshot_timestamp": self.snapshot_timestamp,
            "source_timestamp": self.source_timestamp,
            "retrieval_timestamp": self.retrieval_timestamp,
            "odds_type": self.odds_type.value,
            "content_hash": self.content_hash,
        }
