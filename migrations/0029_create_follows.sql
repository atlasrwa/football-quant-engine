-- Migration 0029: Create follows table
-- Phase 3.3: Social follow relationships
-- Ownership: CLASS A (User-owned — follower manages)
--
-- Constraints:
--   - user cannot follow themselves
--   - duplicate follows impossible (PK)
--   - deleting a follow is supported (unfollow)

BEGIN;

CREATE TABLE IF NOT EXISTS follows (
    follower_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    followed_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- PK prevents duplicates
    PRIMARY KEY (follower_id, followed_id),
    -- Self-follow prevention
    CHECK (follower_id != followed_id)
);

-- "Who follows user X?" (follower count, follower list)
CREATE INDEX idx_follows_followed ON follows (followed_id, created_at DESC);
-- "Who does user X follow?" (following list)
CREATE INDEX idx_follows_follower ON follows (follower_id, created_at DESC);

COMMIT;
