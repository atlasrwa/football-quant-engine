"""Phase 3.4 integration tests: Signal Dispatch & Broadcast.

Tests cover:
- Broadcast creation with trust gate enforcement
- Channel-aware delivery tracking
- Stable deep links
- Idempotency
- RLS (cross-user isolation)
- Immutability (INSERT-only enforcement)
- Trust boundary enforcement (non-PROMOTED rejected)
- Audit event integration
"""

import pytest
import asyncpg
from datetime import datetime, timedelta, timezone
from uuid import uuid4, UUID

from src.persistence.pg_broadcast_repository import PgBroadcastRepository
from src.persistence.pg_prediction_repository import PgPredictionRepository
from src.persistence.pg_quarantine_repository import PgQuarantineRepository
from src.persistence.pg_strategy_repository import PgStrategyRepository, PgStrategyVersionRepository, StrategyRecord
from src.persistence.pg_match_repository import PgMatchRepository
from src.persistence.pg_validation_repository import PgValidationRepository
from src.persistence.broadcast_hashing import compute_broadcast_payload_hash
from src.services.broadcast_service import BroadcastService, BroadcastError
from src.services.prediction_service import PredictionService
from src.services.quarantine_service import QuarantineService
from src.models.match import Match

pytestmark = pytest.mark.asyncio
SYSTEM_ID = UUID("00000000-0000-0000-0000-000000000001")


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

async def _setup_strategy(db_conn) -> tuple:
    """Create strategy + version, return (strategy_id, version, content_hash)."""
    strat_repo = PgStrategyRepository(db_conn)
    sv_repo = PgStrategyVersionRepository(db_conn)
    strat = await strat_repo.create_strategy(StrategyRecord(
        id=uuid4(), owner_id=SYSTEM_ID, name=f"Test_{uuid4().hex[:6]}",
        description=None, visibility="private", status="active",
    ))
    sv = await sv_repo.create_version(strat.id, {
        "name": "T", "metric": "xC", "market": "corners",
        "conditions": [{"field": "f", "op": ">", "value": float(hash(uuid4()) % 1000)}],
        "logic": "and", "direction": "OVER", "min_odds": 1.5,
    }, SYSTEM_ID)
    return strat.id, sv.version, sv.content_hash


async def _setup_match(db_conn, external_id: int = None) -> int:
    """Insert a match and return surrogate match_id."""
    ext_id = external_id or (hash(uuid4()) % 900000 + 100000)
    repo = PgMatchRepository(db_conn)
    match = Match(id=ext_id, date_unix=1700000000, league_id=4759, season="2023",
                  home_team="A", away_team="B", home_goals=2, away_goals=1,
                  total_goals=3, home_xg=1.5, away_xg=1.0, referee="Ref",
                  over_under_line=2.5, over_odds=1.90, under_odds=2.00)
    return await repo.upsert(match)


async def _create_prediction(db_conn, strat_id, version, content_hash, match_id) -> dict:
    """Create a prediction and return the record."""
    svc = PredictionService(db_conn)
    return await svc.create_prediction(
        user_id=SYSTEM_ID, strategy_id=strat_id,
        strategy_version=version, strategy_content_hash=content_hash,
        match_id=match_id, match_date_unix=1700000000,
        home_team="A", away_team="B", league_id=4759,
        market_type="OVER_UNDER", direction="OVER",
        entry_odds=1.90, model_edge_pct=5.0,
        confidence=75.0, recommended_stake=0.05,
        source="PAPER_TRADE",
    )


async def _promote_strategy(db_conn, strat_id, version):
    """Enter quarantine with past dates and promote a strategy version."""
    from datetime import timedelta
    past = datetime.now(timezone.utc) - timedelta(days=91)
    quarantine_until = past + timedelta(days=90)

    # Insert quarantine entry with quarantine_until already in the past
    await db_conn.execute(
        """
        INSERT INTO quarantine_entries (strategy_id, strategy_version, user_id,
            status, entered_at, quarantine_until)
        VALUES ($1, $2, $3, 'PENDING_QUARANTINE', $4, $5)
        ON CONFLICT (strategy_id, strategy_version) DO NOTHING
        """,
        strat_id, version, SYSTEM_ID, past, quarantine_until,
    )

    # Create a PASSED validation run
    val_repo = PgValidationRepository(db_conn)
    await val_repo.create(
        strategy_id=strat_id, strategy_version=version,
        status="PASSED", p_value=0.01, roi_pct=5.0,
        sample_size=300, effect_size=0.3, ci_lower=0.5, ci_upper=2.0,
        min_sample_required=250, min_roi_required=3.0, max_p_value=0.05,
        fdr_submission_count=1, reason="Passed",
    )

    # Promotion also requires enough positive paper trading (see
    # QuarantineService.MIN_PAPER_BETS_FOR_PROMOTION) — seed it directly
    # rather than settling real predictions, since these tests are about
    # broadcast behavior, not paper trading itself.
    from src.services.quarantine_service import QuarantineService
    q_repo = PgQuarantineRepository(db_conn)
    await q_repo.update_paper_pnl(
        strat_id, version,
        pnl_delta=1.0, bets_delta=QuarantineService.MIN_PAPER_BETS_FOR_PROMOTION,
    )

    # Promote
    svc = QuarantineService(db_conn)
    result = await svc.promote(strat_id, version, SYSTEM_ID)
    assert result["status"] == "PROMOTED", "Promotion failed"
    return result


# ═══════════════════════════════════════════════════════════════
# BROADCAST CREATION + TRUST GATE
# ═══════════════════════════════════════════════════════════════

class TestBroadcastCreation:
    async def test_broadcast_success_with_promoted_strategy(self, db_conn):
        """Broadcast succeeds when strategy version is PROMOTED."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)
        await _promote_strategy(db_conn, strat_id, version)

        svc = BroadcastService(db_conn)
        broadcast = await svc.create_broadcast(
            user_id=SYSTEM_ID,
            prediction_id=pred["id"],
            channel="web",
        )

        assert broadcast is not None
        assert broadcast["prediction_id"] == pred["id"]
        assert broadcast["channel"] == "web"
        assert broadcast["status"] in ("DISPATCHED", "DELIVERED")
        assert broadcast["payload_hash"] is not None
        assert len(broadcast["payload_hash"]) == 64
        assert broadcast["deep_link"] == f"/predictions/{pred['id']}"
        assert broadcast["user_id"] == SYSTEM_ID

    async def test_broadcast_non_promoted_rejected(self, db_conn):
        """Broadcast fails when strategy is PENDING_QUARANTINE (not PROMOTED)."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        # Enter quarantine but do NOT promote
        qe_repo = PgQuarantineRepository(db_conn)
        await qe_repo.enter(strat_id, version, SYSTEM_ID)

        svc = BroadcastService(db_conn)
        with pytest.raises(BroadcastError, match="not PROMOTED"):
            await svc.create_broadcast(
                user_id=SYSTEM_ID,
                prediction_id=pred["id"],
                channel="web",
            )

    async def test_broadcast_no_quarantine_record_rejected(self, db_conn):
        """Broadcast fails when strategy has no quarantine record."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = BroadcastService(db_conn)
        with pytest.raises(BroadcastError, match="no quarantine record"):
            await svc.create_broadcast(
                user_id=SYSTEM_ID,
                prediction_id=pred["id"],
                channel="web",
            )

    async def test_broadcast_nonexistent_prediction_rejected(self, db_conn):
        """Broadcast fails for non-existent prediction."""
        svc = BroadcastService(db_conn)
        with pytest.raises(BroadcastError, match="not found"):
            await svc.create_broadcast(
                user_id=SYSTEM_ID,
                prediction_id=uuid4(),
                channel="web",
            )

    async def test_broadcast_unsupported_channel_rejected(self, db_conn):
        """Broadcast fails for unsupported channel."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)
        await _promote_strategy(db_conn, strat_id, version)

        svc = BroadcastService(db_conn)
        with pytest.raises(BroadcastError, match="Unsupported channel"):
            await svc.create_broadcast(
                user_id=SYSTEM_ID,
                prediction_id=pred["id"],
                channel="carrier_pigeon",
            )


# ═══════════════════════════════════════════════════════════════
# MULTI-CHANNEL BROADCAST
# ═══════════════════════════════════════════════════════════════

class TestMultiChannelBroadcast:
    async def test_one_prediction_multiple_channels(self, db_conn):
        """One prediction can produce multiple broadcasts (one per channel)."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)
        await _promote_strategy(db_conn, strat_id, version)

        svc = BroadcastService(db_conn)
        b_web = await svc.create_broadcast(SYSTEM_ID, pred["id"], "web")
        b_mobile = await svc.create_broadcast(SYSTEM_ID, pred["id"], "mobile")
        b_telegram = await svc.create_broadcast(SYSTEM_ID, pred["id"], "telegram", "@test_channel")

        # All should be different records
        assert b_web["id"] != b_mobile["id"]
        assert b_web["id"] != b_telegram["id"]

        # All reference same prediction
        assert b_web["prediction_id"] == pred["id"]
        assert b_mobile["prediction_id"] == pred["id"]
        assert b_telegram["prediction_id"] == pred["id"]

        # Same payload hash (deterministic)
        assert b_web["payload_hash"] == b_mobile["payload_hash"]

        # Different channels
        assert b_web["channel"] == "web"
        assert b_mobile["channel"] == "mobile"
        assert b_telegram["channel"] == "telegram"

    async def test_get_prediction_broadcasts(self, db_conn):
        """Can retrieve all broadcasts for a prediction."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)
        await _promote_strategy(db_conn, strat_id, version)

        svc = BroadcastService(db_conn)
        await svc.create_broadcast(SYSTEM_ID, pred["id"], "web")
        await svc.create_broadcast(SYSTEM_ID, pred["id"], "mobile")

        broadcasts = await svc.get_prediction_broadcasts(pred["id"])
        assert len(broadcasts) == 2


# ═══════════════════════════════════════════════════════════════
# BROADCAST IDEMPOTENCY
# ═══════════════════════════════════════════════════════════════

class TestBroadcastIdempotency:
    async def test_duplicate_broadcast_idempotent(self, db_conn):
        """Duplicate broadcast (same prediction+channel+destination) is idempotent."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)
        await _promote_strategy(db_conn, strat_id, version)

        svc = BroadcastService(db_conn)
        b1 = await svc.create_broadcast(SYSTEM_ID, pred["id"], "web")
        b2 = await svc.create_broadcast(SYSTEM_ID, pred["id"], "web")

        # Same record returned
        assert b1["id"] == b2["id"]
        assert b1["payload_hash"] == b2["payload_hash"]

    async def test_different_destinations_create_separate_records(self, db_conn):
        """Same channel but different destinations create separate records."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)
        await _promote_strategy(db_conn, strat_id, version)

        svc = BroadcastService(db_conn)
        b1 = await svc.create_broadcast(SYSTEM_ID, pred["id"], "telegram", "@channel1")
        b2 = await svc.create_broadcast(SYSTEM_ID, pred["id"], "telegram", "@channel2")

        assert b1["id"] != b2["id"]
        assert b1["destination"] == "@channel1"
        assert b2["destination"] == "@channel2"


# ═══════════════════════════════════════════════════════════════
# BROADCAST TRUST BOUNDARIES
# ═══════════════════════════════════════════════════════════════

class TestBroadcastTrustBoundaries:
    async def test_client_cannot_broadcast_another_users_prediction(self, db_conn):
        """User cannot broadcast another user's prediction."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)
        await _promote_strategy(db_conn, strat_id, version)

        # Different user trying to broadcast
        other_user = uuid4()
        svc = BroadcastService(db_conn)
        with pytest.raises(BroadcastError, match="another user"):
            await svc.create_broadcast(
                user_id=other_user,
                prediction_id=pred["id"],
                channel="web",
            )

    async def test_payload_hash_is_deterministic(self, db_conn):
        """Payload hash is deterministic for same prediction content."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)
        await _promote_strategy(db_conn, strat_id, version)

        svc = BroadcastService(db_conn)
        b1 = await svc.create_broadcast(SYSTEM_ID, pred["id"], "web")

        # Verify hash matches manual computation
        expected_hash = compute_broadcast_payload_hash(
            prediction_id=str(pred["id"]),
            strategy_id=str(pred["strategy_id"]),
            strategy_version=pred["strategy_version"],
            direction=pred["direction"],
            entry_odds=pred["entry_odds"],
            confidence=pred["confidence"],
            match_id=pred["match_id"],
            proof_hash=pred["proof_hash"],
            prediction_timestamp=pred["created_at"].isoformat(),
        )
        assert b1["payload_hash"] == expected_hash

    async def test_deep_link_stable(self, db_conn):
        """Deep link is stable and deterministic."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)
        await _promote_strategy(db_conn, strat_id, version)

        svc = BroadcastService(db_conn)
        broadcast = await svc.create_broadcast(SYSTEM_ID, pred["id"], "web")

        assert broadcast["deep_link"] == f"/predictions/{pred['id']}"

    async def test_failed_dispatch_still_recorded(self, db_conn):
        """Failed dispatch (missing destination for telegram) is still recorded."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)
        await _promote_strategy(db_conn, strat_id, version)

        svc = BroadcastService(db_conn)
        # Telegram without destination should fail dispatch but still record
        broadcast = await svc.create_broadcast(SYSTEM_ID, pred["id"], "telegram")

        assert broadcast["status"] == "FAILED"
        assert broadcast["error_code"] == "MISSING_DESTINATION"


# ═══════════════════════════════════════════════════════════════
# BROADCAST IMMUTABILITY
# ═══════════════════════════════════════════════════════════════

class TestBroadcastImmutability:
    async def test_update_broadcast_rejected(self, db_conn):
        """UPDATE on broadcast_logs is blocked by trigger."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)
        await _promote_strategy(db_conn, strat_id, version)

        svc = BroadcastService(db_conn)
        broadcast = await svc.create_broadcast(SYSTEM_ID, pred["id"], "web")

        with pytest.raises(asyncpg.RaiseError):
            await db_conn.execute(
                "UPDATE broadcast_logs SET status = 'FAILED' WHERE id = $1",
                broadcast["id"],
            )

    async def test_delete_broadcast_rejected(self, db_conn):
        """DELETE on broadcast_logs is blocked by trigger."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)
        await _promote_strategy(db_conn, strat_id, version)

        svc = BroadcastService(db_conn)
        broadcast = await svc.create_broadcast(SYSTEM_ID, pred["id"], "web")

        with pytest.raises(asyncpg.RaiseError):
            await db_conn.execute(
                "DELETE FROM broadcast_logs WHERE id = $1",
                broadcast["id"],
            )


# ═══════════════════════════════════════════════════════════════
# BROADCAST RLS
# ═══════════════════════════════════════════════════════════════

class TestBroadcastRLS:
    async def test_user_cannot_read_other_users_broadcasts(self, db_conn):
        """RLS prevents reading another user's broadcast records."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)
        await _promote_strategy(db_conn, strat_id, version)

        svc = BroadcastService(db_conn)
        broadcast = await svc.create_broadcast(SYSTEM_ID, pred["id"], "web")

        # Switch to different user context
        other_user = uuid4()
        await db_conn.execute(
            """INSERT INTO users (id, email, username, display_name, password_hash, role)
               VALUES ($1, $2, $3, $4, 'hash', 'user')""",
            other_user, f"{other_user.hex[:8]}@test.com", f"user_{other_user.hex[:8]}",
            f"User {other_user.hex[:8]}",
        )
        await db_conn.execute(f"SET LOCAL app.user_id = '{other_user}'")
        await db_conn.execute("SET LOCAL app.user_role = 'user'")

        # Other user cannot see the broadcast
        row = await db_conn.fetchrow(
            "SELECT * FROM broadcast_logs WHERE id = $1",
            broadcast["id"],
        )
        assert row is None

    async def test_user_cannot_insert_broadcast_for_other_user(self, db_conn):
        """RLS prevents inserting broadcast with another user's user_id."""
        # Create another user
        other_user = uuid4()
        await db_conn.execute(
            """INSERT INTO users (id, email, username, display_name, password_hash, role)
               VALUES ($1, $2, $3, $4, 'hash', 'user')""",
            other_user, f"{other_user.hex[:8]}@test.com", f"user_{other_user.hex[:8]}",
            f"User {other_user.hex[:8]}",
        )

        # Setup prediction as system user
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        # Switch to other_user context
        await db_conn.execute(f"SET LOCAL app.user_id = '{other_user}'")
        await db_conn.execute("SET LOCAL app.user_role = 'user'")

        # Try to insert a broadcast with SYSTEM_ID as user_id — RLS blocks
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await db_conn.execute(
                """
                INSERT INTO broadcast_logs (id, user_id, prediction_id, channel, status, payload_hash)
                VALUES ($1, $2, $3, 'web', 'PENDING', $4)
                """,
                uuid4(), SYSTEM_ID, pred["id"], "a" * 64,
            )


# ═══════════════════════════════════════════════════════════════
# BROADCAST AUDIT EVENTS
# ═══════════════════════════════════════════════════════════════

class TestBroadcastAuditEvents:
    async def test_successful_broadcast_emits_dispatched_event(self, db_conn):
        """Successful broadcast emits BROADCAST_DISPATCHED event."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)
        await _promote_strategy(db_conn, strat_id, version)

        svc = BroadcastService(db_conn)
        broadcast = await svc.create_broadcast(SYSTEM_ID, pred["id"], "web")

        # Check event was emitted
        event = await db_conn.fetchrow(
            """
            SELECT * FROM event_log
            WHERE event_type = 'BROADCAST_DISPATCHED'
              AND aggregate_id = $1
            ORDER BY id DESC LIMIT 1
            """,
            str(broadcast["id"]),
        )
        assert event is not None
        assert event["aggregate_type"] == "broadcast"

    async def test_failed_broadcast_emits_failed_event(self, db_conn):
        """Failed broadcast emits BROADCAST_FAILED event."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)
        await _promote_strategy(db_conn, strat_id, version)

        svc = BroadcastService(db_conn)
        broadcast = await svc.create_broadcast(SYSTEM_ID, pred["id"], "telegram")

        event = await db_conn.fetchrow(
            """
            SELECT * FROM event_log
            WHERE event_type = 'BROADCAST_FAILED'
              AND aggregate_id = $1
            ORDER BY id DESC LIMIT 1
            """,
            str(broadcast["id"]),
        )
        assert event is not None
