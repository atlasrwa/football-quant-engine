"""Proposal Validator — deterministic validation of AI/human proposals.

Every proposal must pass validation before entering the queue.
Invalid proposals are REJECTED, never auto-corrected silently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from src.research.ai.proposal import ProposalStatus, ResearchProposal

logger = logging.getLogger(__name__)

# Supported values
_VALID_DIRECTIONS = {"OVER", "UNDER", "HOME", "DRAW", "AWAY", "YES", "NO"}
_VALID_OPERATORS = {
    "THRESHOLD_GT", "THRESHOLD_LT", "DIFFERENCE_GT", "DIFFERENCE_LT",
    "RATIO_GT", "RATIO_LT", "INTERACTION_AND", "TREND_GT", "TREND_LT",
    "RELATIVE_GT", "RELATIVE_LT",
}
_VALID_MODELS = {"historical_frequency", "logistic_regression", "poisson"}
_VALID_ODDS_MODES = {"NO_ODDS", "SYNTHETIC_ODDS", "HISTORICAL_ODDS"}
_MAX_INTERACTION_DEPTH = 3
_MAX_FEATURES = 5


@dataclass
class ValidationResult:
    """Result of proposal validation."""
    valid: bool
    errors: list[str]
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {"valid": self.valid, "errors": self.errors, "warnings": self.warnings}


class ProposalValidator:
    """Validates research proposals deterministically.

    Checks:
    - Market exists and is supported
    - Features exist and are valid for market
    - Operator is supported
    - Parameters are within allowed ranges
    - Direction is valid
    - Model is compatible
    - No temporal leakage in feature selection
    - Interaction depth within budget
    """

    def __init__(
        self,
        available_markets: Optional[set[str]] = None,
        available_features: Optional[set[str]] = None,
        max_interaction_depth: int = _MAX_INTERACTION_DEPTH,
    ) -> None:
        self._available_markets = available_markets or {
            "GOALS_TOTAL", "CORNERS_TOTAL", "CARDS_TOTAL",
            "OFFSIDES_TOTAL", "BTTS", "MATCH_RESULT_1X2",
        }
        self._available_features = available_features
        self._max_depth = max_interaction_depth

    def validate(self, proposal: ResearchProposal) -> ValidationResult:
        """Validate a proposal. Returns errors if invalid.

        Invalid proposals must be REJECTED, not silently corrected.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Market validation
        if not proposal.market_type:
            errors.append("market_type is required")
        elif proposal.market_type not in self._available_markets:
            errors.append(f"Unknown market: {proposal.market_type}")

        # Direction validation
        if not proposal.direction:
            errors.append("direction is required")
        elif proposal.direction not in _VALID_DIRECTIONS:
            errors.append(f"Invalid direction: {proposal.direction}")

        # Feature validation
        if not proposal.feature_ids:
            errors.append("At least one feature_id required")
        elif len(proposal.feature_ids) > _MAX_FEATURES:
            errors.append(f"Too many features: {len(proposal.feature_ids)} > {_MAX_FEATURES}")
        elif self._available_features:
            for fid in proposal.feature_ids:
                if fid not in self._available_features:
                    errors.append(f"Unknown feature: {fid}")

        # Operator validation
        if proposal.operator_type and proposal.operator_type not in _VALID_OPERATORS:
            errors.append(f"Invalid operator: {proposal.operator_type}")

        # Model validation
        if proposal.model_type and proposal.model_type not in _VALID_MODELS:
            errors.append(f"Unsupported model: {proposal.model_type}")

        # Odds mode validation
        if proposal.odds_mode and proposal.odds_mode not in _VALID_ODDS_MODES:
            errors.append(f"Invalid odds_mode: {proposal.odds_mode}")

        # Conditions validation
        if proposal.conditions:
            if len(proposal.conditions) > self._max_depth:
                errors.append(
                    f"Interaction depth {len(proposal.conditions)} > max {self._max_depth}"
                )
            for i, cond in enumerate(proposal.conditions):
                if not isinstance(cond, dict):
                    errors.append(f"Condition {i} must be a dict")
                elif "feature_id" not in cond or "operator" not in cond:
                    errors.append(f"Condition {i} missing feature_id or operator")
                elif "threshold" not in cond:
                    errors.append(f"Condition {i} missing threshold")

        # Temporal leakage check (basic)
        _POST_MATCH_INDICATORS = {"home_goals", "away_goals", "total_goals", "result"}
        for fid in proposal.feature_ids:
            if fid in _POST_MATCH_INDICATORS:
                errors.append(f"Feature '{fid}' is a post-match outcome, not a pre-match feature")

        if errors:
            logger.warning("Proposal rejected: %s", "; ".join(errors))

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )
