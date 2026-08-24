"""MatchFeatures dataclass representing computed feature vectors."""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True, slots=True)
class MatchFeatures:
    """Computed feature vector for a single match.

    Produced by the FeatureAssembler after running all calculators
    (xG efficiency, rolling form, referee volatility) on raw Match data.
    """

    match_id: int
    date_unix: int
    home_xg_eff_delta_rolling: float
    away_xg_eff_delta_rolling: float
    home_rolling_form: float  # 0–1 normalized
    away_rolling_form: float  # 0–1 normalized
    referee_volatility_index: float
    total_goals: int  # target variable
    over_under_line: float
    over_odds: Optional[float]
    under_odds: Optional[float]

    def __post_init__(self) -> None:
        """Validate feature bounds."""
        if not (0.0 <= self.home_rolling_form <= 1.0):
            raise ValueError(
                f"home_rolling_form must be in [0, 1], got {self.home_rolling_form}"
            )
        if not (0.0 <= self.away_rolling_form <= 1.0):
            raise ValueError(
                f"away_rolling_form must be in [0, 1], got {self.away_rolling_form}"
            )
        if self.referee_volatility_index < 0:
            raise ValueError(
                f"referee_volatility_index must be non-negative, got {self.referee_volatility_index}"
            )
