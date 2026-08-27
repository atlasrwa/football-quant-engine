"""Integration tests for idempotency key mechanism."""

import hashlib
import json

import pytest
import asyncpg
from uuid import uuid4

from src.persistence.pg_idempotency_repository import PgIdempotencyRepository


pytestmark = pytest.mark.asyncio


def _hash_body(body: dict) -> str:
    """Compute SHA-256 of canonical JSON body."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


class TestIdempotencyFirstRequest:
    """Test storing the first occurrence of a request."""

    async def test_store_and_retrieve(self, db_conn, system_user_id):
        """First request stores successfully and can be retrieved."""
        repo = PgIdempotencyRepository(db_conn)
        key = "idem-key-001"
        body = {"name": "Test Strategy", "metric": "xC"}

        await repo.store(
            user_id=system_user_id,
            key=key,
            endpoint="POST /api/v1/strategies",
            http_method="POST",
            request_hash=_hash_body(body),
            response_status=201,
            response_body={"strategy_id": str(uuid4()), "version": 1},
        )

        result = await repo.get(system_user_id, key)
        assert result is not None
        assert result["response_status"] == 201
        assert "strategy_id" in result["response_body"]

    async def test_get_nonexistent_returns_none(self, db_conn, system_user_id):
        """Looking up a nonexistent key returns None."""
        repo = PgIdempotencyRepository(db_conn)
        result = await repo.get(system_user_id, "nonexistent-key")
        assert result is None


class TestIdempotencyDuplicate:
    """Test duplicate request detection."""

    async def test_exact_duplicate_rejected(self, db_conn, system_user_id):
        """Storing the same (user_id, key) twice raises UniqueViolation."""
        repo = PgIdempotencyRepository(db_conn)
        key = "dup-key-001"

        await repo.store(
            user_id=system_user_id,
            key=key,
            endpoint="POST /api/v1/strategies",
            http_method="POST",
            request_hash=_hash_body({"a": 1}),
            response_status=201,
            response_body={"ok": True},
        )

        with pytest.raises(asyncpg.UniqueViolationError):
            await repo.store(
                user_id=system_user_id,
                key=key,
                endpoint="POST /api/v1/strategies",
                http_method="POST",
                request_hash=_hash_body({"a": 1}),
                response_status=201,
                response_body={"ok": True},
            )

    async def test_same_key_different_user_allowed(self, db_conn):
        """Same idempotency key from different users does not conflict."""
        repo = PgIdempotencyRepository(db_conn)
        key = "shared-key-001"

        # Create two test users
        user1 = uuid4()
        user2 = uuid4()
        for uid, uname in [(user1, "idem_user1"), (user2, "idem_user2")]:
            await db_conn.execute(
                "INSERT INTO users (id, username, display_name, role, status) VALUES ($1, $2, $2, 'user', 'active')",
                uid, uname,
            )

        await repo.store(
            user_id=user1, key=key, endpoint="POST /test",
            http_method="POST", request_hash="a" * 64,
            response_status=201, response_body={},
        )
        # Same key, different user — should succeed
        await repo.store(
            user_id=user2, key=key, endpoint="POST /test",
            http_method="POST", request_hash="b" * 64,
            response_status=201, response_body={},
        )


class TestIdempotencyExpiration:
    """Test TTL behavior."""

    async def test_expired_key_not_returned(self, db_conn, system_user_id):
        """An expired key is treated as nonexistent."""
        repo = PgIdempotencyRepository(db_conn)
        key = "expired-key-001"

        # Insert with already-expired timestamp
        await db_conn.execute(
            """
            INSERT INTO idempotency_keys (user_id, idempotency_key, endpoint, http_method,
                                          request_hash, response_status, response_body, expires_at)
            VALUES ($1, $2, 'POST /test', 'POST', $3, 200, '{}', NOW() - INTERVAL '1 hour')
            """,
            system_user_id, key, "a" * 64,
        )

        # Should not be found (expired)
        result = await repo.get(system_user_id, key)
        assert result is None

    async def test_cleanup_removes_expired(self, db_conn, system_user_id):
        """cleanup_expired() removes only expired keys."""
        repo = PgIdempotencyRepository(db_conn)

        # Insert one expired and one valid
        await db_conn.execute(
            """
            INSERT INTO idempotency_keys (user_id, idempotency_key, endpoint, http_method,
                                          request_hash, response_status, response_body, expires_at)
            VALUES ($1, 'expired', 'POST /t', 'POST', $2, 200, '{}', NOW() - INTERVAL '1 hour'),
                   ($1, 'valid', 'POST /t', 'POST', $2, 200, '{}', NOW() + INTERVAL '23 hours')
            """,
            system_user_id, "b" * 64,
        )

        removed = await repo.cleanup_expired()
        assert removed >= 1

        # Valid key should still exist
        result = await repo.get(system_user_id, "valid")
        assert result is not None
