# Batch 8 — Production-Grade Research Persistence & Orchestrator

## Architecture

```
RAW DATA (FootyStats)
    ↓
DATA NORMALIZATION
    ↓
FEATURES (existing)
    ↓
CANDIDATE DISCOVERY (existing)
    ↓
HYPOTHESIS (existing)
    ↓
┌────────────────────────────────┐
│  RESEARCH ORCHESTRATOR         │  ← Batch 8
│  plan → queue → execute        │
│  resume → budget → events      │
└────────────┬───────────────────┘
             ↓
┌────────────────────────────────┐
│  PERSISTENT QUEUE              │  ← Batch 8
│  PostgreSQL + FOR UPDATE       │
│  SKIP LOCKED                   │
│  Worker leases + recovery      │
└────────────┬───────────────────┘
             ↓
EXPERIMENT → WALK-FORWARD → FDR → GOVERNANCE
             ↓
┌────────────────────────────────┐
│  POSTGRESQL PERSISTENCE        │  ← Batch 8
│  research_runs                 │
│  research_candidates           │
│  research_experiments          │
│  research_tasks                │
│  research_events               │
└────────────────────────────────┘
             ↓
RESEARCH MEMORY (queries persistence)
```

## PostgreSQL Schema

Tables:
- `research_runs` — run lifecycle (PK: run_id TEXT)
- `research_candidates` — unique candidates (PK: content_hash TEXT)
- `research_hypotheses` — unique hypotheses (PK: content_hash TEXT)
- `research_experiments` — experiment results (PK: experiment_id TEXT)
- `research_walkforwards` — WF results (PK: content_hash TEXT)
- `research_governance` — governance decisions (serial PK, FK hypothesis_id)
- `research_proposals` — AI/deterministic proposals (PK: proposal_id TEXT)
- `research_tasks` — queue with leases (PK: task_id TEXT)
- `research_events` — immutable audit trail (serial PK)
- `research_migrations` — applied migration tracking

Key constraints: UNIQUE on all content hashes, NOT NULL on required fields, indexes on status/priority/lease_expiry.

## Migration Strategy

- Forward-only versioned SQL files in `src/research/persistence/migrations/`
- `Migrator` class applies pending migrations in order
- Idempotent: uses `IF NOT EXISTS` and `ON CONFLICT DO NOTHING`
- Tracked in `research_migrations` table
- Safe to run multiple times

## Transaction Model

- Connection pooling via `psycopg2.pool.ThreadedConnectionPool`
- Context managers: `connection()`, `cursor()`, `transaction()`
- Auto-commit on success, auto-rollback on exception
- Task claiming uses single atomic UPDATE...RETURNING

## Persistent Queue

- Tasks stored in `research_tasks` table with status column
- Atomic claiming: `SELECT FOR UPDATE SKIP LOCKED` ensures no double-claims
- Priority ordering: highest priority first, then oldest
- Worker lease expiry: claimed tasks have `lease_expiry` timestamp
- Stale recovery: `recover_stale_tasks()` returns expired leases to PENDING

## Worker Leases

- `lease_expiry` set to NOW() + `lease_seconds` (default 300s) on claim
- If worker dies, lease expires and task becomes claimable
- `recover_stale_tasks()` scans for expired leases and resets them
- Tested: worker A claims → A dies → lease expires → B claims successfully

## Crash Recovery

- Tasks in CLAIMED state with expired leases → reset to PENDING
- RETRYABLE tasks → `retry()` moves back to PENDING
- Completed experiments persist through restarts
- Orchestrator resumes: loads run state, claims remaining tasks, skips completed

## Idempotency

- `ON CONFLICT DO NOTHING` on all primary keys
- Same task_id submitted twice → second returns `is_new=False`
- Same experiment_id saved twice → second returns False
- Orchestrator checks memory before queueing: `should_skip_experiment()`
- Crash after result persistence but before task completion → stale recovery → re-claim → idempotent save

## Research Orchestrator

- `plan(run_id, tasks)` — submits tasks, skips already-done experiments
- `execute(run_id, executor, max_tasks)` — claims and executes tasks
- `resume(run_id, executor)` — recovers stale, retries failed, continues
- `cancel(run_id)` — marks run as cancelled
- Run lifecycle: CREATED → PLANNED → RUNNING → COMPLETED/FAILED/PAUSED/BUDGET_EXHAUSTED/CANCELLED
- Invalid state transitions rejected

## Run Lifecycle

```
CREATED → PLANNED → RUNNING → COMPLETED (all tasks done)
                            → PAUSED (max_tasks hit, work remaining)
                            → BUDGET_EXHAUSTED (budget limit reached)
                            → FAILED (unrecoverable error)
         CANCELLED (at any non-terminal state)
```

## Research Identity

All identity based on content hashes:
- Candidates: SHA-256 of (market, features, conditions, direction, operator)
- Tasks: SHA-256 of (task_type, candidate_hash, hypothesis_hash, payload)
- Experiments: deterministic from ExperimentConfig
- Runs: deterministic from ResearchRunIdentity

Never in hashes: timestamps, database IDs, process IDs.

## Research Event Trail

Append-only `research_events` table:
- RUN_PLANNED, RUN_STARTED, RUN_FINISHED, RUN_BUDGET_EXHAUSTED, RUN_CANCELLED
- TASK_CLAIMED, TASK_STARTED, TASK_COMPLETED, TASK_FAILED

Events indexed by entity_type/entity_id and run_id. Cannot be edited.

## Concurrency

- Tested: 10 concurrent workers claiming 100 tasks — all unique, no double claims
- PostgreSQL `FOR UPDATE SKIP LOCKED` ensures correctness
- Python threading for within-process concurrency
- Cross-process safety via database transactions

## Budget Enforcement

Orchestrator checks `ResearchBudget.is_exhausted` before each task claim.
Budget tracks: tasks_used, experiments_used, elapsed_seconds.
Exhaustion produces BUDGET_EXHAUSTED status with clear reason.

## Security

- Database credentials from `RESEARCH_DATABASE_URL` env var
- Never in: research objects, content hashes, events, logs, task payloads, AI context
- Connection string redacted in any logging
- Tested: credentials absent from stored data

## Performance (PostgreSQL)

| Operation | Throughput |
|-----------|-----------|
| Candidate inserts | ~400/s |
| Task inserts | ~400/s |
| Experiment inserts | ~500/s |
| Concurrent claims (5 workers) | ~50 claims/s |

## Configuration

Environment variables:
- `RESEARCH_DATABASE_URL` — PostgreSQL connection string
- `RESEARCH_DB_POOL_MIN` — min pool connections (default 1)
- `RESEARCH_DB_POOL_MAX` — max pool connections (default 5)

## Known Limitations

1. No distributed queue (single PostgreSQL instance)
2. No async support (synchronous operations only)
3. No automatic stale recovery daemon (manual/periodic call)
4. No real LLM provider (MockProvider only)
5. No public API/dashboard
6. No paper trading or live trading
7. No automatic production promotion
8. Single-node operation (no Kubernetes/clustering)
