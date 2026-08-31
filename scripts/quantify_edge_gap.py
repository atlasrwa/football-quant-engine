"""
Quantify the Edge Gap — measurement only, zero API calls.

Reuses the VALIDATED pipeline in ev_test_metrics_vs_bet365.py verbatim:
  - The 7 metric definitions (METRICS dict) exactly as defined
  - The same Poisson GLM + L2 + team shrinkage model (no refit of a different
    model, no substitution)
  - The same multiplicative de-vig
It does NOT change any metric, model, or config. It only adds measurements on
top of the per-match probabilities/outcomes the validated pipeline produces:

  M1  Break-even edge threshold per market/line (analytic, from odds)
  M2  Full actual edge distribution (percentiles) + fraction over threshold
      + the gap (median / upper-percentile actual edge vs threshold)
  M3  Bet365 calibration-error distribution via reliability-curve binning
  M4  (conditional) Are large-error matches identifiable ex-ante?

All data is cached. The odds sample is the 2024/25 season (discovery/older
season, index 1) — NOT the held-out 2025/26 season (index 0). Nothing here
reads the held-out set.
"""

import json
import glob
import os
from collections import defaultdict

import numpy as np
from scipy.stats import poisson, norm, binomtest

# Import the validated pipeline verbatim.
import ev_test_metrics_vs_bet365 as ev

BASE_DIR = '/home/ubuntu'
ODDS_DIR = f'{BASE_DIR}/data/thestatsapi/cache'
OUT_PATH = f'{BASE_DIR}/data/results/edge_gap_measurement.json'

RNG = np.random.default_rng(20260830)
N_BOOT = 10000


# ═══════════════════════════════════════════════════════════════
# M1: BREAK-EVEN EDGE THRESHOLD (analytic)
# ═══════════════════════════════════════════════════════════════
# A flat-stake bet on the OVER at decimal odds O has expected value
#     EV = p_model * O - 1
# Break-even (EV = 0) requires  p_model = 1 / O.
# The market's *vig-adjusted* (fair) probability is p_fair.
# The required edge is how far p_model must exceed p_fair to reach break-even:
#     required_edge(O) = 1/O - p_fair
# With multiplicative de-vig on a two-way market, p_fair = (1/O) / S where
# S = 1/O + 1/O_under = 1 + overround. So:
#     required_edge = 1/O - (1/O)/S = (1/O) * (1 - 1/S) = (1/O) * (overround / S)
# i.e. you must overcome your side's share of the vig. This depends on the
# odds level, so we report it across representative price points.

def required_edge_from_odds(over_odds, under_odds):
    """Break-even edge in probability points for backing the OVER side."""
    raw_over = 1.0 / over_odds
    raw_under = 1.0 / under_odds
    S = raw_over + raw_under              # 1 + overround
    p_fair = raw_over / S
    p_breakeven = 1.0 / over_odds         # p_model needed for EV=0
    return p_breakeven - p_fair


def measurement_1(per_line_odds):
    """per_line_odds: {market_line: list of (over_odds, under_odds)}"""
    out = {}
    # Representative price points for the "varies by odds level" report.
    # For a symmetric two-way market we hold overround fixed at the market
    # mean and vary the OVER price to show the threshold curve.
    for key, pairs in per_line_odds.items():
        overs = np.array([o for o, u in pairs])
        unders = np.array([u for o, u in pairs])
        overrounds = 1.0 / overs + 1.0 / unders - 1.0
        req = np.array([required_edge_from_odds(o, u) for o, u in pairs])

        mean_over = float(np.mean(overrounds))
        # Threshold at representative decimal-odds price points, using the
        # market-mean overround split evenly across the two sides.
        price_points = [1.5, 1.8, 2.0, 2.5, 3.0, 4.0]
        curve = {}
        for O in price_points:
            # implied fair split assuming symmetric half-overround on each side
            raw_over = 1.0 / O
            # reconstruct a plausible under price at the mean overround:
            # S = 1 + overround; raw_under = S - raw_over
            S = 1.0 + mean_over
            raw_under = S - raw_over
            if raw_under <= 0:
                curve[f'odds_{O}'] = None
                continue
            p_fair = raw_over / S
            curve[f'odds_{O}'] = float((1.0 / O) - p_fair)

        out[key] = {
            'n': len(pairs),
            'overround_mean': mean_over,
            'overround_pct': mean_over * 100.0,
            'required_edge_mean_pp': float(np.mean(req) * 100.0),
            'required_edge_median_pp': float(np.median(req) * 100.0),
            'required_edge_p25_pp': float(np.percentile(req, 25) * 100.0),
            'required_edge_p75_pp': float(np.percentile(req, 75) * 100.0),
            'required_edge_by_price_pp': {k: (v * 100.0 if v is not None else None)
                                          for k, v in curve.items()},
        }
    return out


# ═══════════════════════════════════════════════════════════════
# M2: ACTUAL EDGE DISTRIBUTION + GAP
# ═══════════════════════════════════════════════════════════════

def dist_summary(arr):
    arr = np.asarray(arr, dtype=float)
    return {
        'n': int(arr.size),
        'mean_pp': float(np.mean(arr) * 100),
        'median_pp': float(np.median(arr) * 100),
        'std_pp': float(np.std(arr) * 100),
        'p5_pp': float(np.percentile(arr, 5) * 100),
        'p25_pp': float(np.percentile(arr, 25) * 100),
        'p50_pp': float(np.percentile(arr, 50) * 100),
        'p75_pp': float(np.percentile(arr, 75) * 100),
        'p95_pp': float(np.percentile(arr, 95) * 100),
    }


def boot_ci_mean(arr, n_boot=N_BOOT):
    arr = np.asarray(arr, dtype=float)
    n = arr.size
    if n == 0:
        return (None, None)
    means = np.array([np.mean(arr[RNG.integers(0, n, n)]) for _ in range(n_boot)])
    return float(np.percentile(means, 2.5) * 100), float(np.percentile(means, 97.5) * 100)


def boot_ci_median(arr, n_boot=N_BOOT):
    arr = np.asarray(arr, dtype=float)
    n = arr.size
    if n == 0:
        return (None, None)
    meds = np.array([np.median(arr[RNG.integers(0, n, n)]) for _ in range(n_boot)])
    return float(np.percentile(meds, 2.5) * 100), float(np.percentile(meds, 97.5) * 100)


# ═══════════════════════════════════════════════════════════════
# M3: BET365 CALIBRATION-ERROR DISTRIBUTION (reliability curve)
# ═══════════════════════════════════════════════════════════════

def reliability_curve(fair_probs, outcomes, n_bins=10):
    """Bin by market-implied (vig-adjusted) probability; compare bucket
    predicted rate vs bucket realized rate. Returns per-bucket rows and the
    signed error (predicted - realized) with a Wilson-ish CI via bootstrap."""
    fair = np.asarray(fair_probs, dtype=float)
    y = np.asarray(outcomes, dtype=float)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        if i == n_bins - 1:
            mask = (fair >= lo) & (fair <= hi)
        else:
            mask = (fair >= lo) & (fair < hi)
        n = int(mask.sum())
        if n == 0:
            continue
        pred = float(np.mean(fair[mask]))
        realized = float(np.mean(y[mask]))
        # binomial CI on realized rate
        k = int(round(realized * n))
        bt = binomtest(k, n, pred)
        ci = bt.proportion_ci(confidence_level=0.95)
        rows.append({
            'bin_lo': float(lo), 'bin_hi': float(hi), 'n': n,
            'predicted_rate': pred,
            'realized_rate': realized,
            'error_pp': (pred - realized) * 100.0,
            'realized_ci_lo': float(ci.low),
            'realized_ci_hi': float(ci.high),
            'realized_within_ci_of_pred': bool(ci.low <= pred <= ci.high),
        })
    return rows


def per_match_calib_error(fair_probs, outcomes):
    """Per-match |predicted - realized| is degenerate (realized is 0/1), so
    we instead report the per-match signed residual (fair - outcome) which
    aggregates to calibration error, AND the bucketed error (the meaningful
    'how far off is the price' measure). We report the fraction of matches
    falling in buckets whose bucket-level error is within 1/2/5 pp."""
    pass


MIN_BUCKET_N = 8  # buckets smaller than this are noise, reported separately


def systematic_vs_random(rows):
    """Honest classification. Sparse buckets (n < MIN_BUCKET_N) are excluded
    from the error-mass verdict because their realized rate is uninformative
    (wide CI). Among well-populated buckets: if realized rates sit inside the
    price's CI and errors scatter in sign, that is random noise around a
    correct central estimate; if errors are consistently one-signed and large
    relative to CI, that is systematic bias."""
    if not rows:
        return {}
    dense = [r for r in rows if r['n'] >= MIN_BUCKET_N]
    if not dense:
        dense = rows
    errs = np.array([r['error_pp'] for r in dense])
    ns = np.array([r['n'] for r in dense])
    within = np.array([r['realized_within_ci_of_pred'] for r in dense])
    wmean = float(np.sum(errs * ns) / np.sum(ns))
    # weighted mean ABSOLUTE error over dense buckets = typical mispricing size
    wabs = float(np.sum(np.abs(errs) * ns) / np.sum(ns))
    frac_pos = float(np.mean(errs > 0))
    frac_within_ci = float(np.mean(within))
    return {
        'n_buckets_total': len(rows),
        'n_buckets_dense': len(dense),
        'n_sparse_excluded': len(rows) - len(dense),
        'weighted_mean_signed_error_pp': wmean,
        'weighted_mean_abs_error_pp': wabs,
        'unweighted_mean_signed_error_pp': float(np.mean(errs)),
        'frac_dense_buckets_positive_error': frac_pos,
        'frac_dense_buckets_realized_consistent_with_predicted': frac_within_ci,
        'max_abs_dense_bucket_error_pp': float(np.max(np.abs(errs))),
    }


# ═══════════════════════════════════════════════════════════════
# M4: ARE BET365'S ERRORS PREDICTABLE EX-ANTE? (conditional)
# ═══════════════════════════════════════════════════════════════
# Runs only for a market/line where M3 shows meaningful, one-signed error
# mass in dense buckets. We define per-match market error on the OVER side as
#     resid = fair_p_over - outcome_over        (positive => market over-priced the over)
# and test whether resid concentrates by observable PRE-MATCH characteristics.
# Multiple-comparison discipline: we report the whole family size and every
# split, and treat any pattern as a hypothesis requiring held-out confirmation
# (NOT tested here — held-out 2025/26 is off limits).

def measurement_4(rows, matched, market_line):
    resid = np.array(rows['fair_p_over']) - np.array(rows['outcome_over'])
    mids = rows['match_id']

    # Pull pre-match observables for each match from the joined FootyStats record.
    gw, ref, ppg_gap, tempo, league = [], [], [], [], []
    for mid in mids:
        m = matched.get(mid, {})
        gw.append(m.get('game_week', -1))
        ref.append(m.get('refereeID') if m.get('refereeID') is not None else -1)
        hp = m.get('home_ppg', 0) or 0
        ap = m.get('away_ppg', 0) or 0
        ppg_gap.append(abs(hp - ap))
        # pre-match tempo proxy: full-time over 2.5 goals price (lower = higher tempo)
        o = m.get('odds_ft_over25', 0) or 0
        tempo.append(o)
        # league by competition_id
        league.append(m.get('competition_id', -1))
    gw = np.array(gw, float); ppg_gap = np.array(ppg_gap, float)
    tempo = np.array(tempo, float); league = np.array(league)
    ref = np.array([int(r) if r is not None else -1 for r in ref])

    def split_report(name, mask_a, label_a, mask_b, label_b):
        a = resid[mask_a]; b = resid[mask_b]
        if a.size < 8 or b.size < 8:
            return {'characteristic': name, 'status': 'insufficient_subgroup_n',
                    'n_a': int(a.size), 'n_b': int(b.size)}
        # difference in mean residual + bootstrap CI on the difference
        diff = float(np.mean(a) - np.mean(b))
        na, nb = a.size, b.size
        boots = np.array([np.mean(a[RNG.integers(0, na, na)]) - np.mean(b[RNG.integers(0, nb, nb)])
                          for _ in range(N_BOOT)])
        lo, hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
        return {
            'characteristic': name,
            'group_a': label_a, 'group_b': label_b,
            'n_a': int(na), 'n_b': int(nb),
            'mean_resid_a_pp': float(np.mean(a) * 100),
            'mean_resid_b_pp': float(np.mean(b) * 100),
            'diff_pp': diff * 100,
            'diff_ci95_pp': [lo * 100, hi * 100],
            'ci_excludes_zero': bool(lo > 0 or hi < 0),
        }

    splits = []
    # 1) League: the two most common competition_ids
    vals, counts = np.unique(league, return_counts=True)
    if len(vals) >= 2:
        top2 = vals[np.argsort(counts)[::-1][:2]]
        splits.append(split_report('league', league == top2[0], f'comp_{top2[0]}',
                                    league == top2[1], f'comp_{top2[1]}'))
    # 2) Time of season: early (gw <= median) vs late
    gmed = np.median(gw[gw >= 0]) if np.any(gw >= 0) else 0
    splits.append(split_report('time_of_season', (gw >= 0) & (gw <= gmed), f'gw<=%g' % gmed,
                               gw > gmed, f'gw>%g' % gmed))
    # 3) Team strength gap: mismatch (large ppg gap) vs even
    pmed = np.median(ppg_gap)
    splits.append(split_report('ppg_gap', ppg_gap > pmed, f'gap>%.2f' % pmed,
                               ppg_gap <= pmed, f'gap<=%.2f' % pmed))
    # 4) Expected tempo: high-tempo (short over2.5 price) vs low-tempo
    tvalid = tempo > 0
    tmed = np.median(tempo[tvalid]) if np.any(tvalid) else 0
    splits.append(split_report('expected_tempo', tvalid & (tempo <= tmed), f'over25price<=%.2f' % tmed,
                               tvalid & (tempo > tmed), f'over25price>%.2f' % tmed))
    # 5) Referee: high-card refs vs low-card refs — proxy by referee's mean resid
    #    (leave-one-out would be ideal; here we just test top vs bottom referee
    #     tercile by frequency to avoid tiny groups). Report as exploratory.
    ref_ids, ref_counts = np.unique(ref[ref >= 0], return_counts=True)
    frequent = set(ref_ids[ref_counts >= 3].tolist())
    mask_freq = np.array([r in frequent for r in ref])
    splits.append(split_report('referee_frequent_vs_rare', mask_freq, 'freq_ref(>=3 matches)',
                               ~mask_freq, 'rare_ref'))

    family_size = len(splits)
    hits = [s for s in splits if s.get('ci_excludes_zero')]
    return {
        'market_line': market_line,
        'error_signal': 'per-match residual fair_p_over - outcome_over (positive = market over-priced over)',
        'overall_mean_resid_pp': float(np.mean(resid) * 100),
        'family_size': family_size,
        'characteristics_examined': [s['characteristic'] for s in splits],
        'splits': splits,
        'n_splits_ci_excludes_zero': len(hits),
        'multiple_comparison_note': (
            f'{family_size} characteristics tested as one family. With 5 tests, '
            'expected false positives at alpha=0.05 is 0.25. Any hit is a HYPOTHESIS '
            'requiring held-out (2025/26) confirmation, which was NOT performed here.'),
    }




def build_per_match():
    """Return, per metric_id and line, the arrays needed for M1-M4:
       over_odds, under_odds, model_p_over, fair_p_over, edge, outcome_over,
       plus match_id and league tag. Uses ev.* verbatim."""
    crosswalk = ev.load_crosswalk()
    thestats_matches = ev.load_thestats_matches()
    footystats_matches = ev.load_footystats_corpus()
    team_histories = ev.build_team_histories(footystats_matches)

    with open(f'{ODDS_DIR}/step2_odds_targets.json') as f:
        targets = json.load(f)
    target_ids = set(targets['match_ids'])

    odds_files = [f for f in glob.glob(f'{ODDS_DIR}/odds_mt_*.json')
                  if 'all_bookmakers' not in f and 'pinnacle' not in f]
    odds_ids = set('mt_' + os.path.basename(f).replace('odds_mt_', '').replace('.json', '')
                   for f in odds_files)
    target_with_odds = target_ids & odds_ids
    all_odds = ev.load_bet365_odds(target_with_odds)

    filtered = {k: v for k, v in thestats_matches.items() if k in target_with_odds}
    matched, _ = ev.join_matches(filtered, crosswalk, footystats_matches)

    per = {}
    per_line_odds = defaultdict(list)

    for metric_id, metric_def in ev.METRICS.items():
        preds = ev.compute_metric_predictions(metric_def, matched, team_histories,
                                              footystats_matches)
        if preds is None:
            continue
        market_key = 'total_cards' if metric_def['target'] == 'total_cards' else 'total_goals'
        for line in metric_def['lines']:
            line_key = f"{metric_def['target'].replace('total_', '')}_{line}"
            rows = {'over_odds': [], 'under_odds': [], 'model_p_over': [],
                    'fair_p_over': [], 'edge': [], 'outcome_over': [], 'match_id': []}
            for pred in preds:
                mid = pred['match_id']
                odds_data = all_odds.get(mid, {})
                market = odds_data.get(market_key, {})
                line_data = market.get(str(line))
                if line_data is None:
                    continue
                oo = line_data.get('over', {}).get('last_seen')
                uo = line_data.get('under', {}).get('last_seen')
                if oo is None or uo is None:
                    continue
                oo = float(oo); uo = float(uo)
                if oo <= 1.0 or uo <= 1.0:
                    continue
                lam = pred['predicted_lambda']
                p_over = float(np.clip(1.0 - poisson.cdf(int(line), lam), 0.01, 0.99))
                fair_over, _ = ev.devig_multiplicative(oo, uo)
                edge = p_over - fair_over
                outcome = 1.0 if pred['actual_count'] > line else 0.0
                rows['over_odds'].append(oo)
                rows['under_odds'].append(uo)
                rows['model_p_over'].append(p_over)
                rows['fair_p_over'].append(fair_over)
                rows['edge'].append(edge)
                rows['outcome_over'].append(outcome)
                rows['match_id'].append(mid)
            if len(rows['edge']) >= 5:
                per[(metric_id, line_key)] = rows
                # collect odds per market_line (dedup across metrics later)
                per_line_odds[f"{market_key}:{line}"].append((metric_id, line, rows))

    return per, matched


def main():
    print("Building validated per-match arrays (reusing ev_test pipeline verbatim)...")
    per, matched = build_per_match()

    # ---- M1 inputs: unique odds per market/line (dedup by match_id) ----
    market_line_odds = defaultdict(dict)   # key -> {mid: (oo,uo)}
    market_line_calib = defaultdict(lambda: {'fair': {}, 'y': {}})
    for (metric_id, line_key), rows in per.items():
        target = 'total_cards' if line_key.startswith('cards') else 'total_goals'
        line = line_key.split('_')[-1]
        key = f"{target}:{line}"
        for i, mid in enumerate(rows['match_id']):
            market_line_odds[key][mid] = (rows['over_odds'][i], rows['under_odds'][i])
            market_line_calib[key]['fair'][mid] = rows['fair_p_over'][i]
            market_line_calib[key]['y'][mid] = rows['outcome_over'][i]

    per_line_odds_lists = {k: list(v.values()) for k, v in market_line_odds.items()}

    print("M1: break-even thresholds...")
    m1 = measurement_1(per_line_odds_lists)

    # ---- M2: actual edge distribution per metric/line + gap vs threshold ----
    print("M2: actual edge distributions + gap...")
    m2 = {}
    for (metric_id, line_key), rows in per.items():
        target = 'total_cards' if line_key.startswith('cards') else 'total_goals'
        line = line_key.split('_')[-1]
        key = f"{target}:{line}"
        thr_pp = m1[key]['required_edge_mean_pp']
        edge = np.array(rows['edge'])
        summ = dist_summary(edge)
        mean_ci = boot_ci_mean(edge)
        med_ci = boot_ci_median(edge)
        frac_over = float(np.mean(edge > (thr_pp / 100.0)))
        m2[f"{metric_id}|{line_key}"] = {
            'market_line': key,
            'distribution': summ,
            'mean_ci95_pp': mean_ci,
            'median_ci95_pp': med_ci,
            'required_edge_pp': thr_pp,
            'frac_matches_exceeding_threshold': frac_over,
            # THE GAP: threshold minus actual edge (positive => shortfall)
            'gap_median_pp': thr_pp - summ['median_pp'],
            'gap_p75_pp': thr_pp - summ['p75_pp'],
            'gap_p95_pp': thr_pp - summ['p95_pp'],
        }

    # ---- M3: Bet365 calibration error distribution per market/line ----
    print("M3: Bet365 reliability curves...")
    m3 = {}
    for key, d in market_line_calib.items():
        fair = list(d['fair'].values())
        y = list(d['y'].values())
        rows = reliability_curve(fair, y, n_bins=10)
        # fraction of matches priced within X pp of the empirical (bucket) rate
        fair_arr = np.array(fair); y_arr = np.array(y)
        # map each match to its bucket error
        bins = np.linspace(0, 1, 11)
        idx = np.clip(np.digitize(fair_arr, bins) - 1, 0, 9)
        bucket_err = {}
        bucket_dense = {}
        for r in rows:
            b = int(round(r['bin_lo'] * 10))
            bucket_err[b] = abs(r['error_pp'])
            bucket_dense[b] = (r['n'] >= MIN_BUCKET_N)
        # only count matches that live in DENSE buckets (sparse-bucket error is noise)
        match_err = []
        for b in idx:
            b = int(b)
            if bucket_dense.get(b, False):
                match_err.append(bucket_err.get(b, np.nan))
        match_err = np.array([e for e in match_err if not np.isnan(e)])
        within = {
            'basis': 'dense_buckets_only (n>=%d)' % MIN_BUCKET_N,
            'n_matches_in_dense_buckets': int(match_err.size),
            'within_1pp': float(np.mean(match_err <= 1.0)) if match_err.size else None,
            'within_2pp': float(np.mean(match_err <= 2.0)) if match_err.size else None,
            'within_5pp': float(np.mean(match_err <= 5.0)) if match_err.size else None,
        }
        m3[key] = {
            'n_matches': len(y),
            'base_rate_over': float(np.mean(y)),
            'buckets': rows,
            'match_fraction_within': within,
            'systematic_vs_random': systematic_vs_random(rows),
        }

    out = {
        'note': ('Measurement only. Reuses validated 7-metric pipeline verbatim '
                 '(no refit of a different model, no metric substitution). '
                 'Odds sample = 2024/25 discovery season; held-out 2025/26 not touched. '
                 'Zero API calls.'),
        'sample': {'joined_matches': len(matched)},
        'M1_required_edge': m1,
        'M2_actual_edge': m2,
        'M3_bet365_calibration': m3,
    }

    # ---- M4: conditional predictability check ----
    # Trigger where M3 shows meaningful one-signed dense-bucket error mass.
    print("M4: predictability check (conditional)...")
    m4 = {}
    for key, v in m3.items():
        s = v['systematic_vs_random']
        meaningful = (abs(s.get('weighted_mean_signed_error_pp', 0)) >= 3.0 and
                      (v['match_fraction_within'].get('within_5pp') or 1.0) < 0.85)
        if not meaningful:
            m4[key] = {'status': 'skipped',
                       'reason': 'market tightly calibrated in dense buckets; no meaningful error mass to predict'}
            continue
        # build deduped per-match rows for this market:line (odds/fair/outcome are metric-independent)
        d = market_line_calib[key]
        # need over/under odds too:
        odds_map = market_line_odds[key]
        rows = {'fair_p_over': [], 'outcome_over': [], 'match_id': []}
        for mid in d['fair']:
            rows['fair_p_over'].append(d['fair'][mid])
            rows['outcome_over'].append(d['y'][mid])
            rows['match_id'].append(mid)
        m4[key] = measurement_4(rows, matched, key)
    out['M4_predictability'] = m4

    with open(OUT_PATH, 'w') as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nSaved: {OUT_PATH}")

    # ---- concise console summary ----
    print("\n=== M1 REQUIRED EDGE (break-even, pp) ===")
    for key, v in m1.items():
        print(f"  {key:18s} overround={v['overround_pct']:.2f}%  "
              f"req_edge mean={v['required_edge_mean_pp']:.2f}pp "
              f"median={v['required_edge_median_pp']:.2f}pp")
    print("\n=== M2 ACTUAL EDGE vs THRESHOLD (gap in pp) ===")
    for k, v in m2.items():
        d = v['distribution']
        print(f"  {k:40s} median_edge={d['median_pp']:+.2f}pp "
              f"thr={v['required_edge_pp']:.2f}pp GAP(median)={v['gap_median_pp']:.2f}pp "
              f"frac>thr={v['frac_matches_exceeding_threshold']*100:.0f}%")
    print("\n=== M3 BET365 CALIBRATION ===")
    for key, v in m3.items():
        s = v['systematic_vs_random']
        w = v['match_fraction_within']
        print(f"  {key:18s} n={v['n_matches']:4d} "
              f"wmean_err={s['weighted_mean_signed_error_pp']:+.2f}pp "
              f"wabs={s['weighted_mean_abs_error_pp']:.2f}pp "
              f"maxdense={s['max_abs_dense_bucket_error_pp']:.1f}pp "
              f"| within2pp={None if w['within_2pp'] is None else round(w['within_2pp']*100)}% "
              f"within5pp={None if w['within_5pp'] is None else round(w['within_5pp']*100)}%")

    print("\n=== M4 PREDICTABILITY ===")
    for key, v in m4.items():
        if v.get('status') == 'skipped':
            print(f"  {key:18s} SKIPPED ({v['reason']})")
            continue
        print(f"  {key:18s} family_size={v['family_size']} "
              f"overall_resid={v['overall_mean_resid_pp']:+.2f}pp "
              f"hits(ci_excl_0)={v['n_splits_ci_excludes_zero']}")
        for sp in v['splits']:
            if sp.get('status') == 'insufficient_subgroup_n':
                print(f"      {sp['characteristic']:24s} insufficient n")
                continue
            print(f"      {sp['characteristic']:24s} diff={sp['diff_pp']:+.2f}pp "
                  f"ci=[{sp['diff_ci95_pp'][0]:+.1f},{sp['diff_ci95_pp'][1]:+.1f}] "
                  f"excl0={sp['ci_excludes_zero']}")

    return out


if __name__ == '__main__':
    main()
