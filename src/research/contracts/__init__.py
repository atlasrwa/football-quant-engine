"""Semantic contracts governing the QFE V2 research stack."""

from src.research.contracts.bookmaker import (
    BOOKMAKER_SETTLEMENT_REGISTRY_V1,
    Bookmaker,
    BookmakerSettlementRegistry,
    SettlementCompatibility,
    SettlementEligibility,
)

from src.research.contracts.provider import (
    THESTATSAPI_CAPABILITIES_V1,
    CapabilityAudit,
    EvidenceFieldContract,
    ProviderCapabilityRegistry,
)
from src.research.contracts.target import (
    TARGET_REGISTRY_V1,
    ProviderMarketStatus,
    SettlementOutcome,
    TargetContract,
    TargetFamily,
    TargetObservation,
    TargetPeriod,
    TargetRegistry,
    TargetSide,
    TargetStatus,
    binary_event_outcome,
    is_binary_scoring_line,
    settle_count_market,
)

__all__ = [
    "BOOKMAKER_SETTLEMENT_REGISTRY_V1",
    "Bookmaker",
    "BookmakerSettlementRegistry",
    "SettlementCompatibility",
    "SettlementEligibility",
    "THESTATSAPI_CAPABILITIES_V1",
    "CapabilityAudit",
    "EvidenceFieldContract",
    "ProviderCapabilityRegistry",
    "TARGET_REGISTRY_V1",
    "ProviderMarketStatus",
    "SettlementOutcome",
    "TargetContract",
    "TargetFamily",
    "TargetObservation",
    "TargetPeriod",
    "TargetRegistry",
    "TargetSide",
    "TargetStatus",
    "binary_event_outcome",
    "is_binary_scoring_line",
    "settle_count_market",
]
