"""Unit tests for the ingestion module: caching, validation, provider, and pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from src.ingestion.cache import CacheManager
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.provider import DataProvider, MockProvider
from src.ingestion.validator import SchemaValidator
from src.models.match import Match


# ---------------------------------------------------------------------------
# Helper: build a valid raw record dict
# ---------------------------------------------------------------------------

def _make_raw_record(**overrides) -> Dict[str, Any]:
    """Create a valid raw FootyStats record dict with optional overrides."""
    defaults = {
        "id": 9001,
        "date_unix": 1700000000,
        "league_id": 4759,
        "season": "2023",
        "homeID": 101,
        "awayID": 102,
        "home_name": "TeamA",
        "away_name": "TeamB",
        "homeGoalCount": 2,
        "awayGoalCount": 1,
        "totalGoalCount": 3,
        "team_a_xg": 1.8,
        "team_b_xg": 1.2,
        "referee_id": 201,
        "referee_name": "Test Referee",
        "o25_potential": 1.85,
        "u25_potential": 2.05,
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# CacheManager tests
# ---------------------------------------------------------------------------

class TestCacheManager:
    """Tests for the file-based JSON CacheManager."""

    def test_put_and_get(self, tmp_cache_dir):
        cache = CacheManager(cache_dir=tmp_cache_dir)
        record = _make_raw_record()

        cache.put(4759, "2023", 9001, record)
        result = cache.get(4759, "2023", 9001)

        assert result is not None
        assert result["id"] == 9001
        assert result["home_name"] == "TeamA"

    def test_exists_true(self, tmp_cache_dir):
        cache = CacheManager(cache_dir=tmp_cache_dir)
        cache.put(4759, "2023", 9001, _make_raw_record())

        assert cache.exists(4759, "2023", 9001) is True

    def test_exists_false(self, tmp_cache_dir):
        cache = CacheManager(cache_dir=tmp_cache_dir)

        assert cache.exists(4759, "2023", 9999) is False

    def test_get_miss_returns_none(self, tmp_cache_dir):
        cache = CacheManager(cache_dir=tmp_cache_dir)

        result = cache.get(4759, "2023", 9999)
        assert result is None

    def test_hit_miss_counters(self, tmp_cache_dir):
        cache = CacheManager(cache_dir=tmp_cache_dir)
        cache.put(4759, "2023", 9001, _make_raw_record())

        cache.get(4759, "2023", 9001)  # hit
        cache.get(4759, "2023", 9001)  # hit
        cache.get(4759, "2023", 9999)  # miss

        assert cache.hits == 2
        assert cache.misses == 1

    def test_get_bulk(self, tmp_cache_dir):
        cache = CacheManager(cache_dir=tmp_cache_dir)
        for i in range(5):
            cache.put(4759, "2023", 9000 + i, _make_raw_record(id=9000 + i))
        # Add a different league/season record
        cache.put(1234, "2022", 8000, _make_raw_record(id=8000))

        results = cache.get_bulk(4759, "2023")
        assert len(results) == 5

    def test_clear_specific_season(self, tmp_cache_dir):
        cache = CacheManager(cache_dir=tmp_cache_dir)
        for i in range(3):
            cache.put(4759, "2023", 9000 + i, _make_raw_record(id=9000 + i))
        cache.put(4759, "2024", 8000, _make_raw_record(id=8000))

        removed = cache.clear(league_id=4759, season="2023")
        assert removed == 3
        assert cache.exists(4759, "2024", 8000) is True

    def test_clear_all(self, tmp_cache_dir):
        cache = CacheManager(cache_dir=tmp_cache_dir)
        for i in range(5):
            cache.put(4759, "2023", 9000 + i, _make_raw_record(id=9000 + i))

        removed = cache.clear()
        assert removed == 5

    def test_file_naming_convention(self, tmp_cache_dir):
        cache = CacheManager(cache_dir=tmp_cache_dir)
        path = cache.put(4759, "2023", 9001, _make_raw_record())

        assert path.name == "4759_2023_9001.json"
        assert path.parent == tmp_cache_dir

    def test_cached_data_is_valid_json(self, tmp_cache_dir):
        cache = CacheManager(cache_dir=tmp_cache_dir)
        record = _make_raw_record()
        path = cache.put(4759, "2023", 9001, record)

        with open(path, "r") as f:
            loaded = json.load(f)
        assert loaded == record


# ---------------------------------------------------------------------------
# SchemaValidator tests
# ---------------------------------------------------------------------------

class TestSchemaValidator:
    """Tests for schema validation and error logging."""

    def test_valid_record_passes(self, tmp_errors_dir):
        validator = SchemaValidator(errors_dir=tmp_errors_dir)
        record = _make_raw_record()

        errors = validator.validate_single(record)
        assert errors is None

    def test_missing_required_field_fails(self, tmp_errors_dir):
        validator = SchemaValidator(errors_dir=tmp_errors_dir)
        record = _make_raw_record()
        del record["homeGoalCount"]

        errors = validator.validate_single(record)
        assert errors is not None
        assert any("homeGoalCount" in e for e in errors)

    def test_null_required_field_fails(self, tmp_errors_dir):
        validator = SchemaValidator(errors_dir=tmp_errors_dir)
        record = _make_raw_record(id=None)

        errors = validator.validate_single(record)
        assert errors is not None
        assert any("null" in e for e in errors)

    def test_negative_goals_fails(self, tmp_errors_dir):
        validator = SchemaValidator(errors_dir=tmp_errors_dir)
        record = _make_raw_record(homeGoalCount=-1)

        errors = validator.validate_single(record)
        assert errors is not None
        assert any("non-negative" in e for e in errors)

    def test_negative_xg_fails(self, tmp_errors_dir):
        validator = SchemaValidator(errors_dir=tmp_errors_dir)
        record = _make_raw_record(team_a_xg=-0.5)

        errors = validator.validate_single(record)
        assert errors is not None
        assert any("team_a_xg" in e for e in errors)

    def test_non_numeric_field_fails(self, tmp_errors_dir):
        validator = SchemaValidator(errors_dir=tmp_errors_dir)
        record = _make_raw_record(homeGoalCount="two")

        errors = validator.validate_single(record)
        assert errors is not None
        assert any("numeric" in e for e in errors)

    def test_optional_fields_can_be_missing(self, tmp_errors_dir):
        validator = SchemaValidator(errors_dir=tmp_errors_dir)
        record = _make_raw_record()
        del record["team_a_xg"]
        del record["referee_name"]

        errors = validator.validate_single(record)
        assert errors is None

    def test_optional_fields_can_be_null(self, tmp_errors_dir):
        validator = SchemaValidator(errors_dir=tmp_errors_dir)
        record = _make_raw_record(team_a_xg=None, referee_name=None)

        errors = validator.validate_single(record)
        assert errors is None

    def test_batch_validation(self, tmp_errors_dir):
        validator = SchemaValidator(errors_dir=tmp_errors_dir)
        records = [
            _make_raw_record(id=1),
            _make_raw_record(id=2),
            _make_raw_record(id=3, homeGoalCount=None),  # invalid
            _make_raw_record(id=4),
            _make_raw_record(id=5, date_unix=None),  # invalid
        ]

        valid, error_count = validator.validate_batch(records)
        assert len(valid) == 3
        assert error_count == 2
        assert validator.error_count == 2

    def test_error_log_written(self, tmp_errors_dir):
        validator = SchemaValidator(errors_dir=tmp_errors_dir)
        record = _make_raw_record(id=None)

        validator.validate_single(record)

        log_path = validator.error_log_path
        assert log_path.exists()
        with open(log_path, "r") as f:
            lines = f.readlines()
        assert len(lines) == 1

        entry = json.loads(lines[0])
        assert entry["record_id"] is None
        assert len(entry["errors"]) > 0
        assert "timestamp" in entry

    def test_error_log_appends(self, tmp_errors_dir):
        validator = SchemaValidator(errors_dir=tmp_errors_dir)

        validator.validate_single(_make_raw_record(id=None))
        validator.validate_single(_make_raw_record(homeGoalCount=-5))

        with open(validator.error_log_path, "r") as f:
            lines = f.readlines()
        assert len(lines) == 2

    def test_clear_error_log(self, tmp_errors_dir):
        validator = SchemaValidator(errors_dir=tmp_errors_dir)
        validator.validate_single(_make_raw_record(id=None))
        assert validator.error_log_path.exists()

        validator.clear_error_log()
        assert not validator.error_log_path.exists()
        assert validator.error_count == 0


# ---------------------------------------------------------------------------
# MockProvider tests
# ---------------------------------------------------------------------------

class TestMockProvider:
    """Tests for the MockProvider implementation."""

    def test_satisfies_protocol(self):
        provider = MockProvider()
        assert isinstance(provider, DataProvider)

    def test_loads_fixture_data(self):
        provider = MockProvider()
        matches = provider.fetch_matches(4759, "2023")

        assert len(matches) == 64
        assert all(isinstance(m, Match) for m in matches)

    def test_match_fields_populated(self):
        provider = MockProvider()
        matches = provider.fetch_matches(4759, "2023")
        first = matches[0]

        assert first.id == 1001
        assert first.home_team == "Arsenal"
        assert first.away_team == "Chelsea"
        assert first.total_goals == 3
        assert first.home_xg == 1.85

    def test_null_referee_handled(self):
        provider = MockProvider()
        matches = provider.fetch_matches(4759, "2023")

        null_ref_matches = [m for m in matches if m.referee is None]
        assert len(null_ref_matches) >= 2

    def test_zero_xg_handled(self):
        provider = MockProvider()
        matches = provider.fetch_matches(4759, "2023")

        zero_xg = [m for m in matches if m.home_xg == 0.0 and m.away_xg == 0.0]
        assert len(zero_xg) >= 2

    def test_missing_fixture_raises(self, tmp_path):
        provider = MockProvider(fixtures_dir=tmp_path)

        with pytest.raises(FileNotFoundError, match="Fixture file not found"):
            provider.fetch_matches(9999, "2099")

    def test_live_example_raises(self):
        provider = MockProvider(use_live_example=True)

        with pytest.raises(NotImplementedError, match="Live example"):
            provider.fetch_matches(4759, "2023")


# ---------------------------------------------------------------------------
# IngestionPipeline tests
# ---------------------------------------------------------------------------

class TestIngestionPipeline:
    """Tests for the IngestionPipeline orchestrator."""

    def test_ingest_from_fixtures(self):
        pipeline = IngestionPipeline()
        matches = pipeline.ingest_from_fixtures(4759, "2023")

        assert len(matches) == 64
        assert all(isinstance(m, Match) for m in matches)

    def test_ingest_from_raw_records(self, tmp_errors_dir):
        validator = SchemaValidator(errors_dir=tmp_errors_dir)
        pipeline = IngestionPipeline(validator=validator)

        records = [
            _make_raw_record(id=1),
            _make_raw_record(id=2),
            _make_raw_record(id=3, homeGoalCount=None),  # invalid
        ]

        matches = pipeline.ingest_from_raw_records(records)
        assert len(matches) == 2
        assert matches[0].id == 1
        assert matches[1].id == 2

    def test_ingest_from_raw_records_all_invalid(self, tmp_errors_dir):
        validator = SchemaValidator(errors_dir=tmp_errors_dir)
        pipeline = IngestionPipeline(validator=validator)

        records = [
            _make_raw_record(id=None),
            _make_raw_record(homeGoalCount=None),
        ]

        matches = pipeline.ingest_from_raw_records(records)
        assert len(matches) == 0

    def test_ingest_with_caching(self, tmp_cache_dir, tmp_errors_dir):
        cache = CacheManager(cache_dir=tmp_cache_dir)
        validator = SchemaValidator(errors_dir=tmp_errors_dir)
        pipeline = IngestionPipeline(cache=cache, validator=validator)

        # Pre-populate cache with records
        records = [_make_raw_record(id=i) for i in range(5)]
        for record in records:
            cache.put(4759, "2023", record["id"], record)

        # ingest_from_raw_records uses validator directly (no cache lookup)
        # But get_bulk should find cached data
        cached = cache.get_bulk(4759, "2023")
        assert len(cached) == 5

        matches = pipeline.ingest_from_raw_records(cached)
        assert len(matches) == 5

    def test_pipeline_preserves_match_data(self, tmp_errors_dir):
        validator = SchemaValidator(errors_dir=tmp_errors_dir)
        pipeline = IngestionPipeline(validator=validator)

        record = _make_raw_record(
            id=5555,
            home_name="Liverpool",
            away_name="Man City",
            homeGoalCount=3,
            awayGoalCount=2,
            team_a_xg=2.5,
            team_b_xg=1.8,
            referee_name="Oliver",
            o25_potential=1.65,
            u25_potential=2.30,
        )

        matches = pipeline.ingest_from_raw_records([record])
        assert len(matches) == 1

        m = matches[0]
        assert m.id == 5555
        assert m.home_team == "Liverpool"
        assert m.away_team == "Man City"
        assert m.home_goals == 3
        assert m.away_goals == 2
        assert m.total_goals == 5
        assert m.home_xg == 2.5
        assert m.away_xg == 1.8
        assert m.referee == "Oliver"
        assert m.over_odds == 1.65
        assert m.under_odds == 2.30


# ---------------------------------------------------------------------------
# SyntheticMatchGenerator tests
# ---------------------------------------------------------------------------

class TestSyntheticMatchGenerator:
    """Tests for the SyntheticMatchGenerator."""

    def test_generates_correct_count(self, synthetic_generator):
        matches = synthetic_generator.generate(n_matches=50)
        assert len(matches) == 50

    def test_deterministic_output(self, synthetic_generator):
        matches_a = synthetic_generator.generate(n_matches=20, seed=123)
        matches_b = synthetic_generator.generate(n_matches=20, seed=123)
        assert matches_a == matches_b

    def test_different_seeds_different_output(self, synthetic_generator):
        matches_a = synthetic_generator.generate(n_matches=20, seed=1)
        matches_b = synthetic_generator.generate(n_matches=20, seed=2)
        assert matches_a != matches_b

    def test_all_matches_valid(self, synthetic_matches):
        for m in synthetic_matches:
            assert isinstance(m, Match)
            assert m.total_goals == m.home_goals + m.away_goals
            assert m.home_xg >= 0
            assert m.away_xg >= 0
            assert m.over_under_line == 2.5

    def test_chronological_ordering(self, synthetic_matches):
        timestamps = [m.date_unix for m in synthetic_matches]
        assert timestamps == sorted(timestamps)

    def test_null_referees_generated(self):
        from tests.conftest import SyntheticMatchGenerator
        gen = SyntheticMatchGenerator(seed=42)
        matches = gen.generate(n_matches=500, referee_null_pct=0.1)
        null_refs = sum(1 for m in matches if m.referee is None)
        # With 10% rate and 500 matches, expect ~50 (allow range 20-80)
        assert 20 <= null_refs <= 80
