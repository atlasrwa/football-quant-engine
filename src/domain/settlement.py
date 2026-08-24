"""Settlement — outcome resolution for predictions.

Settlement resolves a PredictionEvent against the actual match outcome.
It captures the P&L, CLV (when available), and links back to the prediction.

Settlement is intentionally separate from PredictionEvent because:
1. Settlement happens AFTER the prediction (different lifecycle moment)
2. Settlement requires actual outcome data (match result)
3. CLV requires closing odds (may arrive separately from outcome)
4. A prediction can exist without settlement (pending/expired)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class SettlementOutcome(Enum):
    """The actual outcome that resolves a prediction."""

    WIN = "WIN"
    LOSS = "LOSS"
    VOID = "VOID"       # Match cancelled, bet returned
    PUSH = "PUSH"       # Exactly on the line (Asian handicap)


@dataclass(frozen=True, slots=True)
class Settlement:
    """Immutable settlement record for a resolved prediction.

    Attributes:
        settlement_id: Unique identifier.
        prediction_id: The PredictionEvent being settled.
        match_id: The match that was played.
        outcome: WIN/LOSS/VOID/PUSH.
        actual_total_goals: Actual total goals in the match.
        actual_result: Match result string (e.g., "2-1").
        entry_odds: Odds at prediction time (copied from prediction).
        closing_odds: Actual closing odds (None if unavailable).
        clv_pct: Closing Line Value percentage (None if closing odds unavailable).
        stake: Amount staked.
        profit_loss: Actual P&L for this settlement.
        settled_at: ISO 8601 timestamp of settlement.
    """

    settlement_id: str
    prediction_id: str
    match_id: int
    outcome: SettlementOutcome
    actual_total_goals: int
    actual_result: str
    entry_odds: float | None
    closing_odds: float | None
    clv_pct: float | None
    stake: float
    profit_loss: float
    settled_at: str

    def __post_init__(self) -> None:
        """Validate settlement invariants."""
        if self.entry_odds is not None and self.entry_odds <= 1.0:
            raise ValueError(f"entry_odds must be > 1.0, got {self.entry_odds}")
        if self.closing_odds is not None and self.closing_odds <= 1.0:
            raise ValueError(f"closing_odds must be > 1.0, got {self.closing_odds}")
        if self.stake < 0.0:
            raise ValueError(f"stake must be non-negative, got {self.stake}")

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "settlement_id": self.settlement_id,
            "prediction_id": self.prediction_id,
            "match_id": self.match_id,
            "outcome": self.outcome.value,
            "actual_total_goals": self.actual_total_goals,
            "actual_result": self.actual_result,
            "entry_odds": self.entry_odds,
            "closing_odds": self.closing_odds,
            "clv_pct": self.clv_pct,
            "stake": self.stake,
            "profit_loss": self.profit_loss,
            "settled_at": self.settled_at,
        }

    @property
    def has_clv(self) -> bool:
        """Whether real CLV is available for this settlement."""
        return self.clv_pct is not None

    @property
    def beat_closing_line(self) -> bool | None:
        """Whether entry odds beat the closing line. None if CLV unavailable."""
        if self.clv_pct is None:
            return None
        return self.clv_pct > 0.0

    @staticmethod
    def compute_clv(entry_odds: float | None, closing_odds: float | None) -> float | None:
        """Compute CLV percentage from entry and closing odds.

        CLV = (entry_odds / closing_odds - 1) * 100

        Returns None if either odds value is missing or invalid.
        This delegates to the same logic as CLVCalculator but is
        available as a static utility for Settlement construction.

        Args:
            entry_odds: Decimal odds at entry.
            closing_odds: Decimal odds at market close.

        Returns:
            CLV percentage or None if unavailable.
        """
        if entry_odds is None or closing_odds is None:
            return None
        if entry_odds <= 1.0 or closing_odds <= 1.0:
            return None
        return (entry_odds / closing_odds - 1.0) * 100.0

    @staticmethod
    def compute_profit_loss(
        outcome: SettlementOutcome,
        odds: float | None,
        stake: float,
    ) -> float:
        """Compute P&L for a settlement.

        Args:
            outcome: Settlement outcome.
            odds: Decimal odds (needed for WIN calculation).
            stake: Amount staked.

        Returns:
            Profit/loss value.
        """
        if outcome == SettlementOutcome.WIN:
            if odds is None:
                return 0.0  # Cannot compute without odds
            return stake * (odds - 1.0)
        elif outcome == SettlementOutcome.LOSS:
            return -stake
        else:  # VOID or PUSH
            return 0.0
