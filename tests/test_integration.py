"""End-to-end integration tests for the Football Quant Engine.

Tests the full pipeline: ingest → features → backtest → serialization.
Covers determinism, CLI invocation, result structure, and edge cases.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List

import pytest

from src.backtest.engine import WalkForwardEngine
from src.cli import main as cli_main
from src.features.assembler import FeatureAssembler
from src.ingestion.pipeline import IngestionPipeline
from src.ingestion.provider import MockProvider
from src.models.config import StrategyConfig
from src.models.features import MatchFeatures
from src.models.match import Match
from src.models.results import BacktestResult
from src.serializer import format_summary, result_to_dict, save_result


# ---------------------------------------------------------------------------
# Full Pipeline Integration Tests
# ---------------------------------------------------------------------------

class TestFullPipeline:
    """End-to-end tests running the complete pipeline."""

    def test_ingest_to_features_to_backtest(self):
        """Full pipeline: MockProvider → FeatureAssembler → WalkForwardEngine."""
        # Ingest
        provider = MockProvider()
        matches = provider.fetch_matches(4759, "2023")
        assert len(matches) == 64
        assert all(isinstance(m, Match) for m in matches)

        # Features
        config = StrategyConfig(
            train_window=20, test_window=10, step_size=10,
            min_edge_threshold=0.0,
        )
        assembler = FeatureAssembler(config=config)
        features = assembler.assemble(matches)
        assert len(features) == 64
        assert all(isinstance(f, MatchFeatures) for f in features)

        # Backtest
        engine = WalkForwardEngine(config=config)
        result = engine.run(features)

        assert isinstance(result, BacktestResult)
        assert result.total_bets > 0
        assert len(result.fold_results) > 0
        assert len(result.bet_log) == result.total_bets

    def test_pipeline_via_ingestion_pipeline(self):
        """Use IngestionPipeline.ingest_from_fixtures as entry point."""
        pipeline = IngestionPipeline()
        matches = pipeline.ingest_from_fixtures(4759, "2023")

        config = StrategyConfig(
            train_window=15, test_window=8, step_size=8,
            min_edge_threshold=0.0,
        )
        assembler = FeatureAssembler(config=config)
        features = assembler.assemble(matches)

        engine = WalkForwardEngine(config=config)
        result = engine.run(features)

        assert result.total_bets > 0
        assert -500.0 <= result.net_roi_pct <= 500.0
        assert 0.0 <= result.win_rate_pct <= 100.0
        assert result.max_drawdown_pct >= 0.0
        assert 0.0 <= result.p_value <= 1.0

    def test_deterministic_full_pipeline(self):
        """Two runs with same config produce identical results."""
        config = StrategyConfig(
            train_window=20, test_window=10, step_size=10,
            min_edge_threshold=0.0, random_seed=42,
        )

        def run_pipeline() -> BacktestResult:
            matches = MockProvider().fetch_matches(4759, "2023")
            features = FeatureAssembler(config=config).assemble(matches)
            return WalkForwardEngine(config=config).run(features)

        result1 = run_pipeline()
        result2 = run_pipeline()

        assert result1.total_bets == result2.total_bets
        assert result1.net_roi_pct == result2.net_roi_pct
        assert result1.win_rate_pct == result2.win_rate_pct
        assert result1.max_drawdown_pct == result2.max_drawdown_pct
        assert result1.total_profit == result2.total_profit

        # Bet logs should be identical
        for b1, b2 in zip(result1.bet_log, result2.bet_log):
            assert b1.match_id == b2.match_id
            assert b1.prediction == b2.prediction
            assert b1.profit_loss == b2.profit_loss

    def test_different_configs_different_results(self):
        """Changing config should produce different outcomes."""
        matches = MockProvider().fetch_matches(4759, "2023")

        config1 = StrategyConfig(
            train_window=20, test_window=10, step_size=10,
            min_edge_threshold=0.0,
        )
        config2 = StrategyConfig(
            train_window=20, test_window=10, step_size=10,
            min_edge_threshold=0.5,  # Higher threshold → fewer bets
        )

        features = FeatureAssembler(config=config1).assemble(matches)

        result1 = WalkForwardEngine(config=config1).run(features)
        result2 = WalkForwardEngine(config=config2).run(features)

        # Higher edge threshold should produce fewer or equal bets
        assert result2.total_bets <= result1.total_bets

    def test_pipeline_with_synthetic_data(self, synthetic_matches):
        """Pipeline works with synthetic generator output."""
        config = StrategyConfig(
            train_window=30, test_window=15, step_size=15,
            min_edge_threshold=0.0,
        )
        assembler = FeatureAssembler(config=config)
        features = assembler.assemble(synthetic_matches)

        engine = WalkForwardEngine(config=config)
        result = engine.run(features)

        assert isinstance(result, BacktestResult)
        # With 100 matches and these windows, should get at least 1 fold
        assert len(result.fold_results) >= 1


# ---------------------------------------------------------------------------
# Serialization Integration Tests
# ---------------------------------------------------------------------------

class TestSerialization:
    """Tests for result serialization and output."""

    def _run_backtest(self) -> BacktestResult:
        """Helper to run a quick backtest."""
        matches = MockProvider().fetch_matches(4759, "2023")
        config = StrategyConfig(
            train_window=20, test_window=10, step_size=10,
            min_edge_threshold=0.0,
        )
        features = FeatureAssembler(config=config).assemble(matches)
        return WalkForwardEngine(config=config).run(features)

    def test_result_to_dict_structure(self):
        """Serialized dict has correct top-level keys."""
        result = self._run_backtest()
        data = result_to_dict(result)

        assert "metadata" in data
        assert "strategy_config" in data
        assert "aggregate_metrics" in data
        assert "fold_results" in data
        assert "bet_log" in data

    def test_result_to_dict_is_json_serializable(self):
        """Dict can be serialized to JSON without errors."""
        result = self._run_backtest()
        data = result_to_dict(result)

        # Should not raise
        json_str = json.dumps(data, indent=2)
        assert len(json_str) > 0

        # Should round-trip
        loaded = json.loads(json_str)
        assert loaded["aggregate_metrics"]["total_bets"] == result.total_bets

    def test_save_result_creates_file(self, tmp_path):
        """save_result writes a valid JSON file."""
        result = self._run_backtest()
        path = save_result(result, output_dir=tmp_path, filename="test_result.json")

        assert path.exists()
        assert path.name == "test_result.json"

        with open(path) as f:
            loaded = json.load(f)
        assert loaded["aggregate_metrics"]["total_bets"] == result.total_bets
        assert len(loaded["bet_log"]) == result.total_bets

    def test_save_result_auto_filename(self, tmp_path):
        """save_result generates timestamp-based filename if not specified."""
        result = self._run_backtest()
        path = save_result(result, output_dir=tmp_path)

        assert path.exists()
        assert path.name.startswith("backtest_")
        assert path.suffix == ".json"

    def test_format_summary_contains_metrics(self):
        """Summary string includes key metric values."""
        result = self._run_backtest()
        summary = format_summary(result)

        assert "BACKTEST RESULTS" in summary
        assert "Net ROI" in summary
        assert "Win Rate" in summary
        assert "Max Drawdown" in summary
        assert "p-value" in summary
        assert "Total Bets" in summary
        assert str(result.total_bets) in summary

    def test_format_summary_includes_fold_breakdown(self):
        """Summary includes per-fold information."""
        result = self._run_backtest()
        summary = format_summary(result)

        assert "Fold 0" in summary
        assert "ROI=" in summary

    def test_bet_log_in_output(self, tmp_path):
        """Saved result contains complete bet log with all fields."""
        result = self._run_backtest()
        path = save_result(result, output_dir=tmp_path)

        with open(path) as f:
            loaded = json.load(f)

        for bet in loaded["bet_log"]:
            assert "match_id" in bet
            assert "date_unix" in bet
            assert "prediction" in bet
            assert "actual_outcome" in bet
            assert "odds" in bet
            assert "stake" in bet
            assert "profit_loss" in bet
            assert bet["prediction"] in ("OVER", "UNDER")
            assert bet["actual_outcome"] in ("OVER", "UNDER")


# ---------------------------------------------------------------------------
# CLI Integration Tests
# ---------------------------------------------------------------------------

class TestCLI:
    """Tests for the CLI interface."""

    def test_cli_help(self, capsys):
        """CLI with no args prints help without error."""
        exit_code = cli_main([])
        assert exit_code == 0

    def test_cli_ingest(self, capsys):
        """CLI ingest command runs successfully."""
        exit_code = cli_main(["ingest", "--league-id", "4759", "--season", "2023"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "64 matches" in captured.out

    def test_cli_features(self, capsys):
        """CLI features command runs successfully."""
        exit_code = cli_main(["features", "--league-id", "4759", "--season", "2023"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "64 matches" in captured.out
        assert "64 feature vectors" in captured.out

    def test_cli_backtest(self, capsys, tmp_path):
        """CLI backtest command produces output."""
        exit_code = cli_main([
            "backtest",
            "--league-id", "4759", "--season", "2023",
            "--train-window", "20", "--test-window", "10",
            "--step-size", "10", "--min-edge", "0.0",
            "--output", str(tmp_path),
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "BACKTEST RESULTS" in captured.out
        assert "Results saved to" in captured.out

        # Check output file was created
        json_files = list(tmp_path.glob("backtest_*.json"))
        assert len(json_files) == 1

    def test_cli_run_full_pipeline(self, capsys, tmp_path):
        """CLI run command executes full pipeline."""
        exit_code = cli_main([
            "run",
            "--league-id", "4759", "--season", "2023",
            "--train-window", "20", "--test-window", "10",
            "--step-size", "10", "--min-edge", "0.0",
            "--output", str(tmp_path),
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "Full Pipeline" in captured.out
        assert "matches loaded" in captured.out
        assert "feature vectors assembled" in captured.out
        assert "bets placed" in captured.out
        assert "BACKTEST RESULTS" in captured.out

    def test_cli_verbose(self, capsys):
        """CLI verbose flag doesn't crash."""
        exit_code = cli_main(["ingest", "-v"])
        assert exit_code == 0

    def test_cli_config_file(self, capsys, tmp_path):
        """CLI respects JSON config file."""
        config = {
            "train_window": 15,
            "test_window": 8,
            "step_size": 8,
            "min_edge_threshold": 0.0,
        }
        config_path = tmp_path / "config.json"
        with open(config_path, "w") as f:
            json.dump(config, f)

        exit_code = cli_main([
            "backtest",
            "--config-file", str(config_path),
            "--output", str(tmp_path),
        ])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "BACKTEST RESULTS" in captured.out


# ---------------------------------------------------------------------------
# Edge Case Integration Tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Integration tests for boundary conditions and edge cases."""

    def test_minimal_data_no_folds(self):
        """Very small dataset that can't produce any folds."""
        matches = MockProvider().fetch_matches(4759, "2023")[:10]
        config = StrategyConfig(
            train_window=100, test_window=20, step_size=20,
            min_edge_threshold=0.0,
        )

        features = FeatureAssembler(config=config).assemble(matches)
        result = WalkForwardEngine(config=config).run(features)

        assert result.total_bets == 0
        assert result.fold_results == []
        assert result.net_roi_pct == 0.0
        assert result.p_value == 1.0

    def test_high_threshold_no_bets(self):
        """Very high edge threshold results in no bets."""
        matches = MockProvider().fetch_matches(4759, "2023")
        config = StrategyConfig(
            train_window=20, test_window=10, step_size=10,
            min_edge_threshold=0.99,  # Nearly impossible
        )

        features = FeatureAssembler(config=config).assemble(matches)
        result = WalkForwardEngine(config=config).run(features)

        assert result.total_bets == 0

    def test_single_fold_execution(self):
        """Exactly enough data for one fold."""
        matches = MockProvider().fetch_matches(4759, "2023")[:30]
        config = StrategyConfig(
            train_window=20, test_window=10, step_size=10,
            min_edge_threshold=0.0,
        )

        features = FeatureAssembler(config=config).assemble(matches)
        result = WalkForwardEngine(config=config).run(features)

        assert len(result.fold_results) == 1

    def test_all_matches_zero_xg(self):
        """Pipeline handles matches with zero xG without crashing."""
        from tests.conftest import SyntheticMatchGenerator

        gen = SyntheticMatchGenerator(seed=99)
        # Generate matches that will have near-zero xG
        matches = gen.generate(n_matches=60, xg_noise=0.0, mean_goals=0.5)

        config = StrategyConfig(
            train_window=20, test_window=10, step_size=10,
            min_edge_threshold=0.0,
        )

        features = FeatureAssembler(config=config).assemble(matches)
        result = WalkForwardEngine(config=config).run(features)

        assert isinstance(result, BacktestResult)
        # Should not crash; may have zero bets depending on signals

    def test_result_metrics_consistency(self):
        """Verify metric values are internally consistent."""
        matches = MockProvider().fetch_matches(4759, "2023")
        config = StrategyConfig(
            train_window=20, test_window=10, step_size=10,
            min_edge_threshold=0.0,
        )

        features = FeatureAssembler(config=config).assemble(matches)
        result = WalkForwardEngine(config=config).run(features)

        if result.total_bets > 0:
            # ROI consistency
            expected_roi = (result.total_profit / result.total_staked) * 100.0
            assert abs(result.net_roi_pct - expected_roi) < 0.01

            # Win rate consistency
            wins = sum(1 for b in result.bet_log if b.is_win)
            expected_wr = (wins / result.total_bets) * 100.0
            assert abs(result.win_rate_pct - expected_wr) < 0.01

            # Total profit consistency
            expected_profit = sum(b.profit_loss for b in result.bet_log)
            assert abs(result.total_profit - expected_profit) < 0.01

            # Total staked consistency
            expected_staked = sum(b.stake for b in result.bet_log)
            assert abs(result.total_staked - expected_staked) < 0.01

    def test_fold_bets_sum_to_total(self):
        """Sum of per-fold bet counts equals total bets."""
        matches = MockProvider().fetch_matches(4759, "2023")
        config = StrategyConfig(
            train_window=15, test_window=8, step_size=8,
            min_edge_threshold=0.0,
        )

        features = FeatureAssembler(config=config).assemble(matches)
        result = WalkForwardEngine(config=config).run(features)

        fold_bet_sum = sum(fr.num_bets for fr in result.fold_results)
        assert fold_bet_sum == result.total_bets
