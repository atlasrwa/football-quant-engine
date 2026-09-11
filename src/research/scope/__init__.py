"""Canonical engine scope: which competitions the engine may process, and why.

This package replaces Pilot C as the answer to "which leagues does the engine
work on". Pilot C was a *pre-registered experiment* with a fixed four-league
sample; it was never intended to be the engine's reach, but its competition list
leaked into declared broadcast scope and therefore into everything downstream of
a forecast commitment.

The rule here is provider-derived, not curated:

    A competition enters the engine universe when BOTH providers support it and
    its identity can be resolved deterministically to exactly one competition on
    each side. Anything else fails closed with a named reason.

See :mod:`src.research.scope.dual_provider` for the rule itself and
:mod:`src.research.scope.market_scope` for the ``competition x market`` unit of
eligibility that sits on top of it.

WHAT THIS PACKAGE IS NOT
========================
It is not a publication policy. Being in the engine universe means research
processing is *permitted to the extent the data supports it*; it says nothing
about validated-signal eligibility, which remains governed solely by
:mod:`src.research._data_accumulation_mode`. Full research coverage is not
validated signal coverage, and no function here is allowed to imply otherwise.
"""

from __future__ import annotations

from src.research.scope.dual_provider import (
    DEPRECATED_PILOT_C_MODEL_STATUS,
    DualProviderLeague,
    DualProviderUniverse,
    LEGACY_NON_BEHAVIORAL_MODEL_STATUSES,
    ScopeDecision,
    ScopeExclusionReason,
    build_dual_provider_universe,
    evaluate_league,
)
from src.research.scope.market_scope import (
    CompetitionMarketScope,
    MODEL_MARKET_TO_ODDS_MARKET,
    ODDS_MARKET_TO_MODEL_MARKET,
    MarketExclusionReason,
    ResearchScope,
    build_research_scope,
)

__all__ = [
    "DEPRECATED_PILOT_C_MODEL_STATUS",
    "DualProviderLeague",
    "DualProviderUniverse",
    "LEGACY_NON_BEHAVIORAL_MODEL_STATUSES",
    "ScopeDecision",
    "ScopeExclusionReason",
    "build_dual_provider_universe",
    "evaluate_league",
    "CompetitionMarketScope",
    "MODEL_MARKET_TO_ODDS_MARKET",
    "ODDS_MARKET_TO_MODEL_MARKET",
    "MarketExclusionReason",
    "ResearchScope",
    "build_research_scope",
]
