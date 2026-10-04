"""QFE V2 Layer 5 market-relative research contracts."""

from src.research.layer5.diagnostics import (
    SurfaceDiagnostics,
    compute_surface_diagnostics,
)
from src.research.layer5.disagreement import (
    DisagreementDecision,
    ModelMarketPoint,
    evaluate_single_line,
    evaluate_surface,
)
from src.research.layer5.market_manifest import (
    CapturePrefix,
    build_matched_market_manifest,
    snapshot_capture_prefix,
    write_matched_market_manifest,
)
from src.research.layer5.market_relative import (
    IncrementalInformationResult,
    MarketAnchoredLogisticStack,
    MarketOnlyBenchmarkResult,
    MarketRelativeRow,
    fit_market_anchored_stack,
    fit_market_only_benchmark,
    run_incremental_information_experiment,
)
from src.research.layer5.market_support import (
    audit_market_relative_support,
    render_market_relative_support_markdown,
    write_market_relative_support_audit,
)
from src.research.layer5.market_surface import (
    MarketPoint,
    MarketSurface,
    TwoWayQuote,
    build_market_point,
    build_market_surface,
    isotonic_nonincreasing,
    select_benchmark_bundle,
    select_latest_complete_bundle,
)
from src.research.layer5.protocol import (
    LAYER5_PROTOCOL_HASH,
    LAYER5_PROTOCOL_VERSION,
    LAYER5_PROTOCOL_V1_1_HASH,
    LAYER5_PROTOCOL_V1_1_VERSION,
    active_protocol_hash,
    protocol_active,
    protocol_hash,
    protocol_v1,
    protocol_v1_1,
)

__all__ = [
    "CapturePrefix",
    "DisagreementDecision",
    "IncrementalInformationResult",
    "LAYER5_PROTOCOL_HASH",
    "LAYER5_PROTOCOL_VERSION",
    "LAYER5_PROTOCOL_V1_1_HASH",
    "LAYER5_PROTOCOL_V1_1_VERSION",
    "MarketAnchoredLogisticStack",
    "MarketOnlyBenchmarkResult",
    "MarketPoint",
    "MarketRelativeRow",
    "MarketSurface",
    "ModelMarketPoint",
    "SurfaceDiagnostics",
    "TwoWayQuote",
    "active_protocol_hash",
    "audit_market_relative_support",
    "build_matched_market_manifest",
    "build_market_point",
    "build_market_surface",
    "compute_surface_diagnostics",
    "evaluate_single_line",
    "evaluate_surface",
    "fit_market_anchored_stack",
    "fit_market_only_benchmark",
    "isotonic_nonincreasing",
    "protocol_active",
    "protocol_hash",
    "protocol_v1",
    "protocol_v1_1",
    "render_market_relative_support_markdown",
    "run_incremental_information_experiment",
    "select_benchmark_bundle",
    "select_latest_complete_bundle",
    "snapshot_capture_prefix",
    "write_market_relative_support_audit",
    "write_matched_market_manifest",
]
