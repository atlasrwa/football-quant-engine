#!/usr/bin/env python3
"""Book-disagreement analysis (Bet365 vs Betfair-exchange vs Pinnacle).

Measures how much the books DISAGREE on the same line, using de-vigged fair
probabilities. This needs NO outcomes/settlement — it is purely a property of
the odds — so it has immediate value: if books rarely disagree by more than the
~1pp threshold implied by Betfair's near-zero overround, then cross-book edge is
structurally small regardless of model quality.

For each (fixture, market, line) and each book we compute the de-vigged fair
probability of the OVER (or YES for BTTS) via proportional de-vig. We then report,
per market/line, the distribution of pairwise |fair_p_A - fair_p_B| differences:
mean, median, percentiles, max; the fraction exceeding the ~1pp threshold; and
whether disagreement is SYSTEMATIC (one book consistently higher — signed mean
far from zero relative to spread) or effectively random (signed mean ~ 0).

Reads the cached odds files written by pilotC_multibook_fetch. Zero API cost.
"""
from __future__ import annotations

import glob
import json
import os
from collections import defaultdict
from itertools import combinations

import numpy as np

CH = "/home/ubuntu/data/thestatsapi/championship"
OUT = "/home/ubuntu/data/results/book_disagreement.json"
BOOKS = ["bet365", "betfair-exchange", "pinnacle"]

# Overround threshold implied by Betfair (~1.1% pilot value): an edge must exceed
# roughly half the overround per side to be real. We report the fraction of book
# disagreements exceeding 1pp (0.01 in probability).
THRESHOLD_PP = 0.01

# Two-way markets we can de-vig directly from over/under (or yes/no for btts).
# Each entry: (market_key_in_cache, is_btts)
TWO_WAY_MARKETS = {
    "total_goals": False,
    "match_corners": False,
    "total_cards": False,
    "btts": True,
}


def devig(o, u):
    """Proportional de-vig -> (fair_p_over, overround). None if malformed."""
    if not o or not u:
        return None
    try:
        o, u = float(o), float(u)
    except (TypeError, ValueError):
        return None
    if o <= 1 or u <= 1:
        return None
    ro, ru = 1.0 / o, 1.0 / u
    s = ro + ru
    return ro / s, s - 1.0


def load_book_markets(mid, bk):
    f = f"{CH}/pilotC_odds_{mid}_{bk}.json"
    if not os.path.exists(f):
        return None
    try:
        d = json.load(open(f))
    except Exception:
        return None
    bks = d.get("data", {}).get("bookmakers", [])
    if bks and isinstance(bks[0], dict) and bks[0].get("markets"):
        return bks[0]["markets"]
    return None


def extract_fair_probs(markets, market_key, is_btts):
    """Return {line_str: (fair_p_over, overround)} for a market in one book."""
    out = {}
    node_root = markets.get(market_key, {})
    if is_btts:
        o = node_root.get("yes", {}).get("last_seen")
        u = node_root.get("no", {}).get("last_seen")
        dv = devig(o, u)
        if dv:
            out["yes"] = dv
        return out
    # over/under keyed by line
    for line_str, node in node_root.items():
        if not isinstance(node, dict):
            continue
        o = node.get("over", {}).get("last_seen")
        u = node.get("under", {}).get("last_seen")
        dv = devig(o, u)
        if dv:
            out[line_str] = dv
    return out


def _summary(diffs):
    a = np.array(diffs, dtype=float)
    return {
        "n": int(a.size),
        "mean_pp": round(float(np.mean(a)) * 100, 3),
        "median_pp": round(float(np.median(a)) * 100, 3),
        "p90_pp": round(float(np.percentile(a, 90)) * 100, 3),
        "p95_pp": round(float(np.percentile(a, 95)) * 100, 3),
        "p99_pp": round(float(np.percentile(a, 99)) * 100, 3),
        "max_pp": round(float(np.max(a)) * 100, 3),
        "frac_exceeding_1pp": round(float(np.mean(a > THRESHOLD_PP)), 4),
    }


def _signed_summary(signed):
    """Systematic vs random: signed mean relative to the spread of differences.

    We compute the signed difference (book_A_fair - book_B_fair). If the signed
    mean is large relative to its own std (|mean|/std, i.e. an effect-size-like
    ratio) AND large in absolute pp terms, the disagreement is SYSTEMATIC. If the
    signed mean is near zero it is effectively random noise around agreement.
    """
    a = np.array(signed, dtype=float)
    if a.size == 0:
        return None
    mean = float(np.mean(a))
    std = float(np.std(a)) or 1e-9
    ratio = abs(mean) / std
    systematic = (abs(mean) > 0.005) and (ratio > 0.3)
    return {
        "signed_mean_pp": round(mean * 100, 3),
        "signed_std_pp": round(std * 100, 3),
        "abs_mean_over_std": round(ratio, 3),
        "classification": "systematic" if systematic else "random-ish",
        "direction": ("A>B" if mean > 0 else "B>A") if systematic else "none",
    }


def main():
    # Collect fair probs: fair[(market,line)][book][mid] = fair_p
    fair = defaultdict(lambda: defaultdict(dict))
    overrounds = defaultdict(lambda: defaultdict(list))  # per (market,line) per book

    # discover fixture ids from cache filenames
    mids = set()
    for f in glob.glob(f"{CH}/pilotC_odds_*.json"):
        base = os.path.basename(f).replace("pilotC_odds_", "").replace(".json", "")
        for bk in BOOKS:
            if base.endswith("_" + bk):
                mids.add(base[: -(len(bk) + 1)])
    mids = sorted(mids)

    for mid in mids:
        for bk in BOOKS:
            markets = load_book_markets(mid, bk)
            if markets is None:
                continue
            for market_key, is_btts in TWO_WAY_MARKETS.items():
                probs = extract_fair_probs(markets, market_key, is_btts)
                for line_str, (fp, ovr) in probs.items():
                    fair[(market_key, line_str)][bk][mid] = fp
                    overrounds[(market_key, line_str)][bk].append(ovr)

    per_combo = {}
    pooled_abs = []
    for (market_key, line_str), by_book in sorted(fair.items()):
        combo_key = f"{market_key}@{line_str}"
        entry = {"market": market_key, "line": line_str, "pairs": {}, "overround_mean_pp": {}}
        # mean overround per book on this combo
        for bk in BOOKS:
            ovrs = overrounds[(market_key, line_str)].get(bk, [])
            if ovrs:
                entry["overround_mean_pp"][bk] = round(float(np.mean(ovrs)) * 100, 3)
        for a, b in combinations(BOOKS, 2):
            common = set(by_book.get(a, {})) & set(by_book.get(b, {}))
            if len(common) < 5:
                continue
            abs_diffs, signed = [], []
            for mid in common:
                da = by_book[a][mid] - by_book[b][mid]
                abs_diffs.append(abs(da))
                signed.append(da)
            pooled_abs.extend(abs_diffs)
            entry["pairs"][f"{a}__vs__{b}"] = {
                "abs": _summary(abs_diffs),
                "systematic_vs_random": _signed_summary(signed),
            }
        if entry["pairs"]:
            per_combo[combo_key] = entry

    out = {
        "analysis_date": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "STATUS": "MEASUREMENT ONLY — book-vs-book fair-probability disagreement. "
                  "No model, no outcomes, no edge claim.",
        "method": {
            "de_vig": "proportional (multiplicative) overround removal, last_seen odds",
            "disagreement": "|fair_p_book_A - fair_p_book_B| per fixture, per market/line",
            "threshold_pp": THRESHOLD_PP * 100,
            "books": BOOKS,
            "systematic_rule": "systematic if |signed_mean|>0.5pp AND "
                               "|signed_mean|/std>0.3, else random-ish",
        },
        "n_fixtures_with_any_odds": len(mids),
        "pooled_abs_disagreement": _summary(pooled_abs) if pooled_abs else None,
        "interpretation": (
            "If disagreements rarely exceed ~1pp, cross-book edge is structurally "
            "small regardless of model quality. Betfair's ~1.1% overround means the "
            "required edge is ~1pp; disagreements below that leave little room."),
        "per_combo": per_combo,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=2, default=str)

    print("=== Book disagreement (fair-prob, de-vigged) ===")
    print(f"fixtures with odds: {len(mids)}")
    if out["pooled_abs_disagreement"]:
        print("pooled:", json.dumps(out["pooled_abs_disagreement"]))
    for combo, e in per_combo.items():
        for pair, s in e["pairs"].items():
            ab = s["abs"]; sv = s["systematic_vs_random"]
            print(f"  {combo:22s} {pair:34s} n={ab['n']:3d} "
                  f"mean={ab['mean_pp']:.2f}pp median={ab['median_pp']:.2f}pp "
                  f"max={ab['max_pp']:.2f}pp >1pp={ab['frac_exceeding_1pp']:.0%} "
                  f"[{sv['classification']}]")
    print("saved", OUT)
    return out


if __name__ == "__main__":
    main()
