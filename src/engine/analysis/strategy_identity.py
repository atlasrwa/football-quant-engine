"""Strategy identity and versioning foundation.

Every strategy must have a durable, immutable identity that enables
reproducibility and auditing. Strategies are immutable once published —
changes create a new version.

This is the minimum foundation for Phase 1 reproducibility.
Full social features (creator_id, follows, etc.) are Phase 2+.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List

from src.engine.evaluator import Strategy

logger = logging.getLogger(__name__)

# Schema version for the strategy identity format
SCHEMA_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class StrategyIdentity:
    """Immutable identity for a published strategy.

    Once created, a StrategyIdentity cannot be modified.
    Any change to the strategy definition creates a new version.
    """

    strategy_id: str  # UUID
    strategy_version: int  # Monotonically increasing
    name: str
    content_hash: str  # SHA-256 of strategy definition
    created_at: str  # ISO 8601 timestamp
    schema_version: str = SCHEMA_VERSION
    parent_version: int | None = None  # Previous version if evolved


class StrategyRegistry:
    """Registry for strategy identity and versioning.

    Ensures:
    1. Every strategy gets a unique ID
    2. Modifications create new versions
    3. Historical definitions are preserved
    4. Content hash enables deduplication and integrity verification
    """

    def __init__(self) -> None:
        self._strategies: dict[str, List[StrategyIdentity]] = {}  # id → versions

    def register(
        self,
        strategy: Strategy,
        strategy_id: str | None = None,
    ) -> StrategyIdentity:
        """Register a new strategy or create a new version.

        If strategy_id is provided and exists, creates a new version.
        If strategy_id is None, creates a new strategy with v1.

        Args:
            strategy: The Strategy object to register.
            strategy_id: Optional existing strategy ID for versioning.

        Returns:
            StrategyIdentity with assigned ID and version.
        """
        content_hash = self._compute_hash(strategy)
        now = datetime.now(timezone.utc).isoformat()

        if strategy_id and strategy_id in self._strategies:
            # Create new version
            versions = self._strategies[strategy_id]
            latest_version = versions[-1].strategy_version
            # Check if content actually changed
            if versions[-1].content_hash == content_hash:
                logger.info("Strategy '%s' unchanged, returning existing version", strategy.name)
                return versions[-1]

            identity = StrategyIdentity(
                strategy_id=strategy_id,
                strategy_version=latest_version + 1,
                name=strategy.name,
                content_hash=content_hash,
                created_at=now,
                schema_version=SCHEMA_VERSION,
                parent_version=latest_version,
            )
            versions.append(identity)
        else:
            # New strategy
            sid = strategy_id or str(uuid.uuid4())
            identity = StrategyIdentity(
                strategy_id=sid,
                strategy_version=1,
                name=strategy.name,
                content_hash=content_hash,
                created_at=now,
                schema_version=SCHEMA_VERSION,
                parent_version=None,
            )
            self._strategies[sid] = [identity]

        logger.info(
            "Registered strategy: id=%s v%d name='%s'",
            identity.strategy_id[:8],
            identity.strategy_version,
            identity.name,
        )
        return identity

    def get_version(self, strategy_id: str, version: int) -> StrategyIdentity | None:
        """Get a specific version of a strategy."""
        versions = self._strategies.get(strategy_id, [])
        for v in versions:
            if v.strategy_version == version:
                return v
        return None

    def get_latest(self, strategy_id: str) -> StrategyIdentity | None:
        """Get the latest version of a strategy."""
        versions = self._strategies.get(strategy_id, [])
        return versions[-1] if versions else None

    def list_strategies(self) -> List[StrategyIdentity]:
        """List the latest version of all registered strategies."""
        return [versions[-1] for versions in self._strategies.values()]

    @staticmethod
    def _compute_hash(strategy: Strategy) -> str:
        """Compute content hash for a strategy definition."""
        content = json.dumps({
            "name": strategy.name,
            "metric": strategy.metric,
            "market": strategy.market,
            "conditions": [
                {"field": c.field, "op": c.op, "value": c.value}
                for c in strategy.conditions
            ],
            "logic": strategy.logic,
            "direction": strategy.direction,
            "min_odds": strategy.min_odds,
        }, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()
