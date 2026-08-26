"""Research Run Identity — deterministic provenance for research runs.

Captures the complete configuration that defines a research run,
enabling exact reproducibility and research memory.

A ResearchRunIdentity answers:
"What exactly was tested, with what data, using what methodology?"
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class ResearchRunIdentity:
    """Deterministic identity for a complete research run.

    Represents the full provenance of a research evaluation:
    - What data was used
    - What candidates were generated
    - What experiments were run
    - What walk-forward configuration was applied
    - What model was used
    - What FDR correction was applied

    Two research runs with the same identity must produce
    the same results (within numerical tolerance).

    Attributes:
        dataset_version: Content hash of the dataset.
        candidate_generation_version: Config hash of candidate generation.
        experiment_version: Experiment protocol version.
        walkforward_config_hash: Walk-forward configuration hash.
        model_type: Model type identifier.
        model_parameters_hash: Hash of model parameters.
        fdr_alpha: FDR significance level.
        governance_criteria_hash: Hash of governance criteria.
        market_type: Target market.
        random_seed: Random seed for reproducibility.
    """

    dataset_version: str
    candidate_generation_version: str = ""
    experiment_version: str = "v1"
    walkforward_config_hash: str = ""
    model_type: str = ""
    model_parameters_hash: str = ""
    fdr_alpha: float = 0.05
    governance_criteria_hash: str = ""
    market_type: str = ""
    random_seed: int = 42

    @property
    def run_id(self) -> str:
        """Deterministic run identity hash.

        Same inputs always produce the same run_id.
        Does NOT include: timestamps, runtime, execution order.
        """
        canonical = json.dumps(
            {
                "dataset_version": self.dataset_version,
                "candidate_generation_version": self.candidate_generation_version,
                "experiment_version": self.experiment_version,
                "walkforward_config_hash": self.walkforward_config_hash,
                "model_type": self.model_type,
                "model_parameters_hash": self.model_parameters_hash,
                "fdr_alpha": self.fdr_alpha,
                "governance_criteria_hash": self.governance_criteria_hash,
                "market_type": self.market_type,
                "random_seed": self.random_seed,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @property
    def content_hash(self) -> str:
        """Alias for run_id."""
        return self.run_id

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage/provenance."""
        return {
            "run_id": self.run_id,
            "dataset_version": self.dataset_version,
            "candidate_generation_version": self.candidate_generation_version,
            "experiment_version": self.experiment_version,
            "walkforward_config_hash": self.walkforward_config_hash,
            "model_type": self.model_type,
            "model_parameters_hash": self.model_parameters_hash,
            "fdr_alpha": self.fdr_alpha,
            "governance_criteria_hash": self.governance_criteria_hash,
            "market_type": self.market_type,
            "random_seed": self.random_seed,
        }

    @staticmethod
    def from_components(
        dataset_version: str,
        walkforward_config_hash: str,
        model_type: str,
        model_parameters: dict[str, Any],
        fdr_alpha: float = 0.05,
        governance_criteria_hash: str = "",
        market_type: str = "",
        candidate_generation_version: str = "",
        experiment_version: str = "v1",
        random_seed: int = 42,
    ) -> "ResearchRunIdentity":
        """Create from individual components.

        Automatically computes the model_parameters_hash.
        """
        params_canonical = json.dumps(
            model_parameters, sort_keys=True, separators=(",", ":")
        )
        params_hash = hashlib.sha256(params_canonical.encode("utf-8")).hexdigest()[:16]

        return ResearchRunIdentity(
            dataset_version=dataset_version,
            candidate_generation_version=candidate_generation_version,
            experiment_version=experiment_version,
            walkforward_config_hash=walkforward_config_hash,
            model_type=model_type,
            model_parameters_hash=params_hash,
            fdr_alpha=fdr_alpha,
            governance_criteria_hash=governance_criteria_hash,
            market_type=market_type,
            random_seed=random_seed,
        )
