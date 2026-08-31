"""Layer 2: Market EV.

Real-world edge measurement, closing line value, beat-the-bookie metrics,
prediction settlement lifecycle, quarantine bridge, and signal dispatch
to crypto/community channels.
"""

from src.engine.market.clv import CLVCalculator, CLVResult
from src.engine.market.metrics.bookie import BookieMetrics, BookieMetricsCalculator
from src.engine.market.settlement_service import (
    MatchResult,
    PredictionSettlementService,
    SettlementConflictError,
    SettlementResult,
)
from src.engine.market.quarantine_bridge import QuarantineSettlementBridge
from src.engine.market.signals.crypto_exporter import (
    CryptoSignalExporter,
    DispatchResult,
    KellyCalculator,
    ProofOfAlpha,
    RiskUnitCalculator,
    SignalPayload,
)
from src.engine.market.signals.community_broadcaster import (
    BroadcastConfig,
    BroadcastResult,
    CommunityBroadcaster,
)
from src.engine.market.signals.deeplinker import DeepLink, DeepLinkConfig, DeepLinker

__all__ = [
    # CLV
    "CLVCalculator",
    "CLVResult",
    # Bookie Metrics
    "BookieMetrics",
    "BookieMetricsCalculator",
    # Settlement
    "MatchResult",
    "PredictionSettlementService",
    "SettlementConflictError",
    "SettlementResult",
    # Quarantine Bridge
    "QuarantineSettlementBridge",
    # Signal Export
    "CryptoSignalExporter",
    "DispatchResult",
    "KellyCalculator",
    "ProofOfAlpha",
    "RiskUnitCalculator",
    "SignalPayload",
    # Community Broadcast
    "BroadcastConfig",
    "BroadcastResult",
    "CommunityBroadcaster",
    # Deep Links
    "DeepLink",
    "DeepLinkConfig",
    "DeepLinker",
]
