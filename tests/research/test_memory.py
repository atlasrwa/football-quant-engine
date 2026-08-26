"""Tests for research memory system."""

import pytest

from src.research.candidate_generator import GenerationMethod, ResearchHypothesis
from src.research.experiment import ExperimentResult, ExperimentStatus
from src.research.market import MarketType
from src.research.memory import HypothesisStatus, MemoryEntry, ResearchMemory


class TestResearchMemory:
    """Tests for ResearchMemory."""

    @pytest.fixture
    def memory(self):
        return ResearchMemory()

    @pytest.fixture
    def hypothesis(self):
        return ResearchHypothesis(
            hypothesis_id="hyp_1",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("feat_a",),
            conditions=(("feat_a", ">", 5.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )

    @pytest.fixture
    def result_promising(self):
        return ExperimentResult(
            hypothesis_id="hyp_1",
            market="CORNERS_TOTAL",
            status=ExperimentStatus.COMPLETED,
            n_samples=500,
            n_bets=100,
            n_wins=55,
            win_rate=0.55,
            total_profit_loss=5.0,
            roi_pct=5.0,
            avg_ev=0.05,
            avg_odds=1.90,
            max_drawdown=3.0,
            sharpe_ratio=1.2,
            p_value=0.03,
            is_significant=True,
        )

    def test_store_hypothesis_new(self, memory, hypothesis):
        hid, is_new = memory.store_hypothesis(hypothesis)
        assert is_new is True
        assert hid == hypothesis.hypothesis_id

    def test_store_hypothesis_duplicate(self, memory, hypothesis):
        memory.store_hypothesis(hypothesis)
        # Same content hash → duplicate
        dup = ResearchHypothesis(
            hypothesis_id="hyp_2",  # Different ID
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("feat_a",),
            conditions=(("feat_a", ">", 5.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        hid, is_new = memory.store_hypothesis(dup)
        assert is_new is False
        assert hid == hypothesis.hypothesis_id  # Returns original

    def test_is_duplicate(self, memory, hypothesis):
        assert memory.is_duplicate(hypothesis) is False
        memory.store_hypothesis(hypothesis)
        assert memory.is_duplicate(hypothesis) is True

    def test_store_result_validated(self, memory, hypothesis, result_promising):
        memory.store_hypothesis(hypothesis)
        memory.store_result(hypothesis.hypothesis_id, result_promising)
        entry = memory.get_entry(hypothesis.hypothesis_id)
        assert entry.status == HypothesisStatus.VALIDATED
        assert entry.result is not None
        assert entry.tested_at is not None

    def test_store_result_rejected(self, memory, hypothesis):
        memory.store_hypothesis(hypothesis)
        bad_result = ExperimentResult(
            hypothesis_id="hyp_1",
            market="CORNERS_TOTAL",
            status=ExperimentStatus.COMPLETED,
            n_samples=500,
            n_bets=100,
            n_wins=40,
            win_rate=0.40,
            total_profit_loss=-10.0,
            roi_pct=-10.0,
            avg_ev=-0.1,
            avg_odds=1.90,
            max_drawdown=15.0,
            sharpe_ratio=-0.5,
            p_value=0.8,
            is_significant=False,
        )
        memory.store_result(hypothesis.hypothesis_id, bad_result)
        entry = memory.get_entry(hypothesis.hypothesis_id)
        assert entry.status == HypothesisStatus.REJECTED

    def test_link_experiments(self, memory):
        h1 = ResearchHypothesis(
            hypothesis_id="parent",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 1.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        h2 = ResearchHypothesis(
            hypothesis_id="child",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 2.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        memory.store_hypothesis(h1)
        memory.store_hypothesis(h2)
        memory.link_experiments("parent", "child")
        parent = memory.get_entry("parent")
        child = memory.get_entry("child")
        assert "child" in parent.children_ids
        assert child.parent_id == "parent"

    def test_get_by_status(self, memory, hypothesis, result_promising):
        memory.store_hypothesis(hypothesis)
        memory.store_result(hypothesis.hypothesis_id, result_promising)
        validated = memory.get_by_status(HypothesisStatus.VALIDATED)
        assert len(validated) == 1

    def test_get_promising(self, memory, hypothesis, result_promising):
        memory.store_hypothesis(hypothesis)
        memory.store_result(hypothesis.hypothesis_id, result_promising)
        promising = memory.get_promising()
        assert len(promising) == 1

    def test_get_summary(self, memory, hypothesis, result_promising):
        memory.store_hypothesis(hypothesis)
        memory.store_result(hypothesis.hypothesis_id, result_promising)
        summary = memory.get_summary()
        assert summary["VALIDATED"] == 1

    def test_total_experiments(self, memory, hypothesis):
        assert memory.total_experiments == 0
        memory.store_hypothesis(hypothesis)
        assert memory.total_experiments == 1

    def test_total_tested(self, memory, hypothesis, result_promising):
        memory.store_hypothesis(hypothesis)
        assert memory.total_tested == 0
        memory.store_result(hypothesis.hypothesis_id, result_promising)
        assert memory.total_tested == 1

    def test_to_context_generates_text(self, memory, hypothesis, result_promising):
        memory.store_hypothesis(hypothesis)
        memory.store_result(hypothesis.hypothesis_id, result_promising)
        context = memory.to_context()
        assert "Research Memory Summary" in context
        assert "1/1 tested" in context

    def test_prevents_duplicate_work(self, memory):
        """The core requirement: memory prevents re-testing same hypothesis."""
        h1 = ResearchHypothesis(
            hypothesis_id="first_try",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 5.0),),
            direction="OVER",
            generation_method=GenerationMethod.DETERMINISTIC,
        )
        h2 = ResearchHypothesis(
            hypothesis_id="second_try",
            market=MarketType.CORNERS_TOTAL,
            feature_ids=("f1",),
            conditions=(("f1", ">", 5.0),),  # Same conditions
            direction="OVER",
            generation_method=GenerationMethod.LLM,  # Different source
        )
        _, is_new_1 = memory.store_hypothesis(h1)
        assert is_new_1 is True
        _, is_new_2 = memory.store_hypothesis(h2)
        assert is_new_2 is False  # Prevented!
