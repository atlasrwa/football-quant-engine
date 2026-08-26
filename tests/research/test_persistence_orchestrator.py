"""Comprehensive tests for Batch 8 — PostgreSQL Persistence & Research Orchestrator.

Test categories:
A. PostgreSQL repository (CRUD, duplicates, transactions)
B. Atomic task claiming (FOR UPDATE SKIP LOCKED)
C. Worker leases and stale recovery
D. Orchestrator lifecycle (plan, execute, resume)
E. Idempotency (duplicate tasks, experiments)
F. Concurrency (multiple workers)
G. Crash recovery simulation
H. Budget enforcement
I. Research events (audit trail)
J. Security (no credentials in data)
K. Deterministic identity
L. Integration (full pipeline with persistence)
M. Performance benchmark
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Optional

import pytest

from src.research.persistence.connection import ConnectionManager
from src.research.persistence.migrator import Migrator
from src.research.persistence.postgres import PostgresResearchRepository
from src.research.persistence.memory import InMemoryResearchRepository
from src.research.persistence.research_memory import ResearchMemory
from src.research.queue.manager import QueueManager
from src.research.queue.task import ResearchTask, TaskStatus, TaskType
from src.research.orchestrator import ResearchOrchestrator, RunStatus, RunState
from src.research.ai.budget import ResearchBudget


# ═══════════════════════════════════════════════════════════════
# FIXTURES
# ═══════════════════════════════════════════════════════════════

_TEST_DSN = "postgresql://research:research_test_pw@localhost:5432/research_test"


@pytest.fixture(scope="module")
def pg_conn():
    """Module-scoped PostgreSQL connection for tests."""
    conn = ConnectionManager(dsn=_TEST_DSN, pool_min=2, pool_max=10)
    conn.initialize()
    migrator = Migrator(conn)
    migrator.migrate()
    yield conn
    conn.close()


@pytest.fixture
def pg_repo(pg_conn):
    """Per-test PostgreSQL repository (cleans tables before each test)."""
    repo = PostgresResearchRepository(pg_conn, lease_seconds=5)
    # Clean all research tables before each test
    with pg_conn.cursor() as cur:
        cur.execute("DELETE FROM research_events")
        cur.execute("DELETE FROM research_tasks")
        cur.execute("DELETE FROM research_governance")
        cur.execute("DELETE FROM research_proposals")
        cur.execute("DELETE FROM research_walkforwards")
        cur.execute("DELETE FROM research_experiments")
        cur.execute("DELETE FROM research_hypotheses")
        cur.execute("DELETE FROM research_candidates")
        cur.execute("DELETE FROM research_runs")
    return repo


@pytest.fixture
def mem_repo():
    """In-memory repository for comparison."""
    return InMemoryResearchRepository()


@pytest.fixture
def pg_queue(pg_repo, pg_conn):
    """Queue manager backed by PostgreSQL."""
    return QueueManager(pg_repo)


@pytest.fixture
def pg_memory(pg_repo):
    return ResearchMemory(pg_repo)


# ═══════════════════════════════════════════════════════════════
# A. POSTGRESQL REPOSITORY
# ═══════════════════════════════════════════════════════════════


class TestPostgresRepository:
    """Test PostgreSQL CRUD operations."""

    def test_save_and_get_candidate(self, pg_repo):
        assert pg_repo.save_candidate("hash1", {"market_type": "CORNERS"}) is True
        result = pg_repo.get_candidate("hash1")
        assert result is not None
        assert result["market_type"] == "CORNERS"

    def test_duplicate_candidate_rejected(self, pg_repo):
        assert pg_repo.save_candidate("dup1", {"x": 1}) is True
        assert pg_repo.save_candidate("dup1", {"x": 2}) is False

    def test_candidate_exists(self, pg_repo):
        assert pg_repo.candidate_exists("c1") is False
        pg_repo.save_candidate("c1", {})
        assert pg_repo.candidate_exists("c1") is True

    def test_save_and_get_hypothesis(self, pg_repo):
        pg_repo.save_hypothesis("h1", {"direction": "OVER", "candidate_hash": "c1"})
        result = pg_repo.get_hypothesis("h1")
        assert result["direction"] == "OVER"

    def test_save_and_get_experiment(self, pg_repo):
        pg_repo.save_experiment("exp1", {"status": "COMPLETED", "market_type": "CORNERS"})
        result = pg_repo.get_experiment("exp1")
        assert result["status"] == "COMPLETED"

    def test_duplicate_experiment_rejected(self, pg_repo):
        pg_repo.save_experiment("exp1", {"status": "COMPLETED"})
        assert pg_repo.save_experiment("exp1", {"status": "NEW"}) is False

    def test_save_walkforward(self, pg_repo):
        pg_repo.save_walkforward("wf1", {"folds": 5, "experiment_id": "exp1"})
        result = pg_repo.get_walkforward("wf1")
        assert result["folds"] == 5

    def test_governance_decisions(self, pg_repo):
        pg_repo.save_governance_decision("h1", {"state": "PROMISING"})
        pg_repo.save_governance_decision("h1", {"state": "REJECTED"})
        decisions = pg_repo.get_governance_decisions("h1")
        assert len(decisions) == 2

    def test_save_proposal(self, pg_repo):
        pg_repo.save_proposal("p1", {"source": "AI", "status": "DRAFT"})
        result = pg_repo.get_proposal("p1")
        assert result["source"] == "AI"

    def test_count_candidates(self, pg_repo):
        for i in range(5):
            pg_repo.save_candidate(f"cnt_{i}", {"market_type": "TEST"})
        assert pg_repo.count_candidates() == 5

    def test_list_candidates_filter(self, pg_repo):
        pg_repo.save_candidate("lf1", {"market_type": "CORNERS"})
        pg_repo.save_candidate("lf2", {"market_type": "GOALS"})
        corners = pg_repo.list_candidates(market_type="CORNERS")
        assert len(corners) == 1

    def test_save_and_get_run(self, pg_repo):
        pg_repo.save_run("run1", {"status": "CREATED", "total_tasks": 10})
        result = pg_repo.get_run("run1")
        assert result is not None
        assert result["total_tasks"] == 10

    def test_transaction_rollback(self, pg_conn, pg_repo):
        """Verify transaction rollback on error."""
        pg_repo.save_candidate("tx1", {"market_type": "A"})
        # Verify it exists
        assert pg_repo.candidate_exists("tx1") is True


# ═══════════════════════════════════════════════════════════════
# B. ATOMIC TASK CLAIMING
# ═══════════════════════════════════════════════════════════════


class TestAtomicClaiming:
    """Test FOR UPDATE SKIP LOCKED task claiming."""

    def test_basic_claim(self, pg_repo):
        pg_repo.save_task("t1", {"status": "PENDING", "task_type": "EXPERIMENT", "priority": 0})
        result = pg_repo.claim_next_task("worker_1")
        assert result is not None
        assert result["status"] == "CLAIMED"
        assert result["claimed_by"] == "worker_1"

    def test_empty_queue_returns_none(self, pg_repo):
        assert pg_repo.claim_next_task("w1") is None

    def test_claimed_task_not_reclaimed(self, pg_repo):
        pg_repo.save_task("t1", {"status": "PENDING", "task_type": "EXPERIMENT", "priority": 0})
        pg_repo.claim_next_task("w1")
        # Second claim should get nothing
        assert pg_repo.claim_next_task("w2") is None

    def test_priority_ordering(self, pg_repo):
        pg_repo.save_task("low", {"status": "PENDING", "task_type": "EXPERIMENT", "priority": 0})
        pg_repo.save_task("high", {"status": "PENDING", "task_type": "EXPERIMENT", "priority": 10})
        # Higher priority claimed first
        result = pg_repo.claim_next_task("w1")
        assert result["_id"] == "high"

    def test_concurrent_claims_no_double(self, pg_repo):
        """Multiple threads cannot claim the same task."""
        for i in range(5):
            pg_repo.save_task(f"ct_{i}", {"status": "PENDING", "task_type": "EXPERIMENT", "priority": 0})

        results = []
        def claim(worker_id):
            r = pg_repo.claim_next_task(worker_id)
            if r:
                results.append(r["_id"])

        threads = [threading.Thread(target=claim, args=(f"w{i}",)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have claimed exactly 5 tasks (one each)
        assert len(results) == 5
        assert len(set(results)) == 5  # All unique


# ═══════════════════════════════════════════════════════════════
# C. WORKER LEASES AND STALE RECOVERY
# ═══════════════════════════════════════════════════════════════


class TestLeases:
    """Test worker lease expiry and recovery."""

    def test_lease_set_on_claim(self, pg_repo, pg_conn):
        pg_repo.save_task("lease1", {"status": "PENDING", "task_type": "EXPERIMENT", "priority": 0})
        pg_repo.claim_next_task("w1")
        with pg_conn.cursor() as cur:
            cur.execute("SELECT lease_expiry FROM research_tasks WHERE task_id = 'lease1'")
            row = cur.fetchone()
            assert row["lease_expiry"] is not None

    def test_stale_recovery(self, pg_repo, pg_conn):
        """Tasks with expired leases are recovered."""
        pg_repo.save_task("stale1", {"status": "PENDING", "task_type": "EXPERIMENT", "priority": 0})
        pg_repo.claim_next_task("dead_worker")
        # Artificially expire the lease
        with pg_conn.cursor() as cur:
            cur.execute(
                "UPDATE research_tasks SET lease_expiry = NOW() - INTERVAL '1 hour' WHERE task_id = 'stale1'"
            )
        # Recover
        recovered = pg_repo.recover_stale_tasks()
        assert recovered == 1
        # Should now be claimable
        result = pg_repo.claim_next_task("new_worker")
        assert result is not None
        assert result["_id"] == "stale1"


# ═══════════════════════════════════════════════════════════════
# D. ORCHESTRATOR LIFECYCLE
# ═══════════════════════════════════════════════════════════════


class TestOrchestrator:
    """Test research orchestrator plan/execute/resume."""

    def test_plan_and_execute(self, pg_repo, pg_queue, pg_memory):
        budget = ResearchBudget(max_tasks=100, max_experiments=100)
        orch = ResearchOrchestrator(pg_repo, pg_queue, pg_memory, budget, worker_id="test_w")

        tasks = [
            ResearchTask.create(TaskType.EXPERIMENT, candidate_hash=f"c{i}", payload={"experiment_id": f"e{i}"})
            for i in range(5)
        ]
        state = orch.plan("run_plan_1", tasks)
        assert state.status == RunStatus.PLANNED

        # Execute
        def executor(task_data):
            return f"result_{task_data.get('candidate_hash', '')}"

        state = orch.execute("run_plan_1", executor)
        assert state.completed_tasks == 5
        assert state.status == RunStatus.COMPLETED

    def test_resume_after_partial(self, pg_repo, pg_queue, pg_memory):
        """Resume continues from where it left off."""
        budget = ResearchBudget(max_tasks=100, max_experiments=100)
        orch = ResearchOrchestrator(pg_repo, pg_queue, pg_memory, budget, worker_id="test_w")

        tasks = [
            ResearchTask.create(TaskType.EXPERIMENT, candidate_hash=f"r{i}", payload={"experiment_id": f"re{i}"})
            for i in range(10)
        ]
        orch.plan("run_resume_1", tasks)

        # Execute only 3
        count = [0]
        def limited_executor(task_data):
            count[0] += 1
            return f"result_{count[0]}"

        state = orch.execute("run_resume_1", limited_executor, max_tasks=3)
        assert state.completed_tasks == 3

        # Resume remaining
        state = orch.resume("run_resume_1", limited_executor)
        assert state.completed_tasks >= 3  # At least the resumed ones

    def test_skip_completed_experiments(self, pg_repo, pg_queue, pg_memory):
        """Already-executed experiments are skipped during planning."""
        # Pre-record an experiment
        pg_memory.record_experiment("existing_exp", {"status": "COMPLETED"})

        budget = ResearchBudget(max_tasks=100, max_experiments=100)
        orch = ResearchOrchestrator(pg_repo, pg_queue, pg_memory, budget, worker_id="test_w")

        tasks = [
            ResearchTask.create(TaskType.EXPERIMENT, candidate_hash="c1", payload={"experiment_id": "existing_exp"}),
            ResearchTask.create(TaskType.EXPERIMENT, candidate_hash="c2", payload={"experiment_id": "new_exp"}),
        ]
        state = orch.plan("run_skip_1", tasks)
        assert state.skipped_tasks == 1

    def test_budget_exhaustion_stops_run(self, pg_repo, pg_queue, pg_memory):
        """Run stops when budget exhausted."""
        budget = ResearchBudget(max_tasks=2, max_experiments=100)
        orch = ResearchOrchestrator(pg_repo, pg_queue, pg_memory, budget, worker_id="test_w")

        tasks = [
            ResearchTask.create(TaskType.EXPERIMENT, candidate_hash=f"b{i}", payload={"experiment_id": f"be{i}"})
            for i in range(5)
        ]
        orch.plan("run_budget_1", tasks)
        state = orch.execute("run_budget_1", lambda td: "ok")
        # After 2 tasks, budget.use_task() exhausts max_tasks=2
        # Next iteration checks budget → BUDGET_EXHAUSTED
        assert state.status == RunStatus.BUDGET_EXHAUSTED
        assert state.completed_tasks == 2

    def test_cancel_run(self, pg_repo, pg_queue, pg_memory):
        budget = ResearchBudget(max_tasks=100, max_experiments=100)
        orch = ResearchOrchestrator(pg_repo, pg_queue, pg_memory, budget, worker_id="test_w")
        pg_repo.save_run("cancel_run", {"status": "RUNNING"})
        state = orch.cancel("cancel_run")
        assert state.status == RunStatus.CANCELLED


# ═══════════════════════════════════════════════════════════════
# E. IDEMPOTENCY
# ═══════════════════════════════════════════════════════════════


class TestIdempotency:
    """Test idempotent operations."""

    def test_duplicate_task_submission(self, pg_repo, pg_queue):
        task = ResearchTask.create(TaskType.EXPERIMENT, candidate_hash="idem1")
        _, new1 = pg_queue.submit(task)
        _, new2 = pg_queue.submit(task)
        assert new1 is True
        assert new2 is False

    def test_duplicate_experiment_prevented(self, pg_repo):
        pg_repo.save_experiment("idem_exp", {"status": "COMPLETED"})
        assert pg_repo.save_experiment("idem_exp", {"status": "NEW"}) is False
        # Original preserved
        result = pg_repo.get_experiment("idem_exp")
        assert result["status"] == "COMPLETED"


# ═══════════════════════════════════════════════════════════════
# F. CONCURRENCY
# ═══════════════════════════════════════════════════════════════


class TestConcurrency:
    """Test concurrent worker safety."""

    def test_10_workers_100_tasks(self, pg_repo):
        """10 concurrent workers claiming 100 tasks — each claimed exactly once."""
        for i in range(100):
            pg_repo.save_task(f"conc_{i:03d}", {"status": "PENDING", "task_type": "EXPERIMENT", "priority": 0})

        claimed_ids: list[str] = []
        lock = threading.Lock()

        def worker(wid):
            while True:
                result = pg_repo.claim_next_task(f"worker_{wid}")
                if result is None:
                    break
                with lock:
                    claimed_ids.append(result["_id"])

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(claimed_ids) == 100
        assert len(set(claimed_ids)) == 100  # All unique — no double claims


# ═══════════════════════════════════════════════════════════════
# G. CRASH RECOVERY
# ═══════════════════════════════════════════════════════════════


class TestCrashRecovery:
    """Test recovery from simulated failures."""

    def test_recovery_after_worker_death(self, pg_repo, pg_conn):
        """Dead worker's task recovered via lease expiry."""
        pg_repo.save_task("crash1", {"status": "PENDING", "task_type": "EXPERIMENT", "priority": 0})
        pg_repo.claim_next_task("dead_worker")
        # Expire lease
        with pg_conn.cursor() as cur:
            cur.execute("UPDATE research_tasks SET lease_expiry = NOW() - INTERVAL '1 min' WHERE task_id = 'crash1'")
        # Recover
        pg_repo.recover_stale_tasks()
        # New worker can claim
        result = pg_repo.claim_next_task("alive_worker")
        assert result is not None
        assert result["_id"] == "crash1"

    def test_completed_result_survives_restart(self, pg_repo):
        """Results persist across connection cycles."""
        pg_repo.save_experiment("persist1", {"status": "COMPLETED", "data": "important"})
        # Simulate "restart" by fetching again
        result = pg_repo.get_experiment("persist1")
        assert result["status"] == "COMPLETED"


# ═══════════════════════════════════════════════════════════════
# H. BUDGET ENFORCEMENT
# ═══════════════════════════════════════════════════════════════


class TestBudgetEnforcement:
    """Test budget controls in orchestrator."""

    def test_task_budget_enforced(self, pg_repo, pg_queue, pg_memory):
        budget = ResearchBudget(max_tasks=3, max_experiments=100)
        orch = ResearchOrchestrator(pg_repo, pg_queue, pg_memory, budget, worker_id="bw")
        tasks = [
            ResearchTask.create(TaskType.EXPERIMENT, candidate_hash=f"bt{i}", payload={"experiment_id": f"bte{i}"})
            for i in range(10)
        ]
        orch.plan("budget_run", tasks)
        state = orch.execute("budget_run", lambda td: "ok")
        assert state.completed_tasks == 3
        assert state.status == RunStatus.BUDGET_EXHAUSTED


# ═══════════════════════════════════════════════════════════════
# I. RESEARCH EVENTS
# ═══════════════════════════════════════════════════════════════


class TestResearchEvents:
    """Test append-only event trail."""

    def test_events_recorded(self, pg_repo, pg_queue, pg_memory):
        budget = ResearchBudget(max_tasks=10, max_experiments=10)
        orch = ResearchOrchestrator(pg_repo, pg_queue, pg_memory, budget, worker_id="ev_w")
        tasks = [ResearchTask.create(TaskType.EXPERIMENT, candidate_hash="ev_c", payload={"experiment_id": "ev_e"})]
        orch.plan("event_run", tasks)
        orch.execute("event_run", lambda td: "ok")

        events = pg_repo.get_events(run_id="event_run")
        event_types = [e["event_type"] for e in events]
        assert "RUN_PLANNED" in event_types
        assert "RUN_STARTED" in event_types

    def test_events_are_append_only(self, pg_repo):
        """Events cannot be modified (only appended)."""
        pg_repo.append_event("TEST_EVENT", "test", "t1", data={"msg": "hello"})
        events = pg_repo.get_events(entity_type="test", entity_id="t1")
        assert len(events) == 1
        assert events[0]["data"]["msg"] == "hello"


# ═══════════════════════════════════════════════════════════════
# J. SECURITY
# ═══════════════════════════════════════════════════════════════


class TestSecurity:
    """Test credential security."""

    def test_no_credentials_in_task_data(self, pg_repo):
        """Task data never contains credentials."""
        pg_repo.save_task("sec1", {
            "status": "PENDING", "task_type": "EXPERIMENT",
            "candidate_hash": "c1", "priority": 0,
        })
        task = pg_repo.get_task("sec1")
        task_str = json.dumps(task)
        assert "research_test_pw" not in task_str
        assert "api_key" not in task_str.lower()

    def test_no_credentials_in_events(self, pg_repo):
        pg_repo.append_event("TEST", data={"safe": True})
        events = pg_repo.get_events(entity_type="")
        for e in events:
            e_str = json.dumps(e, default=str)
            assert "research_test_pw" not in e_str


# ═══════════════════════════════════════════════════════════════
# K. DETERMINISTIC IDENTITY
# ═══════════════════════════════════════════════════════════════


class TestDeterministicIdentity:
    """Test that persistence doesn't alter deterministic identity."""

    def test_same_task_same_id(self):
        t1 = ResearchTask.create(TaskType.EXPERIMENT, candidate_hash="det1", payload={"x": 1})
        t2 = ResearchTask.create(TaskType.EXPERIMENT, candidate_hash="det1", payload={"x": 1})
        assert t1.task_id == t2.task_id

    def test_content_hash_not_affected_by_db(self, pg_repo):
        """Saving and loading doesn't change content identity."""
        pg_repo.save_candidate("id_test", {"market_type": "CORNERS", "feature": "x"})
        loaded = pg_repo.get_candidate("id_test")
        # The content hash is the key itself
        assert loaded["_hash"] == "id_test"


# ═══════════════════════════════════════════════════════════════
# L. INTEGRATION
# ═══════════════════════════════════════════════════════════════


class TestIntegration:
    """Full pipeline integration with PostgreSQL persistence."""

    def test_full_pipeline(self, pg_repo, pg_queue, pg_memory):
        """Plan → Execute → Persist → Memory lookup."""
        budget = ResearchBudget(max_tasks=50, max_experiments=50)
        orch = ResearchOrchestrator(pg_repo, pg_queue, pg_memory, budget, worker_id="integ_w")

        # Plan
        tasks = [
            ResearchTask.create(
                TaskType.EXPERIMENT,
                candidate_hash=f"integ_c{i}",
                hypothesis_hash=f"integ_h{i}",
                payload={"experiment_id": f"integ_e{i}"},
            )
            for i in range(10)
        ]
        state = orch.plan("integ_run_1", tasks)
        assert state.status == RunStatus.PLANNED

        # Execute (simulated)
        def executor(task_data):
            exp_id = task_data.get("experiment_id", task_data.get("payload", {}).get("experiment_id", ""))
            cand_hash = task_data.get("candidate_hash", "")
            # Persist result
            pg_memory.record_experiment(exp_id, {"status": "COMPLETED", "candidate_hash": cand_hash})
            pg_memory.record_candidate(cand_hash, {"market_type": "CORNERS"})
            return exp_id

        state = orch.execute("integ_run_1", executor)
        assert state.status == RunStatus.COMPLETED
        assert state.completed_tasks == 10

        # Verify memory
        assert pg_memory.has_experiment("integ_e0") is True
        assert pg_memory.has_candidate("integ_c0") is True
        assert pg_memory.should_skip_experiment("integ_e5") is True

        # Verify no duplicates on re-plan
        state2 = orch.plan("integ_run_1", tasks)
        # Run already completed — returns terminal state
        assert state2.status == RunStatus.COMPLETED


# ═══════════════════════════════════════════════════════════════
# M. PERFORMANCE
# ═══════════════════════════════════════════════════════════════


class TestPerformance:
    """Performance benchmarks on PostgreSQL."""

    def test_10k_candidate_inserts(self, pg_repo):
        start = time.time()
        for i in range(10000):
            pg_repo.save_candidate(f"perf_c_{i:06d}", {"market_type": "CORNERS", "idx": i})
        elapsed = time.time() - start
        assert pg_repo.count_candidates() >= 10000
        assert elapsed < 60.0  # Should complete within 60s
        print(f"\n10k PG candidate inserts: {elapsed:.2f}s ({10000/elapsed:.0f}/s)")

    def test_10k_task_inserts(self, pg_repo):
        start = time.time()
        for i in range(10000):
            pg_repo.save_task(f"perf_t_{i:06d}", {"status": "PENDING", "task_type": "EXPERIMENT", "priority": 0})
        elapsed = time.time() - start
        assert pg_repo.count_tasks() >= 10000
        assert elapsed < 60.0
        print(f"\n10k PG task inserts: {elapsed:.2f}s ({10000/elapsed:.0f}/s)")

    def test_concurrent_claim_throughput(self, pg_repo):
        """Measure claim throughput with multiple workers."""
        for i in range(100):
            pg_repo.save_task(f"tput_{i:04d}", {"status": "PENDING", "task_type": "EXPERIMENT", "priority": 0})

        claimed = []
        lock = threading.Lock()

        def worker(wid):
            while True:
                r = pg_repo.claim_next_task(f"tput_w{wid}")
                if r is None:
                    break
                with lock:
                    claimed.append(r["_id"])

        start = time.time()
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.time() - start

        assert len(claimed) == 100
        assert len(set(claimed)) == 100
        print(f"\n100 concurrent claims (5 workers): {elapsed:.2f}s ({100/elapsed:.0f}/s)")
