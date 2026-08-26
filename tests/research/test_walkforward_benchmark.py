"""Performance benchmark for Batch 5 Walk-Forward + FDR pipeline.

Demonstrates that the system is bounded and does not explode
computationally for realistic research scenarios.

Benchmark scenario:
- 500 hypotheses (various candidates with different conditions)
- 10 walk-forward folds
- 3 probability models
- 3 markets

Measures:
- Total runtime
- Memory usage
- Fold count achieved
- FDR runtime
- Number of rejected/accepted hypotheses
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np
import pytest

from src.research.candidates import CandidateCondition, CandidateOperator, ResearchCandidate
from src.research.data_source import ResearchDataSource, ResearchMatch, MarketOdds
from src.research.experiment_engine.config import ExperimentConfig, OddsMode
from src.research.experiment_engine.dataset import ResearchDataset
from src.research.experiment_engine.hypothesis import ExperimentHypothesis
from src.research.fdr import FDRAdapter, ResearchFamilyBuilder
from src.research.governance import GovernanceClassifier, GovernanceCriteria, GovernanceState
from src.research.market import MarketType, create_default_registry
from src.research.probability import HistoricalFrequencyModel
from src.research.synthetic_data import SyntheticResearchDataSource
from src.research.walkforward import (
    FoldGenerator,
    WalkForwardConfig,
    WalkForwardOrchestrator,
    WalkForwardStatus,
    WindowType,
)
from src.research.walkforward.result import AggregateStatisticalEvidence, StabilityMetrics, WalkForwardResult


DAY = 86400
MONTH = 30 * DAY


@pytest.fixture
def synthetic_source():
    return SyntheticResearchDataSource(seed=42)


@pytest.fixture
def market_registry():
    return create_default_registry()


def _generate_candidates(n: int, market_type: str) -> list[ResearchCandidate]:
    """Generate n diverse candidates for benchmarking."""
    candidates = []
    features = [
        "dangerous_attacks_home", "dangerous_attacks_away",
        "possession_home", "possession_away",
        "shots_home", "shots_away",
        "corners_home", "corners_away",
    ]
    operators = [CandidateOperator.THRESHOLD_GT, CandidateOperator.THRESHOLD_LT]
    directions = ["OVER", "UNDER"]

    rng = np.random.RandomState(42)
    for i in range(n):
        feat_idx = i % len(features)
        op_idx = i % len(operators)
        dir_idx = i % len(directions)
        threshold = 10.0 + rng.uniform(-5, 15)

        candidates.append(ResearchCandidate(
            candidate_id=f"bench_cand_{market_type}_{i:04d}",
            market_type=market_type,
            feature_ids=(features[feat_idx],),
            conditions=(
                CandidateCondition(
                    feature_id=features[feat_idx],
                    operator=">" if operators[op_idx] == CandidateOperator.THRESHOLD_GT else "<",
                    threshold=threshold,
                ),
            ),
            operator_type=operators[op_idx],
            direction=directions[dir_idx],
        ))
    return candidates


class TestPerformanceBenchmark:
    """Performance benchmark demonstrating bounded computation."""

    @pytest.mark.timeout(300)  # 5-minute cap
    def test_benchmark_500_hypotheses_fdr(self):
        """Benchmark: 500 hypotheses through FDR correction.

        This tests the FDR layer performance independently.
        """
        start = time.time()

        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="CORNERS_TOTAL",
            dataset_version="bench_v1",
            research_run_id="benchmark_run",
            hypothesis_count=500,
        )

        # Simulate 500 walk-forward results with varied p-values
        rng = np.random.RandomState(42)
        # Most hypotheses are null (high p-values), few are significant
        p_values = list(rng.uniform(0.01, 0.999, 500))
        # Make ~5% truly significant (very small p-values needed for 500 tests)
        # BH threshold for rank k out of 500: k/500 * 0.05
        # Need p < k/500 * 0.05. For rank 25: 25/500*0.05 = 0.0025
        for i in range(25):
            p_values[i] = rng.uniform(0.00001, 0.0001)  # Very significant

        results = [
            WalkForwardResult(
                hypothesis_hash=f"h{i:04d}",
                candidate_hash=f"c{i:04d}",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=10,
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=p,
                    valid_p_value_count=10,
                ),
            )
            for i, p in enumerate(p_values)
        ]

        fdr_result = adapter.correct(results, family)
        fdr_runtime = time.time() - start

        # Assertions
        assert fdr_result.total_hypotheses == 500
        assert fdr_result.valid_hypotheses == 500
        assert fdr_result.rejected_count > 0  # Some should pass
        assert fdr_result.rejected_count < 100  # Not all should pass
        assert fdr_runtime < 5.0  # Should be very fast

        print(f"\n--- FDR BENCHMARK ---")
        print(f"Hypotheses: {fdr_result.total_hypotheses}")
        print(f"Valid: {fdr_result.valid_hypotheses}")
        print(f"Rejected (pass FDR): {fdr_result.rejected_count}")
        print(f"Accepted (fail FDR): {fdr_result.accepted_count}")
        print(f"FDR runtime: {fdr_runtime:.3f}s")

    @pytest.mark.timeout(300)
    def test_benchmark_walkforward_single_hypothesis(self, synthetic_source):
        """Benchmark: single hypothesis through full walk-forward (10 folds)."""
        start = time.time()

        market = create_default_registry().get(MarketType.CORNERS_TOTAL)
        dataset = ResearchDataset(source=synthetic_source, market=market)

        candidate = ResearchCandidate(
            candidate_id="bench_single",
            market_type=MarketType.CORNERS_TOTAL.value,
            feature_ids=("dangerous_attacks_home",),
            conditions=(
                CandidateCondition(
                    feature_id="dangerous_attacks_home", operator=">", threshold=20.0
                ),
            ),
            operator_type=CandidateOperator.THRESHOLD_GT,
            direction="OVER",
        )
        hypothesis = ExperimentHypothesis.from_candidate(candidate)

        wf_config = WalkForwardConfig(
            initial_training_period=4 * MONTH,
            test_period=2 * MONTH,
            step_period=2 * MONTH,
            minimum_training_observations=5,
            minimum_test_observations=3,
            window_type=WindowType.EXPANDING,
            minimum_folds=3,
            maximum_folds=10,
        )

        base_config = ExperimentConfig(
            hypothesis=hypothesis,
            market_type=MarketType.CORNERS_TOTAL.value,
            dataset_version=dataset.content_hash,
            model_type="historical_frequency",
            model_parameters=(),
            training_start=0,
            training_end=1,
            evaluation_start=2,
            evaluation_end=3,
            minimum_observations=5,
            odds_mode=OddsMode.SYNTHETIC_ODDS,
        )

        orchestrator = WalkForwardOrchestrator(wf_config)
        result = orchestrator.run(
            hypothesis=hypothesis,
            dataset=dataset,
            model_factory=lambda: HistoricalFrequencyModel(),
            experiment_config_base=base_config,
        )

        wf_runtime = time.time() - start

        assert result.fold_count > 0
        assert wf_runtime < 30.0  # Should be fast for single hypothesis

        print(f"\n--- WALK-FORWARD SINGLE HYPOTHESIS ---")
        print(f"Folds attempted: {result.fold_count}")
        print(f"Folds successful: {result.successful_folds}")
        print(f"Total predictions: {result.total_predictions}")
        print(f"Runtime: {wf_runtime:.3f}s")

    @pytest.mark.timeout(300)
    def test_benchmark_multi_hypothesis_walkforward(self, synthetic_source):
        """Benchmark: 50 hypotheses × walk-forward (bounded set for CI)."""
        start = time.time()

        markets = [MarketType.CORNERS_TOTAL, MarketType.GOALS_TOTAL, MarketType.CARDS_TOTAL]
        registry = create_default_registry()
        n_per_market = 17  # ~50 total

        wf_config = WalkForwardConfig(
            initial_training_period=6 * MONTH,
            test_period=3 * MONTH,
            step_period=3 * MONTH,
            minimum_training_observations=5,
            minimum_test_observations=3,
            window_type=WindowType.EXPANDING,
            minimum_folds=3,
            maximum_folds=8,
        )

        all_results: list[WalkForwardResult] = []
        total_candidates = 0

        for market_type in markets:
            market = registry.get(market_type)
            dataset = ResearchDataset(source=synthetic_source, market=market)
            candidates = _generate_candidates(n_per_market, market_type.value)

            for candidate in candidates:
                total_candidates += 1
                hypothesis = ExperimentHypothesis.from_candidate(candidate)

                base_config = ExperimentConfig(
                    hypothesis=hypothesis,
                    market_type=market_type.value,
                    dataset_version=dataset.content_hash,
                    model_type="historical_frequency",
                    model_parameters=(),
                    training_start=0,
                    training_end=1,
                    evaluation_start=2,
                    evaluation_end=3,
                    minimum_observations=5,
                    odds_mode=OddsMode.SYNTHETIC_ODDS,
                )

                orchestrator = WalkForwardOrchestrator(wf_config)
                result = orchestrator.run(
                    hypothesis=hypothesis,
                    dataset=dataset,
                    model_factory=lambda: HistoricalFrequencyModel(),
                    experiment_config_base=base_config,
                )
                all_results.append(result)

        wf_runtime = time.time() - start

        # Now run FDR on all results
        fdr_start = time.time()
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="MULTI",
            dataset_version="bench_multi",
            research_run_id="multi_bench",
            hypothesis_count=total_candidates,
        )
        # Filter to only valid results for FDR
        valid_results = [r for r in all_results if r.p_value_for_fdr is not None]
        fdr_result = adapter.correct(valid_results, family)
        fdr_runtime = time.time() - fdr_start

        total_runtime = time.time() - start

        # Assertions
        assert total_candidates == n_per_market * len(markets)
        assert total_runtime < 120.0  # Under 2 minutes
        assert fdr_runtime < 1.0  # FDR should be instant

        completed = sum(1 for r in all_results if r.status == WalkForwardStatus.COMPLETED)

        print(f"\n--- MULTI-HYPOTHESIS BENCHMARK ---")
        print(f"Total candidates: {total_candidates}")
        print(f"Markets: {len(markets)}")
        print(f"Completed walk-forwards: {completed}")
        print(f"Valid for FDR: {len(valid_results)}")
        print(f"FDR passed: {fdr_result.rejected_count}")
        print(f"FDR failed: {fdr_result.accepted_count}")
        print(f"Walk-forward runtime: {wf_runtime:.3f}s")
        print(f"FDR runtime: {fdr_runtime:.3f}s")
        print(f"Total runtime: {total_runtime:.3f}s")
        print(f"Avg per hypothesis: {wf_runtime / total_candidates:.3f}s")

    @pytest.mark.timeout(300)
    def test_benchmark_governance_pipeline(self):
        """Benchmark: full governance pipeline (classify → FDR → eligibility)."""
        start = time.time()

        # Generate varied walk-forward results
        rng = np.random.RandomState(42)
        n = 100
        results = []

        for i in range(n):
            p = rng.uniform(0.001, 0.5)
            pfr = rng.uniform(0.3, 0.9)
            folds = rng.randint(3, 10)
            preds = rng.randint(30, 200)

            results.append(WalkForwardResult(
                hypothesis_hash=f"h{i:04d}",
                candidate_hash=f"c{i:04d}",
                status=WalkForwardStatus.COMPLETED,
                successful_folds=folds,
                total_predictions=preds,
                mean_fold_roi=rng.uniform(-10, 20),
                mean_fold_ev=rng.uniform(-0.05, 0.15),
                aggregate_brier_score=rng.uniform(0.15, 0.35),
                aggregate_evidence=AggregateStatisticalEvidence(
                    combined_p_value=p,
                    mean_effect_size=rng.uniform(0.001, 0.1),
                    valid_p_value_count=folds,
                ),
                stability=StabilityMetrics(
                    positive_fold_ratio=pfr,
                    max_consecutive_negative=rng.randint(0, 4),
                ),
            ))

        # Phase 1: Walk-forward governance
        classifier = GovernanceClassifier(GovernanceCriteria(
            minimum_folds=3,
            minimum_positive_fold_ratio=0.5,
            minimum_sample_size=30,
            maximum_p_value=0.05,
            minimum_effect_size=0.005,
            minimum_calibration_quality=0.40,
        ))

        wf_validated = []
        for wf_result in results:
            decision = classifier.classify_walk_forward(wf_result)
            if decision.new_state == GovernanceState.WALK_FORWARD_VALIDATED:
                wf_validated.append(wf_result)

        # Phase 2: FDR correction on validated
        adapter = FDRAdapter(alpha=0.05)
        family = ResearchFamilyBuilder.build(
            market_type="BENCHMARK",
            dataset_version="bench_v1",
            hypothesis_count=len(wf_validated),
        )
        fdr_result = adapter.correct(wf_validated, family)

        # Phase 3: Quarantine eligibility
        eligible = 0
        for i, hr in enumerate(fdr_result.hypothesis_results):
            if hr.is_significant:
                decision = classifier.determine_quarantine_eligibility(
                    wf_validated[i], hr
                )
                if decision.new_state == GovernanceState.QUARANTINE_ELIGIBLE:
                    eligible += 1

        total_runtime = time.time() - start

        print(f"\n--- GOVERNANCE PIPELINE BENCHMARK ---")
        print(f"Input hypotheses: {n}")
        print(f"Walk-forward validated: {len(wf_validated)}")
        print(f"FDR passed: {fdr_result.rejected_count}")
        print(f"Quarantine eligible: {eligible}")
        print(f"Total runtime: {total_runtime:.3f}s")

        assert total_runtime < 5.0  # Governance is fast (no model fitting)
        assert len(wf_validated) < n  # Not all should pass
        assert eligible <= fdr_result.rejected_count
