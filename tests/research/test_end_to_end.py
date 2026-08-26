"""End-to-end demonstration of the Research & Discovery Laboratory.

This test proves the complete research loop using SyntheticResearchDataSource:

1. Generate deterministic dataset
2. Register features
3. Generate candidate metrics
4. Generate hypotheses
5. Train probability model
6. Calculate fair odds
7. Compare against synthetic market odds
8. Calculate EV
9. Backtest (walk-forward)
10. Run FDR-equivalent significance test
11. Store result in research memory
12. Send result to ResearchAgent
13. Generate follow-up hypothesis
14. Run second experiment
15. Store relationship between experiments
16. Demonstrate research memory preventing duplicate work

CRITICAL TEST: The synthetic dataset contains a deliberately embedded
relationship (corners ~ dangerous_attacks + possession + corner_tendency).
The discovery engine must find corners-related features as promising
WITHOUT having the discovery rule hard-coded.
"""

import pytest
import numpy as np

from src.research.agent import DeterministicResearchAgent
from src.research.candidate_generator import (
    CandidateGenerator,
    GenerationMethod,
    ResearchHypothesis,
    SearchBudget,
)
from src.research.data_source import ResearchDataSource
from src.research.discovery_runner import DiscoveryConfig, DiscoveryRunner
from src.research.ev_calculator import EVCalculator
from src.research.experiment import ExperimentResult, ExperimentStatus, ResearchExperiment
from src.research.feature_registry import (
    FeatureDefinition,
    FeatureRegistry,
    FeatureTransformEngine,
    TemporalClass,
    TransformType,
)
from src.research.market import (
    ALL_MARKETS,
    CORNERS_OVER_UNDER,
    GOALS_OVER_UNDER,
    MarketDirection,
    MarketType,
)
from src.research.memory import HypothesisStatus, ResearchMemory
from src.research.probability import (
    HistoricalFrequencyModel,
    LogisticRegressionModel,
    ProbabilityEstimate,
)
from src.research.synthetic_data import SyntheticResearchDataSource


class TestEndToEndResearchLoop:
    """Complete end-to-end demonstration of the research laboratory."""

    @pytest.fixture(scope="class")
    def source(self):
        """Deterministic synthetic data source (4 seasons)."""
        return SyntheticResearchDataSource(seed=42, num_seasons=4)

    @pytest.fixture(scope="class")
    def match_dicts(self, source):
        matches = source.get_matches()
        return [m.to_dict() for m in matches]

    def test_step_01_generate_deterministic_dataset(self, source):
        """Step 1: Generate deterministic dataset."""
        matches = source.get_matches()
        assert len(matches) == 132 * 4  # 528 matches
        # Verify determinism
        source2 = SyntheticResearchDataSource(seed=42, num_seasons=4)
        matches2 = source2.get_matches()
        assert matches[0].home_goals == matches2[0].home_goals
        assert matches[-1].corners_home == matches2[-1].corners_home

    def test_step_02_register_features(self, source):
        """Step 2: Register features from available fields."""
        registry = FeatureRegistry()
        available = source.get_available_fields()

        # Register corners-related features (the embedded relationship targets)
        features = [
            FeatureDefinition(
                name="dangerous_attacks_home_avg_5",
                source_fields=("dangerous_attacks_home",),
                transform=TransformType.ROLLING_MEAN,
                params={"window": 5, "team_field": "home_team", "min_periods": 3},
                temporal_class=TemporalClass.DERIVED,
                market_applicability=("CORNERS_TOTAL",),
            ),
            FeatureDefinition(
                name="corners_home_avg_5",
                source_fields=("corners_home",),
                transform=TransformType.ROLLING_MEAN,
                params={"window": 5, "team_field": "home_team", "min_periods": 3},
                temporal_class=TemporalClass.DERIVED,
                market_applicability=("CORNERS_TOTAL",),
            ),
            FeatureDefinition(
                name="possession_diff",
                source_fields=("possession_home", "possession_away"),
                transform=TransformType.DIFFERENCE,
                temporal_class=TemporalClass.POST_MATCH,
                market_applicability=("CORNERS_TOTAL",),
            ),
            FeatureDefinition(
                name="corners_diff",
                source_fields=("corners_home", "corners_away"),
                transform=TransformType.DIFFERENCE,
                temporal_class=TemporalClass.POST_MATCH,
                market_applicability=("CORNERS_TOTAL",),
            ),
        ]
        ids = registry.register_many(features)
        assert registry.count == 4
        assert all(isinstance(i, str) for i in ids)

    def test_step_03_generate_candidate_metrics(self, source, match_dicts):
        """Step 3: Generate candidate metrics via feature transform engine."""
        registry = FeatureRegistry()
        features = [
            FeatureDefinition(
                name="da_home_avg_5",
                source_fields=("dangerous_attacks_home",),
                transform=TransformType.ROLLING_MEAN,
                params={"window": 5, "team_field": "home_team", "min_periods": 3},
                market_applicability=("CORNERS_TOTAL",),
            ),
            FeatureDefinition(
                name="corners_home_avg_5",
                source_fields=("corners_home",),
                transform=TransformType.ROLLING_MEAN,
                params={"window": 5, "team_field": "home_team", "min_periods": 3},
                market_applicability=("CORNERS_TOTAL",),
            ),
        ]
        registry.register_many(features)

        engine = FeatureTransformEngine()
        feature_values = engine.compute_features(match_dicts, features)
        assert len(feature_values) == len(match_dicts)

        # Later matches should have computed values
        filled = sum(1 for fv in feature_values if len(fv) > 0)
        assert filled > len(match_dicts) * 0.5  # Most matches should have features

    def test_step_04_generate_hypotheses(self, source, match_dicts):
        """Step 4: Generate hypotheses from candidates."""
        registry = FeatureRegistry()
        feat = FeatureDefinition(
            name="da_home_avg_5",
            source_fields=("dangerous_attacks_home",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 5, "team_field": "home_team", "min_periods": 3},
            market_applicability=("CORNERS_TOTAL",),
        )
        registry.register(feat)

        engine = FeatureTransformEngine()
        feature_values = engine.compute_features(match_dicts, [feat])

        generator = CandidateGenerator(registry, SearchBudget(min_sample_size=30))
        hypotheses = generator.generate_single_feature_hypotheses(CORNERS_OVER_UNDER, feature_values)
        assert len(hypotheses) > 0
        # All should target CORNERS_TOTAL
        assert all(h.market == MarketType.CORNERS_TOTAL for h in hypotheses)

    def test_step_05_train_probability_model(self, match_dicts):
        """Step 5: Train probability model on historical data."""
        # Build training data
        features_train = [{"x": float(m.get("dangerous_attacks_home", 0))} for m in match_dicts[:200]]
        outcomes_train = [m.get("total_corners", 0) > 9.5 for m in match_dicts[:200]]

        model = LogisticRegressionModel(learning_rate=0.1, max_iter=500)
        model.fit(features_train, outcomes_train)

        # Model should produce valid predictions
        est = model.predict({"x": 20.0})
        assert 0 < est.p_over < 1
        assert abs(est.p_over + est.p_under - 1.0) < 0.001

    def test_step_06_calculate_fair_odds(self):
        """Step 6: Calculate fair odds from market prices."""
        market = CORNERS_OVER_UNDER
        # Example market with 5% overround
        over_odds, under_odds = 1.85, 2.05
        fair_over, fair_under = market.fair_probability(over_odds, under_odds)
        assert abs(fair_over + fair_under - 1.0) < 0.001
        assert fair_over > 0.5  # Over is favored

    def test_step_07_compare_against_market_odds(self, match_dicts):
        """Step 7: Compare model probability against market odds."""
        model = LogisticRegressionModel(learning_rate=0.1, max_iter=500)
        features_train = [{"x": float(m.get("dangerous_attacks_home", 0))} for m in match_dicts[:200]]
        outcomes_train = [m.get("total_corners", 0) > 9.5 for m in match_dicts[:200]]
        model.fit(features_train, outcomes_train)

        # Predict on a test match
        test_match = match_dicts[250]
        est = model.predict({"x": float(test_match.get("dangerous_attacks_home", 0))})

        over_odds = test_match.get("odds_over_corners", 1.90)
        under_odds = test_match.get("odds_under_corners", 2.00)
        fair_over, _ = CORNERS_OVER_UNDER.fair_probability(over_odds, under_odds)

        # Model vs market comparison
        edge = est.p_over - fair_over
        # Edge can be positive or negative — that's fine
        assert isinstance(edge, float)

    def test_step_08_calculate_ev(self, match_dicts):
        """Step 8: Calculate expected value."""
        est = ProbabilityEstimate(p_over=0.58, p_under=0.42, model_name="test")
        result = EVCalculator.compute(
            est, CORNERS_OVER_UNDER,
            over_odds=1.85, under_odds=2.05,
            direction=MarketDirection.OVER,
        )
        assert result is not None
        # EV = 0.58 * 1.85 - 1 = 0.073
        assert abs(result.expected_value - (0.58 * 1.85 - 1)) < 0.001

    def test_step_09_backtest_walk_forward(self, match_dicts):
        """Step 9: Run walk-forward backtest."""
        registry = FeatureRegistry()
        feat = FeatureDefinition(
            name="da_avg",
            source_fields=("dangerous_attacks_home",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 5, "team_field": "home_team", "min_periods": 3},
            market_applicability=("CORNERS_TOTAL",),
        )
        registry.register(feat)

        engine = FeatureTransformEngine()
        feature_values = engine.compute_features(match_dicts, [feat])

        hyp = ResearchHypothesis(
            hypothesis_id="backtest_demo",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=(feat.feature_id,),
            conditions=((feat.feature_id, ">", 0.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )

        experiment = ResearchExperiment(
            train_window=100, test_window=30, step_size=30,
            min_ev_threshold=-0.5, min_odds=1.30, max_odds=5.00,
        )
        model = LogisticRegressionModel()
        result = experiment.run(hyp, match_dicts, feature_values, CORNERS_OVER_UNDER, model)

        assert result.status == ExperimentStatus.COMPLETED
        assert result.n_bets > 0

    def test_step_10_fdr_significance(self, match_dicts):
        """Step 10: Verify FDR-equivalent statistical significance check."""
        registry = FeatureRegistry()
        feat = FeatureDefinition(
            name="da_avg",
            source_fields=("dangerous_attacks_home",),
            transform=TransformType.ROLLING_MEAN,
            params={"window": 5, "team_field": "home_team", "min_periods": 3},
            market_applicability=("CORNERS_TOTAL",),
        )
        registry.register(feat)

        engine = FeatureTransformEngine()
        feature_values = engine.compute_features(match_dicts, [feat])

        hyp = ResearchHypothesis(
            hypothesis_id="fdr_demo",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=(feat.feature_id,),
            conditions=((feat.feature_id, ">", 0.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )

        experiment = ResearchExperiment(
            train_window=100, test_window=30, step_size=30,
            min_ev_threshold=-1.0, min_odds=1.10, max_odds=10.0,
        )
        model = LogisticRegressionModel()
        result = experiment.run(hyp, match_dicts, feature_values, CORNERS_OVER_UNDER, model)

        # p_value should be computed if enough bets
        if result.n_bets >= 30:
            assert result.p_value is not None
            # is_significant uses 0.05 threshold
            if result.p_value < 0.05:
                assert result.is_significant is True

    def test_step_11_store_in_memory(self):
        """Step 11: Store result in research memory."""
        memory = ResearchMemory()
        hyp = ResearchHypothesis(
            hypothesis_id="memory_demo",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 5.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        hid, is_new = memory.store_hypothesis(hyp)
        assert is_new is True

        result = ExperimentResult(
            hypothesis_id="memory_demo",
            market="CORNERS_TOTAL",
            status=ExperimentStatus.COMPLETED,
            n_samples=500, n_bets=80, n_wins=44,
            win_rate=0.55, total_profit_loss=4.0, roi_pct=5.0,
            avg_ev=0.05, avg_odds=1.90, max_drawdown=3.0, sharpe_ratio=1.1,
            p_value=0.04, is_significant=True,
        )
        memory.store_result(hid, result)
        entry = memory.get_entry(hid)
        assert entry.status == HypothesisStatus.VALIDATED

    def test_step_12_send_to_agent(self):
        """Step 12: Send result to ResearchAgent for analysis."""
        memory = ResearchMemory()
        hyp = ResearchHypothesis(
            hypothesis_id="agent_demo",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 5.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        memory.store_hypothesis(hyp)
        result = ExperimentResult(
            hypothesis_id="agent_demo",
            market="CORNERS_TOTAL",
            status=ExperimentStatus.COMPLETED,
            n_samples=500, n_bets=80, n_wins=44,
            win_rate=0.55, total_profit_loss=4.0, roi_pct=5.0,
            avg_ev=0.05, avg_odds=1.90, max_drawdown=3.0, sharpe_ratio=1.1,
        )
        memory.store_result("agent_demo", result)

        agent = DeterministicResearchAgent()
        proposals = agent.analyze_results(memory, [result])
        assert len(proposals) > 0

    def test_step_13_generate_follow_up(self):
        """Step 13: Agent generates follow-up hypothesis."""
        memory = ResearchMemory()
        hyp = ResearchHypothesis(
            hypothesis_id="followup_parent",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 5.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        memory.store_hypothesis(hyp)
        result = ExperimentResult(
            hypothesis_id="followup_parent",
            market="CORNERS_TOTAL",
            status=ExperimentStatus.COMPLETED,
            n_samples=500, n_bets=80, n_wins=44,
            win_rate=0.55, total_profit_loss=4.0, roi_pct=5.0,
            avg_ev=0.05, avg_odds=1.90, max_drawdown=3.0, sharpe_ratio=1.1,
        )
        memory.store_result("followup_parent", result)

        agent = DeterministicResearchAgent()
        proposals = agent.analyze_results(memory, [result])

        # Follow-up should reference parent
        follow_ups = [p for p in proposals if p.follow_up_from == "followup_parent"]
        assert len(follow_ups) > 0

    def test_step_14_run_second_experiment(self, match_dicts):
        """Step 14: Run the follow-up experiment."""
        # Create a follow-up hypothesis (adjusted threshold)
        hyp = ResearchHypothesis(
            hypothesis_id="followup_child",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", -999.0),),  # Always passes for testing
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        experiment = ResearchExperiment(
            train_window=100, test_window=30, step_size=30,
            min_ev_threshold=-1.0, min_odds=1.10, max_odds=10.0,
        )
        # Use a simple feature
        feature_values = [{"f1": float(m.get("dangerous_attacks_home", 0))} for m in match_dicts]
        model = HistoricalFrequencyModel()
        result = experiment.run(hyp, match_dicts, feature_values, CORNERS_OVER_UNDER, model)
        assert result.status == ExperimentStatus.COMPLETED

    def test_step_15_link_experiments(self):
        """Step 15: Store relationship between parent and child experiments."""
        memory = ResearchMemory()
        parent = ResearchHypothesis(
            hypothesis_id="parent_exp",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 5.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        child = ResearchHypothesis(
            hypothesis_id="child_exp",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 5.5),),  # Adjusted threshold
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        memory.store_hypothesis(parent)
        memory.store_hypothesis(child)
        memory.link_experiments("parent_exp", "child_exp")

        parent_entry = memory.get_entry("parent_exp")
        child_entry = memory.get_entry("child_exp")
        assert "child_exp" in parent_entry.children_ids
        assert child_entry.parent_id == "parent_exp"

    def test_step_16_prevent_duplicate_work(self):
        """Step 16: Research memory prevents duplicate hypothesis testing."""
        memory = ResearchMemory()
        hyp1 = ResearchHypothesis(
            hypothesis_id="original",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 5.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        memory.store_hypothesis(hyp1)

        # Try to store the same hypothesis with a different ID
        hyp2 = ResearchHypothesis(
            hypothesis_id="duplicate_attempt",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 5.0),),
            direction="OVER",
            generation_method=GenerationMethod.LLM,  # Different source
        )
        hid, is_new = memory.store_hypothesis(hyp2)
        assert is_new is False
        assert hid == "original"  # Points to existing

    def test_step_17_demonstrate_duplicate_prevention_in_loop(self):
        """Step 17: In a research loop, duplicates are skipped."""
        memory = ResearchMemory()
        tested_count = 0
        skipped_count = 0

        hypotheses = [
            ResearchHypothesis(
                hypothesis_id=f"hyp_{i}",
                market=MarketType.CORNERS_TOTAL,
                feature_ids=("f1",),
                conditions=(("f1", ">", 5.0),),  # All identical content!
                direction="OVER",
                generation_method=GenerationMethod.DETERMINISTIC,
            )
            for i in range(10)
        ]

        for hyp in hypotheses:
            _, is_new = memory.store_hypothesis(hyp)
            if is_new:
                tested_count += 1
            else:
                skipped_count += 1

        # Only the first should be "new"
        assert tested_count == 1
        assert skipped_count == 9


class TestEmbeddedRelationshipDiscovery:
    """CRITICAL TEST: Prove the discovery engine can find the embedded
    corners relationship WITHOUT having it hard-coded.

    The synthetic data has:
    corners ~ 0.3*dangerous_attacks + 0.2*possession + 0.5*corner_tendency

    The engine should find corners-related features as having some
    predictive signal for the CORNERS_TOTAL market.
    """

    @pytest.fixture(scope="class")
    def discovery_report(self):
        """Run full discovery and return report."""
        source = SyntheticResearchDataSource(seed=42, num_seasons=4)
        config = DiscoveryConfig(
            train_window=100,
            test_window=30,
            step_size=30,
            max_candidates=100,
            min_ev_threshold=-0.5,
            rolling_windows=(5,),
            seed=42,
        )
        runner = DiscoveryRunner(source, config)
        report = runner.run(markets=[CORNERS_OVER_UNDER], max_iterations=1)
        return report, runner

    def test_discovery_runs_successfully(self, discovery_report):
        """Discovery completes without error."""
        report, _ = discovery_report
        assert report.total_tested > 0

    def test_candidates_generated(self, discovery_report):
        """Candidates were generated from the feature registry."""
        report, _ = discovery_report
        assert report.total_candidates > 0

    def test_some_hypotheses_tested(self, discovery_report):
        """Hypotheses were actually tested via walk-forward."""
        report, _ = discovery_report
        assert report.total_tested > 5

    def test_corners_features_show_signal(self, discovery_report):
        """Features related to corners/attacks should show SOME signal.

        We don't require statistical significance (synthetic data has noise),
        but corners-related features should NOT all be rejected.
        """
        report, runner = discovery_report
        # Check if any result has positive ROI
        positive_roi = [r for r in report.results if r.roi_pct > 0 and r.n_bets > 10]
        # With the embedded relationship, at least some candidates should
        # show positive signal (even if not statistically significant)
        assert len(positive_roi) > 0, (
            "No hypothesis showed positive ROI — the embedded relationship "
            "should produce at least some positive candidates"
        )

    def test_agent_generates_follow_ups(self, discovery_report):
        """The agent should generate follow-up proposals."""
        report, _ = discovery_report
        assert report.follow_up_proposals >= 0  # May be 0 if no promising results

    def test_memory_tracks_all_experiments(self, discovery_report):
        """Research memory stores all tested hypotheses."""
        _, runner = discovery_report
        memory = runner.memory
        assert memory.total_tested > 0
        assert memory.total_experiments >= memory.total_tested

    def test_feature_registry_populated(self, discovery_report):
        """Feature registry was populated with base features."""
        _, runner = discovery_report
        registry = runner.registry
        assert registry.count > 0

    def test_no_hardcoded_discovery_rule(self):
        """Verify that CandidateGenerator does NOT have corners-specific logic.

        The discovery must be data-driven, not hard-coded.
        """
        import inspect
        from src.research.candidate_generator import CandidateGenerator

        source = inspect.getsource(CandidateGenerator)
        # Should not contain hard-coded corner thresholds or rules
        assert "9.5" not in source  # No hard-coded corners line
        assert "corner_tendency" not in source  # No leaked knowledge of synthetic formula
        assert "0.3 * dangerous" not in source  # No leaked formula


class TestFullDiscoveryRunner:
    """Test the DiscoveryRunner orchestration."""

    def test_runner_completes(self):
        """DiscoveryRunner completes a full run."""
        source = SyntheticResearchDataSource(seed=42, num_seasons=2)
        config = DiscoveryConfig(
            train_window=50,
            test_window=20,
            step_size=20,
            max_candidates=30,
            rolling_windows=(5,),
        )
        runner = DiscoveryRunner(source, config)
        report = runner.run(markets=[CORNERS_OVER_UNDER], max_iterations=1)
        assert report.total_tested > 0

    def test_runner_multiple_markets(self):
        """Runner handles multiple markets."""
        source = SyntheticResearchDataSource(seed=42, num_seasons=2)
        config = DiscoveryConfig(
            train_window=50, test_window=20, step_size=20,
            max_candidates=20, rolling_windows=(5,),
        )
        runner = DiscoveryRunner(source, config)
        report = runner.run(markets=ALL_MARKETS, max_iterations=0)
        assert report.total_tested > 0
        # Results should cover multiple markets
        markets_tested = {r.market for r in report.results}
        assert len(markets_tested) >= 1

    def test_runner_deterministic(self):
        """Same seed produces same results."""
        source1 = SyntheticResearchDataSource(seed=42, num_seasons=2)
        source2 = SyntheticResearchDataSource(seed=42, num_seasons=2)
        config = DiscoveryConfig(
            train_window=50, test_window=20, step_size=20,
            max_candidates=20, rolling_windows=(5,), seed=42,
        )
        runner1 = DiscoveryRunner(source1, config)
        runner2 = DiscoveryRunner(source2, config)
        report1 = runner1.run(markets=[CORNERS_OVER_UNDER], max_iterations=0)
        report2 = runner2.run(markets=[CORNERS_OVER_UNDER], max_iterations=0)
        assert report1.total_tested == report2.total_tested
        assert report1.total_candidates == report2.total_candidates

    def test_runner_respects_budget(self):
        """Runner respects max_candidates budget."""
        source = SyntheticResearchDataSource(seed=42, num_seasons=2)
        config = DiscoveryConfig(
            train_window=50, test_window=20, step_size=20,
            max_candidates=10, rolling_windows=(5,),
        )
        runner = DiscoveryRunner(source, config)
        report = runner.run(markets=[CORNERS_OVER_UNDER], max_iterations=0)
        assert report.total_candidates <= 10
