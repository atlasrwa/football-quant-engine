"""Experiment configuration — complete reproducibility specification.

An experiment is entirely reproducible from its configuration.
The same config always produces the same experiment_id, predictions,
and metrics within numerical tolerance.

No runtime-dependent values enter the identity hash.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.research.experiment_engine.hypothesis import ExperimentHypothesis


class OddsMode(Enum):
    """How odds are sourced for the experiment."""

    NO_ODDS = "NO_ODDS"                # EV not calculated
    SYNTHETIC_ODDS = "SYNTHETIC_ODDS"  # Generated for testing machinery
    HISTORICAL_ODDS = "HISTORICAL_ODDS"  # Real historical bookmaker odds


class ExperimentVersion(Enum):
    """Version of the experiment protocol."""

    V1 = "v1"


@dataclass(frozen=True)
class ExperimentThresholds:
    """Configurable research thresholds.

    These are research labels, NOT production approval criteria.
    """

    min_sample_size: int = 50
    min_ev_threshold: float = 0.0
    min_odds: float = 1.10
    max_odds: float = 15.0
    significance_level: float = 0.05
    min_effect_size: float = 0.01

    def to_dict(self) -> dict[str, Any]:
        return {
            "min_sample_size": self.min_sample_size,
            "min_ev_threshold": self.min_ev_threshold,
            "min_odds": self.min_odds,
            "max_odds": self.max_odds,
            "significance_level": self.significance_level,
            "min_effect_size": self.min_effect_size,
        }


@dataclass(frozen=True)
class ExperimentConfig:
    """Complete experiment specification for full reproducibility.

    Running the same config against the same dataset must produce
    identical results within numerical tolerance.

    Attributes:
        experiment_version: Protocol version.
        hypothesis: The hypothesis under test.
        market_type: Target market identifier.
        dataset_version: Content hash of the dataset.
        model_type: Probability model to use.
        model_parameters: Model configuration.
        training_start: Start of training period (unix timestamp).
        training_end: End of training period (unix timestamp).
        evaluation_start: Start of evaluation period (unix timestamp).
        evaluation_end: End of evaluation period (unix timestamp).
        minimum_observations: Min samples required for valid result.
        odds_mode: How odds are sourced.
        thresholds: Research thresholds.
        random_seed: For reproducibility of stochastic components.
        features: Feature IDs used in the experiment.
    """

    experiment_version: str = ExperimentVersion.V1.value
    hypothesis: Optional[ExperimentHypothesis] = None
    market_type: str = ""
    dataset_version: str = ""
    model_type: str = ""
    model_parameters: tuple[tuple[str, Any], ...] = ()
    training_start: Optional[int] = None
    training_end: Optional[int] = None
    evaluation_start: Optional[int] = None
    evaluation_end: Optional[int] = None
    minimum_observations: int = 50
    odds_mode: OddsMode = OddsMode.NO_ODDS
    thresholds: ExperimentThresholds = field(default_factory=ExperimentThresholds)
    random_seed: int = 42
    features: tuple[str, ...] = ()

    @property
    def experiment_id(self) -> str:
        """Deterministic experiment identity hash.

        Depends on:
        - hypothesis content hash
        - market_type
        - dataset_version
        - model_type + parameters
        - experiment_version
        - training/evaluation windows
        - odds mode
        - thresholds
        - random_seed
        - features

        Does NOT include: created_at, runtime values, random UUIDs.

        Canonical serialization uses sorted JSON with no whitespace.
        """
        canonical = json.dumps(
            {
                "experiment_version": self.experiment_version,
                "hypothesis_hash": self.hypothesis.content_hash if self.hypothesis else "",
                "market_type": self.market_type,
                "dataset_version": self.dataset_version,
                "model_type": self.model_type,
                "model_parameters": sorted(self.model_parameters),
                "training_start": self.training_start,
                "training_end": self.training_end,
                "evaluation_start": self.evaluation_start,
                "evaluation_end": self.evaluation_end,
                "minimum_observations": self.minimum_observations,
                "odds_mode": self.odds_mode.value,
                "thresholds": self.thresholds.to_dict(),
                "random_seed": self.random_seed,
                "features": sorted(self.features),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    def validate(self) -> tuple[bool, str]:
        """Validate configuration completeness.

        Returns:
            (is_valid, reason) tuple.
        """
        if self.hypothesis is None:
            return False, "No hypothesis specified"
        if not self.market_type:
            return False, "No market_type specified"
        if not self.dataset_version:
            return False, "No dataset_version specified"
        if not self.model_type:
            return False, "No model_type specified"
        if self.training_start is None or self.training_end is None:
            return False, "Training period not specified"
        if self.evaluation_start is None or self.evaluation_end is None:
            return False, "Evaluation period not specified"
        if self.training_end > self.evaluation_start:
            return False, "Training period overlaps evaluation period (temporal violation)"
        if self.training_start >= self.training_end:
            return False, "Training start must be before training end"
        if self.evaluation_start >= self.evaluation_end:
            return False, "Evaluation start must be before evaluation end"
        if self.minimum_observations < 1:
            return False, "minimum_observations must be >= 1"
        return True, "Valid"

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage/provenance."""
        return {
            "experiment_id": self.experiment_id,
            "experiment_version": self.experiment_version,
            "hypothesis_hash": self.hypothesis.content_hash if self.hypothesis else None,
            "market_type": self.market_type,
            "dataset_version": self.dataset_version,
            "model_type": self.model_type,
            "model_parameters": dict(self.model_parameters),
            "training_start": self.training_start,
            "training_end": self.training_end,
            "evaluation_start": self.evaluation_start,
            "evaluation_end": self.evaluation_end,
            "minimum_observations": self.minimum_observations,
            "odds_mode": self.odds_mode.value,
            "thresholds": self.thresholds.to_dict(),
            "random_seed": self.random_seed,
            "features": list(self.features),
        }
