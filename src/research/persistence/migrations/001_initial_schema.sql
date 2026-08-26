-- Migration 001: Initial research schema
-- Idempotent: uses IF NOT EXISTS

CREATE TABLE IF NOT EXISTS research_runs (
    run_id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'CREATED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS research_candidates (
    content_hash TEXT PRIMARY KEY,
    market_type TEXT,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_candidates_market ON research_candidates(market_type);

CREATE TABLE IF NOT EXISTS research_hypotheses (
    content_hash TEXT PRIMARY KEY,
    candidate_hash TEXT,
    market_type TEXT,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_hypotheses_candidate ON research_hypotheses(candidate_hash);

CREATE TABLE IF NOT EXISTS research_experiments (
    experiment_id TEXT PRIMARY KEY,
    candidate_hash TEXT,
    hypothesis_hash TEXT,
    market_type TEXT,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_experiments_candidate ON research_experiments(candidate_hash);
CREATE INDEX IF NOT EXISTS idx_experiments_hypothesis ON research_experiments(hypothesis_hash);

CREATE TABLE IF NOT EXISTS research_walkforwards (
    content_hash TEXT PRIMARY KEY,
    experiment_id TEXT,
    hypothesis_hash TEXT,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS research_governance (
    id SERIAL PRIMARY KEY,
    hypothesis_id TEXT NOT NULL,
    decision_state TEXT NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_governance_hypothesis ON research_governance(hypothesis_id);

CREATE TABLE IF NOT EXISTS research_proposals (
    proposal_id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'DETERMINISTIC',
    status TEXT NOT NULL DEFAULT 'DRAFT',
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS research_tasks (
    task_id TEXT PRIMARY KEY,
    task_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    priority INTEGER NOT NULL DEFAULT 0,
    candidate_hash TEXT,
    hypothesis_hash TEXT,
    research_run_id TEXT,
    requested_by TEXT NOT NULL DEFAULT 'DETERMINISTIC',
    worker_id TEXT,
    lease_expiry TIMESTAMPTZ,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    data JSONB NOT NULL,
    result_reference TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    claimed_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_tasks_status ON research_tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_run ON research_tasks(research_run_id);
CREATE INDEX IF NOT EXISTS idx_tasks_lease ON research_tasks(status, lease_expiry) WHERE status = 'CLAIMED';
CREATE INDEX IF NOT EXISTS idx_tasks_pending ON research_tasks(priority DESC, created_at ASC) WHERE status = 'PENDING';

CREATE TABLE IF NOT EXISTS research_events (
    id SERIAL PRIMARY KEY,
    event_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    run_id TEXT,
    worker_id TEXT,
    data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_events_entity ON research_events(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_events_run ON research_events(run_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON research_events(event_type);

-- Migration tracking table
CREATE TABLE IF NOT EXISTS research_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Record this migration
INSERT INTO research_migrations (version, name)
VALUES (1, '001_initial_schema')
ON CONFLICT (version) DO NOTHING;
