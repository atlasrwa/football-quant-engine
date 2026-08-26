"""Tests for research agent interface."""

import pytest

from src.research.agent import (
    DeterministicResearchAgent,
    LLMResearchAgent,
    ResearchAgent,
    ResearchProposal,
)
from src.research.candidate_generator import GenerationMethod, ResearchHypothesis
from src.research.experiment import ExperimentResult, ExperimentStatus
from src.research.market import MarketType
from src.research.memory import ResearchMemory


class TestDeterministicResearchAgent:
    """Tests for the rule-based research agent."""

    @pytest.fixture
    def agent(self):
        return DeterministicResearchAgent()

    @pytest.fixture
    def memory_with_results(self):
        memory = ResearchMemory()
        # Store a promising hypothesis
        hyp = ResearchHypothesis(
            hypothesis_id="promising_1",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("feat_a",),
            conditions=(("feat_a", ">", 5.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        memory.store_hypothesis(hyp)
        result = ExperimentResult(
            hypothesis_id="promising_1",
            market="CORNERS_TOTAL",
            status=ExperimentStatus.COMPLETED,
            n_samples=500,
            n_bets=50,
            n_wins=28,
            win_rate=0.56,
            total_profit_loss=3.0,
            roi_pct=6.0,
            avg_ev=0.06,
            avg_odds=1.90,
            max_drawdown=2.0,
            sharpe_ratio=1.0,
            p_value=0.04,
            is_significant=True,
        )
        memory.store_result("promising_1", result)
        return memory, [result]

    def test_implements_interface(self, agent):
        assert isinstance(agent, ResearchAgent)

    def test_analyze_results_generates_proposals(self, agent, memory_with_results):
        memory, results = memory_with_results
        proposals = agent.analyze_results(memory, results)
        assert len(proposals) > 0
        assert all(isinstance(p, ResearchProposal) for p in proposals)

    def test_proposals_have_hypotheses(self, agent, memory_with_results):
        memory, results = memory_with_results
        proposals = agent.analyze_results(memory, results)
        for p in proposals:
            assert p.hypothesis is not None
            assert p.hypothesis.hypothesis_id is not None
            assert p.rationale != ""

    def test_proposals_not_duplicates(self, agent, memory_with_results):
        """Agent should not propose hypotheses already in memory."""
        memory, results = memory_with_results
        proposals = agent.analyze_results(memory, results)
        for p in proposals:
            assert not memory.is_duplicate(p.hypothesis)

    def test_threshold_adjustment_strategy(self, agent, memory_with_results):
        """Agent should suggest adjacent thresholds for promising results."""
        memory, results = memory_with_results
        proposals = agent.analyze_results(memory, results)
        # Should have some threshold adjustments
        adj_proposals = [p for p in proposals if "adjust" in p.rationale.lower() or "Threshold" in p.rationale]
        assert len(adj_proposals) > 0

    def test_opposite_direction_strategy(self, agent, memory_with_results):
        """Agent should test opposite direction."""
        memory, results = memory_with_results
        proposals = agent.analyze_results(memory, results)
        opp_proposals = [p for p in proposals if "opposite" in p.rationale.lower()]
        assert len(opp_proposals) > 0

    def test_no_proposals_for_bad_results(self, agent):
        """Agent should not generate follow-ups from losing experiments."""
        memory = ResearchMemory()
        hyp = ResearchHypothesis(
            hypothesis_id="loser",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("feat_a",),
            conditions=(("feat_a", ">", 5.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        memory.store_hypothesis(hyp)
        bad_result = ExperimentResult(
            hypothesis_id="loser",
            market="CORNERS_TOTAL",
            status=ExperimentStatus.COMPLETED,
            n_samples=500,
            n_bets=50,
            n_wins=20,
            win_rate=0.40,
            total_profit_loss=-10.0,
            roi_pct=-20.0,
            avg_ev=-0.2,
            avg_odds=1.90,
            max_drawdown=15.0,
            sharpe_ratio=-1.0,
        )
        memory.store_result("loser", bad_result)
        proposals = agent.analyze_results(memory, [bad_result])
        assert len(proposals) == 0

    def test_suggest_next_experiments(self, agent, memory_with_results):
        memory, _ = memory_with_results
        proposals = agent.suggest_next_experiments(
            memory,
            available_features=["feat_a", "feat_b"],
            available_markets=[MarketType.CORNERS_TOTAL, MarketType.GOALS_TOTAL],
        )
        assert isinstance(proposals, list)

    def test_proposals_have_priority(self, agent, memory_with_results):
        memory, results = memory_with_results
        proposals = agent.analyze_results(memory, results)
        for p in proposals:
            assert 1 <= p.priority <= 10

    def test_follow_up_from_linked(self, agent, memory_with_results):
        """Follow-up proposals should reference the parent hypothesis."""
        memory, results = memory_with_results
        proposals = agent.analyze_results(memory, results)
        linked = [p for p in proposals if p.follow_up_from is not None]
        assert len(linked) > 0
        assert all(p.follow_up_from == "promising_1" for p in linked)


class TestLLMResearchAgent:
    """Tests for LLM research agent (falls back to deterministic without LLM)."""

    def test_implements_interface(self):
        agent = LLMResearchAgent(llm_callable=None)
        assert isinstance(agent, ResearchAgent)

    def test_falls_back_to_deterministic(self):
        agent = LLMResearchAgent(llm_callable=None)
        memory = ResearchMemory()
        hyp = ResearchHypothesis(
            hypothesis_id="test",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 5.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        memory.store_hypothesis(hyp)
        result = ExperimentResult(
            hypothesis_id="test",
            market="CORNERS_TOTAL",
            status=ExperimentStatus.COMPLETED,
            n_samples=500, n_bets=50, n_wins=28,
            win_rate=0.56, total_profit_loss=3.0, roi_pct=6.0,
            avg_ev=0.06, avg_odds=1.90, max_drawdown=2.0, sharpe_ratio=1.0,
        )
        memory.store_result("test", result)
        proposals = agent.analyze_results(memory, [result])
        # Should work without LLM
        assert isinstance(proposals, list)
