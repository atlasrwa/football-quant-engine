"""Market comparison adapter for V3.5 frozen distributions.

Market prices are downstream only; they never enter model probabilities.
"""
from __future__ import annotations

from src.research.v3_pilot.market import (
    _bet365, _evaluate_pair, _ou_pair, devig, goal_comparisons,
)


def corner_comparison(corner_distribution: dict, odds_payload: dict) -> dict | None:
    bk = _bet365(odds_payload)
    if not bk:
        return None
    market = ((bk.get("markets") or {}).get("match_corners") or {})
    supported = corner_distribution.get("probabilities") or {}
    choices = []
    for line_key, probs in supported.items():
        node = market.get(str(line_key)) or {}
        pair = _ou_pair(node, "last_seen")
        if pair is None:
            continue
        line = float(line_key)
        p_market_over, _ = devig(*pair)
        choices.append((abs(p_market_over - 0.5), line, pair, node, probs))
    if not choices:
        return None
    _, line, pair, node, probs = sorted(choices, key=lambda x: (x[0], x[1]))[0]
    p_over = float(probs["p_over"])
    cmp = _evaluate_pair(p_over=p_over, over_odds=pair[0], under_odds=pair[1])
    opening_pair = _ou_pair(node, "opening")
    opening = None
    if opening_pair:
        mo, mu = devig(*opening_pair)
        opening = {
            "over_odds": opening_pair[0], "under_odds": opening_pair[1],
            "p_novig_selected": mo if cmp["side"] == "OVER" else mu,
        }
    return {
        "market_family": "corners",
        "market": "Bet365_total_corners",
        "line": line,
        "p_model_over": p_over,
        "model_parent_probabilities": {
            "v3": float(probs["p_over_v3"]),
            "pressure": float(probs["p_over_pressure"]),
            "pressure_weight": float(probs["pressure_weight"]),
        },
        "opening": opening,
        **cmp,
    }


__all__ = ["goal_comparisons", "corner_comparison"]
