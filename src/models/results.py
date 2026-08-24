"""Backtest result dataclasses for recording outcomes and metrics."""

from dataclasses import dataclass, field
from typing import List

from src.models.config import StrategyConfig


@dataclass(frozen=True, slots=True)
class BetRecord:
    """Single bet in the backtest log."""

    match_id: int
    date_unix: int
    prediction: str  # "OVER" or "UNDER"
    actual_outcome: str  # "OVER" or "UNDER"
    odds: float
    stake: float
    profit_loss: float

    def __post_init__(self) -> None:
        """Validate bet record fields."""
        if self.prediction not in ("OVER", "UNDER"):
            raise ValueError(f"prediction must be 'OVER' or 'UNDER', got '{self.prediction}'")
        if self.actual_outcome not in ("OVER", "UNDER"):
            raise ValueError(
                f"actual_outcome must be 'OVER' or 'UNDER', got '{self.actual_outcome}'"
            )
        if self.odds <= 1.0:
            raise ValueError(f"odds must be > 1.0 (decimal format), got {self.odds}")
        if self.stake <= 0:
            raise ValueError(f"stake must be positive, got {self.stake}")

    @property
    def is_win(self) -> bool:
        """Whether this bet was a winner."""
        return self.prediction == self.actual_outcome


@dataclass(frozen=True, slots=True)
class FoldResult:
    """Per-fold breakdown of backtest performance."""

    fold_index: int
    train_start: int  # match index
    train_end: int
    test_start: int
    test_end: int
    net_roi_pct: float
    win_rate_pct: float
    num_bets: int


@dataclass(slots=True)
class BacktestResult:
    """Complete backtest output with aggregate metrics and detailed logs."""

    # Aggregate metrics
    net_roi_pct: float
    win_rate_pct: float
    max_drawdown_pct: float
    p_value: float
    total_bets: int
    total_staked: float
    total_profit: float

    # Breakdowns
    fold_results: List[FoldResult] = field(default_factory=list)
    bet_log: List[BetRecord] = field(default_factory=list)

    # Config used
    strategy_config: StrategyConfig = field(default_factory=StrategyConfig)

    def summary(self) -> str:
        """Return a human-readable summary of backtest results."""
        return (
            f"Backtest Results ({self.total_bets} bets over {len(self.fold_results)} folds)\n"
            f"  Net ROI:       {self.net_roi_pct:+.2f}%\n"
            f"  Win Rate:      {self.win_rate_pct:.1f}%\n"
            f"  Max Drawdown:  {self.max_drawdown_pct:.2f}%\n"
            f"  p-value:       {self.p_value:.4f}\n"
            f"  Total Staked:  {self.total_staked:.2f}\n"
            f"  Total Profit:  {self.total_profit:+.2f}"
        )
