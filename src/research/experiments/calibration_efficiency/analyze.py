"""Analysis of the dependence walk-forward predictions (Phases B8-B10 + stats).

Consumes the paired baseline/dependence corner predictions and computes, per
line and pooled:
- Brier, log loss, ECE, calibration slope/intercept (reusing the experiment
  metrics helpers), sharpness, coverage, base rate.
- Paired block-bootstrap of the (dependence - baseline) Brier/log-loss
  difference, resampling MATCH-WEEK blocks (temporal clustering), collapsing the
  correlated lines within a fixture to one observation so lines are not counted
  as independent evidence.
- Market benchmark: baseline and dependence vs de-vigged pre-match corner odds
  on the common fixtures.

Paired keys are identical by construction (same walk-forward emits both arms per
(fixture,line)), so alignment is exact.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from typing import Optional, Sequence

from src.research.experiments.provider_comparison.metrics import (
    brier_losses,
    compute_metrics,
    log_losses,
)

CORNER_LINES = (7.5, 8.5, 9.5, 10.5)


def _metrics_for(preds: list[dict], prob_key: str, *, market: str, line: Optional[float]) -> dict:
    probs = [p[prob_key] for p in preds]
    outs = [bool(p["y"]) for p in preds]
    return compute_metrics(probs, outs, policy=prob_key, market=market, line=line).to_dict()


def per_line_and_pooled(preds: list[dict]) -> dict:
    """Baseline vs dependence metrics per corner line and pooled."""
    out: dict = {"lines": {}, "pooled": {}}
    for line in CORNER_LINES:
        sub = [p for p in preds if p["line"] == line]
        out["lines"][str(line)] = {
            "n": len(sub),
            "baseline": _metrics_for(sub, "pb", market="CORNERS_TOTAL", line=line),
            "dependence": _metrics_for(sub, "pd", market="CORNERS_TOTAL", line=line),
        }
    out["pooled"] = {
        "n": len(preds),
        "baseline": _metrics_for(preds, "pb", market="CORNERS_TOTAL", line=None),
        "dependence": _metrics_for(preds, "pd", market="CORNERS_TOTAL", line=None),
    }
    return out


def _paired_block_bootstrap(
    preds: list[dict], metric: str, *, n_boot: int = 2000, seed: int = 20260909
) -> dict:
    """Paired (dependence - baseline) loss difference, block bootstrap by week.

    Collapses lines within a fixture to one mean loss-diff (so correlated lines
    are one observation), and resamples MATCH-WEEK blocks (clustered temporal
    dependence). <0 means dependence has lower loss (better).
    """
    loss_fn = brier_losses if metric == "brier" else log_losses
    # group by fixture, then aggregate lines
    by_fixture: dict[str, list[float]] = defaultdict(list)
    fixture_week: dict[str, str] = {}
    fixture_ko: dict[str, int] = {}
    for p in preds:
        lb = loss_fn([p["pb"]], [bool(p["y"])])[0]
        ld = loss_fn([p["pd"]], [bool(p["y"])])[0]
        by_fixture[p["k"]].append(ld - lb)
        fixture_week[p["k"]] = p["wb"]
        fixture_ko[p["k"]] = p["ko"]
    fixture_diff = {fk: sum(v) / len(v) for fk, v in by_fixture.items()}
    n_fix = len(fixture_diff)
    if n_fix == 0:
        return {"metric": metric, "n_fixtures": 0}
    observed = sum(fixture_diff.values()) / n_fix

    # blocks = match-weeks
    blocks: dict[str, list[str]] = defaultdict(list)
    for fk in fixture_diff:
        blocks[fixture_week[fk]].append(fk)
    block_ids = list(blocks.keys())
    rng = random.Random(seed)
    n_blocks = len(block_ids)
    boots = []
    for _ in range(n_boot):
        vals = []
        for _ in range(n_blocks):
            b = block_ids[rng.randrange(n_blocks)]
            vals.extend(fixture_diff[fk] for fk in blocks[b])
        if vals:
            boots.append(sum(vals) / len(vals))
    boots.sort()
    lo = boots[int(0.025 * len(boots))]
    hi = boots[int(0.975 * len(boots)) - 1]
    prob_dep_better = sum(1 for b in boots if b < 0) / len(boots)
    return {
        "metric": metric,
        "observed_diff_dependence_minus_baseline": round(observed, 6),
        "ci95": [round(lo, 6), round(hi, 6)],
        "prob_dependence_better": round(prob_dep_better, 4),
        "n_fixtures": n_fix,
        "n_blocks": n_blocks,
        "n_predictions": len(preds),
    }


def paired_uncertainty(preds: list[dict], *, n_boot: int = 2000, seed: int = 20260909) -> dict:
    return {
        "brier": _paired_block_bootstrap(preds, "brier", n_boot=n_boot, seed=seed),
        "log_loss": _paired_block_bootstrap(preds, "log_loss", n_boot=n_boot, seed=seed),
    }


def market_comparison(preds: list[dict], market_probs: dict) -> Optional[dict]:
    """Baseline & dependence vs de-vigged pre-match corner market, common fixtures.

    market_probs: {(fixture_key, line) -> fair P(over)}.
    """
    rows = []
    for p in preds:
        mp = market_probs.get((p["k"], p["line"]))
        if mp is None:
            continue
        rows.append((p["pb"], p["pd"], mp, bool(p["y"])))
    if not rows:
        return None
    n = len(rows)
    def brier(probs, outs):
        return sum((pp - (1.0 if yy else 0.0)) ** 2 for pp, yy in zip(probs, outs)) / len(probs)
    base_b = brier([r[0] for r in rows], [r[3] for r in rows])
    dep_b = brier([r[1] for r in rows], [r[3] for r in rows])
    mkt_b = brier([r[2] for r in rows], [r[3] for r in rows])
    return {
        "n_line_preds": n,
        "baseline_brier": round(base_b, 4),
        "dependence_brier": round(dep_b, 4),
        "market_brier": round(mkt_b, 4),
        "baseline_gap_to_market": round(base_b - mkt_b, 4),
        "dependence_gap_to_market": round(dep_b - mkt_b, 4),
    }
