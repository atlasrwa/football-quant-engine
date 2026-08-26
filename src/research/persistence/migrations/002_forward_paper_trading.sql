-- Batch 10: Forward Research & Paper Trading Schema
-- Migration: 002_forward_paper_trading.sql

-- ═══════════════════════════════════════════════════════════════
-- FUTURE FIXTURES
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS future_fixtures (
    fixture_id VARCHAR(16) PRIMARY KEY,
    source_fixture_id INTEGER NOT NULL,
    home_team_id INTEGER NOT NULL,
    away_team_id INTEGER NOT NULL,
    home_team_name VARCHAR(200) DEFAULT '',
    away_team_name VARCHAR(200) DEFAULT '',
    competition_id INTEGER DEFAULT 0,
    season_id INTEGER DEFAULT 0,
    kickoff_timestamp BIGINT NOT NULL,
    source VARCHAR(50) NOT NULL DEFAULT '',
    retrieved_at DOUBLE PRECISION DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'SCHEDULED',
    content_hash VARCHAR(16) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fixtures_kickoff ON future_fixtures(kickoff_timestamp);
CREATE INDEX IF NOT EXISTS idx_fixtures_status ON future_fixtures(status);
CREATE INDEX IF NOT EXISTS idx_fixtures_competition ON future_fixtures(competition_id);
CREATE INDEX IF NOT EXISTS idx_fixtures_source ON future_fixtures(source, source_fixture_id);

-- ═══════════════════════════════════════════════════════════════
-- PRE-MATCH FEATURE SNAPSHOTS
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS prematch_snapshots (
    snapshot_id VARCHAR(16) PRIMARY KEY,
    fixture_id VARCHAR(16) NOT NULL REFERENCES future_fixtures(fixture_id),
    prediction_timestamp DOUBLE PRECISION NOT NULL,
    kickoff_timestamp DOUBLE PRECISION NOT NULL,
    features JSONB NOT NULL DEFAULT '{}',
    feature_provenance JSONB DEFAULT '[]',
    source_dataset_id VARCHAR(64) DEFAULT '',
    source_data_version VARCHAR(64) DEFAULT '',
    hypothesis_id VARCHAR(64) DEFAULT '',
    model_id VARCHAR(64) DEFAULT '',
    research_run_id VARCHAR(64) DEFAULT '',
    content_hash VARCHAR(16) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_snapshots_fixture ON prematch_snapshots(fixture_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_prediction_ts ON prematch_snapshots(prediction_timestamp);
CREATE INDEX IF NOT EXISTS idx_snapshots_hypothesis ON prematch_snapshots(hypothesis_id);

-- ═══════════════════════════════════════════════════════════════
-- ODDS SNAPSHOTS
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS odds_snapshots (
    odds_snapshot_id VARCHAR(16) PRIMARY KEY,
    fixture_id VARCHAR(16) NOT NULL REFERENCES future_fixtures(fixture_id),
    market VARCHAR(50) NOT NULL,
    selection VARCHAR(20) NOT NULL,
    line DOUBLE PRECISION NOT NULL DEFAULT 0,
    decimal_odds DOUBLE PRECISION NOT NULL,
    source VARCHAR(50) DEFAULT '',
    bookmaker VARCHAR(100) DEFAULT '',
    snapshot_timestamp DOUBLE PRECISION NOT NULL,
    source_timestamp DOUBLE PRECISION,
    retrieval_timestamp DOUBLE PRECISION DEFAULT 0,
    odds_type VARCHAR(20) NOT NULL DEFAULT 'PRE_MATCH',
    content_hash VARCHAR(16) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_odds_fixture ON odds_snapshots(fixture_id);
CREATE INDEX IF NOT EXISTS idx_odds_market ON odds_snapshots(market);
CREATE INDEX IF NOT EXISTS idx_odds_timestamp ON odds_snapshots(snapshot_timestamp);
CREATE INDEX IF NOT EXISTS idx_odds_type ON odds_snapshots(odds_type);
CREATE INDEX IF NOT EXISTS idx_odds_fixture_market ON odds_snapshots(fixture_id, market);

-- ═══════════════════════════════════════════════════════════════
-- PAPER TRADES
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS paper_trades (
    trade_id VARCHAR(16) PRIMARY KEY,
    strategy_id VARCHAR(64) NOT NULL DEFAULT '',
    hypothesis_id VARCHAR(64) NOT NULL DEFAULT '',
    research_run_id VARCHAR(64) DEFAULT '',
    fixture_id VARCHAR(16) NOT NULL REFERENCES future_fixtures(fixture_id),
    market VARCHAR(50) NOT NULL,
    selection VARCHAR(20) NOT NULL,
    line DOUBLE PRECISION NOT NULL DEFAULT 0,
    model_probability DOUBLE PRECISION NOT NULL,
    market_probability DOUBLE PRECISION NOT NULL,
    odds_at_prediction DOUBLE PRECISION NOT NULL,
    edge DOUBLE PRECISION NOT NULL DEFAULT 0,
    expected_value DOUBLE PRECISION NOT NULL DEFAULT 0,
    stake DOUBLE PRECISION NOT NULL DEFAULT 0,
    bankroll_before DOUBLE PRECISION DEFAULT 0,
    prediction_timestamp DOUBLE PRECISION NOT NULL,
    kickoff_timestamp DOUBLE PRECISION NOT NULL,
    snapshot_id VARCHAR(16) DEFAULT '',
    odds_snapshot_id VARCHAR(16) DEFAULT '',
    status VARCHAR(30) NOT NULL DEFAULT 'GENERATED',
    closing_odds DOUBLE PRECISION,
    clv DOUBLE PRECISION,
    settlement_result VARCHAR(10),
    settlement_timestamp DOUBLE PRECISION,
    profit_loss DOUBLE PRECISION,
    content_hash VARCHAR(16) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_trades_status ON paper_trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_strategy ON paper_trades(strategy_id);
CREATE INDEX IF NOT EXISTS idx_trades_hypothesis ON paper_trades(hypothesis_id);
CREATE INDEX IF NOT EXISTS idx_trades_fixture ON paper_trades(fixture_id);
CREATE INDEX IF NOT EXISTS idx_trades_market ON paper_trades(market);
CREATE INDEX IF NOT EXISTS idx_trades_prediction_ts ON paper_trades(prediction_timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_settlement_ts ON paper_trades(settlement_timestamp);
CREATE INDEX IF NOT EXISTS idx_trades_kickoff ON paper_trades(kickoff_timestamp);

-- ═══════════════════════════════════════════════════════════════
-- CLV OBSERVATIONS
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS clv_observations (
    trade_id VARCHAR(16) PRIMARY KEY REFERENCES paper_trades(trade_id),
    prediction_odds DOUBLE PRECISION NOT NULL,
    closing_odds DOUBLE PRECISION NOT NULL,
    clv DOUBLE PRECISION NOT NULL,
    prediction_implied_prob DOUBLE PRECISION NOT NULL,
    closing_implied_prob DOUBLE PRECISION NOT NULL,
    is_positive BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- ═══════════════════════════════════════════════════════════════
-- FORWARD EVENTS (append-only audit trail)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS forward_events (
    id BIGSERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    entity_id VARCHAR(64) DEFAULT '',
    fixture_id VARCHAR(16) DEFAULT '',
    timestamp DOUBLE PRECISION NOT NULL,
    data JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_forward_events_type ON forward_events(event_type);
CREATE INDEX IF NOT EXISTS idx_forward_events_fixture ON forward_events(fixture_id);
CREATE INDEX IF NOT EXISTS idx_forward_events_timestamp ON forward_events(timestamp);
