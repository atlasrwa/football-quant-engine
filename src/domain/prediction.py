"""PredictionEvent — the canonical atomic prediction record.

This is the foundational domain object for Phase 2 and all future features.
Every prediction the system makes — whether from a backtest or live signal —
becomes a PredictionEvent with full provenance.

A PredictionEvent will eventually power:
- Paper betting (track virtual P&L)
- User prediction history
- Creator reputation scoring
- Leaderboards
- Social feeds (follows, copies)
- Strategy marketplace
- Proof-of-alpha (on-chain attestations)
- CLV tracking

None of those downstream features are built in Phase 2.
This module establishes the domain object correctly.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class PredictionStatus(Enum):
    """Lifecycle status of a prediction event."""

    PENDING = "PENDING"       # Prediction placed, awaiting match
    SETTLED_WIN = "SETTLED_WIN"
    SETTLED_LOSS = "SETTLED_LOSS"
    SETTLED_VOID = "SETTLED_VOID"
    EXPIRED = "EXPIRED"       # Match cancelled or data unavailable


class PredictionSource(Enum):
    """How this prediction was generated."""

    BACKTEST = "BACKTEST"     # Generated during walk-forward backtest
    LIVE_SIGNAL = "LIVE_SIGNAL"  # Generated from live signal pipeline
    PAPER_TRADE = "PAPER_TRADE"  # Generated during quarantine paper trading


@dataclass(frozen=True, slots=True)
class PredictionEvent:
    """Canonical atomic prediction record with full provenance.

    This is the single source of truth for "the system predicted X
    for match Y using strategy Z at time T with edge E."

    Attributes:
        prediction_id: Unique identifier (UUID).
        strategy_id: Strategy that generated this prediction.
        strategy_version: Version of the strategy.
        strategy_content_hash: Content hash of the strategy definition.
        model_version_id: ModelVersion used (links to full provenance).
        match_id: The match being predicted.
        match_date_unix: When the match occurs.
        home_team: Home team name.
        away_team: Away team name.
        league_id: League identifier.
        market_type: Type of market (e.g., "OVER_UNDER").
        market_line: Market line (e.g., 2.5).
        direction: Prediction direction ("OVER"/"UNDER"/"BACK"/"LAY").
        entry_odds: Decimal odds at prediction time (None if unavailable).
        model_edge_pct: Model's estimated edge percentage.
        confidence: Confidence score (0-100).
        recommended_stake: Recommended stake as fraction of bankroll.
        source: How generated (BACKTEST/LIVE_SIGNAL/PAPER_TRADE).
        status: Current lifecycle status.
        proof_hash: SHA-256 proof-of-alpha hash (pre-commitment).
        created_at: ISO 8601 timestamp when prediction was generated.
        settled_at: ISO 8601 timestamp when settled (None if pending).
    """

    prediction_id: str
    strategy_id: str
    strategy_version: int
    strategy_content_hash: str
    model_version_id: str | None
    match_id: int
    match_date_unix: int
    home_team: str
    away_team: str
    league_id: int
    market_type: str
    market_line: float | None
    direction: str
    entry_odds: float | None
    model_edge_pct: float
    confidence: float
    recommended_stake: float
    source: PredictionSource
    status: PredictionStatus
    proof_hash: str
    created_at: str
    settled_at: str | None

    def __post_init__(self) -> None:
        """Validate prediction invariants."""
        if self.entry_odds is not None and self.entry_odds <= 1.0:
            raise ValueError(
                f"entry_odds must be > 1.0 or None, got {self.entry_odds}"
            )
        if self.direction not in ("OVER", "UNDER", "BACK", "LAY"):
            raise ValueError(
                f"direction must be OVER/UNDER/BACK/LAY, got {self.direction}"
            )
        if not (0.0 <= self.confidence <= 100.0):
            raise ValueError(
                f"confidence must be in [0, 100], got {self.confidence}"
            )
        if self.recommended_stake < 0.0:
            raise ValueError(
                f"recommended_stake must be non-negative, got {self.recommended_stake}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary (JSON-safe)."""
        return {
            "prediction_id": self.prediction_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "strategy_content_hash": self.strategy_content_hash,
            "model_version_id": self.model_version_id,
            "match_id": self.match_id,
            "match_date_unix": self.match_date_unix,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "league_id": self.league_id,
            "market_type": self.market_type,
            "market_line": self.market_line,
            "direction": self.direction,
            "entry_odds": self.entry_odds,
            "model_edge_pct": self.model_edge_pct,
            "confidence": self.confidence,
            "recommended_stake": self.recommended_stake,
            "source": self.source.value,
            "status": self.status.value,
            "proof_hash": self.proof_hash,
            "created_at": self.created_at,
            "settled_at": self.settled_at,
        }

    @property
    def is_settled(self) -> bool:
        """Whether this prediction has been settled."""
        return self.status in (
            PredictionStatus.SETTLED_WIN,
            PredictionStatus.SETTLED_LOSS,
            PredictionStatus.SETTLED_VOID,
        )

    @property
    def is_win(self) -> bool | None:
        """Whether this prediction won. None if not settled."""
        if self.status == PredictionStatus.SETTLED_WIN:
            return True
        if self.status == PredictionStatus.SETTLED_LOSS:
            return False
        return None

    @staticmethod
    def compute_proof_hash(
        strategy_content_hash: str,
        match_id: int,
        direction: str,
        entry_odds: float | None,
        timestamp: int,
    ) -> str:
        """Compute deterministic proof-of-alpha hash.

        This hash pre-commits to the prediction before the match occurs.
        It can be published (e.g., on-chain) as proof the prediction
        was made before the outcome was known.

        Args:
            strategy_content_hash: Hash of the strategy definition.
            match_id: Match being predicted.
            direction: Prediction direction.
            entry_odds: Odds at prediction time.
            timestamp: Unix timestamp of prediction.

        Returns:
            SHA-256 hex digest.
        """
        canonical = json.dumps({
            "strategy_content_hash": strategy_content_hash,
            "match_id": match_id,
            "direction": direction,
            "entry_odds": entry_odds,
            "timestamp": timestamp,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()
