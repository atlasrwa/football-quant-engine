"""Signal Generator for Over/Under predictions.

MVP strategy: heuristic-based signal using combined feature scores.
Designed to be replaced with ML model in future iterations.
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from src.models.config import StrategyConfig
from src.models.features import MatchFeatures

logger = logging.getLogger(__name__)


class SignalGenerator:
    """Generates Over/Under signals with estimated edge.

    MVP heuristic strategy:
    - Combines xG efficiency deltas, rolling form, and referee volatility
      into a composite score predicting goal volume.
    - Positive composite → OVER signal; negative → UNDER signal.
    - Edge magnitude is the absolute composite score (capped at 1.0).

    Signals are only emitted when edge >= min_edge_threshold.
    """

    # Feature weights for the composite score
    WEIGHT_XG_HOME = 0.25
    WEIGHT_XG_AWAY = 0.25
    WEIGHT_FORM_HOME = 0.15
    WEIGHT_FORM_AWAY = 0.15
    WEIGHT_REF_VOLATILITY = 0.20

    def __init__(self, config: Optional[StrategyConfig] = None) -> None:
        """Initialize SignalGenerator.

        Args:
            config: Strategy configuration with min_edge_threshold.
        """
        self._config = config or StrategyConfig()
        self._min_edge = self._config.min_edge_threshold

    @property
    def min_edge(self) -> float:
        """Minimum edge required to emit a signal."""
        return self._min_edge

    def generate(
        self, features: MatchFeatures
    ) -> Optional[Tuple[str, float]]:
        """Generate a signal for a single match.

        Args:
            features: The computed feature vector for the match.

        Returns:
            Tuple of (prediction, edge) if edge meets threshold, else None.
            prediction is "OVER" or "UNDER".
            edge is in [min_edge_threshold, 1.0].
        """
        composite = self._compute_composite(features)
        edge = min(abs(composite), 1.0)

        if edge < self._min_edge:
            return None

        prediction = "OVER" if composite > 0 else "UNDER"
        return prediction, edge

    def _compute_composite(self, features: MatchFeatures) -> float:
        """Compute composite score from features.

        Positive values indicate higher expected goal volume (OVER).
        Negative values indicate lower expected goal volume (UNDER).

        Args:
            features: Match feature vector.

        Returns:
            Composite score (unbounded float).
        """
        # xG efficiency: positive delta means teams score more than expected
        xg_component = (
            self.WEIGHT_XG_HOME * features.home_xg_eff_delta_rolling
            + self.WEIGHT_XG_AWAY * features.away_xg_eff_delta_rolling
        )

        # Form: high form teams tend to score more (shift to center at 0.5)
        form_component = (
            self.WEIGHT_FORM_HOME * (features.home_rolling_form - 0.5)
            + self.WEIGHT_FORM_AWAY * (features.away_rolling_form - 0.5)
        )

        # Referee volatility: higher volatility → more likely over
        # Normalize around 1.3 (approximate league average std)
        ref_component = (
            self.WEIGHT_REF_VOLATILITY * (features.referee_volatility_index - 1.3)
        )

        return xg_component + form_component + ref_component
