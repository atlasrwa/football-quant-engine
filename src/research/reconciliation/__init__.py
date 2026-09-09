"""Provider reconciliation — explicit policies for combining observations.

When FootyStats and TheStatsAPI both report the same concept for the same
canonical entity, we must choose a value under an EXPLICIT policy. We NEVER
pick the numerically larger observation and never silently average.

Policies:
- FOOTYSTATS_ONLY               : use FootyStats; ignore TheStatsAPI.
- THESTATSAPI_ONLY              : use TheStatsAPI; ignore FootyStats.
- PREFERRED_PROVIDER_WITH_FALLBACK : use the preferred provider's value; fall
                                  back to the other only when the preferred
                                  value is MISSING (not merely None — a
                                  provider that observed absence is respected).
- VALIDATED_BLEND               : average ONLY when both providers agree within
                                  a validated tolerance; otherwise it does NOT
                                  blend and returns no selected value, flagging
                                  disagreement. This is deliberately
                                  conservative: an unvalidated blend is never
                                  produced, and no learned blend is introduced
                                  into the champion model here.

Every reconciled field retains: selected value, selected source, per-provider
inputs, support/missingness, provenance timestamps, and a measurable
disagreement metric.
"""

from __future__ import annotations

from src.research.reconciliation.policy import ReconciliationPolicy
from src.research.reconciliation.reconciler import (
    ReconciledField,
    Reconciler,
    SelectionOutcome,
)

__all__ = [
    "ReconciliationPolicy",
    "ReconciledField",
    "Reconciler",
    "SelectionOutcome",
]
