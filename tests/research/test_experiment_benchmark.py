"""Performance benchmark for Batch 4 — Experiment Engine.

Controlled benchmark:
- 1,000 matches (via larger synthetic source)
- 50 candidate hypotheses
- 3 models
- 3 markets

Measures:
- Total experiments
- Execution time
- Average experiment time
- Failed experiments
- Eligible observations

This is NOT premature optimization. It establishes a baseline.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from src.research.candidates import CandidateCondition, CandidateOperator, ResearchCandidate
from src.research.data_source import MarketOdds, ResearchDataSource, ResearchMatch
from src.research.experiment_engine.config import ExperimentConfig, OddsMode
from src.research.experiment_engine.dataset import ResearchDataset
from src.research.experiment_engine.hypothesis import ExperimentHypothesis
from src.research.experiment_engine.result import ExperimentResultStatus
from src.research.experiment_engine.runner import ExperimentRunner
from src.research.market import MarketType, create_default_registry
from src.research.probability import HistoricalFrequencyModel, LogisticRegressionModel, PoissonModel

import numpy as np


# ═══════════════════════════════════════════════════════════════
# LARGE SYNTHETIC DATA SOURCE (1000+ matches)
# ═══════════════════════════════════════════════════════════════


class BenchmarkDataSource(ResearchDataSource):
    """Large synthetic source for benchmarking (1000 matches)."""

    def __init__(self, num_matches: int = 1000, seed: int = 42):
        self._rng = np.random.default_rng(seed)
        self._matches: list[ResearchMatch] = []
        self._odds: list[MarketOdds] = []
        self._generate(num_matches)

    def _generate(self, n: int) -> None:
        rng = self._rng
        base_date = 1577836800  # 2020-01-01

        teams = [f"Team_{i}" for i in range(20)]

        for i in range(n):
            date_unix = base_date + i * 86400 * 3  # every 3 days
            home = teams[i % 20]
            away = teams[(i + 7) % 20]

            home_goals = int(rng.poisson(1.4))
            away_goals = int(rng.poisson(1.1))
            total_corners = int(max(0, rng.normal(10, 3)))
            total_cards = int(max(0, rng.poisson(3.5)))
            home_poss = float(np.clip(50 + rng.normal(0, 8), 30, 70))
            da_home = int(max(10, rng.normal(25, 8)))
            da_away = int(max(10, rng.normal(23, 8)))
            shots_home = int(max(2, rng.poisson(12)))
            shots_away = int(max(2, rng.poisson(10)))

            self._matches.append(ResearchMatch(
                match_id=i + 10000,
                date_unix=date_unix,
                league_id=1001,
                season=f"{2020 + i // 380}",
                home_team=home,
                away_team=away,
                home_goals=home_goals,
                away_goals=away_goals,
                total_goals=home_goals + away_goals,
                corners_home=int(max(0, total_corners * home_poss / 100)),
                corners_away=int(max(0, total_corners * (100 - home_poss) / 100)),
                total_corners=total_corners,
                total_cards=total_cards,
                yellow_cards_home=int(max(0, total_cards // 2)),
                yellow_cards_away=total_cards - int(max(0, total_cards // 2)),
                dangerous_attacks_home=da_home,
                dangerous_attacks_away=da_away,
                possession_home=home_poss,
                possession_away=100.0 - home_poss,
                shots_home=shots_home,
                shots_away=shots_away,
                shots_on_target_home=int(max(1, shots_home * 0.35)),
                shots_on_target_away=int(max(1, shots_away * 0.35)),
            ))

            # Generate odds for 3 markets
            for market_name, line in [("GOALS_TOTAL", 2.5), ("CORNERS_TOTAL", 9.5), ("CARDS_TOTAL", 3.5)]:
                p_over = float(np.clip(0.5 + rng.normal(0, 0.08), 0.3, 0.7))
                margin = 1.05
                self._odds.append(MarketOdds(
                    match_id=i + 10000,
                    market=market_name,
                    line=line,
                    over_odds=float(margin / p_over),
                    under_odds=float(margin / (1 - p_over)),
                    timestamp=date_unix - 3600,
                ))

    def get_matches(self, **kwargs) -> list[ResearchMatch]:
        result = self._matches
        league_id = kwargs.get("league_id")
        season = kwargs.get("season")
        min_date = kwargs.get("min_date")
        max_date = kwargs.get("max_date")
        if league_id is not None:
            result = [m for m in result if m.league_id == league_id]
        if season is not None:
            result = [m for m in result if m.season == season]
        if min_date is not None:
            result = [m for m in result if m.date_unix >= min_date]
        if max_date is not None:
            result = [m for m in result if m.date_unix < max_date]
        return sorted(result, key=lambda m: m.date_unix)

    def get_available_fields(self) -> list[str]:
        if self._matches:
            return self._matches[0].available_fields
        return []

    def get_market_odds(self, **kwargs) -> list[MarketOdds]:
        result = self._odds
        match_ids = kwargs.get("match_ids")
        market = kwargs.get("market")
        if match_ids is not None:
            ids = set(match_ids)
            result = [o for o in result if o.match_id in ids]
        if market is not None:
            result = [o for o in result if o.market == market]
        return result


# ═══════════════════════════════════════════════════════════════
# BENCHMARK
# ═══════════════════════════════════════════════════════════════


def _generate_hypotheses(n: int = 50) -> list[ExperimentHypothesis]:
    """Generate n diverse hypotheses for benchmarking."""
    features = [
        "dangerous_attacks_home", "dangerous_attacks_away",
        "possession_home", "shots_home", "shots_away",
        "shots_on_target_home", "shots_on_target_away",
    ]
    operators = [">", "<"]
    directions = ["OVER", "UNDER"]

    hypotheses = []
    rng = np.random.default_rng(99)

    for i in range(n):
        feat = features[i % len(features)]
        op = operators[i % 2]
        direction = directions[i % 2]
        # Varying thresholds
        threshold = float(15 + (i % 20))

        candidate = ResearchCandidate(
            candidate_id=f"bench_candidate_{i}",
            market_type="CORNERS_TOTAL",
            feature_ids=(feat,),
            conditions=(CandidateCondition(feat, op, threshold),),
            operator_type=CandidateOperator.THRESHOLD_GT if op == ">" else CandidateOperator.THRESHOLD_LT,
            direction=direction,
        )
        hypotheses.append(ExperimentHypothesis.from_candidate(candidate))

    return hypotheses


class TestPerformanceBenchmark:
    """Performance benchmark establishing baseline metrics."""

    @pytest.fixture
    def benchmark_source(self):
        return BenchmarkDataSource(num_matches=1000, seed=42)

    def test_benchmark_experiment_engine(self, benchmark_source):
        """Run controlled benchmark: 1000 matches × 50 hypotheses × 3 models × 3 markets.

        Records total experiments, execution time, failures, and observations.
        """
        registry = create_default_registry()
        markets = [
            registry.get(MarketType.CORNERS_TOTAL),
            registry.get(MarketType.GOALS_TOTAL),
            registry.get(MarketType.CARDS_TOTAL),
        ]
        model_factories = [
            ("HistoricalFrequencyModel", lambda: HistoricalFrequencyModel(min_observations=5)),
            ("LogisticRegressionModel", lambda: LogisticRegressionModel(seed=42, max_iter=50)),
            ("PoissonModel", lambda: PoissonModel(line=9.5)),
        ]

        hypotheses = _generate_hypotheses(50)
        matches = benchmark_source.get_matches()
        midpoint = matches[600].date_unix  # 60/40 split

        runner = ExperimentRunner()
        total_experiments = 0
        completed = 0
        failed = 0
        total_predictions = 0
        total_eligible = 0

        start_time = time.time()

        for market in markets:
            dataset = ResearchDataset(source=benchmark_source, market=market)

            for model_name, model_factory in model_factories:
                for hypothesis in hypotheses:
                    config = ExperimentConfig(
                        hypothesis=hypothesis,
                        market_type=market.market_type.value,
                        dataset_version=dataset.content_hash,
                        model_type=model_name,
                        training_start=matches[0].date_unix,
                        training_end=midpoint,
                        evaluation_start=midpoint,
                        evaluation_end=matches[-1].date_unix + 1,
                        odds_mode=OddsMode.SYNTHETIC_ODDS,
                        minimum_observations=10,
                        random_seed=42,
                    )

                    model = model_factory()
                    result = runner.run(config, dataset, model)
                    total_experiments += 1

                    if result.status == ExperimentResultStatus.COMPLETED:
                        completed += 1
                        total_predictions += result.prediction_count
                        total_eligible += result.observation_counts.eligible_rows
                    else:
                        failed += 1

        elapsed = time.time() - start_time

        # Report
        print(f"\n{'=' * 60}")
        print("BATCH 4 PERFORMANCE BENCHMARK")
        print(f"{'=' * 60}")
        print(f"Dataset:              1,000 matches")
        print(f"Hypotheses:           50")
        print(f"Models:               3")
        print(f"Markets:              3")
        print(f"Total experiments:    {total_experiments}")
        print(f"Completed:            {completed}")
        print(f"Failed:               {failed}")
        print(f"Total predictions:    {total_predictions:,}")
        print(f"Total eligible obs:   {total_eligible:,}")
        print(f"Execution time:       {elapsed:.2f}s")
        print(f"Avg experiment time:  {elapsed / total_experiments * 1000:.2f}ms")
        print(f"Experiments/sec:      {total_experiments / elapsed:.1f}")
        print(f"{'=' * 60}")

        # Assertions: must complete in reasonable time
        assert total_experiments == 450  # 50 × 3 × 3
        assert completed > 0
        assert elapsed < 120.0, f"Benchmark took {elapsed:.1f}s, expected < 120s"
        # At least some experiments should produce predictions
        assert total_predictions > 0
        # Avg time per experiment should be reasonable
        avg_ms = elapsed / total_experiments * 1000
        assert avg_ms < 500, f"Average {avg_ms:.1f}ms per experiment, expected < 500ms"
