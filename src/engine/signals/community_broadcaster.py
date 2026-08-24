"""Community signal distribution service.

Automated background worker that polls for promoted strategies,
evaluates conditions against live fixtures, and dispatches formatted
alerts to Telegram and Discord communities.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, List

import httpx

from src.engine.evaluator import Signal
from src.engine.metrics.bookie import BookieMetrics
from src.engine.signals.crypto_exporter import (
    CryptoSignalExporter,
    ProofOfAlpha,
    SignalPayload,
)
from src.engine.signals.deeplinker import DeepLink, DeepLinker

logger = logging.getLogger(__name__)


@dataclass
class BroadcastResult:
    """Result of a broadcast operation with optional PredictionEvents.

    Backward-compatible: supports len(), indexing, iteration, and equality
    comparison with lists, so existing code continues to work unchanged.
    """

    payloads: List[SignalPayload]
    prediction_events: list  # List[PredictionEvent] when identity provided

    def __len__(self) -> int:
        """Support len() for backward compatibility."""
        return len(self.payloads)

    def __getitem__(self, index):
        """Support indexing for backward compatibility."""
        return self.payloads[index]

    def __iter__(self):
        """Support iteration for backward compatibility."""
        return iter(self.payloads)

    def __eq__(self, other) -> bool:
        """Support equality comparison with lists for backward compatibility."""
        if isinstance(other, list):
            return self.payloads == other
        if isinstance(other, BroadcastResult):
            return self.payloads == other.payloads
        return NotImplemented


@dataclass
class BroadcastConfig:
    """Configuration for community signal broadcasting."""

    poll_interval_seconds: int = 300  # 5 minutes
    quiet_hours_start: int = 1  # 1am UTC
    quiet_hours_end: int = 6  # 6am UTC
    telegram_url: str | None = None
    discord_url: str | None = None
    dry_run: bool = False


class CommunityBroadcaster:
    """Broadcasts promoted strategy signals to community channels.

    Consumes signals and match data, formats rich messages with
    deep-links and proof hashes, and dispatches to configured webhooks.
    """

    def __init__(
        self,
        config: BroadcastConfig | None = None,
        deep_linker: DeepLinker | None = None,
    ) -> None:
        self.config = config or BroadcastConfig()
        self.deep_linker = deep_linker or DeepLinker()
        self._exporter = CryptoSignalExporter(
            telegram_url=self.config.telegram_url,
            discord_url=self.config.discord_url,
            dry_run=self.config.dry_run,
        )

    async def run_once(
        self,
        signals: List[Signal],
        match_data: List[dict],
        metrics: BookieMetrics | None = None,
        strategy_json: str = "{}",
        validation_passed: bool = False,
        strategy_identity: Any = None,
        source: str = "LIVE_SIGNAL",
    ) -> "BroadcastResult":
        """Process and broadcast signals for current fixtures.

        Args:
            signals: Generated signals from strategy evaluation.
            match_data: List of match info dicts (parallel to signals or lookup).
            metrics: Bookie metrics for the strategy.
            strategy_json: Strategy JSON for proof hash.
            validation_passed: Authoritative validation state from the validation
                system. The broadcaster does NOT decide validation status.
            strategy_identity: Optional identity info for PredictionEvent emission.
            source: Prediction source ("LIVE_SIGNAL" or "PAPER_TRADE").

        Returns:
            BroadcastResult containing dispatched payloads and prediction events.
        """
        if self.is_quiet_hours(self._current_hour_utc()):
            logger.info("Quiet hours active, skipping broadcast")
            return BroadcastResult(payloads=[], prediction_events=[])

        payloads: List[SignalPayload] = []
        prediction_events: list = []

        for i, signal in enumerate(signals):
            match_info = match_data[i] if i < len(match_data) else {}

            # Generate deep-links
            deep_links = self.deep_linker.generate_links(signal, match_info)

            # Generate proof hash
            ts = int(time.time())
            proof_hash = ProofOfAlpha.generate_hash(strategy_json, ts, "{}")

            # Build payload — validation state comes from authoritative source
            # R05: NEVER hardcode fdr_validated=True
            payload = SignalPayload(
                match_info=self._format_match(match_info),
                market_line=f"{signal.direction} (edge: {signal.edge:.1%})",
                direction=signal.direction,
                recommended_stake=0.05,  # Default conservative
                edge_pct=metrics.vig_adjusted_edge_pct if metrics else 0.0,
                confidence=metrics.confidence_index if metrics else 0.0,
                fdr_validated=validation_passed,
                proof_hash=proof_hash,
                timestamp=ts,
            )

            # Dispatch
            if not self.config.dry_run:
                if self.config.telegram_url:
                    msg = self.format_broadcast_telegram(payload, deep_links)
                    await self._send_webhook(self.config.telegram_url, {"text": msg, "parse_mode": "Markdown"})
                if self.config.discord_url:
                    embed = self.format_broadcast_discord(payload, deep_links)
                    await self._send_webhook(self.config.discord_url, embed)

            payloads.append(payload)

            # Emit PredictionEvent if strategy identity is available
            if strategy_identity is not None:
                prediction_event = self._create_prediction_event(
                    signal, match_info, strategy_identity, source,
                    confidence=metrics.confidence_index if metrics else 50.0,
                )
                if prediction_event is not None:
                    prediction_events.append(prediction_event)

        logger.info("Broadcast complete: %d signals dispatched", len(payloads))
        return BroadcastResult(payloads=payloads, prediction_events=prediction_events)

    def format_broadcast_telegram(
        self, payload: SignalPayload, deep_links: List[DeepLink]
    ) -> str:
        """Format Telegram message with deep-link action buttons.

        Args:
            payload: Signal payload.
            deep_links: Generated platform deep-links.

        Returns:
            Formatted Markdown message.
        """
        badge = "FDR-VALIDATED" if payload.fdr_validated else "PENDING"
        lines = [
            f"*{payload.match_info}*",
            "",
            f"Direction: `{payload.direction}`",
            f"Edge: {payload.edge_pct:.2f}% (vig-adjusted)",
            f"Confidence: {payload.confidence:.0f}/100",
            f"Kelly Stake: {payload.recommended_stake:.2%} bankroll",
            f"Status: [{badge}]",
            "",
            f"Proof: `{payload.proof_hash[:16]}...`",
            "",
            "--- Action Links ---",
        ]

        for link in deep_links:
            lines.append(f"[{link.label}]({link.url})")

        return "\n".join(lines)

    def format_broadcast_discord(
        self, payload: SignalPayload, deep_links: List[DeepLink]
    ) -> dict:
        """Format Discord rich embed with action links.

        Args:
            payload: Signal payload.
            deep_links: Generated platform deep-links.

        Returns:
            Discord webhook payload dict.
        """
        color = 0x00FF00 if payload.fdr_validated else 0xFFAA00
        badge = "FDR-VALIDATED" if payload.fdr_validated else "PENDING"

        link_text = "\n".join(f"[{l.label}]({l.url})" for l in deep_links)

        return {
            "embeds": [{
                "title": f"Signal: {payload.match_info}",
                "color": color,
                "fields": [
                    {"name": "Direction", "value": payload.direction, "inline": True},
                    {"name": "Vig-Adjusted Edge", "value": f"{payload.edge_pct:.2f}%", "inline": True},
                    {"name": "Confidence", "value": f"{payload.confidence:.0f}/100", "inline": True},
                    {"name": "Kelly Stake", "value": f"{payload.recommended_stake:.2%}", "inline": True},
                    {"name": "Status", "value": badge, "inline": True},
                    {"name": "Proof Hash", "value": f"`{payload.proof_hash[:16]}...`", "inline": True},
                    {"name": "Action Links", "value": link_text or "N/A", "inline": False},
                ],
                "footer": {"text": "Football Quant Engine | Proof-of-Alpha"},
            }]
        }

    def is_quiet_hours(self, hour_utc: int) -> bool:
        """Check if current UTC hour is within quiet hours.

        Args:
            hour_utc: Current hour in UTC (0-23).

        Returns:
            True if in quiet hours.
        """
        start = self.config.quiet_hours_start
        end = self.config.quiet_hours_end
        if start <= end:
            return start <= hour_utc < end
        else:
            # Wraps midnight (e.g., 22-6)
            return hour_utc >= start or hour_utc < end

    async def _send_webhook(self, url: str, data: dict) -> bool:
        """Send webhook payload (non-fatal on failure)."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=data)
                if response.status_code < 300:
                    return True
                logger.warning("Webhook failed (%d): %s", response.status_code, url[:50])
                return False
        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.warning("Webhook error: %s", e)
            return False

    def _format_match(self, info: dict) -> str:
        """Format match info into display string."""
        home = info.get("home_team", "Home")
        away = info.get("away_team", "Away")
        league = info.get("league", "")
        if league:
            return f"{home} vs {away} ({league})"
        return f"{home} vs {away}"

    def _current_hour_utc(self) -> int:
        """Get current UTC hour."""
        import datetime
        return datetime.datetime.now(datetime.timezone.utc).hour

    def _create_prediction_event(
        self,
        signal: Signal,
        match_info: dict,
        strategy_identity: Any,
        source: str,
        confidence: float = 50.0,
    ) -> Any:
        """Create a PredictionEvent from a broadcast signal.

        Args:
            signal: The signal being broadcast.
            match_info: Match data dict.
            strategy_identity: StrategyIdentityInfo with id, version, content_hash.
            source: "LIVE_SIGNAL" or "PAPER_TRADE".
            confidence: Confidence score (0-100).

        Returns:
            PredictionEvent in PENDING status, or None on failure.
        """
        from src.domain.factories import PredictionEventFactory
        from src.domain.prediction import PredictionSource

        source_map = {
            "LIVE_SIGNAL": PredictionSource.LIVE_SIGNAL,
            "PAPER_TRADE": PredictionSource.PAPER_TRADE,
        }
        prediction_source = source_map.get(source, PredictionSource.LIVE_SIGNAL)

        return PredictionEventFactory.from_signal(
            signal=signal,
            strategy_id=strategy_identity.strategy_id,
            strategy_version=strategy_identity.strategy_version,
            strategy_content_hash=strategy_identity.content_hash,
            match_id=int(match_info.get("match_id", 0)),
            match_date_unix=int(match_info.get("date_unix", 0)),
            home_team=str(match_info.get("home_team", "Unknown")),
            away_team=str(match_info.get("away_team", "Unknown")),
            league_id=int(match_info.get("league_id", 0)),
            market_type=str(match_info.get("market_type", "OVER_UNDER")),
            market_line=float(match_info.get("market_line", 2.5)),
            model_version_id=getattr(strategy_identity, "model_version_id", None),
            confidence=confidence,
            recommended_stake=0.05,
            source=prediction_source,
        )
