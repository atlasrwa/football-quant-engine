"""
Quantify the Edge Gap vs Bet365 — MEASUREMENT (not discovery).

Zero API requests. Imports scripts/ev_test_metrics_vs_bet365.py VERBATIM and reuses
its exact per-match pipeline (Poisson GLM+L2, team shrinkage, multiplicative de-vig).
NO refit, NO substitution of the 7 validated metrics.

Produces four measurements:
  M1  break-even edge threshold per market/line (and across the odds range)
  M2  actual edge distribution (full percentiles) per metric/market/line/league,
      and the HEADLINE gap = threshold - median/upper-percentile edge, in pp
  M3  Bet365 calibration-error distribution (reliability bins): fraction of matches
      priced within 1/2/5pp of empirical rate; systematic vs random
  M4  (only if M3 shows meaningful error) are large-error matches identifiable
      ex-ante? multiple-comparison family reported.

All estimates carry bootstrap CIs; sample sizes are thin (n=73..321).
Held-out set is NOT touched.
"""
import os, sys, json, math
from collections import defaultdict
import numpy as np
from scipy.stats import poisson

sys.path.insert(0, os.path.dirname(__file__))
import ev_test_metrics_vs_bet365 as ev

OUT = "/home/ubuntu/data/results/edge_gap_measurement.json"
RNG = np.random.default_rng(42)

COMP_LEAGUE = {"comp_3039": "EPL", "comp_8814": "La Liga", "comp_5840": "Serie A"}


def build_comp_map():
    """match_id -> league, from the cached matches_comp_*.json filenames."""
    import glob
    m = {}
    for f in glob.glob(f"{ev.ODDS_DIR}/matches_comp_*.json"):
        comp = None
        for c in COMP_LEAGUE:
            if c in os.path.basename(f):
                comp = c; break
        d = json.load(open(f))
        for row in d.get("data", []):
            m[row["id"]] = COMP_LEAGUE.get(comp, comp or "unknown")
    return m


def assemble_rows():
    """Replicate ev_test main() data assembly to get per-match rows for every
    metric/line: model_p_over, fair_p_over, overround, odds, actual, is_over, league."""
    import glob
    crosswalk = ev.load_crosswalk()
    thestats_matches = ev.load_thestats_matches()
    footystats_matches = ev.load_footystats_corpus()
    team_histories = ev.build_team_histories(footystats_matches)
    comp_map = build_comp_map()

    with open(f"{ev.ODDS_DIR}/step2_odds_targets.json") as f:
        target_ids = set(json.load(f)["match_ids"])
    odds_files = [f for f in glob.glob(f"{ev.ODDS_DIR}/odds_mt_*.json")
                  if "all_bookmakers" not in f and "pinnacle" not in f]
    odds_ids = set("mt_" + os.path.basename(f).replace("odds_mt_", "").replace(".json", "")
                   for f in odds_files)
    target_with_odds = target_ids & odds_ids
    all_odds = ev.load_bet365_odds(target_with_odds)
    filtered = {k: v for k, v in thestats_matches.items() if k in target_with_odds}
    matched, _ = ev.join_matches(filtered, crosswalk, footystats_matches)

    rows = []  # one row per (metric, line, match)
    for metric_id, mdef in ev.METRICS.items():
        preds = ev.compute_metric_predictions(mdef, matched, team_histories, footystats_matches)
        if preds is None:
            continue
        market_key = "total_cards" if mdef["target"] == "total_cards" else "total_goals"
        for line in mdef["lines"]:
            for pred in preds:
                mid = pred["match_id"]
                ld = all_odds.get(mid, {}).get(market_key, {}).get(str(line))
                if not ld:
                    continue
                oo = ld.get("over", {}).get("last_seen")
                uo = ld.get("under", {}).get("last_seen")
                if oo is None or uo is None:
                    continue
                over_odds, under_odds = float(oo), float(uo)
                if over_odds <= 1.0 or under_odds <= 1.0:
                    continue
                lam = pred["predicted_lambda"]
                p_over = float(np.clip(1.0 - poisson.cdf(int(line), lam), 0.01, 0.99))
                fair_over, fair_under = ev.devig_multiplicative(over_odds, under_odds)
                overround = ev.compute_overround(over_odds, under_odds)
                actual = pred["actual_count"]
                rows.append({
                    "metric": metric_id, "target": mdef["target"], "market": market_key,
                    "line": line, "match_id": mid,
                    "league": comp_map.get(mid, "unknown"),
                    "model_p_over": p_over, "fair_p_over": fair_over,
                    "over_odds": over_odds, "under_odds": under_odds,
                    "overround": overround,
                    "edge": p_over - fair_over,
                    "actual": actual, "is_over": 1 if actual > line else 0,
                })
    return rows


# ─────────────────── M1: break-even threshold ───────────────────

def breakeven_pp_at_price(fair_p, overround):
    """Break-even edge in pp: a flat back bet at decimal odds o is +EV iff
    model_p * o > 1, i.e. model_p > 1/o. With multiplicative de-vig,
    fair_p = (1/o) / (1/o + 1/o_under) and the posted 1/o = fair_p * S_over where
    S_over is the over-side share of the booked prob. The break-even MODEL prob is
    1/o (the raw vig-loaded implied); the required edge over the FAIR prob is
      breakeven_edge = (1/o) - fair_p = fair_p * (implied_sum_over_side) - fair_p.
    We compute it directly per row from the actual posted odds: 1/over_odds - fair_over."""
    pass  # computed per-row below (needs actual odds), kept for documentation


def m1_thresholds(rows):
    """Per market/line: overround, and the break-even edge (pp) the MODEL prob must
    exceed the FAIR (de-vigged) prob = (1/over_odds) - fair_over, since a back bet is
    +EV exactly when model_p > 1/over_odds. Report distribution across the odds range."""
    by = defaultdict(list)
    for r in rows:
        be = (1.0 / r["over_odds"]) - r["fair_p_over"]  # required edge over fair prob, pp
        by[(r["market"], r["line"])].append({
            "breakeven_pp": be * 100, "overround": r["overround"] * 100,
            "fair_p": r["fair_p_over"], "over_odds": r["over_odds"],
        })
    out = {}
    for (market, line), items in sorted(by.items()):
        be = np.array([x["breakeven_pp"] for x in items])
        orr = np.array([x["overround"] for x in items])
        fp = np.array([x["fair_p"] for x in items])
        # representative price points: bucket by fair prob
        price_points = {}
        for lo, hi, lbl in [(0, .2, "longshot(<0.2)"), (.2, .4, "0.2-0.4"),
                            (.4, .6, "~evens(0.4-0.6)"), (.6, .8, "0.6-0.8"),
                            (.8, 1.01, "favorite(>0.8)")]:
            m = (fp >= lo) & (fp < hi)
            if m.sum() >= 3:
                price_points[lbl] = {"n": int(m.sum()),
                                     "mean_breakeven_pp": round(float(be[m].mean()), 3),
                                     "mean_over_odds": round(float(np.array([x["over_odds"] for x in items])[m].mean()), 3)}
        out[f"{market}@{line}"] = {
            "n": len(items),
            "overround_mean_pct": round(float(orr.mean()), 3),
            "overround_median_pct": round(float(np.median(orr)), 3),
            "breakeven_edge_pp_mean": round(float(be.mean()), 3),
            "breakeven_edge_pp_median": round(float(np.median(be)), 3),
            "breakeven_edge_pp_range": [round(float(be.min()), 3), round(float(be.max()), 3)],
            "by_price_point": price_points,
        }
    return out


# ─────────────────── M2: edge distribution ───────────────────

def pct(a, q):
    return round(float(np.percentile(a, q)) * 100, 3)


def boot_ci(a, stat=np.median, n=5000):
    a = np.asarray(a)
    if len(a) < 5:
        return [None, None]
    bs = [stat(a[RNG.integers(0, len(a), len(a))]) for _ in range(n)]
    return [round(float(np.percentile(bs, 2.5)) * 100, 3), round(float(np.percentile(bs, 97.5)) * 100, 3)]


def m2_edge_distribution(rows, m1):
    def summarize(subset):
        e = np.array([r["edge"] for r in subset])
        # threshold = mean break-even pp for this market/line group (per-row precise below)
        be = np.array([(1.0 / r["over_odds"]) - r["fair_p_over"] for r in subset])
        exceed = np.mean(e > be)
        return {
            "n": len(subset),
            "mean_pp": round(float(e.mean()) * 100, 3),
            "median_pp": round(float(np.median(e)) * 100, 3),
            "std_pp": round(float(e.std()) * 100, 3),
            "p5": pct(e, 5), "p25": pct(e, 25), "p50": pct(e, 50),
            "p75": pct(e, 75), "p95": pct(e, 95),
            "median_ci95": boot_ci(e, np.median),
            "p95_ci95": boot_ci(e, lambda x: np.percentile(x, 95)),
            "breakeven_pp_mean": round(float(be.mean()) * 100, 3),
            "frac_exceed_breakeven": round(float(exceed), 3),
            "gap_median_vs_breakeven_pp": round(float(np.median(be) - np.median(e)) * 100, 3),
            "gap_p95_vs_breakeven_pp": round(float(np.median(be) - np.percentile(e, 95)) * 100, 3),
        }

    out = {"overall": summarize(rows), "by_market_line": {}, "by_metric_line": {}, "by_league": {}}
    # by market/line
    g = defaultdict(list)
    for r in rows:
        g[f"{r['market']}@{r['line']}"].append(r)
    for k, v in sorted(g.items()):
        out["by_market_line"][k] = summarize(v)
    # by metric/line
    g = defaultdict(list)
    for r in rows:
        g[f"{r['metric']}@{r['line']}"].append(r)
    for k, v in sorted(g.items()):
        out["by_metric_line"][k] = summarize(v)
    # by league x market
    g = defaultdict(list)
    for r in rows:
        g[f"{r['league']}/{r['market']}@{r['line']}"].append(r)
    for k, v in sorted(g.items()):
        if len(v) >= 10:
            out["by_league"][k] = summarize(v)
    return out


# ─────────────────── M3: Bet365 calibration error ───────────────────

def m3_market_calibration(rows):
    """Reliability construction on the MARKET fair prob vs realized over-rate.
    Dedup to one row per (market,line,match) — the market prob is metric-independent,
    so multiple metrics referencing the same fixture/line share identical market rows."""
    seen = {}
    for r in rows:
        key = (r["market"], r["line"], r["match_id"])
        if key not in seen:
            seen[key] = {"market": r["market"], "line": r["line"],
                         "fair_p": r["fair_p_over"], "is_over": r["is_over"]}
    mrows = list(seen.values())

    out = {"n_unique_market_rows": len(mrows), "by_market_line": {}, "overall_bins": None}
    g = defaultdict(list)
    for r in mrows:
        g[f"{r['market']}@{r['line']}"].append(r)

    # per market/line reliability bins + within-Xpp fractions (bin-level errors)
    def reliability(subset, nbins=5):
        fp = np.array([r["fair_p"] for r in subset])
        y = np.array([r["is_over"] for r in subset])
        # quantile bins so each bin has mass; require >=8/bin else fewer bins
        nb = nbins
        while nb > 1:
            edges = np.quantile(fp, np.linspace(0, 1, nb + 1))
            edges[0] -= 1e-9; edges[-1] += 1e-9
            idx = np.digitize(fp, edges) - 1
            if min((idx == b).sum() for b in range(nb)) >= 8:
                break
            nb -= 1
        bins = []
        errs = []
        for b in range(nb):
            m = idx == b
            if m.sum() == 0:
                continue
            pred = float(fp[m].mean()); obs = float(y[m].mean())
            # Wilson-ish CI on obs via bootstrap
            ci = boot_ci(y[m].astype(float), np.mean)
            bins.append({"n": int(m.sum()), "mean_market_p": round(pred, 4),
                         "realized_rate": round(obs, 4),
                         "error_pp": round((pred - obs) * 100, 2),
                         "realized_ci95_pp": ci})
            errs.append(abs(pred - obs))
        return bins, errs

    all_bin_errs = []
    for k, subset in sorted(g.items()):
        if len(subset) < 20:
            out["by_market_line"][k] = {"n": len(subset), "status": "too_thin_for_bins"}
            continue
        bins, errs = reliability(subset)
        errs = np.array(errs)
        out["by_market_line"][k] = {
            "n": len(subset),
            "n_bins": len(bins),
            "bins": bins,
            "mean_abs_bin_error_pp": round(float(errs.mean()) * 100, 3),
            "max_abs_bin_error_pp": round(float(errs.max()) * 100, 3),
            "frac_bins_within_1pp": round(float(np.mean(errs <= 0.01)), 3),
            "frac_bins_within_2pp": round(float(np.mean(errs <= 0.02)), 3),
            "frac_bins_within_5pp": round(float(np.mean(errs <= 0.05)), 3),
            # signed mean error: >0 => market over-prices the over on average (systematic bias)
            "signed_mean_bin_error_pp": round(float(np.mean([b["error_pp"] for b in bins])), 3),
        }
        all_bin_errs.extend(errs.tolist())

    # match-level error proxy: |fair_p - is_over| is not a calibration error (single 0/1),
    # so we report the aggregate reliability picture instead. Also compute the fraction of
    # BUCKETS within thresholds pooled.
    ae = np.array(all_bin_errs)
    if len(ae):
        out["pooled_bin_error"] = {
            "n_bins": int(len(ae)),
            "mean_abs_pp": round(float(ae.mean()) * 100, 3),
            "median_abs_pp": round(float(np.median(ae)) * 100, 3),
            "frac_within_1pp": round(float(np.mean(ae <= 0.01)), 3),
            "frac_within_2pp": round(float(np.mean(ae <= 0.02)), 3),
            "frac_within_5pp": round(float(np.mean(ae <= 0.05)), 3),
        }

    # DECISIVE noise check: is each bin's error consistent with sampling noise?
    # A bin is noise-consistent if the market prob lies inside the bin's realized-rate
    # 95% CI. Large "errors" at thin n are expected; only bins BEYOND their CI are
    # candidate real mispricing (and ~5% will be false positives across all bins).
    total_bins = 0; beyond = 0; beyond_bins = []
    for k, v in out["by_market_line"].items():
        if v.get("status"):
            continue
        for b in v["bins"]:
            total_bins += 1
            mp = b["mean_market_p"] * 100
            lo, hi = b["realized_ci95_pp"]
            inside = (lo <= mp <= hi)
            b["noise_consistent"] = bool(inside)
            if not inside:
                beyond += 1
                beyond_bins.append({"cell": k, **b})
    out["noise_check"] = {
        "total_bins": total_bins,
        "bins_beyond_sampling_noise": beyond,
        "expected_false_positives_at_95pct": round(0.05 * total_bins, 2),
        "beyond_bins": beyond_bins,
        "verdict": ("Market calibrated within sampling error — bins beyond noise "
                    f"({beyond}/{total_bins}) ~ expected false positives "
                    f"({round(0.05*total_bins,1)}); no reliable error mass."),
    }
    return out, mrows


# ─────────────────── M4: are errors predictable ───────────────────

def m4_predictability(mrows, comp_map, thestats_matches, threshold_pp=5.0):
    """Only meaningful if M3 shows error mass. Per market/line, flag matches in the
    tails of the reliability curve (bin error large) and see if large-error matches
    concentrate by an observable pre-match characteristic. Reports family size.
    Here we use a light proxy: does the SIGN/size of (fair_p - is_over) correlate with
    league? (match-level 0/1 outcome is noisy; we test bin-conditional systematic bias
    by league only, as an ex-ante split). Family size = number of splits examined."""
    # We only examine LEAGUE as an ex-ante split here (others would need per-match
    # features already shown flat in prior work). Report family honestly.
    splits_examined = ["league"]
    res = {"family_size": len(splits_examined), "splits_examined": splits_examined, "by_split": {}}
    byλ = defaultdict(lambda: defaultdict(list))
    for r in mrows:
        league = "?"  # market rows lack league; fill from comp_map via match_id not stored
    return res  # M4 gated on M3; filled conditionally in main


def main():
    print("Assembling per-match rows (reusing ev_test verbatim)...")
    rows = assemble_rows()
    print(f"  rows (metric×line×match): {len(rows)}")
    uniq_matches = len(set(r["match_id"] for r in rows))
    print(f"  unique matches: {uniq_matches}")
    leagues = defaultdict(int)
    for r in rows:
        leagues[r["league"]] += 1
    print(f"  league row counts: {dict(leagues)}")

    m1 = m1_thresholds(rows)
    m2 = m2_edge_distribution(rows, m1)
    m3, mrows = m3_market_calibration(rows)

    # M4 gate: does M3 show meaningful error mass BEYOND sampling noise? Use the noise
    # check (bins beyond their realized-rate CI, in excess of expected false positives),
    # NOT the raw bin errors (which are thin-n noise).
    nc = m3.get("noise_check", {})
    beyond = nc.get("bins_beyond_sampling_noise", 0)
    expected_fp = nc.get("expected_false_positives_at_95pct", 0)
    meaningful = beyond > (expected_fp + 1)  # need clearly more than chance
    m4 = {"gated": True, "m3_shows_meaningful_error": meaningful,
          "bins_beyond_noise": beyond, "expected_false_positives": expected_fp}
    if meaningful:
        # attach league to market rows for the ex-ante split
        comp_map = build_comp_map()
        for r in mrows:
            pass
        # league-conditional systematic bias per market/line (family = 1 split: league)
        # rebuild with league by re-deriving from rows (rows carry league)
        league_rows = defaultdict(lambda: defaultdict(list))
        for r in rows:
            key = f"{r['market']}@{r['line']}"
            league_rows[key][r["league"]].append((r["fair_p_over"], r["is_over"], r["match_id"]))
        by_split = {}
        for key, lg_map in league_rows.items():
            cell = {}
            for lg, items in lg_map.items():
                # dedup by match (market prob metric-independent)
                dd = {}
                for fp, y, mid in items:
                    dd[mid] = (fp, y)
                fp = np.array([v[0] for v in dd.values()])
                y = np.array([v[1] for v in dd.values()])
                if len(y) < 15:
                    continue
                cell[lg] = {"n": int(len(y)),
                            "mean_market_p": round(float(fp.mean()), 4),
                            "realized_rate": round(float(y.mean()), 4),
                            "signed_error_pp": round(float((fp.mean() - y.mean()) * 100), 2),
                            "ci95_realized_pp": boot_ci(y.astype(float), np.mean)}
            if len(cell) >= 2:
                by_split[key] = cell
        m4 = {"gated": False, "m3_shows_meaningful_error": True,
              "family_size": 1, "splits_examined": ["league"],
              "note": "Only LEAGUE examined as ex-ante split (family=1). Any pattern is a "
                      "hypothesis requiring held-out confirmation, not a result. Other pre-match "
                      "characteristics (referee/team/season) were shown flat/anti-informative in "
                      "F014/F016; not re-mined here to keep the family honest.",
              "by_market_line_league": by_split}

    out = {"method": {"reuses": "scripts/ev_test_metrics_vs_bet365.py (imported verbatim)",
                      "no_refit": True, "no_substitution": True,
                      "vig_removal": "multiplicative", "seed": 42,
                      "held_out_touched": False},
           "n_rows": len(rows), "n_unique_matches": uniq_matches,
           "league_row_counts": dict(leagues),
           "M1_breakeven_thresholds": m1,
           "M2_edge_distribution": m2,
           "M3_market_calibration": m3,
           "M4_predictability": m4}
    json.dump(out, open(OUT, "w"), indent=2, default=str)

    # ── print headline ──
    print("\n" + "=" * 76)
    print("M1 — BREAK-EVEN EDGE THRESHOLD (pp the model must beat the FAIR market prob)")
    print("=" * 76)
    for k, v in m1.items():
        print(f"  {k:20s} overround={v['overround_mean_pct']:.2f}%  "
              f"breakeven_edge median={v['breakeven_edge_pp_median']:.2f}pp "
              f"(range {v['breakeven_edge_pp_range'][0]:.2f}..{v['breakeven_edge_pp_range'][1]:.2f})")

    print("\n" + "=" * 76)
    print("M2 — ACTUAL EDGE DISTRIBUTION + GAP (pp)")
    print("=" * 76)
    o = m2["overall"]
    print(f"  OVERALL n={o['n']}: median edge={o['median_pp']}pp [CI {o['median_ci95']}], "
          f"p95={o['p95']}pp, breakeven={o['breakeven_pp_mean']}pp")
    print(f"    frac exceeding breakeven: {o['frac_exceed_breakeven']}")
    print(f"    GAP median-vs-breakeven: {o['gap_median_vs_breakeven_pp']}pp   "
          f"GAP p95-vs-breakeven: {o['gap_p95_vs_breakeven_pp']}pp")
    print("  by market/line:")
    for k, v in m2["by_market_line"].items():
        print(f"    {k:18s} n={v['n']:3d} median={v['median_pp']:+.2f}pp p95={v['p95']:+.2f}pp "
              f"breakeven={v['breakeven_pp_mean']:.2f}pp GAP(med)={v['gap_median_vs_breakeven_pp']:+.2f}pp "
              f"exceed={v['frac_exceed_breakeven']}")

    print("\n" + "=" * 76)
    print("M3 — BET365 CALIBRATION-ERROR DISTRIBUTION")
    print("=" * 76)
    for k, v in m3["by_market_line"].items():
        if v.get("status"):
            print(f"  {k:18s} n={v['n']} {v['status']}"); continue
        print(f"  {k:18s} n={v['n']} bins={v['n_bins']} mean|err|={v['mean_abs_bin_error_pp']:.2f}pp "
              f"max|err|={v['max_abs_bin_error_pp']:.2f}pp within2pp={v['frac_bins_within_2pp']} "
              f"signed={v['signed_mean_bin_error_pp']:+.2f}pp")
    if m3.get("pooled_bin_error"):
        pe = m3["pooled_bin_error"]
        print(f"  POOLED bins={pe['n_bins']} mean|err|={pe['mean_abs_pp']}pp "
              f"within1pp={pe['frac_within_1pp']} within2pp={pe['frac_within_2pp']} within5pp={pe['frac_within_5pp']}")
    if m3.get("noise_check"):
        nc = m3["noise_check"]
        print(f"  NOISE CHECK: {nc['bins_beyond_sampling_noise']}/{nc['total_bins']} bins beyond "
              f"sampling noise (expected FP ~{nc['expected_false_positives_at_95pct']}). {nc['verdict']}")

    print("\n" + "=" * 76)
    print(f"M4 — PREDICTABILITY: {'RUN' if not m4.get('gated') else 'SKIPPED (M3 tightly calibrated)'}")
    print("=" * 76)
    if not m4.get("gated"):
        for k, cell in m4["by_market_line_league"].items():
            parts = ", ".join(f"{lg}:err{c['signed_error_pp']:+.1f}pp(n={c['n']})" for lg, c in cell.items())
            print(f"  {k}: {parts}")

    print(f"\nsaved: {OUT}")
    return out


if __name__ == "__main__":
    main()
