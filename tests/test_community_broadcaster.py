"""Unit tests for community signal broadcaster."""

from __future__ import annotations

import datetime
import logging

import pytest

from src.engine.analysis.evaluator import Signal
from src.engine.market.metrics.bookie import BookieMetrics
from src.engine.market.signals.community_broadcaster import (
    BroadcastConfig,
    CommunityBroadcaster,
)
from src.engine.market.signals.crypto_exporter import SignalPayload
from src.engine.market.signals.deeplinker import DeepLink

# Fixed clock outside the default quiet-hours window (1am-6am UTC), used by
# tests that aren't specifically exercising quiet-hours behavior — otherwise
# they'd flake depending on the real wall-clock hour they happen to run at.
_NOON_UTC_CLOCK = lambda: datetime.datetime(2024, 6, 15, 12, 0, tzinfo=datetime.timezone.utc)


class TestBroadcastConfig:
    """Tests for BroadcastConfig."""

    def test_defaults(self):
        """Default config has expected values."""
        config = BroadcastConfig()
        assert config.poll_interval_seconds == 300
        assert config.quiet_hours_start == 1
        assert config.quiet_hours_end == 6
        assert config.dry_run is False

    def test_custom_config(self):
        """Custom values override defaults."""
        config = BroadcastConfig(
            poll_interval_seconds=60,
            quiet_hours_start=23,
            quiet_hours_end=7,
            dry_run=True,
        )
        assert config.poll_interval_seconds == 60
        assert config.dry_run is True


class TestCommunityBroadcaster:
    """Tests for CommunityBroadcaster."""

    def _make_signal(self) -> Signal:
        return Signal(
            match_index=0,
            strategy_name="Test Strategy",
            direction="OVER",
            condition_strength=0.12,
            odds=2.00,
        )

    def _make_metrics(self) -> BookieMetrics:
        return BookieMetrics(
            btbr_pct=65.0,
            vig_adjusted_edge_pct=4.5,
            confidence_index=95.0,
            total_signals=100,
            signals_beating_close=65,
            raw_edge_pct=10.5,
        )

    def test_quiet_hours_within(self):
        """Returns True when hour is in quiet period."""
        config = BroadcastConfig(quiet_hours_start=1, quiet_hours_end=6)
        broadcaster = CommunityBroadcaster(config=config)

        assert broadcaster.is_quiet_hours(1) is True
        assert broadcaster.is_quiet_hours(3) is True
        assert broadcaster.is_quiet_hours(5) is True

    def test_quiet_hours_outside(self):
        """Returns False when hour is outside quiet period."""
        config = BroadcastConfig(quiet_hours_start=1, quiet_hours_end=6)
        broadcaster = CommunityBroadcaster(config=config)

        assert broadcaster.is_quiet_hours(0) is False
        assert broadcaster.is_quiet_hours(6) is False
        assert broadcaster.is_quiet_hours(12) is False
        assert broadcaster.is_quiet_hours(23) is False

    def test_quiet_hours_wrapping_midnight(self):
        """Handles quiet hours that wrap past midnight."""
        config = BroadcastConfig(quiet_hours_start=22, quiet_hours_end=6)
        broadcaster = CommunityBroadcaster(config=config)

        assert broadcaster.is_quiet_hours(22) is True
        assert broadcaster.is_quiet_hours(23) is True
        assert broadcaster.is_quiet_hours(0) is True
        assert broadcaster.is_quiet_hours(3) is True
        assert broadcaster.is_quiet_hours(5) is True
        assert broadcaster.is_quiet_hours(6) is False
        assert broadcaster.is_quiet_hours(12) is False
        assert broadcaster.is_quiet_hours(21) is False

    @pytest.mark.asyncio
    async def test_run_once_dry_run(self):
        """Dry-run produces payloads without dispatching.
        R05: Without explicit validation_passed=True, badge must be False.
        """
        config = BroadcastConfig(dry_run=True)
        broadcaster = CommunityBroadcaster(config=config, clock=_NOON_UTC_CLOCK)

        signals = [self._make_signal()]
        match_data = [{"home_team": "Arsenal", "away_team": "Chelsea", "league": "PL"}]
        metrics = self._make_metrics()

        payloads = await broadcaster.run_once(signals, match_data, metrics)

        assert len(payloads) == 1
        assert isinstance(payloads[0], SignalPayload)
        assert payloads[0].direction == "OVER"
        # R05 fix: default is NOT validated (authoritative system must confirm)
        assert payloads[0].fdr_validated is False

    @pytest.mark.asyncio
    async def test_run_once_multiple_signals(self):
        """Handles multiple signals in one broadcast."""
        config = BroadcastConfig(dry_run=True)
        broadcaster = CommunityBroadcaster(config=config, clock=_NOON_UTC_CLOCK)

        signals = [self._make_signal(), self._make_signal(), self._make_signal()]
        match_data = [
            {"home_team": "A", "away_team": "B"},
            {"home_team": "C", "away_team": "D"},
            {"home_team": "E", "away_team": "F"},
        ]

        payloads = await broadcaster.run_once(signals, match_data)
        assert len(payloads) == 3

    @pytest.mark.asyncio
    async def test_run_once_uses_injected_clock_not_wall_clock(self):
        """Quiet-hours check must use the injected clock, never a direct
        datetime.now() call — otherwise it's non-deterministic and any real
        signal generated 1am-6am UTC is silently dropped with no way to test it.
        """
        quiet_clock = lambda: datetime.datetime(2026, 1, 1, 3, 0, tzinfo=datetime.timezone.utc)
        config = BroadcastConfig(dry_run=True, quiet_hours_start=1, quiet_hours_end=6)
        broadcaster = CommunityBroadcaster(config=config, clock=quiet_clock)

        signals = [self._make_signal()]
        match_data = [{"home_team": "Arsenal", "away_team": "Chelsea"}]

        result = await broadcaster.run_once(signals, match_data)
        assert len(result) == 0  # suppressed regardless of real wall-clock time

        active_clock = lambda: datetime.datetime(2026, 1, 1, 14, 0, tzinfo=datetime.timezone.utc)
        broadcaster2 = CommunityBroadcaster(config=config, clock=active_clock)
        result2 = await broadcaster2.run_once(signals, match_data)
        assert len(result2) == 1  # not suppressed outside quiet hours

    @pytest.mark.asyncio
    async def test_run_once_quiet_hours_suppression_is_logged(self, caplog):
        """Suppressed signals must be visible to operators (WARNING), not silent."""
        quiet_clock = lambda: datetime.datetime(2026, 1, 1, 3, 0, tzinfo=datetime.timezone.utc)
        config = BroadcastConfig(dry_run=True, quiet_hours_start=1, quiet_hours_end=6)
        broadcaster = CommunityBroadcaster(config=config, clock=quiet_clock)

        signals = [self._make_signal(), self._make_signal()]
        match_data = [{"home_team": "A", "away_team": "B"}, {"home_team": "C", "away_team": "D"}]

        with caplog.at_level(logging.WARNING):
            await broadcaster.run_once(signals, match_data)

        assert any(
            record.levelno == logging.WARNING and "suppressing 2 signal" in record.message
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_run_once_stake_is_risk_tier_not_hardcoded(self):
        """R06: stake must scale with edge magnitude, not a hardcoded flat value."""
        config = BroadcastConfig(dry_run=True)
        broadcaster = CommunityBroadcaster(config=config, clock=_NOON_UTC_CLOCK)

        big_edge_signal = Signal(
            match_index=0, strategy_name="Big Strength", direction="OVER", condition_strength=0.12, odds=2.0
        )
        small_edge_signal = Signal(
            match_index=1, strategy_name="Small Strength", direction="OVER", condition_strength=0.01, odds=2.0
        )
        match_data = [{"home_team": "A", "away_team": "B"}, {"home_team": "C", "away_team": "D"}]

        result = await broadcaster.run_once([big_edge_signal, small_edge_signal], match_data)

        assert result.payloads[0].stake_tier == "1.00U"
        assert result.payloads[1].stake_tier == "0.25U"
        assert result.payloads[0].recommended_stake > result.payloads[1].recommended_stake

    @pytest.mark.asyncio
    async def test_run_once_empty_signals(self):
        """Empty signal list produces no payloads."""
        config = BroadcastConfig(dry_run=True)
        broadcaster = CommunityBroadcaster(config=config)

        payloads = await broadcaster.run_once([], [])
        assert payloads == []

    def test_format_broadcast_telegram(self):
        """Telegram format includes all required fields."""
        broadcaster = CommunityBroadcaster(config=BroadcastConfig(dry_run=True))

        payload = SignalPayload(
            match_info="Arsenal vs Chelsea (PL)",
            market_line="OVER (edge: 12.0%)",
            direction="OVER",
            recommended_stake=0.05,
            edge_pct=4.5,
            confidence=95.0,
            fdr_validated=True,
            proof_hash="a" * 64,
            timestamp=1000,
        )

        deep_links = [
            DeepLink(platform="stake", url="https://stake.com/test", label="Place Bet on Stake"),
            DeepLink(platform="rollbit", url="https://rollbit.com/test", label="Place Bet on Rollbit"),
        ]

        msg = broadcaster.format_broadcast_telegram(payload, deep_links)

        assert "Arsenal vs Chelsea" in msg
        assert "OVER" in msg
        assert "FDR-VALIDATED" in msg
        assert "4.50%" in msg
        assert "95/100" in msg
        assert "Place Bet on Stake" in msg
        assert "https://stake.com/test" in msg

    def test_format_broadcast_discord(self):
        """Discord format produces valid embed structure."""
        broadcaster = CommunityBroadcaster(config=BroadcastConfig(dry_run=True))

        payload = SignalPayload(
            match_info="Arsenal vs Chelsea",
            market_line="OVER",
            direction="OVER",
            recommended_stake=0.05,
            edge_pct=4.5,
            confidence=95.0,
            fdr_validated=True,
            proof_hash="b" * 64,
            timestamp=1000,
        )

        deep_links = [
            DeepLink(platform="stake", url="https://stake.com/t", label="Stake"),
        ]

        embed = broadcaster.format_broadcast_discord(payload, deep_links)

        assert "embeds" in embed
        assert embed["embeds"][0]["color"] == 0x00FF00
        assert "Signal: Arsenal vs Chelsea" in embed["embeds"][0]["title"]
        fields = {f["name"]: f["value"] for f in embed["embeds"][0]["fields"]}
        assert "Direction" in fields
        assert "Confidence" in fields
        assert "Action Links" in fields

    def test_format_broadcast_discord_unvalidated(self):
        """Unvalidated signals get amber color."""
        broadcaster = CommunityBroadcaster(config=BroadcastConfig(dry_run=True))

        payload = SignalPayload(
            match_info="Test",
            market_line="UNDER",
            direction="UNDER",
            recommended_stake=0.02,
            edge_pct=2.0,
            confidence=80.0,
            fdr_validated=False,
            proof_hash="c" * 64,
            timestamp=1000,
        )

        embed = broadcaster.format_broadcast_discord(payload, [])
        assert embed["embeds"][0]["color"] == 0xFFAA00
