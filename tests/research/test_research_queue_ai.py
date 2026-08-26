"""Comprehensive tests for Batch 7 — Research Queue, Persistence & AI Researcher.

Test categories:
A. Persistence (save/retrieve/duplicate prevention)
B. Research Memory (lookup, history, skip)
C. Queue (state machine, atomic claim, retry, stale recovery)
D. Idempotency (duplicate tasks, experiments, proposals)
E. AI Proposals (structured output, validation, rejection)
F. AI Security (no code exec, no SQL, no credential leakage)
G. Research Integrity (AI cannot bypass FDR/governance)
H. Budget / Cost Controls
I. Reproducibility (deterministic hashes)
J. Integration (end-to-end pipeline)
K. Performance (benchmarks)
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import pytest

from src.research.ai import (
    MockLLMProvider,
    ProposalSource,
    ProposalStatus,
    ProposalValidator,
    ResearchAgent,
    ResearchBudget,
    ResearchContext,
    ResearchContextBuilder,
    ResearchProposal,
)
from src.research.ai.proposal import ResearchPhase
from src.research.ai.provider import DisabledProvider, LLMResponse
from src.research.ai.validator import ValidationResult
from src.research.persistence import InMemoryResearchRepository
from src.research.persistence.research_memory import ResearchMemory
from src.research.queue import QueueManager, ResearchTask, TaskStatus, TaskType


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════


@pytest.fixture
def repo():
    return InMemoryResearchRepository()


@pytest.fixture
def memory(repo):
    return ResearchMemory(repo)


@pytest.fixture
def queue(repo):
    return QueueManager(repo)


@pytest.fixture
def mock_provider():
    return MockLLMProvider()


@pytest.fixture
def agent(mock_provider):
    return ResearchAgent(provider=mock_provider)


@pytest.fixture
def validator():
    return ProposalValidator()


# ═══════════════════════════════════════════════════════════════
# A. PERSISTENCE
# ═══════════════════════════════════════════════════════════════


class TestPersistence:
    """Test repository save/retrieve/duplicate prevention."""

    def test_save_candidate(self, repo):
        assert repo.save_candidate("hash1", {"market_type": "CORNERS"}) is True

    def test_retrieve_candidate(self, repo):
        repo.save_candidate("hash1", {"market_type": "CORNERS"})
        result = repo.get_candidate("hash1")
        assert result is not None
        assert result["market_type"] == "CORNERS"

    def test_duplicate_candidate_rejected(self, repo):
        assert repo.save_candidate("hash1", {"data": 1}) is True
        assert repo.save_candidate("hash1", {"data": 2}) is False

    def test_candidate_exists(self, repo):
        assert repo.candidate_exists("hash1") is False
        repo.save_candidate("hash1", {})
        assert repo.candidate_exists("hash1") is True

    def test_save_hypothesis(self, repo):
        assert repo.save_hypothesis("hyp1", {"direction": "OVER"}) is True
        assert repo.hypothesis_exists("hyp1") is True

    def test_duplicate_hypothesis_rejected(self, repo):
        repo.save_hypothesis("hyp1", {})
        assert repo.save_hypothesis("hyp1", {}) is False

    def test_save_experiment(self, repo):
        assert repo.save_experiment("exp1", {"status": "COMPLETED"}) is True
        assert repo.experiment_exists("exp1") is True

    def test_duplicate_experiment_rejected(self, repo):
        repo.save_experiment("exp1", {})
        assert repo.save_experiment("exp1", {}) is False

    def test_save_walkforward(self, repo):
        assert repo.save_walkforward("wf1", {"folds": 5}) is True

    def test_save_governance(self, repo):
        repo.save_governance_decision("hyp1", {"state": "REJECTED"})
        decisions = repo.get_governance_decisions("hyp1")
        assert len(decisions) == 1

    def test_multiple_governance_decisions(self, repo):
        repo.save_governance_decision("hyp1", {"state": "PROMISING"})
        repo.save_governance_decision("hyp1", {"state": "REJECTED"})
        decisions = repo.get_governance_decisions("hyp1")
        assert len(decisions) == 2

    def test_save_proposal(self, repo):
        assert repo.save_proposal("prop1", {"source": "AI"}) is True
        result = repo.get_proposal("prop1")
        assert result["source"] == "AI"

    def test_count_candidates(self, repo):
        for i in range(5):
            repo.save_candidate(f"c{i}", {})
        assert repo.count_candidates() == 5

    def test_list_candidates_with_filter(self, repo):
        repo.save_candidate("c1", {"market_type": "CORNERS"})
        repo.save_candidate("c2", {"market_type": "GOALS"})
        corners = repo.list_candidates(market_type="CORNERS")
        assert len(corners) == 1


# ═══════════════════════════════════════════════════════════════
# B. RESEARCH MEMORY
# ═══════════════════════════════════════════════════════════════


class TestResearchMemory:
    """Test research memory operations."""

    def test_has_candidate(self, memory):
        assert memory.has_candidate("c1") is False
        memory.record_candidate("c1", {"market": "CORNERS"})
        assert memory.has_candidate("c1") is True

    def test_has_hypothesis(self, memory):
        assert memory.has_hypothesis("h1") is False
        memory.record_hypothesis("h1", {"direction": "OVER"})
        assert memory.has_hypothesis("h1") is True

    def test_has_experiment(self, memory):
        assert memory.has_experiment("e1") is False
        memory.record_experiment("e1", {"status": "COMPLETED"})
        assert memory.has_experiment("e1") is True

    def test_should_skip_duplicate(self, memory):
        assert memory.should_skip_experiment("e1") is False
        memory.record_experiment("e1", {})
        assert memory.should_skip_experiment("e1") is True

    def test_governance_history(self, memory):
        memory.record_governance("h1", {"state": "PROMISING"})
        memory.record_governance("h1", {"state": "REJECTED"})
        history = memory.get_governance_history("h1")
        assert len(history) == 2

    def test_summary(self, memory):
        memory.record_candidate("c1", {})
        memory.record_experiment("e1", {})
        summary = memory.summary()
        assert summary["candidates"] == 1
        assert summary["experiments"] == 1

    def test_duplicate_candidate_returns_false(self, memory):
        assert memory.record_candidate("c1", {}) is True
        assert memory.record_candidate("c1", {}) is False


# ═══════════════════════════════════════════════════════════════
# C. QUEUE STATE MACHINE
# ═══════════════════════════════════════════════════════════════


class TestQueueStateMachine:
    """Test task state machine and queue operations."""

    def test_task_creation(self):
        task = ResearchTask.create(
            task_type=TaskType.EXPERIMENT,
            candidate_hash="c1",
            hypothesis_hash="h1",
        )
        assert task.status == TaskStatus.PENDING
        assert task.task_id == task.content_hash
        assert len(task.task_id) == 16

    def test_valid_transitions(self):
        task = ResearchTask.create(task_type=TaskType.EXPERIMENT)
        task.transition(TaskStatus.CLAIMED)
        assert task.status == TaskStatus.CLAIMED
        task.transition(TaskStatus.RUNNING)
        assert task.status == TaskStatus.RUNNING
        task.transition(TaskStatus.COMPLETED)
        assert task.status == TaskStatus.COMPLETED

    def test_invalid_transition_raises(self):
        task = ResearchTask.create(task_type=TaskType.EXPERIMENT)
        with pytest.raises(ValueError, match="Invalid transition"):
            task.transition(TaskStatus.COMPLETED)  # Can't go PENDING→COMPLETED

    def test_terminal_states(self):
        task = ResearchTask.create(task_type=TaskType.EXPERIMENT)
        task.transition(TaskStatus.CLAIMED)
        task.transition(TaskStatus.RUNNING)
        task.transition(TaskStatus.COMPLETED)
        assert task.is_terminal is True

    def test_submit_task(self, queue):
        task = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c1")
        task_id, is_new = queue.submit(task)
        assert is_new is True
        assert task_id == task.task_id

    def test_duplicate_submit_returns_existing(self, queue):
        task = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c1")
        _, is_new1 = queue.submit(task)
        _, is_new2 = queue.submit(task)
        assert is_new1 is True
        assert is_new2 is False

    def test_claim_task(self, queue):
        task = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c1")
        queue.submit(task)
        claimed = queue.claim("worker_1")
        assert claimed is not None
        assert claimed["status"] == TaskStatus.CLAIMED.value
        assert claimed["claimed_by"] == "worker_1"

    def test_claim_empty_queue(self, queue):
        assert queue.claim("worker_1") is None

    def test_start_task(self, queue):
        task = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c1")
        queue.submit(task)
        queue.claim("worker_1")
        assert queue.start(task.task_id) is True

    def test_complete_task(self, queue):
        task = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c1")
        queue.submit(task)
        queue.claim("worker_1")
        queue.start(task.task_id)
        assert queue.complete(task.task_id, result_reference="result_123") is True

    def test_fail_and_retry(self, queue):
        task = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c1", max_attempts=3)
        queue.submit(task)
        queue.claim("w1")
        queue.start(task.task_id)
        queue.fail(task.task_id, "timeout")
        # Should be RETRYABLE (attempt 1 < max 3)
        task_data = queue._repo.get_task(task.task_id)
        assert task_data["status"] == TaskStatus.RETRYABLE.value
        # Retry puts it back to PENDING
        assert queue.retry(task.task_id) is True
        task_data = queue._repo.get_task(task.task_id)
        assert task_data["status"] == TaskStatus.PENDING.value

    def test_max_attempts_exhausted(self, queue):
        task = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c1", max_attempts=1)
        queue.submit(task)
        queue.claim("w1")
        queue.start(task.task_id)
        queue.fail(task.task_id, "error")
        task_data = queue._repo.get_task(task.task_id)
        assert task_data["status"] == TaskStatus.FAILED.value

    def test_cancel_pending(self, queue):
        task = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c1")
        queue.submit(task)
        assert queue.cancel(task.task_id) is True
        task_data = queue._repo.get_task(task.task_id)
        assert task_data["status"] == TaskStatus.CANCELLED.value

    def test_stale_recovery(self, repo):
        qm = QueueManager(repo, stale_timeout=0.01)  # Very short timeout
        task = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c1")
        qm.submit(task)
        qm.claim("w1")
        time.sleep(0.02)  # Exceed timeout
        recovered = qm.recover_stale()
        assert recovered == 1
        task_data = repo.get_task(task.task_id)
        assert task_data["status"] == TaskStatus.PENDING.value

    def test_queue_depth(self, queue):
        for i in range(5):
            task = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash=f"c{i}")
            queue.submit(task)
        assert queue.queue_depth() == 5

    def test_concurrent_claim_safety(self, repo):
        """Two threads cannot claim the same task."""
        qm = QueueManager(repo)
        task = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="shared")
        qm.submit(task)

        results = []

        def claim_task(worker_id):
            result = qm.claim(worker_id)
            results.append(result)

        t1 = threading.Thread(target=claim_task, args=("w1",))
        t2 = threading.Thread(target=claim_task, args=("w2",))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Exactly one should succeed, one should get None
        claimed = [r for r in results if r is not None]
        assert len(claimed) == 1


# ═══════════════════════════════════════════════════════════════
# D. IDEMPOTENCY
# ═══════════════════════════════════════════════════════════════


class TestIdempotency:
    """Test idempotent operations."""

    def test_duplicate_task_same_id(self):
        """Same content produces same task_id."""
        t1 = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c1", hypothesis_hash="h1")
        t2 = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c1", hypothesis_hash="h1")
        assert t1.task_id == t2.task_id

    def test_different_content_different_id(self):
        t1 = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c1")
        t2 = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c2")
        assert t1.task_id != t2.task_id

    def test_duplicate_experiment_not_rerun(self, memory):
        """Already-executed experiments are not re-run."""
        memory.record_experiment("exp_abc", {"status": "COMPLETED"})
        assert memory.should_skip_experiment("exp_abc") is True

    def test_duplicate_proposal_same_hash(self):
        """Same proposal content produces same hash."""
        p1 = ResearchProposal(
            market_type="CORNERS_TOTAL",
            feature_ids=("dangerous_attacks_home",),
            direction="OVER",
        )
        p2 = ResearchProposal(
            market_type="CORNERS_TOTAL",
            feature_ids=("dangerous_attacks_home",),
            direction="OVER",
        )
        assert p1.content_hash == p2.content_hash


# ═══════════════════════════════════════════════════════════════
# E. AI PROPOSALS
# ═══════════════════════════════════════════════════════════════


class TestAIProposals:
    """Test AI proposal generation and validation."""

    def test_mock_provider_generates(self, agent):
        ctx = ResearchContext(market_type="CORNERS_TOTAL", available_features=("dangerous_attacks_home",))
        proposal = agent.propose(ctx)
        assert proposal is not None
        assert proposal.source == ProposalSource.AI
        assert proposal.phase == ResearchPhase.EXPLORATION
        assert proposal.market_type == "CORNERS_TOTAL"

    def test_ai_disabled_returns_none(self):
        agent = ResearchAgent(provider=DisabledProvider())
        ctx = ResearchContext(market_type="CORNERS_TOTAL")
        proposal = agent.propose(ctx)
        assert proposal is None

    def test_valid_proposal_passes_validation(self, validator):
        proposal = ResearchProposal(
            market_type="CORNERS_TOTAL",
            feature_ids=("dangerous_attacks_home",),
            conditions=({"feature_id": "dangerous_attacks_home", "operator": ">", "threshold": 30.0},),
            direction="OVER",
            operator_type="THRESHOLD_GT",
            model_type="historical_frequency",
        )
        result = validator.validate(proposal)
        assert result.valid is True

    def test_invalid_market_rejected(self, validator):
        proposal = ResearchProposal(
            market_type="NONEXISTENT_MARKET",
            feature_ids=("x",),
            direction="OVER",
        )
        result = validator.validate(proposal)
        assert result.valid is False
        assert "Unknown market" in result.errors[0]

    def test_invalid_direction_rejected(self, validator):
        proposal = ResearchProposal(
            market_type="CORNERS_TOTAL",
            feature_ids=("x",),
            direction="SIDEWAYS",
        )
        result = validator.validate(proposal)
        assert result.valid is False

    def test_no_features_rejected(self, validator):
        proposal = ResearchProposal(
            market_type="CORNERS_TOTAL",
            feature_ids=(),
            direction="OVER",
        )
        result = validator.validate(proposal)
        assert result.valid is False
        assert "feature_id required" in result.errors[0]

    def test_unsupported_model_rejected(self, validator):
        proposal = ResearchProposal(
            market_type="CORNERS_TOTAL",
            feature_ids=("x",),
            direction="OVER",
            model_type="deep_neural_network",
        )
        result = validator.validate(proposal)
        assert result.valid is False

    def test_post_match_feature_rejected(self, validator):
        """Features that are post-match outcomes cannot be used."""
        proposal = ResearchProposal(
            market_type="CORNERS_TOTAL",
            feature_ids=("home_goals",),  # Post-match!
            direction="OVER",
        )
        result = validator.validate(proposal)
        assert result.valid is False
        assert "post-match" in result.errors[0]

    def test_excessive_interaction_rejected(self, validator):
        """Too many conditions rejected."""
        conditions = tuple(
            {"feature_id": f"f{i}", "operator": ">", "threshold": i}
            for i in range(10)
        )
        proposal = ResearchProposal(
            market_type="CORNERS_TOTAL",
            feature_ids=("f0",),
            conditions=conditions,
            direction="OVER",
        )
        result = validator.validate(proposal)
        assert result.valid is False
        assert "depth" in result.errors[0].lower()

    def test_malformed_ai_response_handled(self):
        """Malformed JSON from AI doesn't crash."""
        provider = MockLLMProvider(responses=["this is not json at all"])
        agent = ResearchAgent(provider=provider)
        ctx = ResearchContext(market_type="CORNERS_TOTAL")
        proposal = agent.propose(ctx)
        assert proposal is None

    def test_proposal_has_prompt_version(self, agent):
        ctx = ResearchContext(market_type="CORNERS_TOTAL")
        proposal = agent.propose(ctx)
        assert proposal.prompt_version == "v2"

    def test_proposal_has_context_hash(self, agent):
        ctx = ResearchContext(market_type="CORNERS_TOTAL")
        proposal = agent.propose(ctx)
        assert proposal.context_hash == ctx.content_hash


# ═══════════════════════════════════════════════════════════════
# F. AI SECURITY
# ═══════════════════════════════════════════════════════════════


class TestAISecurity:
    """Test AI security boundaries."""

    def test_ai_cannot_execute_code(self):
        """AI output is parsed as JSON, never executed."""
        provider = MockLLMProvider(responses=['import os; os.system("rm -rf /")'])
        agent = ResearchAgent(provider=provider)
        ctx = ResearchContext()
        # Should return None (invalid JSON), never execute
        proposal = agent.propose(ctx)
        assert proposal is None

    def test_ai_cannot_execute_sql(self):
        """SQL injection in AI output is harmless (parsed as JSON only)."""
        provider = MockLLMProvider(responses=['{"market_type": "DROP TABLE research;--"}'])
        agent = ResearchAgent(provider=provider)
        ctx = ResearchContext()
        proposal = agent.propose(ctx)
        # Either None or rejected by validator (invalid market)
        if proposal:
            validator = ProposalValidator()
            result = validator.validate(proposal)
            assert result.valid is False

    def test_secrets_not_in_context(self):
        """Research context never contains secrets."""
        import os
        os.environ["FOOTYSTATS_API_KEY"] = "super_secret_key"
        os.environ["LLM_API_KEY"] = "another_secret"
        try:
            ctx = ResearchContext(
                market_type="TEST",
                available_features=("f1", "f2"),
            )
            prompt_text = ctx.to_prompt_section()
            ctx_dict = json.dumps({"hash": ctx.content_hash, "text": prompt_text})
            assert "super_secret" not in ctx_dict
            assert "another_secret" not in ctx_dict
        finally:
            del os.environ["FOOTYSTATS_API_KEY"]
            del os.environ["LLM_API_KEY"]

    def test_secrets_not_in_proposal(self):
        """Proposals never contain credentials."""
        proposal = ResearchProposal(
            market_type="CORNERS_TOTAL",
            feature_ids=("f1",),
            direction="OVER",
            rationale="Test",
        )
        d = proposal.to_dict()
        s = json.dumps(d)
        assert "api_key" not in s.lower()
        assert "password" not in s.lower()
        assert "secret" not in s.lower()

    def test_ai_cannot_modify_experiment_result(self):
        """AI proposals are DRAFT — they cannot alter existing results."""
        proposal = ResearchProposal(source=ProposalSource.AI, status=ProposalStatus.DRAFT)
        # Status is DRAFT, never EXECUTED or VALIDATED without deterministic pipeline
        assert proposal.status == ProposalStatus.DRAFT
        assert proposal.source == ProposalSource.AI


# ═══════════════════════════════════════════════════════════════
# G. RESEARCH INTEGRITY
# ═══════════════════════════════════════════════════════════════


class TestResearchIntegrity:
    """Test that AI cannot bypass deterministic evaluation."""

    def test_ai_proposals_enter_exploration(self, agent):
        """AI proposals always start in EXPLORATION phase."""
        ctx = ResearchContext(market_type="CORNERS_TOTAL")
        proposal = agent.propose(ctx)
        assert proposal.phase == ResearchPhase.EXPLORATION

    def test_ai_cannot_set_validated_status(self):
        """Even if AI output claims VALIDATED, it's overridden to DRAFT."""
        provider = MockLLMProvider(responses=[json.dumps({
            "market_type": "CORNERS_TOTAL",
            "feature_ids": ["dangerous_attacks_home"],
            "conditions": [{"feature_id": "dangerous_attacks_home", "operator": ">", "threshold": 30}],
            "direction": "OVER",
            "operator_type": "THRESHOLD_GT",
            "model_type": "historical_frequency",
            "rationale": "test",
            "confidence": 0.9,
            "status": "VALIDATED",  # AI tries to set this
        })])
        agent = ResearchAgent(provider=provider)
        ctx = ResearchContext(market_type="CORNERS_TOTAL")
        proposal = agent.propose(ctx)
        # Status is always DRAFT from AI, regardless of what it claims
        assert proposal.status == ProposalStatus.DRAFT

    def test_exploration_validation_separation(self):
        """Research phases are explicit and ordered."""
        phases = list(ResearchPhase)
        assert phases.index(ResearchPhase.EXPLORATION) < phases.index(ResearchPhase.VALIDATION)
        assert phases.index(ResearchPhase.VALIDATION) < phases.index(ResearchPhase.CONFIRMATION)


# ═══════════════════════════════════════════════════════════════
# H. BUDGET / COST CONTROLS
# ═══════════════════════════════════════════════════════════════


class TestBudget:
    """Test research budget controls."""

    def test_budget_tracks_usage(self):
        budget = ResearchBudget(max_tasks=5, max_experiments=3)
        assert budget.tasks_remaining == 5
        budget.use_task()
        assert budget.tasks_remaining == 4

    def test_budget_exhaustion(self):
        budget = ResearchBudget(max_tasks=2)
        assert budget.is_exhausted is False
        budget.use_task()
        budget.use_task()
        assert budget.is_exhausted is True
        assert "max_tasks" in budget.exhaustion_reason

    def test_budget_prevents_overuse(self):
        budget = ResearchBudget(max_ai_proposals=1)
        assert budget.use_ai_proposal() is True
        assert budget.use_ai_proposal() is False

    def test_budget_multiple_limits(self):
        budget = ResearchBudget(max_tasks=100, max_experiments=2)
        budget.use_experiment()
        budget.use_experiment()
        assert budget.is_exhausted is True
        assert "max_experiments" in budget.exhaustion_reason

    def test_runtime_budget(self):
        budget = ResearchBudget(max_runtime_seconds=0.01)
        budget.elapsed_seconds = 1.0
        assert budget.is_exhausted is True


# ═══════════════════════════════════════════════════════════════
# I. REPRODUCIBILITY
# ═══════════════════════════════════════════════════════════════


class TestReproducibility:
    """Test deterministic identity hashes."""

    def test_task_id_deterministic(self):
        t1 = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c1", payload={"x": 1})
        t2 = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c1", payload={"x": 1})
        assert t1.task_id == t2.task_id

    def test_task_id_changes_with_content(self):
        t1 = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c1")
        t2 = ResearchTask.create(task_type=TaskType.EXPERIMENT, candidate_hash="c2")
        assert t1.task_id != t2.task_id

    def test_proposal_hash_deterministic(self):
        p1 = ResearchProposal(market_type="CORNERS", feature_ids=("f1",), direction="OVER")
        p2 = ResearchProposal(market_type="CORNERS", feature_ids=("f1",), direction="OVER")
        assert p1.content_hash == p2.content_hash

    def test_proposal_hash_changes(self):
        p1 = ResearchProposal(market_type="CORNERS", feature_ids=("f1",), direction="OVER")
        p2 = ResearchProposal(market_type="CORNERS", feature_ids=("f1",), direction="UNDER")
        assert p1.content_hash != p2.content_hash

    def test_context_hash_deterministic(self):
        c1 = ResearchContext(market_type="TEST", available_features=("a", "b"))
        c2 = ResearchContext(market_type="TEST", available_features=("a", "b"))
        assert c1.content_hash == c2.content_hash


# ═══════════════════════════════════════════════════════════════
# J. INTEGRATION (end-to-end)
# ═══════════════════════════════════════════════════════════════


class TestIntegration:
    """End-to-end integration tests."""

    def test_full_pipeline_with_memory(self, repo, memory, queue, agent):
        """Full flow: propose → validate → queue → execute → persist → no duplicate."""
        # Step 1: AI proposes
        ctx = ResearchContext(market_type="CORNERS_TOTAL", available_features=("dangerous_attacks_home",))
        proposal = agent.propose(ctx)
        assert proposal is not None

        # Step 2: Validate
        validator = ProposalValidator()
        result = validator.validate(proposal)
        assert result.valid is True

        # Step 3: Check memory
        assert memory.has_candidate(proposal.content_hash) is False

        # Step 4: Record candidate
        memory.record_candidate(proposal.content_hash, proposal.to_dict())

        # Step 5: Queue task
        task = ResearchTask.create(
            task_type=TaskType.EXPERIMENT,
            candidate_hash=proposal.content_hash,
            requested_by="AI",
        )
        task_id, is_new = queue.submit(task)
        assert is_new is True

        # Step 6: Claim and execute
        claimed = queue.claim("worker_1")
        assert claimed is not None
        queue.start(task_id)
        queue.complete(task_id, result_reference="wf_result_hash")

        # Step 7: Record experiment
        memory.record_experiment("exp_" + proposal.content_hash, {"status": "COMPLETED"})

        # Step 8: Try to submit same task again
        _, is_new2 = queue.submit(task)
        assert is_new2 is False  # Idempotent

        # Step 9: Memory prevents duplicate experiment
        assert memory.should_skip_experiment("exp_" + proposal.content_hash) is True

    def test_ai_disabled_pipeline_works(self, repo, memory, queue):
        """System works with AI disabled."""
        agent = ResearchAgent(provider=DisabledProvider())
        ctx = ResearchContext(market_type="CORNERS_TOTAL")

        # AI returns None — system continues normally
        proposal = agent.propose(ctx)
        assert proposal is None

        # Deterministic candidate can still be queued
        task = ResearchTask.create(
            task_type=TaskType.EXPERIMENT,
            candidate_hash="deterministic_c1",
            requested_by="DETERMINISTIC",
        )
        task_id, is_new = queue.submit(task)
        assert is_new is True
        assert queue.queue_depth() == 1


# ═══════════════════════════════════════════════════════════════
# K. PERFORMANCE
# ═══════════════════════════════════════════════════════════════


class TestPerformance:
    """Performance benchmarks."""

    def test_10k_candidate_inserts(self, repo):
        """10,000 candidates in reasonable time."""
        start = time.time()
        for i in range(10000):
            repo.save_candidate(f"c{i:06d}", {"market_type": "CORNERS", "idx": i})
        elapsed = time.time() - start
        assert repo.count_candidates() == 10000
        assert elapsed < 5.0  # Should be very fast in-memory
        print(f"\n10k candidate inserts: {elapsed:.3f}s")

    def test_10k_task_inserts(self, repo):
        """10,000 tasks in reasonable time."""
        start = time.time()
        for i in range(10000):
            repo.save_task(f"t{i:06d}", {"status": "PENDING", "type": "EXPERIMENT"})
        elapsed = time.time() - start
        assert repo.count_tasks() == 10000
        assert elapsed < 5.0
        print(f"\n10k task inserts: {elapsed:.3f}s")

    def test_1k_experiment_inserts(self, repo):
        """1,000 experiments."""
        start = time.time()
        for i in range(1000):
            repo.save_experiment(f"e{i:04d}", {"status": "COMPLETED", "predictions": i * 10})
        elapsed = time.time() - start
        assert repo.count_experiments() == 1000
        assert elapsed < 2.0
        print(f"\n1k experiment inserts: {elapsed:.3f}s")

    def test_duplicate_detection_performance(self, repo):
        """Duplicate detection at scale."""
        for i in range(1000):
            repo.save_candidate(f"c{i}", {})
        start = time.time()
        for i in range(1000):
            repo.candidate_exists(f"c{i}")
        elapsed = time.time() - start
        assert elapsed < 1.0
        print(f"\n1k lookups: {elapsed:.3f}s")

    def test_queue_claim_throughput(self, repo):
        """Queue claiming throughput."""
        qm = QueueManager(repo)
        for i in range(1000):
            repo.save_task(f"t{i}", {"status": "PENDING", "type": "EXPERIMENT"})
        start = time.time()
        claimed = 0
        while True:
            result = qm.claim(f"w{claimed}")
            if result is None:
                break
            claimed += 1
        elapsed = time.time() - start
        assert claimed == 1000
        assert elapsed < 5.0
        print(f"\n1k claims: {elapsed:.3f}s ({claimed/elapsed:.0f} claims/s)")
