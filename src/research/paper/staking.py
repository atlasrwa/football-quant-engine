"""Staking Model — paper-only stake calculation.

Supports:
- FIXED_STAKE: Fixed monetary amount per trade
- FIXED_PERCENT_BANKROLL: Fixed percentage of current bankroll
- KELLY_FRACTION: Fractional Kelly criterion (simulation only)

Kelly is explicitly labeled as a SIMULATION model.
No real funds. No wallet. No broker. No bookmaker execution.

Conservative defaults:
- Starting bankroll: 10,000 units
- Max stake: 5% of bankroll
- Min stake: 1 unit
- Kelly fraction: 0.25 (quarter Kelly for conservatism)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class StakingType(Enum):
    """Staking strategy types."""
    FIXED_STAKE = "FIXED_STAKE"
    FIXED_PERCENT_BANKROLL = "FIXED_PERCENT_BANKROLL"
    KELLY_FRACTION = "KELLY_FRACTION"


@dataclass(frozen=True)
class StakingConfig:
    """Configuration for paper staking.

    Conservative defaults to prevent unrealistic position sizes.
    """
    staking_type: StakingType = StakingType.FIXED_STAKE
    starting_bankroll: float = 10_000.0
    fixed_stake: float = 100.0  # For FIXED_STAKE
    percent_of_bankroll: float = 0.02  # For FIXED_PERCENT (2%)
    kelly_fraction: float = 0.25  # Quarter Kelly
    max_stake_pct: float = 0.05  # Max 5% of bankroll per trade
    min_stake: float = 1.0  # Minimum stake
    max_stake: float = 1000.0  # Absolute maximum

    def validate(self) -> list[str]:
        """Validate staking configuration."""
        errors: list[str] = []
        if self.starting_bankroll <= 0:
            errors.append("starting_bankroll must be > 0")
        if self.fixed_stake <= 0:
            errors.append("fixed_stake must be > 0")
        if not (0 < self.percent_of_bankroll <= 1.0):
            errors.append("percent_of_bankroll must be (0, 1.0]")
        if not (0 < self.kelly_fraction <= 1.0):
            errors.append("kelly_fraction must be (0, 1.0]")
        if not (0 < self.max_stake_pct <= 1.0):
            errors.append("max_stake_pct must be (0, 1.0]")
        if self.min_stake <= 0:
            errors.append("min_stake must be > 0")
        if self.max_stake < self.min_stake:
            errors.append("max_stake must be >= min_stake")
        return errors


class StakingModel:
    """Paper-only staking calculator.

    Tracks bankroll and calculates stakes based on config.
    No real funds involved.
    """

    def __init__(self, config: Optional[StakingConfig] = None) -> None:
        self._config = config or StakingConfig()
        self._bankroll = self._config.starting_bankroll
        self._total_staked: float = 0.0
        self._trade_count: int = 0

    @property
    def bankroll(self) -> float:
        """Current paper bankroll."""
        return self._bankroll

    @property
    def starting_bankroll(self) -> float:
        return self._config.starting_bankroll

    @property
    def total_staked(self) -> float:
        return self._total_staked

    @property
    def trade_count(self) -> int:
        return self._trade_count

    @property
    def roi(self) -> float:
        """Return on investment (current vs starting)."""
        if self._config.starting_bankroll <= 0:
            return 0.0
        return (self._bankroll - self._config.starting_bankroll) / self._config.starting_bankroll

    def calculate_stake(
        self,
        model_probability: float,
        decimal_odds: float,
    ) -> float:
        """Calculate paper stake for a trade.

        Args:
            model_probability: Model's predicted probability of winning.
            decimal_odds: Decimal odds for the selection.

        Returns:
            Stake amount (may be 0 if below minimum or bankroll insufficient).
        """
        if self._bankroll <= 0:
            return 0.0

        if decimal_odds < 1.0:
            return 0.0

        if model_probability <= 0 or model_probability >= 1.0:
            return 0.0

        if self._config.staking_type == StakingType.FIXED_STAKE:
            stake = self._config.fixed_stake

        elif self._config.staking_type == StakingType.FIXED_PERCENT_BANKROLL:
            stake = self._bankroll * self._config.percent_of_bankroll

        elif self._config.staking_type == StakingType.KELLY_FRACTION:
            stake = self._kelly_stake(model_probability, decimal_odds)

        else:
            stake = self._config.fixed_stake

        # Apply limits
        max_allowed = self._bankroll * self._config.max_stake_pct
        stake = min(stake, max_allowed)
        stake = min(stake, self._config.max_stake)
        stake = min(stake, self._bankroll)  # Can't bet more than bankroll

        if stake < self._config.min_stake:
            return 0.0  # Below minimum — no trade

        return round(stake, 2)

    def record_result(self, stake: float, profit_loss: float) -> None:
        """Record trade result, updating bankroll.

        Args:
            stake: Amount staked.
            profit_loss: Realized P&L (positive = win, negative = loss).
        """
        self._bankroll += profit_loss
        self._total_staked += stake
        self._trade_count += 1

    def _kelly_stake(self, probability: float, odds: float) -> float:
        """Calculate Kelly criterion stake.

        Kelly fraction f* = (bp - q) / b
        where b = odds - 1, p = probability, q = 1 - p

        Applied with configured kelly_fraction for conservatism.
        """
        b = odds - 1.0
        if b <= 0:
            return 0.0

        p = probability
        q = 1.0 - p
        kelly = (b * p - q) / b

        if kelly <= 0:
            return 0.0  # Negative Kelly = don't bet

        # Apply fraction for conservatism
        fractional_kelly = kelly * self._config.kelly_fraction
        return self._bankroll * fractional_kelly

    def to_dict(self) -> dict[str, Any]:
        return {
            "staking_type": self._config.staking_type.value,
            "bankroll": round(self._bankroll, 2),
            "starting_bankroll": self._config.starting_bankroll,
            "total_staked": round(self._total_staked, 2),
            "trade_count": self._trade_count,
            "roi": round(self.roi, 4),
        }
