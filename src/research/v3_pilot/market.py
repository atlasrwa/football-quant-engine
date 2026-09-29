"""Market comparison layer for V3. Model distributions arrive already frozen."""
from __future__ import annotations

import math
from typing import Any

from .freeze import load_freeze
from .model import poisson_over

_F = load_freeze()
_SEL = _F["selection"]

def _decimal(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x > 1.0 and math.isfinite(x) else None

def devig(over_odds: float, under_odds: float) -> tuple[float, float]:
    a, b = 1.0 / over_odds, 1.0 / under_odds
    s = a + b
    return a / s, b / s

def _bet365(payload: dict) -> dict | None:
    for bk in ((payload or {}).get("data") or {}).get("bookmakers", []) or []:
        name = str(bk.get("bookmaker") or "").strip().lower()
        if name.startswith("bet365"):
            return bk
    return None

def _ou_pair(node: dict, field: str = "last_seen") -> tuple[float, float] | None:
    if not isinstance(node, dict):
        return None
    over = _decimal((node.get("over") or {}).get(field))
    under = _decimal((node.get("under") or {}).get(field))
    if over is None or under is None:
        return None
    return over, under

def _evaluate_pair(*, p_over: float, over_odds: float, under_odds: float) -> dict:
    market_over, market_under = devig(over_odds, under_odds)
    if p_over >= market_over:
        side = "OVER"
        p_model = p_over
        p_market = market_over
        price = over_odds
        opposite = under_odds
    else:
        side = "UNDER"
        p_model = 1.0 - p_over
        p_market = market_under
        price = under_odds
        opposite = over_odds
    delta = p_model - p_market
    raw_break_even = 1.0 / price
    qualifies = (
        p_model >= float(_SEL["min_selected_probability"])
        and delta >= float(_SEL["min_model_minus_market_novig"])
        and (
            not bool(_SEL["must_beat_vig_loaded_break_even"])
            or p_model > raw_break_even
        )
    )
    return {
        "side": side,
        "p_model_selected": p_model,
        "p_market_novig_selected": p_market,
        "model_minus_market_novig": delta,
        "price_decimal": price,
        "opposite_price_decimal": opposite,
        "raw_break_even_selected": raw_break_even,
        "two_way_overround": (1/over_odds + 1/under_odds),
        "qualifies": qualifies,
    }

def goal_comparisons(goal_distribution: dict, odds_payload: dict) -> list[dict]:
    bk = _bet365(odds_payload)
    if not bk:
        return []
    markets = bk.get("markets") or {}
    tg = markets.get("total_goals") or {}
    out = []
    for line in (2.5, 3.5):
        node = tg.get(str(line)) or {}
        pair = _ou_pair(node, "last_seen")
        if pair is None:
            continue
        p_over = float(goal_distribution["probabilities"][str(line)]["p_over"])
        cmp = _evaluate_pair(
            p_over=p_over, over_odds=pair[0], under_odds=pair[1]
        )
        op = _ou_pair(node, "opening")
        opening = None
        if op:
            mo, mu = devig(*op)
            opening = {
                "over_odds": op[0], "under_odds": op[1],
                "p_novig_selected": mo if cmp["side"] == "OVER" else mu,
            }
        out.append({
            "market_family": "goals",
            "market": "Bet365_total_goals",
            "line": line,
            "p_model_over": p_over,
            "opening": opening,
            **cmp,
        })
    return out

def corner_comparison(corner_distribution: dict, odds_payload: dict) -> dict | None:
    bk = _bet365(odds_payload)
    if not bk:
        return None
    mc = ((bk.get("markets") or {}).get("match_corners") or {})
    choices = []
    for line_raw, node in mc.items():
        try:
            line = float(line_raw)
        except (TypeError, ValueError):
            continue
        if abs((line % 1) - 0.5) > 1e-9:
            continue
        pair = _ou_pair(node, "last_seen")
        if pair is None:
            continue
        pmo, _ = devig(*pair)
        choices.append((abs(pmo - 0.5), line, pair, node))
    if not choices:
        return None
    _, line, pair, node = sorted(choices, key=lambda x: (x[0], x[1]))[0]
    p_over = poisson_over(line, float(corner_distribution["lambda_total"]))
    cmp = _evaluate_pair(p_over=p_over, over_odds=pair[0], under_odds=pair[1])
    op = _ou_pair(node, "opening")
    opening = None
    if op:
        mo, mu = devig(*op)
        opening = {
            "over_odds": op[0], "under_odds": op[1],
            "p_novig_selected": mo if cmp["side"] == "OVER" else mu,
        }
    return {
        "market_family": "corners",
        "market": "Bet365_total_corners",
        "line": line,
        "p_model_over": p_over,
        "opening": opening,
        **cmp,
    }
