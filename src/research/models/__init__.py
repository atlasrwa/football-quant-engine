"""Research prediction models.

Contains specialized statistical models for football prediction:
- Dixon-Coles bivariate Poisson (goals)
- Negative binomial regression (corners, cards)
- Derived probability models (BTTS, clean sheet)
- Post-hoc calibration wrappers
- Model factory for market-appropriate model selection
"""

from src.research.models.dixon_coles import DixonColesModel
from src.research.models.count_regression import (
    CountRegressionModel,
    create_corners_model,
    create_cards_model,
)
from src.research.models.derived_goals import (
    BTTSModel,
    CleanSheetModel,
    ExactGoalsModel,
)
from src.research.models.calibration import (
    CalibratedModel,
    PlattScaler,
    IsotonicCalibrator,
)
from src.research.models.factory import (
    create_model_for_market,
    create_model_factory_for_market,
    AVAILABLE_MODELS,
)
from src.research.models.market_relative import (
    MarketRelativeCountModel,
    MarketRelativeParams,
    implied_lambda_from_p_over,
)
from src.research.models.latent_team_state import (
    LatentTeamStateForecaster,
    MatchObservation,
    ScorelineForecast,
    StateOffset,
)

__all__ = [
    # Core models
    "DixonColesModel",
    "CountRegressionModel",
    "create_corners_model",
    "create_cards_model",
    # Derived models
    "BTTSModel",
    "CleanSheetModel",
    "ExactGoalsModel",
    # Calibration
    "CalibratedModel",
    "PlattScaler",
    "IsotonicCalibrator",
    # Market-relative research model
    "MarketRelativeCountModel",
    "MarketRelativeParams",
    "implied_lambda_from_p_over",
    # Latent raw-stat team state
    "LatentTeamStateForecaster",
    "MatchObservation",
    "ScorelineForecast",
    "StateOffset",
    # Factory
    "create_model_for_market",
    "create_model_factory_for_market",
    "AVAILABLE_MODELS",
]
