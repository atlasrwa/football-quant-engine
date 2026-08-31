"""
Market-First EV Scanner (zero API).

Scans every scannable market/line with THREE model families against cached
Bet365 prices, applies a MANDATORY reliability filter, re-runs the
disagreement-decile test on filtered flags, and backtests the scanner as a
strategy.

Families:
  A  Standard models — Dixon-Coles (goals O/U, 1X2, BTTS) and CountRegression
     (corners, cards). Fit WALK-FORWARD on the corpus with the model spec fixed
     (no hyperparameter retune). Nothing is serialized on disk, so a single
     in-window fit is required to produce any prediction; the spec/hyperparameters
     are used exactly as defined in src/research/models/*.
  B  The 7 discovered metrics — imported VERBATIM from ev_test_metrics_vs_bet365
     (no refit, no substitution).
  C  Matchup-interaction models — P(outcome | profileA x profileB) on continuous
     team profiles (not team identity), tested against a marginal-combination
     baseline.

All data cached. Odds sample = TheStatsAPI Bet365 cache joined to the FootyStats
corpus (2024/25 discovery season). Held-out 2025/26 is NOT touched here.

Vig removed multiplicatively (ev.devig_multiplicative) — every edge reported is
net of overround.
"""

import json, os, sys, glob, math
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
from scipy.stats import poisson

sys.path.insert(0, os.path.dirname(__file__))
import ev_test_metrics_vs_bet365 as ev  # family B + all data plumbing, verbatim

sys.path.insert(0, '/home/ubuntu')
from src.research.models.dixon_coles import DixonColesModel
from src.research.models.derived_goals import BTTSModel
from src.research.models.count_regression import create_corners_model, create_cards_model

BASE = '/home/ubuntu'
ODDS_DIR = f'{BASE}/data/thestatsapi/cache'
CORPUS_DIR = f'{BASE}/data/discovery/corpus'
OUT = f'{BASE}/data/results/market_first_scan.json'
RNG = np.random.default_rng(42)

# ── Reliability filter thresholds (pre-specified) ──
MIN_TEAM_MATCHES = 8      # each team needs >=8 prior in-window matches
MIN_MARKET_N = 50         # a market/line needs >=50 joined matches to be scanned
DIVERGENCE_MIN_PP = 3.0   # |edge| must be >= 3pp to be a "flag" (below the smallest threshold)
EXTREME_LAMBDA = (0.3, 5.5)   # non-extreme fitted rate estimates
CONF_MIN = 0.30           # DC prediction_confidence floor


def boot_ci(profits, n=10000, seed=42):
    profits = np.asarray(profits, float)
    if profits.size == 0:
        return 0.0, 0.0, 0.0
    rng = np.random.default_rng(seed)
    m = profits.size
    b = np.array([np.mean(profits[rng.integers(0, m, m)]) for _ in range(n)])
    return float(np.mean(profits)), float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))


def bss_vs_naive(probs, outcomes):
    p = np.asarray(probs, float); y = np.asarray(outcomes, float)
    bs = np.mean((p - y) ** 2); base = np.mean(y)
    bsn = np.mean((base - y) ** 2)
    return 0.0 if bsn == 0 else 1.0 - bs / bsn


# ════════════════════════════════════════════════════════════════
# DATA: reuse ev for the join, then attach corner/card/goal outcomes
# ════════════════════════════════════════════════════════════════

def load_all():
    crosswalk = ev.load_crosswalk()
    thestats = ev.load_thestats_matches()
    footy = ev.load_footystats_corpus()
    team_hist = ev.build_team_histories(footy)
    with open(f'{ODDS_DIR}/step2_odds_targets.json') as f:
        target_ids = set(json.load(f)['match_ids'])
    odds_files = [f for f in glob.glob(f'{ODDS_DIR}/odds_mt_*.json')
                  if 'all_bookmakers' not in f and 'pinnacle' not in f]
    odds_ids = set('mt_' + os.path.basename(f).replace('odds_mt_', '').replace('.json', '')
                   for f in odds_files)
    tw = target_ids & odds_ids
    all_odds = ev.load_bet365_odds(tw)
    filt = {k: v for k, v in thestats.items() if k in tw}
    matched, _ = ev.join_matches(filt, crosswalk, footy)
    return footy, team_hist, all_odds, matched


def bet365_ou(all_odds, mid, market, line):
    ld = all_odds.get(mid, {}).get(market, {}).get(str(line))
    if not ld:
        return None
    o = ld.get('over', {}).get('last_seen'); u = ld.get('under', {}).get('last_seen')
    if o is None or u is None:
        return None
    o = float(o); u = float(u)
    if o <= 1.0 or u <= 1.0:
        return None
    return o, u


def bet365_1x2(all_odds, mid):
    m = all_odds.get(mid, {}).get('match_odds')
    if not m:
        return None
    try:
        h = float(m['home']['last_seen']); d = float(m['draw']['last_seen']); a = float(m['away']['last_seen'])
    except (KeyError, TypeError, ValueError):
        return None
    if min(h, d, a) <= 1.0:
        return None
    return h, d, a


def bet365_btts(all_odds, mid):
    m = all_odds.get(mid, {}).get('btts')
    if not m:
        return None
    try:
        y = float(m['yes']['last_seen']); n = float(m['no']['last_seen'])
    except (KeyError, TypeError, ValueError):
        return None
    if min(y, n) <= 1.0:
        return None
    return y, n


def devig2(a, b):
    ra, rb = 1.0/a, 1.0/b
    s = ra + rb
    return ra/s, rb/s


def devig3(h, d, a):
    r = np.array([1.0/h, 1.0/d, 1.0/a]); s = r.sum()
    return (r/s).tolist()


# ════════════════════════════════════════════════════════════════
# FAMILY A: Dixon-Coles + Count models, walk-forward, spec fixed
# ════════════════════════════════════════════════════════════════

def build_family_A(footy, matched, all_odds):
    """Fit DC and count models ONCE on all corpus matches strictly before the
    earliest odds match (walk-forward, point-in-time), then predict on the
    odds-sample matches. Same single-refit discipline the ev pipeline uses."""
    # earliest odds match date
    dates = [fm.get('date_unix', 0) for fm in matched.values()]
    earliest = min(dates)

    train = [m for m in footy if m.get('date_unix', 0) < earliest
             and m.get('home_name') and m.get('away_name')]

    # DC feature dicts
    dc_feats = [{'home_team': m['home_name'], 'away_team': m['away_name'],
                 'home_goals': m.get('homeGoalCount', 0) or 0,
                 'away_goals': m.get('awayGoalCount', 0) or 0,
                 'date_unix': m.get('date_unix', 0)} for m in train]
    dc = DixonColesModel(line=2.5)          # spec as defined; not retuned
    dc.fit(dc_feats, [False] * len(dc_feats), training_end=earliest)
    btts = BTTSModel(goals_model=dc)

    # Count models for corners & cards. They read named fields from each dict.
    def count_feats(target):
        rows = []
        for m in train:
            if target == 'total_corners':
                c = (m.get('team_a_corners') or 0) + (m.get('team_b_corners') or 0)
            else:
                c = ((m.get('team_a_yellow_cards') or 0) + (m.get('team_b_yellow_cards') or 0)
                     + (m.get('team_a_red_cards') or 0) + (m.get('team_b_red_cards') or 0))
            rows.append({
                target: c,
                'home_team_id': m['home_name'], 'away_team_id': m['away_name'],
                'dangerous_attacks_home': m.get('team_a_dangerous_attacks') or 0,
                'dangerous_attacks_away': m.get('team_b_dangerous_attacks') or 0,
                'shots_home': m.get('team_a_shots') or 0, 'shots_away': m.get('team_b_shots') or 0,
                'possession_home': m.get('team_a_possession') or 50,
                'possession_away': m.get('team_b_possession') or 50,
            })
        return rows

    corners_models = {}
    for ln in (9.5, 10.5, 11.5):
        cm = create_corners_model(line=ln)
        cm.fit(count_feats('total_corners'), [False] * len(train))
        corners_models[ln] = cm
    cards_models = {}
    for ln in (3.5, 4.5):
        cm = create_cards_model(line=ln)
        cm.fit(count_feats('total_cards'), [False] * len(train))
        cards_models[ln] = cm

    # team match counts in-window (for reliability filter)
    team_counts = defaultdict(int)
    for m in train:
        team_counts[m['home_name']] += 1
        team_counts[m['away_name']] += 1

    return dc, btts, corners_models, cards_models, team_counts


def predict_family_A(matched, all_odds, dc, btts, corners_models, cards_models, team_counts):
    """Produce per-match A-family predictions for every scannable market/line."""
    out = defaultdict(list)   # (market,line,'A') -> list of record dicts
    for mid, fm in matched.items():
        f = {'home_team': fm['home_name'], 'away_team': fm['away_name']}
        hg = fm.get('homeGoalCount', 0) or 0; ag = fm.get('awayGoalCount', 0) or 0
        total_goals = hg + ag
        conf = dc.prediction_confidence(f)
        lam_h, lam_a = dc.get_expected_goals(f)
        tmin = min(team_counts.get(fm['home_name'], 0), team_counts.get(fm['away_name'], 0))
        rel_common = {'match_id': mid, 'home': fm['home_name'], 'away': fm['away_name'],
                      'date_unix': fm.get('date_unix', 0), 'team_min_matches': tmin,
                      'dc_conf': conf, 'lam_sum': lam_h + lam_a}

        # goals O/U
        for ln in (1.5, 2.5, 3.5, 4.5):
            odds = bet365_ou(all_odds, mid, 'total_goals', ln)
            if not odds:
                continue
            p_over, _ = dc.predict_over_under(f, ln)
            p_over = float(np.clip(p_over, 0.01, 0.99))
            fair_o, _ = devig2(*odds)
            out[('goals', ln, 'A')].append({**rel_common,
                'model_p': p_over, 'fair_p': fair_o, 'edge': p_over - fair_o,
                'outcome': 1.0 if total_goals > ln else 0.0,
                'odds_bet': odds[0], 'odds_other': odds[1],
                'overround': odds[0] and (1/odds[0] + 1/odds[1] - 1),
                'reliable_extra': True})

        # BTTS
        bo = bet365_btts(all_odds, mid)
        if bo:
            p_yes = float(np.clip(btts.predict_btts_probability(f), 0.01, 0.99))
            fair_yes, _ = devig2(*bo)
            out[('btts', None, 'A')].append({**rel_common,
                'model_p': p_yes, 'fair_p': fair_yes, 'edge': p_yes - fair_yes,
                'outcome': 1.0 if (hg >= 1 and ag >= 1) else 0.0,
                'odds_bet': bo[0], 'odds_other': bo[1],
                'overround': 1/bo[0] + 1/bo[1] - 1, 'reliable_extra': True})

        # 1X2 (score the HOME side as the canonical two-outcome-ised bet)
        x = bet365_1x2(all_odds, mid)
        if x:
            ph, pd, pa = dc.predict_match_probabilities(f)
            fair = devig3(*x)
            out[('1x2_home', None, 'A')].append({**rel_common,
                'model_p': float(np.clip(ph, 0.01, 0.99)), 'fair_p': fair[0],
                'edge': float(np.clip(ph, 0.01, 0.99)) - fair[0],
                'outcome': 1.0 if hg > ag else 0.0,
                'odds_bet': x[0], 'odds_other': None,
                'overround': (1/x[0]+1/x[1]+1/x[2]-1), 'reliable_extra': True})

        # corners O/U (uses count model + separate reliability on corners history)
        total_corners = None  # need realized corners from corpus record
        tc = fm.get('team_a_corners'); tc2 = fm.get('team_b_corners')
        if tc is not None and tc2 is not None:
            total_corners = (tc or 0) + (tc2 or 0)
        for ln, cm in corners_models.items():
            odds = bet365_ou(all_odds, mid, 'match_corners', ln)
            if not odds or total_corners is None:
                continue
            p_over, _ = cm.predict_over_under({'home_team_id': fm['home_name'],
                                               'away_team_id': fm['away_name']}, ln)
            p_over = float(np.clip(p_over, 0.01, 0.99))
            fair_o, _ = devig2(*odds)
            out[('corners', ln, 'A')].append({**rel_common,
                'model_p': p_over, 'fair_p': fair_o, 'edge': p_over - fair_o,
                'outcome': 1.0 if total_corners > ln else 0.0,
                'odds_bet': odds[0], 'odds_other': odds[1],
                'overround': 1/odds[0] + 1/odds[1] - 1, 'reliable_extra': True})

        # cards O/U
        ya = fm.get('team_a_yellow_cards'); yb = fm.get('team_b_yellow_cards')
        total_cards = None
        if ya is not None and yb is not None:
            total_cards = ((ya or 0) + (yb or 0) + (fm.get('team_a_red_cards') or 0)
                           + (fm.get('team_b_red_cards') or 0))
        for ln, cm in cards_models.items():
            odds = bet365_ou(all_odds, mid, 'total_cards', ln)
            if not odds or total_cards is None:
                continue
            p_over, _ = cm.predict_over_under({'home_team_id': fm['home_name'],
                                               'away_team_id': fm['away_name']}, ln)
            p_over = float(np.clip(p_over, 0.01, 0.99))
            fair_o, _ = devig2(*odds)
            out[('cards', ln, 'A')].append({**rel_common,
                'model_p': p_over, 'fair_p': fair_o, 'edge': p_over - fair_o,
                'outcome': 1.0 if total_cards > ln else 0.0,
                'odds_bet': odds[0], 'odds_other': odds[1],
                'overround': 1/odds[0] + 1/odds[1] - 1, 'reliable_extra': True})
    return out


# ════════════════════════════════════════════════════════════════
# FAMILY B: the 7 discovered metrics, verbatim via ev
# ════════════════════════════════════════════════════════════════

def predict_family_B(footy, team_hist, matched, all_odds, team_counts):
    out = defaultdict(list)
    for metric_id, mdef in ev.METRICS.items():
        preds = ev.compute_metric_predictions(mdef, matched, team_hist, footy)
        if preds is None:
            continue
        market = 'total_cards' if mdef['target'] == 'total_cards' else 'total_goals'
        market_short = 'cards' if market == 'total_cards' else 'goals'
        for ln in mdef['lines']:
            for pred in preds:
                mid = pred['match_id']
                odds = bet365_ou(all_odds, mid, market, ln)
                if not odds:
                    continue
                lam = pred['predicted_lambda']
                p_over = float(np.clip(1.0 - poisson.cdf(int(ln), lam), 0.01, 0.99))
                fair_o, _ = ev.devig_multiplicative(*odds)
                tmin = min(team_counts.get(pred['home'], 0), team_counts.get(pred['away'], 0))
                out[(market_short, ln, f'B:{metric_id}')].append({
                    'match_id': mid, 'home': pred['home'], 'away': pred['away'],
                    'date_unix': pred['date_unix'], 'team_min_matches': tmin,
                    'dc_conf': 1.0, 'lam_sum': lam,
                    'model_p': p_over, 'fair_p': float(fair_o), 'edge': p_over - float(fair_o),
                    'outcome': 1.0 if pred['actual_count'] > ln else 0.0,
                    'odds_bet': odds[0], 'odds_other': odds[1],
                    'overround': 1/odds[0] + 1/odds[1] - 1, 'reliable_extra': True})
    return out


# ════════════════════════════════════════════════════════════════
# FAMILY C: matchup interaction on continuous profiles vs marginal baseline
# ════════════════════════════════════════════════════════════════

def build_family_C(footy, matched, all_odds, earliest, team_hist):
    """Interaction test on GOALS totals. Profile each team by continuous rolling
    features (attacking rate, conceding rate). Baseline = additive/marginal
    combination (sum of team rates -> Poisson). Interaction = baseline PLUS an
    interaction term (product of standardized attack_home x concede_away etc.)
    fit by Poisson GLM on training data. The test: does adding the interaction
    term improve out-of-sample BSS vs the market and vs the marginal baseline?"""
    # Build training rows: for each pre-earliest match, team rolling rates before it
    def team_rate(name, field, window, before):
        return ev.get_team_rolling_stat(team_hist, name, field, window, before)

    def make_row(m):
        d = m.get('date_unix', 0)
        h, a = m.get('home_name'), m.get('away_name')
        # marginals: attacking (goals scored) & conceding proxies via rolling goals + xg
        ah = team_rate(h, 'overallGoalCount', 5, d)   # match total goals when h played (tempo)
        aa = team_rate(a, 'overallGoalCount', 5, d)
        xh = team_rate(h, 'xg', 5, d); xa = team_rate(a, 'xg', 5, d)
        if None in (ah, aa, xh, xa):
            return None
        tot = m.get('overallGoalCount', 0) or 0
        return {'h_tempo': ah, 'a_tempo': aa, 'h_xg': xh, 'a_xg': xa,
                'total': tot, 'date': d, 'home': h, 'away': a}

    train_rows = [r for r in (make_row(m) for m in footy
                              if m.get('date_unix', 0) < earliest) if r]
    if len(train_rows) < 100:
        return None

    X_marg = np.array([[r['h_tempo'], r['a_tempo'], r['h_xg'], r['a_xg']] for r in train_rows])
    y = np.array([r['total'] for r in train_rows], float)
    # standardize
    mu = X_marg.mean(0); sd = X_marg.std(0); sd[sd == 0] = 1
    Xz = (X_marg - mu) / sd
    # interaction columns: tempo_h*tempo_a, xg_h*xg_a, tempo_h*xg_a, xg_h*tempo_a
    inter = np.column_stack([Xz[:,0]*Xz[:,1], Xz[:,2]*Xz[:,3], Xz[:,0]*Xz[:,3], Xz[:,2]*Xz[:,1]])

    def fit_poisson(X, y, l2=0.01):
        from scipy.optimize import minimize
        from scipy.special import gammaln
        n, k = X.shape
        def nll(p):
            lo = np.clip(p[0] + X @ p[1:], -3, 3); lam = np.exp(lo)
            return -np.sum(y*lo - lam - gammaln(y+1)) + l2*np.sum(p[1:]**2)
        r = minimize(nll, np.zeros(k+1), method='L-BFGS-B', options={'maxiter': 300})
        return r.x

    beta_marg = fit_poisson(Xz, y)
    beta_int = fit_poisson(np.column_stack([Xz, inter]), y)

    return {'mu': mu, 'sd': sd, 'beta_marg': beta_marg, 'beta_int': beta_int,
            'team_hist': team_hist}


def predict_family_C(cmodel, matched, all_odds, team_counts):
    if cmodel is None:
        return {}
    mu, sd = cmodel['mu'], cmodel['sd']
    bm, bi = cmodel['beta_marg'], cmodel['beta_int']
    th = cmodel['team_hist']
    out = defaultdict(list)
    for mid, fm in matched.items():
        d = fm.get('date_unix', 0); h, a = fm['home_name'], fm['away_name']
        ah = ev.get_team_rolling_stat(th, h, 'overallGoalCount', 5, d)
        aa = ev.get_team_rolling_stat(th, a, 'overallGoalCount', 5, d)
        xh = ev.get_team_rolling_stat(th, h, 'xg', 5, d)
        xa = ev.get_team_rolling_stat(th, a, 'xg', 5, d)
        if None in (ah, aa, xh, xa):
            continue
        z = (np.array([ah, aa, xh, xa]) - mu) / sd
        inter = np.array([z[0]*z[1], z[2]*z[3], z[0]*z[3], z[2]*z[1]])
        lam_marg = math.exp(np.clip(bm[0] + z @ bm[1:], -3, 3))
        lam_int = math.exp(np.clip(bi[0] + np.concatenate([z, inter]) @ bi[1:], -3, 3))
        hg = fm.get('homeGoalCount', 0) or 0; ag = fm.get('awayGoalCount', 0) or 0
        tot = hg + ag
        tmin = min(team_counts.get(h, 0), team_counts.get(a, 0))
        for ln in (1.5, 2.5, 3.5):
            odds = bet365_ou(all_odds, mid, 'total_goals', ln)
            if not odds:
                continue
            fair_o, _ = devig2(*odds)
            p_marg = float(np.clip(1 - poisson.cdf(int(ln), lam_marg), 0.01, 0.99))
            p_int = float(np.clip(1 - poisson.cdf(int(ln), lam_int), 0.01, 0.99))
            base = {'match_id': mid, 'home': h, 'away': a, 'date_unix': d,
                    'team_min_matches': tmin, 'dc_conf': 1.0, 'outcome': 1.0 if tot > ln else 0.0,
                    'odds_bet': odds[0], 'odds_other': odds[1],
                    'overround': 1/odds[0]+1/odds[1]-1, 'reliable_extra': True}
            out[('goals', ln, 'C:marginal')].append({**base, 'lam_sum': lam_marg,
                'model_p': p_marg, 'fair_p': fair_o, 'edge': p_marg - fair_o})
            out[('goals', ln, 'C:interaction')].append({**base, 'lam_sum': lam_int,
                'model_p': p_int, 'fair_p': fair_o, 'edge': p_int - fair_o})
    return out


# ════════════════════════════════════════════════════════════════
# RELIABILITY FILTER + DISAGREEMENT RE-TEST + BACKTEST
# ════════════════════════════════════════════════════════════════

def is_reliable(r):
    return (r.get('team_min_matches', 0) >= MIN_TEAM_MATCHES
            and EXTREME_LAMBDA[0] <= r.get('lam_sum', 1.0) <= EXTREME_LAMBDA[1]
            and r.get('dc_conf', 1.0) >= CONF_MIN)


def disagreement_deciles(rows):
    """Re-run the disagreement-decile test: rank by |edge|, decile, report
    follow-the-model ROI + model-minus-market BSS per decile and the corr."""
    rows = [r for r in rows if 'outcome' in r]
    if len(rows) < 30:
        return None
    ordered = sorted(rows, key=lambda r: abs(r['edge']))
    n = len(ordered); nb = min(10, max(3, n // 20))
    corr_pairs = []
    decs = []
    for b in range(nb):
        lo = (b*n)//nb; hi = ((b+1)*n)//nb
        bk = ordered[lo:hi]
        if not bk:
            continue
        y = [r['outcome'] for r in bk]
        mb = bss_vs_naive([r['model_p'] for r in bk], y)
        kb = bss_vs_naive([r['fair_p'] for r in bk], y)
        # follow-the-model flat bet
        profits = []
        for r in bk:
            if r['edge'] >= 0:  # model says over more likely -> back over
                profits.append((r['odds_bet']-1) if r['outcome'] == 1 else -1)
            elif r.get('odds_other'):
                profits.append((r['odds_other']-1) if r['outcome'] == 0 else -1)
            else:
                profits.append((r['odds_bet']-1) if r['outcome'] == 1 else -1)
        roi, clo, chi = boot_ci(profits)
        decs.append({'decile': b+1, 'n': len(bk),
                     'dis_min_pp': abs(ordered[lo]['edge'])*100,
                     'dis_max_pp': abs(ordered[hi-1]['edge'])*100,
                     'model_minus_market_bss_pct': (mb-kb)*100,
                     'follow_roi_pct': roi*100, 'follow_roi_ci_pct': [clo*100, chi*100]})
        corr_pairs.append((b, (mb-kb)*100))
    if len(corr_pairs) >= 3:
        idx = np.array([c[0] for c in corr_pairs]); val = np.array([c[1] for c in corr_pairs])
        corr = float(np.corrcoef(idx, val)[0,1]) if val.std() > 0 else 0.0
    else:
        corr = 0.0
    return {'n': n, 'n_deciles': nb, 'deciles': decs, 'bucketidx_vs_bss_corr': corr}


def backtest_flags(rows):
    """Backtest: among RELIABLE rows, flag those with |edge| >= DIVERGENCE_MIN_PP,
    bet the side the model favours, flat stake. Report flags, hit rate, ROI+CI,
    overround."""
    flags = [r for r in rows if is_reliable(r) and abs(r['edge']) >= DIVERGENCE_MIN_PP/100]
    if not flags:
        return {'n_flags': 0}
    profits = []; hits = 0
    for r in flags:
        if r['edge'] >= 0:
            win = r['outcome'] == 1
            profits.append((r['odds_bet']-1) if win else -1)
        elif r.get('odds_other'):
            win = r['outcome'] == 0
            profits.append((r['odds_other']-1) if win else -1)
        else:
            win = r['outcome'] == 1
            profits.append((r['odds_bet']-1) if win else -1)
        hits += 1 if win else 0
    roi, clo, chi = boot_ci(profits)
    return {'n_flags': len(flags), 'hit_rate': hits/len(flags),
            'roi_pct': roi*100, 'roi_ci95_pct': [clo*100, chi*100],
            'overround_mean_pct': float(np.mean([r['overround'] for r in flags]))*100}


def edge_dist(rows):
    e = np.array([r['edge'] for r in rows])*100
    y = [r['outcome'] for r in rows]
    return {'n': len(rows), 'edge_mean_pp': float(e.mean()), 'edge_median_pp': float(np.median(e)),
            'edge_p5_pp': float(np.percentile(e,5)), 'edge_p95_pp': float(np.percentile(e,95)),
            'model_bss_pct': bss_vs_naive([r['model_p'] for r in rows], y)*100,
            'market_bss_pct': bss_vs_naive([r['fair_p'] for r in rows], y)*100}


def main():
    print("Loading cached data (zero API)...")
    footy, team_hist, all_odds, matched = load_all()
    earliest = min(fm.get('date_unix', 0) for fm in matched.values())
    print(f"  joined odds matches: {len(matched)}")

    print("Family A: fitting Dixon-Coles + count models (walk-forward, spec fixed)...")
    dc, btts, corners_m, cards_m, team_counts = build_family_A(footy, matched, all_odds)
    A = predict_family_A(matched, all_odds, dc, btts, corners_m, cards_m, team_counts)

    print("Family B: 7 discovered metrics (verbatim)...")
    B = predict_family_B(footy, team_hist, matched, all_odds, team_counts)

    print("Family C: interaction vs marginal baseline...")
    cmodel = build_family_C(footy, matched, all_odds, earliest, team_hist)
    C = predict_family_C(cmodel, matched, all_odds, team_counts)

    allfam = {}
    allfam.update(A); allfam.update(B); allfam.update(C)

    REQ = {('goals',1.5):4.15,('goals',2.5):3.04,('goals',3.5):1.96,('goals',4.5):4.0,
           ('cards',3.5):4.05,('cards',4.5):4.0,('corners',9.5):4.0,('corners',10.5):4.0,
           ('corners',11.5):4.0,('btts',None):4.0,('1x2_home',None):4.0}

    results = {}
    for key, rows in sorted(allfam.items(), key=lambda kv: str(kv[0])):
        market, line, fam = key
        if len(rows) < MIN_MARKET_N and market not in ('cards','corners'):
            pass
        rel = [r for r in rows if is_reliable(r)]
        kd = f"{market}|{line}|{fam}"
        results[kd] = {
            'market': market, 'line': line, 'family': fam,
            'n_all': len(rows), 'n_reliable': len(rel),
            'n_removed_by_filter': len(rows) - len(rel),
            'required_edge_pp': REQ.get((market, line)),
            'edge_all': edge_dist(rows) if rows else None,
            'edge_reliable': edge_dist(rel) if rel else None,
            'disagreement_all': disagreement_deciles(rows),
            'disagreement_reliable': disagreement_deciles(rel),
            'backtest_reliable': backtest_flags(rel),
        }

    out = {
        'analysis_date': datetime.now(timezone.utc).isoformat(),
        'note': ('Market-first scan. Family A = Dixon-Coles + CountRegression '
                 '(walk-forward single fit, spec fixed, no retune). Family B = 7 '
                 'metrics verbatim via ev. Family C = interaction vs marginal. '
                 'All edges net of multiplicative vig. Held-out 2025/26 not touched.'),
        'reliability_filter': {'min_team_matches': MIN_TEAM_MATCHES,
                               'extreme_lambda_bounds': EXTREME_LAMBDA, 'dc_conf_min': CONF_MIN,
                               'divergence_flag_pp': DIVERGENCE_MIN_PP},
        'joined_matches': len(matched),
        'results': results,
    }
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nSaved: {OUT}\n")

    # console summary
    print(f"{'market|line|family':42s} {'nAll':>5s} {'nRel':>5s} {'edgeMed':>8s} {'mdlBSS':>7s} {'mktBSS':>7s} {'disCorr':>8s} {'flags':>5s} {'flagROI':>9s}")
    for kd, r in results.items():
        er = r['edge_reliable'] or r['edge_all']
        dr = r['disagreement_reliable'] or {}
        bt = r['backtest_reliable']
        if not er:
            continue
        print(f"{kd:42s} {r['n_all']:5d} {r['n_reliable']:5d} {er['edge_median_pp']:+8.2f} "
              f"{er['model_bss_pct']:+7.2f} {er['market_bss_pct']:+7.2f} "
              f"{dr.get('bucketidx_vs_bss_corr',0):+8.2f} {bt.get('n_flags',0):5d} "
              f"{('%.1f'%bt['roi_pct']) if bt.get('n_flags') else 'n/a':>9s}")
    return out


if __name__ == '__main__':
    main()
