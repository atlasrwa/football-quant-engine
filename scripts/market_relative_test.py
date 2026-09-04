"""Market-relative (residual-vs-market) benchmark — the missing angle.

Question: does adding leak-free prior-only raw-stat information to the de-vigged
market price beat the price itself?

For each league-season and supported market, this script walks forward with three
aligned forecast series: naive training base rate, de-vigged market probability, and
the market-relative residual model. It reports paired Brier skill versus market with
a dependence-aware circular moving-block bootstrap and controls false discovery using
Benjamini–Hochberg across the tested family.

Cached API pages are merged by season before evaluation. This is essential: treating
pagination files as independent seasons duplicates the statistical family and lets
result keys overwrite one another. Cards remain out of scope because this corpus has
no pre-match cards odds. Zero API calls are made.
"""

import glob
import json
import math
import os
import re
import sys

import numpy as np

sys.path.insert(0, "/home/ubuntu")

from src.research.calibration import CalibrationEvaluator  # noqa: E402
from src.research.ev_calculator import (  # noqa: E402
    DevigMethod,
    MarketProbabilityNormalizer,
)
from src.research.models.market_relative import MarketRelativeCountModel  # noqa: E402
from src.research.models.prior_only_features import (  # noqa: E402
    CORNERS_FEATURES,
    assert_no_same_match_leakage,
    attach_market_odds,
    build_prior_only_features,
)

SEED = 20260902
MIN_TRAIN = 100
REFIT = 50
BH_Q = 0.10
BOOTSTRAP_DRAWS = 10000
CACHE = "/home/ubuntu/.cache/footystats_research"
OUTPUT = "/home/ubuntu/data/results/market_relative_test.json"

# Goals reuse the attacking-pressure schema because both totals are driven by attacking
# volume. All values in this schema are strictly-prior rolling features.
MARKETS = {
    "goals": {"target": "total_goals", "line": 2.5, "features": CORNERS_FEATURES},
    "corners": {"target": "total_corners", "line": 9.5, "features": CORNERS_FEATURES},
}

_NORM = MarketProbabilityNormalizer(method=DevigMethod.MULTIPLICATIVE)


def _match_key(match):
    """Stable identity used to deduplicate overlapping/repeated cache pages."""
    match_id = match.get("id")
    if match_id is not None:
        return ("id", str(match_id))
    return (
        "fixture",
        match.get("date_unix"),
        match.get("homeID", match.get("home_id")),
        match.get("awayID", match.get("away_id")),
        match.get("competition_id"),
    )


def load_corpus_files():
    """Merge cached pagination files into one match list per season ID."""
    by_season = {}
    for path in sorted(glob.glob(os.path.join(CACHE, "league-matches_*.json"))):
        match = re.search(r"season_id:_(\d+)", path)
        if not match:
            continue
        season_id = match.group(1)
        try:
            with open(path, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, ValueError, TypeError):
            continue
        matches = payload["data"] if isinstance(payload, dict) and "data" in payload else payload
        if not isinstance(matches, list):
            continue

        merged = by_season.setdefault(season_id, {})
        for fixture in matches:
            if isinstance(fixture, dict) and fixture.get("date_unix"):
                merged.setdefault(_match_key(fixture), fixture)

    output = []
    for season_id in sorted(by_season, key=lambda value: int(value)):
        matches = list(by_season[season_id].values())
        if len(matches) >= MIN_TRAIN + 30:
            output.append((season_id, matches))
    return output


def _devig_p_over(match, market_target):
    """Pre-match de-vigged P(over) directly from a corpus fixture."""
    from src.research.models.prior_only_features import market_odds_for

    over, under = market_odds_for(match, market_target)
    if over is None or under is None:
        return None
    result = _NORM.normalize_two_way(over, under)
    if result is None or not math.isfinite(result[0]):
        return None
    return result[0]


def _target_value(match, target):
    from src.research.models.prior_only_features import _num

    if target == "total_goals":
        home = _num(match.get("homeGoalCount"))
        away = _num(match.get("awayGoalCount"))
        if home is None or away is None:
            total = _num(match.get("totalGoalCount"))
            return total if total is not None else _num(match.get("overallGoalCount"))
        return home + away
    if target == "total_corners":
        return _num(match.get("totalCornerCount"))
    return None


def walk_forward(matches, target, line, features):
    """Return aligned market, residual, naive, and outcome series, or ``None``."""
    feature_rows = build_prior_only_features(matches, target_field="total_corners")
    # The immutable feature rows are checked once before any expanding-window fit.
    assert_no_same_match_leakage(matches, feature_rows)

    sorted_matches = sorted(matches, key=lambda match: match.get("date_unix", 0))
    for match, feature in zip(sorted_matches, feature_rows):
        feature.pop("total_corners", None)
        feature[target] = _target_value(match, target)
    attach_market_odds(matches, feature_rows, market=target)

    if len(feature_rows) < MIN_TRAIN + 30:
        return None

    residual_predictions = []
    market_predictions = []
    naive_predictions = []
    actuals = []
    match_ids = []
    used_refit_beta_norms = []
    current_beta_norm = None
    current_refit_recorded = False
    model = None

    prior_over = 0
    prior_count = 0
    for feature in feature_rows[:MIN_TRAIN]:
        count = feature.get(target)
        if count is not None and count >= 0:
            prior_count += 1
            prior_over += int(count > line)

    for index in range(MIN_TRAIN, len(feature_rows)):
        if (index - MIN_TRAIN) % REFIT == 0:
            model = MarketRelativeCountModel(
                target_field=target,
                line=line,
                feature_fields=features,
                l2=5.0,
                devig_method=DevigMethod.MULTIPLICATIVE,
            )
            model.fit(feature_rows[:index])
            current_beta_norm = model.params.beta_l2_norm if model.params else 0.0
            current_refit_recorded = False

        row = feature_rows[index]
        count = row.get(target)
        base_rate = (prior_over / prior_count) if prior_count else 0.5
        if count is not None and count >= 0:
            prior_count += 1
            prior_over += int(count > line)
        if count is None or count < 0:
            continue

        market_probability = model.devig_p_over(row)
        if market_probability is None:
            continue
        residual_probability = model.predict_p_over(row)
        if residual_probability is None:
            continue

        if not current_refit_recorded:
            used_refit_beta_norms.append(float(current_beta_norm or 0.0))
            current_refit_recorded = True
        residual_predictions.append(float(residual_probability))
        market_predictions.append(float(market_probability))
        naive_predictions.append(float(base_rate))
        actuals.append(float(count > line))
        match_ids.append(row.get("date_unix"))

    if len(actuals) < 40:
        return None
    return {
        "mr": np.array(residual_predictions),
        "mkt": np.array(market_predictions),
        "naive": np.array(naive_predictions),
        "actuals": np.array(actuals),
        "mids": match_ids,
        "mean_beta_norm": float(np.mean(used_refit_beta_norms)) if used_refit_beta_norms else 0.0,
        "n_used_refits": len(used_refit_beta_norms),
    }


def bss_vs_ref(predictions, reference, actuals):
    """Brier skill of predictions relative to another aligned forecast series."""
    prediction_brier = np.mean((predictions - actuals) ** 2)
    reference_brier = np.mean((reference - actuals) ** 2)
    return None if reference_brier <= 0 else (1.0 - prediction_brier / reference_brier) * 100.0


def ece_of(predictions, actuals):
    evaluation = CalibrationEvaluator(n_bins=10, min_samples=30).evaluate(
        list(predictions), [bool(actual) for actual in actuals]
    )
    return evaluation.ece if evaluation.is_valid else None


def _circular_block_sample(rng, n_observations, block_length):
    """Sample chronological circular blocks until one bootstrap series is filled."""
    indexes = []
    while len(indexes) < n_observations:
        start = int(rng.integers(0, n_observations))
        take = min(block_length, n_observations - len(indexes))
        indexes.extend((start + offset) % n_observations for offset in range(take))
    return np.asarray(indexes, dtype=int)


def paired_market_ci(series, seed=SEED, n_boot=BOOTSTRAP_DRAWS, block_length=None):
    """Moving-block bootstrap of paired Brier skill for residual versus market.

    Adjacent walk-forward forecasts share rolling histories and fitted models, so IID
    fixture resampling is inappropriate. Circular chronological blocks preserve local
    dependence. The default block length is ceil(sqrt(n)), bounded to [5, REFIT].
    """
    if n_boot <= 0:
        raise ValueError("n_boot must be positive")
    residual, market, actuals = series["mr"], series["mkt"], series["actuals"]
    n_observations = len(actuals)
    if n_observations == 0:
        raise ValueError("series must contain at least one observation")
    if block_length is None:
        block_length = min(REFIT, n_observations, max(5, math.ceil(math.sqrt(n_observations))))
    if not 1 <= block_length <= n_observations:
        raise ValueError("block_length must be between 1 and the series length")

    point = bss_vs_ref(residual, market, actuals)
    rng = np.random.default_rng(seed)
    bootstrap = []
    for _ in range(n_boot):
        indexes = _circular_block_sample(rng, n_observations, block_length)
        residual_brier = np.mean((residual[indexes] - actuals[indexes]) ** 2)
        market_brier = np.mean((market[indexes] - actuals[indexes]) ** 2)
        if market_brier > 0:
            bootstrap.append((1.0 - residual_brier / market_brier) * 100.0)
    if not bootstrap:
        raise ValueError("market Brier score is zero in every bootstrap sample")

    values = np.asarray(bootstrap, dtype=float)
    low, high = np.quantile(values, [0.025, 0.975])
    p_two_sided = min(1.0, 2.0 * min(float((values <= 0).mean()), float((values >= 0).mean())))
    return {
        "bss_vs_market_pct": round(float(point), 3),
        "ci95_pct": [round(float(low), 3), round(float(high), 3)],
        "p": p_two_sided,
        "bootstrap_block_length": block_length,
    }


def bh_reject(p_values, q=BH_Q):
    indexes = [index for index, value in enumerate(p_values) if value is not None]
    if not indexes:
        return [False] * len(p_values)
    order = sorted(indexes, key=lambda index: p_values[index])
    largest_rejected_rank = 0
    for rank, index in enumerate(order, 1):
        if p_values[index] <= (rank / len(indexes)) * q:
            largest_rejected_rank = rank
    rejected = [False] * len(p_values)
    for rank, index in enumerate(order, 1):
        if rank <= largest_rejected_rank:
            rejected[index] = True
    return rejected


def _percent(value):
    return "N/A" if value is None else f"{value:+.2f}%"


def main():
    print("=" * 84)
    print("MARKET-RELATIVE TEST — does raw-stat residual beat the DE-VIGGED MARKET PRICE?")
    print("=" * 84)
    print(
        f"seed={SEED}  MIN_TRAIN={MIN_TRAIN}  REFIT={REFIT}  "
        f"BH q={BH_Q}  (zero API, within-league)\n"
    )

    corpus = load_corpus_files()
    print(f"Loaded {len(corpus)} merged league-seasons with >= {MIN_TRAIN + 30} matches.\n")

    results = {}
    cells = []
    for season_id, matches in corpus:
        for market_name, specification in MARKETS.items():
            odds_count = sum(
                _devig_p_over(match, specification["target"]) is not None for match in matches
            )
            if odds_count < MIN_TRAIN + 30:
                continue
            series = walk_forward(
                matches,
                specification["target"],
                specification["line"],
                specification["features"],
            )
            if series is None:
                continue

            count = len(series["actuals"])
            market_vs_naive = bss_vs_ref(series["mkt"], series["naive"], series["actuals"])
            residual_vs_naive = bss_vs_ref(series["mr"], series["naive"], series["actuals"])
            paired = paired_market_ci(series)
            market_ece = ece_of(series["mkt"], series["actuals"])
            residual_ece = ece_of(series["mr"], series["actuals"])
            key = f"{season_id}:{market_name}"
            if key in results:
                raise AssertionError(f"duplicate result key after cache merge: {key}")
            results[key] = {
                "season_id": season_id,
                "market": market_name,
                "n": count,
                "bss_vs_naive_market_pct": (
                    round(market_vs_naive, 3) if market_vs_naive is not None else None
                ),
                "bss_vs_naive_mktres_pct": (
                    round(residual_vs_naive, 3) if residual_vs_naive is not None else None
                ),
                "paired_vs_market": paired,
                "ece_market": round(market_ece, 4) if market_ece is not None else None,
                "ece_mktres": round(residual_ece, 4) if residual_ece is not None else None,
                "mean_residual_beta_norm": round(series["mean_beta_norm"], 4),
                "n_used_refits": series["n_used_refits"],
            }
            cells.append((market_name, season_id, paired, count))

    p_values = [cell[2].get("p") if cell[2] else None for cell in cells]
    rejected = bh_reject(p_values)

    print("-" * 84)
    print("PER-MARKET AGGREGATE (BSS vs de-vigged market; positive => residual adds info)")
    print("-" * 84)
    for market_name in MARKETS:
        market_results = [value for value in results.values() if value["market"] == market_name]
        values = [value["paired_vs_market"]["bss_vs_market_pct"] for value in market_results]
        betas = [value["mean_residual_beta_norm"] for value in market_results]
        market_naive = [
            value["bss_vs_naive_market_pct"]
            for value in market_results
            if value["bss_vs_naive_market_pct"] is not None
        ]
        if not values:
            print(f"  {market_name:8s}: no cells")
            continue
        positive = sum(value > 0 for value in values)
        print(
            f"  {market_name:8s}: cells={len(values):3d}  "
            f"market-vs-naive(median)={np.median(market_naive):+.2f}%  "
            f"residual-vs-market: mean={np.mean(values):+.3f}% "
            f"median={np.median(values):+.3f}% pos={positive}/{len(values)}  "
            f"mean|beta|={np.mean(betas):.3f}"
        )

    print("\n" + "=" * 84)
    print(f"DOES THE RESIDUAL BEAT THE MARKET? (paired, BH family={len(cells)}, q={BH_Q})")
    print("=" * 84)
    significant = []
    for (market_name, season_id, paired, count), is_rejected in zip(cells, rejected):
        if is_rejected and paired and paired["bss_vs_market_pct"] > 0:
            significant.append((market_name, season_id, paired, count))
    print(f"  Cells tested: {len(cells)}")
    print(f"  Cells where residual SIGNIFICANTLY beats the market (BH, positive): {len(significant)}")
    for market_name, season_id, paired, count in significant:
        print(
            f"    - {market_name} season {season_id} (n={count}): "
            f"BSS_vs_market={_percent(paired['bss_vs_market_pct'])} "
            f"CI[{_percent(paired['ci95_pct'][0])},{_percent(paired['ci95_pct'][1])}] "
            f"p={paired['p']:.6g}"
        )
    verdict = bool(significant)
    print(
        "\n  VERDICT: raw-stat residual beats the de-vigged market in a "
        f"BH-surviving way: {verdict}"
    )

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    output = {
        "config": {
            "seed": SEED,
            "min_train": MIN_TRAIN,
            "refit": REFIT,
            "bootstrap_draws": BOOTSTRAP_DRAWS,
            "bootstrap_method": "circular_moving_block",
            "bootstrap_block_length": "min(REFIT, n, max(5, ceil(sqrt(n))))",
            "bh_q": BH_Q,
            "devig": "multiplicative",
            "league_seasons": len(corpus),
            "family_size": len(cells),
        },
        "cells": results,
        "verdict_residual_beats_market_bh": verdict,
    }
    with open(OUTPUT, "w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)
        handle.write("\n")
    print("\nsaved: data/results/market_relative_test.json")


if __name__ == "__main__":
    main()
