"""Provider comparison experiment (EVALUATION ONLY).

Empirically compares forecasting information from FootyStats vs TheStatsAPI vs
reconciled combinations vs the current champion vs a market benchmark, under
strict point-in-time-safe, out-of-sample walk-forward evaluation.

This package NEVER modifies the champion engine and is NOT wired into any
production path. It reuses the merged PR #3 infrastructure (canonical identity,
observation model, reconciliation, evaluation harness) and the existing champion
model (LeagueCountModel + build_prior_only_features) unchanged, varying ONLY the
provider/reconciliation input policy.

Honesty rules enforced throughout:
- Identity joins use ONLY high-confidence (>=0.9) canonical team mappings; the
  known-wrong fuzzy entries in the legacy crosswalk are excluded. No fuzzy
  matching in the comparison path.
- NULL != ZERO; no imputation to inflate coverage.
- Where the historical data cannot establish point-in-time availability (e.g.
  genuine closing odds, per-observation stat timestamps), the comparison is
  marked UNSUPPORTED rather than fabricated.
"""

from __future__ import annotations

__all__ = []
