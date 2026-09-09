"""Descriptive (pre-gate) reporting + preregistered readiness assessment.

Before the preregistered sample gate is met, ONLY descriptive statistics are
allowed (mission section 21): N, coverage, movement distribution, sign split,
bookmaker continuity, market coverage. This module never reports "alpha",
"edge", "profitable", or a "promotion candidate"; those words do not appear.

The readiness state is one of:
    PRICE_DISCOVERY_NOT_ENOUGH_DATA  (below the descriptive floor)
    PRICE_DISCOVERY_EXPLORATORY      (enough for descriptives, gate NOT met)
    PRICE_DISCOVERY_EVALUABLE        (preregistered gate met)

EVALUABLE is only ever returned when the preregistered ReadinessGate passes.
"""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from typing import Optional

from src.research.experiments.price_discovery.dataset import (
    PROSPECTIVE_GATE,
    PriceDiscoveryDataset,
    Transition,
)


def _median(xs):
    return statistics.median(xs) if xs else None


def _movement_stats(transitions: list[Transition]) -> dict:
    deltas = [t.delta_market_logit for t in transitions]
    if not deltas:
        return {
            "n": 0, "mean": None, "median": None, "median_abs": None,
            "sign_positive": 0, "sign_negative": 0, "sign_zero": 0,
        }
    abs_deltas = [abs(d) for d in deltas]
    return {
        "n": len(deltas),
        "mean": statistics.fmean(deltas),
        "median": _median(deltas),
        "median_abs": _median(abs_deltas),
        "stdev": statistics.pstdev(deltas) if len(deltas) > 1 else 0.0,
        "sign_positive": sum(1 for d in deltas if d > 0),
        "sign_negative": sum(1 for d in deltas if d < 0),
        "sign_zero": sum(1 for d in deltas if d == 0),
    }


def _group_counts(transitions: list[Transition], attr: str) -> dict:
    out: dict = {}
    for t in transitions:
        k = getattr(t, attr)
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], str(kv[0]))))


@dataclass(frozen=True)
class ReadinessAssessment:
    """The full readiness assessment (descriptive + gate)."""

    readiness_state: str
    gate: dict
    same_book_late_final: int
    confirmed_lineups: int
    pre_post_lineup_pairs: int
    captured_fixtures: int

    def to_dict(self) -> dict:
        return {
            "readiness_state": self.readiness_state,
            "gate": self.gate,
            "counts": {
                "captured_fixtures": self.captured_fixtures,
                "same_book_late_final": self.same_book_late_final,
                "confirmed_lineups": self.confirmed_lineups,
                "pre_post_lineup_pairs": self.pre_post_lineup_pairs,
            },
        }


def assess_readiness(
    dataset: PriceDiscoveryDataset,
    *,
    confirmed_lineups: int = 0,
    pre_post_lineup_pairs: int = 0,
    descriptive_floor_transitions: int = 30,
) -> ReadinessAssessment:
    """Assess the preregistered readiness state.

    ``confirmed_lineups`` / ``pre_post_lineup_pairs`` are passed in because the
    current store carries no lineup captures (they are 0 until the collector
    accumulates LATE/FINAL lineups). The gate uses the preregistered
    thresholds and is NEVER relaxed here.
    """
    same_book_late_final = dataset.transition_counts.get("LATE->FINAL", 0)
    captured_fixtures = dataset.n_fixtures

    gate = PROSPECTIVE_GATE.evaluate(
        captured_fixtures=captured_fixtures,
        same_book_late_final=same_book_late_final,
        confirmed_lineups=confirmed_lineups,
        pre_post_lineup_pairs=pre_post_lineup_pairs,
    )

    if gate["met"]:
        state = "PRICE_DISCOVERY_EVALUABLE"
    elif len(dataset.transitions) >= descriptive_floor_transitions:
        state = "PRICE_DISCOVERY_EXPLORATORY"
    else:
        state = "PRICE_DISCOVERY_NOT_ENOUGH_DATA"

    return ReadinessAssessment(
        readiness_state=state,
        gate=gate,
        same_book_late_final=same_book_late_final,
        confirmed_lineups=confirmed_lineups,
        pre_post_lineup_pairs=pre_post_lineup_pairs,
        captured_fixtures=captured_fixtures,
    )


def descriptive_report(dataset: PriceDiscoveryDataset) -> dict:
    """Pure descriptive statistics (allowed pre-gate). No predictive claims."""
    t = dataset.transitions
    return {
        "dataset": dataset.to_dict(),
        "movement": _movement_stats(t),
        "movement_by_transition": {
            label: _movement_stats([x for x in t if f"{x.earlier_vintage}->{x.later_vintage}" == label])
            for label in sorted(dataset.transition_counts)
        },
        "coverage": {
            "by_bookmaker": _group_counts(t, "bookmaker"),
            "by_market": _group_counts(t, "market"),
            "by_competition": _group_counts(t, "league"),
        },
        "bookmaker_continuity": {
            # fraction of transitions per book (same-book by construction).
            "books_present": sorted({x.bookmaker for x in t}),
            "n_books": len({x.bookmaker for x in t}),
        },
        "line_changes": {
            "n": len(dataset.line_changes),
            "note": "line changes are tracked separately and never counted as price movement",
        },
    }


def build_full_report(
    dataset: PriceDiscoveryDataset,
    *,
    confirmed_lineups: int = 0,
    pre_post_lineup_pairs: int = 0,
) -> dict:
    readiness = assess_readiness(
        dataset,
        confirmed_lineups=confirmed_lineups,
        pre_post_lineup_pairs=pre_post_lineup_pairs,
    )
    return {
        "readiness": readiness.to_dict(),
        "descriptive": descriptive_report(dataset),
        "disclaimer": (
            "Descriptive only. No predictive-signal, edge, or profitability "
            "claim is made or permitted before the preregistered gate is met."
        ),
    }
