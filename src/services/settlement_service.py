"""Settlement service — atomic prediction resolution.

Ensures:
- Settlement outcome computed by SettlementFactory._resolve_outcome() (I11)
- Closing odds sourced from market_prices, never client (I9)
- CLV is NULL when closing_odds unavailable (I4)
- P&L computed by Settlement.compute_profit_loss()
- Settlement is idempotent: UNIQUE(prediction_id) (I14)
- BACKTEST predictions cannot be settled via this path (I12)
- Paper ledger + portfolio update is ATOMIC with settlement
- Event log emitted in same transaction

Transaction flow:
    BEGIN
      1. Load prediction (verify PENDING + not BACKTEST)
      2. Load closing odds from market_prices
      3. Compute outcome (SettlementFactory._resolve_outcome)
      4. Compute P&L (Settlement.compute_profit_loss)
      5. Compute CLV (Settlement.compute_clv)
      6. INSERT settlement
      7. UPDATE prediction status
      8. INSERT paper_ledger_entry
      9. UPDATE paper_portfolio.current_balance
      9b. UPDATE quarantine_entries.paper_pnl/paper_bets (PAPER_TRADE only)
      10. Emit event
    COMMIT
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

import asyncpg

from src.domain.settlement import Settlement, SettlementOutcome
from src.domain.factories import SettlementFactory
from src.persistence.events import EventService, EventTypes
from src.persistence.pg_market_price_repository import PgMarketPriceRepository
from src.persistence.pg_paper_repository import PgPaperLedgerRepository, PgPaperPortfolioRepository
from src.persistence.pg_prediction_repository import PgPredictionRepository
from src.persistence.pg_quarantine_repository import PgQuarantineRepository
from src.persistence.pg_settlement_repository import PgSettlementRepository


class SettlementError(Exception):
    """Raised when settlement cannot proceed."""
    pass


class SettlementService:
    """Atomic settlement of predictions against match results."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def settle_prediction(
        self,
        prediction_id: UUID,
        actual_home_goals: int,
        actual_away_goals: int,
        stake: float = 1.0,
        portfolio_id: Optional[UUID] = None,
    ) -> dict:
        """Settle a single prediction against actual match result.

        Closing odds are loaded from market_prices (never client-supplied).
        Outcome is computed by SettlementFactory (never client-supplied).

        Args:
            prediction_id: The prediction to settle.
            actual_home_goals: Authoritative home goals.
            actual_away_goals: Authoritative away goals.
            stake: Stake amount for P&L calculation.
            portfolio_id: Optional paper portfolio for ledger entry.

        Returns:
            The created settlement record.

        Raises:
            SettlementError: If prediction not found, not PENDING, or is BACKTEST.
        """
        pred_repo = PgPredictionRepository(self._conn)
        settle_repo = PgSettlementRepository(self._conn)

        # 1. Load prediction
        prediction = await pred_repo.get_by_id(prediction_id)
        if not prediction:
            raise SettlementError(f"Prediction {prediction_id} not found")

        # IDEMPOTENCY CHECK (I14): already settled?
        existing = await settle_repo.get_by_prediction_id(prediction_id)
        if existing:
            return existing  # Return existing settlement — no side effects

        # Verify eligibility
        if prediction["status"] != "PENDING":
            raise SettlementError(
                f"Prediction {prediction_id} is {prediction['status']}, not PENDING"
            )

        # I12: BACKTEST predictions cannot enter live settlement
        if prediction["source"] == "BACKTEST":
            raise SettlementError(
                "BACKTEST predictions cannot be settled via live settlement path"
            )

        actual_total_goals = actual_home_goals + actual_away_goals

        # 2. Load closing odds from market_prices (I9: never client-supplied)
        closing_odds = await self._get_closing_odds(
            prediction["match_id"],
            prediction["market_type"],
            prediction["direction"],
        )

        # 3. Compute outcome (I11: server-derived)
        outcome = SettlementFactory._resolve_outcome(
            direction=prediction["direction"],
            market_line=prediction["market_line"],
            actual_total_goals=actual_total_goals,
        )

        # 4. Compute P&L
        entry_odds = prediction["entry_odds"]
        profit_loss = Settlement.compute_profit_loss(
            outcome=outcome,
            odds=entry_odds,
            stake=stake,
        )

        # 5. Compute CLV (I4: NULL if closing_odds unavailable)
        clv_pct = Settlement.compute_clv(entry_odds, closing_odds)

        # 6. INSERT settlement
        settlement_id = uuid4()
        now = datetime.now(timezone.utc)
        actual_result = f"{actual_home_goals}-{actual_away_goals}"

        settlement = await settle_repo.create(
            settlement_id=settlement_id,
            prediction_id=prediction_id,
            match_id=prediction["match_id"],
            outcome=outcome.value,
            actual_total_goals=actual_total_goals,
            actual_result=actual_result,
            entry_odds=entry_odds,
            closing_odds=closing_odds,
            clv_pct=clv_pct,
            stake=stake,
            profit_loss=profit_loss,
            settled_at=now,
        )

        # 7. UPDATE prediction status
        status_map = {
            SettlementOutcome.WIN: "SETTLED_WIN",
            SettlementOutcome.LOSS: "SETTLED_LOSS",
            SettlementOutcome.VOID: "SETTLED_VOID",
            SettlementOutcome.PUSH: "SETTLED_VOID",
        }
        await pred_repo.mark_settled(prediction_id, status_map[outcome])

        # 8-9. Paper ledger + portfolio update (if portfolio specified)
        if portfolio_id:
            await self._update_paper_portfolio(
                portfolio_id, prediction_id, settlement_id, profit_loss, stake,
                prediction["direction"], outcome.value,
            )

        # 9b. Quarantine paper P&L (drives the 90-day promotion gate). Only
        # PAPER_TRADE predictions count; VOID/PUSH carry no P&L impact.
        if prediction["source"] == "PAPER_TRADE" and outcome not in (
            SettlementOutcome.VOID, SettlementOutcome.PUSH,
        ):
            await PgQuarantineRepository(self._conn).update_paper_pnl(
                strategy_id=prediction["strategy_id"],
                strategy_version=prediction["strategy_version"],
                pnl_delta=profit_loss,
                bets_delta=1,
            )

        # 10. Emit event
        await EventService(self._conn).emit(
            event_type=EventTypes.PREDICTION_SETTLED,
            aggregate_type="prediction",
            aggregate_id=str(prediction_id),
            actor_type="service",
            payload={
                "settlement_id": str(settlement_id),
                "outcome": outcome.value,
                "profit_loss": profit_loss,
                "clv_pct": clv_pct,
            },
        )

        return settlement

    async def _get_closing_odds(
        self, match_id: int, market_type: str, direction: str
    ) -> Optional[float]:
        """Retrieve authoritative closing odds from market_prices.

        Returns None if unavailable (I4: never fabricated).
        """
        mp_repo = PgMarketPriceRepository(self._conn)
        return await mp_repo.get_closing_price(match_id, market_type, direction)

    async def _update_paper_portfolio(
        self,
        portfolio_id: UUID,
        prediction_id: UUID,
        settlement_id: UUID,
        profit_loss: float,
        stake: float,
        direction: str,
        outcome: str,
    ) -> None:
        """Append ledger entry and update cached balance atomically."""
        ledger_repo = PgPaperLedgerRepository(self._conn)
        portfolio_repo = PgPaperPortfolioRepository(self._conn)

        # Dedup: check if settlement already has a ledger entry
        if await ledger_repo.has_settlement_entry(settlement_id):
            return

        # Get current balance
        current_balance = await ledger_repo.get_latest_balance(portfolio_id)
        if current_balance is None:
            portfolio = await portfolio_repo.get_by_id(portfolio_id)
            current_balance = portfolio["current_balance"] if portfolio else 0.0

        new_balance = current_balance + profit_loss

        # Append ledger entry
        await ledger_repo.append(
            portfolio_id=portfolio_id,
            entry_type="BET_SETTLED",
            amount=profit_loss,
            balance_after=new_balance,
            prediction_id=prediction_id,
            settlement_id=settlement_id,
            metadata={
                "direction": direction,
                "outcome": outcome,
                "stake": stake,
            },
        )

        # Update cached balance
        await portfolio_repo.update_balance(portfolio_id, new_balance)
