"""Integration tests for provenance chain: dataset/feature/model versions."""

import pytest
import asyncpg
from uuid import uuid4, UUID

from src.persistence.pg_provenance_repository import (
    PgDatasetVersionRepository,
    PgFeatureVersionRepository,
    PgModelVersionRepository,
)
from src.persistence.pg_strategy_repository import (
    PgStrategyRepository,
    PgStrategyVersionRepository,
    StrategyRecord,
)
from src.persistence.hashing import (
    compute_dataset_content_hash,
    compute_feature_version_hash,
    compute_model_version_hash,
)


pytestmark = pytest.mark.asyncio


SYSTEM_ID = UUID("00000000-0000-0000-0000-000000000001")


class TestDatasetVersions:
    """Test deterministic dataset snapshots."""

    async def test_create_dataset_version(self, db_conn):
        """Basic creation succeeds with computed content_hash."""
        repo = PgDatasetVersionRepository(db_conn)
        result = await repo.create(
            source="footystats", league_id=4759, season="2023",
            match_ids=[100, 200, 300, 400, 500],
            date_range_start=1700000000, date_range_end=1700500000,
            created_by=SYSTEM_ID,
        )
        assert result["content_hash"] == compute_dataset_content_hash([100, 200, 300, 400, 500])
        assert result["n_matches"] == 5

    async def test_same_content_deduplicates(self, db_conn):
        """Same match IDs produce same hash and return existing record."""
        repo = PgDatasetVersionRepository(db_conn)
        r1 = await repo.create(
            source="footystats", league_id=4759, season="2023",
            match_ids=[10, 20, 30],
            date_range_start=1700000000, date_range_end=1700300000,
            created_by=SYSTEM_ID,
        )
        r2 = await repo.create(
            source="footystats", league_id=4759, season="2023",
            match_ids=[30, 10, 20],  # Different order — same sorted set
            date_range_start=1700000000, date_range_end=1700300000,
            created_by=SYSTEM_ID,
        )
        assert r1["id"] == r2["id"]
        assert r1["content_hash"] == r2["content_hash"]

    async def test_different_content_produces_different_hash(self, db_conn):
        """Different match IDs produce different hashes."""
        repo = PgDatasetVersionRepository(db_conn)
        r1 = await repo.create(
            source="test", league_id=1, season="a",
            match_ids=[1, 2, 3],
            date_range_start=1, date_range_end=3,
            created_by=SYSTEM_ID,
        )
        r2 = await repo.create(
            source="test", league_id=1, season="a",
            match_ids=[1, 2, 4],  # Different!
            date_range_start=1, date_range_end=4,
            created_by=SYSTEM_ID,
        )
        assert r1["content_hash"] != r2["content_hash"]

    async def test_immutability_update_blocked(self, db_conn):
        """UPDATE on dataset_versions is blocked."""
        repo = PgDatasetVersionRepository(db_conn)
        r = await repo.create(
            source="test", league_id=2, season="b",
            match_ids=[99, 98, 97],
            date_range_start=1, date_range_end=3,
            created_by=SYSTEM_ID,
        )
        result = await db_conn.execute(
            "UPDATE dataset_versions SET n_matches = 999 WHERE id = $1", r["id"]
        )
        assert result == "UPDATE 0"  # RLS blocks


class TestFeatureVersions:
    """Test feature version configuration persistence."""

    async def _create_dataset(self, db_conn) -> UUID:
        repo = PgDatasetVersionRepository(db_conn)
        r = await repo.create(
            source="test", league_id=4759, season="2023",
            match_ids=list(range(1000, 1050)),
            date_range_start=1700000000, date_range_end=1700500000,
            created_by=SYSTEM_ID,
        )
        return r["id"]

    async def test_create_feature_version(self, db_conn):
        """Basic creation with correct content_hash."""
        ds_id = await self._create_dataset(db_conn)
        repo = PgFeatureVersionRepository(db_conn)

        result = await repo.create(
            dataset_id=ds_id, xg_rolling_window=5,
            form_rolling_window=6, referee_min_matches=5,
            created_by=SYSTEM_ID,
        )
        expected_hash = compute_feature_version_hash(str(ds_id), 5, 6, 5, None)
        assert result["content_hash"] == expected_hash

    async def test_same_config_deduplicates(self, db_conn):
        """Same dataset + same params = same feature version."""
        ds_id = await self._create_dataset(db_conn)
        repo = PgFeatureVersionRepository(db_conn)

        r1 = await repo.create(ds_id, 5, 6, 5, created_by=SYSTEM_ID)
        r2 = await repo.create(ds_id, 5, 6, 5, created_by=SYSTEM_ID)
        assert r1["id"] == r2["id"]

    async def test_different_config_produces_different_version(self, db_conn):
        """Different parameters produce a new version."""
        ds_id = await self._create_dataset(db_conn)
        repo = PgFeatureVersionRepository(db_conn)

        r1 = await repo.create(ds_id, 5, 6, 5, created_by=SYSTEM_ID)
        r2 = await repo.create(ds_id, 10, 6, 5, created_by=SYSTEM_ID)  # Different xg window
        assert r1["content_hash"] != r2["content_hash"]

    async def test_dataset_relationship(self, db_conn):
        """Feature version references its parent dataset."""
        ds_id = await self._create_dataset(db_conn)
        repo = PgFeatureVersionRepository(db_conn)
        r = await repo.create(ds_id, 5, 6, 5, created_by=SYSTEM_ID)
        assert r["dataset_id"] == ds_id


class TestModelVersions:
    """Test model version configuration persistence."""

    async def _create_provenance_base(self, db_conn) -> tuple:
        """Create dataset + feature version + strategy version."""
        ds_repo = PgDatasetVersionRepository(db_conn)
        ds = await ds_repo.create("test", 4759, "2023", list(range(2000, 2050)),
                                  1700000000, 1700500000, SYSTEM_ID)

        fv_repo = PgFeatureVersionRepository(db_conn)
        fv = await fv_repo.create(ds["id"], 5, 6, 5, created_by=SYSTEM_ID)

        # Create strategy + version for model to reference
        strat_repo = PgStrategyRepository(db_conn)
        strat = await strat_repo.create_strategy(StrategyRecord(
            id=uuid4(), owner_id=SYSTEM_ID, name="Model Test Strat",
            description=None, visibility="private", status="active",
        ))
        sv_repo = PgStrategyVersionRepository(db_conn)
        sv = await sv_repo.create_version(strat.id, {
            "name": "Model Test", "metric": "xC", "market": "corners",
            "conditions": [{"field": "f", "op": ">", "value": 1.0}],
            "logic": "and", "direction": "OVER", "min_odds": 1.5,
        }, SYSTEM_ID)

        return ds, fv, strat, sv

    async def test_create_model_version(self, db_conn):
        """Basic creation with deterministic hash."""
        ds, fv, strat, sv = await self._create_provenance_base(db_conn)
        repo = PgModelVersionRepository(db_conn)

        result = await repo.create(
            strategy_id=strat.id, strategy_version=sv.version,
            strategy_content_hash=sv.content_hash,
            feature_version_id=fv["id"],
            train_window=200, test_window=50, step_size=50,
            min_odds=1.5, max_odds=5.0, created_by=SYSTEM_ID,
        )
        expected_hash = compute_model_version_hash(
            sv.content_hash, str(fv["id"]), 200, 50, 50, 1.5, 5.0
        )
        assert result["content_hash"] == expected_hash

    async def test_same_config_deduplicates(self, db_conn):
        """Same inputs produce same model version."""
        ds, fv, strat, sv = await self._create_provenance_base(db_conn)
        repo = PgModelVersionRepository(db_conn)

        r1 = await repo.create(strat.id, sv.version, sv.content_hash,
                               fv["id"], 200, 50, 50, 1.5, 5.0, SYSTEM_ID)
        r2 = await repo.create(strat.id, sv.version, sv.content_hash,
                               fv["id"], 200, 50, 50, 1.5, 5.0, SYSTEM_ID)
        assert r1["id"] == r2["id"]

    async def test_provenance_chain_integrity(self, db_conn):
        """Model version links to strategy and feature version correctly."""
        ds, fv, strat, sv = await self._create_provenance_base(db_conn)
        repo = PgModelVersionRepository(db_conn)

        mv = await repo.create(strat.id, sv.version, sv.content_hash,
                               fv["id"], 200, 50, 50, 1.5, 5.0, SYSTEM_ID)
        assert mv["strategy_content_hash"] == sv.content_hash
        assert mv["feature_version_id"] == fv["id"]
