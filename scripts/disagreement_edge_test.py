"""
Disagreement-Concentrated Edge Test (Zero API Cost)

Question: In the matches where our model most disagrees with the market, who is right?

This is a RE-SLICING of the exact same per-match model probabilities and
vig-adjusted market probabilities produced by the EV test. It performs NO model
substitution, NO refitting, NO retuning. It imports the EV test module and reuses
its functions verbatim (same Poisson GLM + L2, same team shrinkage, same walk-forward
training, same multiplicative vig removal). The only new work is:

  1. Compute disagreement = |model_p_over - fair_market_p_over| per match.
  2. Rank & bucket by disagreement (deciles, or quintiles if buckets too thin).
  3. Per bucket: n, model BSS vs market BSS head-to-head, realized flat-bet return
     with 95% bootstrap CI, directional accuracy.
  4. Report the cross-bucket pattern (monotonic / flat / degrading).
  5. Directional split of the top bucket (model HIGHER vs LOWER than market).
  6. Characterize the top-disagreement fixtures (teams, pairings, referees, leagues).

Zero API calls: all inputs are cached. If any required cache is missing the script
aborts rather than fetching.
"""

import json
import os
import sys
import glob
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
from scipy.stats import poisson

sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
import ev_test_metrics_vs_bet365 as ev  # reuse exact pipeline; no reimplementation

BASE_DIR = '/home/ubuntu'
ODDS_DIR = f'{BASE_DIR}/data/thestatsapi/cache'
CORPUS_DIR = f'{BASE_DIR}/data/discovery/corpus'
OUT_JSON = f'{BASE_DIR}/data/results/disagreement_edge_test.json'

RNG_SEED = 42


# ───────────────────────────────────────────────────────────────
# Per-match record construction (reuses ev.* verbatim)
# ───────────────────────────────────────────────────────────────

def build_match_meta():
    """Extra per-match metadata for characterization: refereeID, competition_id,
    season — keyed by (home_name, away_name, date_unix) from the FootyStats corpus."""
    meta = {}
    for cf in sorted(glob.glob(f'{CORPUS_DIR}/league-matches_*.json')):
        with open(cf) as f:
            data = json.load(f)
        for m in data.get('data', []):
            key = (m.get('home_name', ''), m.get('away_name', ''), m.get('date_unix', 0))
            meta[key] = {
                'refereeID': m.get('refereeID'),
                'competition_id': m.get('competition_id'),
                'season': m.get('season'),
            }
    return meta


def collect_per_match_records():
    """Reproduce, for every metric/line, the exact per-match model & market
    probabilities the EV test computes internally, and retain them per match."""
    crosswalk = ev.load_crosswalk()
    thestats_matches = ev.load_thestats_matches()
    footystats_matches = ev.load_footystats_corpus()
    team_histories = ev.build_team_histories(footystats_matches)
    meta = build_match_meta()

    with open(f'{ODDS_DIR}/step2_odds_targets.json') as f:
        targets = json.load(f)
    target_ids = set(targets['match_ids'])

    odds_files = [f for f in glob.glob(f'{ODDS_DIR}/odds_mt_*.json')
                  if 'all_bookmakers' not in f and 'pinnacle' not in f]
    odds_ids = set('mt_' + os.path.basename(f).replace('odds_mt_', '').replace('.json', '')
                   for f in odds_files)
    target_with_odds = target_ids & odds_ids

    all_odds = ev.load_bet365_odds(target_with_odds)

    filtered_thestats = {k: v for k, v in thestats_matches.items() if k in target_with_odds}
    matched, _ = ev.join_matches(filtered_thestats, crosswalk, footystats_matches)

    records = {}  # (metric_id, line) -> list of record dicts

    for metric_id, metric_def in ev.METRICS.items():
        preds = ev.compute_metric_predictions(
            metric_def, matched, team_histories, footystats_matches
        )
        if preds is None:
            continue

        market_key = 'total_cards' if metric_def['target'] == 'total_cards' else 'total_goals'

        for line in metric_def['lines']:
            key = (metric_id, line)
            rows = []
            for pred in preds:
                mid = pred['match_id']
                line_data = all_odds.get(mid, {}).get(market_key, {}).get(str(line))
                if line_data is None:
                    continue
                over_s = line_data.get('over', {}).get('last_seen')
                under_s = line_data.get('under', {}).get('last_seen')
                if over_s is None or under_s is None:
                    continue
                over_odds = float(over_s)
                under_odds = float(under_s)
                if over_odds <= 1.0 or under_odds <= 1.0:
                    continue

                lam = pred['predicted_lambda']
                p_over = float(np.clip(1.0 - poisson.cdf(int(line), lam), 0.01, 0.99))
                fair_over, fair_under = ev.devig_multiplicative(over_odds, under_odds)
                overround = ev.compute_overround(over_odds, under_odds)

                actual = pred['actual_count']
                outcome_over = 1.0 if actual > line else 0.0

                mkey = (pred['home'], pred['away'], pred['date_unix'])
                mm = meta.get(mkey, {})

                rows.append({
                    'match_id': mid,
                    'home': pred['home'],
                    'away': pred['away'],
                    'date_unix': pred['date_unix'],
                    'refereeID': mm.get('refereeID'),
                    'competition_id': mm.get('competition_id'),
                    'season': mm.get('season'),
                    'actual_count': actual,
                    'outcome_over': outcome_over,
                    'model_p_over': p_over,
                    'fair_p_over': float(fair_over),
                    'disagreement': float(abs(p_over - fair_over)),
                    'signed_diff': float(p_over - fair_over),  # + => model higher than market
                    'over_odds': over_odds,
                    'under_odds': under_odds,
                    'overround': float(overround),
                })
            if len(rows) >= 5:
                records[key] = rows
    return records


# ───────────────────────────────────────────────────────────────
# Metrics on a subset of records
# ───────────────────────────────────────────────────────────────

def bss_vs_naive(probs, outcomes):
    probs = np.asarray(probs, float)
    outcomes = np.asarray(outcomes, float)
    bs = np.mean((probs - outcomes) ** 2)
    base = np.mean(outcomes)
    bs_naive = np.mean((base - outcomes) ** 2)
    if bs_naive == 0:
        return 0.0
    return 1.0 - bs / bs_naive


def directional_accuracy(rows):
    """Among matches, how often is the model's probability CLOSER to the realized
    outcome (0/1) than the market's probability? Ties excluded from numerator/denom."""
    wins = 0
    comparable = 0
    for r in rows:
        o = r['outcome_over']
        dm = abs(r['model_p_over'] - o)
        dk = abs(r['fair_p_over'] - o)
        if dm == dk:
            continue
        comparable += 1
        if dm < dk:
            wins += 1
    if comparable == 0:
        return None, 0, 0
    return wins / comparable, wins, comparable


def flat_bet_return_over(rows, seed=RNG_SEED):
    """Realized flat-bet return: back OVER at cached over_odds on every match in the
    subset (this is the natural bet the disagreement analysis interrogates: where the
    model most departs from the market). 1u stake; win => odds-1, lose => -1.
    Returns (roi, ci_lo, ci_hi, n)."""
    if not rows:
        return 0.0, 0.0, 0.0, 0
    profits = []
    for r in rows:
        if r['outcome_over'] == 1.0:
            profits.append(r['over_odds'] - 1.0)
        else:
            profits.append(-1.0)
    profits = np.asarray(profits, float)
    roi = float(np.mean(profits))
    rng = np.random.default_rng(seed)
    n = len(profits)
    boot = np.array([np.mean(profits[rng.choice(n, n, replace=True)]) for _ in range(10000)])
    boot.sort()
    return roi, float(boot[250]), float(boot[9750]), n


def directional_bet_return(rows, seed=RNG_SEED):
    """Realized flat-bet return betting the SIDE the model prefers vs market:
    if model_p_over > fair_p_over => back OVER; else back UNDER. This is the
    'follow the disagreement' strategy. Returns (roi, ci_lo, ci_hi, n, n_over, n_under)."""
    if not rows:
        return 0.0, 0.0, 0.0, 0, 0, 0
    profits = []
    n_over = n_under = 0
    for r in rows:
        if r['signed_diff'] >= 0:  # model says higher -> back OVER
            n_over += 1
            profits.append((r['over_odds'] - 1.0) if r['outcome_over'] == 1.0 else -1.0)
        else:  # model says lower -> back UNDER
            n_under += 1
            profits.append((r['under_odds'] - 1.0) if r['outcome_over'] == 0.0 else -1.0)
    profits = np.asarray(profits, float)
    roi = float(np.mean(profits))
    rng = np.random.default_rng(seed)
    n = len(profits)
    boot = np.array([np.mean(profits[rng.choice(n, n, replace=True)]) for _ in range(10000)])
    boot.sort()
    return roi, float(boot[250]), float(boot[9750]), n, n_over, n_under


def summarize_subset(rows):
    model_bss = bss_vs_naive([r['model_p_over'] for r in rows],
                             [r['outcome_over'] for r in rows])
    market_bss = bss_vs_naive([r['fair_p_over'] for r in rows],
                              [r['outcome_over'] for r in rows])
    diracc, dwins, dcomp = directional_accuracy(rows)
    roi_over, lo_over, hi_over, n_over_bets = flat_bet_return_over(rows)
    droi, dlo, dhi, dn, dn_over, dn_under = directional_bet_return(rows)
    return {
        'n': len(rows),
        'disagreement_mean': float(np.mean([r['disagreement'] for r in rows])),
        'disagreement_min': float(np.min([r['disagreement'] for r in rows])),
        'disagreement_max': float(np.max([r['disagreement'] for r in rows])),
        'model_bss_pct': model_bss * 100,
        'market_bss_pct': market_bss * 100,
        'model_minus_market_bss_pct': (model_bss - market_bss) * 100,
        'directional_accuracy': None if diracc is None else diracc,
        'directional_wins': dwins,
        'directional_comparable': dcomp,
        'over_flat_roi_pct': roi_over * 100,
        'over_flat_roi_ci95_pct': [lo_over * 100, hi_over * 100],
        'follow_disagreement_roi_pct': droi * 100,
        'follow_disagreement_roi_ci95_pct': [dlo * 100, dhi * 100],
        'follow_disagreement_n_over': dn_over,
        'follow_disagreement_n_under': dn_under,
        'base_rate_over': float(np.mean([r['outcome_over'] for r in rows])),
    }


# ───────────────────────────────────────────────────────────────
# Bucketing
# ───────────────────────────────────────────────────────────────

def bucket_by_disagreement(rows, n_buckets):
    """Sort by disagreement ascending and split into n_buckets near-equal groups.
    Bucket 0 = lowest disagreement, bucket n_buckets-1 = highest."""
    ordered = sorted(rows, key=lambda r: r['disagreement'])
    n = len(ordered)
    buckets = []
    for b in range(n_buckets):
        lo = (b * n) // n_buckets
        hi = ((b + 1) * n) // n_buckets
        buckets.append(ordered[lo:hi])
    return buckets


def classify_pattern(bucket_summaries):
    """Classify cross-bucket pattern of model_minus_market_bss from low->high
    disagreement. Returns a label and the correlation of bucket index vs metric."""
    vals = [b['model_minus_market_bss_pct'] for b in bucket_summaries]
    idx = np.arange(len(vals))
    if len(vals) < 3 or np.std(vals) == 0:
        return 'insufficient', 0.0, vals
    corr = float(np.corrcoef(idx, vals)[0, 1])
    # Spread of the relationship
    top = vals[-1]
    bottom = vals[0]
    if corr >= 0.5 and top > bottom:
        label = 'IMPROVES_WITH_DISAGREEMENT (supports thesis)'
    elif corr <= -0.5 and top < bottom:
        label = 'DEGRADES_WITH_DISAGREEMENT (fatal: model most wrong when most confident)'
    else:
        label = 'FLAT / NO_MONOTONIC_RELATION (disagreement uncorrelated with performance)'
    return label, corr, vals


# ───────────────────────────────────────────────────────────────
# Pooled analysis across all metric/line combos
# ───────────────────────────────────────────────────────────────

def zscore_within(rows, key):
    """Standardize disagreement within each (metric,line) so pooling across markets
    with different overrounds/scales is fair. Adds 'disagreement_z'."""
    vals = np.array([r[key] for r in rows], float)
    mu, sd = vals.mean(), vals.std()
    if sd == 0:
        sd = 1.0
    for r in rows:
        r['disagreement_z'] = (r[key] - mu) / sd


def main():
    print("=" * 80)
    print("DISAGREEMENT-CONCENTRATED EDGE TEST (zero API)")
    print("=" * 80)

    records = collect_per_match_records()
    if not records:
        print("ABORT: no per-match records built (cache missing?). No API fallback.")
        sys.exit(1)

    combos = sorted(records.keys())
    total_rows = sum(len(v) for v in records.values())
    print(f"Metric/line combos: {len(combos)}  |  total per-match rows (across combos): {total_rows}")

    out = {
        'analysis_date': datetime.now(timezone.utc).isoformat(),
        'method': {
            'reuses': 'scripts/ev_test_metrics_vs_bet365.py (imported verbatim)',
            'model': 'Poisson GLM + L2 (lambda=0.01), team empirical-Bayes shrinkage (strength=10)',
            'vig_removal': 'multiplicative (proportional overround removal)',
            'disagreement': '|model_p_over - fair_market_p_over|',
            'no_substitution': True, 'no_refit': True, 'no_threshold_tuning': True,
            'bootstrap': '10000 resamples, seed=42, 95% percentile CI',
        },
        'per_combo': {},
        'pooled': {},
    }

    # ── Per-combo bucketing ─────────────────────────────────────
    # Deciles need ~30/bucket at n=300. Per-combo n ranges 70-281, so per-combo
    # deciles would be 7-28/bucket (too thin for stable CIs). We therefore report
    # per-combo QUINTILES and reserve DECILES for the pooled analysis (n>1000).
    for (metric_id, line) in combos:
        rows = records[(metric_id, line)]
        n = len(rows)
        n_buckets = 5  # quintiles per combo (see rationale above)
        buckets = bucket_by_disagreement(rows, n_buckets)
        bucket_summaries = [summarize_subset(b) for b in buckets if b]
        label, corr, vals = classify_pattern(bucket_summaries)
        out['per_combo'][f'{metric_id}@{line}'] = {
            'n': n,
            'n_buckets': n_buckets,
            'bucket_type': 'quintile',
            'overall': summarize_subset(rows),
            'buckets_low_to_high_disagreement': bucket_summaries,
            'pattern': label,
            'bucketidx_vs_bss_corr': corr,
        }
        print(f"\n{metric_id}@{line}  n={n}  pattern={label}  corr={corr:+.2f}")
        for i, b in enumerate(bucket_summaries):
            print(f"   Q{i+1} n={b['n']:3d} dis=[{b['disagreement_min']*100:4.1f},"
                  f"{b['disagreement_max']*100:5.1f}]%  "
                  f"mdl-mkt BSS={b['model_minus_market_bss_pct']:+6.2f}%  "
                  f"dirAcc={('  n/a' if b['directional_accuracy'] is None else format(b['directional_accuracy']*100,'4.0f')+'%')}  "
                  f"followROI={b['follow_disagreement_roi_pct']:+6.1f}% "
                  f"[{b['follow_disagreement_roi_ci95_pct'][0]:+5.1f},{b['follow_disagreement_roi_ci95_pct'][1]:+5.1f}]")

    # ── Pooled across all combos (within-combo z-scored disagreement) ──
    pooled_rows = []
    for (metric_id, line) in combos:
        rows = [dict(r) for r in records[(metric_id, line)]]
        zscore_within(rows, 'disagreement')
        for r in rows:
            r['combo'] = f'{metric_id}@{line}'
        pooled_rows.extend(rows)

    # Rank pooled by z-scored disagreement, decile buckets
    pooled_rows.sort(key=lambda r: r['disagreement_z'])
    n_pool = len(pooled_rows)
    n_buckets_pool = 10
    pooled_buckets = []
    for b in range(n_buckets_pool):
        lo = (b * n_pool) // n_buckets_pool
        hi = ((b + 1) * n_pool) // n_buckets_pool
        pooled_buckets.append(pooled_rows[lo:hi])
    pooled_summaries = [summarize_subset(b) for b in pooled_buckets]
    label, corr, vals = classify_pattern(pooled_summaries)

    out['pooled'] = {
        'note': ('Pools all metric/line rows. Disagreement standardized WITHIN each '
                 'metric/line (z-score) before ranking so markets with different '
                 'overround scales are comparable. NOTE: rows are not independent '
                 'matches — a single fixture contributes to multiple metric/line '
                 'combos — so pooled CIs understate correlation. Treat as descriptive.'),
        'n_rows': n_pool,
        'n_buckets': n_buckets_pool,
        'bucket_type': 'decile',
        'buckets_low_to_high_disagreement': pooled_summaries,
        'pattern': label,
        'bucketidx_vs_bss_corr': corr,
    }

    print(f"\n{'='*80}\nPOOLED (decile, within-combo z-scored disagreement)  n_rows={n_pool}")
    print(f"pattern={label}  corr={corr:+.2f}")
    for i, b in enumerate(pooled_summaries):
        print(f"  D{i+1:2d} n={b['n']:3d}  mdl-mkt BSS={b['model_minus_market_bss_pct']:+6.2f}%  "
              f"mktBSS={b['market_bss_pct']:+6.2f}%  mdlBSS={b['model_bss_pct']:+6.2f}%  "
              f"dirAcc={('n/a' if b['directional_accuracy'] is None else format(b['directional_accuracy']*100,'4.0f')+'%')}  "
              f"followROI={b['follow_disagreement_roi_pct']:+6.1f}% "
              f"[{b['follow_disagreement_roi_ci95_pct'][0]:+5.1f},{b['follow_disagreement_roi_ci95_pct'][1]:+5.1f}]")

    # ── Top-disagreement directional split + fixture characterization ──
    top_bucket = pooled_buckets[-1]
    higher = [r for r in top_bucket if r['signed_diff'] > 0]
    lower = [r for r in top_bucket if r['signed_diff'] < 0]

    def dir_block(rows):
        if not rows:
            return {'n': 0}
        s = summarize_subset(rows)
        return s

    out['top_decile_directional_split'] = {
        'n_top': len(top_bucket),
        'model_higher_than_market': dir_block(higher),
        'model_lower_than_market': dir_block(lower),
    }

    # Fixture characterization on the top decile
    team_counts = defaultdict(int)
    pairing_counts = defaultdict(int)
    ref_counts = defaultdict(int)
    comp_counts = defaultdict(int)
    for r in top_bucket:
        team_counts[r['home']] += 1
        team_counts[r['away']] += 1
        pair = tuple(sorted([r['home'], r['away']]))
        pairing_counts[pair] += 1
        ref_counts[r['refereeID']] += 1
        comp_counts[r['competition_id']] += 1

    out['top_decile_characterization'] = {
        'top_teams': sorted(team_counts.items(), key=lambda x: -x[1])[:15],
        'top_pairings': [list(k) + [v] for k, v in
                         sorted(pairing_counts.items(), key=lambda x: -x[1])[:15]],
        'referee_concentration': sorted(
            [(str(k), v) for k, v in ref_counts.items()], key=lambda x: -x[1])[:15],
        'competition_breakdown': sorted(
            [(str(k), v) for k, v in comp_counts.items()], key=lambda x: -x[1]),
        'unique_matches_in_top_decile': len(set(r['match_id'] for r in top_bucket)),
    }

    print(f"\nTop decile directional split:")
    print(f"  model HIGHER than market: n={len(higher)}", 
          f"follow-ROI={dir_block(higher).get('follow_disagreement_roi_pct'):+.1f}%" if higher else "")
    print(f"  model LOWER  than market: n={len(lower)}",
          f"follow-ROI={dir_block(lower).get('follow_disagreement_roi_pct'):+.1f}%" if lower else "")

    with open(OUT_JSON, 'w') as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nSaved: {OUT_JSON}")
    return out


if __name__ == '__main__':
    main()
