"""Phase 3.4 integration tests: Attestation Commit/Reveal lifecycle.

Tests cover:
- Commitment creation (server-generated hash, before settlement)
- Reveal creation (server-derived fields, after settlement)
- Lifecycle ordering constraints
- Idempotency
- RLS (cross-user isolation)
- Immutability (INSERT-only enforcement)
- Trust boundary enforcement
- Provenance queries
- Audit event integration
"""

import pytest
import asyncpg
from datetime import datetime, timezone
from uuid import uuid4, UUID

from src.persistence.pg_attestation_repository import PgAttestationRepository
from src.persistence.pg_prediction_repository import PgPredictionRepository
from src.persistence.pg_settlement_repository import PgSettlementRepository
from src.persistence.pg_match_repository import PgMatchRepository
from src.persistence.pg_strategy_repository import PgStrategyRepository, PgStrategyVersionRepository, StrategyRecord
from src.persistence.pg_market_price_repository import PgMarketPriceRepository
from src.persistence.broadcast_hashing import compute_commitment_hash, compute_reveal_hash
from src.services.attestation_service import AttestationService, AttestationError
from src.services.prediction_service import PredictionService
from src.services.settlement_service import SettlementService
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


async def _settle_prediction(db_conn, prediction_id) -> dict:
    """Settle a prediction and return the settlement record."""
    svc = SettlementService(db_conn)
    return await svc.settle_prediction(
        prediction_id=prediction_id,
        actual_home_goals=2,
        actual_away_goals=1,
        stake=1.0,
    )


# ═══════════════════════════════════════════════════════════════
# COMMITMENT CREATION
# ═══════════════════════════════════════════════════════════════

class TestCommitmentCreation:
    async def test_create_commitment_success(self, db_conn):
        """Commitment is created with server-generated hash before settlement."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        commitment = await svc.create_commitment(
            user_id=SYSTEM_ID,
            prediction_id=pred["id"],
        )

        assert commitment is not None
        assert commitment["prediction_id"] == pred["id"]
        assert commitment["commitment_hash"] is not None
        assert len(commitment["commitment_hash"]) == 64
        assert commitment["chain_id"] is None
        assert commitment["contract_address"] is None
        assert commitment["tx_hash"] is None
        assert commitment["block_number"] is None

    async def test_commitment_hash_is_deterministic(self, db_conn):
        """Commitment hash matches manual computation from authoritative fields."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        commitment = await svc.create_commitment(SYSTEM_ID, pred["id"])

        expected = compute_commitment_hash(
            prediction_id=str(pred["id"]),
            strategy_id=str(pred["strategy_id"]),
            strategy_version=pred["strategy_version"],
            entry_odds=pred["entry_odds"],
            proof_hash=pred["proof_hash"],
            prediction_timestamp=pred["created_at"].isoformat(),
        )
        assert commitment["commitment_hash"] == expected

    async def test_commitment_references_existing_proof_hash(self, db_conn):
        """Commitment includes the existing proof_hash (no modification)."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        commitment = await svc.create_commitment(SYSTEM_ID, pred["id"])

        # Verify proof_hash is part of commitment content
        expected = compute_commitment_hash(
            prediction_id=str(pred["id"]),
            strategy_id=str(pred["strategy_id"]),
            strategy_version=pred["strategy_version"],
            entry_odds=pred["entry_odds"],
            proof_hash=pred["proof_hash"],
            prediction_timestamp=pred["created_at"].isoformat(),
        )
        assert commitment["commitment_hash"] == expected

    async def test_commitment_for_nonexistent_prediction_rejected(self, db_conn):
        """Commitment for nonexistent prediction is rejected."""
        svc = AttestationService(db_conn)
        with pytest.raises(AttestationError, match="not found"):
            await svc.create_commitment(SYSTEM_ID, uuid4())

    async def test_commitment_after_settlement_rejected(self, db_conn):
        """Commitment cannot be created after prediction is settled."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        # Settle first
        await _settle_prediction(db_conn, pred["id"])

        # Try to create commitment — should fail
        svc = AttestationService(db_conn)
        with pytest.raises(AttestationError, match="already settled"):
            await svc.create_commitment(SYSTEM_ID, pred["id"])

    async def test_cross_user_commitment_rejected(self, db_conn):
        """Cannot create commitment for another user's prediction."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        other_user = uuid4()
        svc = AttestationService(db_conn)
        with pytest.raises(AttestationError, match="another user"):
            await svc.create_commitment(other_user, pred["id"])


# ═══════════════════════════════════════════════════════════════
# COMMITMENT IDEMPOTENCY
# ═══════════════════════════════════════════════════════════════

class TestCommitmentIdempotency:
    async def test_duplicate_commitment_idempotent(self, db_conn):
        """Duplicate commitment for same prediction returns existing."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        c1 = await svc.create_commitment(SYSTEM_ID, pred["id"])
        c2 = await svc.create_commitment(SYSTEM_ID, pred["id"])

        assert c1["id"] == c2["id"]
        assert c1["commitment_hash"] == c2["commitment_hash"]


# ═══════════════════════════════════════════════════════════════
# REVEAL CREATION
# ═══════════════════════════════════════════════════════════════

class TestRevealCreation:
    async def test_create_reveal_success(self, db_conn):
        """Reveal created after commitment + settlement."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        # Commit first
        svc = AttestationService(db_conn)
        commitment = await svc.create_commitment(SYSTEM_ID, pred["id"])

        # Then settle
        settlement = await _settle_prediction(db_conn, pred["id"])

        # Then reveal
        reveal = await svc.create_reveal(SYSTEM_ID, pred["id"])

        assert reveal is not None
        assert reveal["commitment_id"] == commitment["id"]
        assert reveal["prediction_id"] == pred["id"]
        assert reveal["settlement_id"] == settlement["id"]
        assert reveal["reveal_hash"] is not None
        assert len(reveal["reveal_hash"]) == 64
        assert reveal["reveal_payload"] is not None
        assert reveal["chain_id"] is None

    async def test_reveal_payload_contains_settlement_data(self, db_conn):
        """Reveal payload contains authoritative settlement fields."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        commitment = await svc.create_commitment(SYSTEM_ID, pred["id"])
        settlement = await _settle_prediction(db_conn, pred["id"])
        reveal = await svc.create_reveal(SYSTEM_ID, pred["id"])

        payload = reveal["reveal_payload"]
        assert payload["outcome"] == settlement["outcome"]
        assert payload["profit_loss"] == settlement["profit_loss"]
        assert payload["entry_odds"] == settlement["entry_odds"]
        assert payload["commitment_hash"] == commitment["commitment_hash"]
        assert payload["prediction_id"] == str(pred["id"])
        assert payload["settlement_id"] == str(settlement["id"])

    async def test_reveal_without_commitment_rejected(self, db_conn):
        """Reveal without prior commitment is rejected."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        # Settle without commitment
        await _settle_prediction(db_conn, pred["id"])

        svc = AttestationService(db_conn)
        with pytest.raises(AttestationError, match="No commitment"):
            await svc.create_reveal(SYSTEM_ID, pred["id"])

    async def test_reveal_before_settlement_rejected(self, db_conn):
        """Reveal before settlement is rejected."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        # Commit but don't settle
        svc = AttestationService(db_conn)
        await svc.create_commitment(SYSTEM_ID, pred["id"])

        with pytest.raises(AttestationError, match="has not been settled"):
            await svc.create_reveal(SYSTEM_ID, pred["id"])

    async def test_cross_user_reveal_rejected(self, db_conn):
        """Cannot create reveal for another user's prediction."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        await svc.create_commitment(SYSTEM_ID, pred["id"])
        await _settle_prediction(db_conn, pred["id"])

        other_user = uuid4()
        with pytest.raises(AttestationError, match="another user"):
            await svc.create_reveal(other_user, pred["id"])

    async def test_reveal_for_nonexistent_prediction_rejected(self, db_conn):
        """Reveal for nonexistent prediction is rejected."""
        svc = AttestationService(db_conn)
        with pytest.raises(AttestationError, match="not found"):
            await svc.create_reveal(SYSTEM_ID, uuid4())


# ═══════════════════════════════════════════════════════════════
# REVEAL IDEMPOTENCY
# ═══════════════════════════════════════════════════════════════

class TestRevealIdempotency:
    async def test_duplicate_reveal_idempotent(self, db_conn):
        """Duplicate reveal returns existing record."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        await svc.create_commitment(SYSTEM_ID, pred["id"])
        await _settle_prediction(db_conn, pred["id"])

        r1 = await svc.create_reveal(SYSTEM_ID, pred["id"])
        r2 = await svc.create_reveal(SYSTEM_ID, pred["id"])

        assert r1["id"] == r2["id"]
        assert r1["reveal_hash"] == r2["reveal_hash"]


# ═══════════════════════════════════════════════════════════════
# ATTESTATION IMMUTABILITY
# ═══════════════════════════════════════════════════════════════

class TestAttestationImmutability:
    async def test_update_commitment_rejected(self, db_conn):
        """UPDATE on attestation_commitments is blocked by trigger."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        commitment = await svc.create_commitment(SYSTEM_ID, pred["id"])

        with pytest.raises(asyncpg.RaiseError):
            await db_conn.execute(
                "UPDATE attestation_commitments SET commitment_hash = $1 WHERE id = $2",
                "x" * 64, commitment["id"],
            )

    async def test_delete_commitment_rejected(self, db_conn):
        """DELETE on attestation_commitments is blocked by trigger."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        commitment = await svc.create_commitment(SYSTEM_ID, pred["id"])

        with pytest.raises(asyncpg.RaiseError):
            await db_conn.execute(
                "DELETE FROM attestation_commitments WHERE id = $1",
                commitment["id"],
            )

    async def test_update_reveal_rejected(self, db_conn):
        """UPDATE on attestation_reveals is blocked by trigger."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        await svc.create_commitment(SYSTEM_ID, pred["id"])
        await _settle_prediction(db_conn, pred["id"])
        reveal = await svc.create_reveal(SYSTEM_ID, pred["id"])

        with pytest.raises(asyncpg.RaiseError):
            await db_conn.execute(
                "UPDATE attestation_reveals SET reveal_hash = $1 WHERE id = $2",
                "y" * 64, reveal["id"],
            )

    async def test_delete_reveal_rejected(self, db_conn):
        """DELETE on attestation_reveals is blocked by trigger."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        await svc.create_commitment(SYSTEM_ID, pred["id"])
        await _settle_prediction(db_conn, pred["id"])
        reveal = await svc.create_reveal(SYSTEM_ID, pred["id"])

        with pytest.raises(asyncpg.RaiseError):
            await db_conn.execute(
                "DELETE FROM attestation_reveals WHERE id = $1",
                reveal["id"],
            )


# ═══════════════════════════════════════════════════════════════
# ATTESTATION RLS
# ═══════════════════════════════════════════════════════════════

class TestAttestationRLS:
    async def test_user_cannot_read_other_users_commitment(self, db_conn):
        """RLS prevents reading another user's commitment."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        commitment = await svc.create_commitment(SYSTEM_ID, pred["id"])

        # Switch to different user
        other_user = uuid4()
        await db_conn.execute(
            """INSERT INTO users (id, email, username, display_name, password_hash, role)
               VALUES ($1, $2, $3, $4, 'hash', 'user')""",
            other_user, f"{other_user.hex[:8]}@test.com", f"user_{other_user.hex[:8]}",
            f"User {other_user.hex[:8]}",
        )
        await db_conn.execute(f"SET LOCAL app.user_id = '{other_user}'")
        await db_conn.execute("SET LOCAL app.user_role = 'user'")

        # Other user cannot see the commitment
        row = await db_conn.fetchrow(
            "SELECT * FROM attestation_commitments WHERE id = $1",
            commitment["id"],
        )
        assert row is None

    async def test_user_cannot_read_other_users_reveal(self, db_conn):
        """RLS prevents reading another user's reveal."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        await svc.create_commitment(SYSTEM_ID, pred["id"])
        await _settle_prediction(db_conn, pred["id"])
        reveal = await svc.create_reveal(SYSTEM_ID, pred["id"])

        # Switch to different user
        other_user = uuid4()
        await db_conn.execute(
            """INSERT INTO users (id, email, username, display_name, password_hash, role)
               VALUES ($1, $2, $3, $4, 'hash', 'user')""",
            other_user, f"{other_user.hex[:8]}@test.com", f"user_{other_user.hex[:8]}",
            f"User {other_user.hex[:8]}",
        )
        await db_conn.execute(f"SET LOCAL app.user_id = '{other_user}'")
        await db_conn.execute("SET LOCAL app.user_role = 'user'")

        # Other user cannot see the reveal
        row = await db_conn.fetchrow(
            "SELECT * FROM attestation_reveals WHERE id = $1",
            reveal["id"],
        )
        assert row is None


# ═══════════════════════════════════════════════════════════════
# ATTESTATION PROVENANCE
# ═══════════════════════════════════════════════════════════════

class TestAttestationProvenance:
    async def test_full_provenance_query(self, db_conn):
        """Full attestation provenance is queryable (commit + reveal)."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        commitment = await svc.create_commitment(SYSTEM_ID, pred["id"])
        await _settle_prediction(db_conn, pred["id"])
        reveal = await svc.create_reveal(SYSTEM_ID, pred["id"])

        # Query full provenance
        attestation = await svc.get_attestation(pred["id"])
        assert attestation is not None
        assert attestation["commitment_id"] == commitment["id"]
        assert attestation["commitment_hash"] == commitment["commitment_hash"]
        assert attestation["reveal_id"] == reveal["id"]
        assert attestation["reveal_hash"] == reveal["reveal_hash"]
        assert attestation["prediction_id"] == pred["id"]

    async def test_provenance_before_reveal(self, db_conn):
        """Provenance query returns commitment-only before reveal."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        commitment = await svc.create_commitment(SYSTEM_ID, pred["id"])

        attestation = await svc.get_attestation(pred["id"])
        assert attestation is not None
        assert attestation["commitment_hash"] == commitment["commitment_hash"]
        assert attestation["reveal_id"] is None

    async def test_no_provenance_without_commitment(self, db_conn):
        """Provenance query returns None without commitment."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        attestation = await svc.get_attestation(pred["id"])
        assert attestation is None


# ═══════════════════════════════════════════════════════════════
# ATTESTATION AUDIT EVENTS
# ═══════════════════════════════════════════════════════════════

class TestAttestationAuditEvents:
    async def test_commitment_emits_event(self, db_conn):
        """Commitment creation emits ATTESTATION_COMMITTED event."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        commitment = await svc.create_commitment(SYSTEM_ID, pred["id"])

        event = await db_conn.fetchrow(
            """
            SELECT * FROM event_log
            WHERE event_type = 'ATTESTATION_COMMITTED'
              AND aggregate_id = $1
            ORDER BY id DESC LIMIT 1
            """,
            str(commitment["id"]),
        )
        assert event is not None
        assert event["aggregate_type"] == "attestation"

    async def test_reveal_emits_event(self, db_conn):
        """Reveal creation emits ATTESTATION_REVEALED event."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        await svc.create_commitment(SYSTEM_ID, pred["id"])
        await _settle_prediction(db_conn, pred["id"])
        reveal = await svc.create_reveal(SYSTEM_ID, pred["id"])

        event = await db_conn.fetchrow(
            """
            SELECT * FROM event_log
            WHERE event_type = 'ATTESTATION_REVEALED'
              AND aggregate_id = $1
            ORDER BY id DESC LIMIT 1
            """,
            str(reveal["id"]),
        )
        assert event is not None
        assert event["aggregate_type"] == "attestation"


# ═══════════════════════════════════════════════════════════════
# WEB3 READINESS (nullable blockchain fields)
# ═══════════════════════════════════════════════════════════════

class TestWeb3Readiness:
    async def test_commitment_blockchain_fields_nullable(self, db_conn):
        """Commitment blockchain fields are all NULL (no blockchain dependency)."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        commitment = await svc.create_commitment(SYSTEM_ID, pred["id"])

        assert commitment["chain_id"] is None
        assert commitment["contract_address"] is None
        assert commitment["tx_hash"] is None
        assert commitment["block_number"] is None

    async def test_reveal_blockchain_fields_nullable(self, db_conn):
        """Reveal blockchain fields are all NULL (no blockchain dependency)."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        pred = await _create_prediction(db_conn, strat_id, version, content_hash, match_id)

        svc = AttestationService(db_conn)
        await svc.create_commitment(SYSTEM_ID, pred["id"])
        await _settle_prediction(db_conn, pred["id"])
        reveal = await svc.create_reveal(SYSTEM_ID, pred["id"])

        assert reveal["chain_id"] is None
        assert reveal["contract_address"] is None
        assert reveal["tx_hash"] is None
        assert reveal["block_number"] is None
