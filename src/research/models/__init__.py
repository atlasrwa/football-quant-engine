"""Statistical model primitives retained for the QFE V2 reboot.

No model in this package is automatically promoted. Each is a reusable
candidate that must earn its place through chronological out-of-sample
probability quality and calibration.
"""

from src.research.models.calibration import IsotonicCalibrator, PlattScaler
from src.research.models.count_regression import CountRegressionModel
from src.research.models.dixon_coles import DixonColesModel
from src.research.models.hierarchical_count import LeagueCountModel
from src.research.models.latent_team_state import LatentTeamStateForecaster

__all__ = [
    "IsotonicCalibrator",
    "PlattScaler",
    "CountRegressionModel",
    "DixonColesModel",
    "LeagueCountModel",
    "LatentTeamStateForecaster",
]
