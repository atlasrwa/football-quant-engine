-- Migration 0012: Force RLS on tables even for the table owner
-- Without FORCE, the owner role bypasses all RLS policies.
-- Since fqe_app is both owner and application user, we must force.

BEGIN;

ALTER TABLE users FORCE ROW LEVEL SECURITY;
ALTER TABLE user_wallets FORCE ROW LEVEL SECURITY;
ALTER TABLE strategies FORCE ROW LEVEL SECURITY;
ALTER TABLE strategy_versions FORCE ROW LEVEL SECURITY;
ALTER TABLE strategy_forks FORCE ROW LEVEL SECURITY;
ALTER TABLE matches FORCE ROW LEVEL SECURITY;
ALTER TABLE event_log FORCE ROW LEVEL SECURITY;
ALTER TABLE idempotency_keys FORCE ROW LEVEL SECURITY;

COMMIT;
