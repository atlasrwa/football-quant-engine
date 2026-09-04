"""Predeclared La Liga corners confirmation protocol.

This protocol is intentionally narrower than the broad league x market report.
It defines one correlated family: a hierarchical count model for Spain La Liga
corners at 8.5, 9.5, and 10.5.  It is only valid for evaluations generated after
this source version is committed; it cannot retroactively validate Pilot-C
results or turn a historical finding into a production signal.
"""

from __future__ import annotations

import hashlib
import json
from statistics import median
from typing import Any, Mapping, Sequence

LEAGUE = "Spain La Liga"
MARKET = "corners"
LINES = (8.5, 9.5, 10.5)
BASELINE_CONTRAST = "hierarchical_vs_climatology"
INDEPENDENT_CONTRAST = "hierarchical_vs_independent"

PROTOCOL: dict[str, Any] = {
    "document_id": "laliga-corners-hierarchical-v2",
    "scope": {
        "league": LEAGUE,
        "market": MARKET,
        "lines": list(LINES),
        "unit": "fixture scored across all three correlated lines",
    },
    "hypothesis": (
        "The hierarchical corner-count arm improves out-of-time probabilistic "
        "forecasts over the expanding league-aware baseline across the La Liga "
        "8.5/9.5/10.5 family."
    ),
    "required_contrasts": {
        "baseline": BASELINE_CONTRAST,
        "independent": INDEPENDENT_CONTRAST,
    },
    "primary_estimand": (
        "reference Brier loss minus hierarchical Brier loss on identical "
        "walk-forward fixture-line observations; positive favors hierarchy"
    ),
    "family_rule": (
        "Adjacent lines are one correlated confirmation family. Line-level cells "
        "remain published, but are not separate discoveries."
    ),
    "historical_gate": {
        "median_within_league_brier_improvement_positive": True,
        "positive_majority_of_walk_forward_folds": True,
        "calibration_preserved_or_improved": True,
        "beats_independent_model": True,
    },
    "promotion_gate": {
        "untouched_later_season": True,
        "immutable_prospective_predictions": True,
        "same_book_clv": True,
        "execution_adjusted_roi": True,
        "stable_by_time_to_kickoff": True,
    },
    "spatial_features": "BLOCKED_UNVERIFIED_ORIENTATION",
    "production_status": "RESEARCH_ONLY",
}


def protocol_definition() -> dict[str, Any]:
    """Return the immutable protocol plus a deterministic content hash."""
    payload = json.loads(json.dumps(PROTOCOL))
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    payload["protocol_sha256"] = hashlib.sha256(encoded).hexdigest()
    return payload


def summarize_confirmation(cells: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize the correlated La Liga family without claiming promotion.

    ``cells`` are the fully published, same-fixture count-evaluation cells. A
    line that cannot be evaluated leaves the family insufficient rather than
    being silently dropped. The summary has no independent family p-value: this
    evaluator's standard BH correction remains the broad-report multiplicity
    control, while a predeclared joint market-relative omnibus analysis awaits
    genuinely timestamped prices.
    """
    protocol = protocol_definition()
    by_key = {
        (cell.get("line"), cell.get("contrast")): cell
        for cell in cells
        if cell.get("league") == LEAGUE and cell.get("market") == MARKET
    }
    baseline = [by_key.get((line, BASELINE_CONTRAST)) for line in LINES]
    independent = [by_key.get((line, INDEPENDENT_CONTRAST)) for line in LINES]
    required = [*baseline, *independent]
    missing = [
        f"{line}:{contrast}"
        for line, contrast, cell in (
            *((line, BASELINE_CONTRAST, cell) for line, cell in zip(LINES, baseline)),
            *((line, INDEPENDENT_CONTRAST, cell) for line, cell in zip(LINES, independent)),
        )
        if cell is None
    ]
    insufficient = [
        f"{cell.get('line')}:{cell.get('contrast')}"
        for cell in required
        if cell is not None and cell.get("status") != "tested"
    ]
    output: dict[str, Any] = {
        "protocol": protocol,
        "status": "insufficient" if missing or insufficient else "tested_research_only",
        "missing_cells": missing,
        "insufficient_cells": insufficient,
        "line_results": [],
        "family_metrics": {},
        "historical_gate": {key: False for key in protocol["historical_gate"]},
        "promotion_gate": {
            key: False for key in protocol["promotion_gate"]
        },
        "decision": "RESEARCH_ONLY_NOT_PROMOTABLE",
        "reason": (
            "An untouched later season, immutable prospective predictions, "
            "same-book CLV, execution-adjusted ROI, and timing stability are "
            "required before any production or delivery change."
        ),
    }
    if missing or insufficient:
        return output

    baseline_effects: list[float] = []
    independent_effects: list[float] = []
    calibration_effects: list[float] = []
    positive_folds = 0
    total_folds = 0
    for baseline_cell, independent_cell in zip(baseline, independent, strict=True):
        assert baseline_cell is not None and independent_cell is not None
        baseline_brier = float(baseline_cell["effects"]["brier"]["point"])
        independent_brier = float(independent_cell["effects"]["brier"]["point"])
        baseline_ece = float(baseline_cell["effects"]["ece"]["point"])
        folds = baseline_cell.get("fold_stability", {}).get("folds", [])
        line_positive = sum(
            float(fold["brier_effect"]) > 0.0 for fold in folds
        )
        baseline_effects.append(baseline_brier)
        independent_effects.append(independent_brier)
        calibration_effects.append(baseline_ece)
        positive_folds += line_positive
        total_folds += len(folds)
        output["line_results"].append({
            "line": baseline_cell["line"],
            "hierarchical_vs_league_baseline_brier": baseline_brier,
            "hierarchical_vs_independent_brier": independent_brier,
            "hierarchical_vs_league_baseline_ece": baseline_ece,
            "positive_walk_forward_folds": line_positive,
            "walk_forward_folds": len(folds),
            "fixture_ids_identical_across_arms": baseline_cell[
                "identical_fixture_ids_across_arms"
            ],
        })

    output["family_metrics"] = {
        "median_hierarchical_vs_league_baseline_brier": median(baseline_effects),
        "median_hierarchical_vs_independent_brier": median(independent_effects),
        "median_hierarchical_vs_league_baseline_ece": median(calibration_effects),
        "positive_fold_fraction": positive_folds / total_folds if total_folds else 0.0,
        "fold_count_across_family": total_folds,
        "omnibus_p_value": None,
        "omnibus_status": "BLOCKED_NO_TIMESTAMPED_MARKET_RELATIVE_DATA",
    }
    output["historical_gate"] = {
        "median_within_league_brier_improvement_positive": median(baseline_effects) > 0.0,
        "positive_majority_of_walk_forward_folds": (
            total_folds > 0 and positive_folds / total_folds > 0.5
        ),
        "calibration_preserved_or_improved": median(calibration_effects) >= 0.0,
        "beats_independent_model": median(independent_effects) > 0.0,
    }
    return output
