"""Forward Research Repository — persistence for forward/paper trading objects.

Extends the research persistence layer with forward-specific operations.
Does NOT modify the existing ResearchRepository interface.

Uses adapter pattern: InMemoryForwardRepository for tests,
PostgresForwardRepository for production (via migrations).

All operations use content hashes for deterministic identity.
Duplicate prevention is built-in (save returns False if exists).
"""

from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod
from typing import Any, Optional


class ForwardRepository(ABC):
    """Abstract persistence interface for forward research objects."""

    # ═══ FIXTURES ═══

    @abstractmethod
    def save_fixture(self, fixture_id: str, data: dict[str, Any]) -> bool:
        """Save a future fixture. Returns False if already exists."""
        ...

    @abstractmethod
    def get_fixture(self, fixture_id: str) -> Optional[dict[str, Any]]:
        """Get fixture by ID."""
        ...

    @abstractmethod
    def update_fixture(self, fixture_id: str, updates: dict[str, Any]) -> bool:
        """Update fixture fields."""
        ...

    @abstractmethod
    def list_fixtures(self, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        """List fixtures with optional status filter."""
        ...

    # ═══ SNAPSHOTS ═══

    @abstractmethod
    def save_snapshot(self, snapshot_id: str, data: dict[str, Any]) -> bool:
        """Save a pre-match feature snapshot. Returns False if duplicate."""
        ...

    @abstractmethod
    def get_snapshot(self, snapshot_id: str) -> Optional[dict[str, Any]]:
        """Get snapshot by ID."""
        ...

    @abstractmethod
    def list_snapshots(self, fixture_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        """List snapshots, optionally filtered by fixture."""
        ...

    # ═══ ODDS SNAPSHOTS ═══

    @abstractmethod
    def save_odds_snapshot(self, odds_snapshot_id: str, data: dict[str, Any]) -> bool:
        """Save an odds snapshot. Returns False if duplicate."""
        ...

    @abstractmethod
    def get_odds_snapshot(self, odds_snapshot_id: str) -> Optional[dict[str, Any]]:
        """Get odds snapshot by ID."""
        ...

    @abstractmethod
    def list_odds_snapshots(
        self, fixture_id: Optional[str] = None, market: Optional[str] = None,
        odds_type: Optional[str] = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List odds snapshots with filters."""
        ...

    # ═══ PAPER TRADES ═══

    @abstractmethod
    def save_trade(self, trade_id: str, data: dict[str, Any]) -> bool:
        """Save a paper trade. Returns False if duplicate."""
        ...

    @abstractmethod
    def get_trade(self, trade_id: str) -> Optional[dict[str, Any]]:
        """Get trade by ID."""
        ...

    @abstractmethod
    def update_trade(self, trade_id: str, updates: dict[str, Any]) -> bool:
        """Update trade fields (e.g., status, settlement)."""
        ...

    @abstractmethod
    def list_trades(
        self, status: Optional[str] = None, strategy_id: Optional[str] = None,
        fixture_id: Optional[str] = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List trades with filters."""
        ...

    @abstractmethod
    def count_trades(self, status: Optional[str] = None) -> int:
        """Count trades with optional status filter."""
        ...

    # ═══ CLV ═══

    @abstractmethod
    def save_clv(self, trade_id: str, data: dict[str, Any]) -> bool:
        """Save CLV result for a trade."""
        ...

    @abstractmethod
    def get_clv(self, trade_id: str) -> Optional[dict[str, Any]]:
        """Get CLV result for a trade."""
        ...

    # ═══ EVENTS ═══

    @abstractmethod
    def append_forward_event(self, event: dict[str, Any]) -> None:
        """Append an immutable forward event."""
        ...

    @abstractmethod
    def list_forward_events(
        self, fixture_id: Optional[str] = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List forward events."""
        ...


class InMemoryForwardRepository(ForwardRepository):
    """Thread-safe in-memory forward repository for testing.

    All data lost when instance is garbage collected.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._fixtures: dict[str, dict[str, Any]] = {}
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._odds_snapshots: dict[str, dict[str, Any]] = {}
        self._trades: dict[str, dict[str, Any]] = {}
        self._clv: dict[str, dict[str, Any]] = {}
        self._events: list[dict[str, Any]] = []

    # ═══ FIXTURES ═══

    def save_fixture(self, fixture_id: str, data: dict[str, Any]) -> bool:
        with self._lock:
            if fixture_id in self._fixtures:
                return False
            self._fixtures[fixture_id] = {**data, "_id": fixture_id, "_created_at": time.time()}
            return True

    def get_fixture(self, fixture_id: str) -> Optional[dict[str, Any]]:
        return self._fixtures.get(fixture_id)

    def update_fixture(self, fixture_id: str, updates: dict[str, Any]) -> bool:
        with self._lock:
            if fixture_id not in self._fixtures:
                return False
            self._fixtures[fixture_id].update(updates)
            return True

    def list_fixtures(self, status: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        items = list(self._fixtures.values())
        if status:
            items = [f for f in items if f.get("status") == status]
        return items[:limit]

    # ═══ SNAPSHOTS ═══

    def save_snapshot(self, snapshot_id: str, data: dict[str, Any]) -> bool:
        with self._lock:
            if snapshot_id in self._snapshots:
                return False
            self._snapshots[snapshot_id] = {**data, "_id": snapshot_id, "_created_at": time.time()}
            return True

    def get_snapshot(self, snapshot_id: str) -> Optional[dict[str, Any]]:
        return self._snapshots.get(snapshot_id)

    def list_snapshots(self, fixture_id: Optional[str] = None, limit: int = 100) -> list[dict[str, Any]]:
        items = list(self._snapshots.values())
        if fixture_id:
            items = [s for s in items if s.get("fixture_id") == fixture_id]
        return items[:limit]

    # ═══ ODDS SNAPSHOTS ═══

    def save_odds_snapshot(self, odds_snapshot_id: str, data: dict[str, Any]) -> bool:
        with self._lock:
            if odds_snapshot_id in self._odds_snapshots:
                return False
            self._odds_snapshots[odds_snapshot_id] = {
                **data, "_id": odds_snapshot_id, "_created_at": time.time(),
            }
            return True

    def get_odds_snapshot(self, odds_snapshot_id: str) -> Optional[dict[str, Any]]:
        return self._odds_snapshots.get(odds_snapshot_id)

    def list_odds_snapshots(
        self, fixture_id: Optional[str] = None, market: Optional[str] = None,
        odds_type: Optional[str] = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        items = list(self._odds_snapshots.values())
        if fixture_id:
            items = [s for s in items if s.get("fixture_id") == fixture_id]
        if market:
            items = [s for s in items if s.get("market") == market]
        if odds_type:
            items = [s for s in items if s.get("odds_type") == odds_type]
        return items[:limit]

    # ═══ PAPER TRADES ═══

    def save_trade(self, trade_id: str, data: dict[str, Any]) -> bool:
        with self._lock:
            if trade_id in self._trades:
                return False
            self._trades[trade_id] = {**data, "_id": trade_id, "_created_at": time.time()}
            return True

    def get_trade(self, trade_id: str) -> Optional[dict[str, Any]]:
        return self._trades.get(trade_id)

    def update_trade(self, trade_id: str, updates: dict[str, Any]) -> bool:
        with self._lock:
            if trade_id not in self._trades:
                return False
            self._trades[trade_id].update(updates)
            return True

    def list_trades(
        self, status: Optional[str] = None, strategy_id: Optional[str] = None,
        fixture_id: Optional[str] = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        items = list(self._trades.values())
        if status:
            items = [t for t in items if t.get("status") == status]
        if strategy_id:
            items = [t for t in items if t.get("strategy_id") == strategy_id]
        if fixture_id:
            items = [t for t in items if t.get("fixture_id") == fixture_id]
        return items[:limit]

    def count_trades(self, status: Optional[str] = None) -> int:
        if status:
            return sum(1 for t in self._trades.values() if t.get("status") == status)
        return len(self._trades)

    # ═══ CLV ═══

    def save_clv(self, trade_id: str, data: dict[str, Any]) -> bool:
        with self._lock:
            if trade_id in self._clv:
                return False
            self._clv[trade_id] = {**data, "_id": trade_id, "_created_at": time.time()}
            return True

    def get_clv(self, trade_id: str) -> Optional[dict[str, Any]]:
        return self._clv.get(trade_id)

    # ═══ EVENTS ═══

    def append_forward_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            self._events.append({**event, "_created_at": time.time()})

    def list_forward_events(
        self, fixture_id: Optional[str] = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        items = self._events
        if fixture_id:
            items = [e for e in items if e.get("fixture_id") == fixture_id]
        return items[-limit:]
