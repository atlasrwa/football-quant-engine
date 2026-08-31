"""Derived probability models from the Dixon-Coles goals model.

These models compute BTTS (Both Teams To Score) and Clean Sheet probabilities
directly from the bivariate Poisson scoreline distribution — they don't fit
independent classifiers. This is the correct statistical approach because
these outcomes are deterministic functions of the goal counts, not independent
events.

P(BTTS)               = P(home >= 1 AND away >= 1) from scoreline grid
P(clean_sheet_home)   = P(away_goals = 0) = sum(grid[:, 0])
P(clean_sheet_away)   = P(home_goals = 0) = sum(grid[0, :])

Advantages over an independent classifier:
- Coherent with the goals model (no contradictory probability assignments)
- Shares the underlying team strength parameters
- No additional training data or features required
- Mathematically correct derivation, not an approximation

Implements ProbabilityModel ABC for pipeline integration.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from src.research.models.dixon_coles import DixonColesModel
from src.research.probability import (
    PredictionResult,
    PredictionStatus,
    ProbabilityEstimate,
    ProbabilityModel,
    TrainingMetadata,
)


# ═══════════════════════════════════════════════════════════════
# BTTS MODEL (Both Teams To Score)
# ═══════════════════════════════════════════════════════════════


class BTTSModel(ProbabilityModel):
    """Both Teams To Score probability model derived from Dixon-Coles.

    P(BTTS = Yes) = P(home >= 1 AND away >= 1)
                  = 1 - P(home = 0) - P(away = 0) + P(home = 0 AND away = 0)

    This is computed exactly from the Dixon-Coles scoreline grid.
    No separate training is needed — this model wraps an already-fitted
    Dixon-Coles instance.

    For the ProbabilityModel interface:
    - p_over = P(BTTS = Yes) — "over" means both teams score
    - p_under = P(BTTS = No) — "under" means at least one team kept clean sheet
    """

    def __init__(self, goals_model: Optional[DixonColesModel] = None) -> None:
        """Initialize BTTS model.

        Args:
            goals_model: Pre-fitted Dixon-Coles model. If None, one will be
                created and fitted when fit() is called.
        """
        self._goals_model = goals_model or DixonColesModel(line=2.5)

    @property
    def name(self) -> str:
        return "btts_derived"

    @property
    def is_fitted(self) -> bool:
        return self._goals_model.is_fitted

    @property
    def training_metadata(self) -> Optional[TrainingMetadata]:
        return self._goals_model.training_metadata

    @property
    def goals_model(self) -> DixonColesModel:
        """The underlying Dixon-Coles model."""
        return self._goals_model

    def _get_parameters(self) -> dict[str, Any]:
        return {"derived_from": "dixon_coles", "target": "btts"}

    def fit(
        self,
        features: list[dict[str, float]],
        outcomes: list[bool],
        training_start: Optional[int] = None,
        training_end: Optional[int] = None,
    ) -> None:
        """Fit the underlying Dixon-Coles model.

        If the goals_model is already fitted, this is a no-op.
        Otherwise, delegates to the goals model's fit().
        """
        if not self._goals_model.is_fitted:
            self._goals_model.fit(
                features, outcomes,
                training_start=training_start,
                training_end=training_end,
            )

    def predict(self, features: dict[str, float]) -> ProbabilityEstimate:
        """Predict P(BTTS = Yes) from the scoreline grid.

        p_over = P(both teams score at least 1)
        p_under = P(at least one clean sheet)
        """
        grid = self._goals_model.predict_scoreline(features)
        p_btts = self._compute_btts(grid)
        p_btts = max(0.01, min(0.99, p_btts))

        return ProbabilityEstimate(
            p_over=p_btts,
            p_under=1.0 - p_btts,
            model_name=self.name,
        )

    def predict_btts_probability(self, features: dict[str, float]) -> float:
        """Return P(BTTS = Yes) directly."""
        grid = self._goals_model.predict_scoreline(features)
        return self._compute_btts(grid)

    @staticmethod
    def _compute_btts(grid: np.ndarray) -> float:
        """Compute P(both teams score) from scoreline grid.

        P(BTTS) = 1 - P(home=0) - P(away=0) + P(0,0)
                = sum over all (i,j) where i>=1 and j>=1
        """
        n = grid.shape[0]
        p_btts = 0.0
        for i in range(1, n):
            for j in range(1, n):
                p_btts += grid[i, j]
        return float(p_btts)


# ═══════════════════════════════════════════════════════════════
# CLEAN SHEET MODEL
# ═══════════════════════════════════════════════════════════════


class CleanSheetModel(ProbabilityModel):
    """Clean sheet probability model derived from Dixon-Coles.

    Predicts probability that a specific side keeps a clean sheet:
    - P(home_clean_sheet) = P(away_goals = 0) = sum(grid[:, 0])
    - P(away_clean_sheet) = P(home_goals = 0) = sum(grid[0, :])

    For the ProbabilityModel interface:
    - When side="home": p_over = P(home keeps clean sheet)
    - When side="away": p_over = P(away keeps clean sheet)
    - p_under = P(the side concedes at least 1)

    Can also compute P(any clean sheet) = P(home CS OR away CS).
    """

    def __init__(
        self,
        goals_model: Optional[DixonColesModel] = None,
        side: str = "home",
    ) -> None:
        """Initialize clean sheet model.

        Args:
            goals_model: Pre-fitted Dixon-Coles model.
            side: "home" (P(away scores 0)) or "away" (P(home scores 0))
                  or "any" (P(at least one team scores 0)).
        """
        self._goals_model = goals_model or DixonColesModel(line=2.5)
        self._side = side
        assert side in ("home", "away", "any"), f"side must be home/away/any, got {side}"

    @property
    def name(self) -> str:
        return f"clean_sheet_{self._side}_derived"

    @property
    def is_fitted(self) -> bool:
        return self._goals_model.is_fitted

    @property
    def training_metadata(self) -> Optional[TrainingMetadata]:
        return self._goals_model.training_metadata

    @property
    def goals_model(self) -> DixonColesModel:
        return self._goals_model

    def _get_parameters(self) -> dict[str, Any]:
        return {"derived_from": "dixon_coles", "target": f"clean_sheet_{self._side}"}

    def fit(
        self,
        features: list[dict[str, float]],
        outcomes: list[bool],
        training_start: Optional[int] = None,
        training_end: Optional[int] = None,
    ) -> None:
        """Fit the underlying Dixon-Coles model if not already fitted."""
        if not self._goals_model.is_fitted:
            self._goals_model.fit(
                features, outcomes,
                training_start=training_start,
                training_end=training_end,
            )

    def predict(self, features: dict[str, float]) -> ProbabilityEstimate:
        """Predict clean sheet probability.

        p_over = P(clean sheet for configured side)
        p_under = P(side concedes at least 1)
        """
        grid = self._goals_model.predict_scoreline(features)
        p_cs = self._compute_clean_sheet(grid)
        p_cs = max(0.01, min(0.99, p_cs))

        return ProbabilityEstimate(
            p_over=p_cs,
            p_under=1.0 - p_cs,
            model_name=self.name,
        )

    def predict_all_clean_sheet_probs(
        self, features: dict[str, float]
    ) -> dict[str, float]:
        """Return all clean sheet probabilities for a match.

        Returns:
            Dict with keys: home_cs, away_cs, any_cs, no_cs
        """
        grid = self._goals_model.predict_scoreline(features)

        # P(away scores 0) = home keeps CS
        p_home_cs = float(np.sum(grid[:, 0]))
        # P(home scores 0) = away keeps CS
        p_away_cs = float(np.sum(grid[0, :]))
        # P(at least one clean sheet) = P(home CS OR away CS)
        # = P(home CS) + P(away CS) - P(both CS) where P(both CS) = P(0,0)
        p_both_cs = float(grid[0, 0])
        p_any_cs = p_home_cs + p_away_cs - p_both_cs
        p_no_cs = 1.0 - p_any_cs

        return {
            "home_cs": p_home_cs,
            "away_cs": p_away_cs,
            "any_cs": p_any_cs,
            "no_cs": p_no_cs,
        }

    def _compute_clean_sheet(self, grid: np.ndarray) -> float:
        """Compute clean sheet probability for configured side."""
        if self._side == "home":
            # Home keeps CS = away scores 0 = sum of column 0
            return float(np.sum(grid[:, 0]))
        elif self._side == "away":
            # Away keeps CS = home scores 0 = sum of row 0
            return float(np.sum(grid[0, :]))
        else:  # "any"
            p_home_cs = float(np.sum(grid[:, 0]))
            p_away_cs = float(np.sum(grid[0, :]))
            p_both_cs = float(grid[0, 0])
            return p_home_cs + p_away_cs - p_both_cs


# ═══════════════════════════════════════════════════════════════
# EXACT GOALS MODEL
# ═══════════════════════════════════════════════════════════════


class ExactGoalsModel(ProbabilityModel):
    """Exact total goals probability model derived from Dixon-Coles.

    Predicts P(total_goals = k) for any k, or P(total_goals > line)
    for over/under markets at arbitrary lines.

    Useful for exotic markets (exact goals, goal bands).
    """

    def __init__(
        self,
        goals_model: Optional[DixonColesModel] = None,
        line: float = 2.5,
    ) -> None:
        self._goals_model = goals_model or DixonColesModel(line=line)
        self._line = line

    @property
    def name(self) -> str:
        return f"exact_goals_derived"

    @property
    def is_fitted(self) -> bool:
        return self._goals_model.is_fitted

    @property
    def training_metadata(self) -> Optional[TrainingMetadata]:
        return self._goals_model.training_metadata

    def _get_parameters(self) -> dict[str, Any]:
        return {"derived_from": "dixon_coles", "target": "exact_goals", "line": self._line}

    def fit(
        self,
        features: list[dict[str, float]],
        outcomes: list[bool],
        training_start: Optional[int] = None,
        training_end: Optional[int] = None,
    ) -> None:
        if not self._goals_model.is_fitted:
            self._goals_model.fit(
                features, outcomes,
                training_start=training_start,
                training_end=training_end,
            )

    def predict(self, features: dict[str, float]) -> ProbabilityEstimate:
        """Predict P(over) / P(under) for configured line."""
        p_over, p_under = self._goals_model.predict_over_under(features, self._line)
        p_over = max(0.01, min(0.99, p_over))
        return ProbabilityEstimate(
            p_over=p_over,
            p_under=1.0 - p_over,
            model_name=self.name,
        )

    def predict_exact_total(
        self, features: dict[str, float], max_total: int = 10
    ) -> list[float]:
        """Return P(total_goals = k) for k = 0, 1, ..., max_total.

        Useful for exact goals markets and goal bands.
        """
        grid = self._goals_model.predict_scoreline(features)
        n = grid.shape[0]

        probs = [0.0] * (max_total + 1)
        for i in range(n):
            for j in range(n):
                total = i + j
                if total <= max_total:
                    probs[total] += grid[i, j]

        return probs

    def predict_goal_band(
        self, features: dict[str, float], low: int, high: int
    ) -> float:
        """Return P(low <= total_goals <= high).

        E.g., predict_goal_band(feat, 2, 3) = P(2 or 3 goals).
        """
        dist = self.predict_exact_total(features, max_total=max(high, 10))
        return sum(dist[low:high + 1])
