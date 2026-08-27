"""Phase 3.3 integration tests: Predictions + Settlement + Paper Ledger."""

import pytest
import asyncpg
from datetime import datetime, timezone
from uuid import uuid4, UUID

from src.persistence.pg_prediction_repository import PgPredictionRepository
from src.persistence.pg_settlement_repository import PgSettlementRepository
from src.persistence.pg_paper_repository import PgPaperPortfolioRepository, PgPaperLedgerRepository
from src.persistence.pg_match_repository import PgMatchRepository
from src.persistence.pg_strategy_repository import PgStrategyRepository, PgStrategyVersionRepository, StrategyRecord
from src.services.prediction_service import PredictionService
from src.services.settlement_service import SettlementService, SettlementError
from src.models.match import Match

pytestmark = pytest.mark.asyncio
SYSTEM_ID = UUID("00000000-0000-0000-0000-000000000001")


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


# ═══════════════════════════════════════════════════════════════
# PREDICTION CREATION
# ═══════════════════════════════════════════════════════════════

class TestPredictionCreation:
    async def test_create_prediction_with_server_proof_hash(self, db_conn):
        """Prediction is created with server-computed proof_hash (I10)."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)

        svc = PredictionService(db_conn)
        pred = await svc.create_prediction(
            user_id=SYSTEM_ID, strategy_id=strat_id,
            strategy_version=version, strategy_content_hash=content_hash,
            match_id=match_id, match_date_unix=1700000000,
            home_team="A", away_team="B", league_id=4759,
            market_type="OVER_UNDER", direction="OVER",
            entry_odds=1.90, model_edge_pct=5.0,
            confidence=75.0, recommended_stake=0.05,
            source="PAPER_TRADE",
        )
        assert pred["proof_hash"] is not None
        assert len(pred["proof_hash"]) == 64
        assert pred["status"] == "PENDING"
        assert pred["source"] == "PAPER_TRADE"

    async def test_prediction_null_odds_preserved(self, db_conn):
        """NULL entry_odds are preserved (I3: never fabricated)."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)

        svc = PredictionService(db_conn)
        pred = await svc.create_prediction(
            user_id=SYSTEM_ID, strategy_id=strat_id,
            strategy_version=version, strategy_content_hash=content_hash,
            match_id=match_id, match_date_unix=1700000000,
            home_team="X", away_team="Y", league_id=4759,
            market_type="OVER_UNDER", direction="UNDER",
            entry_odds=None, model_edge_pct=3.0,
            confidence=50.0, recommended_stake=0.01,
            source="LIVE_SIGNAL",
        )
        assert pred["entry_odds"] is None

    async def test_invalid_odds_rejected(self, db_conn):
        """entry_odds <= 1.0 rejected by CHECK constraint."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)

        repo = PgPredictionRepository(db_conn)
        with pytest.raises(asyncpg.CheckViolationError):
            await repo.create(
                prediction_id=uuid4(), user_id=SYSTEM_ID,
                strategy_id=strat_id, strategy_version=version,
                strategy_content_hash=content_hash, match_id=match_id,
                match_date_unix=1700000000, home_team="A", away_team="B",
                league_id=4759, market_type="X", direction="OVER",
                entry_odds=0.95, model_edge_pct=1.0,
                confidence=50.0, recommended_stake=0.01,
                source="PAPER_TRADE", proof_hash="a" * 64,
            )


# ═══════════════════════════════════════════════════════════════
# SETTLEMENT
# ═══════════════════════════════════════════════════════════════

class TestSettlement:
    async def _create_pending_prediction(self, db_conn) -> UUID:
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        svc = PredictionService(db_conn)
        pred = await svc.create_prediction(
            user_id=SYSTEM_ID, strategy_id=strat_id,
            strategy_version=version, strategy_content_hash=content_hash,
            match_id=match_id, match_date_unix=1700000000,
            home_team="H", away_team="A", league_id=4759,
            market_type="OVER_UNDER", direction="OVER",
            entry_odds=2.0, model_edge_pct=5.0,
            confidence=70.0, recommended_stake=0.05,
            source="PAPER_TRADE", market_line=2.5,
        )
        return pred["id"]

    async def test_settle_prediction_win(self, db_conn):
        """Settlement computes WIN outcome correctly."""
        pred_id = await self._create_pending_prediction(db_conn)
        svc = SettlementService(db_conn)
        settlement = await svc.settle_prediction(
            prediction_id=pred_id,
            actual_home_goals=2, actual_away_goals=1,  # total=3 > 2.5 → OVER wins
            stake=1.0,
        )
        assert settlement["outcome"] == "WIN"
        assert settlement["profit_loss"] == 1.0  # stake * (odds-1) = 1*(2.0-1)
        assert settlement["actual_total_goals"] == 3

    async def test_settle_prediction_loss(self, db_conn):
        """Settlement computes LOSS outcome correctly."""
        pred_id = await self._create_pending_prediction(db_conn)
        svc = SettlementService(db_conn)
        settlement = await svc.settle_prediction(
            prediction_id=pred_id,
            actual_home_goals=1, actual_away_goals=1,  # total=2 < 2.5 → OVER loses
            stake=1.0,
        )
        assert settlement["outcome"] == "LOSS"
        assert settlement["profit_loss"] == -1.0

    async def test_settlement_idempotent(self, db_conn):
        """Same prediction settled twice returns existing (I14)."""
        pred_id = await self._create_pending_prediction(db_conn)
        svc = SettlementService(db_conn)

        s1 = await svc.settle_prediction(pred_id, 3, 0, stake=1.0)
        s2 = await svc.settle_prediction(pred_id, 3, 0, stake=1.0)  # repeat

        assert s1["id"] == s2["id"]  # Same settlement returned

    async def test_backtest_prediction_cannot_be_settled(self, db_conn):
        """BACKTEST predictions rejected by settlement service (I12)."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)

        repo = PgPredictionRepository(db_conn)
        pred_id = uuid4()
        await repo.create(
            prediction_id=pred_id, user_id=SYSTEM_ID,
            strategy_id=strat_id, strategy_version=version,
            strategy_content_hash=content_hash, match_id=match_id,
            match_date_unix=1700000000, home_team="A", away_team="B",
            league_id=4759, market_type="OVER_UNDER", direction="OVER",
            entry_odds=2.0, model_edge_pct=5.0,
            confidence=70.0, recommended_stake=0.05,
            source="BACKTEST", proof_hash="b" * 64,
        )

        svc = SettlementService(db_conn)
        with pytest.raises(SettlementError, match="BACKTEST"):
            await svc.settle_prediction(pred_id, 2, 1)

    async def test_null_closing_odds_produces_null_clv(self, db_conn):
        """CLV is NULL when closing_odds unavailable (I4)."""
        pred_id = await self._create_pending_prediction(db_conn)
        svc = SettlementService(db_conn)
        # No market_prices inserted → closing_odds will be NULL
        settlement = await svc.settle_prediction(pred_id, 2, 1)
        assert settlement["closing_odds"] is None
        assert settlement["clv_pct"] is None


# ═══════════════════════════════════════════════════════════════
# SETTLEMENT IMMUTABILITY
# ═══════════════════════════════════════════════════════════════

class TestSettlementImmutability:
    async def test_settlement_update_blocked(self, db_conn):
        """UPDATE on settlements is blocked (trust test 1)."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        svc = PredictionService(db_conn)
        pred = await svc.create_prediction(
            user_id=SYSTEM_ID, strategy_id=strat_id,
            strategy_version=version, strategy_content_hash=content_hash,
            match_id=match_id, match_date_unix=1700000000,
            home_team="A", away_team="B", league_id=4759,
            market_type="OVER_UNDER", direction="OVER",
            entry_odds=2.0, model_edge_pct=5.0,
            confidence=70.0, recommended_stake=0.05,
            source="PAPER_TRADE", market_line=2.5,
        )
        settle_svc = SettlementService(db_conn)
        s = await settle_svc.settle_prediction(pred["id"], 3, 0)

        result = await db_conn.execute(
            "UPDATE settlements SET profit_loss = 999 WHERE id = $1", s["id"]
        )
        assert result == "UPDATE 0"  # RLS blocks

    async def test_settlement_delete_blocked(self, db_conn):
        """DELETE on settlements is blocked (trust test 2)."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)
        svc = PredictionService(db_conn)
        pred = await svc.create_prediction(
            user_id=SYSTEM_ID, strategy_id=strat_id,
            strategy_version=version, strategy_content_hash=content_hash,
            match_id=match_id, match_date_unix=1700000000,
            home_team="A", away_team="B", league_id=4759,
            market_type="OVER_UNDER", direction="OVER",
            entry_odds=2.0, model_edge_pct=5.0,
            confidence=70.0, recommended_stake=0.05,
            source="PAPER_TRADE", market_line=2.5,
        )
        settle_svc = SettlementService(db_conn)
        s = await settle_svc.settle_prediction(pred["id"], 3, 0)

        result = await db_conn.execute(
            "DELETE FROM settlements WHERE id = $1", s["id"]
        )
        assert result == "DELETE 0"  # RLS blocks


# ═══════════════════════════════════════════════════════════════
# PAPER LEDGER TRUST
# ═══════════════════════════════════════════════════════════════

class TestPaperLedgerTrust:
    async def test_ledger_update_blocked(self, db_conn):
        """UPDATE on paper_ledger_entries is blocked (trust test 3)."""
        repo = PgPaperPortfolioRepository(db_conn)
        ledger = PgPaperLedgerRepository(db_conn)

        portfolio = await repo.create(user_id=SYSTEM_ID, name=f"Trust_{uuid4().hex[:6]}")
        entry_id = await ledger.append(
            portfolio_id=portfolio["id"], entry_type="OPENING_BALANCE",
            amount=1000.0, balance_after=1000.0,
        )

        result = await db_conn.execute(
            "UPDATE paper_ledger_entries SET amount = 999999 WHERE id = $1", entry_id
        )
        assert result == "UPDATE 0"  # RLS blocks

    async def test_ledger_delete_blocked(self, db_conn):
        """DELETE on paper_ledger_entries is blocked (trust test 4)."""
        repo = PgPaperPortfolioRepository(db_conn)
        ledger = PgPaperLedgerRepository(db_conn)

        portfolio = await repo.create(user_id=SYSTEM_ID, name=f"Del_{uuid4().hex[:6]}")
        entry_id = await ledger.append(
            portfolio_id=portfolio["id"], entry_type="OPENING_BALANCE",
            amount=500.0, balance_after=500.0,
        )

        result = await db_conn.execute(
            "DELETE FROM paper_ledger_entries WHERE id = $1", entry_id
        )
        assert result == "DELETE 0"  # RLS blocks

    async def test_ledger_balance_reconstruction(self, db_conn):
        """Ledger entries allow balance reconstruction."""
        repo = PgPaperPortfolioRepository(db_conn)
        ledger = PgPaperLedgerRepository(db_conn)

        portfolio = await repo.create(user_id=SYSTEM_ID, name=f"Recon_{uuid4().hex[:6]}",
                                      initial_balance=1000.0)
        await ledger.append(portfolio["id"], "OPENING_BALANCE", 1000.0, 1000.0)
        await ledger.append(portfolio["id"], "BET_SETTLED", 50.0, 1050.0)
        await ledger.append(portfolio["id"], "BET_SETTLED", -30.0, 1020.0)

        entries = await ledger.get_by_portfolio(portfolio["id"])
        assert len(entries) == 3
        # Reconstruct: 1000 + 50 - 30 = 1020
        total = sum(e["amount"] for e in entries)
        assert total == 1020.0
        assert entries[-1]["balance_after"] == 1020.0

    async def test_settlement_creates_ledger_entry(self, db_conn):
        """Settlement atomically creates a ledger entry when portfolio specified."""
        strat_id, version, content_hash = await _setup_strategy(db_conn)
        match_id = await _setup_match(db_conn)

        # Create portfolio
        pp_repo = PgPaperPortfolioRepository(db_conn)
        portfolio = await pp_repo.create(user_id=SYSTEM_ID, name=f"Settle_{uuid4().hex[:6]}")
        ledger = PgPaperLedgerRepository(db_conn)
        await ledger.append(portfolio["id"], "OPENING_BALANCE", 1000.0, 1000.0)

        # Create prediction
        svc = PredictionService(db_conn)
        pred = await svc.create_prediction(
            user_id=SYSTEM_ID, strategy_id=strat_id,
            strategy_version=version, strategy_content_hash=content_hash,
            match_id=match_id, match_date_unix=1700000000,
            home_team="H", away_team="A", league_id=4759,
            market_type="OVER_UNDER", direction="OVER",
            entry_odds=2.0, model_edge_pct=5.0,
            confidence=70.0, recommended_stake=0.05,
            source="PAPER_TRADE", market_line=2.5,
        )

        # Settle with portfolio
        settle_svc = SettlementService(db_conn)
        await settle_svc.settle_prediction(
            pred["id"], 3, 0, stake=1.0, portfolio_id=portfolio["id"]
        )

        # Check ledger has entry
        entries = await ledger.get_by_portfolio(portfolio["id"])
        assert len(entries) == 2  # OPENING + BET_SETTLED
        assert entries[1]["entry_type"] == "BET_SETTLED"
        assert entries[1]["amount"] == 1.0  # WIN: stake*(odds-1) = 1*(2-1)
