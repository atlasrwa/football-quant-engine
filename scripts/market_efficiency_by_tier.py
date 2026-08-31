"""
Lower-Tier Market Efficiency Test

Tests the hypothesis: as league tier descends, the market's own calibration
(BSS vs naive) degrades, creating exploitable gaps.

Uses FootyStats corpus odds (market averages) across all 25 leagues.
Zero API calls — entirely from cached data.

Methodology:
- Market calibration: devig implied probs, score as BSS vs naive base rate
- Overround: (1/over_odds + 1/under_odds) - 1
- Our metrics: same 7 validated metrics from the EV test (Poisson GLM + shrinkage)
- Walk-forward: train on older season, predict on newer season per league
"""

import json
import glob
import math
import warnings
import numpy as np
from collections import defaultdict
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import poisson, norm

warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

BASE_DIR = '/home/ubuntu'
CORPUS_DIR = f'{BASE_DIR}/data/discovery/corpus'
RESULTS_DIR = f'{BASE_DIR}/data/results'

# League tier classification
TIER_MAP = {
    'England Premier League': 'Tier 1 (Top 5)',
    'Spain La Liga': 'Tier 1 (Top 5)',
    'Germany Bundesliga': 'Tier 1 (Top 5)',
    'Italy Serie A': 'Tier 1 (Top 5)',
    'France Ligue 1': 'Tier 1 (Top 5)',
    'England Championship': 'Tier 2 (Second divisions)',
    'Germany 2. Bundesliga': 'Tier 2 (Second divisions)',
    'Italy Serie B': 'Tier 2 (Second divisions)',
    'France Ligue 2': 'Tier 2 (Second divisions)',
    'Netherlands Eredivisie': 'Tier 3 (Smaller top-flights)',
    'Belgium Pro League': 'Tier 3 (Smaller top-flights)',
    'Turkey Süper Lig': 'Tier 3 (Smaller top-flights)',
    'Portugal Liga NOS': 'Tier 3 (Smaller top-flights)',
    'Scotland Premiership': 'Tier 3 (Smaller top-flights)',
    'Greece Super League': 'Tier 3 (Smaller top-flights)',
    'Austria Bundesliga': 'Tier 3 (Smaller top-flights)',
    'Switzerland Super League': 'Tier 3 (Smaller top-flights)',
    'Denmark Superliga': 'Tier 4 (Nordic/small)',
    'Norway Eliteserien': 'Tier 4 (Nordic/small)',
    'Sweden Allsvenskan': 'Tier 4 (Nordic/small)',
    'Finland Veikkausliiga': 'Tier 4 (Nordic/small)',
    'Poland Ekstraklasa': 'Tier 4 (Nordic/small)',
    'Brazil Serie A': 'Tier 3 (Smaller top-flights)',
    'Australia A-League': 'Tier 4 (Nordic/small)',
    'USA MLS': 'Tier 3 (Smaller top-flights)',
}

# Markets to test
GOALS_LINES = [1.5, 2.5, 3.5]
CORNERS_LINES = [8.5, 9.5, 10.5]

# Odds field mapping
GOALS_ODDS_MAP = {
    1.5: ('odds_ft_over15', 'odds_ft_under15'),
    2.5: ('odds_ft_over25', 'odds_ft_under25'),
    3.5: ('odds_ft_over35', 'odds_ft_under35'),
}
CORNERS_ODDS_MAP = {
    8.5: ('odds_corners_over_85', 'odds_corners_under_85'),
    9.5: ('odds_corners_over_95', 'odds_corners_under_95'),
    10.5: ('odds_corners_over_105', 'odds_corners_under_105'),
}


# ═══════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════════

def load_manifest():
    with open(f'{CORPUS_DIR}/manifest.json') as f:
        return json.load(f)


def load_season_matches(season_id):
    """Load all matches for a season from the corpus."""
    matches = []
    for page in range(1, 10):
        path = f'{CORPUS_DIR}/league-matches_{{max_per_page:_300,_page:_{page},_season_id:_{season_id}}}.json'
        try:
            with open(path) as f:
                data = json.load(f)
            matches.extend(data.get('data', []))
        except FileNotFoundError:
            break
    return matches


# ═══════════════════════════════════════════════════════════════════════════════
# MARKET CALIBRATION (BSS)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_overround(over_odds, under_odds):
    """Compute overround for a two-way market."""
    if over_odds <= 1.0 or under_odds <= 1.0:
        return None
    return (1.0 / over_odds + 1.0 / under_odds) - 1.0


def devig_multiplicative(over_odds, under_odds):
    """Remove vig using multiplicative method. Returns (fair_p_over, fair_p_under)."""
    if over_odds <= 1.0 or under_odds <= 1.0:
        return None, None
    raw_over = 1.0 / over_odds
    raw_under = 1.0 / under_odds
    total = raw_over + raw_under
    return raw_over / total, raw_under / total


def compute_bss(predictions, outcomes):
    """Brier Skill Score. predictions and outcomes are arrays of probabilities/binary."""
    predictions = np.array(predictions)
    outcomes = np.array(outcomes, dtype=float)
    
    bs_model = np.mean((predictions - outcomes) ** 2)
    naive_rate = np.mean(outcomes)
    bs_naive = np.mean((naive_rate - outcomes) ** 2)
    
    if bs_naive < 1e-10:
        return 0.0, bs_model, bs_naive, naive_rate
    
    bss = 1.0 - bs_model / bs_naive
    return bss, bs_model, bs_naive, naive_rate


def bootstrap_bss_ci(predictions, outcomes, n_boot=5000, ci=0.95):
    """Bootstrap confidence interval for BSS."""
    predictions = np.array(predictions)
    outcomes = np.array(outcomes, dtype=float)
    n = len(predictions)
    
    rng = np.random.default_rng(42)
    bss_samples = []
    
    for _ in range(n_boot):
        idx = rng.choice(n, size=n, replace=True)
        p_boot = predictions[idx]
        o_boot = outcomes[idx]
        bs = np.mean((p_boot - o_boot) ** 2)
        naive = np.mean(o_boot)
        bs_naive = np.mean((naive - o_boot) ** 2)
        if bs_naive > 1e-10:
            bss_samples.append(1.0 - bs / bs_naive)
    
    if not bss_samples:
        return 0.0, 0.0
    
    bss_samples = np.sort(bss_samples)
    alpha = (1 - ci) / 2
    lo = bss_samples[int(alpha * len(bss_samples))]
    hi = bss_samples[int((1 - alpha) * len(bss_samples))]
    return float(lo), float(hi)


# ═══════════════════════════════════════════════════════════════════════════════
# POISSON GLM (same as EV test — exact reproduction)
# ═══════════════════════════════════════════════════════════════════════════════

def fit_poisson_glm_l2(X, y, l2_penalty=0.01):
    """Fit Poisson GLM with L2 regularization."""
    n, k = X.shape
    X_mean = X.mean(axis=0)
    X_std = X.std(axis=0)
    X_std[X_std == 0] = 1.0
    X_norm = (X - X_mean) / X_std
    
    def neg_ll(params):
        intercept = params[0]
        weights = params[1:]
        log_lam = intercept + X_norm @ weights
        log_lam = np.clip(log_lam, -5, 5)
        lam = np.exp(log_lam)
        ll = np.sum(y * log_lam - lam - gammaln(y + 1))
        ll -= l2_penalty * np.sum(weights ** 2)
        return -ll
    
    x0 = np.zeros(k + 1)
    x0[0] = np.log(max(0.1, np.mean(y)))
    
    result = minimize(neg_ll, x0, method='L-BFGS-B',
                     options={'maxiter': 300, 'ftol': 1e-8})
    
    intercept_norm = result.x[0]
    weights_norm = result.x[1:]
    weights_orig = weights_norm / X_std
    intercept_orig = intercept_norm - np.sum(weights_norm * X_mean / X_std)
    
    return intercept_orig, weights_orig


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE EXTRACTION (per-team rolling windows)
# ═══════════════════════════════════════════════════════════════════════════════

def build_team_histories(matches):
    """Build per-team match histories from a list of matches."""
    team_histories = defaultdict(list)
    for m in sorted(matches, key=lambda x: x.get('date_unix', 0)):
        date_unix = m.get('date_unix', 0)
        home = m.get('home_name', '')
        away = m.get('away_name', '')
        if home:
            team_histories[home].append((date_unix, m, 'home'))
        if away:
            team_histories[away].append((date_unix, m, 'away'))
    return team_histories


def extract_stat(match, role, field_name):
    """Extract a stat from a match given the team's role."""
    prefix = 'team_a_' if role == 'home' else 'team_b_'
    opp_prefix = 'team_b_' if role == 'home' else 'team_a_'
    
    if field_name == 'yellow_cards':
        v = match.get(f'{prefix}yellow_cards')
        return float(v) if v is not None and v >= 0 else None
    elif field_name == 'fouls':
        v = match.get(f'{prefix}fouls')
        return float(v) if v is not None and v >= 0 else None
    elif field_name == 'shotsOnTarget':
        v = match.get(f'{prefix}shotsOnTarget')
        return float(v) if v is not None and v >= 0 else None
    elif field_name == 'xg':
        v = match.get(f'{prefix}xg')
        return float(v) if v is not None else None
    elif field_name == 'goals':
        v = match.get('homeGoalCount') if role == 'home' else match.get('awayGoalCount')
        return float(v) if v is not None and v >= 0 else None
    elif field_name == 'overallGoalCount':
        v = match.get('overallGoalCount')
        return float(v) if v is not None and v >= 0 else None
    elif field_name == 'shotsOnTarget_conceded':
        v = match.get(f'{opp_prefix}shotsOnTarget')
        return float(v) if v is not None and v >= 0 else None
    elif field_name == 'xg_conceded':
        v = match.get(f'{opp_prefix}xg')
        return float(v) if v is not None else None
    elif field_name == '2h_cards':
        v = match.get(f'{prefix}2h_cards')
        return float(v) if v is not None and v >= 0 else None
    elif field_name == 'corners':
        # Total corners in match
        v = match.get('match_corners')
        if v is None:
            # Try computing from team-level
            ca = match.get('team_a_corners')
            cb = match.get('team_b_corners')
            if ca is not None and cb is not None:
                return float(ca + cb)
        return float(v) if v is not None and v >= 0 else None
    elif field_name == 'corners_for':
        v = match.get(f'{prefix}corners')
        return float(v) if v is not None and v >= 0 else None
    elif field_name == 'corners_against':
        v = match.get(f'{opp_prefix}corners')
        return float(v) if v is not None and v >= 0 else None
    return None


def get_team_rolling_stat(team_histories, team_name, field_name, window, before_date):
    """Get rolling average of a stat for a team before a given date."""
    history = team_histories.get(team_name, [])
    prior = [(d, m, r) for d, m, r in history if d < before_date]
    prior = prior[-window:]
    
    if len(prior) < window:
        return None
    
    values = []
    for _, m, role in prior:
        val = extract_stat(m, role, field_name)
        if val is None:
            return None
        values.append(val)
    
    return np.mean(values)


# ═══════════════════════════════════════════════════════════════════════════════
# METRIC DEFINITIONS (same 7 as EV test + 3 goals metrics reusable for corners)
# ═══════════════════════════════════════════════════════════════════════════════

GOALS_METRICS = {
    'goals_sot_xg': {
        'features': [('home', 'shotsOnTarget_conceded', 10), ('away', 'xg_conceded', 10)],
    },
    'goals_sot_count': {
        'features': [('home', 'shotsOnTarget_conceded', 10), ('away', 'overallGoalCount', 5)],
    },
    'goals_count_xg': {
        'features': [('home', 'overallGoalCount', 5), ('away', 'xg', 5)],
    },
}

CARDS_METRICS = {
    'cards_minimal_pair': {
        'features': [('home', 'yellow_cards', 5), ('away', 'yellow_cards', 5)],
    },
    'cards_best_pair': {
        'features': [('home', 'yellow_cards', 5), ('away', 'yellow_cards', 10)],
    },
    'cards_with_fouls': {
        'features': [('away', 'yellow_cards', 10), ('home', 'fouls', 5)],
    },
    'cards_triple_halfsplit': {
        'features': [('home', 'yellow_cards', 5), ('away', 'yellow_cards', 10), ('away', '2h_cards', 10)],
    },
}

CORNERS_METRICS = {
    'corners_for_against': {
        'features': [('home', 'corners_for', 5), ('away', 'corners_for', 5)],
    },
    'corners_total_history': {
        'features': [('home', 'corners_for', 10), ('away', 'corners_against', 10)],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# WALK-FORWARD MODEL PREDICTION
# ═══════════════════════════════════════════════════════════════════════════════

def compute_metric_predictions_walkforward(metric_def, train_matches, test_matches,
                                            target_field, team_histories):
    """
    Walk-forward: fit on train_matches, predict on test_matches.
    Returns list of (predicted_lambda, actual_count) for test matches.
    """
    feature_defs = metric_def['features']
    
    # Build training set
    training_X = []
    training_y = []
    
    for m in train_matches:
        date_unix = m.get('date_unix', 0)
        home = m.get('home_name', '')
        away = m.get('away_name', '')
        
        features = []
        valid = True
        for (side, stat_name, window) in feature_defs:
            team = home if side == 'home' else away
            val = get_team_rolling_stat(team_histories, team, stat_name, window, date_unix)
            if val is None:
                valid = False
                break
            features.append(val)
        
        if not valid:
            continue
        
        if target_field == 'total_goals':
            target_val = m.get('overallGoalCount', 0) or 0
        elif target_field == 'total_cards':
            ya = m.get('team_a_yellow_cards', 0) or 0
            yb = m.get('team_b_yellow_cards', 0) or 0
            ra = m.get('team_a_red_cards', 0) or 0
            rb = m.get('team_b_red_cards', 0) or 0
            target_val = ya + yb + ra + rb
        elif target_field == 'total_corners':
            ca = m.get('team_a_corners')
            cb = m.get('team_b_corners')
            if ca is None or cb is None:
                continue
            target_val = ca + cb
        else:
            continue
        
        training_X.append(features)
        training_y.append(target_val)
    
    if len(training_X) < 30:
        return None
    
    X_train = np.array(training_X)
    y_train = np.array(training_y, dtype=float)
    
    # Fit model
    try:
        intercept, weights = fit_poisson_glm_l2(X_train, y_train, l2_penalty=0.01)
    except:
        return None
    
    # Predict on test matches
    results = []
    for m in test_matches:
        date_unix = m.get('date_unix', 0)
        home = m.get('home_name', '')
        away = m.get('away_name', '')
        
        features = []
        valid = True
        for (side, stat_name, window) in feature_defs:
            team = home if side == 'home' else away
            val = get_team_rolling_stat(team_histories, team, stat_name, window, date_unix)
            if val is None:
                valid = False
                break
            features.append(val)
        
        if not valid:
            continue
        
        # Get actual outcome
        if target_field == 'total_goals':
            actual = m.get('overallGoalCount', 0) or 0
        elif target_field == 'total_cards':
            ya = m.get('team_a_yellow_cards', 0) or 0
            yb = m.get('team_b_yellow_cards', 0) or 0
            ra = m.get('team_a_red_cards', 0) or 0
            rb = m.get('team_b_red_cards', 0) or 0
            actual = ya + yb + ra + rb
        elif target_field == 'total_corners':
            ca = m.get('team_a_corners')
            cb = m.get('team_b_corners')
            if ca is None or cb is None:
                continue
            actual = ca + cb
        else:
            continue
        
        # Predict lambda
        log_lam = intercept + np.dot(weights, np.array(features))
        log_lam = np.clip(log_lam, -3, 4)
        lam = np.exp(log_lam)
        
        results.append({'lambda': float(lam), 'actual': int(actual), 'match': m})
    
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ANALYSIS
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_league(league_name, train_season_id, test_season_id, year):
    """Run full analysis for one league."""
    # Load both seasons
    train_matches = load_season_matches(train_season_id)
    test_matches = load_season_matches(test_season_id)
    
    if not train_matches or not test_matches:
        return None
    
    # Sort by date
    train_matches.sort(key=lambda m: m.get('date_unix', 0))
    test_matches.sort(key=lambda m: m.get('date_unix', 0))
    
    # Build team histories from BOTH seasons (all data feeds rolling windows)
    all_matches = train_matches + test_matches
    all_matches.sort(key=lambda m: m.get('date_unix', 0))
    team_histories = build_team_histories(all_matches)
    
    results = {
        'league': league_name,
        'tier': TIER_MAP.get(league_name, 'Unknown'),
        'test_year': year,
        'n_test_matches': len(test_matches),
        'markets': {}
    }
    
    # ─── GOALS MARKETS ───────────────────────────────────────────────────────
    for line in GOALS_LINES:
        over_field, under_field = GOALS_ODDS_MAP[line]
        
        market_probs = []
        outcomes = []
        overrounds = []
        
        for m in test_matches:
            over_odds = m.get(over_field)
            under_odds = m.get(under_field)
            actual_goals = m.get('overallGoalCount')
            
            if not over_odds or not under_odds or over_odds <= 1 or under_odds <= 1:
                continue
            if actual_goals is None:
                continue
            
            fair_over, fair_under = devig_multiplicative(over_odds, under_odds)
            if fair_over is None:
                continue
            
            ov = compute_overround(over_odds, under_odds)
            
            market_probs.append(fair_over)
            outcomes.append(1.0 if actual_goals > line else 0.0)
            overrounds.append(ov if ov is not None else 0)
        
        if len(market_probs) < 20:
            continue
        
        # Market BSS
        market_bss, bs_market, bs_naive, naive_rate = compute_bss(market_probs, outcomes)
        bss_ci_lo, bss_ci_hi = bootstrap_bss_ci(market_probs, outcomes)
        
        market_result = {
            'line': f'goals_{line}',
            'n': len(market_probs),
            'market_bss': market_bss,
            'market_bss_ci': [bss_ci_lo, bss_ci_hi],
            'overround_mean': np.mean(overrounds),
            'overround_std': np.std(overrounds),
            'naive_rate': naive_rate,
            'metric_results': {}
        }
        
        # ─── OUR METRICS vs MARKET ──────────────────────────────────────────
        for metric_name, metric_def in GOALS_METRICS.items():
            preds = compute_metric_predictions_walkforward(
                metric_def, train_matches, test_matches, 'total_goals', team_histories
            )
            if preds is None or len(preds) < 20:
                continue
            
            # Align predictions with odds matches
            # We need to match by the test match identity
            # Since both come from test_matches, align by date+teams
            pred_lookup = {}
            for p in preds:
                m = p['match']
                key = (m.get('home_name', ''), m.get('away_name', ''), m.get('date_unix', 0))
                pred_lookup[key] = p
            
            metric_probs = []
            metric_outcomes = []
            aligned_market_probs = []
            aligned_odds = []
            
            for m in test_matches:
                over_odds = m.get(over_field)
                under_odds = m.get(under_field)
                actual_goals = m.get('overallGoalCount')
                
                if not over_odds or not under_odds or over_odds <= 1 or under_odds <= 1:
                    continue
                if actual_goals is None:
                    continue
                
                key = (m.get('home_name', ''), m.get('away_name', ''), m.get('date_unix', 0))
                if key not in pred_lookup:
                    continue
                
                p = pred_lookup[key]
                lam = p['lambda']
                # P(goals > line)
                p_over = 1.0 - poisson.cdf(int(line), lam)
                p_over = np.clip(p_over, 0.01, 0.99)
                
                fair_over, _ = devig_multiplicative(over_odds, under_odds)
                if fair_over is None:
                    continue
                
                metric_probs.append(p_over)
                metric_outcomes.append(1.0 if actual_goals > line else 0.0)
                aligned_market_probs.append(fair_over)
                aligned_odds.append(over_odds)
            
            if len(metric_probs) < 20:
                continue
            
            # Metric BSS
            metric_bss, _, _, _ = compute_bss(metric_probs, metric_outcomes)
            metric_bss_ci_lo, metric_bss_ci_hi = bootstrap_bss_ci(metric_probs, metric_outcomes)
            
            # Market BSS on same subset
            aligned_market_bss, _, _, _ = compute_bss(aligned_market_probs, metric_outcomes)
            
            # Edge: metric_prob - market_prob
            edges = np.array(metric_probs) - np.array(aligned_market_probs)
            
            # Realized return on positive-edge bets
            pos_mask = edges > 0
            n_pos = int(pos_mask.sum())
            if n_pos > 0:
                pos_outcomes = np.array(metric_outcomes)[pos_mask]
                pos_odds = np.array(aligned_odds)[pos_mask]
                profits = np.where(pos_outcomes == 1.0, pos_odds - 1.0, -1.0)
                roi = float(np.mean(profits))
                # Bootstrap ROI CI
                rng = np.random.default_rng(42)
                boot_rois = []
                for _ in range(5000):
                    idx = rng.choice(n_pos, size=n_pos, replace=True)
                    boot_rois.append(np.mean(profits[idx]))
                boot_rois = np.sort(boot_rois)
                roi_ci_lo = float(boot_rois[int(0.025 * 5000)])
                roi_ci_hi = float(boot_rois[int(0.975 * 5000)])
            else:
                roi = 0.0
                roi_ci_lo = 0.0
                roi_ci_hi = 0.0
            
            market_result['metric_results'][metric_name] = {
                'n': len(metric_probs),
                'metric_bss': metric_bss,
                'metric_bss_ci': [metric_bss_ci_lo, metric_bss_ci_hi],
                'aligned_market_bss': aligned_market_bss,
                'delta_bss': metric_bss - aligned_market_bss,
                'edge_mean': float(np.mean(edges)),
                'edge_std': float(np.std(edges)),
                'n_positive_ev': n_pos,
                'realized_roi': roi,
                'roi_ci': [roi_ci_lo, roi_ci_hi],
            }
        
        results['markets'][f'goals_{line}'] = market_result
    
    # ─── CORNERS MARKETS ─────────────────────────────────────────────────────
    for line in CORNERS_LINES:
        over_field, under_field = CORNERS_ODDS_MAP[line]
        
        market_probs = []
        outcomes = []
        overrounds = []
        
        for m in test_matches:
            over_odds = m.get(over_field)
            under_odds = m.get(under_field)
            
            if not over_odds or not under_odds or over_odds <= 1 or under_odds <= 1:
                continue
            
            # Total corners
            ca = m.get('team_a_corners')
            cb = m.get('team_b_corners')
            if ca is None or cb is None:
                continue
            total_corners = ca + cb
            
            fair_over, _ = devig_multiplicative(over_odds, under_odds)
            if fair_over is None:
                continue
            
            ov = compute_overround(over_odds, under_odds)
            
            market_probs.append(fair_over)
            outcomes.append(1.0 if total_corners > line else 0.0)
            overrounds.append(ov if ov is not None else 0)
        
        if len(market_probs) < 20:
            continue
        
        market_bss, _, _, naive_rate = compute_bss(market_probs, outcomes)
        bss_ci_lo, bss_ci_hi = bootstrap_bss_ci(market_probs, outcomes)
        
        market_result = {
            'line': f'corners_{line}',
            'n': len(market_probs),
            'market_bss': market_bss,
            'market_bss_ci': [bss_ci_lo, bss_ci_hi],
            'overround_mean': np.mean(overrounds),
            'overround_std': np.std(overrounds),
            'naive_rate': naive_rate,
            'metric_results': {}
        }
        
        # Corner metrics
        for metric_name, metric_def in CORNERS_METRICS.items():
            preds = compute_metric_predictions_walkforward(
                metric_def, train_matches, test_matches, 'total_corners', team_histories
            )
            if preds is None or len(preds) < 20:
                continue
            
            pred_lookup = {}
            for p in preds:
                m_p = p['match']
                key = (m_p.get('home_name', ''), m_p.get('away_name', ''), m_p.get('date_unix', 0))
                pred_lookup[key] = p
            
            metric_probs = []
            metric_outcomes = []
            aligned_market_probs = []
            aligned_odds = []
            
            for m in test_matches:
                over_odds = m.get(over_field)
                under_odds = m.get(under_field)
                
                if not over_odds or not under_odds or over_odds <= 1 or under_odds <= 1:
                    continue
                
                ca = m.get('team_a_corners')
                cb = m.get('team_b_corners')
                if ca is None or cb is None:
                    continue
                total_corners = ca + cb
                
                key = (m.get('home_name', ''), m.get('away_name', ''), m.get('date_unix', 0))
                if key not in pred_lookup:
                    continue
                
                p = pred_lookup[key]
                lam = p['lambda']
                p_over = 1.0 - poisson.cdf(int(line), lam)
                p_over = np.clip(p_over, 0.01, 0.99)
                
                fair_over, _ = devig_multiplicative(over_odds, under_odds)
                if fair_over is None:
                    continue
                
                metric_probs.append(p_over)
                metric_outcomes.append(1.0 if total_corners > line else 0.0)
                aligned_market_probs.append(fair_over)
                aligned_odds.append(over_odds)
            
            if len(metric_probs) < 20:
                continue
            
            metric_bss, _, _, _ = compute_bss(metric_probs, metric_outcomes)
            metric_bss_ci_lo, metric_bss_ci_hi = bootstrap_bss_ci(metric_probs, metric_outcomes)
            aligned_market_bss, _, _, _ = compute_bss(aligned_market_probs, metric_outcomes)
            
            edges = np.array(metric_probs) - np.array(aligned_market_probs)
            pos_mask = edges > 0
            n_pos = int(pos_mask.sum())
            if n_pos > 0:
                pos_outcomes = np.array(metric_outcomes)[pos_mask]
                pos_odds = np.array(aligned_odds)[pos_mask]
                profits = np.where(pos_outcomes == 1.0, pos_odds - 1.0, -1.0)
                roi = float(np.mean(profits))
                rng = np.random.default_rng(42)
                boot_rois = []
                for _ in range(5000):
                    idx = rng.choice(n_pos, size=n_pos, replace=True)
                    boot_rois.append(np.mean(profits[idx]))
                boot_rois = np.sort(boot_rois)
                roi_ci_lo = float(boot_rois[int(0.025 * 5000)])
                roi_ci_hi = float(boot_rois[int(0.975 * 5000)])
            else:
                roi = 0.0
                roi_ci_lo = 0.0
                roi_ci_hi = 0.0
            
            market_result['metric_results'][metric_name] = {
                'n': len(metric_probs),
                'metric_bss': metric_bss,
                'metric_bss_ci': [metric_bss_ci_lo, metric_bss_ci_hi],
                'aligned_market_bss': aligned_market_bss,
                'delta_bss': metric_bss - aligned_market_bss,
                'edge_mean': float(np.mean(edges)),
                'edge_std': float(np.std(edges)),
                'n_positive_ev': n_pos,
                'realized_roi': roi,
                'roi_ci': [roi_ci_lo, roi_ci_hi],
            }
        
        results['markets'][f'corners_{line}'] = market_result
    
    # ─── CARDS (outcomes only, no odds — measure metric BSS vs naive) ────────
    # We compute card metrics but can only measure BSS vs naive (no market to compare)
    for line in [3.5, 4.5]:
        card_preds_all = {}
        for metric_name, metric_def in CARDS_METRICS.items():
            preds = compute_metric_predictions_walkforward(
                metric_def, train_matches, test_matches, 'total_cards', team_histories
            )
            if preds and len(preds) >= 20:
                card_preds_all[metric_name] = preds
        
        if card_preds_all:
            # Use first available metric for sample stats
            first_preds = list(card_preds_all.values())[0]
            card_outcomes = [1.0 if p['actual'] > line else 0.0 for p in first_preds]
            naive_rate = np.mean(card_outcomes)
            
            card_result = {
                'line': f'cards_{line}',
                'n': len(first_preds),
                'market_bss': None,  # No card odds available
                'market_bss_ci': None,
                'overround_mean': None,
                'naive_rate': naive_rate,
                'metric_results': {}
            }
            
            for metric_name, preds in card_preds_all.items():
                metric_probs = []
                metric_outcomes = []
                for p in preds:
                    lam = p['lambda']
                    p_over = 1.0 - poisson.cdf(int(line), lam)
                    p_over = np.clip(p_over, 0.01, 0.99)
                    metric_probs.append(p_over)
                    metric_outcomes.append(1.0 if p['actual'] > line else 0.0)
                
                metric_bss, _, _, _ = compute_bss(metric_probs, metric_outcomes)
                ci_lo, ci_hi = bootstrap_bss_ci(metric_probs, metric_outcomes)
                
                card_result['metric_results'][metric_name] = {
                    'n': len(metric_probs),
                    'metric_bss': metric_bss,
                    'metric_bss_ci': [ci_lo, ci_hi],
                    'aligned_market_bss': None,
                    'delta_bss': None,
                }
            
            results['markets'][f'cards_{line}'] = card_result
    
    return results


def main():
    print("=" * 100)
    print("LOWER-TIER MARKET EFFICIENCY TEST")
    print("Hypothesis: Market calibration degrades in lower-tier leagues")
    print("=" * 100)
    print()
    
    manifest = load_manifest()
    
    all_results = []
    
    for league_info in manifest['leagues']:
        league = league_info['league']
        # seasons[0] = newer (test), seasons[1] = older (train)
        test_season = league_info['seasons'][0]
        train_season = league_info['seasons'][1]
        
        print(f"\n{'─'*80}")
        print(f"Processing: {league} (train={train_season['year']}, test={test_season['year']})")
        print(f"{'─'*80}")
        
        result = analyze_league(
            league, 
            train_season['season_id'], 
            test_season['season_id'],
            test_season['year']
        )
        
        if result:
            all_results.append(result)
            # Print summary for this league
            for market_key, market_data in result['markets'].items():
                mbss = market_data['market_bss']
                ov = market_data['overround_mean']
                n = market_data['n']
                if mbss is not None:
                    print(f"  {market_key:<15} n={n:>4}  market_BSS={mbss:>8.4f}  overround={ov:.4f}")
                else:
                    print(f"  {market_key:<15} n={n:>4}  market_BSS=N/A (no odds)")
    
    # Save raw results
    output_path = f'{RESULTS_DIR}/market_efficiency_by_tier.json'
    with open(output_path, 'w') as f:
        json.dump({
            'analysis_date': '2026-08-28',
            'method': 'FootyStats embedded odds (market averages), devigged multiplicative',
            'n_leagues': len(all_results),
            'api_requests_used': 0,
            'results': all_results,
        }, f, indent=2, default=str)
    print(f"\n\nResults saved to {output_path}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SUMMARY TABLE
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n")
    print("=" * 130)
    print("KEY OUTPUT TABLE: League × Market × Market BSS × Best Metric BSS × ΔBSS × Overround × n")
    print("=" * 130)
    print(f"{'League':<28} {'Market':<14} {'Mkt BSS':>8} {'95% CI':>16} {'Best Metric':>12} {'ΔBSS':>7} {'Overround':>10} {'n':>5} {'Tier'}")
    print("-" * 130)
    
    # Sort by market BSS (sloppiest first)
    rows = []
    for r in all_results:
        for market_key, market_data in r['markets'].items():
            if market_data['market_bss'] is None:
                continue
            
            # Find best metric
            best_metric_bss = None
            best_metric_name = ''
            for mname, mdata in market_data.get('metric_results', {}).items():
                if best_metric_bss is None or mdata['metric_bss'] > best_metric_bss:
                    best_metric_bss = mdata['metric_bss']
                    best_metric_name = mname
            
            rows.append({
                'league': r['league'],
                'tier': r['tier'],
                'market': market_key,
                'market_bss': market_data['market_bss'],
                'market_bss_ci': market_data['market_bss_ci'],
                'overround': market_data['overround_mean'],
                'n': market_data['n'],
                'best_metric_bss': best_metric_bss,
                'best_metric_name': best_metric_name,
                'delta_bss': (best_metric_bss - market_data['market_bss']) if best_metric_bss is not None else None,
            })
    
    # Sort by market BSS ascending (sloppiest markets first)
    rows.sort(key=lambda x: x['market_bss'])
    
    for row in rows:
        ci = row['market_bss_ci']
        ci_str = f"[{ci[0]:+.4f},{ci[1]:+.4f}]" if ci else "N/A"
        mbss = f"{row['best_metric_bss']:.4f}" if row['best_metric_bss'] is not None else "N/A"
        dbss = f"{row['delta_bss']:+.4f}" if row['delta_bss'] is not None else "N/A"
        print(f"{row['league']:<28} {row['market']:<14} {row['market_bss']:>+8.4f} {ci_str:>16} {mbss:>12} {dbss:>7} {row['overround']:>10.4f} {row['n']:>5} {row['tier']}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # TIER SUMMARY
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n\n")
    print("=" * 100)
    print("TIER SUMMARY — Average Market BSS by Tier and Market Type")
    print("=" * 100)
    
    from collections import defaultdict
    tier_market_bss = defaultdict(lambda: defaultdict(list))
    tier_overround = defaultdict(lambda: defaultdict(list))
    
    for row in rows:
        market_type = row['market'].rsplit('_', 1)[0]  # 'goals' or 'corners'
        tier_market_bss[row['tier']][market_type].append(row['market_bss'])
        tier_overround[row['tier']][market_type].append(row['overround'])
    
    tier_order = ['Tier 1 (Top 5)', 'Tier 2 (Second divisions)', 'Tier 3 (Smaller top-flights)', 'Tier 4 (Nordic/small)']
    
    print(f"\n{'Tier':<35} {'Market':>10} {'Avg BSS':>10} {'Std BSS':>10} {'Avg OR':>10} {'n leagues':>10}")
    print("-" * 90)
    for tier in tier_order:
        for mtype in ['goals', 'corners']:
            bss_vals = tier_market_bss[tier][mtype]
            or_vals = tier_overround[tier][mtype]
            if bss_vals:
                print(f"{tier:<35} {mtype:>10} {np.mean(bss_vals):>+10.4f} {np.std(bss_vals):>10.4f} {np.mean(or_vals):>10.4f} {len(bss_vals):>10}")
    
    print("\n\nDone. Zero API requests used.")


if __name__ == '__main__':
    main()
