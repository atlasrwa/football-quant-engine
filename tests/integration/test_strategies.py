"""Integration tests for strategies, strategy_versions, and strategy_forks."""

import json

import pytest
import asyncpg
from uuid import uuid4

from src.persistence.pg_strategy_repository import (
    PgStrategyRepository,
    PgStrategyVersionRepository,
    PgStrategyForkRepository,
    StrategyRecord,
    compute_content_hash,
    strategy_to_definition,
)
from src.engine.analysis.evaluator import Condition, Strategy
from src.engine.analysis.strategy_identity import StrategyRegistry


pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════
# HASHING COMPATIBILITY
# ═══════════════════════════════════════════════════════════════════

class TestContentHashCompatibility:
    """Verify that compute_content_hash() produces identical output to StrategyRegistry._compute_hash()."""

    def test_same_hash_as_registry(self):
        """The DB hash function matches the engine's hash function exactly."""
        strategy = Strategy(
            name="EPL Corners Over",
            metric="xC",
            market="corners_over_under",
            conditions=(
                Condition(field="home_xC", op=">", value=2.5),
                Condition(field="away_xC", op=">", value=1.8),
            ),
            logic="and",
            direction="OVER",
            min_odds=1.70,
        )

        # Engine's canonical hash
        engine_hash = StrategyRegistry._compute_hash(strategy)

        # DB layer's hash (from definition dict)
        definition = strategy_to_definition(strategy)
        db_hash = compute_content_hash(definition)

        assert engine_hash == db_hash

    def test_different_definitions_produce_different_hashes(self):
        """Changed definition → different hash."""
        def1 = {
            "name": "Strategy A", "metric": "xC", "market": "corners",
            "conditions": [{"field": "home_xC", "op": ">", "value": 2.5}],
            "logic": "and", "direction": "OVER", "min_odds": 1.70,
        }
        def2 = {
            "name": "Strategy A", "metric": "xC", "market": "corners",
            "conditions": [{"field": "home_xC", "op": ">", "value": 3.0}],  # changed
            "logic": "and", "direction": "OVER", "min_odds": 1.70,
        }
        assert compute_content_hash(def1) != compute_content_hash(def2)

    def test_hash_is_deterministic(self):
        """Same definition always produces same hash."""
        definition = {
            "name": "Determinism", "metric": "xB", "market": "cards",
            "conditions": [{"field": "home_xB", "op": ">=", "value": 8.0}],
            "logic": "and", "direction": "OVER", "min_odds": 1.80,
        }
        hashes = {compute_content_hash(definition) for _ in range(100)}
        assert len(hashes) == 1

    def test_hash_independent_of_json_key_order(self):
        """Key order in the input dict doesn't affect the hash (sort_keys=True)."""
        # Provide keys in different orders — hash should be identical
        def_ordered = {
            "name": "Order Test", "metric": "xC", "market": "corners",
            "conditions": [{"field": "f", "op": ">", "value": 1.0}],
            "logic": "and", "direction": "OVER", "min_odds": 1.50,
        }
        def_reversed = {
            "min_odds": 1.50, "direction": "OVER", "logic": "and",
            "conditions": [{"value": 1.0, "op": ">", "field": "f"}],
            "market": "corners", "metric": "xC", "name": "Order Test",
        }
        assert compute_content_hash(def_ordered) == compute_content_hash(def_reversed)


# ═══════════════════════════════════════════════════════════════════
# STRATEGY OWNERSHIP
# ═══════════════════════════════════════════════════════════════════

class TestStrategyOwnership:
    """Test strategy creation and ownership constraints."""

    async def test_create_strategy(self, db_conn, system_user_id):
        """Basic strategy creation succeeds."""
        repo = PgStrategyRepository(db_conn)
        record = StrategyRecord(
            id=uuid4(), owner_id=system_user_id,
            name="Test Strategy", description="A test",
            visibility="private", status="active",
        )
        created = await repo.create_strategy(record)
        assert created.id == record.id
        assert created.owner_id == system_user_id
        assert created.visibility == "private"

    async def test_owner_id_immutable(self, db_conn, system_user_id):
        """owner_id cannot be changed after creation."""
        repo = PgStrategyRepository(db_conn)
        strat = StrategyRecord(
            id=uuid4(), owner_id=system_user_id,
            name="Immutable Owner", description=None,
            visibility="private", status="active",
        )
        await repo.create_strategy(strat)

        # Attempt to change owner
        with pytest.raises(asyncpg.RaiseError, match="owner_id is immutable"):
            new_owner = uuid4()
            # Create a new user first
            await db_conn.execute(
                "INSERT INTO users (id, username, display_name, role, status) VALUES ($1, $2, $2, 'user', 'active')",
                new_owner, "attacker",
            )
            await db_conn.execute(
                "UPDATE strategies SET owner_id = $2 WHERE id = $1",
                strat.id, new_owner,
            )

    async def test_visibility_change_allowed(self, db_conn, system_user_id):
        """Owner can change visibility."""
        repo = PgStrategyRepository(db_conn)
        strat = StrategyRecord(
            id=uuid4(), owner_id=system_user_id,
            name="Vis Test", description=None,
            visibility="private", status="active",
        )
        await repo.create_strategy(strat)
        updated = await repo.update_visibility(strat.id, "public")
        assert updated.visibility == "public"


# ═══════════════════════════════════════════════════════════════════
# STRATEGY VERSIONS
# ═══════════════════════════════════════════════════════════════════

class TestStrategyVersions:
    """Test version creation, numbering, immutability, and deduplication."""

    async def _create_strategy(self, db_conn, system_user_id) -> StrategyRecord:
        """Helper to create a parent strategy."""
        repo = PgStrategyRepository(db_conn)
        record = StrategyRecord(
            id=uuid4(), owner_id=system_user_id,
            name="Versioned Strategy", description=None,
            visibility="private", status="active",
        )
        return await repo.create_strategy(record)

    async def test_create_first_version(self, db_conn, system_user_id):
        """First version gets version=1."""
        strat = await self._create_strategy(db_conn, system_user_id)
        repo = PgStrategyVersionRepository(db_conn)

        definition = {
            "name": "V1", "metric": "xC", "market": "corners_over_under",
            "conditions": [{"field": "home_xC", "op": ">", "value": 2.5}],
            "logic": "and", "direction": "OVER", "min_odds": 1.70,
        }
        v = await repo.create_version(strat.id, definition, system_user_id)
        assert v.version == 1
        assert v.content_hash == compute_content_hash(definition)
        assert v.is_deprecated is False

    async def test_version_auto_increments(self, db_conn, system_user_id):
        """Subsequent versions get incrementing numbers."""
        strat = await self._create_strategy(db_conn, system_user_id)
        repo = PgStrategyVersionRepository(db_conn)

        def1 = {
            "name": "V1", "metric": "xC", "market": "corners",
            "conditions": [{"field": "home_xC", "op": ">", "value": 2.0}],
            "logic": "and", "direction": "OVER", "min_odds": 1.50,
        }
        def2 = {
            "name": "V2", "metric": "xC", "market": "corners",
            "conditions": [{"field": "home_xC", "op": ">", "value": 3.0}],
            "logic": "and", "direction": "OVER", "min_odds": 1.50,
        }

        v1 = await repo.create_version(strat.id, def1, system_user_id)
        v2 = await repo.create_version(strat.id, def2, system_user_id)

        assert v1.version == 1
        assert v2.version == 2

    async def test_duplicate_content_hash_detected_by_lookup(self, db_conn, system_user_id):
        """Same content_hash is detectable via get_by_content_hash (app-level dedup)."""
        strat = await self._create_strategy(db_conn, system_user_id)
        repo = PgStrategyVersionRepository(db_conn)

        definition = {
            "name": "Unique", "metric": "xB", "market": "cards_over_under",
            "conditions": [{"field": "home_xB", "op": ">=", "value": 8.0}],
            "logic": "and", "direction": "OVER", "min_odds": 1.80,
        }
        v1 = await repo.create_version(strat.id, definition, system_user_id)

        # Application checks for duplicate before creating
        existing = await repo.get_by_content_hash(v1.content_hash)
        assert existing is not None
        assert existing.content_hash == v1.content_hash

    async def test_version_definition_immutable(self, db_conn, system_user_id):
        """Cannot change definition/content_hash after creation."""
        strat = await self._create_strategy(db_conn, system_user_id)
        repo = PgStrategyVersionRepository(db_conn)

        definition = {
            "name": "Immutable", "metric": "xO", "market": "offsides",
            "conditions": [{"field": "home_xO", "op": ">", "value": 1.0}],
            "logic": "and", "direction": "OVER", "min_odds": 1.60,
        }
        v = await repo.create_version(strat.id, definition, system_user_id)

        with pytest.raises(asyncpg.RaiseError, match="immutable"):
            await db_conn.execute(
                "UPDATE strategy_versions SET definition = $2::jsonb WHERE id = $1",
                v.id, json.dumps({"name": "HACKED"}),
            )

    async def test_deprecation_allowed(self, db_conn, system_user_id):
        """is_deprecated can be set (only mutable lifecycle field)."""
        strat = await self._create_strategy(db_conn, system_user_id)
        repo = PgStrategyVersionRepository(db_conn)

        definition = {
            "name": "Will Deprecate", "metric": "xC", "market": "corners",
            "conditions": [{"field": "f", "op": ">", "value": 1.0}],
            "logic": "and", "direction": "OVER", "min_odds": 1.50,
        }
        v = await repo.create_version(strat.id, definition, system_user_id)
        deprecated = await repo.deprecate_version(strat.id, v.version)
        assert deprecated.is_deprecated is True
        assert deprecated.deprecated_at is not None

    async def test_get_latest_version(self, db_conn, system_user_id):
        """get_latest_version returns the highest version number."""
        strat = await self._create_strategy(db_conn, system_user_id)
        repo = PgStrategyVersionRepository(db_conn)

        for i in range(3):
            await repo.create_version(strat.id, {
                "name": f"V{i+1}", "metric": "xC", "market": "corners",
                "conditions": [{"field": "f", "op": ">", "value": float(i)}],
                "logic": "and", "direction": "OVER", "min_odds": 1.50,
            }, system_user_id)

        latest = await repo.get_latest_version(strat.id)
        assert latest.version == 3


# ═══════════════════════════════════════════════════════════════════
# STRATEGY FORKS
# ═══════════════════════════════════════════════════════════════════

class TestStrategyForks:
    """Test fork lineage tracking."""

    async def test_create_fork(self, db_conn, system_user_id):
        """Fork records are created with full lineage."""
        strat_repo = PgStrategyRepository(db_conn)
        ver_repo = PgStrategyVersionRepository(db_conn)
        fork_repo = PgStrategyForkRepository(db_conn)

        # Create source strategy + version
        source = await strat_repo.create_strategy(StrategyRecord(
            id=uuid4(), owner_id=system_user_id,
            name="Source", description=None,
            visibility="public", status="active",
        ))
        source_v = await ver_repo.create_version(source.id, {
            "name": "Source", "metric": "xC", "market": "corners",
            "conditions": [{"field": "f", "op": ">", "value": 1.0}],
            "logic": "and", "direction": "OVER", "min_odds": 1.50,
        }, system_user_id)

        # Create target strategy (the fork)
        target = await strat_repo.create_strategy(StrategyRecord(
            id=uuid4(), owner_id=system_user_id,
            name="Forked Strategy", description="Forked from Source",
            visibility="private", status="active",
        ))

        # Record the fork
        fork = await fork_repo.create_fork(
            source_strategy_id=source.id,
            source_version=source_v.version,
            source_content_hash=source_v.content_hash,
            target_strategy_id=target.id,
            forked_by=system_user_id,
        )
        assert fork["source_strategy_id"] == source.id
        assert fork["source_version"] == source_v.version
        assert fork["target_strategy_id"] == target.id

    async def test_fork_update_blocked(self, db_conn, system_user_id):
        """Fork records cannot be updated (RLS blocks or trigger fires)."""
        strat_repo = PgStrategyRepository(db_conn)
        ver_repo = PgStrategyVersionRepository(db_conn)
        fork_repo = PgStrategyForkRepository(db_conn)

        source = await strat_repo.create_strategy(StrategyRecord(
            id=uuid4(), owner_id=system_user_id,
            name="ForkSrc", description=None,
            visibility="public", status="active",
        ))
        source_v = await ver_repo.create_version(source.id, {
            "name": "ForkSrc", "metric": "xB", "market": "cards",
            "conditions": [{"field": "f", "op": ">", "value": 2.0}],
            "logic": "and", "direction": "OVER", "min_odds": 1.60,
        }, system_user_id)

        target = await strat_repo.create_strategy(StrategyRecord(
            id=uuid4(), owner_id=system_user_id,
            name="ForkTarget", description=None,
            visibility="private", status="active",
        ))

        fork = await fork_repo.create_fork(
            source.id, source_v.version, source_v.content_hash,
            target.id, system_user_id,
        )

        # Update attempt — either RLS blocks (0 rows) or trigger fires
        result = await db_conn.execute(
            "UPDATE strategy_forks SET source_version = 99 WHERE id = $1",
            fork["id"],
        )
        # RLS may block (UPDATE 0) or trigger raises — either is acceptable
        assert result == "UPDATE 0" or "immutable" in str(result)

    async def test_fork_delete_blocked(self, db_conn, system_user_id):
        """Fork records cannot be deleted (RLS blocks or trigger fires)."""
        strat_repo = PgStrategyRepository(db_conn)
        ver_repo = PgStrategyVersionRepository(db_conn)
        fork_repo = PgStrategyForkRepository(db_conn)

        source = await strat_repo.create_strategy(StrategyRecord(
            id=uuid4(), owner_id=system_user_id,
            name="ForkSrc2", description=None,
            visibility="public", status="active",
        ))
        source_v = await ver_repo.create_version(source.id, {
            "name": "ForkSrc2", "metric": "xB", "market": "cards",
            "conditions": [{"field": "g", "op": ">", "value": 3.0}],
            "logic": "and", "direction": "OVER", "min_odds": 1.70,
        }, system_user_id)

        target = await strat_repo.create_strategy(StrategyRecord(
            id=uuid4(), owner_id=system_user_id,
            name="ForkTarget2", description=None,
            visibility="private", status="active",
        ))

        fork = await fork_repo.create_fork(
            source.id, source_v.version, source_v.content_hash,
            target.id, system_user_id,
        )

        # Delete attempt — either RLS blocks (DELETE 0) or trigger fires
        result = await db_conn.execute(
            "DELETE FROM strategy_forks WHERE id = $1", fork["id"]
        )
        assert result == "DELETE 0" or "immutable" in str(result)

    async def test_fork_lineage_lookup(self, db_conn, system_user_id):
        """Can look up fork source from target strategy."""
        strat_repo = PgStrategyRepository(db_conn)
        ver_repo = PgStrategyVersionRepository(db_conn)
        fork_repo = PgStrategyForkRepository(db_conn)

        source = await strat_repo.create_strategy(StrategyRecord(
            id=uuid4(), owner_id=system_user_id,
            name="LineageSrc", description=None,
            visibility="public", status="active",
        ))
        source_v = await ver_repo.create_version(source.id, {
            "name": "LineageSrc", "metric": "xO", "market": "offsides",
            "conditions": [{"field": "f", "op": "<", "value": 5.0}],
            "logic": "and", "direction": "UNDER", "min_odds": 1.90,
        }, system_user_id)

        target = await strat_repo.create_strategy(StrategyRecord(
            id=uuid4(), owner_id=system_user_id,
            name="LineageTarget", description=None,
            visibility="private", status="active",
        ))

        await fork_repo.create_fork(
            source.id, source_v.version, source_v.content_hash,
            target.id, system_user_id,
        )

        # Look up from target side
        lineage = await fork_repo.get_fork_source(target.id)
        assert lineage is not None
        assert lineage["source_strategy_id"] == source.id
        assert lineage["source_content_hash"] == source_v.content_hash
