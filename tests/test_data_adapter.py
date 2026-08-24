"""Unit tests for the data provider abstraction layer."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.engine.data.base import BaseDataLoader, MATCH_RECORD_SCHEMA
from src.engine.data.footystats import FootyStatsAdapter
from src.engine.data.synthetic import SyntheticDataLoader


class TestMatchRecordSchema:
    """Tests for the canonical schema definition."""

    def test_schema_has_required_columns(self):
        """Schema includes all identity, metric, market, and outcome columns."""
        assert "match_id" in MATCH_RECORD_SCHEMA
        assert "date_unix" in MATCH_RECORD_SCHEMA
        assert "attacks_home" in MATCH_RECORD_SCHEMA
        assert "fouls_home" in MATCH_RECORD_SCHEMA
        assert "offsides_home" in MATCH_RECORD_SCHEMA
        assert "over_odds" in MATCH_RECORD_SCHEMA
        assert "actual_total" in MATCH_RECORD_SCHEMA

    def test_schema_types_are_valid(self):
        """All schema type annotations are recognized."""
        valid_types = {"int", "float", "str"}
        for col, dtype in MATCH_RECORD_SCHEMA.items():
            assert dtype in valid_types, f"Column '{col}' has invalid type '{dtype}'"


class TestBaseDataLoader:
    """Tests for BaseDataLoader ABC."""

    def test_cannot_instantiate_directly(self):
        """ABC cannot be instantiated without implementing load()."""
        with pytest.raises(TypeError):
            BaseDataLoader()

    def test_validate_schema_adds_missing_columns(self):
        """validate_schema fills missing columns with defaults."""

        class MinimalLoader(BaseDataLoader):
            def load(self, **kwargs):
                return pd.DataFrame({"match_id": [1, 2], "date_unix": [100, 200]})

        loader = MinimalLoader()
        df = loader.load()
        result = loader.validate_schema(df)

        # All schema columns should be present
        for col in MATCH_RECORD_SCHEMA:
            assert col in result.columns

    def test_validate_schema_coerces_types(self):
        """validate_schema coerces string numbers to numeric."""

        class StringLoader(BaseDataLoader):
            def load(self, **kwargs):
                return pd.DataFrame({
                    "match_id": ["1", "2"],
                    "attacks_home": ["50", "60"],
                })

        loader = StringLoader()
        df = loader.load()
        result = loader.validate_schema(df)

        assert result["attacks_home"].dtype in [np.float64, float]

    def test_validate_schema_preserves_extra_columns(self):
        """Extra columns not in schema are preserved."""

        class ExtraLoader(BaseDataLoader):
            def load(self, **kwargs):
                return pd.DataFrame({
                    "match_id": [1],
                    "extra_col": ["hello"],
                })

        loader = ExtraLoader()
        df = loader.load()
        result = loader.validate_schema(df)

        assert "extra_col" in result.columns


class TestFootyStatsAdapter:
    """Tests for FootyStatsAdapter."""

    def _make_raw_df(self, n: int = 5) -> pd.DataFrame:
        """Create a raw DataFrame mimicking FootyStats output."""
        return pd.DataFrame({
            "id": range(1, n + 1),
            "date_unix": range(1000, 1000 + n),
            "competition_id": [4759] * n,
            "season": ["2023/2024"] * n,
            "home_name": [f"Home_{i}" for i in range(n)],
            "away_name": [f"Away_{i}" for i in range(n)],
            "attacks_home": [100 + i for i in range(n)],
            "attacks_away": [90 + i for i in range(n)],
            "dangerous_attacks_home": [50 + i for i in range(n)],
            "dangerous_attacks_away": [45 + i for i in range(n)],
            "shots_off_target_home": [5] * n,
            "shots_off_target_away": [4] * n,
            "fouls_home": [12] * n,
            "fouls_away": [14] * n,
            "team_a_possession": [55.0] * n,
            "team_b_possession": [45.0] * n,
            "referee_cpm": [4.2] * n,
            "team_a_offsides": [3] * n,
            "team_b_offsides": [2] * n,
            "team_a_ppda": [8.5] * n,
            "team_b_ppda": [10.0] * n,
            "o25_potential": [1.85] * n,
            "u25_potential": [2.00] * n,
            "homeGoalCount": [2] * n,
            "awayGoalCount": [1] * n,
        })

    def test_load_from_dataframe(self):
        """Adapter loads and maps from a pre-loaded DataFrame."""
        adapter = FootyStatsAdapter()
        raw = self._make_raw_df()

        result = adapter.load(data=raw)

        assert "match_id" in result.columns
        assert "attacks_home" in result.columns
        assert "possession_home" in result.columns
        assert len(result) == 5

    def test_column_mapping_applied(self):
        """Raw FootyStats columns are renamed to canonical names."""
        adapter = FootyStatsAdapter()
        raw = self._make_raw_df()

        result = adapter.load(data=raw)

        # referee_cpm → referee_cards_per_match
        assert "referee_cards_per_match" in result.columns
        # team_a_possession → possession_home
        assert result["possession_home"].iloc[0] == 55.0

    def test_actual_total_derived_from_goals(self):
        """actual_total computed from homeGoalCount + awayGoalCount."""
        adapter = FootyStatsAdapter()
        raw = self._make_raw_df()

        result = adapter.load(data=raw)

        assert result["actual_total"].iloc[0] == 3.0  # 2 + 1

    def test_market_line_defaults_to_2_5(self):
        """Missing market_line defaults to 2.5."""
        adapter = FootyStatsAdapter()
        raw = self._make_raw_df()
        # No market_line column in raw data

        result = adapter.load(data=raw)

        assert result["market_line"].iloc[0] == 2.5

    def test_load_from_csv(self, tmp_path):
        """Adapter loads from CSV file."""
        adapter = FootyStatsAdapter()
        raw = self._make_raw_df(3)
        csv_path = tmp_path / "matches.csv"
        raw.to_csv(csv_path, index=False)

        result = adapter.load(path=csv_path)

        assert len(result) == 3
        assert "match_id" in result.columns

    def test_load_from_json(self, tmp_path):
        """Adapter loads from JSON file."""
        adapter = FootyStatsAdapter()
        raw = self._make_raw_df(3)
        json_path = tmp_path / "matches.json"
        raw.to_json(json_path)

        result = adapter.load(path=json_path)

        assert len(result) == 3

    def test_load_no_source_raises(self):
        """Neither path nor data raises ValueError."""
        adapter = FootyStatsAdapter()

        with pytest.raises(ValueError, match="Either 'path' or 'data'"):
            adapter.load()

    def test_unsupported_format_raises(self, tmp_path):
        """Unsupported file extension raises ValueError."""
        adapter = FootyStatsAdapter()
        bad_path = tmp_path / "data.xml"
        bad_path.write_text("<data/>")

        with pytest.raises(ValueError, match="Unsupported file format"):
            adapter.load(path=bad_path)

    def test_column_overrides(self):
        """Custom column overrides are applied."""
        raw = pd.DataFrame({
            "my_custom_id": [1, 2],
            "date_unix": [100, 200],
        })
        adapter = FootyStatsAdapter(column_overrides={"my_custom_id": "match_id"})

        result = adapter.load(data=raw)

        assert result["match_id"].iloc[0] == 1

    def test_output_schema_complete(self):
        """Output DataFrame has all MATCH_RECORD_SCHEMA columns."""
        adapter = FootyStatsAdapter()
        raw = self._make_raw_df()

        result = adapter.load(data=raw)

        for col in MATCH_RECORD_SCHEMA:
            assert col in result.columns


class TestSyntheticDataLoader:
    """Tests for SyntheticDataLoader."""

    def test_generates_correct_count(self):
        """Generates specified number of rows."""
        loader = SyntheticDataLoader(n=500, seed=1)
        df = loader.load()

        assert len(df) == 500

    def test_deterministic_output(self):
        """Same seed produces identical output."""
        loader1 = SyntheticDataLoader(n=100, seed=42)
        loader2 = SyntheticDataLoader(n=100, seed=42)

        df1 = loader1.load()
        df2 = loader2.load()

        pd.testing.assert_frame_equal(df1, df2)

    def test_different_seeds_differ(self):
        """Different seeds produce different output."""
        loader1 = SyntheticDataLoader(n=100, seed=1)
        loader2 = SyntheticDataLoader(n=100, seed=2)

        df1 = loader1.load()
        df2 = loader2.load()

        assert not df1["attacks_home"].equals(df2["attacks_home"])

    def test_schema_conformance(self):
        """Output has all MATCH_RECORD_SCHEMA columns."""
        loader = SyntheticDataLoader(n=50, seed=1)
        df = loader.load()

        for col in MATCH_RECORD_SCHEMA:
            assert col in df.columns

    def test_nan_injection(self):
        """NaN values are injected at approximately the configured rate."""
        loader = SyntheticDataLoader(n=10000, seed=1, nan_rate=0.10)
        df = loader.load()

        # Check a float column for NaN presence
        nan_rate = df["attacks_home"].isna().mean()
        # Should be roughly 10% (allow tolerance)
        assert 0.05 < nan_rate < 0.20

    def test_no_nan_when_rate_zero(self):
        """No NaN injected when nan_rate=0."""
        loader = SyntheticDataLoader(n=100, seed=1, nan_rate=0.0, extreme_rate=0.0, void_rate=0.0)
        df = loader.load()

        # Float columns should have no NaN (except naturally)
        assert df["attacks_home"].notna().all()
        assert df["actual_total"].notna().all()

    def test_extreme_values_injected(self):
        """Extreme values are present when extreme_rate > 0."""
        loader = SyntheticDataLoader(n=5000, seed=1, nan_rate=0.0, extreme_rate=0.05)
        df = loader.load()

        # Some referee_cards_per_match should be > 10
        assert (df["referee_cards_per_match"] > 10).any()

    def test_void_matches_have_nan_outcome(self):
        """Void matches have NaN actual_total."""
        loader = SyntheticDataLoader(n=5000, seed=1, nan_rate=0.0, void_rate=0.05)
        df = loader.load()

        # Some actual_total should be NaN
        assert df["actual_total"].isna().any()

    def test_performance_10k_under_1_second(self):
        """10,000 rows generated in under 1 second."""
        import time
        loader = SyntheticDataLoader(n=10000, seed=1)
        start = time.perf_counter()
        loader.load()
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0

    def test_compatible_with_xmetric_engine(self):
        """Output can be fed directly to XMetricEngine.compute_all()."""
        from src.engine.xmetrics import XMetricEngine

        loader = SyntheticDataLoader(n=100, seed=42, nan_rate=0.0)
        df = loader.load()

        engine = XMetricEngine()
        result = engine.compute_all(df)

        assert "home_xC" in result.columns
        assert "home_xB" in result.columns
        assert "home_xO" in result.columns
