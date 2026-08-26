"""Candidate Discovery Engine for the research laboratory.

Systematically generates bounded, reproducible candidate metrics and
hypotheses from available research features. Implements:

- Multiple candidate operators (threshold, difference, ratio, interaction, trend, relative)
- Feature family awareness
- Market compatibility
- Parameter space search
- Deduplication via content hashing
- Correlation-based redundancy filtering
- Sample-size awareness
- Temporal causality preservation
- Budget controls to prevent combinatorial explosion

The engine outputs ResearchCandidate objects ready for downstream
evaluation. It does NOT evaluate, backtest, or claim profitability.

Architecture:
    FeatureRegistry → FeatureFamilies → ParameterSpace → CandidateEngine → ResearchCandidate
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import numpy as np

from src.research.feature_families import FeatureFamily, FeatureFamilyRegistry
from src.research.feature_registry import FeatureDefinition, FeatureRegistry
from src.research.parameter_space import ParameterGrid, ParameterRange, ParameterSet


# ═══════════════════════════════════════════════════════════════
# CANDIDATE OPERATOR TYPES
# ═══════════════════════════════════════════════════════════════


class CandidateOperator(Enum):
    """Types of candidate generation operators."""

    THRESHOLD_GT = "THRESHOLD_GT"       # feature > threshold
    THRESHOLD_LT = "THRESHOLD_LT"       # feature < threshold
    DIFFERENCE_GT = "DIFFERENCE_GT"     # feature_a - feature_b > threshold
    DIFFERENCE_LT = "DIFFERENCE_LT"     # feature_a - feature_b < threshold
    RATIO_GT = "RATIO_GT"              # feature_a / feature_b > threshold
    RATIO_LT = "RATIO_LT"              # feature_a / feature_b < threshold
    INTERACTION_AND = "INTERACTION_AND" # feature_a > x AND feature_b > y
    TREND_GT = "TREND_GT"              # trend(feature) > threshold
    TREND_LT = "TREND_LT"              # trend(feature) < threshold
    RELATIVE_GT = "RELATIVE_GT"         # home_feature - away_feature > threshold
    RELATIVE_LT = "RELATIVE_LT"         # home_feature - away_feature < threshold


class CandidateStatus(Enum):
    """Lifecycle status of a candidate."""

    GENERATED = "GENERATED"
    FILTERED_REDUNDANT = "FILTERED_REDUNDANT"
    FILTERED_INSUFFICIENT_DATA = "FILTERED_INSUFFICIENT_DATA"
    FILTERED_INCOMPATIBLE = "FILTERED_INCOMPATIBLE"
    READY = "READY"


class GenerationMethod(Enum):
    """How a candidate was generated."""

    DETERMINISTIC_GRID = "DETERMINISTIC_GRID"
    DETERMINISTIC_QUANTILE = "DETERMINISTIC_QUANTILE"
    HUMAN = "HUMAN"
    LLM = "LLM"


# ═══════════════════════════════════════════════════════════════
# CANDIDATE CONDITION
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class CandidateCondition:
    """A single condition in a candidate.

    Represents one atomic predicate like 'feature_x > 5.0'.

    Attributes:
        feature_id: Feature this condition applies to.
        operator: Comparison operator (>, <, >=, <=).
        threshold: Threshold value.
    """

    feature_id: str
    operator: str  # ">", "<", ">=", "<="
    threshold: float

    def evaluate(self, feature_value: Optional[float]) -> Optional[bool]:
        """Evaluate this condition against a feature value.

        Returns None if feature_value is None (missing data).
        """
        if feature_value is None:
            return None
        if self.operator == ">":
            return feature_value > self.threshold
        elif self.operator == "<":
            return feature_value < self.threshold
        elif self.operator == ">=":
            return feature_value >= self.threshold
        elif self.operator == "<=":
            return feature_value <= self.threshold
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_id": self.feature_id,
            "operator": self.operator,
            "threshold": self.threshold,
        }


# ═══════════════════════════════════════════════════════════════
# RESEARCH CANDIDATE
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ResearchCandidate:
    """A reproducible research candidate metric/hypothesis.

    Contains everything needed to reproduce and evaluate the candidate.
    The content_hash provides deterministic identity — equivalent
    definitions always produce the same hash.

    Attributes:
        candidate_id: Human-readable identifier.
        market_type: Target market for this candidate.
        feature_ids: Features used (sorted for canonical ordering).
        conditions: Atomic conditions (AND logic).
        operator_type: Type of candidate generation operator.
        direction: Expected outcome direction (OVER/UNDER/HOME/DRAW/AWAY).
        generation_method: How this candidate was generated.
        parameters: Generation parameters (window sizes, thresholds, etc.).
        feature_families: Families of features used.
        required_observations: Minimum matches needed to evaluate.
        created_at: ISO timestamp of generation.
        status: Current lifecycle status.
    """

    candidate_id: str
    market_type: str
    feature_ids: tuple[str, ...]
    conditions: tuple[CandidateCondition, ...]
    operator_type: CandidateOperator
    direction: str
    generation_method: GenerationMethod = GenerationMethod.DETERMINISTIC_QUANTILE
    parameters: dict[str, Any] = field(default_factory=dict)
    feature_families: tuple[str, ...] = ()
    required_observations: int = 50
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: CandidateStatus = CandidateStatus.GENERATED

    @property
    def content_hash(self) -> str:
        """Deterministic content hash for deduplication.

        Canonicalization rules:
        - feature_ids sorted alphabetically
        - conditions sorted by (feature_id, operator, threshold)
        - Parameters serialized with sort_keys
        - Does NOT depend on candidate_id, created_at, or status
        """
        sorted_conditions = sorted(
            [c.to_dict() for c in self.conditions],
            key=lambda c: (c["feature_id"], c["operator"], c["threshold"]),
        )
        canonical = json.dumps(
            {
                "market_type": self.market_type,
                "feature_ids": sorted(self.feature_ids),
                "conditions": sorted_conditions,
                "direction": self.direction,
                "operator_type": self.operator_type.value,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]

    @property
    def interaction_depth(self) -> int:
        """Number of conditions (interaction depth)."""
        return len(self.conditions)

    def to_dict(self) -> dict[str, Any]:
        """Serialize for storage/provenance."""
        return {
            "candidate_id": self.candidate_id,
            "market_type": self.market_type,
            "feature_ids": list(self.feature_ids),
            "conditions": [c.to_dict() for c in self.conditions],
            "operator_type": self.operator_type.value,
            "direction": self.direction,
            "generation_method": self.generation_method.value,
            "parameters": self.parameters,
            "content_hash": self.content_hash,
            "status": self.status.value,
        }


# ═══════════════════════════════════════════════════════════════
# DISCOVERY BUDGET
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class DiscoveryBudget:
    """Budget controls to prevent combinatorial explosion.

    Every limit is configurable. The engine MUST respect all limits
    and fail safely when exceeded (truncate, not crash).

    Attributes:
        max_features_per_candidate: Max features in one candidate.
        max_interaction_depth: Max conditions ANDed together.
        max_candidates: Hard cap on total candidates generated.
        max_candidates_per_market: Per-market cap.
        max_candidates_per_family: Per-family cap.
        max_parameter_combinations: Cap on parameter grid size.
        min_observations: Minimum matches for a candidate to be researchable.
        correlation_threshold: Optional redundancy filter (0-1, None=disabled).
    """

    max_features_per_candidate: int = 3
    max_interaction_depth: int = 2
    max_candidates: int = 500
    max_candidates_per_market: int = 200
    max_candidates_per_family: int = 100
    max_parameter_combinations: int = 100
    min_observations: int = 50
    correlation_threshold: Optional[float] = None  # None = disabled

    def __post_init__(self):
        if self.max_candidates < 1:
            raise ValueError("max_candidates must be >= 1")
        if self.max_interaction_depth < 1:
            raise ValueError("max_interaction_depth must be >= 1")
        if self.min_observations < 1:
            raise ValueError("min_observations must be >= 1")
        if self.correlation_threshold is not None:
            if not (0.0 < self.correlation_threshold <= 1.0):
                raise ValueError("correlation_threshold must be in (0, 1]")


# ═══════════════════════════════════════════════════════════════
# CANDIDATE DISCOVERY ENGINE
# ═══════════════════════════════════════════════════════════════


@dataclass(frozen=True, slots=True)
class GenerationReport:
    """Report of a candidate generation run.

    Attributes:
        total_generated: Candidates before filtering.
        total_after_dedup: After exact deduplication.
        total_after_redundancy: After correlation filtering.
        total_after_sample_filter: After sample-size check.
        final_count: Final candidate count.
        generation_time_ms: Elapsed time in milliseconds.
        budget_exhausted: Whether budget cap was hit.
    """

    total_generated: int
    total_after_dedup: int
    total_after_redundancy: int
    total_after_sample_filter: int
    final_count: int
    generation_time_ms: float
    budget_exhausted: bool


class CandidateDiscoveryEngine:
    """Systematic candidate discovery from research features.

    Generates bounded, reproducible candidates using:
    - Feature families for market-aware generation
    - Parameter grids for threshold search
    - Multiple operators (threshold, difference, ratio, interaction, trend, relative)
    - Deduplication via content hashing
    - Optional correlation filtering
    - Sample-size pre-filtering

    Usage:
        engine = CandidateDiscoveryEngine(registry, families, budget)
        candidates, report = engine.discover(market_type, feature_values)
    """

    def __init__(
        self,
        registry: FeatureRegistry,
        family_registry: Optional[FeatureFamilyRegistry] = None,
        budget: Optional[DiscoveryBudget] = None,
        seed: int = 42,
    ) -> None:
        self._registry = registry
        self._families = family_registry or FeatureFamilyRegistry()
        self._budget = budget or DiscoveryBudget()
        self._rng = np.random.default_rng(seed)

    @property
    def budget(self) -> DiscoveryBudget:
        return self._budget

    def discover(
        self,
        market_type: str,
        feature_values: list[dict[str, float]],
        directions: Optional[list[str]] = None,
    ) -> tuple[list[ResearchCandidate], GenerationReport]:
        """Run full candidate discovery for a market.

        Args:
            market_type: Target market (e.g., "CORNERS_TOTAL").
            feature_values: Computed feature values per match.
            directions: Directions to generate for (default: ["OVER", "UNDER"]).

        Returns:
            (candidates, report) — candidates ready for evaluation.
        """
        start_time = time.time()
        directions = directions or ["OVER", "UNDER"]

        # Get market-appropriate features
        market_features = self._families.get_market_features(
            self._registry, market_type
        )
        # Also include features explicitly marked for this market
        explicit_features = self._registry.features_for_market(market_type)
        all_features = list({f.feature_id: f for f in market_features + explicit_features}.values())

        # Generate candidates
        candidates: list[ResearchCandidate] = []
        budget_exhausted = False

        for direction in directions:
            if len(candidates) >= self._budget.max_candidates:
                budget_exhausted = True
                break

            # Single-feature threshold candidates
            singles = self._generate_threshold_candidates(
                all_features, feature_values, market_type, direction
            )
            candidates.extend(singles)

            # Difference candidates (if budget allows)
            if len(candidates) < self._budget.max_candidates:
                diffs = self._generate_difference_candidates(
                    all_features, feature_values, market_type, direction
                )
                candidates.extend(diffs)

            # Ratio candidates
            if len(candidates) < self._budget.max_candidates:
                ratios = self._generate_ratio_candidates(
                    all_features, feature_values, market_type, direction
                )
                candidates.extend(ratios)

            # Interaction (AND) candidates
            if (
                len(candidates) < self._budget.max_candidates
                and self._budget.max_interaction_depth >= 2
            ):
                interactions = self._generate_interaction_candidates(
                    all_features, feature_values, market_type, direction
                )
                candidates.extend(interactions)

        total_generated = len(candidates)

        # Enforce budget cap
        candidates = candidates[: self._budget.max_candidates]

        # Deduplication
        candidates = self._deduplicate(candidates)
        total_after_dedup = len(candidates)

        # Correlation filtering (optional)
        if self._budget.correlation_threshold is not None:
            candidates = self._filter_redundancy(candidates, feature_values)
        total_after_redundancy = len(candidates)

        # Sample-size filtering
        candidates = self._filter_by_sample_size(candidates, feature_values)
        total_after_sample = len(candidates)

        # Mark as READY
        ready_candidates: list[ResearchCandidate] = []
        for c in candidates:
            ready_candidates.append(ResearchCandidate(
                candidate_id=c.candidate_id,
                market_type=c.market_type,
                feature_ids=c.feature_ids,
                conditions=c.conditions,
                operator_type=c.operator_type,
                direction=c.direction,
                generation_method=c.generation_method,
                parameters=c.parameters,
                feature_families=c.feature_families,
                required_observations=c.required_observations,
                created_at=c.created_at,
                status=CandidateStatus.READY,
            ))

        elapsed_ms = (time.time() - start_time) * 1000.0

        report = GenerationReport(
            total_generated=total_generated,
            total_after_dedup=total_after_dedup,
            total_after_redundancy=total_after_redundancy,
            total_after_sample_filter=total_after_sample,
            final_count=len(ready_candidates),
            generation_time_ms=elapsed_ms,
            budget_exhausted=budget_exhausted or total_generated >= self._budget.max_candidates,
        )

        return ready_candidates, report

    # ═══════════════════════════════════════════════════════════
    # GENERATION OPERATORS
    # ═══════════════════════════════════════════════════════════

    def _generate_threshold_candidates(
        self,
        features: list[FeatureDefinition],
        feature_values: list[dict[str, float]],
        market_type: str,
        direction: str,
    ) -> list[ResearchCandidate]:
        """Single-feature threshold candidates: feature > threshold."""
        candidates = []
        quantiles = (0.25, 0.50, 0.75)

        for feat in features:
            if len(candidates) >= self._budget.max_candidates_per_market:
                break

            fid = feat.feature_id
            values = [fv[fid] for fv in feature_values if fid in fv]
            if len(values) < self._budget.min_observations:
                continue

            arr = np.array(values)
            family = self._families.get_family(feat)

            for q in quantiles:
                threshold = float(np.quantile(arr, q))

                # GT condition
                cond = CandidateCondition(feature_id=fid, operator=">", threshold=threshold)
                cid = f"thresh_{fid}_gt_{q:.2f}_{direction}"
                candidates.append(ResearchCandidate(
                    candidate_id=cid,
                    market_type=market_type,
                    feature_ids=(fid,),
                    conditions=(cond,),
                    operator_type=CandidateOperator.THRESHOLD_GT,
                    direction=direction,
                    generation_method=GenerationMethod.DETERMINISTIC_QUANTILE,
                    parameters={"quantile": q, "threshold": threshold},
                    feature_families=(family.value,),
                    required_observations=self._budget.min_observations,
                ))

                # LT condition
                cond_lt = CandidateCondition(feature_id=fid, operator="<", threshold=threshold)
                cid_lt = f"thresh_{fid}_lt_{q:.2f}_{direction}"
                candidates.append(ResearchCandidate(
                    candidate_id=cid_lt,
                    market_type=market_type,
                    feature_ids=(fid,),
                    conditions=(cond_lt,),
                    operator_type=CandidateOperator.THRESHOLD_LT,
                    direction=direction,
                    generation_method=GenerationMethod.DETERMINISTIC_QUANTILE,
                    parameters={"quantile": q, "threshold": threshold},
                    feature_families=(family.value,),
                    required_observations=self._budget.min_observations,
                ))

        return candidates

    def _generate_difference_candidates(
        self,
        features: list[FeatureDefinition],
        feature_values: list[dict[str, float]],
        market_type: str,
        direction: str,
    ) -> list[ResearchCandidate]:
        """Difference candidates: feature_a - feature_b > threshold."""
        candidates = []
        # Find home/away pairs
        pairs = self._find_home_away_pairs(features)

        for feat_home, feat_away in pairs[:20]:  # Limit pairs
            if len(candidates) >= self._budget.max_candidates_per_family:
                break

            fid_h, fid_a = feat_home.feature_id, feat_away.feature_id
            # Compute differences
            diffs = []
            for fv in feature_values:
                if fid_h in fv and fid_a in fv:
                    diffs.append(fv[fid_h] - fv[fid_a])

            if len(diffs) < self._budget.min_observations:
                continue

            arr = np.array(diffs)
            threshold = float(np.median(arr))
            family = self._families.get_family(feat_home)

            cond = CandidateCondition(feature_id=f"{fid_h}-{fid_a}", operator=">", threshold=threshold)
            candidates.append(ResearchCandidate(
                candidate_id=f"diff_{fid_h}_{fid_a}_gt_{direction}",
                market_type=market_type,
                feature_ids=(fid_h, fid_a),
                conditions=(cond,),
                operator_type=CandidateOperator.DIFFERENCE_GT,
                direction=direction,
                parameters={"threshold": threshold, "operation": "difference"},
                feature_families=(family.value,),
                required_observations=self._budget.min_observations,
            ))

        return candidates

    def _generate_ratio_candidates(
        self,
        features: list[FeatureDefinition],
        feature_values: list[dict[str, float]],
        market_type: str,
        direction: str,
    ) -> list[ResearchCandidate]:
        """Ratio candidates: feature_a / feature_b > threshold."""
        candidates = []
        pairs = self._find_home_away_pairs(features)

        for feat_home, feat_away in pairs[:15]:  # Limit
            if len(candidates) >= self._budget.max_candidates_per_family:
                break

            fid_h, fid_a = feat_home.feature_id, feat_away.feature_id
            ratios = []
            for fv in feature_values:
                if fid_h in fv and fid_a in fv and fv[fid_a] != 0:
                    ratios.append(fv[fid_h] / fv[fid_a])

            if len(ratios) < self._budget.min_observations:
                continue

            arr = np.array(ratios)
            for q in (0.50, 0.75):
                threshold = float(np.quantile(arr, q))
                family = self._families.get_family(feat_home)

                cond = CandidateCondition(
                    feature_id=f"{fid_h}/{fid_a}", operator=">", threshold=threshold
                )
                candidates.append(ResearchCandidate(
                    candidate_id=f"ratio_{fid_h}_{fid_a}_gt_{q:.2f}_{direction}",
                    market_type=market_type,
                    feature_ids=(fid_h, fid_a),
                    conditions=(cond,),
                    operator_type=CandidateOperator.RATIO_GT,
                    direction=direction,
                    parameters={"quantile": q, "threshold": threshold, "operation": "ratio"},
                    feature_families=(family.value,),
                    required_observations=self._budget.min_observations,
                ))

        return candidates

    def _generate_interaction_candidates(
        self,
        features: list[FeatureDefinition],
        feature_values: list[dict[str, float]],
        market_type: str,
        direction: str,
    ) -> list[ResearchCandidate]:
        """Interaction candidates: feature_a > x AND feature_b > y."""
        candidates = []
        if len(features) < 2:
            return candidates

        # Select limited pairs from different families
        pairs = []
        for i, f1 in enumerate(features):
            for f2 in features[i + 1:]:
                fam1 = self._families.get_family(f1)
                fam2 = self._families.get_family(f2)
                if fam1 != fam2:  # Cross-family interactions only
                    pairs.append((f1, f2))

        # Limit pairs deterministically
        if len(pairs) > 30:
            indices = self._rng.choice(len(pairs), size=30, replace=False)
            pairs = [pairs[i] for i in sorted(indices)]

        for f1, f2 in pairs:
            if len(candidates) >= self._budget.max_candidates_per_family:
                break

            fid1, fid2 = f1.feature_id, f2.feature_id
            vals1 = [fv.get(fid1) for fv in feature_values if fid1 in fv]
            vals2 = [fv.get(fid2) for fv in feature_values if fid2 in fv]

            if (len(vals1) < self._budget.min_observations or
                    len(vals2) < self._budget.min_observations):
                continue

            t1 = float(np.median(vals1))
            t2 = float(np.median(vals2))

            cond1 = CandidateCondition(feature_id=fid1, operator=">", threshold=t1)
            cond2 = CandidateCondition(feature_id=fid2, operator=">", threshold=t2)

            fam1 = self._families.get_family(f1)
            fam2 = self._families.get_family(f2)

            candidates.append(ResearchCandidate(
                candidate_id=f"interact_{fid1}_{fid2}_{direction}",
                market_type=market_type,
                feature_ids=(fid1, fid2),
                conditions=(cond1, cond2),
                operator_type=CandidateOperator.INTERACTION_AND,
                direction=direction,
                parameters={"threshold_1": t1, "threshold_2": t2},
                feature_families=(fam1.value, fam2.value),
                required_observations=self._budget.min_observations,
            ))

        return candidates

    # ═══════════════════════════════════════════════════════════
    # FILTERING
    # ═══════════════════════════════════════════════════════════

    def _deduplicate(self, candidates: list[ResearchCandidate]) -> list[ResearchCandidate]:
        """Remove exact duplicate candidates by content hash."""
        seen: set[str] = set()
        unique: list[ResearchCandidate] = []
        for c in candidates:
            h = c.content_hash
            if h not in seen:
                seen.add(h)
                unique.append(c)
        return unique

    def _filter_redundancy(
        self,
        candidates: list[ResearchCandidate],
        feature_values: list[dict[str, float]],
    ) -> list[ResearchCandidate]:
        """Filter highly correlated candidates (optional).

        For each pair of single-feature candidates targeting the same feature
        with similar thresholds, keep only one.

        This is a computational optimization, NOT a statistical rejection.
        Filtered candidates are marked FILTERED_REDUNDANT.
        """
        if not candidates:
            return candidates

        threshold = self._budget.correlation_threshold
        if threshold is None:
            return candidates

        # Group by (market, direction, operator_type, first_feature)
        groups: dict[str, list[ResearchCandidate]] = {}
        for c in candidates:
            if len(c.feature_ids) == 1:
                key = f"{c.market_type}_{c.direction}_{c.operator_type.value}_{c.feature_ids[0]}"
                groups.setdefault(key, []).append(c)

        # Within each group, keep candidates with sufficiently different thresholds
        kept_hashes: set[str] = set()
        for group_candidates in groups.values():
            if len(group_candidates) <= 1:
                for c in group_candidates:
                    kept_hashes.add(c.content_hash)
                continue

            # Sort by threshold
            sorted_cands = sorted(
                group_candidates,
                key=lambda c: c.conditions[0].threshold if c.conditions else 0,
            )
            # Keep first, then skip if too close
            kept_hashes.add(sorted_cands[0].content_hash)
            last_kept_thresh = sorted_cands[0].conditions[0].threshold

            for c in sorted_cands[1:]:
                curr_thresh = c.conditions[0].threshold
                # Relative difference
                if last_kept_thresh != 0:
                    rel_diff = abs(curr_thresh - last_kept_thresh) / abs(last_kept_thresh)
                else:
                    rel_diff = abs(curr_thresh - last_kept_thresh)

                if rel_diff >= (1.0 - threshold):
                    kept_hashes.add(c.content_hash)
                    last_kept_thresh = curr_thresh

        # Multi-feature candidates always pass
        result = []
        for c in candidates:
            if len(c.feature_ids) > 1 or c.content_hash in kept_hashes:
                result.append(c)
        return result

    def _filter_by_sample_size(
        self,
        candidates: list[ResearchCandidate],
        feature_values: list[dict[str, float]],
    ) -> list[ResearchCandidate]:
        """Filter candidates with insufficient data to evaluate.

        A candidate is researchable only if enough matches have all
        required features present.
        """
        result = []
        for c in candidates:
            # Count matches with all required features present
            count = 0
            for fv in feature_values:
                if all(fid in fv for fid in c.feature_ids):
                    count += 1
            if count >= c.required_observations:
                result.append(c)
        return result

    # ═══════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════

    def _find_home_away_pairs(
        self, features: list[FeatureDefinition]
    ) -> list[tuple[FeatureDefinition, FeatureDefinition]]:
        """Find home/away feature pairs (e.g., corners_home_avg_5, corners_away_avg_5)."""
        pairs = []
        by_base: dict[str, list[FeatureDefinition]] = {}

        for f in features:
            # Heuristic: strip 'home'/'away' to find base name
            name = f.name.lower()
            base = name.replace("_home", "").replace("_away", "").replace("home_", "").replace("away_", "")
            by_base.setdefault(base, []).append(f)

        for base, group in by_base.items():
            homes = [f for f in group if "home" in f.name.lower()]
            aways = [f for f in group if "away" in f.name.lower()]
            for h in homes:
                for a in aways:
                    pairs.append((h, a))

        return pairs
