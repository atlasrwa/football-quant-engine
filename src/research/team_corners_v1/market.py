from __future__ import annotations
from src.research.v3_pilot.market import _bet365, _ou_pair, devig
from .config import PRIMARY_LINES, spec

_SELECTION = spec()["selection"]

def team_corner_pair(payload: dict, role: str, line: float, field: str = "last_seen"):
    book = _bet365(payload)
    if not book:
        return None
    markets = book.get("markets") or {}
    team = (markets.get("team_corners") or {}).get(role) or {}
    node = team.get(str(float(line))) or team.get(str(line)) or {}
    return _ou_pair(node, field)

def compare_probability(p_over: float, over_odds: float, under_odds: float,
                        *, role: str, line: float) -> dict:
    market_over, market_under = devig(float(over_odds), float(under_odds))
    if float(p_over) >= market_over:
        side = "OVER"
        p_model = float(p_over)
        p_market = float(market_over)
        price = float(over_odds)
    else:
        side = "UNDER"
        p_model = 1.0 - float(p_over)
        p_market = float(market_under)
        price = float(under_odds)
    delta = p_model - p_market
    raw_be = 1.0 / price
    qualifies = (
        p_model >= float(_SELECTION["min_selected_probability"])
        and delta >= float(_SELECTION["min_model_minus_market_novig"])
        and (not _SELECTION["must_beat_raw_break_even"] or p_model > raw_be)
    )
    return {
        "role": role, "line": float(line), "side": side,
        "p_model": p_model, "p_market": p_market, "delta": delta,
        "price": price, "raw_break_even": raw_be, "qualifies": bool(qualifies),
        "over_odds": float(over_odds), "under_odds": float(under_odds),
        "market_over": float(market_over), "market_under": float(market_under),
        "two_way_overround": 1.0 / float(over_odds) + 1.0 / float(under_odds),
    }

def comparisons(prediction: dict, odds: dict) -> list[dict]:
    out = []
    for role, side_pred in (prediction.get("sides") or {}).items():
        probs = side_pred.get("probabilities") or {}
        for line in PRIMARY_LINES:
            pair = team_corner_pair(odds, role, line)
            node = probs.get(str(line))
            if not pair or not node:
                continue
            rec = compare_probability(float(node["p_over"]), pair[0], pair[1], role=role, line=line)
            rec["team_id"] = side_pred["team_id"]
            rec["team_name"] = side_pred["team_name"]
            rec["mu"] = side_pred["mu"]
            rec["components"] = side_pred["components"]
            rec["model_version"] = side_pred["model_version"]
            out.append(rec)
    return out

def best_qualifier(rows: list[dict], role: str) -> dict | None:
    eligible = [r for r in rows if r["role"] == role and r["qualifies"]]
    if not eligible:
        return None
    return sorted(eligible, key=lambda r: (-r["delta"], r["line"], r["side"]))[0]

def quoted_roles(rows: list[dict]) -> set[str]:
    return {str(r["role"]) for r in rows}
