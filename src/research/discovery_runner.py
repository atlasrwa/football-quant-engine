"""Discovery runner — orchestrates the full research loop.

Connects all research components into a single executable pipeline:
Data → Features → Candidates → Hypotheses → Experiments → Memory → Agent

This is the entry point for running automated research.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.research.agent import DeterministicResearchAgent, ResearchAgent
from src.research.candidate_generator import CandidateGenerator, SearchBudget
from src.research.data_source import ResearchDataSource
from src.research.ev_calculator import EVCalculator
from src.research.experiment import ExperimentResult, ResearchExperiment
from src.research.feature_registry import (
    FeatureDefinition,
    FeatureRegistry,
    FeatureTransformEngine,
    TemporalClass,
    TransformType,
)
from src.research.market import ALL_MARKETS, ResearchMarket
from src.research.memory import ResearchMemory
from src.research.models.factory import create_model_for_market
from src.research.probability import (
    HistoricalFrequencyModel,
    LogisticRegressionModel,
    ProbabilityModel,
)


@dataclass
class DiscoveryConfig:
    """Configuration for a discovery run."""
    train_window: int = 200
    test_window: int = 50
    step_size: int = 50
    max_candidates: int = 200
    min_ev_threshold: float = 0.0
    min_odds: float = 1.30
    max_odds: float = 5.00
    rolling_windows: tuple[int, ...] = (3, 5, 10)
    seed: int = 42


@dataclass
class DiscoveryReport:
    """Summary of a discovery run."""
    total_candidates: int = 0
    total_tested: int = 0
    total_promising: int = 0
    total_validated: int = 0
    total_rejected: int = 0
    best_roi: float = 0.0
    best_hypothesis_id: Optional[str] = None
    follow_up_proposals: int = 0
    results: list[ExperimentResult] = field(default_factory=list)


class DiscoveryRunner:
    """Orchestrates the complete research discovery loop.

    Usage:
        source = SyntheticResearchDataSource()
        runner = DiscoveryRunner(source)
        report = runner.run()
    """

    def __init__(
        self,
        data_source: ResearchDataSource,
        config: Optional[DiscoveryConfig] = None,
        agent: Optional[ResearchAgent] = None,
        memory: Optional[ResearchMemory] = None,
    ) -> None:
        self._source = data_source
        self._config = config or DiscoveryConfig()
        self._agent = agent or DeterministicResearchAgent()
        self._memory = memory or ResearchMemory()
        self._registry = FeatureRegistry()
        self._transform_engine = FeatureTransformEngine()

    @property
    def memory(self) -> ResearchMemory:
        return self._memory

    @property
    def registry(self) -> FeatureRegistry:
        return self._registry

    def run(
        self,
        markets: Optional[list[ResearchMarket]] = None,
        max_iterations: int = 2,
    ) -> DiscoveryReport:
        """Execute the full discovery loop.

        Steps:
        1. Load data from source
        2. Register base features
        3. Compute feature values
        4. For each market:
           a. Generate candidates
           b. Run experiments (walk-forward)
           c. Store results in memory
        5. Send results to agent for follow-ups
        6. Run follow-up experiments
        7. Compile report

        Args:
            markets: Markets to research (default: all).
            max_iterations: Max agent feedback iterations.

        Returns:
            DiscoveryReport with full results.
        """
        markets = markets or ALL_MARKETS
        report = DiscoveryReport()

        # 1. Load data
        matches = self._source.get_matches()
        if not matches:
            return report

        match_dicts = [m.to_dict() for m in matches]

        # 2. Register base features
        self._register_base_features()

        # 3. Compute feature values
        all_features = self._registry.all_features()
        feature_values = self._transform_engine.compute_features(match_dicts, all_features)

        # 4. For each market: generate and test candidates
        all_results: list[ExperimentResult] = []

        for market in markets:
            # Generate candidates
            generator = CandidateGenerator(
                self._registry,
                SearchBudget(max_candidates=self._config.max_candidates // len(markets)),
                seed=self._config.seed,
            )
            hypotheses = generator.generate_all(market, feature_values)
            report.total_candidates += len(hypotheses)

            # Run experiments
            experiment = ResearchExperiment(
                train_window=self._config.train_window,
                test_window=self._config.test_window,
                step_size=self._config.step_size,
                min_ev_threshold=self._config.min_ev_threshold,
                min_odds=self._config.min_odds,
                max_odds=self._config.max_odds,
            )
            model = create_model_for_market(market.market_type.value)

            for hyp in hypotheses:
                # Check duplicate
                _, is_new = self._memory.store_hypothesis(hyp)
                if not is_new:
                    continue

                result = experiment.run(hyp, match_dicts, feature_values, market, model)
                self._memory.store_result(hyp.hypothesis_id, result)
                all_results.append(result)
                report.total_tested += 1

        # 5. Agent feedback loop
        for iteration in range(max_iterations):
            proposals = self._agent.analyze_results(self._memory, all_results)
            report.follow_up_proposals += len(proposals)

            if not proposals:
                break

            for proposal in proposals[:20]:  # Limit per iteration
                hyp = proposal.hypothesis
                _, is_new = self._memory.store_hypothesis(hyp)
                if not is_new:
                    continue

                # Find matching market
                target_market = None
                for m in markets:
                    if m.market_type == hyp.market:
                        target_market = m
                        break
                if target_market is None:
                    continue

                experiment = ResearchExperiment(
                    train_window=self._config.train_window,
                    test_window=self._config.test_window,
                    step_size=self._config.step_size,
                )
                model = create_model_for_market(target_market.market_type.value)
                result = experiment.run(hyp, match_dicts, feature_values, target_market, model)
                self._memory.store_result(hyp.hypothesis_id, result)
                all_results.append(result)
                report.total_tested += 1

                if proposal.follow_up_from:
                    self._memory.link_experiments(proposal.follow_up_from, hyp.hypothesis_id)

        # 6. Compile report
        report.results = all_results
        summary = self._memory.get_summary()
        report.total_promising = summary.get("PROMISING", 0)
        report.total_validated = summary.get("VALIDATED", 0)
        report.total_rejected = summary.get("REJECTED", 0)

        if all_results:
            best = max(all_results, key=lambda r: r.roi_pct)
            report.best_roi = best.roi_pct
            report.best_hypothesis_id = best.hypothesis_id

        return report

    def _register_base_features(self) -> None:
        """Register base features from available data fields."""
        available = self._source.get_available_fields()

        # Raw post-match stats (used for rolling features)
        stat_fields = [
            ("corners_home", ("CORNERS_TOTAL",)),
            ("corners_away", ("CORNERS_TOTAL",)),
            ("total_corners", ("CORNERS_TOTAL",)),
            ("dangerous_attacks_home", ("CORNERS_TOTAL", "GOALS_TOTAL")),
            ("dangerous_attacks_away", ("CORNERS_TOTAL", "GOALS_TOTAL")),
            ("attacks_home", ("CORNERS_TOTAL", "GOALS_TOTAL")),
            ("attacks_away", ("CORNERS_TOTAL", "GOALS_TOTAL")),
            ("possession_home", ("CORNERS_TOTAL", "GOALS_TOTAL")),
            ("possession_away", ("CORNERS_TOTAL", "GOALS_TOTAL")),
            ("shots_home", ("GOALS_TOTAL",)),
            ("shots_away", ("GOALS_TOTAL",)),
            ("shots_on_target_home", ("GOALS_TOTAL",)),
            ("shots_on_target_away", ("GOALS_TOTAL",)),
            ("fouls_home", ("CARDS_TOTAL",)),
            ("fouls_away", ("CARDS_TOTAL",)),
            ("total_cards", ("CARDS_TOTAL",)),
            ("total_goals", ("GOALS_TOTAL",)),
            ("home_xg", ("GOALS_TOTAL",)),
            ("away_xg", ("GOALS_TOTAL",)),
        ]

        for field_name, market_apps in stat_fields:
            if field_name not in available:
                continue

            # Rolling mean features at multiple windows
            for window in self._config.rolling_windows:
                for team_field in ("home_team", "away_team"):
                    side = "home" if team_field == "home_team" else "away"
                    feat = FeatureDefinition(
                        name=f"{field_name}_avg_{window}_{side}",
                        source_fields=(field_name,),
                        transform=TransformType.ROLLING_MEAN,
                        params={"window": window, "team_field": team_field, "min_periods": 3},
                        temporal_class=TemporalClass.DERIVED,
                        market_applicability=market_apps,
                        description=f"Rolling {window}-match mean of {field_name} for {side} team",
                    )
                    self._registry.register(feat)

        # Difference features
        diff_pairs = [
            ("corners_home", "corners_away", ("CORNERS_TOTAL",)),
            ("dangerous_attacks_home", "dangerous_attacks_away", ("CORNERS_TOTAL", "GOALS_TOTAL")),
            ("possession_home", "possession_away", ("CORNERS_TOTAL", "GOALS_TOTAL")),
            ("shots_home", "shots_away", ("GOALS_TOTAL",)),
            ("fouls_home", "fouls_away", ("CARDS_TOTAL",)),
        ]

        for field_a, field_b, market_apps in diff_pairs:
            if field_a in available and field_b in available:
                feat = FeatureDefinition(
                    name=f"{field_a}_minus_{field_b}",
                    source_fields=(field_a, field_b),
                    transform=TransformType.DIFFERENCE,
                    temporal_class=TemporalClass.POST_MATCH,
                    market_applicability=market_apps,
                    description=f"Difference: {field_a} - {field_b}",
                )
                self._registry.register(feat)

        # Ratio features
        ratio_pairs = [
            ("dangerous_attacks_home", "attacks_home", ("CORNERS_TOTAL", "GOALS_TOTAL")),
            ("dangerous_attacks_away", "attacks_away", ("CORNERS_TOTAL", "GOALS_TOTAL")),
            ("shots_on_target_home", "shots_home", ("GOALS_TOTAL",)),
            ("shots_on_target_away", "shots_away", ("GOALS_TOTAL",)),
        ]

        for field_a, field_b, market_apps in ratio_pairs:
            if field_a in available and field_b in available:
                feat = FeatureDefinition(
                    name=f"{field_a}_div_{field_b}",
                    source_fields=(field_a, field_b),
                    transform=TransformType.RATIO,
                    temporal_class=TemporalClass.POST_MATCH,
                    market_applicability=market_apps,
                    description=f"Ratio: {field_a} / {field_b}",
                )
                self._registry.register(feat)
