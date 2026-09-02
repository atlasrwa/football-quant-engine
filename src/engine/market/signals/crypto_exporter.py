"""Crypto-native signal exporter for Telegram/Discord communities.

.. deprecated::
    **DEPRECATED — user-facing EV/edge/stake framing.** The market-beating
    objective is closed (edge ceiling measured directly). Signal payloads that
    surface edge percentages, recommended stakes, and stake tiers are exactly the
    "value bet" framing the project no longer makes. This exporter is retained for
    internal research only — it is **not a product claim**, must not be presented
    as betting advice, and no stake sizing may be added. The supported deliverable
    is the calibrated prediction engine in ``src.research.prediction_engine``,
    whose public output is calibrated probabilities and directional calls with no
    edge/stake framing. See ``src.research._ev_deprecation``.

Formats live signals into webhook payloads with risk-unit stake tiers
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

from src.engine.analysis.evaluator import Signal
from src.engine.market.metrics.bookie import BookieMetrics
from src.engine.analysis.validator import ValidationVerdict

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class SignalPayload:
    """Formatted signal payload for webhook dispatch."""

    match_info: str
    market_line: str
    direction: str
    # Heuristic risk-unit stake fraction (0-1 of bankroll). NOT Kelly/probability
    # -derived — see R06 and RiskUnitCalculator. Never present this as calibrated
    # investment sizing to subscribers.
    recommended_stake: float
    edge_pct: float
    confidence: float
    fdr_validated: bool
    proof_hash: str
    timestamp: int
    stake_tier: str = "0.25U"  # Display label, e.g. "0.25U" / "0.50U" / "1.00U"


@dataclass(frozen=True)
class DispatchResult:
    """Result of a signal dispatch, containing payload and optional PredictionEvent.

    Backward-compatible: attribute access delegates to payload so existing code
    that uses `result.direction`, `result.fdr_validated`, etc. continues to work.
    isinstance(result, SignalPayload) will NOT pass — use result.payload for that.
    """

    payload: SignalPayload
    prediction_event: "Any | None" = None  # PredictionEvent when identity is provided

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to payload for backward compatibility."""
        payload = object.__getattribute__(self, "payload")
        if hasattr(payload, name):
            return getattr(payload, name)
        raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")


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


class RiskUnitCalculator:
    """Heuristic risk-unit stake sizing based on edge magnitude.

    R06 fix: subscriber-facing stake sizing must never imply a calibrated
    probability estimate we cannot statistically back. This buckets the
    model's reported edge into fixed unit tiers (0.25U / 0.50U / 1.00U)
    instead of deriving a stake from an uncalibrated win-probability guess.
    `KellyCalculator` remains available for internal/research use, but its
    output must not be surfaced as subscriber-facing stake guidance.
    """

    BASE_UNIT: float = 0.01  # 1.00U == 1% of bankroll

    # Edge-magnitude breakpoints -> risk units. Tune these from realized
    # calibration data, not from a probability model with no track record.
    TIERS: tuple[tuple[float, float], ...] = (
        (0.05, 1.00),
        (0.02, 0.50),
        (0.00, 0.25),
    )

    def compute(self, condition_strength: float) -> tuple[float, str]:
        """Map |condition_strength| to a stake fraction and a human-readable tier label.

        Args:
            condition_strength: Hypothesis-layer condition strength (can be negative;
                magnitude is used).

        Returns:
            (stake_fraction, tier_label), e.g. (0.005, "0.50U").
        """
        magnitude = abs(condition_strength)
        units = self.TIERS[-1][1]
        for threshold, tier_units in self.TIERS:
            if magnitude >= threshold:
                units = tier_units
                break
        return units * self.BASE_UNIT, f"{units:.2f}U"


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
        self._kelly = KellyCalculator()  # retained for internal/research use only
        self._risk_tier = RiskUnitCalculator()

    async def dispatch(
        self,
        signal: Signal,
        match_info: dict,
        metrics: BookieMetrics,
        verdict: ValidationVerdict | None = None,
        strategy_json: str = "{}",
        strategy_identity: "StrategyIdentityInfo | None" = None,
        source: str = "LIVE_SIGNAL",
    ) -> "SignalPayload | DispatchResult":
        """Format and dispatch a signal to configured webhooks.

        Args:
            signal: The generated signal.
            match_info: Dict with match details (home_team, away_team, etc.).
            metrics: Beat the Bookie metrics for this strategy.
            verdict: Optional validation verdict for FDR badge.
            strategy_json: Strategy JSON for proof hash.
            strategy_identity: Optional identity info for PredictionEvent emission.
            source: Prediction source ("LIVE_SIGNAL" or "PAPER_TRADE").

        Returns:
            SignalPayload when strategy_identity is None (backward compatible).
            DispatchResult when strategy_identity is provided (includes PredictionEvent).
        """
        ts = int(time.time())

        # R06: subscriber-facing stake is a heuristic risk-unit tier derived
        # from condition strength magnitude — NOT a Kelly fraction derived from an
        # uncalibrated win-probability guess. See RiskUnitCalculator.
        stake_fraction, stake_tier = self._risk_tier.compute(signal.condition_strength)

        # Proof of Alpha hash
        verdict_json = json.dumps({"passed": verdict.passed, "p_value": verdict.p_value}) if verdict else "{}"
        proof_hash = ProofOfAlpha.generate_hash(strategy_json, ts, verdict_json)

        # FDR validated badge
        fdr_validated = verdict.passed if verdict else False

        payload = SignalPayload(
            match_info=self._format_match_info(match_info),
            market_line=f"{signal.direction} (strength: {signal.condition_strength:.1%})",
            direction=signal.direction,
            recommended_stake=round(stake_fraction, 4),
            edge_pct=metrics.vig_adjusted_edge_pct,
            confidence=metrics.confidence_index,
            fdr_validated=fdr_validated,
            proof_hash=proof_hash,
            timestamp=ts,
            stake_tier=stake_tier,
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

        # Emit PredictionEvent if strategy identity is available
        prediction_event = None
        if strategy_identity is not None:
            prediction_event = self._create_prediction_event(
                signal, match_info, strategy_identity, source,
                confidence=metrics.confidence_index,
                recommended_stake=stake_fraction,
            )
            return DispatchResult(payload=payload, prediction_event=prediction_event)

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
            f"Stake: {payload.stake_tier} (heuristic risk tier, not financial advice)",
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
                    {"name": "Stake Tier (heuristic)", "value": payload.stake_tier, "inline": True},
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
        """Rough internal win-probability estimate from odds and edge.

        R06: this is an uncalibrated linear heuristic (no Brier/log-loss
        validation) and must NOT be used to size subscriber-facing stakes —
        `dispatch()` uses `RiskUnitCalculator` for that. Retained only for
        internal research callers that explicitly want a quick estimate.
        """
        if odds <= 1.0:
            return 0.0
        implied = 1.0 / odds
        # Edge represents our estimated advantage over the market
        estimated = implied + edge * 0.1  # Conservative scaling
        return max(0.01, min(0.99, estimated))

    def _create_prediction_event(
        self,
        signal: Signal,
        match_info: dict,
        strategy_identity: Any,
        source: str,
        confidence: float = 50.0,
        recommended_stake: float = 0.01,
    ) -> Any:
        """Create a PredictionEvent from a live signal dispatch.

        Args:
            signal: The signal being dispatched.
            match_info: Match data dict.
            strategy_identity: StrategyIdentityInfo with id, version, content_hash.
            source: "LIVE_SIGNAL" or "PAPER_TRADE".
            confidence: Confidence score (0-100).
            recommended_stake: Kelly fraction.

        Returns:
            PredictionEvent in PENDING status.
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
            recommended_stake=recommended_stake,
            source=prediction_source,
        )
