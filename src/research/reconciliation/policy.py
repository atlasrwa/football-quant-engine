"""Reconciliation policy enumeration."""

from __future__ import annotations

from enum import Enum


class ReconciliationPolicy(Enum):
    """How to reconcile the same concept observed by multiple providers.

    None of these ever selects the numerically larger value.
    """
    FOOTYSTATS_ONLY = "FOOTYSTATS_ONLY"
    THESTATSAPI_ONLY = "THESTATSAPI_ONLY"
    PREFERRED_PROVIDER_WITH_FALLBACK = "PREFERRED_PROVIDER_WITH_FALLBACK"
    VALIDATED_BLEND = "VALIDATED_BLEND"
