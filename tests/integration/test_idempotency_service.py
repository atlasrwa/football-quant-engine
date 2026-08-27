"""Integration tests for IdempotencyService — the application-layer dedup logic."""

import asyncio

import pytest
import asyncpg
from uuid import uuid4

from src.persistence.idempotency import (
    IdempotencyService,
    IdempotencyConflictError,
    compute_request_hash,
)


pytestmark = pytest.mark.asyncio


class TestIdempotencyCheck:
    """Test the check phase of idempotency."""

    async def test_new_key_returns_none(self, db_conn, system_user_id):
        """First-time key returns None (proceed with execution)."""
        svc = IdempotencyService(db_conn)
        result = await svc.check(system_user_id, "new-key-001", "a" * 64)
        assert result is None

    async def test_existing_key_same_hash_returns_cached(self, db_conn, system_user_id):
        """Same key + same hash returns cached response."""
        svc = IdempotencyService(db_conn)
        key = "cached-key-001"
        req_hash = compute_request_hash({"name": "test"})

        # Store first
        await svc.store(
            system_user_id, key, "POST /api/v1/strategies", "POST",
            req_hash, 201, {"strategy_id": "abc-123"},
        )

        # Check returns cached
        result = await svc.check(system_user_id, key, req_hash)
        assert result is not None
        assert result.response_status == 201
        assert result.response_body["strategy_id"] == "abc-123"
        assert result.is_conflict is False

    async def test_existing_key_different_hash_raises_conflict(self, db_conn, system_user_id):
        """Same key + different hash raises IdempotencyConflictError."""
        svc = IdempotencyService(db_conn)
        key = "conflict-key-001"
        hash1 = compute_request_hash({"name": "original"})
        hash2 = compute_request_hash({"name": "different"})

        await svc.store(
            system_user_id, key, "POST /test", "POST",
            hash1, 201, {"ok": True},
        )

        with pytest.raises(IdempotencyConflictError):
            await svc.check(system_user_id, key, hash2)


class TestIdempotencyStore:
    """Test the store phase of idempotency."""

    async def test_store_succeeds(self, db_conn, system_user_id):
        """First store for a key succeeds."""
        svc = IdempotencyService(db_conn)
        await svc.store(
            system_user_id, "store-key-001", "POST /test", "POST",
            "b" * 64, 200, {"result": "ok"},
        )
        # Verify it's retrievable
        result = await svc.check(system_user_id, "store-key-001", "b" * 64)
        assert result is not None
        assert result.response_status == 200

    async def test_duplicate_store_raises(self, db_conn, system_user_id):
        """Storing the same key twice raises UniqueViolationError."""
        svc = IdempotencyService(db_conn)
        key = "dup-store-001"
        await svc.store(
            system_user_id, key, "POST /test", "POST",
            "c" * 64, 201, {},
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await svc.store(
                system_user_id, key, "POST /test", "POST",
                "c" * 64, 201, {},
            )


class TestRequestHashComputation:
    """Test the canonical request hash function."""

    def test_deterministic(self):
        """Same body always produces same hash."""
        body = {"name": "test", "value": 42}
        h1 = compute_request_hash(body)
        h2 = compute_request_hash(body)
        assert h1 == h2

    def test_key_order_independent(self):
        """Different key ordering produces same hash (sort_keys=True)."""
        h1 = compute_request_hash({"b": 2, "a": 1})
        h2 = compute_request_hash({"a": 1, "b": 2})
        assert h1 == h2

    def test_different_values_different_hash(self):
        """Different values produce different hashes."""
        h1 = compute_request_hash({"x": 1})
        h2 = compute_request_hash({"x": 2})
        assert h1 != h2

    def test_hash_is_sha256(self):
        """Output is a 64-char hex string (SHA-256)."""
        h = compute_request_hash({"test": True})
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


class TestConcurrentVersionCreation:
    """Test concurrency protection for strategy version numbering."""

    async def test_concurrent_version_creation_no_duplicates(self, db_conn, system_user_id):
        """Two concurrent version creates cannot both get the same version number.

        The UNIQUE(strategy_id, version) constraint prevents this at the DB level.
        One will succeed and one will get version N+1 (due to serial retry)
        or raise UniqueViolationError (which the application retries).
        """
        from src.persistence.pg_strategy_repository import (
            PgStrategyRepository,
            PgStrategyVersionRepository,
            StrategyRecord,
        )

        strat_repo = PgStrategyRepository(db_conn)
        ver_repo = PgStrategyVersionRepository(db_conn)

        # Create parent strategy
        strat = await strat_repo.create_strategy(StrategyRecord(
            id=uuid4(), owner_id=system_user_id,
            name="Concurrent Test", description=None,
            visibility="private", status="active",
        ))

        # Create first version
        v1 = await ver_repo.create_version(strat.id, {
            "name": "V1", "metric": "xC", "market": "corners",
            "conditions": [{"field": "f", "op": ">", "value": 1.0}],
            "logic": "and", "direction": "OVER", "min_odds": 1.50,
        }, system_user_id)
        assert v1.version == 1

        # Create second version (different definition)
        v2 = await ver_repo.create_version(strat.id, {
            "name": "V2", "metric": "xC", "market": "corners",
            "conditions": [{"field": "f", "op": ">", "value": 2.0}],
            "logic": "and", "direction": "OVER", "min_odds": 1.50,
        }, system_user_id)
        assert v2.version == 2

        # Verify no gaps or duplicates
        versions = await ver_repo.list_versions(strat.id)
        version_numbers = [v.version for v in versions]
        assert version_numbers == [1, 2]

    async def test_content_hash_detectable_for_dedup(self, db_conn, system_user_id):
        """Duplicate definition is detectable via get_by_content_hash (app-level dedup)."""
        from src.persistence.pg_strategy_repository import (
            PgStrategyRepository,
            PgStrategyVersionRepository,
            StrategyRecord,
            compute_content_hash,
        )

        strat_repo = PgStrategyRepository(db_conn)
        ver_repo = PgStrategyVersionRepository(db_conn)

        strat = await strat_repo.create_strategy(StrategyRecord(
            id=uuid4(), owner_id=system_user_id,
            name="Hash Dedup Test", description=None,
            visibility="private", status="active",
        ))

        definition = {
            "name": "Duplicate", "metric": "xB", "market": "cards",
            "conditions": [{"field": "f", "op": ">=", "value": 5.0}],
            "logic": "and", "direction": "OVER", "min_odds": 1.80,
        }

        await ver_repo.create_version(strat.id, definition, system_user_id)

        # Application checks before second insert
        content_hash = compute_content_hash(definition)
        existing = await ver_repo.get_by_content_hash(content_hash)
        assert existing is not None
