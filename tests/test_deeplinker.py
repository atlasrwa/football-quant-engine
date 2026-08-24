"""Unit tests for the 1-click bet deep-linker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.api.routes.builder_ui import (
    BENCHMARK_STRATEGIES,
    get_template_by_metric,
    get_template_by_name,
    get_templates,
)
from src.engine.evaluator import Signal, StrategyEvaluator
from src.engine.signals.deeplinker import DeepLink, DeepLinkConfig, DeepLinker


class TestDeepLinker:
    """Tests for DeepLinker URL generation."""

    def _make_signal(self) -> Signal:
        return Signal(
            match_index=0,
            strategy_name="Test",
            direction="OVER",
            edge=0.10,
            odds=2.00,
        )

    def _make_match_info(self) -> dict:
        return {
            "home_team": "Arsenal",
            "away_team": "Chelsea",
            "league": "Premier League",
            "market": "corners",
        }

    def test_generate_links_all_platforms(self):
        """Generates links for all 3 platforms."""
        linker = DeepLinker()
        signal = self._make_signal()
        match_info = self._make_match_info()

        links = linker.generate_links(signal, match_info)

        assert len(links) == 3
        platforms = {l.platform for l in links}
        assert platforms == {"stake", "rollbit", "polymarket"}

    def test_stake_url_structure(self):
        """Stake URL contains event slug and market param."""
        linker = DeepLinker()
        match_info = self._make_match_info()

        url = linker.generate_stake_url(match_info, "corners")

        assert "stake.com/sports/football" in url
        assert "arsenal-vs-chelsea" in url
        assert "market=corners" in url

    def test_rollbit_url_structure(self):
        """Rollbit URL contains event slug and market param."""
        linker = DeepLinker()
        match_info = self._make_match_info()

        url = linker.generate_rollbit_url(match_info, "corners")

        assert "rollbit.com/sports/soccer" in url
        assert "arsenal-vs-chelsea" in url
        assert "market=corners" in url

    def test_polymarket_url_structure(self):
        """Polymarket URL contains event slug."""
        linker = DeepLinker()
        match_info = self._make_match_info()

        url = linker.generate_polymarket_url(match_info, "corners")

        assert "polymarket.com/event" in url
        assert "arsenal-chelsea-corners" in url

    def test_affiliate_tag_stake(self):
        """Stake affiliate tag injected into URL."""
        config = DeepLinkConfig(affiliate_stake="my_ref_123")
        linker = DeepLinker(config=config)

        url = linker.generate_stake_url(self._make_match_info(), "corners")
        assert "ref=my_ref_123" in url

    def test_affiliate_tag_rollbit(self):
        """Rollbit affiliate tag injected into URL."""
        config = DeepLinkConfig(affiliate_rollbit="aff_456")
        linker = DeepLinker(config=config)

        url = linker.generate_rollbit_url(self._make_match_info(), "corners")
        assert "aff=aff_456" in url

    def test_no_affiliate_by_default(self):
        """No affiliate params when tags are None."""
        linker = DeepLinker()
        url = linker.generate_stake_url(self._make_match_info(), "corners")
        assert "ref=" not in url

    def test_url_encoding_special_chars(self):
        """Special characters in team names are URL-encoded."""
        linker = DeepLinker()
        match_info = {"home_team": "FC Köln", "away_team": "1. FC Nürnberg"}

        url = linker.generate_stake_url(match_info, "cards")
        # Should not contain raw unicode or spaces
        assert " " not in url

    def test_generate_telegram_buttons(self):
        """Generates Telegram inline keyboard buttons."""
        linker = DeepLinker()
        links = [
            DeepLink(platform="stake", url="https://stake.com/x", label="Stake"),
            DeepLink(platform="rollbit", url="https://rollbit.com/x", label="Rollbit"),
        ]

        buttons = linker.generate_telegram_buttons(links, "abc123" * 10)

        # 2 link buttons + 1 proof button
        assert len(buttons) == 3
        assert buttons[0]["text"] == "Stake"
        assert buttons[0]["url"] == "https://stake.com/x"
        assert buttons[2]["text"] == "View Proof-of-Alpha Hash"
        assert "proof:" in buttons[2]["callback_data"]

    def test_generate_telegram_keyboard(self):
        """Generates full inline keyboard markup."""
        linker = DeepLinker()
        links = [
            DeepLink(platform="stake", url="https://stake.com/x", label="Stake"),
        ]

        keyboard = linker.generate_telegram_keyboard(links, "hash123" * 10)

        assert "inline_keyboard" in keyboard
        assert len(keyboard["inline_keyboard"]) == 2  # 1 link + 1 proof

    def test_missing_match_info_fields(self):
        """Handles missing optional fields gracefully."""
        linker = DeepLinker()
        match_info = {}  # empty

        links = linker.generate_links(self._make_signal(), match_info)
        assert len(links) == 3
        # Should use defaults without crashing
        for link in links:
            assert "http" in link.url


class TestBuilderTemplates:
    """Tests for benchmark strategy templates."""

    def test_get_templates_returns_10(self):
        """Returns exactly 10 benchmark strategies."""
        templates = get_templates()
        assert len(templates) == 10

    def test_template_structure(self):
        """Each template has required fields."""
        templates = get_templates()
        required_fields = {"name", "metric", "market", "conditions", "logic", "direction", "min_odds"}

        for t in templates:
            assert required_fields.issubset(t.keys()), f"Missing fields in '{t.get('name')}'"

    def test_get_by_metric_xC(self):
        """Filtering by xC returns 4 strategies."""
        xc = get_template_by_metric("xC")
        assert len(xc) == 4
        assert all(s["metric"] == "xC" for s in xc)

    def test_get_by_metric_xB(self):
        """Filtering by xB returns 3 strategies."""
        xb = get_template_by_metric("xB")
        assert len(xb) == 3

    def test_get_by_metric_xO(self):
        """Filtering by xO returns 3 strategies."""
        xo = get_template_by_metric("xO")
        assert len(xo) == 3

    def test_get_by_name(self):
        """Find template by exact name."""
        result = get_template_by_name("EPL Corner Pressure Over")
        assert result is not None
        assert result["metric"] == "xC"

    def test_get_by_name_not_found(self):
        """Returns None for unknown name."""
        assert get_template_by_name("Nonexistent") is None

    def test_templates_loadable_by_evaluator(self):
        """All templates can be loaded by StrategyEvaluator."""
        evaluator = StrategyEvaluator()
        templates = get_templates()

        # Remove non-schema fields before loading
        loadable = []
        for t in templates:
            clean = {k: v for k, v in t.items() if k in {"name", "metric", "market", "conditions", "logic", "direction", "min_odds"}}
            loadable.append(clean)

        strategies = evaluator.load_strategies_from_list(loadable)
        assert len(strategies) == 10

    def test_benchmark_json_files_exist(self):
        """All 10 benchmark JSON files exist on disk."""
        benchmark_dir = Path("data/strategies/benchmarks")
        json_files = list(benchmark_dir.glob("*.json"))
        assert len(json_files) == 10

    def test_benchmark_json_files_valid(self):
        """All benchmark JSON files are valid and loadable."""
        evaluator = StrategyEvaluator()
        benchmark_dir = Path("data/strategies/benchmarks")

        for json_file in benchmark_dir.glob("*.json"):
            strategies = evaluator.load_strategies(json_file)
            assert len(strategies) == 1, f"Failed for {json_file.name}"

    def test_benchmark_metrics_distribution(self):
        """JSON files have correct metric distribution: 4 xC, 3 xB, 3 xO."""
        evaluator = StrategyEvaluator()
        benchmark_dir = Path("data/strategies/benchmarks")

        metrics = {"xC": 0, "xB": 0, "xO": 0}
        for json_file in benchmark_dir.glob("*.json"):
            strategies = evaluator.load_strategies(json_file)
            metrics[strategies[0].metric] += 1

        assert metrics["xC"] == 4
        assert metrics["xB"] == 3
        assert metrics["xO"] == 3
