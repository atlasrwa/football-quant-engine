"""StrategyConfig dataclass for backtest execution parameters."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    """Configuration for backtest execution.

    All parameters have sensible defaults and can be overridden
    via CLI flags or a JSON config file.
    """

    # Walk-forward parameters
    train_window: int = 100  # matches in training fold
    test_window: int = 20  # matches in test fold
    step_size: int = 20  # fold advance step

    # Feature parameters
    xg_rolling_window: int = 5
    form_rolling_window: int = 6
    referee_min_matches: int = 5
    variance_rolling_window: int = 10

    # Staking parameters
    base_stake: float = 1.0
    max_stake_multiplier: float = 3.0
    min_stake_multiplier: float = 0.25
    min_edge_threshold: float = 0.05

    # Reproducibility
    random_seed: int = 42

    def __post_init__(self) -> None:
        """Validate configuration constraints."""
        if self.train_window < 1:
            raise ValueError("train_window must be >= 1")
        if self.test_window < 1:
            raise ValueError("test_window must be >= 1")
        if self.step_size < 1:
            raise ValueError("step_size must be >= 1")
        if self.base_stake <= 0:
            raise ValueError("base_stake must be positive")
        if self.max_stake_multiplier <= self.min_stake_multiplier:
            raise ValueError(
                "max_stake_multiplier must be greater than min_stake_multiplier"
            )
        if not (0.0 <= self.min_edge_threshold <= 1.0):
            raise ValueError("min_edge_threshold must be in [0, 1]")
