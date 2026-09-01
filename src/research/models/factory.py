"""Model factory — selects the appropriate model for each market type.

Maps market types to their statistically appropriate prediction model:
- Goals → Dixon-Coles bivariate Poisson
- Corners → Count regression (Poisson/NB with feature conditioning)
- Cards → Count regression (Poisson with foul features)
- BTTS → Derived from Dixon-Coles (not a separate classifier)
- Clean Sheet → Derived from Dixon-Coles

This factory is the single point where model selection decisions live.
Both DiscoveryRunner and WalkForwardOrchestrator call through here.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from src.research.models.calibration import CalibratedModel
from src.research.models.count_regression import (
    CountRegressionModel,
    create_cards_model,
    create_corners_model,
)
from src.research.models.derived_goals import BTTSModel, CleanSheetModel
from src.research.models.dixon_coles import DixonColesModel
from src.research.probability import (
    HistoricalFrequencyModel,
    LogisticRegressionModel,
    PoissonModel,
    ProbabilityModel,
)


# Type alias for model factory (creates fresh instance per fold)
ModelFactory = Callable[[], ProbabilityModel]


# ═══════════════════════════════════════════════════════════════
# MODEL SELECTION BY MARKET TYPE
# ═══════════════════════════════════════════════════════════════

# Mapping from market type string to default model configuration
_MARKET_MODEL_MAP: dict[str, dict[str, Any]] = {
    # Goals markets
    "GOALS_TOTAL": {
        "model_type": "dixon_coles",
        "params": {"line": 2.5, "time_decay_days": 365.0, "min_team_matches": 3},
    },
    # Corners markets
    "CORNERS_TOTAL": {
        "model_type": "count_regression_corners",
        "params": {"line": 9.5},
    },
    # Cards markets
    "CARDS_TOTAL": {
        "model_type": "count_regression_cards",
        "params": {"line": 3.5},
    },
    # BTTS — derived from goals model
    "BTTS": {
        "model_type": "btts_derived",
        "params": {},
    },
    # Team-specific goals
    "HOME_GOALS": {
        "model_type": "dixon_coles",
        "params": {"line": 1.5},
    },
    "AWAY_GOALS": {
        "model_type": "dixon_coles",
        "params": {"line": 1.5},
    },
    # Offsides — use count regression with generic features
    "OFFSIDES_TOTAL": {
        "model_type": "count_regression",
        "params": {"target_field": "total_offsides", "line": 4.5},
    },
    # ── Asymmetric per-side markets (asymmetric-matchup-engine) ──────────
    # Each is one direction's Per_Side_Target modelled by the elastic-net
    # DirectionalCountModel. These are the per-side counts the InteractionModel
    # fits per direction; the factory exposes them so the walk-forward
    # orchestrator can select them by market type. Team cards has no per-side
    # PRICE (audit) but is still a modelled per-side count here.
    "ASYM_TEAM_CORNERS": {
        "model_type": "asymmetric_directional",
        "params": {"line": 4.5},
    },
    "ASYM_TEAM_GOALS": {
        "model_type": "asymmetric_directional",
        "params": {"line": 1.5},
    },
    "ASYM_TEAM_SOT": {
        "model_type": "asymmetric_directional",
        "params": {"line": 4.5},
    },
    "ASYM_TEAM_CARDS": {
        "model_type": "asymmetric_directional",
        "params": {"line": 2.5},
    },
}


def create_model_for_market(
    market_type: str,
    model_type_override: Optional[str] = None,
    model_params_override: Optional[dict[str, Any]] = None,
    use_calibration: bool = False,
    calibration_method: str = "isotonic",
) -> ProbabilityModel:
    """Create the appropriate model for a market type.

    This is the primary entry point for model selection. Use this
    instead of directly instantiating models.

    Args:
        market_type: Market type string (e.g., "GOALS_TOTAL", "CORNERS_TOTAL").
        model_type_override: Override the default model type for this market.
        model_params_override: Override model parameters.
        use_calibration: Whether to wrap with calibration.
        calibration_method: "platt" or "isotonic" (if use_calibration=True).

    Returns:
        A fresh ProbabilityModel instance ready for fitting.
    """
    # Get default config for this market
    market_config = _MARKET_MODEL_MAP.get(market_type, {
        "model_type": "logistic_regression",
        "params": {},
    })

    model_type = model_type_override or market_config["model_type"]
    params = model_params_override or market_config["params"]

    # Create model
    model = _create_model_instance(model_type, params)

    # Optionally wrap with calibration
    if use_calibration:
        model = CalibratedModel(model, method=calibration_method)

    return model


def create_model_factory_for_market(
    market_type: str,
    model_type_override: Optional[str] = None,
    model_params_override: Optional[dict[str, Any]] = None,
    use_calibration: bool = False,
) -> ModelFactory:
    """Create a model factory for walk-forward validation.

    Returns a callable that creates a fresh model instance each time
    it's called. This ensures no state leaks between folds.

    Args:
        market_type: Market type string.
        model_type_override: Override default model type.
        model_params_override: Override parameters.
        use_calibration: Whether to calibrate.

    Returns:
        Callable that creates fresh ProbabilityModel instances.
    """
    def factory() -> ProbabilityModel:
        return create_model_for_market(
            market_type=market_type,
            model_type_override=model_type_override,
            model_params_override=model_params_override,
            use_calibration=use_calibration,
        )
    return factory


# ═══════════════════════════════════════════════════════════════
# INTERNAL: Model instantiation
# ═══════════════════════════════════════════════════════════════


def _create_model_instance(model_type: str, params: dict[str, Any]) -> ProbabilityModel:
    """Create a single model instance from type name and parameters."""

    if model_type == "dixon_coles":
        return DixonColesModel(
            line=params.get("line", 2.5),
            time_decay_days=params.get("time_decay_days", 365.0),
            min_team_matches=params.get("min_team_matches", 3),
            max_goals=params.get("max_goals", 10),
        )

    elif model_type == "count_regression_corners":
        return create_corners_model(line=params.get("line", 9.5))

    elif model_type == "count_regression_cards":
        return create_cards_model(line=params.get("line", 3.5))

    elif model_type == "count_regression":
        return CountRegressionModel(
            target_field=params.get("target_field", "total_corners"),
            line=params.get("line", 9.5),
            feature_fields=params.get("feature_fields"),
            use_team_effects=params.get("use_team_effects", True),
        )

    elif model_type == "btts_derived":
        # BTTS wraps a Dixon-Coles model
        dc = DixonColesModel(line=2.5)
        return BTTSModel(goals_model=dc)

    elif model_type == "clean_sheet_home":
        dc = DixonColesModel(line=2.5)
        return CleanSheetModel(goals_model=dc, side="home")

    elif model_type == "clean_sheet_away":
        dc = DixonColesModel(line=2.5)
        return CleanSheetModel(goals_model=dc, side="away")

    elif model_type == "logistic_regression":
        return LogisticRegressionModel(
            learning_rate=params.get("learning_rate", 0.01),
            max_iter=params.get("max_iter", 1000),
            seed=params.get("seed"),
        )

    elif model_type == "historical_frequency":
        return HistoricalFrequencyModel(
            min_observations=params.get("min_observations", 1),
            lookback_window=params.get("lookback_window"),
        )

    elif model_type == "poisson":
        return PoissonModel(line=params.get("line", 2.5))

    elif model_type == "asymmetric_directional":
        # Lazy import keeps the isolated asymmetric package out of the default
        # import graph and avoids any cycle; the build/backtest path here never
        # touches the CLI-only live_fetch module.
        from src.research.asymmetric.directional_model import DirectionalCountModel

        return DirectionalCountModel(
            target_field=params.get("target_field", "count"),
            line=params.get("line", 2.5),
        )

    else:
        # Unknown model type — fall back to logistic regression
        return LogisticRegressionModel()


# ═══════════════════════════════════════════════════════════════
# ALL AVAILABLE MODEL TYPES (for documentation/discovery)
# ═══════════════════════════════════════════════════════════════

AVAILABLE_MODELS = {
    "dixon_coles": "Dixon-Coles bivariate Poisson (goals, team-strength based)",
    "count_regression_corners": "Poisson/NB regression for corners (feature-conditioned)",
    "count_regression_cards": "Poisson/NB regression for cards (foul-conditioned)",
    "count_regression": "Generic count regression (configurable target)",
    "btts_derived": "BTTS derived from Dixon-Coles scoreline grid",
    "clean_sheet_home": "Home clean sheet derived from Dixon-Coles",
    "clean_sheet_away": "Away clean sheet derived from Dixon-Coles",
    "logistic_regression": "Generic logistic regression (existing baseline)",
    "historical_frequency": "Historical frequency baseline",
    "poisson": "Simple Poisson model (existing)",
    "asymmetric_directional": "Elastic-net Poisson/NB per-side directional count model (asymmetric-matchup-engine)",
}
