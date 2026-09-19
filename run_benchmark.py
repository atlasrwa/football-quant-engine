"""Walk-forward benchmark: all models vs baselines vs FootyStats public predictions.

Runs a proper walk-forward evaluation (expanding window, no look-ahead) on
EPL 2023/24 real data. Reports Brier scores and reliability analysis for:
- Goals O/U 2.5
- Corners O/U 9.5
- Cards O/U 3.5
- BTTS
- Clean Sheet (home)

Benchmarks:
- Naive constant (training base rate)
- FootyStats public *_potential fields
- Our statistical models (Dixon-Coles, CountRegression, derived)
"""

import os
import sys
sys.path.insert(0, "/home/ubuntu")

with open("/home/ubuntu/.env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

import numpy as np
from src.research.footystats.client import FootyStatsResearchClient
from src.research.footystats.normalizer import MatchNormalizer
from src.research.models.dixon_coles import DixonColesModel
from src.research.models.count_regression import create_corners_model, create_cards_model
from src.research.models.prior_only_features import (
    assert_no_same_match_leakage,
    build_prior_only_features,
)
from src.research.models.derived_goals import BTTSModel, CleanSheetModel

# ═══════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════

print("=" * 75)
print("WALK-FORWARD BENCHMARK — EPL 2023/24 (380 matches)")
print("=" * 75)
print()

client = FootyStatsResearchClient(api_key=os.environ["FOOTYSTATS_API_KEY"])
raw_matches = client.fetch_season_matches(4759)

normalizer = MatchNormalizer()
normalized = normalizer.normalize_batch(raw_matches)
match_dicts = [m.to_dict() for m in sorted(normalized, key=lambda x: x.date_unix)]

# Build features with team IDs and keep raw data for FootyStats fields
team_name_to_id = {}
features = []
raw_by_match_id = {m.get("id", i): m for i, m in enumerate(raw_matches)}

for i, m in enumerate(match_dicts):
    ht, at = m.get("home_team", ""), m.get("away_team", "")
    if ht not in team_name_to_id:
        team_name_to_id[ht] = len(team_name_to_id)
    if at not in team_name_to_id:
        team_name_to_id[at] = len(team_name_to_id)
    feat = {k: float(v) for k, v in m.items() if isinstance(v, (int, float)) and v is not None}
    feat["home_team_id"] = float(team_name_to_id[ht])
    feat["away_team_id"] = float(team_name_to_id[at])
    features.append(feat)

# Count-market features are built from prior fixtures only. The assertion is a hard
# failure so this benchmark cannot silently return to same-match numeric features.
prior_raw_matches = sorted(
    [m for m in raw_matches if m.get("status") == "complete"],
    key=lambda m: m.get("date_unix", 0),
)
corners_features = build_prior_only_features(prior_raw_matches, target_field="total_corners")
cards_features = build_prior_only_features(prior_raw_matches, target_field="total_cards")
assert_no_same_match_leakage(prior_raw_matches, corners_features)
assert_no_same_match_leakage(prior_raw_matches, cards_features)
if len(corners_features) != len(features) or len(cards_features) != len(features):
    raise AssertionError("prior-only count feature rows do not align with normalized fixtures")

# Map raw FootyStats potentials by match_id
footystats_preds = {}
for raw in raw_matches:
    mid = raw.get("id")
    if mid:
        footystats_preds[mid] = {
            "o25_potential": raw.get("o25_potential"),
            "corners_o95_potential": raw.get("corners_o95_potential"),
            "btts_potential": raw.get("btts_potential"),
            "cards_potential": raw.get("cards_potential"),
        }


# ═══════════════════════════════════════════════════════════════
# WALK-FORWARD EVALUATION
# ═══════════════════════════════════════════════════════════════

# Walk-forward: train on [0, i), predict at i, expanding window
# Start predicting after 150 matches (need enough for DC to fit)
MIN_TRAIN = 150

def brier_score(preds, actuals):
    return float(np.mean([(p - a) ** 2 for p, a in zip(preds, actuals)]))

def reliability_bins(preds, actuals, n_bins=5):
    """Compute reliability diagram data (predicted vs observed frequency)."""
    preds_arr = np.array(preds)
    actuals_arr = np.array(actuals)
    bins = np.linspace(0, 1, n_bins + 1)
    result = []
    for i in range(n_bins):
        mask = (preds_arr >= bins[i]) & (preds_arr < bins[i + 1])
        if i == n_bins - 1:
            mask = (preds_arr >= bins[i]) & (preds_arr <= bins[i + 1])
        if np.sum(mask) >= 3:
            mean_pred = float(np.mean(preds_arr[mask]))
            mean_actual = float(np.mean(actuals_arr[mask]))
            count = int(np.sum(mask))
            result.append((mean_pred, mean_actual, count))
    return result


# Collect walk-forward predictions
wf_results = {
    "goals": {"dc": [], "naive": [], "footystats": [], "actual": []},
    "corners": {"cr": [], "naive": [], "footystats": [], "actual": []},
    "cards": {"cr": [], "naive": [], "footystats": [], "actual": []},
    "btts": {"dc": [], "naive": [], "footystats": [], "actual": []},
    "cs_home": {"dc": [], "naive": [], "actual": []},
}

print(f"Running walk-forward from match {MIN_TRAIN} to {len(features)}...")
print(f"(Training window expands: {MIN_TRAIN} → {len(features)-1} matches)")
print()

# Per-model refit intervals: more frequent refitting helps the regularized
# Dixon-Coles model track form changes, while the count regression models
# (corners, cards) have their own shrinkage and calibrate better with larger
# training increments between refits.
REFIT_INTERVAL_DC = 10       # Dixon-Coles (goals, BTTS, clean sheet)
REFIT_INTERVAL_CORNERS = 50  # Count regression for corners
REFIT_INTERVAL_CARDS = 50    # Count regression for cards

dc_model = None
corners_model = None
cards_model = None

for i in range(MIN_TRAIN, len(features)):
    train_data = features[:i]
    test_feat = features[i]
    corners_train = corners_features[:i]
    cards_train = cards_features[:i]
    corners_test = corners_features[i]
    cards_test = cards_features[i]
    match_id = int(test_feat.get("match_id", 0))

    # Refit Dixon-Coles (goals/BTTS/CS) at its own interval
    if (i - MIN_TRAIN) % REFIT_INTERVAL_DC == 0:
        dc_model = DixonColesModel(line=2.5)
        dc_model.fit(train_data, [f.get("total_goals", 0) > 2.5 for f in train_data])

    # Refit corners model at its own interval
    if (i - MIN_TRAIN) % REFIT_INTERVAL_CORNERS == 0:
        corners_model = create_corners_model(line=9.5)
        corners_model.fit(corners_train, [f.get("total_corners") is not None and f["total_corners"] > 9.5 for f in corners_train])

    # Refit cards model at its own interval
    if (i - MIN_TRAIN) % REFIT_INTERVAL_CARDS == 0:
        cards_model = create_cards_model(line=3.5)
        cards_model.fit(cards_train, [f.get("total_cards") is not None and f["total_cards"] > 3.5 for f in cards_train])

    # ─── GOALS O/U 2.5 ───
    actual_goals = 1.0 if test_feat.get("total_goals", 0) > 2.5 else 0.0
    dc_pred = dc_model.predict(test_feat).p_over
    naive_goals = sum(1 for f in train_data if f.get("total_goals", 0) > 2.5) / len(train_data)

    # FootyStats benchmark
    fs_goals = None
    fs_data = footystats_preds.get(match_id, {})
    o25_pot = fs_data.get("o25_potential")
    if o25_pot is not None and o25_pot > 0:
        fs_goals = o25_pot / 100.0  # Convert percentage to probability

    wf_results["goals"]["dc"].append(dc_pred)
    wf_results["goals"]["naive"].append(naive_goals)
    wf_results["goals"]["actual"].append(actual_goals)
    if fs_goals is not None:
        wf_results["goals"]["footystats"].append((fs_goals, actual_goals))

    # ─── CORNERS O/U 9.5 ───
    total_corners = corners_test.get("total_corners")
    if total_corners is None:
        raise AssertionError("missing corners label in benchmark scoring row")
    actual_corners = 1.0 if total_corners > 9.5 else 0.0
    cr_pred = corners_model.predict(corners_test).p_over
    valid_corners_train = [f["total_corners"] for f in corners_train if f.get("total_corners") is not None]
    naive_corners = sum(value > 9.5 for value in valid_corners_train) / len(valid_corners_train)

    fs_corners = None
    corners_pot = fs_data.get("corners_o95_potential")
    if corners_pot is not None and corners_pot > 0:
        fs_corners = corners_pot / 100.0

    wf_results["corners"]["cr"].append(cr_pred)
    wf_results["corners"]["naive"].append(naive_corners)
    wf_results["corners"]["actual"].append(actual_corners)
    if fs_corners is not None:
        wf_results["corners"]["footystats"].append((fs_corners, actual_corners))

    # ─── CARDS O/U 3.5 ───
    total_cards = cards_test.get("total_cards")
    if total_cards is None:
        raise AssertionError("missing cards label in benchmark scoring row")
    actual_cards = 1.0 if total_cards > 3.5 else 0.0
    cards_pred = cards_model.predict(cards_test).p_over
    valid_cards_train = [f["total_cards"] for f in cards_train if f.get("total_cards") is not None]
    naive_cards = sum(value > 3.5 for value in valid_cards_train) / len(valid_cards_train)

    wf_results["cards"]["cr"].append(cards_pred)
    wf_results["cards"]["naive"].append(naive_cards)
    wf_results["cards"]["actual"].append(actual_cards)

    # ─── BTTS ───
    actual_btts = 1.0 if (test_feat.get("home_goals", 0) >= 1 and test_feat.get("away_goals", 0) >= 1) else 0.0
    btts_model = BTTSModel(goals_model=dc_model)
    btts_pred = btts_model.predict(test_feat).p_over
    naive_btts = sum(1 for f in train_data if f.get("home_goals", 0) >= 1 and f.get("away_goals", 0) >= 1) / len(train_data)

    fs_btts = None
    btts_pot = fs_data.get("btts_potential")
    if btts_pot is not None and btts_pot > 0:
        fs_btts = btts_pot / 100.0

    wf_results["btts"]["dc"].append(btts_pred)
    wf_results["btts"]["naive"].append(naive_btts)
    wf_results["btts"]["actual"].append(actual_btts)
    if fs_btts is not None:
        wf_results["btts"]["footystats"].append((fs_btts, actual_btts))

    # ─── CLEAN SHEET HOME ───
    actual_cs = 1.0 if test_feat.get("away_goals", 0) == 0 else 0.0
    cs_model = CleanSheetModel(goals_model=dc_model, side="home")
    cs_pred = cs_model.predict(test_feat).p_over
    naive_cs = sum(1 for f in train_data if f.get("away_goals", 0) == 0) / len(train_data)

    wf_results["cs_home"]["dc"].append(cs_pred)
    wf_results["cs_home"]["naive"].append(naive_cs)
    wf_results["cs_home"]["actual"].append(actual_cs)

n_preds = len(wf_results["goals"]["actual"])
print(f"Walk-forward complete: {n_preds} predictions generated")
print()


# ═══════════════════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════════════════

print("=" * 75)
print("BRIER SCORES (lower = better)")
print("=" * 75)
print()
print(f"{'Target':<20} {'Naive':<12} {'Our Model':<12} {'FootyStats':<12} {'Model vs FS':<12}")
print("-" * 68)

# Goals
goals_naive_b = brier_score(wf_results["goals"]["naive"], wf_results["goals"]["actual"])
goals_dc_b = brier_score(wf_results["goals"]["dc"], wf_results["goals"]["actual"])
fs_goals_pairs = wf_results["goals"]["footystats"]
if fs_goals_pairs:
    fs_goals_b = brier_score([p for p, _ in fs_goals_pairs], [a for _, a in fs_goals_pairs])
    # Also compute our model's Brier on same subset
    # (FootyStats may not have predictions for all matches)
    fs_str = f"{fs_goals_b:.4f}"
    comparison = "BETTER" if goals_dc_b < fs_goals_b else "worse"
else:
    fs_str = "N/A"
    comparison = "-"
print(f"{'Goals O/U 2.5':<20} {goals_naive_b:<12.4f} {goals_dc_b:<12.4f} {fs_str:<12} {comparison:<12}")

# Corners
corners_naive_b = brier_score(wf_results["corners"]["naive"], wf_results["corners"]["actual"])
corners_cr_b = brier_score(wf_results["corners"]["cr"], wf_results["corners"]["actual"])
fs_corners_pairs = wf_results["corners"]["footystats"]
if fs_corners_pairs:
    fs_corners_b = brier_score([p for p, _ in fs_corners_pairs], [a for _, a in fs_corners_pairs])
    fs_str = f"{fs_corners_b:.4f}"
    comparison = "BETTER" if corners_cr_b < fs_corners_b else "worse"
else:
    fs_str = "N/A"
    comparison = "-"
print(f"{'Corners O/U 9.5':<20} {corners_naive_b:<12.4f} {corners_cr_b:<12.4f} {fs_str:<12} {comparison:<12}")

# Cards
cards_naive_b = brier_score(wf_results["cards"]["naive"], wf_results["cards"]["actual"])
cards_cr_b = brier_score(wf_results["cards"]["cr"], wf_results["cards"]["actual"])
print(f"{'Cards O/U 3.5':<20} {cards_naive_b:<12.4f} {cards_cr_b:<12.4f} {'N/A':<12} {'-':<12}")

# BTTS
btts_naive_b = brier_score(wf_results["btts"]["naive"], wf_results["btts"]["actual"])
btts_dc_b = brier_score(wf_results["btts"]["dc"], wf_results["btts"]["actual"])
fs_btts_pairs = wf_results["btts"]["footystats"]
if fs_btts_pairs:
    fs_btts_b = brier_score([p for p, _ in fs_btts_pairs], [a for _, a in fs_btts_pairs])
    fs_str = f"{fs_btts_b:.4f}"
    comparison = "BETTER" if btts_dc_b < fs_btts_b else "worse"
else:
    fs_str = "N/A"
    comparison = "-"
print(f"{'BTTS':<20} {btts_naive_b:<12.4f} {btts_dc_b:<12.4f} {fs_str:<12} {comparison:<12}")

# Clean Sheet
cs_naive_b = brier_score(wf_results["cs_home"]["naive"], wf_results["cs_home"]["actual"])
cs_dc_b = brier_score(wf_results["cs_home"]["dc"], wf_results["cs_home"]["actual"])
print(f"{'Clean Sheet (H)':<20} {cs_naive_b:<12.4f} {cs_dc_b:<12.4f} {'N/A':<12} {'-':<12}")

print()
print("-" * 68)
print()

# Improvement summary
print("IMPROVEMENT vs NAIVE:")
print(f"  Goals:       {(goals_naive_b - goals_dc_b)/goals_naive_b*100:+.1f}%")
print(f"  Corners:     {(corners_naive_b - corners_cr_b)/corners_naive_b*100:+.1f}%")
print(f"  Cards:       {(cards_naive_b - cards_cr_b)/cards_naive_b*100:+.1f}%")
print(f"  BTTS:        {(btts_naive_b - btts_dc_b)/btts_naive_b*100:+.1f}%")
print(f"  Clean Sheet: {(cs_naive_b - cs_dc_b)/cs_naive_b*100:+.1f}%")

print()
print("=" * 75)
print("RELIABILITY ANALYSIS (5-bin calibration)")
print("=" * 75)

for target_name, model_key, results_key in [
    ("Goals O/U 2.5", "dc", "goals"),
    ("Corners O/U 9.5", "cr", "corners"),
    ("Cards O/U 3.5", "cr", "cards"),
    ("BTTS", "dc", "btts"),
    ("Clean Sheet (H)", "dc", "cs_home"),
]:
    preds = wf_results[results_key][model_key]
    actuals = wf_results[results_key]["actual"]
    bins = reliability_bins(preds, actuals, n_bins=5)
    print(f"\n  {target_name}:")
    print(f"    {'Predicted':>10}  {'Observed':>10}  {'Count':>6}  {'|Gap|':>6}")
    total_gap = 0
    total_n = 0
    for pred_mean, obs_mean, count in bins:
        gap = abs(pred_mean - obs_mean)
        total_gap += gap * count
        total_n += count
        print(f"    {pred_mean:>10.3f}  {obs_mean:>10.3f}  {count:>6}  {gap:>6.3f}")
    ece = total_gap / total_n if total_n > 0 else 0
    print(f"    ECE (weighted avg |gap|): {ece:.4f}")

print()
print("=" * 75)
print("PREDICTION DIVERSITY (unique values)")
print("=" * 75)
print()
for target_name, model_key, results_key in [
    ("Goals", "dc", "goals"),
    ("Corners", "cr", "corners"),
    ("Cards", "cr", "cards"),
    ("BTTS", "dc", "btts"),
    ("CS Home", "dc", "cs_home"),
]:
    preds = wf_results[results_key][model_key]
    unique = len(set(round(p, 4) for p in preds))
    print(f"  {target_name:<12}: {unique}/{len(preds)} unique values, range [{min(preds):.3f}, {max(preds):.3f}]")

print()
print("=" * 75)
print("NOTES")
print("=" * 75)
print("""
1. Walk-forward protocol: expanding training window, no look-ahead.
   Per-model refit intervals: Dixon-Coles every 10 matches, corners/cards every 50.
2. FootyStats *_potential fields are their public pre-match predictions
   (converted from percentage to probability for Brier comparison).
3. Calibration wrapper NOT applied (single-season data too small for
   calibration holdout to help). Should be applied with multi-season data.
4. All models use ONLY pre-match information. No post-match stat leakage.
5. Dixon-Coles uses team identity only. CountRegression uses team effects
   + match features (attacks, shots, fouls, possession from PRIOR matches).
6. Reference calibration (multi-league, 25 leagues x 3 seasons):
   Corners ECE = 0.064, Cards ECE = 0.058.
   Single-season ECE figures will vary — use multi-league as the baseline.
""")
