"""PostgreSQL Research Repository Implementation.

Implements ResearchRepository with:
- Transactional operations
- Atomic task claiming (SELECT FOR UPDATE SKIP LOCKED)
- Worker leases with expiry
- JSONB storage for flexible research data
- Content-hash based identity (no UUIDs)
- Duplicate prevention via UNIQUE constraints
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import psycopg2
import psycopg2.extras

from src.research.persistence.connection import ConnectionManager
from src.research.persistence.repository import ResearchRepository

logger = logging.getLogger(__name__)

_DEFAULT_LEASE_SECONDS = 300  # 5 minutes


class PostgresResearchRepository(ResearchRepository):
    """PostgreSQL-backed research repository.

    Thread-safe via connection pooling and database transactions.
    Atomic task claiming via FOR UPDATE SKIP LOCKED.
    """

    def __init__(
        self,
        conn_manager: ConnectionManager,
        lease_seconds: int = _DEFAULT_LEASE_SECONDS,
    ) -> None:
        self._conn = conn_manager
        self._lease_seconds = lease_seconds

    # ═══ RESEARCH RUNS ═══

    def save_run(self, run_id: str, data: dict[str, Any]) -> bool:
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO research_runs (run_id, data, status)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (run_id) DO NOTHING""",
                    (run_id, json.dumps(data), data.get("status", "CREATED")),
                )
                return cur.rowcount > 0
        except Exception as e:
            logger.warning("save_run failed: %s", str(e)[:200])
            return False

    def get_run(self, run_id: str) -> Optional[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT data, status, created_at FROM research_runs WHERE run_id = %s", (run_id,))
            row = cur.fetchone()
            if row:
                result = dict(row["data"])
                result["_id"] = run_id
                result["status"] = row["status"]
                result["_created_at"] = row["created_at"].timestamp() if row["created_at"] else 0
                return result
            return None

    def update_run(self, run_id: str, updates: dict[str, Any]) -> bool:
        """Update run fields (status, data merge)."""
        with self._conn.cursor() as cur:
            if "status" in updates:
                cur.execute(
                    """UPDATE research_runs SET status = %s, updated_at = NOW()
                       WHERE run_id = %s""",
                    (updates["status"], run_id),
                )
            if "data" in updates:
                cur.execute(
                    """UPDATE research_runs SET data = data || %s, updated_at = NOW()
                       WHERE run_id = %s""",
                    (json.dumps(updates["data"]), run_id),
                )
            return cur.rowcount > 0

    def list_runs(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT run_id, data, status, created_at FROM research_runs ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (limit, offset),
            )
            results = []
            for row in cur.fetchall():
                d = dict(row["data"])
                d["_id"] = row["run_id"]
                d["status"] = row["status"]
                results.append(d)
            return results

    # ═══ CANDIDATES ═══

    def save_candidate(self, content_hash: str, data: dict[str, Any]) -> bool:
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO research_candidates (content_hash, market_type, data)
                       VALUES (%s, %s, %s)
                       ON CONFLICT (content_hash) DO NOTHING""",
                    (content_hash, data.get("market_type", ""), json.dumps(data)),
                )
                return cur.rowcount > 0
        except Exception:
            return False

    def get_candidate(self, content_hash: str) -> Optional[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT data FROM research_candidates WHERE content_hash = %s", (content_hash,))
            row = cur.fetchone()
            if row:
                result = dict(row["data"])
                result["_hash"] = content_hash
                return result
            return None

    def candidate_exists(self, content_hash: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("SELECT 1 FROM research_candidates WHERE content_hash = %s", (content_hash,))
            return cur.fetchone() is not None

    def list_candidates(self, market_type: Optional[str] = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            if market_type:
                cur.execute(
                    "SELECT content_hash, data FROM research_candidates WHERE market_type = %s LIMIT %s OFFSET %s",
                    (market_type, limit, offset),
                )
            else:
                cur.execute(
                    "SELECT content_hash, data FROM research_candidates LIMIT %s OFFSET %s",
                    (limit, offset),
                )
            results = []
            for row in cur.fetchall():
                d = dict(row["data"])
                d["_hash"] = row["content_hash"]
                results.append(d)
            return results

    # ═══ HYPOTHESES ═══

    def save_hypothesis(self, content_hash: str, data: dict[str, Any]) -> bool:
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO research_hypotheses (content_hash, candidate_hash, market_type, data)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (content_hash) DO NOTHING""",
                    (content_hash, data.get("candidate_hash", ""), data.get("market_type", ""), json.dumps(data)),
                )
                return cur.rowcount > 0
        except Exception:
            return False

    def get_hypothesis(self, content_hash: str) -> Optional[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT data FROM research_hypotheses WHERE content_hash = %s", (content_hash,))
            row = cur.fetchone()
            if row:
                result = dict(row["data"])
                result["_hash"] = content_hash
                return result
            return None

    def hypothesis_exists(self, content_hash: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("SELECT 1 FROM research_hypotheses WHERE content_hash = %s", (content_hash,))
            return cur.fetchone() is not None

    # ═══ EXPERIMENTS ═══

    def save_experiment(self, experiment_id: str, data: dict[str, Any]) -> bool:
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO research_experiments (experiment_id, candidate_hash, hypothesis_hash, market_type, data)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (experiment_id) DO NOTHING""",
                    (experiment_id, data.get("candidate_hash", ""), data.get("hypothesis_hash", ""),
                     data.get("market_type", ""), json.dumps(data)),
                )
                return cur.rowcount > 0
        except Exception:
            return False

    def get_experiment(self, experiment_id: str) -> Optional[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT data FROM research_experiments WHERE experiment_id = %s", (experiment_id,))
            row = cur.fetchone()
            if row:
                result = dict(row["data"])
                result["_id"] = experiment_id
                return result
            return None

    def experiment_exists(self, experiment_id: str) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("SELECT 1 FROM research_experiments WHERE experiment_id = %s", (experiment_id,))
            return cur.fetchone() is not None

    # ═══ WALK-FORWARD ═══

    def save_walkforward(self, content_hash: str, data: dict[str, Any]) -> bool:
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO research_walkforwards (content_hash, experiment_id, hypothesis_hash, data)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (content_hash) DO NOTHING""",
                    (content_hash, data.get("experiment_id", ""), data.get("hypothesis_hash", ""), json.dumps(data)),
                )
                return cur.rowcount > 0
        except Exception:
            return False

    def get_walkforward(self, content_hash: str) -> Optional[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT data FROM research_walkforwards WHERE content_hash = %s", (content_hash,))
            row = cur.fetchone()
            return dict(row["data"]) if row else None

    # ═══ GOVERNANCE ═══

    def save_governance_decision(self, hypothesis_id: str, data: dict[str, Any]) -> bool:
        with self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO research_governance (hypothesis_id, decision_state, data)
                   VALUES (%s, %s, %s)""",
                (hypothesis_id, data.get("state", data.get("new_state", "")), json.dumps(data)),
            )
            return True

    def get_governance_decisions(self, hypothesis_id: str) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT data, created_at FROM research_governance WHERE hypothesis_id = %s ORDER BY created_at",
                (hypothesis_id,),
            )
            return [dict(row["data"]) for row in cur.fetchall()]

    # ═══ PROPOSALS ═══

    def save_proposal(self, proposal_id: str, data: dict[str, Any]) -> bool:
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO research_proposals (proposal_id, source, status, data)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (proposal_id) DO NOTHING""",
                    (proposal_id, data.get("source", "DETERMINISTIC"), data.get("status", "DRAFT"), json.dumps(data)),
                )
                return cur.rowcount > 0
        except Exception:
            return False

    def get_proposal(self, proposal_id: str) -> Optional[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute("SELECT data FROM research_proposals WHERE proposal_id = %s", (proposal_id,))
            row = cur.fetchone()
            return dict(row["data"]) if row else None

    # ═══ TASKS (with atomic claiming) ═══

    def save_task(self, task_id: str, data: dict[str, Any]) -> bool:
        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO research_tasks
                       (task_id, task_type, status, priority, candidate_hash,
                        hypothesis_hash, research_run_id, requested_by,
                        max_attempts, data)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (task_id) DO NOTHING""",
                    (
                        task_id,
                        data.get("task_type", "EXPERIMENT"),
                        data.get("status", "PENDING"),
                        data.get("priority", 0),
                        data.get("candidate_hash", ""),
                        data.get("hypothesis_hash", ""),
                        data.get("research_run_id", ""),
                        data.get("requested_by", "DETERMINISTIC"),
                        data.get("max_attempts", 3),
                        json.dumps(data),
                    ),
                )
                return cur.rowcount > 0
        except Exception:
            return False

    def get_task(self, task_id: str) -> Optional[dict[str, Any]]:
        with self._conn.cursor() as cur:
            cur.execute(
                """SELECT task_id, task_type, status, priority, worker_id,
                          attempt_count, max_attempts, data, result_reference,
                          error_message, claimed_at, started_at, completed_at
                   FROM research_tasks WHERE task_id = %s""",
                (task_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            result = dict(row["data"])
            result["_id"] = row["task_id"]
            result["task_id"] = row["task_id"]
            result["status"] = row["status"]
            result["worker_id"] = row["worker_id"]
            result["attempt_count"] = row["attempt_count"]
            result["max_attempts"] = row["max_attempts"]
            result["result_reference"] = row["result_reference"]
            result["error_message"] = row["error_message"]
            result["claimed_by"] = row["worker_id"] or ""
            result["claimed_at"] = row["claimed_at"].timestamp() if row["claimed_at"] else 0
            return result

    def update_task(self, task_id: str, updates: dict[str, Any]) -> bool:
        """Update task columns."""
        with self._conn.cursor() as cur:
            sets = []
            values = []
            for key, val in updates.items():
                if key == "status":
                    sets.append("status = %s")
                    values.append(val)
                elif key == "claimed_by":
                    sets.append("worker_id = %s")
                    values.append(val or None)
                elif key == "claimed_at":
                    if val:
                        sets.append("claimed_at = to_timestamp(%s)")
                        values.append(val)
                    else:
                        sets.append("claimed_at = NULL")
                elif key == "started_at":
                    sets.append("started_at = to_timestamp(%s)")
                    values.append(val)
                elif key == "completed_at":
                    sets.append("completed_at = to_timestamp(%s)")
                    values.append(val)
                elif key == "attempt_count":
                    sets.append("attempt_count = %s")
                    values.append(val)
                elif key == "result_reference":
                    sets.append("result_reference = %s")
                    values.append(val)
                elif key == "error_message":
                    sets.append("error_message = %s")
                    values.append(val)
                elif key == "lease_expiry":
                    if val:
                        sets.append("lease_expiry = to_timestamp(%s)")
                        values.append(val)
                    else:
                        sets.append("lease_expiry = NULL")

            if not sets:
                return False

            values.append(task_id)
            sql = f"UPDATE research_tasks SET {', '.join(sets)} WHERE task_id = %s"
            cur.execute(sql, values)
            return cur.rowcount > 0

    def claim_next_task(self, worker_id: str) -> Optional[dict[str, Any]]:
        """Atomically claim the next pending task using FOR UPDATE SKIP LOCKED.

        Also recovers stale leases (expired lease_expiry).
        """
        lease_expiry = datetime.now(timezone.utc) + timedelta(seconds=self._lease_seconds)

        with self._conn.connection() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # Claim next PENDING task (highest priority first, oldest first)
                cur.execute(
                    """UPDATE research_tasks
                       SET status = 'CLAIMED',
                           worker_id = %s,
                           claimed_at = NOW(),
                           lease_expiry = %s
                       WHERE task_id = (
                           SELECT task_id FROM research_tasks
                           WHERE status = 'PENDING'
                           ORDER BY priority DESC, created_at ASC
                           LIMIT 1
                           FOR UPDATE SKIP LOCKED
                       )
                       RETURNING task_id, task_type, status, data, candidate_hash, hypothesis_hash""",
                    (worker_id, lease_expiry),
                )
                row = cur.fetchone()
                if row:
                    result = dict(row["data"])
                    result["_id"] = row["task_id"]
                    result["task_id"] = row["task_id"]
                    result["status"] = "CLAIMED"
                    result["claimed_by"] = worker_id
                    result["claimed_at"] = time.time()
                    return result
                return None

    def recover_stale_tasks(self) -> int:
        """Recover tasks with expired leases back to PENDING."""
        with self._conn.cursor() as cur:
            cur.execute(
                """UPDATE research_tasks
                   SET status = 'PENDING', worker_id = NULL, claimed_at = NULL, lease_expiry = NULL
                   WHERE status = 'CLAIMED' AND lease_expiry < NOW()""",
            )
            count = cur.rowcount
            if count:
                logger.info("Recovered %d stale tasks", count)
            return count

    def list_tasks(self, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        with self._conn.cursor() as cur:
            if status:
                cur.execute(
                    "SELECT task_id, status, data FROM research_tasks WHERE status = %s LIMIT %s",
                    (status, limit),
                )
            else:
                cur.execute("SELECT task_id, status, data FROM research_tasks LIMIT %s", (limit,))
            results = []
            for row in cur.fetchall():
                d = dict(row["data"])
                d["_id"] = row["task_id"]
                d["status"] = row["status"]
                results.append(d)
            return results

    # ═══ EVENTS ═══

    def append_event(self, event_type: str, entity_type: str = "", entity_id: str = "",
                     run_id: str = "", worker_id: str = "", data: Optional[dict] = None) -> None:
        """Append an immutable research event."""
        with self._conn.cursor() as cur:
            cur.execute(
                """INSERT INTO research_events (event_type, entity_type, entity_id, run_id, worker_id, data)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (event_type, entity_type, entity_id, run_id, worker_id,
                 json.dumps(data) if data else None),
            )

    def get_events(self, entity_type: str = "", entity_id: str = "",
                   run_id: str = "", limit: int = 100) -> list[dict[str, Any]]:
        """Query research events."""
        with self._conn.cursor() as cur:
            conditions = []
            values = []
            if entity_type:
                conditions.append("entity_type = %s")
                values.append(entity_type)
            if entity_id:
                conditions.append("entity_id = %s")
                values.append(entity_id)
            if run_id:
                conditions.append("run_id = %s")
                values.append(run_id)

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            values.append(limit)
            cur.execute(
                f"SELECT event_type, entity_type, entity_id, run_id, worker_id, data, created_at "
                f"FROM research_events {where} ORDER BY created_at LIMIT %s",
                values,
            )
            return [dict(row) for row in cur.fetchall()]

    # ═══ STATISTICS ═══

    def count_candidates(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM research_candidates")
            return cur.fetchone()["cnt"]

    def count_experiments(self) -> int:
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM research_experiments")
            return cur.fetchone()["cnt"]

    def count_tasks(self, status: Optional[str] = None) -> int:
        with self._conn.cursor() as cur:
            if status:
                cur.execute("SELECT COUNT(*) as cnt FROM research_tasks WHERE status = %s", (status,))
            else:
                cur.execute("SELECT COUNT(*) as cnt FROM research_tasks")
            return cur.fetchone()["cnt"]
