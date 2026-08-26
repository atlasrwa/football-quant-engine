"""Research Family definition for FDR correction.

A research family is the unit of multiple-testing correction.
All hypotheses within the same family are corrected together.

The family definition is critical:
- Too narrow → misses multiple testing issues
- Too broad → excessively conservative

Default: all candidates from one research run for one market.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class ResearchFamily:
    """Defines a research family for FDR correction.

    A research family groups hypotheses that were searched together.
    FDR correction is applied within each family.

    Attributes:
        family_id: Deterministic identifier for this family.
        market_type: Market this family covers.
        dataset_version: Dataset used for discovery.
        research_run_id: The research run that produced candidates.
        candidate_generation_config: How candidates were generated.
        model_family: Model type used for evaluation (optional).
        description: Human-readable description.
        hypothesis_count: Number of hypotheses in this family.
    """

    family_id: str
    market_type: str
    dataset_version: str
    research_run_id: str = ""
    candidate_generation_config: str = ""
    model_family: str = ""
    description: str = ""
    hypothesis_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "family_id": self.family_id,
            "market_type": self.market_type,
            "dataset_version": self.dataset_version,
            "research_run_id": self.research_run_id,
            "candidate_generation_config": self.candidate_generation_config,
            "model_family": self.model_family,
            "description": self.description,
            "hypothesis_count": self.hypothesis_count,
        }


class ResearchFamilyBuilder:
    """Builds research families from discovery context.

    The builder ensures deterministic family_id generation
    from the research context.
    """

    @staticmethod
    def build(
        market_type: str,
        dataset_version: str,
        research_run_id: str = "",
        candidate_generation_config: str = "",
        model_family: str = "",
        hypothesis_count: int = 0,
        description: str = "",
    ) -> ResearchFamily:
        """Build a research family with deterministic ID.

        The family_id is a hash of:
        - market_type
        - dataset_version
        - research_run_id
        - candidate_generation_config
        - model_family

        This ensures the same research context always produces
        the same family identity.
        """
        canonical = json.dumps(
            {
                "market_type": market_type,
                "dataset_version": dataset_version,
                "research_run_id": research_run_id,
                "candidate_generation_config": candidate_generation_config,
                "model_family": model_family,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        family_id = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

        return ResearchFamily(
            family_id=family_id,
            market_type=market_type,
            dataset_version=dataset_version,
            research_run_id=research_run_id,
            candidate_generation_config=candidate_generation_config,
            model_family=model_family,
            description=description or f"Family for {market_type} run={research_run_id}",
            hypothesis_count=hypothesis_count,
        )
