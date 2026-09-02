"""Layer 2: Market EV (DEPRECATED — market-comparison, internal research only).

.. deprecated::
    The market-beating objective is closed: the edge ceiling was measured
    directly (median edge 0-1pp vs a 2-4pp requirement). The EV / edge / CLV /
    beat-the-bookie constructs re-exported here are retained for Pilot C and
    internal research **only** and are **not a product claim**. They must not be
    surfaced in user-facing output, and no stake sizing may be added. The
    supported deliverable is the calibrated prediction engine in
    ``src.research.prediction_engine``. See ``src.research._ev_deprecation``.

Historically: real-world edge measurement, closing line value, beat-the-bookie
metrics, prediction settlement lifecycle, quarantine bridge, and signal dispatch.
Settlement/quarantine/attestation-adjacent pieces here remain in use; the
EV/edge/CLV pieces are deprecated market-comparison research tooling.
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
