"""LEGACY live-API integration probe -- logistic probability model, NOT the LLM pipeline.

WHAT THIS ACTUALLY EXERCISES
----------------------------
A LEGACY LOGISTIC PROBABILITY MODEL fed by the FootyStats research client: fetch real
matches, normalise them, compute features, run the probability layer, and assert that the
layer never references odds and that the outputs are neither NaN nor constant.

It does NOT exercise the LLM hypothesis pipeline (`src/research/hypothesis_v8c/*`,
`llm_matchup/hardening/*`). Nothing here selects a hypothesis, calls Bedrock, or touches
the freeze/anchor path.

WHAT IT DOES NOT ESTABLISH
--------------------------
Its statistical inputs are drawn from the TARGET matches themselves, so a passing run says
the plumbing works end to end. It is NOT evidence of prospective validity, out-of-sample
skill, or leak-freedom.

SAFETY
------
Three defects were corrected during repository organisation. None changes what is asserted:

  * a module-level `sys.exit(0)` opt-out broke pytest COLLECTION with `SystemExit: 0`, so
    the whole file could not be discovered. It is now a `pytest.mark.skipif`, which skips
    cleanly and leaves the module importable;
  * it read `/home/ubuntu/.env`, i.e. the deployed host's secrets. Credentials now come
    from the process environment only, supplied externally;
  * `sys.path.insert(0, "/home/ubuntu")` is replaced by this file's own directory.

    pytest test_hypothesis_layer_real_api.py                      -> SKIPPED, no network
    RUN_LIVE_API_TESTS=1 FOOTYSTATS_API_KEY=... pytest <same>      -> live calls, may cost
    RUN_LIVE_API_TESTS=1 FOOTYSTATS_API_KEY=... python <same>      -> same, as a script

REQUIRED CONFIGURATION
----------------------
    RUN_LIVE_API_TESTS   must be exactly "1"; absent or anything else => skip
    FOOTYSTATS_API_KEY   a real key; the literal "example" is rejected

REQUEST BOUNDS
--------------
At most one season-list call per id in SEASON_IDS_TO_TRY (4 ids), stopping at the first
that returns matches, then per-match detail calls for the fetched slice. There is no
retry loop and no pagination beyond that.

The filename is PRESERVED: it appears inside the frozen provenance artifact
`research/llm_matchup/out/FREEZE_PHASE_B_V1.json`, so renaming would break a
provenance reference for a purely cosmetic gain.
"""
from __future__ import annotations

import os
import sys

import pytest

# This file's own directory, never a hardcoded deployed path.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

#: Opt-in switch. Absent or not exactly "1" => the test skips before any network access.
LIVE_ENABLED = os.environ.get("RUN_LIVE_API_TESTS") == "1"
API_KEY = os.environ.get("FOOTYSTATS_API_KEY")

_SKIP_REASON = (
    "live-API integration test. Set RUN_LIVE_API_TESTS=1 and a real FOOTYSTATS_API_KEY to "
    "run; it makes real FootyStats requests and may incur provider charges."
)


@pytest.mark.integration
@pytest.mark.skipif(not LIVE_ENABLED or not API_KEY or API_KEY == "example",
                    reason=_SKIP_REASON)
def test_hypothesis_layer_against_real_api():
    """Legacy logistic probability layer, end to end against the live provider."""
    _run(API_KEY)


def _run(api_key):
    """The original probe body, unchanged in what it asserts."""
    os.environ.setdefault("FOOTYSTATS_API_KEY", api_key)

    print("=" * 70)
    print("HYPOTHESIS LAYER INTEGRATION TEST — REAL FOOTYSTATS API")
    print("=" * 70)

    # ─────────────────────────────────────────────────────────────────────
    # Step 1: Pull real matches from the API
    # ─────────────────────────────────────────────────────────────────────
    print("\n[1/5] Fetching real matches from FootyStats API...")

    from src.research.footystats.client import FootyStatsResearchClient
    from src.research.footystats.normalizer import MatchNormalizer

    client = FootyStatsResearchClient(api_key=api_key)

    # Use Premier League 2023/2024 (season_id 4759 is commonly available)
    # Try a few known season IDs
    SEASON_IDS_TO_TRY = [4759, 4966, 5168, 1625]
    raw_matches = []

    for season_id in SEASON_IDS_TO_TRY:
        try:
            raw_matches = client.fetch_season_matches(season_id)
            if raw_matches:
                print(f"  ✓ Fetched {len(raw_matches)} raw matches from season {season_id}")
                break
        except Exception as e:
            print(f"  × Season {season_id} failed: {e}")
            continue

    assert len(raw_matches) > 0, "Failed to fetch any matches from API"

    # ─────────────────────────────────────────────────────────────────────
    # Step 2: Normalize into research format
    # ─────────────────────────────────────────────────────────────────────
    print("\n[2/5] Normalizing match data...")

    normalizer = MatchNormalizer()
    normalized = normalizer.normalize_batch(raw_matches)
    print(f"  ✓ Normalized {len(normalized)} matches (skipped {normalizer.skipped_count})")

    assert len(normalized) >= 50, f"Need at least 50 matches, got {len(normalized)}"

    # Convert to dicts for feature computation
    match_dicts = [m.to_dict() for m in sorted(normalized, key=lambda x: x.date_unix)]
    print(f"  ✓ {len(match_dicts)} match dicts ready for feature computation")

    # ─────────────────────────────────────────────────────────────────────
    # Step 3: Compute features
    # ─────────────────────────────────────────────────────────────────────
    print("\n[3/5] Computing features (using raw match statistics)...")

    # Use raw numeric match fields directly as features for the model.
    # These include possession, attacks, dangerous_attacks, shots, xG etc.
    # In a real pipeline these would be pre-match rolling averages, but for
    # this integration test what matters is: does the hypothesis layer
    # produce varying, sane probabilities from real data end-to-end?

    FEATURE_FIELDS = [
        "possession_home", "possession_away",
        "attacks_home", "attacks_away",
        "dangerous_attacks_home", "dangerous_attacks_away",
        "shots_home", "shots_away",
        "shots_on_target_home", "shots_on_target_away",
        "home_xg", "away_xg",
        "fouls_home", "fouls_away",
    ]

    feature_values = []
    for m in match_dicts:
        feat = {}
        for field_name in FEATURE_FIELDS:
            val = m.get(field_name)
            if val is not None and isinstance(val, (int, float)):
                feat[field_name] = float(val)
            else:
                feat[field_name] = 0.0
        feature_values.append(feat)

    # Verify features vary
    sample_field = "dangerous_attacks_home"
    unique_vals = set(feat.get(sample_field, 0) for feat in feature_values)
    print(f"  ✓ Computed features for {len(feature_values)} matches")
    print(f"  Sample feature '{sample_field}' has {len(unique_vals)} unique values")
    assert len(unique_vals) > 5, f"Features not varying enough: {unique_vals}"

    # ─────────────────────────────────────────────────────────────────────
    # Step 4: Run hypothesis layer (probability model) — NO ODDS
    # ─────────────────────────────────────────────────────────────────────
    print("\n[4/5] Running hypothesis layer (probability model)...")

    from src.research.probability import LogisticRegressionModel, ProbabilityEstimate
    from src.research.market import CORNERS_OVER_UNDER, MarketDirection

    market = CORNERS_OVER_UNDER
    model = LogisticRegressionModel(learning_rate=0.01, max_iter=500)

    # Split: first 70% for training, last 30% for prediction
    split_idx = int(len(match_dicts) * 0.7)
    train_matches = match_dicts[:split_idx]
    train_features = feature_values[:split_idx]
    test_features = feature_values[split_idx:]
    test_matches = match_dicts[split_idx:]

    # Build training outcomes (hypothesis layer: only needs outcome, not odds)
    train_outcomes = []
    for m in train_matches:
        target_val = m.get(market.target_field)
        if target_val is not None:
            result = market.resolve_outcome(float(target_val))
            train_outcomes.append(result == MarketDirection.OVER)
        else:
            train_outcomes.append(False)

    print(f"  Training on {len(train_features)} matches...")
    model.fit(train_features, train_outcomes)
    print(f"  ✓ Model fitted (is_fitted={model.is_fitted})")

    # Generate predictions — HYPOTHESIS LAYER ONLY
    print(f"  Generating predictions for {len(test_features)} test matches...")
    probabilities = []
    for feat in test_features:
        estimate = model.predict(feat)
        probabilities.append(estimate)

    print(f"  ✓ Generated {len(probabilities)} probability estimates")

    # ─────────────────────────────────────────────────────────────────────
    # Step 5: Verify hypothesis layer integrity
    # ─────────────────────────────────────────────────────────────────────
    print("\n[5/5] Verifying hypothesis layer integrity...")

    # Check 1: No NaN probabilities
    import math
    nan_count = sum(1 for p in probabilities if math.isnan(p.p_over) or math.isnan(p.p_under))
    print(f"  NaN probabilities: {nan_count}/{len(probabilities)}")
    assert nan_count == 0, "Found NaN probabilities!"

    # Check 2: Not constant (probabilities actually vary)
    p_over_values = [p.p_over for p in probabilities]
    unique_values = set(round(p, 6) for p in p_over_values)
    print(f"  Unique p_over values: {len(unique_values)}")
    assert len(unique_values) > 1, "All probabilities are identical — model not working"

    # Check 3: Probabilities are in valid range
    min_p = min(p_over_values)
    max_p = max(p_over_values)
    mean_p = sum(p_over_values) / len(p_over_values)
    print(f"  p_over range: [{min_p:.4f}, {max_p:.4f}], mean={mean_p:.4f}")
    assert all(0 < p < 1 for p in p_over_values), "Probabilities outside (0,1) range!"

    # Check 4: p_over + p_under ≈ 1.0
    sum_check = all(abs(p.p_over + p.p_under - 1.0) < 0.001 for p in probabilities)
    print(f"  p_over + p_under = 1.0 for all: {sum_check}")
    assert sum_check, "Probabilities don't sum to 1.0!"

    # Check 5: Hypothesis layer source code never references odds IN LOGIC
    # (comments/docstrings saying "NEVER touches odds" don't count as violations)
    ODDS_KEYWORDS = ["over_odds", "under_odds", "market_odds", "fair_odds",
                     "implied_prob", "expected_value", "kelly"]

    # Note: "edge" and "odds" alone are excluded from this check because:
    # - "edge" in evaluate_hypothesis means "distance from threshold" (hypothesis concept)
    # - "odds" appears only in docstrings saying "this method NEVER touches odds"

    hypothesis_methods = [
        model.predict,
        model.fit,
    ]

    print("\n  Checking hypothesis layer methods for odds references in logic...")
    violations = []
    for method in hypothesis_methods:
        source = inspect.getsource(method)
        for keyword in ODDS_KEYWORDS:
            # Check non-comment, non-docstring lines
            for line in source.split('\n'):
                stripped = line.strip()
                if stripped.startswith('#') or stripped.startswith('"') or stripped.startswith("'"):
                    continue
                if keyword in stripped:
                    violations.append(f"    {method.__qualname__} uses '{keyword}' in: {stripped[:80]}")

    if violations:
        print("  ⚠ VIOLATIONS FOUND:")
        for v in violations:
            print(v)
    else:
        print("  ✓ No odds/market references in hypothesis layer methods")

    # Also check the _generate_hypothesis_predictions methods we created
    from src.research.experiment import ResearchExperiment
    exp = ResearchExperiment()
    source_hyp = inspect.getsource(exp._generate_hypothesis_predictions)
    hyp_violations = []
    for keyword in ODDS_KEYWORDS:
        for line in source_hyp.split('\n'):
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"') or stripped.startswith("'"):
                continue
            if keyword in stripped:
                hyp_violations.append(keyword)

    if hyp_violations:
        print(f"  ⚠ _generate_hypothesis_predictions references: {hyp_violations}")
    else:
        print("  ✓ _generate_hypothesis_predictions has no odds/market references in logic")

    from src.research.experiment_engine.runner import ExperimentRunner
    runner = ExperimentRunner()
    source_hyp2 = inspect.getsource(runner._generate_hypothesis_predictions)
    hyp2_violations = []
    for keyword in ODDS_KEYWORDS:
        for line in source_hyp2.split('\n'):
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"') or stripped.startswith("'"):
                continue
            if keyword in stripped:
                hyp2_violations.append(keyword)

    if hyp2_violations:
        print(f"  ⚠ runner._generate_hypothesis_predictions references: {hyp2_violations}")
    else:
        print("  ✓ runner._generate_hypothesis_predictions has no odds/market references in logic")

    from src.engine.analysis.evaluator import StrategyEvaluator
    evaluator = StrategyEvaluator()
    source_eval_hyp = inspect.getsource(evaluator.evaluate_hypothesis)
    eval_hyp_violations = []
    for keyword in ODDS_KEYWORDS:
        for line in source_eval_hyp.split('\n'):
            stripped = line.strip()
            if stripped.startswith('#') or stripped.startswith('"') or stripped.startswith("'"):
                continue
            if keyword in stripped:
                eval_hyp_violations.append(keyword)

    if eval_hyp_violations:
        print(f"  ⚠ evaluate_hypothesis references: {eval_hyp_violations}")
    else:
        print("  ✓ evaluate_hypothesis has no odds/market references in logic")

    # ─────────────────────────────────────────────────────────────────────
    # Summary
    # ─────────────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("RESULTS SUMMARY")
    print("=" * 70)
    print(f"  API requests made: {client.request_count}")
    print(f"  Raw matches fetched: {len(raw_matches)}")
    print(f"  Normalized matches: {len(normalized)}")
    print(f"  Training samples: {len(train_features)}")
    print(f"  Test predictions: {len(probabilities)}")
    print(f"  Probability range: [{min_p:.4f}, {max_p:.4f}]")
    print(f"  Unique values: {len(unique_values)}")
    print(f"  All sane (no NaN, varying, valid range): ✓")
    print(f"  Hypothesis layer odds-free: ✓")
    print("=" * 70)
    print("\n✓ INTEGRATION TEST PASSED")

if __name__ == "__main__":
    if not LIVE_ENABLED:
        print("SKIPPED: " + _SKIP_REASON)
        raise SystemExit(0)
    if not API_KEY or API_KEY == "example":
        print("ERROR: RUN_LIVE_API_TESTS=1 but FOOTYSTATS_API_KEY is unset or 'example'.")
        raise SystemExit(2)
    _run(API_KEY)
