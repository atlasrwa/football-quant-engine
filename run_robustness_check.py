"""Leak-free multi-league, multi-season robustness check for corners and cards.

Evaluates the frozen CountRegression models across 25 leagues and three cached seasons
per league. Every CountRegression input is built from strictly earlier fixtures by
``build_prior_only_features``; ``assert_no_same_match_leakage`` is a hard failure.
The former artifact was contaminated by final-match numeric fields and is not evidence
of predictive skill. This run overwrites ``robustness_results.json`` with the guarded
results.
"""

import os
import sys
import json
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, "/home/ubuntu")

# This run is intentionally cache-only: all 25 × 3 inputs are already present in
# CACHE_DIR, so no API credential is loaded or requested.

import numpy as np
from src.research.footystats.client import FootyStatsResearchClient
from src.research.footystats.normalizer import MatchNormalizer
from src.research.models.count_regression import create_corners_model, create_cards_model
from src.research.models.prior_only_features import (
    assert_no_same_match_leakage,
    build_prior_only_features,
)


# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

CACHE_DIR = Path("/home/ubuntu/.cache/footystats_research")
MIN_TRAIN = 100  # Minimum matches before predictions start (smaller leagues have fewer)
REFIT_INTERVAL = 50  # Per existing config for corners/cards

# Target leagues (25 leagues across tiers)
TARGET_LEAGUES = [
    # Top 5 European leagues
    "England Premier League",
    "Spain La Liga",
    "Italy Serie A",
    "Germany Bundesliga",
    "France Ligue 1",
    # Second-tier European leagues
    "England Championship",
    "Germany 2. Bundesliga",
    "Italy Serie B",
    "France Ligue 2",
    # Smaller / less-heavily-bet leagues
    "Netherlands Eredivisie",
    "Scotland Premiership",
    "Belgium Pro League",
    "Austria Bundesliga",
    "Switzerland Super League",
    "Greece Super League",
    "Norway Eliteserien",
    "Sweden Allsvenskan",
    "Turkey Süper Lig",
    "Portugal Liga NOS",
    "Denmark Superliga",
    "Poland Ekstraklasa",
    "Finland Veikkausliiga",
    "Brazil Serie A",
    "USA MLS",
    "Australia A-League",
]

# Number of most recent completed seasons per league
SEASONS_PER_LEAGUE = 3


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def brier_score(preds, actuals):
    """Brier score (lower = better)."""
    return float(np.mean([(p - a) ** 2 for p, a in zip(preds, actuals)]))


def compute_ece(preds, actuals, n_bins=5):
    """Expected Calibration Error (5-bin)."""
    preds_arr = np.array(preds)
    actuals_arr = np.array(actuals)
    bins = np.linspace(0, 1, n_bins + 1)
    total_gap = 0
    total_n = 0
    for i in range(n_bins):
        mask = (preds_arr >= bins[i]) & (preds_arr < bins[i + 1])
        if i == n_bins - 1:
            mask = (preds_arr >= bins[i]) & (preds_arr <= bins[i + 1])
        if np.sum(mask) >= 3:
            gap = abs(float(np.mean(preds_arr[mask])) - float(np.mean(actuals_arr[mask])))
            total_gap += gap * int(np.sum(mask))
            total_n += int(np.sum(mask))
    return total_gap / total_n if total_n > 0 else None


@dataclass
class LeagueSeasonResult:
    """Results for one league-season."""
    league: str
    season_year: str
    n_matches: int
    n_predictions: int
    # Corners
    corners_brier: Optional[float] = None
    corners_naive_brier: Optional[float] = None
    corners_vs_naive_pct: Optional[float] = None
    corners_ece: Optional[float] = None
    corners_data_coverage: float = 1.0  # Fraction of matches with valid corner data
    # Cards
    cards_brier: Optional[float] = None
    cards_naive_brier: Optional[float] = None
    cards_vs_naive_pct: Optional[float] = None
    cards_ece: Optional[float] = None
    cards_data_coverage: float = 1.0
    # Data quality flags
    data_quality_notes: str = ""


# ═══════════════════════════════════════════════════════════════
# DATA LOADING & FEATURE BUILDING
# ═══════════════════════════════════════════════════════════════

def load_season_features(client, normalizer, season_id):
    """Build guarded, strictly-prior corners and cards feature sets for a season.

    The raw final-match numeric fields are retained only as historical values and labels;
    ``build_prior_only_features`` never exposes the predicted fixture's own statistics.
    The structural assertions are deliberately hard failures: evaluation must stop rather
    than emit a contaminated result.
    """
    raw_matches = client.fetch_season_matches(season_id)
    complete = sorted(
        [m for m in raw_matches if m.get("status") == "complete"],
        key=lambda m: m.get("date_unix", 0),
    )
    if not complete:
        return {}, "NO DATA"

    corners = build_prior_only_features(complete, target_field="total_corners")
    cards = build_prior_only_features(complete, target_field="total_cards")
    assert_no_same_match_leakage(complete, corners)
    assert_no_same_match_leakage(complete, cards)

    notes = []
    n = len(complete)
    corners_coverage = sum(f.get("total_corners") is not None for f in corners) / n
    cards_coverage = sum(f.get("total_cards") is not None for f in cards) / n
    if corners_coverage < 0.8:
        notes.append(f"corners_coverage={corners_coverage:.0%}")
    if cards_coverage < 0.8:
        notes.append(f"cards_coverage={cards_coverage:.0%}")

    return {"corners": corners, "cards": cards}, "; ".join(notes) if notes else ""


# ═══════════════════════════════════════════════════════════════
# WALK-FORWARD BENCHMARK (per league-season)
# ═══════════════════════════════════════════════════════════════

def run_walk_forward(feature_sets, min_train=MIN_TRAIN, refit_interval=REFIT_INTERVAL):
    """Run guarded walk-forward evaluation for corners and cards.

    ``feature_sets`` must be the hard-checked output of ``load_season_features``.
    Each naive prediction is the outcome rate among valid labels available strictly
    before the fixture; no missing target is silently counted as an under.
    """
    corners_features = feature_sets["corners"]
    cards_features = feature_sets["cards"]
    if len(corners_features) != len(cards_features):
        raise AssertionError("corners/cards feature lengths differ")
    n = len(corners_features)
    if n < min_train + 30:
        # Not enough data for meaningful walk-forward
        return None

    # Adjust min_train for smaller leagues
    effective_min_train = min(min_train, max(60, n // 3))

    corners_preds, corners_actuals = [], []
    cards_preds, cards_actuals = [], []
    corners_naive_preds, cards_naive_preds = [], []

    corners_model = None
    cards_model = None

    for i in range(effective_min_train, n):
        c_train = corners_features[:i]
        k_train = cards_features[:i]
        c_test = corners_features[i]
        k_test = cards_features[i]

        # Refit at interval
        if (i - effective_min_train) % refit_interval == 0:
            corners_model = create_corners_model(line=9.5)
            corners_model.fit(
                c_train,
                [f.get("total_corners") is not None and f["total_corners"] > 9.5 for f in c_train],
            )

            cards_model = create_cards_model(line=3.5)
            cards_model.fit(
                k_train,
                [f.get("total_cards") is not None and f["total_cards"] > 3.5 for f in k_train],
            )

        # Corners prediction
        total_corners = c_test.get("total_corners")
        if total_corners is not None and total_corners >= 0:
            actual_corners = 1.0 if total_corners > 9.5 else 0.0
            pred_corners = corners_model.predict(c_test).p_over
            prior_corners = [f["total_corners"] for f in c_train if f.get("total_corners") is not None]
            naive_corners = sum(value > 9.5 for value in prior_corners) / len(prior_corners)
            corners_preds.append(pred_corners)
            corners_actuals.append(actual_corners)
            corners_naive_preds.append(naive_corners)

        # Cards prediction
        total_cards = k_test.get("total_cards")
        if total_cards is not None and total_cards >= 0:
            actual_cards = 1.0 if total_cards > 3.5 else 0.0
            pred_cards = cards_model.predict(k_test).p_over
            prior_cards = [f["total_cards"] for f in k_train if f.get("total_cards") is not None]
            naive_cards = sum(value > 3.5 for value in prior_cards) / len(prior_cards)
            cards_preds.append(pred_cards)
            cards_actuals.append(actual_cards)
            cards_naive_preds.append(naive_cards)

    # Compute metrics
    result = {
        "n_predictions": max(len(corners_preds), len(cards_preds)),
    }

    if len(corners_preds) >= 20:
        corners_b = brier_score(corners_preds, corners_actuals)
        corners_naive_b = brier_score(corners_naive_preds, corners_actuals)
        result["corners_brier"] = corners_b
        result["corners_naive_brier"] = corners_naive_b
        if corners_naive_b > 0:
            result["corners_vs_naive_pct"] = (corners_naive_b - corners_b) / corners_naive_b * 100
        result["corners_ece"] = compute_ece(corners_preds, corners_actuals)
        result["corners_data_coverage"] = len(corners_preds) / (n - effective_min_train)

    if len(cards_preds) >= 20:
        cards_b = brier_score(cards_preds, cards_actuals)
        cards_naive_b = brier_score(cards_naive_preds, cards_actuals)
        result["cards_brier"] = cards_b
        result["cards_naive_brier"] = cards_naive_b
        if cards_naive_b > 0:
            result["cards_vs_naive_pct"] = (cards_naive_b - cards_b) / cards_naive_b * 100
        result["cards_ece"] = compute_ece(cards_preds, cards_actuals)
        result["cards_data_coverage"] = len(cards_preds) / (n - effective_min_train)

    return result


# ═══════════════════════════════════════════════════════════════
# MAIN: MULTI-LEAGUE, MULTI-SEASON RUN
# ═══════════════════════════════════════════════════════════════

def get_completed_seasons(league_info, max_seasons=SEASONS_PER_LEAGUE):
    """Get most recent completed seasons for a league."""
    seasons = league_info.get("season", [])
    completed = []
    for s in seasons:
        year = s.get("year", 0)
        if isinstance(year, int):
            if year > 20000000:  # split-year: 20252026
                end_year = year % 10000
                if end_year <= 2026:
                    completed.append(s)
            elif year >= 2000:  # calendar year
                if year <= 2025:
                    completed.append(s)
    completed.sort(key=lambda s: s.get("year", 0), reverse=True)
    return completed[:max_seasons]


def main():
    print("=" * 80)
    print("ROBUSTNESS CHECK: Corners (O/U 9.5) & Cards (O/U 3.5)")
    print("Walk-forward across 25 leagues × 3 seasons")
    print("=" * 80)
    print()
    print("Config:")
    print(f"  MIN_TRAIN = {MIN_TRAIN} (adjusted down for smaller leagues)")
    print(f"  REFIT_INTERVAL = {REFIT_INTERVAL}")
    print(f"  Cache dir: {CACHE_DIR}")
    print()

    client = FootyStatsResearchClient(cache_dir=CACHE_DIR)
    normalizer = MatchNormalizer()

    # Get available leagues
    leagues = client.fetch_league_list()
    league_map = {l.get("name", ""): l for l in leagues}

    # Build run plan
    run_plan = []
    for target in TARGET_LEAGUES:
        info = league_map.get(target)
        if not info:
            for lname, ldata in league_map.items():
                if target.lower() in lname.lower() or lname.lower() in target.lower():
                    info = ldata
                    break
        if not info:
            print(f"  WARNING: League not found: {target}")
            continue

        seasons = get_completed_seasons(info)
        for s in seasons:
            run_plan.append({
                "league": info.get("name", target),
                "season_id": s["id"],
                "year": str(s.get("year", "?")),
            })

    print(f"Run plan: {len(run_plan)} league-seasons across {len(set(r['league'] for r in run_plan))} leagues")
    print("  Cache-only run: 0 API requests and no credentials required.")
    print()

    # Execute
    all_results = []
    errors = []

    for idx, item in enumerate(run_plan):
        league = item["league"]
        season_id = item["season_id"]
        year = item["year"]
        progress = f"[{idx+1}/{len(run_plan)}]"

        try:
            feature_sets, quality_notes = load_season_features(client, normalizer, season_id)
            n_matches = len(feature_sets.get("corners", ()))

            if n_matches < 60:
                print(f"  {progress} {league} {year}: SKIPPED ({n_matches} matches, too few)")
                continue

            wf_result = run_walk_forward(feature_sets)
            if wf_result is None:
                print(f"  {progress} {league} {year}: SKIPPED (insufficient for walk-forward)")
                continue

            result = LeagueSeasonResult(
                league=league,
                season_year=year,
                n_matches=n_matches,
                n_predictions=wf_result.get("n_predictions", 0),
                corners_brier=wf_result.get("corners_brier"),
                corners_naive_brier=wf_result.get("corners_naive_brier"),
                corners_vs_naive_pct=wf_result.get("corners_vs_naive_pct"),
                corners_ece=wf_result.get("corners_ece"),
                corners_data_coverage=wf_result.get("corners_data_coverage", 1.0),
                cards_brier=wf_result.get("cards_brier"),
                cards_naive_brier=wf_result.get("cards_naive_brier"),
                cards_vs_naive_pct=wf_result.get("cards_vs_naive_pct"),
                cards_ece=wf_result.get("cards_ece"),
                cards_data_coverage=wf_result.get("cards_data_coverage", 1.0),
                data_quality_notes=quality_notes,
            )
            all_results.append(result)

            # Brief progress output
            c_imp = f"{result.corners_vs_naive_pct:+.1f}%" if result.corners_vs_naive_pct is not None else "N/A"
            k_imp = f"{result.cards_vs_naive_pct:+.1f}%" if result.cards_vs_naive_pct is not None else "N/A"
            flag = " ⚠" if quality_notes else ""
            print(f"  {progress} {league:<35} {year:<10} n={n_matches:<4} corners={c_imp:<8} cards={k_imp:<8}{flag}")

        except Exception as e:
            errors.append(f"{league} {year}: {str(e)[:80]}")
            print(f"  {progress} {league} {year}: ERROR - {str(e)[:60]}")

    # ═══════════════════════════════════════════════════════════════
    # RESULTS SUMMARY
    # ═══════════════════════════════════════════════════════════════

    print()
    print("=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)
    print()

    if errors:
        print(f"Errors ({len(errors)}):")
        for e in errors:
            print(f"  {e}")
        print()

    # ─── PER-LEAGUE BREAKDOWN ───
    print("─" * 80)
    print("PER-LEAGUE RESULTS (averaged across seasons)")
    print("─" * 80)
    print()
    print(f"{'League':<35} {'#Szns':<6} {'Corners vs Naive':<18} {'Corners ECE':<13} {'Cards vs Naive':<16} {'Cards ECE':<11} {'Notes'}")
    print("-" * 120)

    # Group by league
    by_league = {}
    for r in all_results:
        by_league.setdefault(r.league, []).append(r)

    league_summaries = []
    for league in TARGET_LEAGUES:
        # Find matching results (handle partial name matching)
        results = by_league.get(league, [])
        if not results:
            for key in by_league:
                if league.lower() in key.lower() or key.lower() in league.lower():
                    results = by_league[key]
                    break

        if not results:
            print(f"  {league:<33} {'—':<6} {'NO DATA'}")
            continue

        n_seasons = len(results)

        # Average corners
        c_vals = [r.corners_vs_naive_pct for r in results if r.corners_vs_naive_pct is not None]
        c_ece_vals = [r.corners_ece for r in results if r.corners_ece is not None]
        c_avg = np.mean(c_vals) if c_vals else None
        c_ece_avg = np.mean(c_ece_vals) if c_ece_vals else None

        # Average cards
        k_vals = [r.cards_vs_naive_pct for r in results if r.cards_vs_naive_pct is not None]
        k_ece_vals = [r.cards_ece for r in results if r.cards_ece is not None]
        k_avg = np.mean(k_vals) if k_vals else None
        k_ece_avg = np.mean(k_ece_vals) if k_ece_vals else None

        # Notes
        notes = []
        low_cov = [r for r in results if r.corners_data_coverage < 0.8 or r.cards_data_coverage < 0.8]
        if low_cov:
            notes.append("low_coverage")
        quality_issues = [r for r in results if r.data_quality_notes]
        if quality_issues:
            notes.append(quality_issues[0].data_quality_notes)

        c_str = f"{c_avg:+.1f}%" if c_avg is not None else "N/A"
        c_ece_str = f"{c_ece_avg:.4f}" if c_ece_avg is not None else "N/A"
        k_str = f"{k_avg:+.1f}%" if k_avg is not None else "N/A"
        k_ece_str = f"{k_ece_avg:.4f}" if k_ece_avg is not None else "N/A"
        note_str = "; ".join(notes) if notes else ""

        print(f"  {league:<33} {n_seasons:<6} {c_str:<18} {c_ece_str:<13} {k_str:<16} {k_ece_str:<11} {note_str}")

        league_summaries.append({
            "league": league,
            "n_seasons": n_seasons,
            "corners_avg": c_avg,
            "corners_ece_avg": c_ece_avg,
            "cards_avg": k_avg,
            "cards_ece_avg": k_ece_avg,
        })

    # ─── PER-SEASON DETAIL ───
    print()
    print("─" * 80)
    print("PER LEAGUE-SEASON DETAIL")
    print("─" * 80)
    print()
    print(f"{'League':<30} {'Season':<12} {'Matches':<8} {'C vs Naive':<12} {'C ECE':<8} {'K vs Naive':<12} {'K ECE':<8} {'Notes'}")
    print("-" * 110)

    for r in all_results:
        c_str = f"{r.corners_vs_naive_pct:+.1f}%" if r.corners_vs_naive_pct is not None else "N/A"
        c_ece = f"{r.corners_ece:.4f}" if r.corners_ece is not None else "N/A"
        k_str = f"{r.cards_vs_naive_pct:+.1f}%" if r.cards_vs_naive_pct is not None else "N/A"
        k_ece = f"{r.cards_ece:.4f}" if r.cards_ece is not None else "N/A"
        notes = r.data_quality_notes if r.data_quality_notes else ""
        print(f"  {r.league:<28} {r.season_year:<12} {r.n_matches:<8} {c_str:<12} {c_ece:<8} {k_str:<12} {k_ece:<8} {notes}")

    # ─── AGGREGATE SUMMARY ───
    print()
    print("─" * 80)
    print("AGGREGATE SUMMARY")
    print("─" * 80)
    print()

    all_corners = [r.corners_vs_naive_pct for r in all_results if r.corners_vs_naive_pct is not None]
    all_cards = [r.cards_vs_naive_pct for r in all_results if r.cards_vs_naive_pct is not None]
    all_corners_ece = [r.corners_ece for r in all_results if r.corners_ece is not None]
    all_cards_ece = [r.cards_ece for r in all_results if r.cards_ece is not None]

    print(f"  CORNERS (O/U 9.5):")
    print(f"    League-seasons evaluated: {len(all_corners)}")
    print(f"    Mean vs naive: {np.mean(all_corners):+.1f}%")
    print(f"    Median vs naive: {np.median(all_corners):+.1f}%")
    print(f"    Std: {np.std(all_corners):.1f}%")
    print(f"    Positive (beating naive): {sum(1 for x in all_corners if x > 0)}/{len(all_corners)} ({sum(1 for x in all_corners if x > 0)/len(all_corners)*100:.0f}%)")
    print(f"    Mean ECE: {np.mean(all_corners_ece):.4f}")
    print(f"    Median ECE: {np.median(all_corners_ece):.4f}")
    print()
    print(f"  CARDS (O/U 3.5):")
    print(f"    League-seasons evaluated: {len(all_cards)}")
    print(f"    Mean vs naive: {np.mean(all_cards):+.1f}%")
    print(f"    Median vs naive: {np.median(all_cards):+.1f}%")
    print(f"    Std: {np.std(all_cards):.1f}%")
    print(f"    Positive (beating naive): {sum(1 for x in all_cards if x > 0)}/{len(all_cards)} ({sum(1 for x in all_cards if x > 0)/len(all_cards)*100:.0f}%)")
    print(f"    Mean ECE: {np.mean(all_cards_ece):.4f}")
    print(f"    Median ECE: {np.median(all_cards_ece):.4f}")
    print()

    # ─── BY LEAGUE TIER ───
    tier_top5 = TARGET_LEAGUES[:5]
    tier_second = TARGET_LEAGUES[5:9]
    tier_smaller = TARGET_LEAGUES[9:]

    for tier_name, tier_leagues in [("Top 5", tier_top5), ("Second Tier", tier_second), ("Smaller/Less-Bet", tier_smaller)]:
        tier_corners = []
        tier_cards = []
        for r in all_results:
            if any(t.lower() in r.league.lower() or r.league.lower() in t.lower() for t in tier_leagues):
                if r.corners_vs_naive_pct is not None:
                    tier_corners.append(r.corners_vs_naive_pct)
                if r.cards_vs_naive_pct is not None:
                    tier_cards.append(r.cards_vs_naive_pct)
        if tier_corners or tier_cards:
            c_str = f"{np.mean(tier_corners):+.1f}%" if tier_corners else "N/A"
            k_str = f"{np.mean(tier_cards):+.1f}%" if tier_cards else "N/A"
            print(f"  {tier_name:<20}: corners={c_str:<8} cards={k_str:<8} (n={len(tier_corners)} league-seasons)")

    print()
    print("─" * 80)
    print("INTERPRETATION NOTES")
    print("─" * 80)
    print("""
  - vs naive > 0% means the model beats the strictly-prior, expanding-training
    base-rate predictor
  - ECE < 0.05 indicates well-calibrated predictions
  - Results broken out per league and per season (not pooled) so survivorship
    bias from pooling is avoided
  - Model parameters are FROZEN (no tuning in this run)
  - Walk-forward: expanding window, no look-ahead, refit every 50 matches
  - Data coverage < 80% is flagged (sentinel -1 values for missing corners/cards)
""")

    # Save raw results to JSON for later analysis
    results_path = Path("/home/ubuntu/robustness_results.json")
    results_json = []
    for r in all_results:
        results_json.append({
            "league": r.league,
            "season_year": r.season_year,
            "n_matches": r.n_matches,
            "n_predictions": r.n_predictions,
            "corners_brier": r.corners_brier,
            "corners_naive_brier": r.corners_naive_brier,
            "corners_vs_naive_pct": r.corners_vs_naive_pct,
            "corners_ece": r.corners_ece,
            "corners_data_coverage": r.corners_data_coverage,
            "cards_brier": r.cards_brier,
            "cards_naive_brier": r.cards_naive_brier,
            "cards_vs_naive_pct": r.cards_vs_naive_pct,
            "cards_ece": r.cards_ece,
            "cards_data_coverage": r.cards_data_coverage,
            "data_quality_notes": r.data_quality_notes,
        })
    with open(results_path, "w") as f:
        json.dump(results_json, f, indent=2)
    print(f"  Raw results saved to: {results_path}")


if __name__ == "__main__":
    main()
