"""Integration tests for backtest_runs and backtest_bets."""

import pytest
import asyncpg
from uuid import uuid4, UUID

from src.persistence.pg_backtest_repository import PgBacktestRunRepository, PgBacktestBetRepository
from src.persistence.pg_provenance_repository import (
    PgDatasetVersionRepository, PgFeatureVersionRepository, PgModelVersionRepository,
)
from src.persistence.pg_strategy_repository import (
    PgStrategyRepository, PgStrategyVersionRepository, StrategyRecord,
)
from src.persistence.hashing import compute_backtest_run_hash


pytestmark = pytest.mark.asyncio

SYSTEM_ID = UUID("00000000-0000-0000-0000-000000000001")


async def _build_provenance(db_conn) -> dict:
    """Create full provenance chain and return all IDs."""
    ds_repo = PgDatasetVersionRepository(db_conn)
    ds = await ds_repo.create("test", 4759, "2023", list(range(3000, 3020)),
                              1700000000, 1700200000, SYSTEM_ID)

    fv_repo = PgFeatureVersionRepository(db_conn)
    fv = await fv_repo.create(ds["id"], 5, 6, 5, created_by=SYSTEM_ID)

    strat_repo = PgStrategyRepository(db_conn)
    strat = await strat_repo.create_strategy(StrategyRecord(
        id=uuid4(), owner_id=SYSTEM_ID, name="BT Test",
        description=None, visibility="private", status="active",
    ))
    sv_repo = PgStrategyVersionRepository(db_conn)
    sv = await sv_repo.create_version(strat.id, {
        "name": "BT Test", "metric": "xC", "market": "corners",
        "conditions": [{"field": "f", "op": ">", "value": 2.0}],
        "logic": "and", "direction": "OVER", "min_odds": 1.5,
    }, SYSTEM_ID)

    mv_repo = PgModelVersionRepository(db_conn)
    mv = await mv_repo.create(strat.id, sv.version, sv.content_hash,
                              fv["id"], 200, 50, 50, 1.5, 5.0, SYSTEM_ID)

    return {
        "dataset_id": ds["id"], "feature_version_id": fv["id"],
        "model_version_id": mv["id"], "strategy_id": strat.id,
        "strategy_version": sv.version, "strategy_content_hash": sv.content_hash,
    }


async def _insert_match(db_conn, external_id: int) -> int:
    row = await db_conn.fetchrow(
        """INSERT INTO matches (external_id, external_source, date_unix, league_id, season,
           home_team, away_team, home_goals, away_goals)
           VALUES ($1, 'footystats', 1700000000, 4759, '2023', 'H', 'A', 1, 1)
           ON CONFLICT (external_source, external_id) DO UPDATE SET home_goals = EXCLUDED.home_goals
           RETURNING match_id""", external_id)
    return row["match_id"]


class TestBacktestRuns:
    """Test backtest run lifecycle and deduplication."""

    async def test_create_run(self, db_conn):
        """Basic run creation in RUNNING status."""
        prov = await _build_provenance(db_conn)
        repo = PgBacktestRunRepository(db_conn)

        run = await repo.create(
            user_id=SYSTEM_ID, **{k: prov[k] for k in [
                "strategy_id", "strategy_version", "strategy_content_hash",
                "dataset_id", "feature_version_id", "model_version_id",
            ]}, config={"train_window": 200, "test_window": 50},
        )
        assert run["status"] == "RUNNING"
        assert run["total_bets"] is None
        assert run["content_hash"] == compute_backtest_run_hash(
            str(prov["model_version_id"]), str(prov["dataset_id"])
        )

    async def test_complete_run(self, db_conn):
        """Run transitions from RUNNING to COMPLETED with metrics."""
        prov = await _build_provenance(db_conn)
        repo = PgBacktestRunRepository(db_conn)

        run = await repo.create(user_id=SYSTEM_ID, **{k: prov[k] for k in [
            "strategy_id", "strategy_version", "strategy_content_hash",
            "dataset_id", "feature_version_id", "model_version_id",
        ]}, config={})

        completed = await repo.complete(
            run_id=run["id"], total_bets=50, net_roi_pct=5.2,
            win_rate=55.0, max_drawdown_pct=12.0, avg_model_edge_pct=3.1,
            total_profit_loss=26.0, total_staked=500.0, n_folds=4,
        )
        assert completed["status"] == "COMPLETED"
        assert completed["total_bets"] == 50
        assert completed["net_roi_pct"] == 5.2
        assert completed["completed_at"] is not None

    async def test_same_user_dedup(self, db_conn):
        """Same user + same content_hash raises UniqueViolation."""
        prov = await _build_provenance(db_conn)
        repo = PgBacktestRunRepository(db_conn)

        await repo.create(user_id=SYSTEM_ID, **{k: prov[k] for k in [
            "strategy_id", "strategy_version", "strategy_content_hash",
            "dataset_id", "feature_version_id", "model_version_id",
        ]}, config={})

        with pytest.raises(asyncpg.UniqueViolationError):
            await repo.create(user_id=SYSTEM_ID, **{k: prov[k] for k in [
                "strategy_id", "strategy_version", "strategy_content_hash",
                "dataset_id", "feature_version_id", "model_version_id",
            ]}, config={})

    async def test_different_users_allowed(self, db_conn):
        """Different users can independently run the same configuration."""
        prov = await _build_provenance(db_conn)
        repo = PgBacktestRunRepository(db_conn)

        # Create second user
        user2 = uuid4()
        await db_conn.execute(
            "INSERT INTO users (id, username, display_name, role, status) VALUES ($1, $2, $2, 'user', 'active')",
            user2, f"user_{uuid4().hex[:8]}",
        )

        await repo.create(user_id=SYSTEM_ID, **{k: prov[k] for k in [
            "strategy_id", "strategy_version", "strategy_content_hash",
            "dataset_id", "feature_version_id", "model_version_id",
        ]}, config={})

        # Same config, different user — should succeed
        run2 = await repo.create(user_id=user2, **{k: prov[k] for k in [
            "strategy_id", "strategy_version", "strategy_content_hash",
            "dataset_id", "feature_version_id", "model_version_id",
        ]}, config={})
        assert run2["user_id"] == user2

    async def test_completed_run_immutable(self, db_conn):
        """COMPLETED runs cannot be further modified."""
        prov = await _build_provenance(db_conn)
        repo = PgBacktestRunRepository(db_conn)

        run = await repo.create(user_id=SYSTEM_ID, **{k: prov[k] for k in [
            "strategy_id", "strategy_version", "strategy_content_hash",
            "dataset_id", "feature_version_id", "model_version_id",
        ]}, config={})

        await repo.complete(run["id"], 10, 3.0, 60.0, 5.0, 2.0, 15.0, 500.0, 2)

        # Try to modify completed run — trigger should block
        with pytest.raises(asyncpg.RaiseError, match="COMPLETED"):
            await db_conn.execute(
                "UPDATE backtest_runs SET total_bets = 999 WHERE id = $1", run["id"]
            )

    async def test_provenance_query(self, db_conn):
        """Full provenance chain is queryable from a run."""
        prov = await _build_provenance(db_conn)
        repo = PgBacktestRunRepository(db_conn)

        run = await repo.create(user_id=SYSTEM_ID, **{k: prov[k] for k in [
            "strategy_id", "strategy_version", "strategy_content_hash",
            "dataset_id", "feature_version_id", "model_version_id",
        ]}, config={})

        chain = await repo.get_provenance(run["id"])
        assert chain is not None
        assert chain["run_id"] == run["id"]
        assert chain["model_version_id"] == prov["model_version_id"]
        assert chain["feature_version_id"] == prov["feature_version_id"]
        assert chain["dataset_id"] == prov["dataset_id"]
        assert chain["strategy_content_hash"] == prov["strategy_content_hash"]


class TestBacktestBets:
    """Test backtest bet records."""

    async def _create_run(self, db_conn) -> UUID:
        prov = await _build_provenance(db_conn)
        repo = PgBacktestRunRepository(db_conn)
        run = await repo.create(user_id=SYSTEM_ID, **{k: prov[k] for k in [
            "strategy_id", "strategy_version", "strategy_content_hash",
            "dataset_id", "feature_version_id", "model_version_id",
        ]}, config={})
        return run["id"]

    async def test_insert_bet(self, db_conn):
        """Basic bet insertion succeeds."""
        run_id = await self._create_run(db_conn)
        match_id = await _insert_match(db_conn, 70001)
        repo = PgBacktestBetRepository(db_conn)

        bet_id = await repo.insert(
            run_id=run_id, match_id=match_id, fold_index=0,
            strategy_name="Test", direction="OVER", odds=2.10,
            stake=1.0, outcome="WIN", profit_loss=1.10,
            model_edge_pct=5.0, clv_pct=None,
        )
        assert bet_id > 0

    async def test_null_clv_preserved(self, db_conn):
        """NULL CLV is stored as-is, never fabricated."""
        run_id = await self._create_run(db_conn)
        match_id = await _insert_match(db_conn, 70002)
        repo = PgBacktestBetRepository(db_conn)

        await repo.insert(
            run_id=run_id, match_id=match_id, fold_index=0,
            strategy_name="Test", direction="UNDER", odds=1.85,
            stake=1.0, outcome="LOSS", profit_loss=-1.0,
            model_edge_pct=3.0, clv_pct=None,
        )

        bets = await repo.get_by_run(run_id)
        assert len(bets) == 1
        assert bets[0]["clv_pct"] is None

    async def test_batch_insert(self, db_conn):
        """Batch insertion of multiple bets."""
        run_id = await self._create_run(db_conn)
        match_id = await _insert_match(db_conn, 70003)
        repo = PgBacktestBetRepository(db_conn)

        bets = [
            {"match_id": match_id, "fold_index": 0, "strategy_name": "S1",
             "direction": "OVER", "odds": 2.0, "stake": 1.0,
             "outcome": "WIN", "profit_loss": 1.0, "model_edge_pct": 4.0},
            {"match_id": match_id, "fold_index": 0, "strategy_name": "S1",
             "direction": "UNDER", "odds": 1.9, "stake": 1.0,
             "outcome": "LOSS", "profit_loss": -1.0, "model_edge_pct": 3.0},
        ]
        count = await repo.insert_batch(run_id, bets)
        assert count == 2
        assert await repo.count_by_run(run_id) == 2

    async def test_immutability_update_blocked(self, db_conn):
        """UPDATE on backtest_bets is blocked."""
        run_id = await self._create_run(db_conn)
        match_id = await _insert_match(db_conn, 70004)
        repo = PgBacktestBetRepository(db_conn)

        bet_id = await repo.insert(
            run_id=run_id, match_id=match_id, fold_index=0,
            strategy_name="T", direction="OVER", odds=2.0,
            stake=1.0, outcome="WIN", profit_loss=1.0, model_edge_pct=5.0,
        )

        result = await db_conn.execute(
            "UPDATE backtest_bets SET profit_loss = 999.0 WHERE id = $1", bet_id
        )
        assert result == "UPDATE 0"  # RLS blocks


class TestCrossUserIsolation:
    """Verify user A cannot access user B's backtest data."""

    async def test_user_cannot_see_other_user_runs(self, db_conn):
        """RLS prevents cross-user access to backtest_runs."""
        prov = await _build_provenance(db_conn)

        # Create user B
        user_b = uuid4()
        await db_conn.execute(
            "INSERT INTO users (id, username, display_name, role, status) VALUES ($1, $2, $2, 'user', 'active')",
            user_b, f"userb_{uuid4().hex[:8]}",
        )

        # System creates a run
        repo = PgBacktestRunRepository(db_conn)
        run = await repo.create(user_id=SYSTEM_ID, **{k: prov[k] for k in [
            "strategy_id", "strategy_version", "strategy_content_hash",
            "dataset_id", "feature_version_id", "model_version_id",
        ]}, config={})

        # Switch to user B context
        await db_conn.execute(f"SET LOCAL app.user_id = '{user_b}'")
        await db_conn.execute("SET LOCAL app.user_role = 'user'")

        # User B cannot see system's run
        result = await db_conn.fetchrow(
            "SELECT * FROM backtest_runs WHERE id = $1", run["id"]
        )
        assert result is None

    async def test_user_cannot_see_other_user_bets(self, db_conn):
        """RLS prevents cross-user access to backtest_bets via parent run."""
        prov = await _build_provenance(db_conn)
        repo = PgBacktestRunRepository(db_conn)
        bet_repo = PgBacktestBetRepository(db_conn)

        run = await repo.create(user_id=SYSTEM_ID, **{k: prov[k] for k in [
            "strategy_id", "strategy_version", "strategy_content_hash",
            "dataset_id", "feature_version_id", "model_version_id",
        ]}, config={})
        match_id = await _insert_match(db_conn, 70010)
        await bet_repo.insert(run["id"], match_id, 0, "S", "OVER", 2.0, 1.0, "WIN", 1.0, 5.0)

        # Create and switch to user B
        user_b = uuid4()
        await db_conn.execute(
            "INSERT INTO users (id, username, display_name, role, status) VALUES ($1, $2, $2, 'user', 'active')",
            user_b, f"userb2_{uuid4().hex[:8]}",
        )
        await db_conn.execute(f"SET LOCAL app.user_id = '{user_b}'")
        await db_conn.execute("SET LOCAL app.user_role = 'user'")

        # User B cannot see bets
        bets = await db_conn.fetch(
            "SELECT * FROM backtest_bets WHERE run_id = $1", run["id"]
        )
        assert len(bets) == 0
