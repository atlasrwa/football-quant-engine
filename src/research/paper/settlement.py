"""Paper Trade Settlement — determines outcome of paper trades.

Settlement logic:
    WIN:  profit = stake * (odds - 1)
    LOSS: profit = -stake
    VOID: profit = 0 (stake returned)

Settlement does NOT modify the original prediction.
Settlement does NOT change prediction odds or probability.
Settlement is a SEPARATE event that happens after the match completes.

Reuses standard decimal-odds settlement — no new settlement logic created.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class SettlementResult:
    """Result of settling a paper trade.

    Immutable record of what happened.
    """
    trade_id: str
    outcome: str  # "WIN", "LOSS", "VOID"
    stake: float
    odds: float
    profit_loss: float
    return_amount: float  # Total returned (stake + profit for WIN, 0 for LOSS)
    settlement_timestamp: float

    @property
    def is_winner(self) -> bool:
        return self.outcome == "WIN"

    @property
    def is_loser(self) -> bool:
        return self.outcome == "LOSS"

    @property
    def is_void(self) -> bool:
        return self.outcome == "VOID"

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "outcome": self.outcome,
            "stake": self.stake,
            "odds": self.odds,
            "profit_loss": round(self.profit_loss, 4),
            "return_amount": round(self.return_amount, 4),
            "settlement_timestamp": self.settlement_timestamp,
        }


def settle_trade(
    trade_id: str,
    outcome: str,
    stake: float,
    odds: float,
    settlement_timestamp: float,
) -> SettlementResult:
    """Settle a paper trade.

    Args:
        trade_id: Trade identifier.
        outcome: "WIN", "LOSS", or "VOID".
        stake: Original stake amount.
        odds: Decimal odds at prediction time.
        settlement_timestamp: When settlement occurred.

    Returns:
        SettlementResult with P&L calculated.

    Raises:
        ValueError: If outcome is invalid or inputs are malformed.
    """
    if outcome not in ("WIN", "LOSS", "VOID"):
        raise ValueError(f"Invalid outcome: {outcome}. Must be WIN, LOSS, or VOID.")

    if stake < 0:
        raise ValueError(f"Stake must be >= 0, got {stake}")

    if odds < 1.0 and outcome != "VOID":
        raise ValueError(f"Odds must be >= 1.0, got {odds}")

    if outcome == "WIN":
        profit_loss = stake * (odds - 1.0)
        return_amount = stake + profit_loss
    elif outcome == "LOSS":
        profit_loss = -stake
        return_amount = 0.0
    else:  # VOID
        profit_loss = 0.0
        return_amount = stake  # Stake returned

    return SettlementResult(
        trade_id=trade_id,
        outcome=outcome,
        stake=stake,
        odds=odds,
        profit_loss=profit_loss,
        return_amount=return_amount,
        settlement_timestamp=settlement_timestamp,
    )


def determine_outcome(
    market: str,
    selection: str,
    line: float,
    actual_value: Optional[float],
) -> str:
    """Determine trade outcome from match result.

    Args:
        market: Market type (e.g., "CORNERS_TOTAL", "GOALS_TOTAL").
        selection: Selection (e.g., "OVER", "UNDER").
        line: Market line (e.g., 9.5).
        actual_value: Actual match outcome value. None = VOID.

    Returns:
        "WIN", "LOSS", or "VOID".
    """
    if actual_value is None:
        return "VOID"  # Cannot settle without result — NOT zero

    if selection == "OVER":
        return "WIN" if actual_value > line else "LOSS"
    elif selection == "UNDER":
        return "WIN" if actual_value < line else "LOSS"
    elif selection in ("HOME", "DRAW", "AWAY", "YES", "NO"):
        # For 1X2 and BTTS: actual_value encodes the result
        # Simplified: 1=HOME, 0=DRAW, -1=AWAY for 1X2
        # For BTTS: 1=YES, 0=NO
        if selection == "HOME" and actual_value == 1:
            return "WIN"
        elif selection == "DRAW" and actual_value == 0:
            return "WIN"
        elif selection == "AWAY" and actual_value == -1:
            return "WIN"
        elif selection == "YES" and actual_value == 1:
            return "WIN"
        elif selection == "NO" and actual_value == 0:
            return "WIN"
        else:
            return "LOSS"
    else:
        return "VOID"  # Unknown selection → cannot settle
