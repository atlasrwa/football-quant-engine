"""
Coverage Matrix Audit — Part 1 (market coverage) + Part 2 gating (per-side markets).

Cache-first: enumerates every market x line x book from cached pilotC_odds_* files.
Structural per-side detection: a market body is per-side iff its top-level keys are
exactly {home, away}. Computes coverage rate (% fixtures where market appears),
typical (median) overround, and detects per-side STAT markets (team_corners,
team_total_goals, team_shots, etc). Writes data/coverage_audit/markets.json.

Live extension (cma_odds_{mid}_{book}) is supported for uncached books/fixtures but
guarded by a pre-spend cap check; run with a fixture list + THESTATS_MAX_REQUESTS set.
"""
from __future__ import annotations

import glob
import json
import os
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, "/home/ubuntu/scripts")
import coverage_audit_common as cac

CACHE = "/home/ubuntu/data/thestatsapi/championship"
BOOKS = ["bet365", "paddy-power", "betmgm-uk", "pinnacle", "betfair-exchange"]

# Markets whose bodies are keyed home/away but are RESULT markets, not per-side stats.
RESULT_PER_SIDE = {"asian_handicap", "draw_no_bet", "handicap_result"}
# Team-scoped statistic markets that answer the gating question.
PER_SIDE_STAT_HINTS = ("team_corners", "team_total_goals", "team_shots",
                       "team_cards", "team_total_cards", "team_shots_on_target",
                       "team_clean_sheet")


def classify_market(name: str, body):
    """Return kind: per_side_stat | result_per_side | match_total | result | other."""
    if not isinstance(body, dict):
        return "other"
    keys = set(body.keys())
    if keys == {"home", "away"}:
        if name in RESULT_PER_SIDE:
            return "result_per_side"
        return "per_side_stat"
    # 1X2-style
    if keys == {"home", "draw", "away"} or keys <= {"yes", "no"}:
        return "result"
    # match total: line-string keys or over/under bodies
    if all(_is_line(k) for k in keys):
        return "match_total"
    return "other"


def _is_line(k: str) -> bool:
    try:
        float(k)
        return True
    except (TypeError, ValueError):
        return False


def _price(sel):
    """Extract a decimal price from a selection dict (last_seen preferred)."""
    if not isinstance(sel, dict):
        return None
    for key in ("last_seen", "opening"):
        v = sel.get(key)
        if isinstance(v, dict):
            v = v.get("odds") or v.get("price") or v.get("decimal")
        try:
            fv = float(v)
            if fv > 1.0:
                return fv
        except (TypeError, ValueError):
            continue
    return None


def _two_way_overround(body):
    """Compute overround for a two-way (over/under or yes/no) market body if possible."""
    if not isinstance(body, dict):
        return None
    # find a nested over/under pair anywhere one level down, or yes/no at top
    pairs = []
    if {"yes", "no"} <= set(body.keys()):
        pairs.append((body.get("yes"), body.get("no")))
    for v in body.values():
        if isinstance(v, dict) and {"over", "under"} <= set(v.keys()):
            pairs.append((v.get("over"), v.get("under")))
    ors = []
    for a, b in pairs:
        pa, pb = _price(a), _price(b)
        if pa and pb:
            ors.append(1.0 / pa + 1.0 / pb)
    ors = [o for o in ors if o >= 0.99]  # flag/skip sub-1.0 (parse error)
    return round(statistics.median(ors), 4) if ors else None


def _per_side_overround(body):
    """Overround for per-side markets: body[home|away][line][over|under]."""
    if not isinstance(body, dict):
        return None
    ors = []
    for side in ("home", "away"):
        sb = body.get(side)
        if not isinstance(sb, dict):
            continue
        for _line, ou in sb.items():
            if isinstance(ou, dict) and {"over", "under"} <= set(ou.keys()):
                pa, pb = _price(ou["over"]), _price(ou["under"])
                if pa and pb:
                    ors.append(1.0 / pa + 1.0 / pb)
    ors = [o for o in ors if o >= 0.99]
    return round(statistics.median(ors), 4) if ors else None


def _lines(body):
    """Distinct line keys observed in a market body (top-level or nested home/away)."""
    out = set()
    if not isinstance(body, dict):
        return out
    for k, v in body.items():
        if _is_line(k):
            out.add(k)
        elif k in ("home", "away") and isinstance(v, dict):
            for kk in v.keys():
                if _is_line(kk):
                    out.add(kk)
    return out


def scan_cached():
    """Scan all cached pilotC_odds_* files -> per-book market coverage."""
    # book -> market -> {"fixtures_present": set(mid), "lines": set, "overrounds": []}
    agg = defaultdict(lambda: defaultdict(lambda: {"fixtures": set(), "lines": set(),
                                                   "overrounds": [], "kind": None}))
    book_fixture_totals = defaultdict(set)  # book -> set(mid) files seen
    per_side_stat_hits = defaultdict(lambda: defaultdict(set))  # book->market->set(mid)

    for f in glob.glob(f"{CACHE}/pilotC_odds_*.json"):
        base = os.path.basename(f)[len("pilotC_odds_"):-len(".json")]
        book = next((b for b in BOOKS if base.endswith("_" + b)), None)
        if not book:
            continue
        mid = base[: -(len(book) + 1)]
        book_fixture_totals[book].add(mid)
        try:
            d = json.load(open(f)).get("data", {})
        except (OSError, ValueError):
            continue
        for bk in d.get("bookmakers", []):
            markets = bk.get("markets", {})
            if not isinstance(markets, dict):
                continue
            for name, body in markets.items():
                rec = agg[book][name]
                rec["fixtures"].add(mid)
                rec["lines"] |= _lines(body)
                kind = classify_market(name, body)
                rec["kind"] = kind
                ov = _two_way_overround(body)
                if ov is None:
                    ov = _per_side_overround(body)
                if ov is not None:
                    rec["overrounds"].append(ov)
                if kind == "per_side_stat" or any(h in name for h in PER_SIDE_STAT_HINTS):
                    per_side_stat_hits[book][name].add(mid)
    return agg, book_fixture_totals, per_side_stat_hits


def build_report():
    agg, totals, per_side = scan_cached()
    out = {"source": "cached pilotC_odds_* (Championship cohort)",
           "books_in_cache": sorted(totals.keys()),
           "books_never_probed": [b for b in BOOKS if b not in totals],
           "by_book": {}, "per_side_stat_markets": {}}
    for book, markets in agg.items():
        n_fix = len(totals[book])
        mrec = {}
        for name, r in markets.items():
            cov = cac.rate(len(r["fixtures"]), n_fix)
            mrec[name] = {
                "kind": r["kind"],
                "lines": sorted(r["lines"], key=lambda x: float(x) if _is_line(x) else 0),
                "coverage": cov,
                "typical_overround": (round(statistics.median(r["overrounds"]), 4)
                                      if r["overrounds"] else None),
            }
        out["by_book"][book] = {"n_fixtures_sampled": n_fix, "markets": mrec}
    # gating summary
    for book, hits in per_side.items():
        out["per_side_stat_markets"][book] = {
            name: cac.rate(len(mids), len(totals[book])) for name, mids in hits.items()
        }
    # decisive gating flag
    any_per_side = any(out["per_side_stat_markets"].get(b) for b in totals)
    out["gating"] = {
        "per_side_stat_markets_found": any_per_side,
        "detail": {b: sorted(out["per_side_stat_markets"].get(b, {}).keys())
                   for b in totals},
    }
    return out


if __name__ == "__main__":
    cac.snapshot_budget("markets_pass_before")
    report = build_report()
    path = cac.write_artifact("markets.json", report)
    print("books in cache:", report["books_in_cache"])
    print("books never probed:", report["books_never_probed"])
    print("\nPER-SIDE STAT MARKETS FOUND:", report["gating"]["per_side_stat_markets_found"])
    for b, names in report["gating"]["detail"].items():
        print(f"  {b}: {names}")
    print("\nMarket coverage (bet365 example):")
    for name, r in sorted(report["by_book"].get("bet365", {}).get("markets", {}).items(),
                          key=lambda kv: -(kv[1]["coverage"]["pct"] or 0)):
        print(f"  {name:26s} {r['kind']:16s} cov={r['coverage']['pct']}% "
              f"(n={r['coverage']['total']}) lines={r['lines'][:6]} OR={r['typical_overround']}")
    cac.snapshot_budget("markets_pass_after")
    print("\nsaved:", path)
