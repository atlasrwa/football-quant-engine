"""Integration tests for event_log immutability and audit trail."""

import pytest
import asyncpg
from uuid import uuid4

from src.persistence.pg_event_repository import PgEventLogRepository
from src.persistence.repositories import EventRecord


pytestmark = pytest.mark.asyncio


class TestEventLogAppend:
    """Test append operations on the event log."""

    async def test_append_event(self, db_conn):
        """Basic event insertion succeeds and returns an ID."""
        repo = PgEventLogRepository(db_conn)
        event = EventRecord(
            event_type="USER_REGISTERED",
            aggregate_type="user",
            aggregate_id=str(uuid4()),
            actor_type="system",
        )
        event_id = await repo.append(event)
        assert event_id > 0

    async def test_append_with_payload(self, db_conn):
        """Event with JSONB payload is stored correctly."""
        repo = PgEventLogRepository(db_conn)
        aggregate_id = str(uuid4())
        event = EventRecord(
            event_type="STRATEGY_CREATED",
            aggregate_type="strategy",
            aggregate_id=aggregate_id,
            actor_type="user",
            actor_id=uuid4(),
            payload={"name": "Test Strategy", "metric": "xC"},
            correlation_id=uuid4(),
        )
        event_id = await repo.append(event)

        # Retrieve and verify
        events = await repo.get_by_aggregate("strategy", aggregate_id)
        assert len(events) == 1
        assert events[0]["event_type"] == "STRATEGY_CREATED"
        payload = events[0]["payload"]
        if isinstance(payload, str):
            import json as _json
            payload = _json.loads(payload)
        assert payload["name"] == "Test Strategy"

    async def test_append_multiple_for_same_aggregate(self, db_conn):
        """Multiple events can be appended for the same aggregate."""
        repo = PgEventLogRepository(db_conn)
        agg_id = str(uuid4())

        for event_type in ["STRATEGY_CREATED", "STRATEGY_VERSION_CREATED", "STRATEGY_VISIBILITY_CHANGED"]:
            await repo.append(EventRecord(
                event_type=event_type,
                aggregate_type="strategy",
                aggregate_id=agg_id,
                actor_type="user",
                actor_id=uuid4(),
            ))

        events = await repo.get_by_aggregate("strategy", agg_id)
        assert len(events) == 3


class TestEventLogImmutability:
    """Test that UPDATE and DELETE are blocked (by RLS or triggers)."""

    async def test_update_has_no_effect(self, db_conn):
        """UPDATE on event_log is silently blocked (RLS prevents matching)."""
        repo = PgEventLogRepository(db_conn)
        event_id = await repo.append(EventRecord(
            event_type="TEST_EVENT",
            aggregate_type="test",
            aggregate_id="test-1",
            actor_type="system",
        ))

        # Attempt update — RLS blocks it (0 rows affected)
        result = await db_conn.execute(
            "UPDATE event_log SET event_type = 'MODIFIED' WHERE id = $1",
            event_id,
        )
        assert result == "UPDATE 0"  # No rows matched due to RLS

        # Verify unchanged
        row = await db_conn.fetchrow(
            "SELECT event_type FROM event_log WHERE id = $1", event_id
        )
        assert row["event_type"] == "TEST_EVENT"

    async def test_delete_has_no_effect(self, db_conn):
        """DELETE on event_log is silently blocked (RLS prevents matching)."""
        repo = PgEventLogRepository(db_conn)
        event_id = await repo.append(EventRecord(
            event_type="TEST_EVENT",
            aggregate_type="test",
            aggregate_id="test-2",
            actor_type="system",
        ))

        # Attempt delete — RLS blocks it (0 rows affected)
        result = await db_conn.execute(
            "DELETE FROM event_log WHERE id = $1", event_id
        )
        assert result == "DELETE 0"

        # Verify still exists
        row = await db_conn.fetchrow(
            "SELECT id FROM event_log WHERE id = $1", event_id
        )
        assert row is not None


class TestEventLogActorIntegrity:
    """Test that actor identity is server-controlled."""

    async def test_actor_id_is_stored(self, db_conn):
        """actor_id from the event record is persisted."""
        repo = PgEventLogRepository(db_conn)
        actor = uuid4()
        event_id = await repo.append(EventRecord(
            event_type="USER_LOGIN",
            aggregate_type="user",
            aggregate_id=str(actor),
            actor_type="user",
            actor_id=actor,
        ))

        row = await db_conn.fetchrow(
            "SELECT actor_id, actor_type FROM event_log WHERE id = $1", event_id
        )
        assert row["actor_id"] == actor
        assert row["actor_type"] == "user"

    async def test_invalid_actor_type_rejected(self, db_conn):
        """Invalid actor_type fails CHECK constraint."""
        with pytest.raises(asyncpg.CheckViolationError):
            await db_conn.execute(
                """
                INSERT INTO event_log (event_type, aggregate_type, aggregate_id, actor_type)
                VALUES ('TEST', 'test', 'x', 'hacker')
                """
            )
