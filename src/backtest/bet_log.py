"""Bet Logger for recording per-bet outcomes during backtesting."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

from src.models.results import BetRecord

logger = logging.getLogger(__name__)


class BetLogger:
    """Records bet outcomes during backtest execution.

    Accumulates BetRecord entries and supports serialization to JSON lines.
    """

    def __init__(self) -> None:
        """Initialize an empty bet log."""
        self._records: List[BetRecord] = []

    @property
    def records(self) -> List[BetRecord]:
        """All recorded bets."""
        return self._records.copy()

    @property
    def count(self) -> int:
        """Number of bets recorded."""
        return len(self._records)

    def log_bet(
        self,
        match_id: int,
        date_unix: int,
        prediction: str,
        actual_outcome: str,
        odds: float,
        stake: float,
    ) -> BetRecord:
        """Record a single bet outcome.

        Args:
            match_id: The match identifier.
            date_unix: Match timestamp.
            prediction: "OVER" or "UNDER".
            actual_outcome: "OVER" or "UNDER".
            odds: Decimal odds for the prediction.
            stake: Stake size placed.

        Returns:
            The created BetRecord.
        """
        if prediction == actual_outcome:
            profit_loss = stake * (odds - 1.0)
        else:
            profit_loss = -stake

        record = BetRecord(
            match_id=match_id,
            date_unix=date_unix,
            prediction=prediction,
            actual_outcome=actual_outcome,
            odds=odds,
            stake=stake,
            profit_loss=round(profit_loss, 6),
        )
        self._records.append(record)
        return record

    def get_returns(self) -> List[float]:
        """Get per-bet returns (profit_loss / stake).

        Returns:
            List of per-bet return ratios.
        """
        return [r.profit_loss / r.stake for r in self._records]

    def get_cumulative_pnl(self) -> List[float]:
        """Get cumulative P&L series.

        Returns:
            List of cumulative profit/loss values.
        """
        cumulative: List[float] = []
        running = 0.0
        for record in self._records:
            running += record.profit_loss
            cumulative.append(round(running, 6))
        return cumulative

    def total_staked(self) -> float:
        """Total amount staked across all bets."""
        return sum(r.stake for r in self._records)

    def total_profit(self) -> float:
        """Total profit/loss across all bets."""
        return sum(r.profit_loss for r in self._records)

    def win_count(self) -> int:
        """Number of winning bets."""
        return sum(1 for r in self._records if r.is_win)

    def clear(self) -> None:
        """Clear all recorded bets."""
        self._records.clear()

    def to_jsonl(self, path: Path) -> None:
        """Serialize bet log to JSON lines file.

        Args:
            path: Output file path.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for record in self._records:
                entry = {
                    "match_id": record.match_id,
                    "date_unix": record.date_unix,
                    "prediction": record.prediction,
                    "actual_outcome": record.actual_outcome,
                    "odds": record.odds,
                    "stake": record.stake,
                    "profit_loss": record.profit_loss,
                }
                f.write(json.dumps(entry) + "\n")
        logger.info("Wrote %d bet records to %s", len(self._records), path)
