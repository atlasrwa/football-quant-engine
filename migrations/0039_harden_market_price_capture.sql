-- Migration 0039: Harden immutable market price capture and provenance
--
-- Adds immutable capture runs, quote-level provenance and deterministic identities,
-- strict temporal/type checks, and exact closing-line lookup indexes. Existing
-- historical rows are retained and receive legacy-stable identities.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE market_price_capture_runs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider            TEXT NOT NULL,
    source              TEXT NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL,
    completed_at        TIMESTAMPTZ NOT NULL,
    status              TEXT NOT NULL DEFAULT 'COMPLETED',
    request_id          TEXT,
    raw_payload_hash    TEXT,
    metadata            JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT mpcr_status_check
        CHECK (status IN ('COMPLETED', 'PARTIAL', 'FAILED')),
    CONSTRAINT mpcr_time_order_check
        CHECK (completed_at >= started_at),
    CONSTRAINT mpcr_raw_payload_hash_check
        CHECK (raw_payload_hash IS NULL OR raw_payload_hash ~ '^[0-9a-f]{64}$')
);

CREATE UNIQUE INDEX uq_mpcr_provider_source_request
    ON market_price_capture_runs (provider, source, request_id)
    WHERE request_id IS NOT NULL;
CREATE INDEX idx_mpcr_provider_started
    ON market_price_capture_runs (provider, source, started_at DESC);

-- Temporarily remove the append-only triggers so legacy rows can be backfilled
-- inside this migration. They are reinstalled before commit.
DROP TRIGGER IF EXISTS trg_mp_no_update ON market_prices;
DROP TRIGGER IF EXISTS trg_mp_no_delete ON market_prices;
-- The table already has FORCE RLS and no UPDATE policy. The migration runs as
-- owner, so temporarily remove FORCE while the transactional backfill runs.
ALTER TABLE market_prices NO FORCE ROW LEVEL SECURITY;

ALTER TABLE market_prices
    ADD COLUMN bookmaker TEXT,
    ADD COLUMN provider_source_time TIMESTAMPTZ,
    ADD COLUMN retrieved_at TIMESTAMPTZ,
    ADD COLUMN quote_status TEXT,
    ADD COLUMN kickoff_at TIMESTAMPTZ,
    ADD COLUMN raw_payload_hash TEXT,
    ADD COLUMN quote_hash TEXT,
    ADD COLUMN capture_run_id UUID REFERENCES market_price_capture_runs(id) ON DELETE RESTRICT,
    ADD COLUMN provider_quote_id TEXT,
    ADD COLUMN timestamp_semantics TEXT;

-- Existing rows predate capture provenance. Preserve each row and give it a
-- unique, stable legacy identity rather than deleting historical duplicates.
UPDATE market_prices
SET bookmaker = source,
    retrieved_at = observed_at,
    quote_status = 'ACTIVE',
    raw_payload_hash = CASE
        WHEN raw_payload IS NULL THEN NULL
        ELSE encode(digest(raw_payload::text, 'sha256'), 'hex')
    END,
    quote_hash = encode(digest('legacy-market-price:' || id::text, 'sha256'), 'hex'),
    timestamp_semantics = 'RETRIEVAL_TIME';

ALTER TABLE market_prices
    ALTER COLUMN bookmaker SET NOT NULL,
    ALTER COLUMN retrieved_at SET NOT NULL,
    ALTER COLUMN quote_status SET NOT NULL,
    ALTER COLUMN quote_status SET DEFAULT 'ACTIVE',
    ALTER COLUMN quote_hash SET NOT NULL,
    ALTER COLUMN timestamp_semantics SET NOT NULL,
    ALTER COLUMN timestamp_semantics SET DEFAULT 'RETRIEVAL_TIME',
    ADD CONSTRAINT mp_price_type_check
        CHECK (price_type IN ('OPENING', 'SNAPSHOT', 'ENTRY', 'CLOSING', 'LIVE')),
    ADD CONSTRAINT mp_quote_status_check
        CHECK (quote_status IN ('ACTIVE', 'SUSPENDED', 'CLOSED', 'UNAVAILABLE', 'UNKNOWN')),
    ADD CONSTRAINT mp_timestamp_semantics_check
        CHECK (timestamp_semantics IN (
            'PROVIDER_SOURCE_TIME', 'RETRIEVAL_TIME', 'EXACT_CLOSE',
            'LAST_BEFORE_KICKOFF', 'PROVIDER_ESTIMATED'
        )),
    ADD CONSTRAINT mp_retrieval_time_check
        CHECK (observed_at <= retrieved_at),
    ADD CONSTRAINT mp_provider_time_check
        CHECK (provider_source_time IS NULL OR provider_source_time <= retrieved_at),
    ADD CONSTRAINT mp_provider_semantics_check
        CHECK (timestamp_semantics <> 'PROVIDER_SOURCE_TIME' OR provider_source_time IS NOT NULL),
    ADD CONSTRAINT mp_kickoff_cutoff_check
        CHECK (
            kickoff_at IS NULL
            OR (price_type = 'LIVE' AND observed_at >= kickoff_at)
            OR (price_type <> 'LIVE' AND observed_at < kickoff_at)
        ),
    ADD CONSTRAINT mp_raw_payload_hash_check
        CHECK (raw_payload_hash IS NULL OR raw_payload_hash ~ '^[0-9a-f]{64}$'),
    ADD CONSTRAINT mp_quote_hash_check
        CHECK (quote_hash ~ '^[0-9a-f]{64}$');

CREATE UNIQUE INDEX uq_mp_quote_hash ON market_prices (quote_hash);
CREATE UNIQUE INDEX uq_mp_provider_quote_id
    ON market_prices (source, provider_quote_id)
    WHERE provider_quote_id IS NOT NULL;

-- Supports exact line/book/source lookup with a strict observed_at < cutoff.
CREATE INDEX idx_mp_exact_line_book_source_cutoff
    ON market_prices (
        match_id, market_type, selection, line, bookmaker, source,
        observed_at DESC, quote_hash DESC
    )
    INCLUDE (
        odds, price_type, quote_status, provider_source_time, retrieved_at,
        kickoff_at, capture_run_id, timestamp_semantics
    );
CREATE INDEX idx_mp_exact_active_cutoff
    ON market_prices (
        match_id, market_type, selection, line, bookmaker, source,
        observed_at DESC, quote_hash DESC
    )
    INCLUDE (odds, capture_run_id)
    WHERE quote_status = 'ACTIVE' AND price_type <> 'LIVE';

-- Byte-identical quote identity contract shared with src/domain/market.py.
-- Strings are length-prefixed; numeric values use PostgreSQL's network-order
-- binary representation; timestamps use Unix microseconds.
CREATE OR REPLACE FUNCTION market_price_hash_text(value TEXT)
RETURNS BYTEA AS $$
DECLARE
    encoded BYTEA;
BEGIN
    IF value IS NULL THEN
        RETURN int4send(-1);
    END IF;
    encoded := convert_to(value, 'UTF8');
    RETURN int4send(octet_length(encoded)) || encoded;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

CREATE OR REPLACE FUNCTION compute_market_price_quote_hash(
    p_match_id BIGINT,
    p_market_type TEXT,
    p_line DOUBLE PRECISION,
    p_selection TEXT,
    p_odds DOUBLE PRECISION,
    p_observed_at TIMESTAMPTZ,
    p_source TEXT,
    p_bookmaker TEXT,
    p_provider_source_time TIMESTAMPTZ,
    p_provider_quote_id TEXT
)
RETURNS TEXT AS $$
DECLARE
    payload BYTEA := convert_to('market-price-quote-v1', 'UTF8');
BEGIN
    payload := payload
        || int8send(p_match_id)
        || market_price_hash_text(p_market_type)
        || CASE WHEN p_line IS NULL THEN decode('00', 'hex')
                ELSE decode('01', 'hex') || float8send(p_line) END
        || market_price_hash_text(p_selection)
        || float8send(p_odds)
        || int8send((extract(epoch FROM p_observed_at) * 1000000)::BIGINT)
        || market_price_hash_text(p_source)
        || market_price_hash_text(p_bookmaker)
        || CASE WHEN p_provider_source_time IS NULL THEN decode('00', 'hex')
                ELSE decode('01', 'hex')
                     || int8send((extract(epoch FROM p_provider_source_time) * 1000000)::BIGINT) END
        || market_price_hash_text(p_provider_quote_id);
    RETURN encode(digest(payload, 'sha256'), 'hex');
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Keep old callers operational while ensuring every future row receives full
-- minimum provenance. The trigger always computes hashes, preventing callers
-- from supplying an alternate identity for the same quote.
CREATE OR REPLACE FUNCTION populate_market_price_capture_provenance()
RETURNS TRIGGER AS $$
BEGIN
    NEW.bookmaker := COALESCE(NULLIF(NEW.bookmaker, ''), NEW.source);
    NEW.retrieved_at := COALESCE(NEW.retrieved_at, NEW.observed_at);
    NEW.quote_status := COALESCE(NEW.quote_status, 'ACTIVE');
    NEW.timestamp_semantics := COALESCE(
        NEW.timestamp_semantics,
        CASE WHEN NEW.provider_source_time IS NULL
             THEN 'RETRIEVAL_TIME' ELSE 'PROVIDER_SOURCE_TIME' END
    );
    IF NEW.raw_payload_hash IS NULL AND NEW.raw_payload IS NOT NULL THEN
        NEW.raw_payload_hash := encode(digest(NEW.raw_payload::text, 'sha256'), 'hex');
    END IF;
    NEW.quote_hash := compute_market_price_quote_hash(
        NEW.match_id, NEW.market_type, NEW.line, NEW.selection, NEW.odds,
        NEW.observed_at, NEW.source, NEW.bookmaker, NEW.provider_source_time,
        NEW.provider_quote_id
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_mp_capture_provenance
    BEFORE INSERT ON market_prices
    FOR EACH ROW EXECUTE FUNCTION populate_market_price_capture_provenance();

-- A terminal run's quote membership is fixed by the transaction that creates
-- it. This permits atomic run+batch insertion and rejects later attachments.
CREATE OR REPLACE FUNCTION enforce_market_price_capture_run_membership()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.capture_run_id IS NOT NULL AND NOT EXISTS (
        SELECT 1
        FROM market_price_capture_runs run
        WHERE run.id = NEW.capture_run_id
          AND run.xmin::text::BIGINT = pg_current_xact_id()::text::BIGINT
    ) THEN
        RAISE EXCEPTION 'capture run % is not new in this transaction', NEW.capture_run_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_mp_capture_run_membership
    BEFORE INSERT ON market_prices
    FOR EACH ROW EXECUTE FUNCTION enforce_market_price_capture_run_membership();

-- Reinstall append-only protections for both quote rows and capture runs.
CREATE TRIGGER trg_mp_no_update
    BEFORE UPDATE ON market_prices
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();
CREATE TRIGGER trg_mp_no_delete
    BEFORE DELETE ON market_prices
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();
CREATE TRIGGER trg_mpcr_no_update
    BEFORE UPDATE ON market_price_capture_runs
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();
CREATE TRIGGER trg_mpcr_no_delete
    BEFORE DELETE ON market_price_capture_runs
    FOR EACH ROW EXECUTE FUNCTION prevent_modification();

-- Restore the original forced-RLS posture after the owner-only backfill.
ALTER TABLE market_prices FORCE ROW LEVEL SECURITY;
ALTER TABLE market_price_capture_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE market_price_capture_runs FORCE ROW LEVEL SECURITY;
CREATE POLICY mpcr_select_all ON market_price_capture_runs
    FOR SELECT USING (TRUE);
CREATE POLICY mpcr_insert_system ON market_price_capture_runs
    FOR INSERT WITH CHECK (is_admin_or_system());

COMMIT;
