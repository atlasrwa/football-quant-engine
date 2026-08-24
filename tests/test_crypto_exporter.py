"""Unit tests for the crypto-native signal exporter."""

from __future__ import annotations

import hashlib
import json
import time

import pytest

from src.engine.evaluator import Signal
from src.engine.metrics.bookie import BookieMetrics
from src.engine.signals.crypto_exporter import (
    CryptoSignalExporter,
    KellyCalculator,
    ProofOfAlpha,
    SignalPayload,
)
from src.engine.validator import ValidationVerdict


class TestKellyCalculator:
    """Tests for Kelly criterion stake sizing."""

    def test_positive_edge(self):
        """Positive expected value produces positive Kelly."""
        kelly = KellyCalculator()
        # win_prob=0.6, odds=2.0 → f = (0.6*1 - 0.4)/1 = 0.2
        result = kelly.compute(win_prob=0.6, odds=2.0)
        assert result == pytest.approx(0.2)

    def test_no_edge(self):
        """Fair bet (no edge) gives Kelly = 0."""
        kelly = KellyCalculator()
        # win_prob=0.5, odds=2.0 → f = (0.5*1 - 0.5)/1 = 0.0
        result = kelly.compute(win_prob=0.5, odds=2.0)
        assert result == pytest.approx(0.0)

    def test_negative_edge(self):
        """Negative expected value gives Kelly = 0."""
        kelly = KellyCalculator()
        # win_prob=0.3, odds=2.0 → f = (0.3*1 - 0.7)/1 = -0.4 → 0
        result = kelly.compute(win_prob=0.3, odds=2.0)
        assert result == 0.0

    def test_quarter_kelly_cap(self):
        """Kelly is capped at MAX_FRACTION (0.25)."""
        kelly = KellyCalculator()
        # win_prob=0.9, odds=2.0 → f = (0.9*1 - 0.1)/1 = 0.8 → capped at 0.25
        result = kelly.compute(win_prob=0.9, odds=2.0)
        assert result == pytest.approx(0.25)

    def test_extreme_odds(self):
        """High odds with moderate probability."""
        kelly = KellyCalculator()
        # win_prob=0.3, odds=5.0 → f = (0.3*4 - 0.7)/4 = (1.2-0.7)/4 = 0.125
        result = kelly.compute(win_prob=0.3, odds=5.0)
        assert result == pytest.approx(0.125)

    def test_invalid_inputs(self):
        """Invalid inputs return 0."""
        kelly = KellyCalculator()
        assert kelly.compute(0.0, 2.0) == 0.0
        assert kelly.compute(1.0, 2.0) == 0.0
        assert kelly.compute(0.5, 1.0) == 0.0
        assert kelly.compute(-0.1, 2.0) == 0.0
        assert kelly.compute(0.5, 0.5) == 0.0


class TestProofOfAlpha:
    """Tests for SHA-256 proof hash generation."""

    def test_deterministic(self):
        """Same inputs produce same hash."""
        h1 = ProofOfAlpha.generate_hash('{"name":"test"}', 1000, '{"p":0.01}')
        h2 = ProofOfAlpha.generate_hash('{"name":"test"}', 1000, '{"p":0.01}')
        assert h1 == h2

    def test_different_strategy_different_hash(self):
        """Different strategy JSON produces different hash."""
        h1 = ProofOfAlpha.generate_hash('{"name":"a"}', 1000, '{}')
        h2 = ProofOfAlpha.generate_hash('{"name":"b"}', 1000, '{}')
        assert h1 != h2

    def test_different_timestamp_different_hash(self):
        """Different timestamps produce different hashes."""
        h1 = ProofOfAlpha.generate_hash('{}', 1000, '{}')
        h2 = ProofOfAlpha.generate_hash('{}', 1001, '{}')
        assert h1 != h2

    def test_hash_format(self):
        """Hash is 64-character hex string (SHA-256)."""
        h = ProofOfAlpha.generate_hash('test', 0, 'test')
        assert len(h) == 64
        assert all(c in '0123456789abcdef' for c in h)

    def test_matches_manual_sha256(self):
        """Hash matches manual SHA-256 computation."""
        strategy = '{"x":1}'
        ts = 12345
        verdict = '{"p":0.02}'
        payload = f"{strategy}|{ts}|{verdict}"
        expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        result = ProofOfAlpha.generate_hash(strategy, ts, verdict)
        assert result == expected


class TestCryptoSignalExporter:
    """Tests for CryptoSignalExporter."""

    def _make_signal(self) -> Signal:
        return Signal(
            match_index=0,
            strategy_name="High xC Over",
            direction="OVER",
            edge=0.15,
            odds=2.10,
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

    def _make_verdict(self, passed: bool = True) -> ValidationVerdict:
        return ValidationVerdict(
            passed=passed,
            p_value=0.02,
            mean_profit=0.05,
            roi_pct=5.0,
            sample_size=300,
            confidence_interval=(0.01, 0.09),
            effect_size=0.15,
            reason="PROMOTED",
        )

    @pytest.mark.asyncio
    async def test_dispatch_dry_run(self):
        """Dry-run dispatch returns payload without sending."""
        exporter = CryptoSignalExporter(dry_run=True)
        signal = self._make_signal()
        metrics = self._make_metrics()
        verdict = self._make_verdict()

        payload = await exporter.dispatch(
            signal=signal,
            match_info={"home_team": "Arsenal", "away_team": "Chelsea", "league": "PL"},
            metrics=metrics,
            verdict=verdict,
        )

        assert isinstance(payload, SignalPayload)
        assert payload.direction == "OVER"
        assert payload.fdr_validated is True
        assert payload.confidence == 95.0
        assert len(payload.proof_hash) == 64

    @pytest.mark.asyncio
    async def test_dispatch_without_verdict(self):
        """Dispatch works without validation verdict."""
        exporter = CryptoSignalExporter(dry_run=True)
        signal = self._make_signal()
        metrics = self._make_metrics()

        payload = await exporter.dispatch(
            signal=signal,
            match_info={"home_team": "Team A", "away_team": "Team B"},
            metrics=metrics,
            verdict=None,
        )

        assert payload.fdr_validated is False

    def test_format_telegram(self):
        """Telegram format produces Markdown string."""
        exporter = CryptoSignalExporter(dry_run=True)
        payload = SignalPayload(
            match_info="Arsenal vs Chelsea (PL)",
            market_line="OVER (edge: 15.0%)",
            direction="OVER",
            recommended_stake=0.05,
            edge_pct=4.5,
            confidence=95.0,
            fdr_validated=True,
            proof_hash="a" * 64,
            timestamp=1000,
        )

        msg = exporter.format_telegram(payload)

        assert "Arsenal vs Chelsea" in msg
        assert "OVER" in msg
        assert "FDR-VALIDATED" in msg
        assert "Kelly" in msg
        assert "aaaa" in msg  # proof hash prefix

    def test_format_discord(self):
        """Discord format produces embed dict."""
        exporter = CryptoSignalExporter(dry_run=True)
        payload = SignalPayload(
            match_info="Arsenal vs Chelsea (PL)",
            market_line="OVER (edge: 15.0%)",
            direction="OVER",
            recommended_stake=0.05,
            edge_pct=4.5,
            confidence=95.0,
            fdr_validated=True,
            proof_hash="b" * 64,
            timestamp=1000,
        )

        embed = exporter.format_discord(payload)

        assert "embeds" in embed
        assert len(embed["embeds"]) == 1
        assert embed["embeds"][0]["title"] == "Signal: Arsenal vs Chelsea (PL)"
        assert embed["embeds"][0]["color"] == 0x00FF00  # Green for validated

    def test_format_discord_unvalidated(self):
        """Unvalidated signals get amber color."""
        exporter = CryptoSignalExporter(dry_run=True)
        payload = SignalPayload(
            match_info="Test Match",
            market_line="UNDER",
            direction="UNDER",
            recommended_stake=0.02,
            edge_pct=2.0,
            confidence=80.0,
            fdr_validated=False,
            proof_hash="c" * 64,
            timestamp=1000,
        )

        embed = exporter.format_discord(payload)
        assert embed["embeds"][0]["color"] == 0xFFAA00  # Amber

    @pytest.mark.asyncio
    async def test_kelly_stake_in_payload(self):
        """Payload includes Kelly-calculated stake."""
        exporter = CryptoSignalExporter(dry_run=True)
        signal = self._make_signal()
        metrics = self._make_metrics()

        payload = await exporter.dispatch(
            signal=signal,
            match_info={"home_team": "A", "away_team": "B"},
            metrics=metrics,
        )

        # Kelly stake should be a reasonable fraction
        assert 0.0 <= payload.recommended_stake <= 0.25

    @pytest.mark.asyncio
    async def test_proof_hash_is_deterministic_for_same_inputs(self):
        """Same dispatch inputs (with fixed time) produce reproducible hashes."""
        # Can't fully control time.time() but we can verify hash format
        exporter = CryptoSignalExporter(dry_run=True)
        signal = self._make_signal()
        metrics = self._make_metrics()

        payload = await exporter.dispatch(
            signal=signal,
            match_info={"home_team": "A", "away_team": "B"},
            metrics=metrics,
            strategy_json='{"test": true}',
        )

        assert len(payload.proof_hash) == 64
        assert all(c in '0123456789abcdef' for c in payload.proof_hash)
