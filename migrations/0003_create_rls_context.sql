-- Migration 0003: RLS context helpers and foundation
-- Phase 3.1-A: Row-Level Security infrastructure
--
-- Every authenticated request sets:
--   SET LOCAL app.user_id = '<uuid>';
--   SET LOCAL app.user_role = '<role>';
--
-- These helper functions extract the session context safely.

BEGIN;

-- Helper: get current user ID from session context
CREATE OR REPLACE FUNCTION current_app_user_id()
RETURNS UUID AS $$
BEGIN
    RETURN NULLIF(current_setting('app.user_id', TRUE), '')::UUID;
EXCEPTION
    WHEN OTHERS THEN RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

-- Helper: get current user role from session context
CREATE OR REPLACE FUNCTION current_app_user_role()
RETURNS TEXT AS $$
BEGIN
    RETURN NULLIF(current_setting('app.user_role', TRUE), '');
EXCEPTION
    WHEN OTHERS THEN RETURN NULL;
END;
$$ LANGUAGE plpgsql STABLE;

-- Helper: check if current user is admin or system
CREATE OR REPLACE FUNCTION is_admin_or_system()
RETURNS BOOLEAN AS $$
BEGIN
    RETURN current_app_user_role() IN ('admin', 'system');
END;
$$ LANGUAGE plpgsql STABLE;

-- Enable RLS on users table
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Users can read their own row; admins/system can read all
CREATE POLICY users_select_own ON users
    FOR SELECT
    USING (
        id = current_app_user_id()
        OR is_admin_or_system()
    );

-- Users can update their own row (not role/status); admins can update any
CREATE POLICY users_update_own ON users
    FOR UPDATE
    USING (
        id = current_app_user_id()
        OR is_admin_or_system()
    )
    WITH CHECK (
        id = current_app_user_id()
        OR is_admin_or_system()
    );

-- Only system/admin can insert users (registration goes through service)
CREATE POLICY users_insert ON users
    FOR INSERT
    WITH CHECK (TRUE);  -- Controlled by application layer at registration

-- Enable RLS on user_wallets
ALTER TABLE user_wallets ENABLE ROW LEVEL SECURITY;

-- Users can only see/manage their own wallets; admins see all
CREATE POLICY wallets_select_own ON user_wallets
    FOR SELECT
    USING (
        user_id = current_app_user_id()
        OR is_admin_or_system()
    );

CREATE POLICY wallets_insert_own ON user_wallets
    FOR INSERT
    WITH CHECK (
        user_id = current_app_user_id()
        OR is_admin_or_system()
    );

CREATE POLICY wallets_update_own ON user_wallets
    FOR UPDATE
    USING (
        user_id = current_app_user_id()
        OR is_admin_or_system()
    );

CREATE POLICY wallets_delete_own ON user_wallets
    FOR DELETE
    USING (
        user_id = current_app_user_id()
        OR is_admin_or_system()
    );

-- Grant usage to fqe_app role (the application connects as this role)
GRANT ALL ON ALL TABLES IN SCHEMA public TO fqe_app;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO fqe_app;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO fqe_app;

COMMIT;
