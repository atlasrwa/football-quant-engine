"""Candidate and hypothesis generation for the research laboratory.

Systematically generates feature combinations, thresholds, and strategy
hypotheses for evaluation. Implements bounded search to avoid
combinatorial explosion.

Every generated hypothesis has:
- Unique identity (content hash)
- Full provenance (features, transforms, params)
- Expected direction
- Generation method
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import numpy as np

from src.research.feature_registry import FeatureDefinition, FeatureRegistry, TransformType
from src.research.market import MarketType, ResearchMarket


class GenerationMethod(Enum):
    """How a hypothesis was generated."""
    DETERMINISTIC = "DETERMINISTIC"
    HUMAN = "HUMAN"
    LLM = "LLM"


@dataclass(frozen=True)
class ResearchHypothesis:
    """A testable research hypothesis.

    Represents: "Feature X with condition Y predicts market Z in direction D."
    """
    hypothesis_id: str
    market: MarketType
    feature_ids: tuple[str, ...]
    conditions: tuple[tuple[str, str, float], ...]  # (feature_id, operator, threshold)
    direction: str  # "OVER" or "UNDER"
    generation_method: GenerationMethod
    rationale: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    params: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        """Deterministic content hash for deduplication."""
        canonical = json.dumps({
            "market": self.market.value,
            "feature_ids": list(self.feature_ids),
            "conditions": [list(c) for c in self.conditions],
            "direction": self.direction,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True, slots=True)
class SearchBudget:
    """Bounds for candidate search to avoid combinatorial explosion.

    Attributes:
        max_features_per_hypothesis: Maximum features in one hypothesis.
        max_interaction_depth: Maximum interaction term depth.
        min_sample_size: Minimum matches required per hypothesis.
        max_candidates: Maximum total candidates to generate.
        threshold_quantiles: Quantiles to use for threshold generation.
    """
    max_features_per_hypothesis: int = 3
    max_interaction_depth: int = 2
    min_sample_size: int = 50
    max_candidates: int = 500
    threshold_quantiles: tuple[float, ...] = (0.25, 0.50, 0.75)


class CandidateGenerator:
    """Generates research hypothesis candidates from feature registry.

    Combines features, transforms, and thresholds systematically
    within the bounds of a SearchBudget.
    """

    def __init__(
        self,
        registry: FeatureRegistry,
        budget: Optional[SearchBudget] = None,
        seed: int = 42,
    ) -> None:
        self._registry = registry
        self._budget = budget or SearchBudget()
        self._rng = np.random.default_rng(seed)

    def generate_single_feature_hypotheses(
        self,
        market: ResearchMarket,
        feature_values: list[dict[str, float]],
    ) -> list[ResearchHypothesis]:
        """Generate hypotheses from single features with threshold search.

        For each feature applicable to the market, generate hypotheses
        at multiple threshold quantiles.
        """
        features = self._registry.features_for_market(market.market_type.value)
        hypotheses: list[ResearchHypothesis] = []

        for feat in features:
            fid = feat.feature_id
            # Collect non-None values for this feature
            values = [fv.get(fid) for fv in feature_values if fid in fv]
            if len(values) < self._budget.min_sample_size:
                continue

            arr = np.array(values)
            # Generate thresholds at quantiles
            for q in self._budget.threshold_quantiles:
                threshold = float(np.quantile(arr, q))

                # OVER hypothesis: feature > threshold → OVER
                hyp_over = ResearchHypothesis(
                    hypothesis_id=f"single_{fid}_gt_{q:.2f}_{market.market_type.value}_OVER",
                    market=market.market_type,
                    feature_ids=(fid,),
                    conditions=((fid, ">", threshold),),
                    direction="OVER",
                    generation_method=GenerationMethod.DETERMINISTIC,
                    rationale=f"{feat.name} > {threshold:.3f} predicts OVER {market.market_type.value}",
                )
                hypotheses.append(hyp_over)

                # UNDER hypothesis: feature < threshold → UNDER
                hyp_under = ResearchHypothesis(
                    hypothesis_id=f"single_{fid}_lt_{q:.2f}_{market.market_type.value}_UNDER",
                    market=market.market_type,
                    feature_ids=(fid,),
                    conditions=((fid, "<", threshold),),
                    direction="UNDER",
                    generation_method=GenerationMethod.DETERMINISTIC,
                    rationale=f"{feat.name} < {threshold:.3f} predicts UNDER {market.market_type.value}",
                )
                hypotheses.append(hyp_under)

        return hypotheses[:self._budget.max_candidates]

    def generate_pair_hypotheses(
        self,
        market: ResearchMarket,
        feature_values: list[dict[str, float]],
    ) -> list[ResearchHypothesis]:
        """Generate hypotheses from feature pairs (AND conditions)."""
        features = self._registry.features_for_market(market.market_type.value)
        hypotheses: list[ResearchHypothesis] = []

        if len(features) < 2:
            return hypotheses

        # Select top feature pairs (limit combinations)
        pairs = []
        for i, f1 in enumerate(features):
            for f2 in features[i + 1:]:
                pairs.append((f1, f2))
        # Limit pairs
        if len(pairs) > 50:
            indices = self._rng.choice(len(pairs), size=50, replace=False)
            pairs = [pairs[i] for i in indices]

        for f1, f2 in pairs:
            fid1, fid2 = f1.feature_id, f2.feature_id
            vals1 = [fv.get(fid1) for fv in feature_values if fid1 in fv]
            vals2 = [fv.get(fid2) for fv in feature_values if fid2 in fv]

            if len(vals1) < self._budget.min_sample_size or len(vals2) < self._budget.min_sample_size:
                continue

            t1 = float(np.median(vals1))
            t2 = float(np.median(vals2))

            hyp = ResearchHypothesis(
                hypothesis_id=f"pair_{fid1}_{fid2}_{market.market_type.value}_OVER",
                market=market.market_type,
                feature_ids=(fid1, fid2),
                conditions=((fid1, ">", t1), (fid2, ">", t2)),
                direction="OVER",
                generation_method=GenerationMethod.DETERMINISTIC,
                rationale=f"{f1.name} > {t1:.3f} AND {f2.name} > {t2:.3f} → OVER",
            )
            hypotheses.append(hyp)

            if len(hypotheses) >= self._budget.max_candidates:
                break

        return hypotheses[:self._budget.max_candidates]

    def generate_all(
        self,
        market: ResearchMarket,
        feature_values: list[dict[str, float]],
    ) -> list[ResearchHypothesis]:
        """Generate all candidate hypotheses within budget."""
        singles = self.generate_single_feature_hypotheses(market, feature_values)
        pairs = self.generate_pair_hypotheses(market, feature_values)
        all_candidates = singles + pairs
        return all_candidates[:self._budget.max_candidates]
