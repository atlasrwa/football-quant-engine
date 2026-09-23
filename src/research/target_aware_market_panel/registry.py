"""Market capability registry, DERIVED by scanning the provider cache (never hand-asserted).

Two capabilities are kept separate for every market:
  OUTCOME_LABEL_CAPABILITY   can the historical target be settled deterministically from
                             provider data (coverage, null semantics, half consistency)?
  MARKET_PRICE_CAPABILITY    do raw pre-kickoff timestamped prices exist AND is there a
                             validated adapter AND does the priced quantity equal the label?
Fail closed on every unknown.
"""
from __future__ import annotations

import glob
import json
import os
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.research.thestatsapi.closing_provider import parse_capture_timestamp
from src.research.thestatsapi.normalizer import _cell, parse_iso_to_unix

REGISTRY_VERSION = "market_capability_registry_v1"

#: Frozen label-verification thresholds.
MIN_LABEL_COVERAGE = 0.90          # both sides non-null in >= 90% of finished matches w/ stats
MAX_ONE_SIDED_NULL_SHARE = 0.01    # nulls must be whole-stat missing, not "null means zero"
MIN_HALF_CONSISTENCY = 0.99        # first_half + second_half == all
MIN_LABEL_ROWS = 1000

#: Adapters that exist AND are validated in this repository (by module + extractor).
VALIDATED_PRE_MATCH_ADAPTERS = {
    "total_goals": "src.research.thestatsapi.odds_normalizer._extract_total_goals",
    "match_odds": "src.research.thestatsapi.odds_normalizer._extract_1x2",
    "btts": "src.research.thestatsapi.odds_normalizer (BTTS)",
}
VALIDATED_CLOSING_ADAPTERS = {
    "total_goals": "src.research.thestatsapi.closing_provider._total_goals",
    "match_odds": "src.research.thestatsapi.closing_provider._match_odds",
}

G, C, B, O, R = "GOALS", "CORNERS", "BOOKINGS", "OFFSIDES", "RESULT"


def _m(mid, family, period, scope, stat, label, odds=None, odds_semantics="NONE", context_only=False):
    return {"market_id": mid, "family": family, "period": period, "scope": scope,
            "statistic": stat, "label_spec": label, "odds_spec": odds,
            "odds_semantics": odds_semantics, "context_only": context_only}


def _stat(group, key, period):
    return {"kind": "STAT", "group": group, "key": key, "period": period}


def _score(period):
    return {"kind": "SCORE", "period": period}


def candidate_markets() -> List[Dict[str, Any]]:
    """Every market family the audit must consider (the audit decides support, not this list)."""
    ms = []
    FM, FH, SH = "FULL_MATCH", "FIRST_HALF", "SECOND_HALF"
    for per, pk in ((FM, "all"), (FH, "first_half"), (SH, "second_half")):
        pre = "" if per == FM else ("FH_" if per == FH else "SH_")
        ms += [
            _m(f"{pre}TOTAL_GOALS", "GOALS" if per == FM else "HALF_TIME", per, "TOTAL", G,
               _score(per), {"market": "total_goals" if per == FM else
                             ("first_half_total_goals" if per == FH else None)},
               "SAME" if per != SH else "NONE"),
            _m(f"{pre}HOME_GOALS", "TEAM_TOTALS" if per == FM else "HALF_TIME", per, "HOME_TEAM",
               G, _score(per), {"market": "team_total_goals", "side": "home"} if per == FM
               else None, "SAME" if per == FM else "NONE"),
            _m(f"{pre}AWAY_GOALS", "TEAM_TOTALS" if per == FM else "HALF_TIME", per, "AWAY_TEAM",
               G, _score(per), {"market": "team_total_goals", "side": "away"} if per == FM
               else None, "SAME" if per == FM else "NONE"),
            _m(f"{pre}BTTS", "GOALS" if per == FM else "HALF_TIME", per, "TOTAL", "BTTS",
               _score(per), {"market": {"FULL_MATCH": "btts", "FIRST_HALF": "btts_first_half",
                                        "SECOND_HALF": "btts_second_half"}[per]}, "SAME"),
            _m(f"{pre}TOTAL_CORNERS", "CORNERS" if per == FM else "HALF_TIME", per, "TOTAL", C,
               _stat("overview", "corner_kicks", pk),
               {"market": "match_corners"} if per == FM else None,
               "SAME" if per == FM else "NONE"),
            _m(f"{pre}HOME_CORNERS", "TEAM_TOTALS" if per == FM else "HALF_TIME", per,
               "HOME_TEAM", C, _stat("overview", "corner_kicks", pk),
               {"market": "team_corners", "side": "home"} if per == FM else None,
               "SAME" if per == FM else "NONE"),
            _m(f"{pre}AWAY_CORNERS", "TEAM_TOTALS" if per == FM else "HALF_TIME", per,
               "AWAY_TEAM", C, _stat("overview", "corner_kicks", pk),
               {"market": "team_corners", "side": "away"} if per == FM else None,
               "SAME" if per == FM else "NONE"),
            _m(f"{pre}TOTAL_YELLOW_CARDS", "BOOKINGS" if per == FM else "HALF_TIME", per, "TOTAL",
               "YELLOW_CARDS", _stat("overview", "yellow_cards", pk),
               {"market": "total_cards"} if per == FM else None,
               "PROXY_CARDS_MARKET_QUANTITY_DIFFERS" if per == FM else "NONE"),
            _m(f"{pre}HOME_YELLOW_CARDS", "BOOKINGS" if per == FM else "HALF_TIME", per,
               "HOME_TEAM", "YELLOW_CARDS", _stat("overview", "yellow_cards", pk)),
            _m(f"{pre}AWAY_YELLOW_CARDS", "BOOKINGS" if per == FM else "HALF_TIME", per,
               "AWAY_TEAM", "YELLOW_CARDS", _stat("overview", "yellow_cards", pk)),
            _m(f"{pre}TOTAL_CARDS", "BOOKINGS" if per == FM else "HALF_TIME", per, "TOTAL",
               "CARDS_YELLOW_PLUS_RED",
               {"kind": "SUM", "parts": [_stat("overview", "yellow_cards", pk),
                                         _stat("overview", "red_cards", pk)]},
               {"market": "total_cards"} if per == FM else None,
               "UNVERIFIED_BOOKMAKER_CARD_COUNTING"),
            _m(f"{pre}HOME_CARDS", "BOOKINGS" if per == FM else "HALF_TIME", per, "HOME_TEAM",
               "CARDS_YELLOW_PLUS_RED",
               {"kind": "SUM", "parts": [_stat("overview", "yellow_cards", pk),
                                         _stat("overview", "red_cards", pk)]}),
            _m(f"{pre}AWAY_CARDS", "BOOKINGS" if per == FM else "HALF_TIME", per, "AWAY_TEAM",
               "CARDS_YELLOW_PLUS_RED",
               {"kind": "SUM", "parts": [_stat("overview", "yellow_cards", pk),
                                         _stat("overview", "red_cards", pk)]}),
            _m(f"{pre}TOTAL_OFFSIDES", "OFFSIDES", per, "TOTAL", O,
               _stat("attack", "offsides", pk)),
            _m(f"{pre}HOME_OFFSIDES", "OFFSIDES", per, "HOME_TEAM", O,
               _stat("attack", "offsides", pk)),
            _m(f"{pre}AWAY_OFFSIDES", "OFFSIDES", per, "AWAY_TEAM", O,
               _stat("attack", "offsides", pk)),
        ]
    ms.append(_m("MATCH_RESULT_1X2", "RESULT", "FULL_MATCH", "TOTAL", R, _score("FULL_MATCH"),
                 {"market": "match_odds"}, "SAME", context_only=True))
    for m in ms:
        if m["odds_spec"] and not m["odds_spec"].get("market"):
            m["odds_spec"] = None
    return ms


# ─────────────────────────────── label scanning ───────────────────────────────
def _load(path):
    try:
        return json.load(open(path))
    except (OSError, json.JSONDecodeError):
        return None


def load_cache(cache: str) -> Dict[str, Any]:
    fixtures, stats_seen = {}, {}
    for f in sorted(glob.glob(os.path.join(cache, "_all_fixtures*.json"))):
        for x in (_load(f) or {}).get("fixtures", []):
            if isinstance(x, dict) and str(x.get("status")).lower() == "finished":
                fixtures.setdefault(x["id"], x)
    for f in sorted(glob.glob(os.path.join(cache, "*stats_mt_*.json"))):
        base = os.path.basename(f)
        if base.startswith(("tamp_", "dpl_")):
            continue                           # operator gap fetches are not the panel
        d = _load(f)
        mid = ((d or {}).get("data") or {}).get("match_id")
        if mid:
            stats_seen.setdefault(mid, {})[json.dumps(d["data"], sort_keys=True)] = d
    stats = {m: next(iter(v.values())) for m, v in stats_seen.items() if len(v) == 1}
    kickoffs = {}
    for pat in ("_all_fixtures*.json", "discovery_comp_*_scheduled_*.json",
                "fixture_odds_matches_*.json"):
        for f in sorted(glob.glob(os.path.join(cache, pat))):
            d = _load(f) or {}
            for x in (d.get("fixtures") or d.get("data") or []):
                if isinstance(x, dict) and x.get("id"):
                    kickoffs.setdefault(x["id"], parse_iso_to_unix(x.get("utc_date")))
    captures = []            # (match_id, capture_ts, bookmakers) for research_odds files
    for f in sorted(glob.glob(os.path.join(cache, "research_odds_mt_*.json"))):
        d = (_load(f) or {}).get("data") or {}
        captures.append((d.get("match_id"), parse_capture_timestamp(os.path.basename(f)),
                         d.get("bookmakers") or []))
    cma = []                 # untimestamped cma "last_seen" payloads (never a close)
    for f in sorted(glob.glob(os.path.join(cache, "odds_mt_*.json"))):
        cma.append((((_load(f) or {}).get("data") or {}).get("bookmakers") or []))
    return {"fixtures": fixtures, "stats": stats, "kickoffs": kickoffs, "cache": cache,
            "captures": captures, "cma": cma,
            "n_stats_conflicts": sum(1 for v in stats_seen.values() if len(v) > 1)}


def _stat_pair(sd, spec):
    return [_cell(sd, spec["group"], spec["key"], spec["period"], s) for s in ("home", "away")]


def label_capability(m: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    ls = m["label_spec"]
    fx, st = data["fixtures"], data["stats"]
    if ls["kind"] == "SCORE":
        if ls["period"] == "FULL_MATCH":
            n = len(fx)
            ok = sum(1 for x in fx.values() if (x.get("score") or {}).get("home") is not None
                     and (x.get("score") or {}).get("away") is not None)
            supported = n >= MIN_LABEL_ROWS and ok / max(1, n) >= MIN_LABEL_COVERAGE
            return {"historical_label_supported": supported, "label_provider": "thestatsapi",
                    "label_fields": ["fixture.score.home", "fixture.score.away"],
                    "label_semantics_verified": supported, "coverage": round(ok / max(1, n), 4),
                    "n_label_rows": ok, "half_resolution_supported": False,
                    "failure_reason": None if supported else "insufficient score coverage"}
        key = "half_time_home" if ls["period"] == "FIRST_HALF" else "second_half_home"
        n_bulk = sum(1 for x in fx.values() if key in (x.get("score") or {}))
        return {"historical_label_supported": False, "label_provider": "thestatsapi",
                "label_fields": [f"fixture.score.{key}"], "label_semantics_verified": False,
                "coverage": round(n_bulk / max(1, len(fx)), 4), "n_label_rows": n_bulk,
                "half_resolution_supported": False,
                "failure_reason": "bulk fixture lists carry no half-time score "
                                  f"({n_bulk}/{len(fx)} rows); only single-match records do. "
                                  "Needs a provider backfill; never derived from full-match "
                                  "totals"}
    parts = ls["parts"] if ls["kind"] == "SUM" else [ls]
    part_res = []
    for p in parts:
        both = one = zero = nonnull = cons = cons_n = 0
        for mid, d in st.items():
            sd = d.get("data") or {}
            h, a = _stat_pair(sd, p)
            if h is not None and a is not None:
                both += 1
            elif (h is None) != (a is None):
                one += 1
            for v in (h, a):
                if v is not None:
                    nonnull += 1
                    zero += float(v) == 0
            if p["period"] != "all":
                for side in ("home", "away"):
                    vals = [_cell(sd, p["group"], p["key"], per, side)
                            for per in ("all", "first_half", "second_half")]
                    if None not in vals:
                        cons_n += 1
                        cons += float(vals[1]) + float(vals[2]) == float(vals[0])
        n = len(st)
        cov = both / max(1, n)
        reasons = []
        if n < MIN_LABEL_ROWS:
            reasons.append("too few stats payloads")
        if cov < MIN_LABEL_COVERAGE:
            reasons.append(f"{p['key']}.{p['period']} both-side coverage {cov:.3f} < "
                           f"{MIN_LABEL_COVERAGE}")
        if one / max(1, n) > MAX_ONE_SIDED_NULL_SHARE:
            reasons.append(f"{p['key']} one-sided nulls (possible null-means-zero)")
        if p["period"] != "all" and (cons_n == 0 or cons / cons_n < MIN_HALF_CONSISTENCY):
            reasons.append(f"{p['key']} halves do not sum to full match")
        part_res.append({"field": f"stats.{p['group']}.{p['key']}.{p['period']}",
                         "coverage": round(cov, 4), "one_sided_null_share":
                         round(one / max(1, n), 4),
                         "zero_share_of_non_null": round(zero / max(1, nonnull), 4),
                         "half_consistency": (round(cons / cons_n, 4) if cons_n else None),
                         "reasons": reasons})
    supported = all(not r["reasons"] for r in part_res)
    return {"historical_label_supported": supported, "label_provider": "thestatsapi",
            "label_fields": [r["field"] for r in part_res],
            "label_semantics_verified": supported,
            "coverage": min(r["coverage"] for r in part_res), "label_parts": part_res,
            "n_label_rows": len(st),
            "half_resolution_supported": supported and ls.get("period", parts[0]["period"])
                                         != "all",
            "failure_reason": None if supported else "; ".join(
                x for r in part_res for x in r["reasons"])}


# ─────────────────────────────── odds scanning ───────────────────────────────
def _node(markets, spec):
    v = (markets or {}).get(spec["market"])
    if isinstance(v, dict) and spec.get("side"):
        v = v.get(spec["side"])
    return v if isinstance(v, dict) and v else None


def odds_capability(m: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    spec = m["odds_spec"]
    base = {"market_odds_supported": False, "odds_provider": None,
            "timestamped_pre_match_supported": False,
            "genuine_last_before_kickoff_supported": False, "known_lines": {},
            "raw_price_present": False, "n_pre_kickoff_captures": 0,
            "n_matches_with_pre_kickoff_capture": 0}
    if not spec:
        return {**base, "odds_failure_reason": "no provider market for this quantity in any "
                                               "cached odds payload"}
    pre, matches, lines, cma = 0, set(), {}, 0
    for mid, cts, bks in data["captures"]:
        k = data["kickoffs"].get(mid)
        if cts is None or k is None or cts >= k:       # only strictly pre-kickoff captures
            continue
        for b in bks:
            node = _node(b.get("markets"), spec)
            if node:
                pre += 1
                matches.add(mid)
                for ln in node:
                    lines[ln] = lines.get(ln, 0) + 1
    for bks in data["cma"]:
        for b in bks:
            if _node(b.get("markets"), spec):
                cma += 1
    raw = pre > 0 or cma > 0
    validated = spec["market"] in VALIDATED_PRE_MATCH_ADAPTERS
    same = m["odds_semantics"] == "SAME"
    supported = raw and validated and same
    reason = None
    if not raw:
        reason = "market key absent from every cached odds payload"
    elif not same:
        reason = f"priced quantity differs from label ({m['odds_semantics']})"
    elif not validated:
        reason = "raw prices present but no validated adapter (normalizer/closing) for this key"
    ts_ok = supported and pre > 0
    return {"market_odds_supported": supported,
            "odds_provider": "thestatsapi" if raw else None,
            "timestamped_pre_match_supported": ts_ok,
            "genuine_last_before_kickoff_supported":
                ts_ok and spec["market"] in VALIDATED_CLOSING_ADAPTERS,
            "known_lines": dict(sorted(lines.items(), key=lambda kv: -kv[1])[:10]),
            "raw_price_present": raw, "n_pre_kickoff_captures": pre,
            "n_matches_with_pre_kickoff_capture": len(matches),
            "n_cma_last_seen_payloads_untimestamped": cma,
            "odds_failure_reason": reason}


def build_registry(cache: str) -> Dict[str, Any]:
    data = load_cache(cache)
    entries = []
    for m in candidate_markets():
        lab = label_capability(m, data)
        odd = odds_capability(m, data)
        model_ok = lab["historical_label_supported"] and lab["label_semantics_verified"]
        related_market = odd["raw_price_present"] and m["odds_semantics"] in (
            "SAME", "PROXY_CARDS_MARKET_QUANTITY_DIFFERS")
        gen_ok = model_ok and related_market and not m["context_only"]
        fail = []
        if not model_ok:
            fail.append(f"label: {lab['failure_reason']}")
        if model_ok and not related_market:
            fail.append("no provider market for this statistic/scope/period")
        if m["context_only"]:
            fail.append("context only (1X2 is not a target of this experiment)")
        entries.append({
            "market_id": m["market_id"], "family": m["family"], "period": m["period"],
            "scope": m["scope"], "statistic": m["statistic"],
            **{k: v for k, v in lab.items()},
            **{k: v for k, v in odd.items()},
            "odds_semantics": m["odds_semantics"],
            "settlement_rule": settlement_rule(m),
            "provider_semantic_notes": semantic_notes(m),
            "eligible_for_oos_modeling": model_ok and not m["context_only"],
            "eligible_for_hypothesis_generation": gen_ok,
            "eligible_for_market_comparison": gen_ok and odd["timestamped_pre_match_supported"],
            "failure_reason": "; ".join(fail) or None,
        })
    return {"registry_version": REGISTRY_VERSION, "provider": "thestatsapi",
            "derived_from_cache_scan": True,
            "n_finished_fixtures": len(data["fixtures"]),
            "n_stats_payloads_unambiguous": len(data["stats"]),
            "n_stats_payload_conflicts_excluded": data["n_stats_conflicts"],
            "thresholds": {"MIN_LABEL_COVERAGE": MIN_LABEL_COVERAGE,
                           "MAX_ONE_SIDED_NULL_SHARE": MAX_ONE_SIDED_NULL_SHARE,
                           "MIN_HALF_CONSISTENCY": MIN_HALF_CONSISTENCY,
                           "MIN_LABEL_ROWS": MIN_LABEL_ROWS},
            "eligibility_rules": {
                "eligible_for_oos_modeling": "label supported AND semantics verified AND not "
                                             "context-only",
                "eligible_for_hypothesis_generation":
                    "modeling-eligible AND a provider market exists in the raw captures for the "
                    "same statistic/scope/period (SAME), OR the pre-registered BOOKINGS proxy "
                    "exception: total yellow cards vs the provider 'total_cards' market, "
                    "flagged PROXY and never eligible for market comparison",
                "eligible_for_market_comparison":
                    "generation-eligible AND validated adapter AND quantity SAME AND "
                    "pre-kickoff timestamped captures exist"},
            "markets": entries}


def settlement_rule(m) -> str:
    q = {"GOALS": "goals", "CORNERS": "corner_kicks", "YELLOW_CARDS": "yellow_cards",
         "OFFSIDES": "offsides", "CARDS_YELLOW_PLUS_RED": "yellow_cards + red_cards",
         "BTTS": "home goals >= 1 AND away goals >= 1", "RESULT": "sign(home - away)"}[
        m["statistic"]]
    side = {"TOTAL": "home + away", "HOME_TEAM": "home", "AWAY_TEAM": "away"}[m["scope"]]
    if m["statistic"] in ("BTTS", "RESULT"):
        return f"{q} ({m['period']})"
    return f"OVER_x iff ({side} of {q}, {m['period']}) > x ; x is a half-line (no push)"


def semantic_notes(m) -> List[str]:
    n = []
    if m["statistic"] == "YELLOW_CARDS" and m["scope"] == "TOTAL" and m["period"] == "FULL_MATCH":
        n.append("provider-native yellow-card count; the provider 'total_cards' market's "
                 "counting rule (second yellow, reds, booking points) is unverified, so this "
                 "target is a PROXY and never compared with that market")
    if m["statistic"] == "CARDS_YELLOW_PLUS_RED":
        n.append("red_cards is mostly null with mixed zero encoding; yellow+red cannot be "
                 "settled safely (fail closed)")
    if m["statistic"] == "GOALS":
        n.append("full-match goals = fixture score home/away (regulation for league matches)")
    return n


def settle(market_id: str, line: Optional[float], fixture: Dict[str, Any],
           stats: Optional[Dict[str, Any]]) -> Optional[float]:
    """Deterministic historical label for a universe target. None (never a guess) when the
    provider value is missing. Only generation+modeling-eligible full-match markets."""
    sc = fixture.get("score") or {}
    h, a = sc.get("home"), sc.get("away")
    sd = (stats or {}).get("data") or {}

    def stat(key, group="overview"):
        v = [_cell(sd, group, key, "all", s) for s in ("home", "away")]
        return None if None in v else [float(x) for x in v]
    if market_id == "BTTS":
        return None if h is None or a is None else float(h >= 1 and a >= 1)
    qty = {"TOTAL_GOALS": None if h is None or a is None else h + a,
           "HOME_GOALS": h, "AWAY_GOALS": a}
    if market_id in qty:
        q = qty[market_id]
    elif market_id in ("TOTAL_CORNERS", "HOME_CORNERS", "AWAY_CORNERS"):
        v = stat("corner_kicks")
        q = None if v is None else {"TOTAL_CORNERS": v[0] + v[1], "HOME_CORNERS": v[0],
                                    "AWAY_CORNERS": v[1]}[market_id]
    elif market_id == "TOTAL_YELLOW_CARDS":
        v = stat("yellow_cards")
        q = None if v is None else v[0] + v[1]
    else:
        raise ValueError(f"{market_id} is not a settleable universe target")
    if q is None or line is None or float(line) % 1 != 0.5:
        return None
    return float(float(q) > float(line))
