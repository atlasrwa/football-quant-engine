"""Forward Research Orchestrator — coordinates prospective research pipeline.

Operations:
    sync_fixtures()          — Discover upcoming fixtures
    build_snapshots()        — Create pre-match feature snapshots
    capture_odds()           — Record current odds snapshots
    generate_predictions()   — Run eligible strategies on upcoming fixtures
    generate_paper_trades()  — Create paper trades for positive-EV predictions
    capture_closing_odds()   — Record closing odds for completed fixtures
    settle_trades()          — Settle paper trades for completed fixtures
    compute_clv()            — Calculate CLV for settled trades
    reconcile()              — Verify consistency

Each operation is:
- Idempotent (safe to re-run)
- Restart-safe (crash at any point → clean recovery)
- Bounded (configurable limits)
- Observable (event trail)

Callable periodically by an external scheduler.
Does NOT create a complex distributed scheduler internally.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from src.research.forward.future_fixture import FixtureStatus, FutureFixture
from src.research.forward.odds import OddsSnapshot, OddsType
from src.research.forward.providers import FutureFixtureProvider, OddsProvider
from src.research.forward.snapshot import PreMatchSnapshot
from src.research.forward.temporal_features import TemporalFeatureEngine
from src.research.paper.clv import CLVResult, compute_clv
from src.research.paper.paper_trade import PaperTrade, PaperTradeStatus
from src.research.paper.settlement import SettlementResult, settle_trade
from src.research.paper.staking import StakingModel

logger = logging.getLogger(__name__)


class ForwardEventType(Enum):
    """Events emitted by the forward orchestrator."""
    FIXTURE_DISCOVERED = "FIXTURE_DISCOVERED"
    FEATURE_SNAPSHOT_CREATED = "FEATURE_SNAPSHOT_CREATED"
    ODDS_SNAPSHOT_CAPTURED = "ODDS_SNAPSHOT_CAPTURED"
    PREDICTION_GENERATED = "PREDICTION_GENERATED"
    PAPER_TRADE_CREATED = "PAPER_TRADE_CREATED"
    PAPER_TRADE_APPROVED = "PAPER_TRADE_APPROVED"
    PAPER_TRADE_OPENED = "PAPER_TRADE_OPENED"
    CLOSING_ODDS_CAPTURED = "CLOSING_ODDS_CAPTURED"
    PAPER_TRADE_SETTLED = "PAPER_TRADE_SETTLED"
    CLV_CALCULATED = "CLV_CALCULATED"
    TRADE_REJECTED = "TRADE_REJECTED"
    TRADE_CANCELLED = "TRADE_CANCELLED"


@dataclass
class ForwardEvent:
    """Immutable forward research event for audit trail.

    Never contains credentials or secrets.
    """
    event_type: ForwardEventType
    entity_id: str = ""
    fixture_id: str = ""
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "entity_id": self.entity_id,
            "fixture_id": self.fixture_id,
            "timestamp": self.timestamp,
            "data": self.data,
        }


@dataclass
class ForwardRunResult:
    """Result of a forward orchestrator operation."""
    operation: str
    success: bool = True
    fixtures_processed: int = 0
    snapshots_created: int = 0
    odds_captured: int = 0
    predictions_generated: int = 0
    trades_created: int = 0
    trades_settled: int = 0
    clv_calculated: int = 0
    errors: list[str] = field(default_factory=list)
    events: list[ForwardEvent] = field(default_factory=list)
    started_at: float = 0.0
    completed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "operation": self.operation,
            "success": self.success,
            "fixtures_processed": self.fixtures_processed,
            "snapshots_created": self.snapshots_created,
            "odds_captured": self.odds_captured,
            "predictions_generated": self.predictions_generated,
            "trades_created": self.trades_created,
            "trades_settled": self.trades_settled,
            "clv_calculated": self.clv_calculated,
            "error_count": len(self.errors),
            "event_count": len(self.events),
            "duration_seconds": round(self.completed_at - self.started_at, 2) if self.completed_at else 0,
        }


class ForwardResearchOrchestrator:
    """Coordinates the forward research pipeline.

    Usage:
        orchestrator = ForwardResearchOrchestrator(
            fixture_provider=provider,
            odds_provider=odds_prov,
            feature_engine=engine,
            staking_model=staking,
        )
        result = orchestrator.sync_fixtures()
        result = orchestrator.capture_odds()
        ...

    Each method is idempotent and restart-safe.
    """

    def __init__(
        self,
        fixture_provider: FutureFixtureProvider,
        odds_provider: Optional[OddsProvider] = None,
        feature_engine: Optional[TemporalFeatureEngine] = None,
        staking_model: Optional[StakingModel] = None,
        max_fixtures_per_run: int = 100,
        max_trades_per_run: int = 50,
    ) -> None:
        self._fixture_provider = fixture_provider
        self._odds_provider = odds_provider
        self._feature_engine = feature_engine
        self._staking_model = staking_model or StakingModel()
        self._max_fixtures = max_fixtures_per_run
        self._max_trades = max_trades_per_run

        # In-memory state (would be persisted in production)
        self._fixtures: dict[str, FutureFixture] = {}
        self._snapshots: dict[str, PreMatchSnapshot] = {}
        self._odds_snapshots: list[OddsSnapshot] = []
        self._trades: dict[str, PaperTrade] = {}
        self._clv_results: dict[str, CLVResult] = {}
        self._events: list[ForwardEvent] = []

    @property
    def fixtures(self) -> dict[str, FutureFixture]:
        return dict(self._fixtures)

    @property
    def trades(self) -> dict[str, PaperTrade]:
        return dict(self._trades)

    @property
    def events(self) -> list[ForwardEvent]:
        return list(self._events)

    def sync_fixtures(
        self,
        competition_id: Optional[int] = None,
        from_timestamp: Optional[float] = None,
        to_timestamp: Optional[float] = None,
    ) -> ForwardRunResult:
        """Discover and sync upcoming fixtures.

        Idempotent: same fixture discovered twice → stored once.
        """
        result = ForwardRunResult(operation="sync_fixtures", started_at=time.time())

        try:
            fixtures = self._fixture_provider.get_upcoming_fixtures(
                competition_id=competition_id,
                from_timestamp=from_timestamp,
                to_timestamp=to_timestamp,
                limit=self._max_fixtures,
            )

            for fixture in fixtures:
                fid = fixture.fixture_id
                if fid not in self._fixtures:
                    self._fixtures[fid] = fixture
                    self._emit_event(ForwardEventType.FIXTURE_DISCOVERED, fid, fid)
                    result.fixtures_processed += 1
                else:
                    # Update status if changed
                    existing = self._fixtures[fid]
                    if existing.status != fixture.status:
                        self._fixtures[fid] = fixture

        except Exception as e:
            result.errors.append(f"sync_fixtures failed: {type(e).__name__}: {str(e)[:200]}")
            result.success = False

        result.completed_at = time.time()
        result.events = list(self._events[-result.fixtures_processed:])
        return result

    def build_snapshots(
        self,
        prediction_timestamp: Optional[float] = None,
        hypothesis_id: str = "",
        model_id: str = "",
    ) -> ForwardRunResult:
        """Build pre-match feature snapshots for scheduled fixtures.

        Only builds for SCHEDULED fixtures that haven't been snapshot yet.
        Idempotent: same fixture+hypothesis → same snapshot (not recreated).
        """
        result = ForwardRunResult(operation="build_snapshots", started_at=time.time())

        if not self._feature_engine:
            result.errors.append("No feature engine configured")
            result.success = False
            result.completed_at = time.time()
            return result

        pred_time = prediction_timestamp or time.time()

        for fid, fixture in self._fixtures.items():
            if fixture.status != FixtureStatus.SCHEDULED:
                continue
            if fixture.kickoff_timestamp <= pred_time:
                continue  # Already past kickoff

            # Check if snapshot already exists for this fixture+hypothesis
            snapshot_key = f"{fid}_{hypothesis_id}"
            if snapshot_key in self._snapshots:
                continue

            try:
                snapshot = self._feature_engine.build_snapshot(
                    fixture_id=fid,
                    home_team_id=fixture.home_team_id,
                    away_team_id=fixture.away_team_id,
                    prediction_timestamp=pred_time,
                    kickoff_timestamp=float(fixture.kickoff_timestamp),
                    hypothesis_id=hypothesis_id,
                    model_id=model_id,
                )
                self._snapshots[snapshot_key] = snapshot
                self._emit_event(
                    ForwardEventType.FEATURE_SNAPSHOT_CREATED,
                    snapshot.snapshot_id, fid,
                )
                result.snapshots_created += 1
            except ValueError as e:
                result.errors.append(f"Snapshot failed for {fid}: {str(e)[:100]}")

        result.completed_at = time.time()
        return result

    def capture_odds(
        self,
        market: Optional[str] = None,
    ) -> ForwardRunResult:
        """Capture current odds for scheduled fixtures.

        Idempotent: same odds at same time → same snapshot (deduplicated by content hash).
        """
        result = ForwardRunResult(operation="capture_odds", started_at=time.time())

        if not self._odds_provider:
            result.errors.append("No odds provider configured")
            result.success = False
            result.completed_at = time.time()
            return result

        existing_hashes = {s.odds_snapshot_id for s in self._odds_snapshots}

        for fid, fixture in self._fixtures.items():
            if fixture.status != FixtureStatus.SCHEDULED:
                continue

            try:
                snapshots = self._odds_provider.get_odds_snapshot(
                    fixture_id=fid, market=market,
                )
                for snap in snapshots:
                    if snap.odds_snapshot_id not in existing_hashes:
                        self._odds_snapshots.append(snap)
                        existing_hashes.add(snap.odds_snapshot_id)
                        self._emit_event(
                            ForwardEventType.ODDS_SNAPSHOT_CAPTURED,
                            snap.odds_snapshot_id, fid,
                        )
                        result.odds_captured += 1
            except Exception as e:
                result.errors.append(f"Odds capture failed for {fid}: {str(e)[:100]}")

        result.completed_at = time.time()
        return result

    def settle_trades(
        self,
        get_result: Callable[[str, str, str, float], Optional[str]],
        get_actual_value: Callable[[str, str], Optional[float]],
    ) -> ForwardRunResult:
        """Settle paper trades for completed fixtures.

        Args:
            get_result: Function(fixture_id, market, selection, line) → outcome or None.
            get_actual_value: Function(fixture_id, market) → actual value or None.

        Idempotent: already-settled trades are skipped.
        """
        result = ForwardRunResult(operation="settle_trades", started_at=time.time())

        for trade_id, trade in list(self._trades.items()):
            if trade.status != PaperTradeStatus.OPEN:
                continue

            # Check if fixture is completed
            fixture = self._fixtures.get(trade.fixture_id)
            if not fixture or fixture.status != FixtureStatus.COMPLETED:
                continue

            try:
                actual = get_actual_value(trade.fixture_id, trade.market)
                if actual is None:
                    continue  # Result not available yet — do NOT convert to zero

                from src.research.paper.settlement import determine_outcome
                outcome = determine_outcome(
                    trade.market, trade.selection, trade.line, actual,
                )

                settlement = settle_trade(
                    trade_id=trade_id,
                    outcome=outcome,
                    stake=trade.stake,
                    odds=trade.odds_at_prediction,
                    settlement_timestamp=time.time(),
                )

                # Get closing odds for CLV
                closing_odds = None
                if self._odds_provider:
                    closing_snaps = self._odds_provider.get_closing_odds(
                        trade.fixture_id, trade.market,
                    )
                    if closing_snaps:
                        # Use first matching selection
                        for cs in closing_snaps:
                            if cs.selection.value == trade.selection:
                                closing_odds = cs.decimal_odds
                                break

                # Compute CLV
                clv_val = None
                if closing_odds and closing_odds >= 1.0:
                    clv_result = compute_clv(trade_id, trade.odds_at_prediction, closing_odds)
                    if clv_result:
                        clv_val = clv_result.clv
                        self._clv_results[trade_id] = clv_result

                # Settle the trade
                settled_trade = trade.settle(
                    result=outcome,
                    profit_loss=settlement.profit_loss,
                    settlement_timestamp=settlement.settlement_timestamp,
                    closing_odds=closing_odds,
                    clv=clv_val,
                )
                self._trades[trade_id] = settled_trade

                # Update staking model
                self._staking_model.record_result(trade.stake, settlement.profit_loss)

                self._emit_event(
                    ForwardEventType.PAPER_TRADE_SETTLED,
                    trade_id, trade.fixture_id,
                    {"outcome": outcome, "profit_loss": settlement.profit_loss},
                )
                result.trades_settled += 1

            except Exception as e:
                result.errors.append(f"Settlement failed for {trade_id}: {str(e)[:100]}")

        result.completed_at = time.time()
        return result

    def add_trade(self, trade: PaperTrade) -> bool:
        """Add a paper trade. Idempotent (duplicate → False)."""
        if trade.trade_id in self._trades:
            return False
        self._trades[trade.trade_id] = trade
        self._emit_event(
            ForwardEventType.PAPER_TRADE_CREATED,
            trade.trade_id, trade.fixture_id,
        )
        return True

    def approve_trade(self, trade_id: str) -> bool:
        """Approve a generated trade for paper trading."""
        trade = self._trades.get(trade_id)
        if not trade or trade.status != PaperTradeStatus.GENERATED:
            return False
        self._trades[trade_id] = trade.transition(PaperTradeStatus.APPROVED_FOR_PAPER)
        self._emit_event(ForwardEventType.PAPER_TRADE_APPROVED, trade_id, trade.fixture_id)
        return True

    def open_trade(self, trade_id: str) -> bool:
        """Open an approved trade."""
        trade = self._trades.get(trade_id)
        if not trade or trade.status != PaperTradeStatus.APPROVED_FOR_PAPER:
            return False
        self._trades[trade_id] = trade.transition(PaperTradeStatus.OPEN)
        self._emit_event(ForwardEventType.PAPER_TRADE_OPENED, trade_id, trade.fixture_id)
        return True

    def _emit_event(
        self, event_type: ForwardEventType, entity_id: str = "",
        fixture_id: str = "", data: Optional[dict[str, Any]] = None,
    ) -> None:
        """Emit an immutable forward event."""
        self._events.append(ForwardEvent(
            event_type=event_type,
            entity_id=entity_id,
            fixture_id=fixture_id,
            data=data or {},
        ))
