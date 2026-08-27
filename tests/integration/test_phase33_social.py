"""Phase 3.3 integration tests: Social (follows, quarantine, cross-user isolation)."""

import pytest
import asyncpg
from datetime import datetime, timedelta, timezone
from uuid import uuid4, UUID

from src.persistence.pg_social_repository import PgFollowRepository, PgReputationRepository, PgLeaderboardRepository
from src.persistence.pg_quarantine_repository import PgQuarantineRepository
from src.persistence.pg_validation_repository import PgValidationRepository
from src.persistence.pg_strategy_repository import PgStrategyRepository, PgStrategyVersionRepository, StrategyRecord
from src.persistence.pg_paper_repository import PgPaperPortfolioRepository
from src.services.quarantine_service import QuarantineService, QuarantineError

pytestmark = pytest.mark.asyncio
SYSTEM_ID = UUID("00000000-0000-0000-0000-000000000001")


async def _create_user(db_conn, name: str = None) -> UUID:
    """Create a test user and return UUID."""
    uid = uuid4()
    uname = name or f"user_{uuid4().hex[:8]}"
    await db_conn.execute(
        "INSERT INTO users (id, username, display_name, role, status) VALUES ($1, $2, $2, 'user', 'active')",
        uid, uname,
    )
    return uid


# ═══════════════════════════════════════════════════════════════
# FOLLOWS
# ═══════════════════════════════════════════════════════════════

class TestFollows:
    async def test_follow_and_unfollow(self, db_conn):
        """Basic follow/unfollow cycle."""
        user_a = await _create_user(db_conn)
        user_b = await _create_user(db_conn)
        repo = PgFollowRepository(db_conn)

        assert await repo.follow(user_a, user_b) is True
        assert await repo.is_following(user_a, user_b) is True
        assert await repo.follower_count(user_b) == 1

        assert await repo.unfollow(user_a, user_b) is True
        assert await repo.is_following(user_a, user_b) is False
        assert await repo.follower_count(user_b) == 0

    async def test_self_follow_prevented(self, db_conn):
        """User cannot follow themselves (CHECK constraint)."""
        user_a = await _create_user(db_conn)
        with pytest.raises(asyncpg.CheckViolationError):
            await db_conn.execute(
                "INSERT INTO follows (follower_id, followed_id) VALUES ($1, $1)", user_a
            )

    async def test_duplicate_follow_idempotent(self, db_conn):
        """Following same user twice is idempotent (ON CONFLICT DO NOTHING)."""
        user_a = await _create_user(db_conn)
        user_b = await _create_user(db_conn)
        repo = PgFollowRepository(db_conn)

        await repo.follow(user_a, user_b)
        result = await repo.follow(user_a, user_b)  # duplicate
        assert result is False  # Already exists
        assert await repo.follower_count(user_b) == 1  # Still just 1

    async def test_follower_and_following_lists(self, db_conn):
        """Follower/following lists are correct."""
        user_a = await _create_user(db_conn)
        user_b = await _create_user(db_conn)
        user_c = await _create_user(db_conn)
        repo = PgFollowRepository(db_conn)

        await repo.follow(user_a, user_b)  # A follows B
        await repo.follow(user_c, user_b)  # C follows B

        followers = await repo.get_followers(user_b)
        assert set(followers) == {user_a, user_c}

        following = await repo.get_following(user_a)
        assert following == [user_b]


# ═══════════════════════════════════════════════════════════════
# QUARANTINE
# ═══════════════════════════════════════════════════════════════

class TestQuarantine:
    async def _setup_strategy(self, db_conn) -> tuple:
        strat_repo = PgStrategyRepository(db_conn)
        sv_repo = PgStrategyVersionRepository(db_conn)
        strat = await strat_repo.create_strategy(StrategyRecord(
            id=uuid4(), owner_id=SYSTEM_ID, name=f"Q_{uuid4().hex[:6]}",
            description=None, visibility="private", status="active",
        ))
        sv = await sv_repo.create_version(strat.id, {
            "name": "Q", "metric": "xC", "market": "corners",
            "conditions": [{"field": "f", "op": ">", "value": float(hash(uuid4()) % 100)}],
            "logic": "and", "direction": "OVER", "min_odds": 1.5,
        }, SYSTEM_ID)
        return strat.id, sv.version

    async def test_enter_quarantine(self, db_conn):
        """Strategy version enters quarantine."""
        strat_id, version = await self._setup_strategy(db_conn)
        svc = QuarantineService(db_conn)
        entry = await svc.enter_quarantine(strat_id, version, SYSTEM_ID)
        assert entry["status"] == "PENDING_QUARANTINE"
        assert entry["quarantine_until"] is not None

    async def test_version_specific_quarantine(self, db_conn):
        """Each version has independent quarantine (I19)."""
        strat_repo = PgStrategyRepository(db_conn)
        sv_repo = PgStrategyVersionRepository(db_conn)
        strat = await strat_repo.create_strategy(StrategyRecord(
            id=uuid4(), owner_id=SYSTEM_ID, name=f"Multi_{uuid4().hex[:6]}",
            description=None, visibility="private", status="active",
        ))
        sv1 = await sv_repo.create_version(strat.id, {
            "name": "V1", "metric": "xC", "market": "corners",
            "conditions": [{"field": "a", "op": ">", "value": 1.0}],
            "logic": "and", "direction": "OVER", "min_odds": 1.5,
        }, SYSTEM_ID)
        sv2 = await sv_repo.create_version(strat.id, {
            "name": "V2", "metric": "xC", "market": "corners",
            "conditions": [{"field": "b", "op": ">", "value": 2.0}],
            "logic": "and", "direction": "OVER", "min_odds": 1.5,
        }, SYSTEM_ID)

        repo = PgQuarantineRepository(db_conn)
        e1 = await repo.enter(strat.id, sv1.version, SYSTEM_ID)
        e2 = await repo.enter(strat.id, sv2.version, SYSTEM_ID)
        assert e1["id"] != e2["id"]

        # Reject v1, v2 unaffected
        await repo.reject(strat.id, sv1.version)
        q2 = await repo.get(strat.id, sv2.version)
        assert q2["status"] == "PENDING_QUARANTINE"

    async def test_promotion_requires_validation(self, db_conn):
        """Promotion fails without PASSED validation."""
        strat_id, version = await self._setup_strategy(db_conn)
        svc = QuarantineService(db_conn)
        await svc.enter_quarantine(strat_id, version, SYSTEM_ID)

        with pytest.raises(QuarantineError, match="no PASSED validation"):
            await svc.promote(strat_id, version, SYSTEM_ID)

    async def test_promotion_requires_90_days(self, db_conn):
        """Promotion fails if 90-day period not elapsed."""
        strat_id, version = await self._setup_strategy(db_conn)
        svc = QuarantineService(db_conn)
        await svc.enter_quarantine(strat_id, version, SYSTEM_ID)

        # Insert a PASSED validation
        val_repo = PgValidationRepository(db_conn)
        await val_repo.create(
            strategy_id=strat_id, strategy_version=version,
            status="PASSED", p_value=0.01, roi_pct=5.0,
            sample_size=300, effect_size=0.3, ci_lower=0.5, ci_upper=2.0,
            min_sample_required=250, min_roi_required=3.0, max_p_value=0.05,
            fdr_submission_count=1, reason="All gates passed",
        )

        # Still can't promote — 90 days haven't elapsed
        with pytest.raises(QuarantineError, match="90-day"):
            await svc.promote(strat_id, version, SYSTEM_ID)

    async def test_quarantine_state_immutable_after_promotion(self, db_conn):
        """Once PROMOTED, status cannot change again."""
        strat_id, version = await self._setup_strategy(db_conn)
        repo = PgQuarantineRepository(db_conn)

        # Enter quarantine with quarantine_until already in the past (simulate 90 days elapsed)
        from datetime import datetime, timedelta, timezone
        past = datetime.now(timezone.utc) - timedelta(days=91)
        await db_conn.execute(
            """INSERT INTO quarantine_entries (strategy_id, strategy_version, user_id,
               status, entered_at, quarantine_until)
               VALUES ($1, $2, $3, 'PENDING_QUARANTINE', $4, $5)
               ON CONFLICT (strategy_id, strategy_version) DO NOTHING""",
            strat_id, version, SYSTEM_ID, past, past + timedelta(days=90),
        )

        # Insert validation
        val_repo = PgValidationRepository(db_conn)
        await val_repo.create(
            strategy_id=strat_id, strategy_version=version,
            status="PASSED", p_value=0.01, roi_pct=5.0,
            sample_size=300, effect_size=0.3, ci_lower=0.5, ci_upper=2.0,
            min_sample_required=250, min_roi_required=3.0, max_p_value=0.05,
            fdr_submission_count=1, reason="Passed",
        )

        svc = QuarantineService(db_conn)
        result = await svc.promote(strat_id, version, SYSTEM_ID)
        assert result["status"] == "PROMOTED"

        # Try to reject after promotion — should fail
        with pytest.raises((QuarantineError, asyncpg.RaiseError)):
            await svc.reject(strat_id, version, SYSTEM_ID)


# ═══════════════════════════════════════════════════════════════
# CROSS-USER ISOLATION
# ═══════════════════════════════════════════════════════════════

class TestCrossUserIsolation:
    async def test_user_cannot_see_other_user_predictions(self, db_conn):
        """User A cannot read User B's predictions (RLS)."""
        from src.services.prediction_service import PredictionService
        from src.persistence.pg_strategy_repository import PgStrategyRepository, PgStrategyVersionRepository, StrategyRecord
        from src.persistence.pg_match_repository import PgMatchRepository
        from src.models.match import Match

        strat_repo = PgStrategyRepository(db_conn)
        sv_repo = PgStrategyVersionRepository(db_conn)
        strat = await strat_repo.create_strategy(StrategyRecord(
            id=uuid4(), owner_id=SYSTEM_ID, name=f"Iso_{uuid4().hex[:6]}",
            description=None, visibility="private", status="active",
        ))
        sv = await sv_repo.create_version(strat.id, {
            "name": "Iso", "metric": "xC", "market": "corners",
            "conditions": [{"field": "f", "op": ">", "value": float(hash(uuid4()) % 100)}],
            "logic": "and", "direction": "OVER", "min_odds": 1.5,
        }, SYSTEM_ID)

        match_repo = PgMatchRepository(db_conn)
        ext_id = hash(uuid4()) % 900000 + 100000
        match_id = await match_repo.upsert(Match(
            id=ext_id, date_unix=1700000000, league_id=4759, season="2023",
            home_team="A", away_team="B", home_goals=1, away_goals=1,
            total_goals=2, home_xg=1.0, away_xg=1.0, referee=None,
            over_under_line=2.5, over_odds=1.9, under_odds=2.0,
        ))

        # System creates a prediction
        svc = PredictionService(db_conn)
        pred = await svc.create_prediction(
            user_id=SYSTEM_ID, strategy_id=strat.id,
            strategy_version=sv.version, strategy_content_hash=sv.content_hash,
            match_id=match_id, match_date_unix=1700000000,
            home_team="A", away_team="B", league_id=4759,
            market_type="OVER_UNDER", direction="OVER",
            entry_odds=1.9, model_edge_pct=5.0,
            confidence=70.0, recommended_stake=0.05,
            source="PAPER_TRADE",
        )

        # Switch to user B
        user_b = await _create_user(db_conn)
        await db_conn.execute(f"SET LOCAL app.user_id = '{user_b}'")
        await db_conn.execute("SET LOCAL app.user_role = 'user'")

        # User B cannot see system's prediction
        row = await db_conn.fetchrow(
            "SELECT * FROM predictions WHERE id = $1", pred["id"]
        )
        assert row is None

    async def test_user_cannot_see_other_user_portfolio(self, db_conn):
        """User A cannot read User B's portfolio (trust test 8)."""
        pp_repo = PgPaperPortfolioRepository(db_conn)
        portfolio = await pp_repo.create(user_id=SYSTEM_ID, name=f"Private_{uuid4().hex[:6]}")

        # Switch to user B
        user_b = await _create_user(db_conn)
        await db_conn.execute(f"SET LOCAL app.user_id = '{user_b}'")
        await db_conn.execute("SET LOCAL app.user_role = 'user'")

        row = await db_conn.fetchrow(
            "SELECT * FROM paper_portfolios WHERE id = $1", portfolio["id"]
        )
        assert row is None


# ═══════════════════════════════════════════════════════════════
# REPUTATION & LEADERBOARD
# ═══════════════════════════════════════════════════════════════

class TestReputationAndLeaderboard:
    async def test_reputation_system_writable_only(self, db_conn):
        """Regular users cannot write to reputation_scores (RLS blocks with error)."""
        user = await _create_user(db_conn)

        # Switch to regular user context
        await db_conn.execute(f"SET LOCAL app.user_id = '{user}'")
        await db_conn.execute("SET LOCAL app.user_role = 'user'")

        # Attempt to insert reputation — should fail (system-only write)
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await db_conn.execute(
                """INSERT INTO reputation_scores (user_id, period_type, period_start, period_end,
                   total_predictions, settled_predictions, reputation_score)
                   VALUES ($1, '30d', '2024-01-01', '2024-01-31', 100, 80, 95.5)""",
                user,
            )

    async def test_leaderboard_readable_by_all(self, db_conn):
        """Leaderboard snapshots are readable by any authenticated user."""
        # Insert as system
        lb_repo = PgLeaderboardRepository(db_conn)
        await lb_repo.insert_snapshot(
            scope="global", period_type="30d", rank=1,
            user_id=SYSTEM_ID, display_name="System",
            score=95.0, roi_pct=10.0, win_rate=60.0, total_bets=100,
        )

        # Switch to regular user
        user = await _create_user(db_conn)
        await db_conn.execute(f"SET LOCAL app.user_id = '{user}'")
        await db_conn.execute("SET LOCAL app.user_role = 'user'")

        # User can read leaderboard
        rows = await db_conn.fetch("SELECT * FROM leaderboard_snapshots")
        assert len(rows) >= 1
