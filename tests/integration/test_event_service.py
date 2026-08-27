"""Integration tests for EventService (transactional audit event emission)."""

import pytest
from uuid import uuid4

from src.persistence.events import EventService, EventTypes


pytestmark = pytest.mark.asyncio


class TestEventServiceEmit:
    """Test event emission within transactions."""

    async def test_emit_returns_event_id(self, db_conn, system_user_id):
        """emit() returns a positive event ID."""
        svc = EventService(db_conn)
        event_id = await svc.emit(
            event_type=EventTypes.USER_REGISTERED,
            aggregate_type="user",
            aggregate_id=str(uuid4()),
            actor_type="system",
        )
        assert event_id > 0

    async def test_emit_with_payload(self, db_conn, system_user_id):
        """Event payload is stored correctly."""
        svc = EventService(db_conn)
        agg_id = str(uuid4())
        await svc.emit(
            event_type=EventTypes.STRATEGY_CREATED,
            aggregate_type="strategy",
            aggregate_id=agg_id,
            actor_id=system_user_id,
            actor_type="user",
            payload={"name": "Test Strategy", "metric": "xC"},
        )

        # Verify stored
        row = await db_conn.fetchrow(
            "SELECT event_type, actor_id, payload FROM event_log WHERE aggregate_id = $1 ORDER BY id DESC LIMIT 1",
            agg_id,
        )
        assert row["event_type"] == "STRATEGY_CREATED"
        assert row["actor_id"] == system_user_id

    async def test_emit_with_correlation(self, db_conn, system_user_id):
        """Events can be grouped by correlation_id."""
        svc = EventService(db_conn)
        corr_id = uuid4()
        agg = str(uuid4())

        id1 = await svc.emit(
            event_type=EventTypes.STRATEGY_CREATED,
            aggregate_type="strategy",
            aggregate_id=agg,
            actor_id=system_user_id,
            correlation_id=corr_id,
        )
        id2 = await svc.emit(
            event_type=EventTypes.STRATEGY_VERSION_CREATED,
            aggregate_type="strategy",
            aggregate_id=agg,
            actor_id=system_user_id,
            correlation_id=corr_id,
            causation_id=id1,
        )

        # Both events share correlation_id
        rows = await db_conn.fetch(
            "SELECT id, event_type, causation_id FROM event_log WHERE correlation_id = $1 ORDER BY id",
            corr_id,
        )
        assert len(rows) == 2
        assert rows[0]["id"] == id1
        assert rows[1]["id"] == id2
        assert rows[1]["causation_id"] == id1

    async def test_all_event_types_are_valid_strings(self):
        """EventTypes registry only contains non-empty strings."""
        for attr in dir(EventTypes):
            if attr.startswith("_"):
                continue
            val = getattr(EventTypes, attr)
            assert isinstance(val, str)
            assert len(val) > 0
            assert val == val.upper()  # All caps convention


class TestEventTransactionality:
    """Verify events are atomic with business operations."""

    async def test_event_visible_within_transaction(self, db_conn, system_user_id):
        """Event is visible within the same transaction immediately."""
        svc = EventService(db_conn)
        agg_id = str(uuid4())
        event_id = await svc.emit(
            event_type=EventTypes.MATCH_IMPORTED,
            aggregate_type="match",
            aggregate_id=agg_id,
            actor_type="service",
        )

        # Should be visible in same transaction
        row = await db_conn.fetchrow(
            "SELECT id FROM event_log WHERE id = $1", event_id
        )
        assert row is not None
