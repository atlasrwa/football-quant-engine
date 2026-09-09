"""Evaluation hooks for provider comparison.

Enables (later) out-of-sample comparison of forecasting arms:
    FootyStats-only  vs  TheStatsAPI-only  vs  combined/reconciled  vs  market

on IDENTICAL fixture subsets and forecast cutoffs. This module computes and
reports comparative metrics; it deliberately does NOT declare a winner. Any
superiority claim requires an explicit out-of-sample study by a human — the
harness enforces "same fixtures, same cutoff" alignment and surfaces coverage
so comparisons are apples-to-apples, but the report's ``verdict`` is always
"NO_CLAIM".

Metrics reused from src/research/calibration.py (Brier, log loss, ECE/MCE);
this module adds Brier skill score (vs a reference arm) and RPS for ordered
multi-outcome markets, plus coverage/support accounting.
"""

from __future__ import annotations

from src.research.evaluation.provider_comparison import (
    ArmPredictions,
    ArmMetrics,
    ProviderComparisonHarness,
    ProviderComparisonReport,
    ranked_probability_score,
)

__all__ = [
    "ArmPredictions",
    "ArmMetrics",
    "ProviderComparisonHarness",
    "ProviderComparisonReport",
    "ranked_probability_score",
]
