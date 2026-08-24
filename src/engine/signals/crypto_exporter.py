"""Crypto-native signal exporter for Telegram/Discord communities.

Formats live signals into webhook payloads with Kelly fraction stake sizing
and SHA-256 Proof-of-Alpha hashes for on-chain verification.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from src.engine.evaluator import Signal
from src.engine.metrics.bookie import BookieMetrics
from src.engine.validator import ValidationVerdict

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SignalPayload:
    """Formatted signal payload for webhook dispatch."""

    match_info: str
    market_line: str
    direction: str
    recommended_stake: float  # Kelly fraction (capped)
    edge_pct: float
    confidence: float
    fdr_validated: bool
    proof_hash: str
    timestamp: int


class KellyCalculator:
    """Kelly criterion stake sizing with safety cap.

    Kelly formula: f* = (p*b - q) / b
    where p = win probability, b = decimal odds - 1, q = 1 - p.
    Capped at MAX_FRACTION to prevent over-betting on estimation errors.
    """

    MAX_FRACTION: float = 0.25  # Quarter-Kelly cap

    def compute(self, win_prob: float, odds: float) -> float:
        """Compute Kelly fraction.

        Args:
            win_prob: Estimated probability of winning (0-1).
            odds: Decimal odds (e.g., 2.0).

        Returns:
            Recommended fraction of bankroll to stake (0 to MAX_FRACTION).
        """
        if win_prob <= 0 or win_prob >= 1 or odds <= 1.0:
            return 0.0

        b = odds - 1.0
        q = 1.0 - win_prob
        kelly = (win_prob * b - q) / b

        if kelly <= 0:
            return 0.0

        return min(kelly, self.MAX_FRACTION)


class ProofOfAlpha:
    """SHA-256 hash generator for on-chain strategy verification.

    Produces a deterministic hash of (strategy_json + timestamp + verdict_json)
    that can be committed on-chain before outcomes are known.
    """

    @staticmethod
    def generate_hash(
        strategy_json: str, timestamp: int, verdict_json: str
    ) -> str:
        """Generate SHA-256 proof hash.

        Args:
            strategy_json: JSON-serialized strategy definition.
            timestamp: Unix timestamp of signal generation.
            verdict_json: JSON-serialized validation verdict.

        Returns:
            Hex-encoded SHA-256 hash string.
        """
        payload = f"{strategy_json}|{timestamp}|{verdict_json}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class CryptoSignalExporter:
    """Dispatches formatted signals to Telegram/Discord webhooks.

    Supports dry-run mode for testing without actual HTTP dispatch.
    """

    def __init__(
        self,
        telegram_url: str | None = None,
        discord_url: str | None = None,
        dry_run: bool = False,
    ) -> None:
        """Initialize exporter.

        Args:
            telegram_url: Telegram bot webhook URL.
            discord_url: Discord webhook URL.
            dry_run: If True, format payloads without sending.
        """
        self.telegram_url = telegram_url
        self.discord_url = discord_url
        self.dry_run = dry_run
        self._kelly = KellyCalculator()

    async def dispatch(
        self,
        signal: Signal,
        match_info: dict,
        metrics: BookieMetrics,
        verdict: ValidationVerdict | None = None,
        strategy_json: str = "{}",
    ) -> SignalPayload:
        """Format and dispatch a signal to configured webhooks.

        Args:
            signal: The generated signal.
            match_info: Dict with match details (home_team, away_team, etc.).
            metrics: Beat the Bookie metrics for this strategy.
            verdict: Optional validation verdict for FDR badge.
            strategy_json: Strategy JSON for proof hash.

        Returns:
            The formatted SignalPayload.
        """
        ts = int(time.time())

        # Kelly stake calculation
        # Estimate win probability from edge
        win_prob = self._estimate_win_prob(signal.odds, signal.edge)
        kelly_stake = self._kelly.compute(win_prob, signal.odds)

        # Proof of Alpha hash
        verdict_json = json.dumps({"passed": verdict.passed, "p_value": verdict.p_value}) if verdict else "{}"
        proof_hash = ProofOfAlpha.generate_hash(strategy_json, ts, verdict_json)

        # FDR validated badge
        fdr_validated = verdict.passed if verdict else False

        payload = SignalPayload(
            match_info=self._format_match_info(match_info),
            market_line=f"{signal.direction} (edge: {signal.edge:.1%})",
            direction=signal.direction,
            recommended_stake=round(kelly_stake, 4),
            edge_pct=metrics.vig_adjusted_edge_pct,
            confidence=metrics.confidence_index,
            fdr_validated=fdr_validated,
            proof_hash=proof_hash,
            timestamp=ts,
        )

        # Dispatch to webhooks
        if not self.dry_run:
            if self.telegram_url:
                msg = self.format_telegram(payload)
                await self._send_webhook(
                    self.telegram_url, {"text": msg, "parse_mode": "Markdown"}
                )
            if self.discord_url:
                embed = self.format_discord(payload)
                await self._send_webhook(self.discord_url, embed)

        return payload

    def format_telegram(self, payload: SignalPayload) -> str:
        """Format payload as Telegram Markdown message.

        Args:
            payload: Signal payload.

        Returns:
            Formatted Markdown string.
        """
        badge = "FDR-VALIDATED" if payload.fdr_validated else "UNVALIDATED"
        lines = [
            f"*{payload.match_info}*",
            f"Direction: `{payload.direction}`",
            f"Market: {payload.market_line}",
            f"Stake: {payload.recommended_stake:.2%} bankroll (Kelly)",
            f"Edge: {payload.edge_pct:.2f}% (vig-adjusted)",
            f"Confidence: {payload.confidence:.0f}/100",
            f"Status: [{badge}]",
            f"Proof: `{payload.proof_hash[:16]}...`",
        ]
        return "\n".join(lines)

    def format_discord(self, payload: SignalPayload) -> dict:
        """Format payload as Discord webhook embed.

        Args:
            payload: Signal payload.

        Returns:
            Discord embed dict.
        """
        color = 0x00FF00 if payload.fdr_validated else 0xFFAA00
        badge = "FDR-VALIDATED" if payload.fdr_validated else "UNVALIDATED"

        return {
            "embeds": [{
                "title": f"Signal: {payload.match_info}",
                "color": color,
                "fields": [
                    {"name": "Direction", "value": payload.direction, "inline": True},
                    {"name": "Market", "value": payload.market_line, "inline": True},
                    {"name": "Kelly Stake", "value": f"{payload.recommended_stake:.2%}", "inline": True},
                    {"name": "Vig-Adjusted Edge", "value": f"{payload.edge_pct:.2f}%", "inline": True},
                    {"name": "Confidence", "value": f"{payload.confidence:.0f}/100", "inline": True},
                    {"name": "Status", "value": badge, "inline": True},
                ],
                "footer": {"text": f"Proof: {payload.proof_hash[:16]}..."},
                "timestamp": payload.timestamp,
            }]
        }

    async def _send_webhook(self, url: str, data: dict) -> bool:
        """Send webhook payload via HTTP POST.

        Non-fatal: failures are logged but do not raise.

        Args:
            url: Webhook endpoint URL.
            data: JSON payload.

        Returns:
            True if successful, False otherwise.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=data)
                if response.status_code < 300:
                    logger.info("Webhook dispatched to %s", url[:50])
                    return True
                else:
                    logger.warning(
                        "Webhook failed (%d): %s", response.status_code, url[:50]
                    )
                    return False
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.warning("Webhook dispatch error: %s", e)
            return False

    def _format_match_info(self, info: dict) -> str:
        """Format match info dict into readable string."""
        home = info.get("home_team", "Home")
        away = info.get("away_team", "Away")
        league = info.get("league", "")
        if league:
            return f"{home} vs {away} ({league})"
        return f"{home} vs {away}"

    def _estimate_win_prob(self, odds: float, edge: float) -> float:
        """Estimate win probability from odds and edge.

        Uses implied probability + edge as an estimate.
        """
        if odds <= 1.0:
            return 0.0
        implied = 1.0 / odds
        # Edge represents our estimated advantage over the market
        estimated = implied + edge * 0.1  # Conservative scaling
        return max(0.01, min(0.99, estimated))
