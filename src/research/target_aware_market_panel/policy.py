"""Frozen policies: target universe, market line policy, target-family context selectors and
baseline semantic coverage. Derived from the registry and provider line structure only; no
outcome, no model result, no market price level is used.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.research.target_aware_market_panel.registry import _node

POLICY_VERSION = "target_aware_policies_v1"

#: Registry market -> odds spec used for line derivation (quantity may be a PROXY: yellows).
LINE_SOURCE = {
    "TOTAL_GOALS": {"market": "total_goals"},
    "HOME_GOALS": {"market": "team_total_goals", "side": "home"},
    "AWAY_GOALS": {"market": "team_total_goals", "side": "away"},
    "TOTAL_CORNERS": {"market": "match_corners"},
    "HOME_CORNERS": {"market": "team_corners", "side": "home"},
    "AWAY_CORNERS": {"market": "team_corners", "side": "away"},
    "TOTAL_YELLOW_CARDS": {"market": "total_cards"},
}
FAMILY_OF = {"TOTAL_GOALS": "GOALS", "BTTS": "GOALS", "TOTAL_CORNERS": "CORNERS",
             "HOME_GOALS": "TEAM_TOTALS", "AWAY_GOALS": "TEAM_TOTALS",
             "HOME_CORNERS": "TEAM_TOTALS", "AWAY_CORNERS": "TEAM_TOTALS",
             "TOTAL_YELLOW_CARDS": "BOOKINGS"}
EVALUATION_FAMILIES = ("GOALS", "CORNERS", "TEAM_TOTALS", "BOOKINGS", "HALF_TIME")


def main_line(data: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Any]:
    """Mode, over strictly pre-kickoff captures, of the most balanced half-line
    (min |over - under| decimal price; ties to the lower line). Uses market STRUCTURE only."""
    counts: Dict[str, int] = {}
    n = 0
    for mid, cts, bks in data["captures"]:
        k = data["kickoffs"].get(mid)
        if cts is None or k is None or cts >= k:
            continue
        for b in bks:
            node = _node(b.get("markets"), spec)
            if not node:
                continue
            best = None
            for ln, sel in node.items():
                try:
                    if float(ln) % 1 != 0.5:
                        continue
                    o = float(sel["over"]["last_seen"] or sel["over"]["opening"])
                    u = float(sel["under"]["last_seen"] or sel["under"]["opening"])
                except (KeyError, TypeError, ValueError):
                    continue
                key = (abs(o - u), float(ln))
                if best is None or key < best[0]:
                    best = (key, ln)
            if best:
                counts[best[1]] = counts.get(best[1], 0) + 1
                n += 1
    if not counts:
        return {"status": "NO_LINE_EVIDENCE"}
    ordered = sorted(counts.items(), key=lambda kv: (-kv[1], float(kv[0])))
    primary = ordered[0][0]
    p = float(primary)
    return {"status": "OK", "primary_line": p,
            "secondary_lines": [p - 1.0, p + 1.0] if p - 1.0 > 0 else [p + 1.0],
            "n_captures": n, "main_line_counts": dict(ordered[:6]),
            "near_tie_with": [ln for ln, c in ordered[1:3] if c >= 0.95 * ordered[0][1]]}


def line_policy(data: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for mid, spec in LINE_SOURCE.items():
        r = main_line(data, spec)
        r["policy"] = ("C_PREREGISTERED_GRID_ANCHORED_ON_PROXY_CARDS_MARKET"
                       if mid == "TOTAL_YELLOW_CARDS" else "A_PROVIDER_OBSERVED_MAIN_LINE")
        out[mid] = r
    out["BTTS"] = {"status": "OK", "primary_line": None, "secondary_lines": [],
                   "policy": "NO_LINE (binary market)"}
    return {"line_policy_version": POLICY_VERSION,
            "rule": "primary = mode over strictly pre-kickoff timestamped captures of the most "
                    "balanced half-line (min |over-under| price, ties to the lower line); "
                    "secondary = primary +/- 1.0. Frozen before any outcome comparison. LLM "
                    "never sets a threshold.",
            "uses_prices_for": "line STRUCTURE only (which line is balanced), never price level "
                               "as a feature or a prompt input",
            "lines": out}


def target_universe(registry: Dict[str, Any], lines: Dict[str, Any]) -> Dict[str, Any]:
    tg = []
    for m in registry["markets"]:
        if not (m["eligible_for_hypothesis_generation"] and m["eligible_for_oos_modeling"]):
            continue
        lp = lines["lines"].get(m["market_id"])
        if not lp or lp["status"] != "OK":
            continue
        base = {"market_id": m["market_id"], "family": FAMILY_OF[m["market_id"]],
                "period": m["period"], "scope": m["scope"], "statistic": m["statistic"],
                "settlement_rule": m["settlement_rule"],
                "eligible_for_market_comparison": m["eligible_for_market_comparison"],
                "proxy": m["odds_semantics"].startswith("PROXY")}
        if lp["primary_line"] is None:
            tg.append({**base, "target_id": m["market_id"], "line": None, "line_role": "PRIMARY"})
            continue
        for role, ln in [("PRIMARY", lp["primary_line"])] + [
                ("SECONDARY", x) for x in lp["secondary_lines"]]:
            tg.append({**base, "target_id": f"{m['market_id']}_OVER_{str(ln).replace('.', '_')}",
                       "line": ln, "line_role": role})
    fams = {f: sorted({t["market_id"] for t in tg if t["family"] == f})
            for f in EVALUATION_FAMILIES}
    return {"target_universe_version": POLICY_VERSION,
            "inclusion_rule": "eligible_for_hypothesis_generation AND eligible_for_oos_modeling "
                              "(market odds NOT required)",
            "targets": tg, "families": fams,
            "family_status": {f: ("EVALUABLE" if fams[f] else
                                  "NOT_EVALUABLE: no generation+modeling-eligible market "
                                  "(provider has no bulk half-time score; half corners/yellows "
                                  "have no provider market)") for f in EVALUATION_FAMILIES}}


#: Deterministic, frozen evidence selectors per family (semantic relevance, not per fixture).
FAMILY_CONTEXT = {
    "GOALS": ["goals", "shots", "shots_on_target", "shots_inside_box", "shots_outside_box",
              "big_chances", "touches_in_box", "final_third_entries", "possession", "saves"],
    "CORNERS": ["corners", "accurate_crosses", "touches_in_box", "final_third_entries", "shots",
                "shots_inside_box", "clearances", "possession"],
    "TEAM_TOTALS": ["goals", "corners", "shots", "shots_on_target", "shots_inside_box",
                    "big_chances", "touches_in_box", "accurate_crosses", "final_third_entries",
                    "clearances", "possession"],
    "BOOKINGS": ["yellow_cards", "fouls", "tackles", "tackles_won_pct", "ground_duel_pct",
                 "aerial_duel_pct", "fouled_in_final_third", "possession", "interceptions"],
}
#: Genuine provider half-level history exposed as context (verified coverage + fh+sh==all).
HALF_CONTEXT = {"CORNERS": ["corners"], "TEAM_TOTALS": ["corners"], "BOOKINGS": ["yellow_cards"],
                "GOALS": ["shots"]}
HALF_PROVIDER_FIELDS = {"corners": ("overview", "corner_kicks"),
                        "yellow_cards": ("overview", "yellow_cards"),
                        "shots": ("overview", "total_shots")}


def context_policy() -> Dict[str, Any]:
    return {"context_policy_version": POLICY_VERSION,
            "rule": "each Sol request is sliced to one family's frozen metric list; raw recent "
                    "match rows keep only those metrics; selectors are code constants, never "
                    "chosen per fixture",
            "family_metrics": FAMILY_CONTEXT, "half_level_metrics": HALF_CONTEXT,
            "excluded_everywhere": ["npxg", "expected_goals", "goals_prevented", "red_cards",
                                    "blocked_shots (defensive interpretation unresolved; "
                                    "never in a slice)"]}


M0_WINDOWS = ("W5", "W10", "SEASON_TO_DATE", "VENUE_SEASON_TO_DATE")


def baseline_semantic_coverage() -> Dict[str, Any]:
    """What M0 already knows, conceptually. No coefficients, no performance, no results."""
    return {
        "baseline_semantic_coverage_version": POLICY_VERSION,
        "m0_definition": {
            "model_class": "elastic_net_logistic_regression (one model per target)",
            "features": "for BOTH teams and EVERY metric in the target family's context list: "
                        "rolling FOR mean and AGAINST mean over W5, W10, current-season-to-date "
                        "and venue-specific current-season-to-date (home team at home, away team "
                        "away), strictly before kickoff, current-season only, NULL != ZERO",
            "windows": list(M0_WINDOWS),
            "family_metrics": FAMILY_CONTEXT,
            "half_level_features": "for BOTH teams and every metric in the family's half-level "
                                   "context: FIRST_HALF and SECOND_HALF rolling FOR/AGAINST "
                                   "means over the same windows (so half-level data never "
                                   "reaches M1 alone)",
            "family_half_metrics": HALF_CONTEXT,
            "controls": ["team strength: mean goal difference over the last 10 same-competition "
                         "matches (both teams)", "competition indicator"],
            "same_data_as_m1": "M0 sees exactly the TheStatsAPI metrics that the LLM sees, so an "
                               "M1 gain cannot come from richer raw data alone"},
        "baseline_already_captures": {
            "GOALS": ["each team's goals scored/conceded rates", "shot volume and quality "
                      "rates (SoT, inside-box, big chances)", "box access and territory "
                      "(touches in box, final-third entries, possession)", "venue", "strength",
                      "competition"],
            "CORNERS": ["each team's corners won/conceded rates", "crossing, box access, shot "
                        "and clearance rates", "possession", "venue", "strength", "competition"],
            "TEAM_TOTALS": ["the team's own FOR rates and the opponent's AGAINST rates for goals "
                            "and corners", "supporting attack/defence rates", "venue",
                            "strength", "competition"],
            "BOOKINGS": ["each team's yellow-card, foul, tackle and duel rates (for and "
                         "against)", "possession/territory", "venue", "strength",
                         "competition"],
        },
        "simple_interaction_grammar": {
            "definition": "any pairwise product, ratio, sum or difference of two M0 rolling-mean "
                          "features; a deterministic enumerator would generate these, so a "
                          "hypothesis that reduces to one is classified SIMPLE_INTERACTION",
            "linear_combinations_of_m0_features": "BASELINE_EQUIVALENT (a linear model already "
                                                  "spans them)"},
        "what_the_llm_should_look_for": [
            "opponent-profile dependence (behaviour against opponents similar to this one)",
            "multi-dimensional attack x defence matchups (three or more interacting dimensions)",
            "state recurrence / recent-regime deviation from long-run behaviour",
            "conditional relationships the rolling means cannot express"],
        "contains_no_coefficients": True, "contains_no_performance": True,
        "contains_no_oos_results": True,
    }
