"""
Zero-Cost EV Test: 7 Discovered Metrics vs Bet365

Tests the 7 validated metrics (4 cards, 3 goals) against cached Bet365 odds.
No API calls required — uses only cached data.

Methodology:
- Each metric uses Poisson GLM with L2 regularization (shrinkage)
- Features are rolling window averages (w5/w10) computed per-team
- Fitting is a SINGLE point-in-time train/test fit (NOT per-match
  walk-forward): the GLM is trained once on all data strictly before the
  earliest odds-sample match, coefficients are frozen, then applied to every
  odds-sample match. Point-in-time safe (no future data in training or
  per-match features), but not an expanding-window refit. See
  compute_metric_predictions for the precise scheme.
- Team-level shrinkage via empirical Bayes (shrink toward global mean)
- Vig removal: multiplicative (proportional overround removal)
- Betting: flat 1-unit stake on whichever side (over/under) the de-vigged
  edge points to (not OVER-only).
"""

import json
import os
import glob
import math
import warnings
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln
from scipy.stats import poisson, norm

warnings.filterwarnings('ignore')

# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════

BASE_DIR = '/home/ubuntu'
CORPUS_DIR = f'{BASE_DIR}/data/discovery/corpus'
ODDS_DIR = f'{BASE_DIR}/data/thestatsapi/cache'
CROSSWALK_PATH = f'{BASE_DIR}/data/mapping/team_crosswalk.json'


def load_crosswalk():
    """Load team crosswalk, returning thestats_id → footystats_name mapping."""
    with open(CROSSWALK_PATH) as f:
        data = json.load(f)
    
    thestats_to_footystats = {}
    for league, teams in data.get('leagues', {}).items():
        for team in teams:
            conf = team.get('confidence', 0)
            if conf >= 0.9:
                tid = team['thestats_id']
                fname = team['footystats_name']
                if tid not in thestats_to_footystats:
                    thestats_to_footystats[tid] = fname
    return thestats_to_footystats


def load_thestats_matches():
    """Load all TheStatsAPI match metadata."""
    matches_files = sorted(glob.glob(f'{ODDS_DIR}/matches_comp_*.json'))
    matches = {}
    for mf in matches_files:
        with open(mf) as f:
            data = json.load(f)
        for m in data['data']:
            matches[m['id']] = {
                'home_team_id': m['home_team']['id'],
                'home_team_name': m['home_team']['name'],
                'away_team_id': m['away_team']['id'],
                'away_team_name': m['away_team']['name'],
                'date': m.get('utc_date', ''),
                'score_home': m.get('score', {}).get('home'),
                'score_away': m.get('score', {}).get('away'),
            }
    return matches


def load_bet365_odds(match_ids):
    """Load Bet365 odds for given match IDs. Returns dict of match_id → odds_data."""
    odds = {}
    for mid in match_ids:
        odds_path = f'{ODDS_DIR}/odds_{mid}.json'
        if not os.path.exists(odds_path):
            continue
        with open(odds_path) as f:
            data = json.load(f)
        
        bet365 = None
        for bm in data.get('data', {}).get('bookmakers', []):
            if bm.get('bookmaker') == 'Bet365':
                bet365 = bm
                break
        
        if bet365 is None:
            continue
        
        odds[mid] = bet365.get('markets', {})
    return odds


def load_footystats_corpus():
    """Load all FootyStats matches from the corpus, sorted by date per team."""
    corpus_files = sorted(glob.glob(f'{CORPUS_DIR}/league-matches_*.json'))
    all_matches = []
    
    for cf in corpus_files:
        with open(cf) as f:
            data = json.load(f)
        if 'data' in data:
            all_matches.extend(data['data'])
    
    # Sort by date
    all_matches.sort(key=lambda m: m.get('date_unix', 0))
    return all_matches


# ═══════════════════════════════════════════════════════════════
# FEATURE COMPUTATION (ROLLING WINDOWS PER TEAM)
# ═══════════════════════════════════════════════════════════════

@dataclass
class TeamHistory:
    """Maintains rolling history for a team."""
    matches: list = field(default_factory=list)


def build_team_histories(all_matches):
    """Build per-team match histories (ordered by date).
    
    Each match is stored with the team's role (home='a' or away='b').
    This is needed because features like 'team_a_yellow_cards' refer to
    the home team's cards IN THAT MATCH.
    """
    team_histories = defaultdict(list)  # team_name → list of (date_unix, match_dict, role)
    
    for m in all_matches:
        date_unix = m.get('date_unix', 0)
        home_name = m.get('home_name', '')
        away_name = m.get('away_name', '')
        
        if home_name:
            team_histories[home_name].append((date_unix, m, 'home'))
        if away_name:
            team_histories[away_name].append((date_unix, m, 'away'))
    
    return team_histories


def get_team_rolling_stat(team_histories, team_name, field_name, window, before_date_unix):
    """Get rolling average of a stat for a team, using only matches before the given date.
    
    field_name should be one of:
    - 'yellow_cards': uses team_a_yellow_cards when home, team_b when away
    - 'fouls': uses team_a_fouls when home, team_b when away
    - 'shotsOnTarget': uses team_a_shotsOnTarget when home, team_b when away
    - 'xg': uses team_a_xg when home, team_b_xg when away
    - 'goals': uses homeGoalCount when home, awayGoalCount when away
    - 'overallGoalCount': total goals in match regardless of role
    - 'shotsOnTarget_conceded': uses team_b_shotsOnTarget when home, team_a when away
    - 'xg_conceded': uses team_b_xg when home, team_a_xg when away
    - '2h_cards': uses team_a_2h_cards when home, team_b_2h_cards when away
    """
    history = team_histories.get(team_name, [])
    
    # Get matches before this date
    prior_matches = [(d, m, role) for d, m, role in history if d < before_date_unix]
    
    # Take last `window` matches
    prior_matches = prior_matches[-window:]
    
    if len(prior_matches) < window:
        return None
    
    values = []
    for _, m, role in prior_matches:
        val = extract_stat(m, role, field_name)
        if val is None:
            return None
        values.append(val)
    
    return np.mean(values)


def extract_stat(match, role, field_name):
    """Extract a stat from a match given the team's role (home/away)."""
    if role == 'home':
        prefix = 'team_a_'
        opp_prefix = 'team_b_'
    else:
        prefix = 'team_b_'
        opp_prefix = 'team_a_'
    
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
        if role == 'home':
            v = match.get('homeGoalCount')
        else:
            v = match.get('awayGoalCount')
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
    else:
        return None


# ═══════════════════════════════════════════════════════════════
# POISSON GLM WITH L2 REGULARIZATION
# ═══════════════════════════════════════════════════════════════

def fit_poisson_glm_l2(X, y, l2_penalty=0.01):
    """Fit Poisson GLM with L2 regularization via MLE.
    
    log(lambda) = intercept + X @ weights
    
    Args:
        X: Feature matrix (n_samples, n_features)
        y: Target count vector (n_samples,)
        l2_penalty: L2 regularization strength
    
    Returns:
        (intercept, weights) tuple
    """
    n, k = X.shape
    
    # Standardize features for stable optimization
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
        # Poisson log-likelihood
        ll = np.sum(y * log_lam - lam - gammaln(y + 1))
        # L2 regularization on weights (not intercept)
        ll -= l2_penalty * np.sum(weights ** 2)
        return -ll
    
    x0 = np.zeros(k + 1)
    x0[0] = np.log(max(0.1, np.mean(y)))
    
    result = minimize(neg_ll, x0, method='L-BFGS-B',
                     options={'maxiter': 300, 'ftol': 1e-8})
    
    # Convert back to original scale
    intercept_norm = result.x[0]
    weights_norm = result.x[1:]
    
    # w_orig = w_norm / std, intercept_orig = intercept_norm - sum(w_norm * mean / std)
    weights_orig = weights_norm / X_std
    intercept_orig = intercept_norm - np.sum(weights_norm * X_mean / X_std)
    
    return intercept_orig, weights_orig


def predict_poisson_prob_over(intercept, weights, features, line):
    """Predict P(count > line) using fitted Poisson GLM.
    
    Args:
        intercept: Fitted intercept
        weights: Fitted weight vector
        features: Feature vector for one match
        line: The over/under line (e.g., 3.5 or 4.5)
    
    Returns:
        P(count > line)
    """
    log_lam = intercept + np.dot(weights, features)
    log_lam = np.clip(log_lam, -3, 4)  # Reasonable range
    lam = np.exp(log_lam)
    
    # P(X > line) = 1 - P(X <= floor(line))
    p_under = poisson.cdf(int(line), lam)
    p_over = 1.0 - p_under
    
    # Clip to avoid degenerate probabilities
    return np.clip(p_over, 0.01, 0.99)


# ═══════════════════════════════════════════════════════════════
# TEAM-LEVEL SHRINKAGE
# ═══════════════════════════════════════════════════════════════

def compute_team_shrinkage_effects(team_histories, target_field, before_date_unix, min_matches=5):
    """Compute team-level effects with shrinkage toward global mean.
    
    For each team, compute their mean target count from matches before
    the given date, then shrink toward the global mean using empirical Bayes.
    
    Shrinkage factor = n_team / (n_team + shrinkage_strength)
    where shrinkage_strength = 10 (matches worth of global prior)
    """
    SHRINKAGE_STRENGTH = 10.0
    
    team_means = {}
    all_values = []
    
    for team_name, history in team_histories.items():
        prior = [(d, m, role) for d, m, role in history if d < before_date_unix]
        if len(prior) < min_matches:
            continue
        
        values = []
        for _, m, role in prior[-30:]:  # Use last 30 matches max
            if target_field == 'total_cards':
                ya = m.get('team_a_yellow_cards', 0) or 0
                yb = m.get('team_b_yellow_cards', 0) or 0
                ra = m.get('team_a_red_cards', 0) or 0
                rb = m.get('team_b_red_cards', 0) or 0
                val = ya + yb + ra + rb
            elif target_field == 'total_goals':
                val = m.get('overallGoalCount', 0) or 0
            else:
                val = 0
            values.append(val)
            all_values.append(val)
        
        if values:
            team_means[team_name] = np.mean(values)
    
    if not all_values:
        return {}
    
    global_mean = np.mean(all_values)
    
    # Apply shrinkage
    team_effects = {}
    for team_name, team_mean in team_means.items():
        n = len([1 for d, m, r in team_histories[team_name] if d < before_date_unix][-30:])
        shrinkage = n / (n + SHRINKAGE_STRENGTH)
        shrunk_mean = shrinkage * team_mean + (1 - shrinkage) * global_mean
        if shrunk_mean > 0 and global_mean > 0:
            team_effects[team_name] = math.log(shrunk_mean / global_mean)
        else:
            team_effects[team_name] = 0.0
    
    return team_effects


# ═══════════════════════════════════════════════════════════════
# METRIC DEFINITIONS
# ═══════════════════════════════════════════════════════════════

METRICS = {
    'cards_minimal_pair': {
        'name': 'Team card rates (home+away, w5)',
        'target': 'total_cards',
        'features': [
            ('home', 'yellow_cards', 5),   # team_a_yellow_cards_w5
            ('away', 'yellow_cards', 5),   # team_b_yellow_cards_w5
        ],
        'lines': [3.5, 4.5],
    },
    'cards_best_pair': {
        'name': 'Team card rates (home w5 + away w10)',
        'target': 'total_cards',
        'features': [
            ('home', 'yellow_cards', 5),   # team_a_yellow_cards_w5
            ('away', 'yellow_cards', 10),  # team_b_yellow_cards_w10
        ],
        'lines': [3.5, 4.5],
    },
    'cards_with_fouls': {
        'name': 'Card rates + foul rate (b_cards_w10 + a_fouls_w5)',
        'target': 'total_cards',
        'features': [
            ('away', 'yellow_cards', 10),  # team_b_yellow_cards_w10
            ('home', 'fouls', 5),          # team_a_fouls_w5
        ],
        'lines': [3.5, 4.5],
    },
    'cards_triple_halfsplit': {
        'name': 'Cards triple with half-split (a_w5 + b_w10 + b_2h_w10)',
        'target': 'total_cards',
        'features': [
            ('home', 'yellow_cards', 5),   # team_a_yellow_cards_w5
            ('away', 'yellow_cards', 10),  # team_b_yellow_cards_w10
            ('away', '2h_cards', 10),      # team_b_2h_cards_w10
        ],
        'lines': [3.5, 4.5],
    },
    'goals_sot_xg': {
        'name': 'Defensive vulnerability (SOT + xG conceded, w10)',
        'target': 'total_goals',
        'features': [
            ('home', 'shotsOnTarget_conceded', 10),  # home_team_b_shotsOnTarget_w10
            ('away', 'xg_conceded', 10),              # away_team_b_xg_w10
        ],
        'lines': [1.5, 2.5, 3.5],
    },
    'goals_sot_count': {
        'name': 'SOT conceded + goal history (w10 + w5)',
        'target': 'total_goals',
        'features': [
            ('home', 'shotsOnTarget_conceded', 10),  # home_team_b_shotsOnTarget_w10
            ('away', 'overallGoalCount', 5),          # away_overallGoalCount_w5
        ],
        'lines': [1.5, 2.5, 3.5],
    },
    'goals_count_xg': {
        'name': 'Goal count + xG (w5)',
        'target': 'total_goals',
        'features': [
            ('home', 'overallGoalCount', 5),  # home_overallGoalCount_w5
            ('away', 'xg', 5),                 # away_team_a_xg_w5
        ],
        'lines': [1.5, 2.5, 3.5],
    },
}


# ═══════════════════════════════════════════════════════════════
# MATCH JOINING (FootyStats ↔ TheStatsAPI via crosswalk)
# ═══════════════════════════════════════════════════════════════

def join_matches(thestats_matches, crosswalk, footystats_matches):
    """Join TheStatsAPI matches to FootyStats matches via crosswalk + date.
    
    Strategy:
    1. Map thestats team_id → footystats team_name via crosswalk
    2. For each TheStatsAPI match, find FootyStats match with same teams and ±1 day
    
    Returns: dict of thestats_match_id → footystats_match (or None)
    """
    # Build FootyStats index: (home_name, away_name) → list of (date_unix, match)
    fs_index = defaultdict(list)
    for m in footystats_matches:
        home = m.get('home_name', '')
        away = m.get('away_name', '')
        date_unix = m.get('date_unix', 0)
        if home and away and date_unix:
            fs_index[(home, away)].append((date_unix, m))
    
    # Join
    joined = {}
    join_failures = []
    
    for mid, info in thestats_matches.items():
        home_tid = info['home_team_id']
        away_tid = info['away_team_id']
        
        home_fs_name = crosswalk.get(home_tid)
        away_fs_name = crosswalk.get(away_tid)
        
        if not home_fs_name or not away_fs_name:
            join_failures.append((mid, 'crosswalk_miss', info))
            continue
        
        # Parse TheStatsAPI date
        date_str = info.get('date', '')
        if not date_str:
            join_failures.append((mid, 'no_date', info))
            continue
        
        try:
            ts_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            ts_unix = int(ts_date.timestamp())
        except:
            join_failures.append((mid, 'bad_date', info))
            continue
        
        # Search FootyStats for matching match (±1 day = 86400 seconds)
        candidates = fs_index.get((home_fs_name, away_fs_name), [])
        best_match = None
        best_diff = float('inf')
        
        for fs_unix, fs_match in candidates:
            diff = abs(fs_unix - ts_unix)
            if diff < best_diff and diff <= 86400:
                best_diff = diff
                best_match = fs_match
        
        if best_match:
            joined[mid] = best_match
        else:
            join_failures.append((mid, 'no_fs_match', {
                'home': home_fs_name, 'away': away_fs_name, 
                'date': date_str
            }))
    
    return joined, join_failures


# ═══════════════════════════════════════════════════════════════
# POINT-IN-TIME MODEL FITTING AND PREDICTION (single train/test fit)
# ═══════════════════════════════════════════════════════════════

def compute_metric_predictions(metric_def, matched_matches, team_histories, 
                                footystats_matches):
    """Compute predictions for a metric across all matched matches.

    Fitting scheme: SINGLE point-in-time train/test fit (NOT per-match
    walk-forward). We fit the Poisson GLM ONCE on all footystats matches
    dated strictly before the earliest odds-sample match, then apply those
    frozen coefficients to every odds-sample match.

    This is point-in-time safe — the training set contains only matches that
    predate the entire evaluation window, and per-match features
    (``get_team_rolling_stat``) use only data before each match. It is NOT a
    walk-forward / expanding-window refit: the GLM coefficients are frozen at
    the earliest odds-match date and never updated across the test season.

    If a genuine walk-forward is required later, refit inside the per-match
    loop on the expanding window up to each target's date. Until then this
    label must not be called "walk-forward".
    """
    target_field = metric_def['target']
    feature_defs = metric_def['features']
    
    predictions = []  # (match_id, features_vector, actual_outcome, date_unix)
    
    for mid, fs_match in matched_matches.items():
        date_unix = fs_match.get('date_unix', 0)
        home_name = fs_match.get('home_name', '')
        away_name = fs_match.get('away_name', '')
        
        # Compute features for this match (using only prior data)
        features = []
        feature_valid = True
        
        for (side, stat_name, window) in feature_defs:
            team_name = home_name if side == 'home' else away_name
            val = get_team_rolling_stat(team_histories, team_name, stat_name, 
                                       window, date_unix)
            if val is None:
                feature_valid = False
                break
            features.append(val)
        
        if not feature_valid:
            continue
        
        # Compute actual outcome
        if target_field == 'total_cards':
            ya = fs_match.get('team_a_yellow_cards', 0) or 0
            yb = fs_match.get('team_b_yellow_cards', 0) or 0
            ra = fs_match.get('team_a_red_cards', 0) or 0
            rb = fs_match.get('team_b_red_cards', 0) or 0
            outcome = ya + yb + ra + rb
        elif target_field == 'total_goals':
            outcome = fs_match.get('overallGoalCount', 0) or 0
        else:
            continue
        
        predictions.append((mid, np.array(features), outcome, date_unix, 
                           home_name, away_name))
    
    if len(predictions) < 10:
        return None
    
    # Sort by date (point-in-time ordering; train set is everything before the
    # earliest odds match — a single frozen fit, not a per-match refit)
    predictions.sort(key=lambda x: x[3])
    
    # Fit model on ALL footystats data before the earliest odds match
    # This uses the full training corpus (discovery + prior seasons)
    earliest_date = predictions[0][3]
    
    # Build training data from ALL prior footystats matches
    training_X = []
    training_y = []
    
    for m in footystats_matches:
        m_date = m.get('date_unix', 0)
        if m_date >= earliest_date:
            continue
        
        home_name = m.get('home_name', '')
        away_name = m.get('away_name', '')
        
        # Compute features
        features = []
        valid = True
        for (side, stat_name, window) in feature_defs:
            team_name = home_name if side == 'home' else away_name
            val = get_team_rolling_stat(team_histories, team_name, stat_name,
                                       window, m_date)
            if val is None:
                valid = False
                break
            features.append(val)
        
        if not valid:
            continue
        
        # Target
        if target_field == 'total_cards':
            ya = m.get('team_a_yellow_cards', 0) or 0
            yb = m.get('team_b_yellow_cards', 0) or 0
            ra = m.get('team_a_red_cards', 0) or 0
            rb = m.get('team_b_red_cards', 0) or 0
            target_val = ya + yb + ra + rb
        elif target_field == 'total_goals':
            target_val = m.get('overallGoalCount', 0) or 0
        else:
            continue
        
        training_X.append(features)
        training_y.append(target_val)
    
    if len(training_X) < 50:
        return None
    
    X_train = np.array(training_X)
    y_train = np.array(training_y, dtype=float)
    
    # Fit Poisson GLM with L2
    intercept, weights = fit_poisson_glm_l2(X_train, y_train, l2_penalty=0.01)
    
    # Generate predictions for all matched matches
    results = []
    for (mid, features, outcome, date_unix, home, away) in predictions:
        # Predict lambda
        log_lam = intercept + np.dot(weights, features)
        log_lam = np.clip(log_lam, -3, 4)
        lam = np.exp(log_lam)
        
        # Add team shrinkage effect
        team_effects = compute_team_shrinkage_effects(
            team_histories, target_field, date_unix, min_matches=5
        )
        home_effect = team_effects.get(home, 0.0)
        away_effect = team_effects.get(away, 0.0)
        # Average the two team effects (both teams contribute to match total)
        team_adj = (home_effect + away_effect) * 0.5
        lam_adj = lam * np.exp(team_adj)
        
        results.append({
            'match_id': mid,
            'features': features.tolist(),
            'actual_count': outcome,
            'predicted_lambda': float(lam_adj),
            'date_unix': date_unix,
            'home': home,
            'away': away,
        })
    
    return results


# ═══════════════════════════════════════════════════════════════
# EV CALCULATION
# ═══════════════════════════════════════════════════════════════

def compute_overround(over_odds, under_odds):
    """Compute overround for a two-way market."""
    if over_odds <= 1.0 or under_odds <= 1.0:
        return None
    return (1.0 / over_odds + 1.0 / under_odds) - 1.0


def devig_multiplicative(over_odds, under_odds):
    """Remove vig using multiplicative (proportional) method.
    
    fair_p = raw_p / sum(raw_p)
    """
    if over_odds <= 1.0 or under_odds <= 1.0:
        return None, None
    raw_over = 1.0 / over_odds
    raw_under = 1.0 / under_odds
    total = raw_over + raw_under
    return raw_over / total, raw_under / total


def compute_bss(predictions, actuals, line):
    """Compute Brier Skill Score for a set of probability predictions.
    
    BSS = 1 - BS_model / BS_naive
    where BS = mean((p - outcome)^2)
    
    Returns (bss, bs_model, bs_naive)
    """
    outcomes = np.array([1.0 if a > line else 0.0 for a in actuals])
    predictions = np.array(predictions)
    
    bs_model = np.mean((predictions - outcomes) ** 2)
    naive_rate = np.mean(outcomes)
    bs_naive = np.mean((naive_rate - outcomes) ** 2)
    
    if bs_naive == 0:
        return 0.0, bs_model, bs_naive
    
    bss = 1.0 - bs_model / bs_naive
    return bss, bs_model, bs_naive


def compute_market_bss(fair_probs, actuals, line):
    """Compute BSS using market (de-vigged) probabilities as predictions."""
    outcomes = np.array([1.0 if a > line else 0.0 for a in actuals])
    fair_probs = np.array(fair_probs)
    
    bs_market = np.mean((fair_probs - outcomes) ** 2)
    naive_rate = np.mean(outcomes)
    bs_naive = np.mean((naive_rate - outcomes) ** 2)
    
    if bs_naive == 0:
        return 0.0, bs_market, bs_naive
    
    bss = 1.0 - bs_market / bs_naive
    return bss, bs_market, bs_naive


def bootstrap_return_ci(edges, odds_vals, n_bootstrap=10000, ci=0.95):
    """Bootstrap confidence interval for realized return.
    
    Realized return = mean(edge_i * (odds_i - 1) / odds_i) for positive-EV bets
    Actually simpler: if you bet 1 unit on every +EV opportunity:
    Return = sum(won_i * (odds_i - 1) - lost_i * 1) / n_bets
    
    But we want theoretical return based on model probabilities:
    For each positive-EV match, expected profit = p_model * odds - 1
    """
    # Only positive-EV bets
    pos_ev_mask = np.array(edges) > 0
    if pos_ev_mask.sum() == 0:
        return 0.0, 0.0, 0.0, 0
    
    pos_edges = np.array(edges)[pos_ev_mask]
    pos_odds = np.array(odds_vals)[pos_ev_mask]
    n_pos = len(pos_edges)
    
    # Expected return per bet for positive EV = model_prob * odds - 1
    # But we have edge = model_prob - fair_prob, so:
    # EV = model_prob * odds - 1 = (fair_prob + edge) * odds - 1
    # Since fair_prob * odds = odds/sum_implied ≈ 1/(1+overround/2) * odds / odds = ... 
    # Simpler: just use EV directly: EV_i = edge_i * odds_i (approximately)
    # Actually EV = p_model * odds - 1, and edge = p_model - p_fair
    # So EV = (p_fair + edge) * odds - 1
    # But p_fair ≈ 1/odds * (1/(1+overround)), so p_fair * odds ≈ 1/(1+overround) < 1
    # So EV ≈ edge * odds + p_fair * odds - 1 ≈ edge * odds - overround/(1+overround)
    
    # For simplicity and correctness, let's just report:
    # mean_edge among positive-EV bets (the signal)
    # and theoretical flat-bet return based on actual outcomes
    
    # Bootstrap the mean edge
    rng = np.random.default_rng(42)
    means = []
    for _ in range(n_bootstrap):
        idx = rng.choice(n_pos, size=n_pos, replace=True)
        means.append(np.mean(pos_edges[idx]))
    
    means = np.sort(means)
    alpha = (1 - ci) / 2
    lo = means[int(alpha * n_bootstrap)]
    hi = means[int((1 - alpha) * n_bootstrap)]
    
    return float(np.mean(pos_edges)), float(lo), float(hi), n_pos


def simulate_flat_bet_return(sides, odds_vals, actuals, line):
    """Simulate flat-bet return, betting whichever side the edge points to.

    Each input row is an already-selected +EV bet. ``sides[i]`` says which side
    of the ``line`` the model backed for match ``i`` — either ``'over'`` or
    ``'under'`` — and ``odds_vals[i]`` are the decimal odds for THAT side.

    For each bet of 1 unit:
    - OVER wins if actual > line  (profit = odds - 1), else loses 1 unit
    - UNDER wins if actual <= line (profit = odds - 1), else loses 1 unit

    Returns: (roi, total_profit, n_bets, ci_lo, ci_hi)

    Historical note: an earlier version graded every bet as OVER regardless of
    which side the edge favoured, silently discarding all UNDER value. It now
    grades the side actually backed.
    """
    profits = []
    for i in range(len(sides)):
        side = sides[i]
        odds = odds_vals[i]
        actual_over = 1.0 if actuals[i] > line else 0.0

        if side == 'over':
            won = actual_over == 1.0
        elif side == 'under':
            won = actual_over == 0.0
        else:
            raise ValueError(f"side must be 'over' or 'under', got {side!r}")

        profits.append((odds - 1.0) if won else -1.0)

    if not profits:
        return 0.0, 0.0, 0, 0.0, 0.0
    
    profits = np.array(profits)
    roi = np.mean(profits)
    total_profit = np.sum(profits)
    
    # Bootstrap CI for ROI
    rng = np.random.default_rng(42)
    n = len(profits)
    boot_rois = []
    for _ in range(10000):
        idx = rng.choice(n, size=n, replace=True)
        boot_rois.append(np.mean(profits[idx]))
    
    boot_rois = np.sort(boot_rois)
    ci_lo = boot_rois[int(0.025 * 10000)]
    ci_hi = boot_rois[int(0.975 * 10000)]
    
    return float(roi), float(total_profit), n, float(ci_lo), float(ci_hi)


# ═══════════════════════════════════════════════════════════════
# MAIN ANALYSIS
# ═══════════════════════════════════════════════════════════════

def main():
    print("=" * 80)
    print("ZERO-COST EV TEST: 7 DISCOVERED METRICS vs BET365")
    print("=" * 80)
    print()
    
    # Load data
    print("Loading data...")
    crosswalk = load_crosswalk()
    print(f"  Crosswalk: {len(crosswalk)} team mappings")
    
    thestats_matches = load_thestats_matches()
    print(f"  TheStatsAPI matches: {len(thestats_matches)}")
    
    footystats_matches = load_footystats_corpus()
    print(f"  FootyStats corpus: {len(footystats_matches)} matches")
    
    # Build team histories
    print("Building team histories...")
    team_histories = build_team_histories(footystats_matches)
    print(f"  Teams tracked: {len(team_histories)}")
    
    # Load target match IDs
    with open(f'{ODDS_DIR}/step2_odds_targets.json') as f:
        targets = json.load(f)
    target_ids = set(targets['match_ids'])
    
    # Filter to matches that have odds files
    odds_files = [f for f in glob.glob(f'{ODDS_DIR}/odds_mt_*.json')
                  if 'all_bookmakers' not in f and 'pinnacle' not in f]
    odds_ids = set('mt_' + os.path.basename(f).replace('odds_mt_', '').replace('.json', '') 
                   for f in odds_files)
    target_with_odds = target_ids & odds_ids
    print(f"  Targets with cached odds: {len(target_with_odds)}")
    
    # Load all Bet365 odds
    print("Loading Bet365 odds...")
    all_odds = load_bet365_odds(target_with_odds)
    print(f"  Loaded odds for {len(all_odds)} matches")
    
    # Join TheStatsAPI → FootyStats via crosswalk
    print("Joining matches via crosswalk...")
    # Only join the ones with odds
    filtered_thestats = {k: v for k, v in thestats_matches.items() if k in target_with_odds}
    matched, join_failures = join_matches(filtered_thestats, crosswalk, footystats_matches)
    print(f"  Joined successfully: {len(matched)}")
    print(f"  Join failures: {len(join_failures)}")
    
    if join_failures:
        reasons = defaultdict(int)
        for _, reason, _ in join_failures:
            reasons[reason] += 1
        for reason, count in reasons.items():
            print(f"    {reason}: {count}")
    
    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    
    # Run each metric
    all_results = {}
    
    for metric_id, metric_def in METRICS.items():
        print(f"\n{'─' * 70}")
        print(f"METRIC: {metric_def['name']}")
        print(f"  ID: {metric_id}")
        print(f"  Target: {metric_def['target']}")
        print(f"  Features: {metric_def['features']}")
        print(f"{'─' * 70}")
        
        # Compute predictions
        preds = compute_metric_predictions(
            metric_def, matched, team_histories, footystats_matches
        )
        
        if preds is None:
            print("  ⚠ INSUFFICIENT DATA — cannot compute predictions")
            all_results[metric_id] = {'status': 'insufficient_data'}
            continue
        
        print(f"  Predictions computed: {len(preds)} matches")
        
        # For each line
        metric_results = {}
        for line in metric_def['lines']:
            line_key = f"{metric_def['target'].replace('total_', '')}_{line}"
            
            # Determine odds market key
            if metric_def['target'] == 'total_cards':
                market_key = 'total_cards'
            else:
                market_key = 'total_goals'
            
            # Match predictions to odds
            matched_preds = []
            for pred in preds:
                mid = pred['match_id']
                odds_data = all_odds.get(mid, {})
                
                market = odds_data.get(market_key, {})
                line_data = market.get(str(line))
                
                if line_data is None:
                    continue
                
                over_odds_str = line_data.get('over', {}).get('last_seen')
                under_odds_str = line_data.get('under', {}).get('last_seen')
                
                if over_odds_str is None or under_odds_str is None:
                    continue
                
                over_odds = float(over_odds_str)
                under_odds = float(under_odds_str)
                
                if over_odds <= 1.0 or under_odds <= 1.0:
                    continue
                
                matched_preds.append({
                    **pred,
                    'over_odds': over_odds,
                    'under_odds': under_odds,
                })
            
            n_matched = len(matched_preds)
            if n_matched < 5:
                print(f"\n  Line {line}: n={n_matched} — INSUFFICIENT (need ≥5)")
                metric_results[line_key] = {'status': 'insufficient', 'n': n_matched}
                continue
            
            # Compute probabilities and edges
            model_probs_over = []
            fair_probs_over = []
            edges = []
            actuals = []
            over_odds_list = []
            under_odds_list = []
            overrounds = []
            # Per-match best +EV side selection (bet the side the edge points to)
            bet_sides = []      # 'over' or 'under' — the side with the larger positive edge
            bet_edges = []      # edge on the backed side (may be <= 0 if neither side +EV)
            bet_odds = []       # decimal odds for the backed side

            for mp in matched_preds:
                lam = mp['predicted_lambda']
                p_over = 1.0 - poisson.cdf(int(line), lam)
                p_over = np.clip(p_over, 0.01, 0.99)
                p_under = 1.0 - p_over

                over_odds = mp['over_odds']
                under_odds = mp['under_odds']

                fair_over, fair_under = devig_multiplicative(over_odds, under_odds)
                overround = compute_overround(over_odds, under_odds)

                edge_over = p_over - fair_over
                edge_under = p_under - fair_under

                # Bet whichever side the edge points to (larger positive edge wins)
                if edge_over >= edge_under:
                    bet_sides.append('over')
                    bet_edges.append(edge_over)
                    bet_odds.append(over_odds)
                else:
                    bet_sides.append('under')
                    bet_edges.append(edge_under)
                    bet_odds.append(under_odds)

                # OVER-side series retained for BSS (model vs market on the OVER event)
                model_probs_over.append(p_over)
                fair_probs_over.append(fair_over)
                edges.append(edge_over)
                actuals.append(mp['actual_count'])
                over_odds_list.append(over_odds)
                under_odds_list.append(under_odds)
                overrounds.append(overround)
            
            # Compute BSS — model vs naive
            model_bss, bs_model, bs_naive = compute_bss(
                model_probs_over, actuals, line
            )
            
            # Compute BSS — market vs naive
            market_bss, bs_market, _ = compute_market_bss(
                fair_probs_over, actuals, line
            )
            
            # Edge distribution
            edges_arr = np.array(edges)
            n_positive_ev = np.sum(edges_arr > 0)
            mean_edge = np.mean(edges_arr)
            median_edge = np.median(edges_arr)
            std_edge = np.std(edges_arr)
            
            # Mean overround
            mean_overround = np.mean(overrounds)
            
            # Theoretical return on +EV bets (side-aware: bet whichever side the
            # edge points to, not OVER-only)
            bet_edges_arr = np.array(bet_edges)
            bet_odds_arr = np.array(bet_odds)
            bet_sides_arr = np.array(bet_sides)
            actuals_arr = np.array(actuals)
            pos_mask = bet_edges_arr > 0
            n_positive_ev_bets = int(pos_mask.sum())
            if pos_mask.sum() > 0:
                sel_sides = bet_sides_arr[pos_mask].tolist()
                sel_odds = bet_odds_arr[pos_mask]
                sel_actuals = actuals_arr[pos_mask]
                sel_edges = bet_edges_arr[pos_mask]

                # Theoretical EV of the backed side: p_model_side * odds_side - 1.
                # For the backed side, p_model_side = fair_side + edge_side and
                # fair_side ≈ 1/odds_side after de-vig, so EV ≈ edge_side * odds_side.
                theoretical_ev = float(np.mean(sel_edges * sel_odds))

                # Actual flat-bet return, grading the side actually backed
                roi, total_profit, n_bets, ci_lo, ci_hi = simulate_flat_bet_return(
                    sel_sides, sel_odds.tolist(), sel_actuals.tolist(), line
                )
            else:
                theoretical_ev = 0.0
                roi = 0.0
                total_profit = 0.0
                n_bets = 0
                ci_lo = 0.0
                ci_hi = 0.0
            
            # Bootstrap CI for mean edge
            mean_edge_val, edge_ci_lo, edge_ci_hi, _ = bootstrap_return_ci(
                edges, over_odds_list
            )
            
            # Print results
            print(f"\n  Line {line} (n={n_matched}):")
            print(f"    Overround (mean): {mean_overround*100:.2f}%")
            print(f"    Model BSS vs naive: {model_bss*100:+.3f}%")
            print(f"    Market BSS vs naive: {market_bss*100:+.3f}%")
            print(f"    Model vs Market BSS: {(model_bss - market_bss)*100:+.3f}%")
            print(f"    Edge distribution:")
            print(f"      Mean: {mean_edge*100:+.3f}%")
            print(f"      Median: {median_edge*100:+.3f}%")
            print(f"      Std: {std_edge*100:.3f}%")
            print(f"      Positive EV: {n_positive_ev}/{n_matched} ({100*n_positive_ev/n_matched:.0f}%)")
            print(f"    Theoretical return (flat-bet +EV only, side the edge points to):")
            print(f"      N bets: {n_bets} (+EV either side; OVER-only +EV was {n_positive_ev})")
            if n_bets > 0:
                print(f"      Realized ROI: {roi*100:+.2f}% [{ci_lo*100:+.2f}%, {ci_hi*100:+.2f}%]")
                print(f"      Theoretical EV per bet: {theoretical_ev*100:+.2f}%")
            
            metric_results[line_key] = {
                'status': 'computed',
                'n': n_matched,
                'overround_mean': float(mean_overround),
                'model_bss': float(model_bss),
                'market_bss': float(market_bss),
                'model_vs_market_bss': float(model_bss - market_bss),
                'edge_mean': float(mean_edge),
                'edge_median': float(median_edge),
                'edge_std': float(std_edge),
                'n_positive_ev': int(n_positive_ev),
                'n_positive_ev_either_side': int(n_positive_ev_bets),
                'theoretical_ev_pos_bets': float(theoretical_ev) if n_bets > 0 else None,
                'realized_roi': float(roi) if n_bets > 0 else None,
                'realized_roi_ci_lo': float(ci_lo) if n_bets > 0 else None,
                'realized_roi_ci_hi': float(ci_hi) if n_bets > 0 else None,
                'n_bets': int(n_bets),
            }
        
        all_results[metric_id] = metric_results
    
    # ═══════════════════════════════════════════════════════════════
    # COVERAGE GAPS
    # ═══════════════════════════════════════════════════════════════
    
    print(f"\n\n{'=' * 80}")
    print("COVERAGE GAPS")
    print("=" * 80)
    
    # Check what couldn't be tested
    goals_markets_tested = set()
    for metric_id, metric_def in METRICS.items():
        if metric_def['target'] == 'total_goals':
            for line in metric_def['lines']:
                goals_markets_tested.add(f"goals_o{line}")
    
    print(f"\n  Goals markets tested: {sorted(goals_markets_tested)}")
    print(f"  BTTS: NOT TESTED (would need logistic model, not Poisson GLM)")
    print(f"  Clean sheet: NOT TESTED (requires separate binary model)")
    print(f"  Cards 3.5: {'TESTED' if any('3.5' in str(r) for r in all_results.values()) else 'NOT TESTED'}")
    print(f"  Cards 4.5: {'TESTED' if any('4.5' in str(r) for r in all_results.values()) else 'NOT TESTED'}")
    
    # Save results
    output = {
        'analysis_date': datetime.now(timezone.utc).isoformat(),
        'method': {
            'model': 'Poisson GLM with L2 regularization (lambda=0.01)',
            'shrinkage': 'Team-level empirical Bayes (strength=10)',
            'vig_removal': 'Multiplicative (proportional overround removal)',
            'fit_scheme': 'Single point-in-time train/test fit: train on all data '
                          'before the earliest odds match, freeze coefficients, predict '
                          'on odds matches. NOT per-match walk-forward.',
            'bet_side': 'Bet whichever side (over/under) the de-vigged edge points to.',
        },
        'sample': {
            'total_odds_matches': len(target_with_odds),
            'joined_to_footystats': len(matched),
            'join_failure_count': len(join_failures),
        },
        'results': all_results,
    }
    
    output_path = f'{BASE_DIR}/data/results/ev_test_metrics_vs_bet365.json'
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\n\nResults saved to: {output_path}")
    
    return all_results


if __name__ == '__main__':
    results = main()
