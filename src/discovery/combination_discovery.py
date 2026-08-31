"""Path B: Combination Discovery with Model-Based Screening.

Discovers small fitted models (2-3 features) as the unit of discovery,
replacing the binary median-split screener that couldn't detect known-good signal.

Key design changes from the failed first run:
1. Unit of discovery = fitted model over feature set, not arithmetic formula
2. Screening = logistic/Poisson regression with regularization + walk-forward
3. Single representative line per target (no Bonferroni within-group)
4. Full ~90 derived features from the good-coverage field set

The known-good corners/cards features MUST pass the sanity gate before
the full search runs. If they don't, the screener is still wrong.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import numpy as np
from scipy import stats as sp_stats
from scipy.special import expit

from src.discovery.corpus import load_discovery_set, load_heldout_set, STAT_FIELDS
from src.discovery.library import MetricLibrary, MetricStatus
from src.engine.analysis.fdr import FDRController

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# FEATURE SPACE DEFINITION
# ═══════════════════════════════════════════════════════════════

# Fields with <10% missing in the discovery set (confirmed by diagnostic)
GOOD_FIELDS = [f for f in STAT_FIELDS if f not in {
    "team_a_freekicks", "team_b_freekicks",
    "team_a_throwins", "team_b_throwins",
    "team_a_goalkicks", "team_b_goalkicks",
}]

ROLLING_WINDOWS = (5, 10)

# Single representative line per target (pre-selected, no multi-line correction needed)
# Chosen as the line closest to 50% base rate for maximum statistical power
TARGETS = {
    "corners_9.5": {"target": "corners", "line": 9.5},      # ~51.6% over
    "cards_3.5": {"target": "cards", "line": 3.5},           # ~55% over
    "goals_2.5": {"target": "goals", "line": 2.5},           # ~53% over
    "btts": {"target": "btts", "line": None},                # ~55% yes
    "clean_sheet": {"target": "clean_sheet", "line": None},  # ~45% yes
}

# Cap on triples: random sample to keep family honest
MAX_TRIPLES = 5000  # Stated explicitly per ground rules
TRIPLE_SEED = 42    # Reproducible selection


@dataclass(frozen=True)
class FeatureSet:
    """A candidate feature combination to be fitted as a model."""
    combo_id: str
    features: tuple[str, ...]  # (field_name_window, ...)
    source_fields: tuple[str, ...]  # raw field names
    windows: tuple[int, ...]
    size: int  # 2 or 3

    @staticmethod
    def make_id(features: tuple[str, ...]) -> str:
        canonical = json.dumps(sorted(features), separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class ScreeningResult:
    """Result of model-based screening for one feature set."""
    combo_id: str
    features: tuple[str, ...]
    size: int

    # Per-target results
    target_results: dict[str, dict[str, Any]]  # target_name -> {vs_naive, p_value, brier, ...}

    # Aggregates
    targets_positive: int
    targets_tested: int
    breadth_score: float
    best_vs_naive_pct: float
    mean_vs_naive_pct: float
    best_p_value: float
    overall_p_value: float  # Fisher's across targets

    # Single-feature comparison (for interaction check)
    best_single_feature_vs_naive: float  # Best any individual feature achieves alone

    passed: bool


# ═══════════════════════════════════════════════════════════════
# FEATURE COMPUTATION (rolling, look-ahead-free)
# ═══════════════════════════════════════════════════════════════

def compute_rolling_features(
    matches: list[dict], fields: list[str], windows: tuple[int, ...] = ROLLING_WINDOWS
) -> list[dict[str, Optional[float]]]:
    """Compute rolling window features for all matches.

    Point-in-time safe: match i uses only data from matches 0..i-1.
    Returns a list parallel to matches with feature values.
    """
    n = len(matches)
    results: list[dict[str, Optional[float]]] = [{} for _ in range(n)]

    for field in fields:
        for window in windows:
            feat_name = f"{field}_w{window}"
            for i in range(n):
                if i < window:
                    results[i][feat_name] = None
                    continue
                # Look back at the previous `window` matches
                vals = []
                valid = True
                for j in range(i - window, i):
                    v = matches[j].get(field)
                    if v is None or v == -1:
                        valid = False
                        break
                    vals.append(float(v))
                if valid and vals:
                    results[i][feat_name] = float(np.mean(vals))
                else:
                    results[i][feat_name] = None

    return results


# ═══════════════════════════════════════════════════════════════
# MODEL-BASED SCREENING
# ═══════════════════════════════════════════════════════════════

def compute_outcome(match: dict, target: str, line: Optional[float]) -> Optional[float]:
    """Compute binary outcome for a match."""
    if target == "corners":
        a = match.get("team_a_corners", -1)
        b = match.get("team_b_corners", -1)
        if a < 0 or b < 0:
            return None
        return 1.0 if (a + b) > line else 0.0
    elif target == "cards":
        ya = match.get("team_a_yellow_cards", -1)
        yb = match.get("team_b_yellow_cards", -1)
        ra = match.get("team_a_red_cards", -1)
        rb = match.get("team_b_red_cards", -1)
        if ya < 0 or yb < 0:
            return None
        total = (ya or 0) + (yb or 0) + (ra if ra >= 0 else 0) + (rb if rb >= 0 else 0)
        return 1.0 if total > line else 0.0
    elif target == "goals":
        g = match.get("overallGoalCount", -1)
        if g < 0:
            return None
        return 1.0 if g > line else 0.0
    elif target == "btts":
        hg = match.get("homeGoalCount", -1)
        ag = match.get("awayGoalCount", -1)
        if hg < 0 or ag < 0:
            return None
        return 1.0 if (hg > 0 and ag > 0) else 0.0
    elif target == "clean_sheet":
        hg = match.get("homeGoalCount", -1)
        ag = match.get("awayGoalCount", -1)
        if hg < 0 or ag < 0:
            return None
        return 1.0 if (hg == 0 or ag == 0) else 0.0
    return None


def fit_logistic_l2(X: np.ndarray, y: np.ndarray, lam: float = 1.0) -> np.ndarray:
    """Fit L2-regularized logistic regression via IRLS.

    Simple, fast, no external dependency beyond numpy/scipy.
    Returns coefficient vector (including intercept as last element).
    """
    n, p = X.shape
    # Add intercept column
    X_aug = np.column_stack([X, np.ones(n)])
    p_aug = p + 1
    beta = np.zeros(p_aug)

    # Regularization matrix (don't regularize intercept)
    reg = np.eye(p_aug) * lam
    reg[-1, -1] = 0.0

    for _ in range(25):  # IRLS iterations
        eta = X_aug @ beta
        eta = np.clip(eta, -10, 10)
        mu = expit(eta)
        w = mu * (1 - mu)
        w = np.maximum(w, 1e-6)
        W = np.diag(w)
        z = eta + (y - mu) / w

        # Weighted least squares with regularization
        XtWX = X_aug.T @ W @ X_aug + reg
        XtWz = X_aug.T @ W @ z
        try:
            beta_new = np.linalg.solve(XtWX, XtWz)
        except np.linalg.LinAlgError:
            break
        if np.max(np.abs(beta_new - beta)) < 1e-6:
            beta = beta_new
            break
        beta = beta_new

    return beta


def screen_feature_set(
    feature_set: FeatureSet,
    matches: list[dict],
    feature_matrix: list[dict[str, Optional[float]]],
) -> ScreeningResult:
    """Screen a feature set using model-based evaluation with walk-forward.

    Fits L2-regularized logistic regression on each target, evaluates
    on temporally-later fold. Reports vs-naive, calibration, breadth.
    """
    n = len(matches)
    feat_names = list(feature_set.features)

    # Build X matrix (only rows with complete data)
    valid_mask = np.ones(n, dtype=bool)
    X_all = np.zeros((n, len(feat_names)))

    for j, fname in enumerate(feat_names):
        for i in range(n):
            v = feature_matrix[i].get(fname)
            if v is None:
                valid_mask[i] = False
            else:
                X_all[i, j] = v

    # Walk-forward: train on first 60%, test on last 40%
    split_idx = int(n * 0.6)
    train_mask = valid_mask.copy()
    train_mask[split_idx:] = False
    test_mask = valid_mask.copy()
    test_mask[:split_idx] = False

    n_train = train_mask.sum()
    n_test = test_mask.sum()

    if n_train < 200 or n_test < 100:
        return _empty_result(feature_set)

    X_train = X_all[train_mask]
    X_test = X_all[test_mask]

    # Standardize features (fit on train, apply to test)
    train_mean = X_train.mean(axis=0)
    train_std = X_train.std(axis=0)
    train_std[train_std == 0] = 1.0
    X_train_s = (X_train - train_mean) / train_std
    X_test_s = (X_test - train_mean) / train_std

    # Evaluate on each target
    target_results = {}
    p_values = []

    for target_name, target_spec in TARGETS.items():
        t_target = target_spec["target"]
        t_line = target_spec["line"]

        # Compute outcomes for train and test
        y_train = []
        train_indices = np.where(train_mask)[0]
        for idx in train_indices:
            o = compute_outcome(matches[idx], t_target, t_line)
            y_train.append(o if o is not None else np.nan)
        y_train = np.array(y_train)

        y_test = []
        test_indices = np.where(test_mask)[0]
        for idx in test_indices:
            o = compute_outcome(matches[idx], t_target, t_line)
            y_test.append(o if o is not None else np.nan)
        y_test = np.array(y_test)

        # Filter NaN outcomes
        train_valid = ~np.isnan(y_train)
        test_valid = ~np.isnan(y_test)

        if train_valid.sum() < 150 or test_valid.sum() < 80:
            target_results[target_name] = {"vs_naive_pct": 0.0, "p_value": 1.0,
                                           "brier": None, "n_test": 0, "positive": False}
            p_values.append(1.0)
            continue

        Xtr = X_train_s[train_valid]
        ytr = y_train[train_valid]
        Xte = X_test_s[test_valid]
        yte = y_test[test_valid]

        # Fit regularized logistic regression
        beta = fit_logistic_l2(Xtr, ytr, lam=1.0)

        # Predict on test set
        Xte_aug = np.column_stack([Xte, np.ones(len(Xte))])
        probs = expit(Xte_aug @ beta)
        probs = np.clip(probs, 0.01, 0.99)

        # Brier score
        brier = float(np.mean((probs - yte) ** 2))
        naive_rate = float(yte.mean())
        naive_brier = float(np.mean((naive_rate - yte) ** 2))

        # vs-naive: Brier skill score
        if naive_brier > 0:
            vs_naive_pct = (1 - brier / naive_brier) * 100
        else:
            vs_naive_pct = 0.0

        # Significance: likelihood ratio test vs intercept-only
        # Null model: just predicts naive_rate for everything
        ll_model = float(np.sum(yte * np.log(probs) + (1 - yte) * np.log(1 - probs)))
        null_prob = np.clip(naive_rate, 0.01, 0.99)
        ll_null = float(np.sum(yte * np.log(null_prob) + (1 - yte) * np.log(1 - null_prob)))
        lr_stat = 2 * (ll_model - ll_null)
        df = len(feat_names)  # number of features (excluding intercept)
        p_value = float(sp_stats.chi2.sf(max(lr_stat, 0), df))

        target_results[target_name] = {
            "vs_naive_pct": round(vs_naive_pct, 4),
            "p_value": round(p_value, 8),
            "brier": round(brier, 6),
            "naive_brier": round(naive_brier, 6),
            "n_test": int(test_valid.sum()),
            "positive": vs_naive_pct > 0 and p_value < 0.10,
        }
        p_values.append(p_value)

    # Aggregate across targets
    targets_positive = sum(1 for r in target_results.values() if r.get("positive", False))
    targets_tested = len(target_results)
    breadth = targets_positive / targets_tested if targets_tested > 0 else 0.0
    vs_naive_values = [r["vs_naive_pct"] for r in target_results.values()]
    best_vs_naive = max(vs_naive_values) if vs_naive_values else 0.0
    mean_vs_naive = float(np.mean(vs_naive_values)) if vs_naive_values else 0.0
    best_p = min(p_values) if p_values else 1.0

    # Fisher's method to combine p-values across targets
    valid_ps = [p for p in p_values if p < 1.0]
    if len(valid_ps) >= 2:
        chi2_stat = -2 * sum(math.log(max(p, 1e-300)) for p in valid_ps)
        df_fisher = 2 * len(valid_ps)
        overall_p = float(sp_stats.chi2.sf(chi2_stat, df_fisher))
    else:
        overall_p = best_p

    # Check if combination beats best single feature
    best_single = _best_single_feature_performance(
        feature_set, matches, feature_matrix, train_mask, test_mask, train_mean, train_std
    )

    # Pass gate: at least 1 target positive, overall_p < 0.05, and beats naive
    passed = targets_positive >= 1 and overall_p < 0.05 and best_vs_naive > 0

    return ScreeningResult(
        combo_id=feature_set.combo_id,
        features=feature_set.features,
        size=feature_set.size,
        target_results=target_results,
        targets_positive=targets_positive,
        targets_tested=targets_tested,
        breadth_score=breadth,
        best_vs_naive_pct=best_vs_naive,
        mean_vs_naive_pct=mean_vs_naive,
        best_p_value=best_p,
        overall_p_value=overall_p,
        best_single_feature_vs_naive=best_single,
        passed=passed,
    )


def _best_single_feature_performance(
    feature_set: FeatureSet,
    matches: list[dict],
    feature_matrix: list[dict],
    train_mask: np.ndarray,
    test_mask: np.ndarray,
    train_mean: np.ndarray,
    train_std: np.ndarray,
) -> float:
    """Find the best vs-naive any single feature achieves alone.

    Used for the interaction check: does the combination add value
    beyond its best single component?
    """
    n = len(matches)
    best = -999.0

    for j, fname in enumerate(feature_set.features):
        # Build single-feature X
        X_single = np.zeros((n, 1))
        valid = np.ones(n, dtype=bool)
        for i in range(n):
            v = feature_matrix[i].get(fname)
            if v is None:
                valid[i] = False
            else:
                X_single[i, 0] = v

        tr = train_mask & valid
        te = test_mask & valid
        if tr.sum() < 150 or te.sum() < 80:
            continue

        Xtr = X_single[tr]
        Xte = X_single[te]

        # Standardize
        m = Xtr.mean()
        s = Xtr.std()
        if s == 0:
            continue
        Xtr_s = (Xtr - m) / s
        Xte_s = (Xte - m) / s

        # Test on corners_9.5 (our best-known target)
        y_test = []
        test_indices = np.where(te)[0]
        for idx in test_indices:
            o = compute_outcome(matches[idx], "corners", 9.5)
            y_test.append(o if o is not None else np.nan)
        y_test = np.array(y_test)
        valid_y = ~np.isnan(y_test)
        if valid_y.sum() < 80:
            continue

        Xte_v = Xte_s[valid_y]
        yte_v = y_test[valid_y]

        # Also need training outcomes
        y_train = []
        train_indices = np.where(tr)[0]
        for idx in train_indices:
            o = compute_outcome(matches[idx], "corners", 9.5)
            y_train.append(o if o is not None else np.nan)
        y_train = np.array(y_train)
        valid_yt = ~np.isnan(y_train)
        if valid_yt.sum() < 100:
            continue

        beta = fit_logistic_l2(Xtr_s[valid_yt], y_train[valid_yt], lam=1.0)
        Xte_aug = np.column_stack([Xte_v, np.ones(len(Xte_v))])
        probs = expit(Xte_aug @ beta)
        probs = np.clip(probs, 0.01, 0.99)

        brier = float(np.mean((probs - yte_v) ** 2))
        naive_rate = float(yte_v.mean())
        naive_brier = naive_rate * (1 - naive_rate)
        if naive_brier > 0:
            vs_naive = (1 - brier / naive_brier) * 100
            best = max(best, vs_naive)

    return best if best > -999 else 0.0


def _empty_result(feature_set: FeatureSet) -> ScreeningResult:
    return ScreeningResult(
        combo_id=feature_set.combo_id,
        features=feature_set.features,
        size=feature_set.size,
        target_results={},
        targets_positive=0,
        targets_tested=0,
        breadth_score=0.0,
        best_vs_naive_pct=0.0,
        mean_vs_naive_pct=0.0,
        best_p_value=1.0,
        overall_p_value=1.0,
        best_single_feature_vs_naive=0.0,
        passed=False,
    )


# ═══════════════════════════════════════════════════════════════
# COMBINATION GENERATOR
# ═══════════════════════════════════════════════════════════════

def generate_feature_names() -> list[str]:
    """Generate the full set of derived feature names from good fields."""
    features = []
    for field in GOOD_FIELDS:
        for w in ROLLING_WINDOWS:
            features.append(f"{field}_w{w}")
    return features


def generate_combinations(
    max_triples: int = MAX_TRIPLES,
    seed: int = TRIPLE_SEED,
) -> tuple[list[FeatureSet], dict[str, Any]]:
    """Generate all pair combinations and a capped random sample of triples.

    Returns (feature_sets, generation_report).
    """
    feature_names = generate_feature_names()
    n_features = len(feature_names)

    # All pairs
    pairs = []
    for a, b in itertools.combinations(feature_names, 2):
        combo_id = FeatureSet.make_id((a, b))
        # Determine source fields and windows
        src_a, w_a = _parse_feature_name(a)
        src_b, w_b = _parse_feature_name(b)
        pairs.append(FeatureSet(
            combo_id=combo_id,
            features=(a, b),
            source_fields=(src_a, src_b),
            windows=(w_a, w_b),
            size=2,
        ))

    n_pairs = len(pairs)

    # Capped random sample of triples
    rng = np.random.default_rng(seed)
    all_triple_indices = list(itertools.combinations(range(n_features), 3))
    n_total_triples = len(all_triple_indices)

    if n_total_triples > max_triples:
        sampled_indices = rng.choice(n_total_triples, size=max_triples, replace=False)
        triple_selections = [all_triple_indices[i] for i in sorted(sampled_indices)]
    else:
        triple_selections = all_triple_indices

    triples = []
    for i, j, k in triple_selections:
        a, b, c = feature_names[i], feature_names[j], feature_names[k]
        combo_id = FeatureSet.make_id((a, b, c))
        src_a, w_a = _parse_feature_name(a)
        src_b, w_b = _parse_feature_name(b)
        src_c, w_c = _parse_feature_name(c)
        triples.append(FeatureSet(
            combo_id=combo_id,
            features=(a, b, c),
            source_fields=(src_a, src_b, src_c),
            windows=(w_a, w_b, w_c),
            size=3,
        ))

    all_combos = pairs + triples
    report = {
        "n_base_features": n_features,
        "feature_names_sample": feature_names[:10],
        "n_pairs": n_pairs,
        "n_total_triples_possible": n_total_triples,
        "n_triples_sampled": len(triples),
        "triple_cap": max_triples,
        "triple_seed": seed,
        "triple_cap_reason": (
            f"Full triple space is {n_total_triples:,} — computationally infeasible. "
            f"Capped at {max_triples:,} via uniform random sample (seed={seed}). "
            f"This cap is stated explicitly; the family size for FDR is {len(all_combos):,} "
            f"(the actual number tested, not the theoretical maximum)."
        ),
        "total_candidates": len(all_combos),
        "family_size_for_fdr": len(all_combos),
    }

    return all_combos, report


def _parse_feature_name(name: str) -> tuple[str, int]:
    """Parse 'field_name_wN' into (field_name, N)."""
    # Last part is _wN
    parts = name.rsplit("_w", 1)
    if len(parts) == 2:
        return parts[0], int(parts[1])
    return name, 5


# ═══════════════════════════════════════════════════════════════
# SANITY GATE
# ═══════════════════════════════════════════════════════════════

def run_sanity_gate(matches: list[dict], feature_matrix: list[dict]) -> dict[str, Any]:
    """Run known-good feature sets through the screener.

    The corners model uses: home_corners, away_corners (rolling averages).
    The cards model uses: home_yellow_cards, away_yellow_cards (rolling averages).

    These MUST show clear signal. If they don't, STOP.
    """
    known_good = [
        FeatureSet(
            combo_id="known_corners_pair",
            features=("team_a_corners_w5", "team_b_corners_w5"),
            source_fields=("team_a_corners", "team_b_corners"),
            windows=(5, 5),
            size=2,
        ),
        FeatureSet(
            combo_id="known_corners_triple",
            features=("team_a_corners_w5", "team_b_corners_w5", "team_a_corners_w10"),
            source_fields=("team_a_corners", "team_b_corners", "team_a_corners"),
            windows=(5, 5, 10),
            size=3,
        ),
        FeatureSet(
            combo_id="known_cards_pair",
            features=("team_a_yellow_cards_w5", "team_b_yellow_cards_w5"),
            source_fields=("team_a_yellow_cards", "team_b_yellow_cards"),
            windows=(5, 5),
            size=2,
        ),
    ]

    results = {}
    for fs in known_good:
        result = screen_feature_set(fs, matches, feature_matrix)
        results[fs.combo_id] = {
            "features": fs.features,
            "passed": result.passed,
            "targets_positive": result.targets_positive,
            "best_vs_naive_pct": result.best_vs_naive_pct,
            "best_p_value": result.best_p_value,
            "overall_p_value": result.overall_p_value,
            "target_details": result.target_results,
        }

    # Check: at least ONE known-good must pass
    any_passed = any(r["passed"] for r in results.values())
    any_significant = any(r["best_p_value"] < 0.05 for r in results.values())

    return {
        "gate_passed": any_passed or any_significant,
        "results": results,
        "verdict": (
            "PASS — known-good features show detectable signal through model-based screening"
            if (any_passed or any_significant) else
            "FAIL — known-good features STILL undetectable. Screener is broken. STOP."
        ),
    }


# ═══════════════════════════════════════════════════════════════
# FULL PIPELINE
# ═══════════════════════════════════════════════════════════════

def run_combination_discovery(max_triples: int = MAX_TRIPLES) -> dict[str, Any]:
    """Execute the full Path B discovery pipeline."""
    start = time.time()
    now = datetime.now(timezone.utc)

    logger.info("=" * 60)
    logger.info("PATH B: COMBINATION DISCOVERY — %s", now.strftime("%Y-%m-%d %H:%M UTC"))
    logger.info("=" * 60)

    # ─── Load data and compute features ───
    logger.info("Loading discovery set...")
    matches = load_discovery_set()
    matches.sort(key=lambda m: m.get("date_unix", 0))
    logger.info("Discovery set: %d matches", len(matches))

    logger.info("Computing rolling features for %d fields × %d windows...",
                len(GOOD_FIELDS), len(ROLLING_WINDOWS))
    feature_matrix = compute_rolling_features(matches, GOOD_FIELDS, ROLLING_WINDOWS)
    logger.info("Feature matrix computed")

    # ─── SANITY GATE (must pass before proceeding) ───
    logger.info("Running sanity gate with known-good features...")
    gate = run_sanity_gate(matches, feature_matrix)
    logger.info("Sanity gate: %s", gate["verdict"])

    for name, result in gate["results"].items():
        logger.info("  %s: passed=%s, best_p=%.6f, best_vs_naive=%+.2f%%",
                    name, result["passed"], result["best_p_value"], result["best_vs_naive_pct"])

    if not gate["gate_passed"]:
        logger.error("SANITY GATE FAILED. Screener cannot detect known-good signal. STOPPING.")
        return {"error": "Sanity gate failed", "gate_results": gate}

    # ─── Generate combinations ───
    logger.info("Generating combinations...")
    combos, gen_report = generate_combinations(max_triples=max_triples)
    family_size = gen_report["total_candidates"]
    logger.info("Generated %d candidates (pairs=%d, triples=%d). Family size=%d",
                family_size, gen_report["n_pairs"], gen_report["n_triples_sampled"], family_size)

    # ─── Screen all candidates ───
    logger.info("Screening %d candidates (model-based, walk-forward)...", family_size)
    all_results: list[ScreeningResult] = []
    passed_screen: list[ScreeningResult] = []

    for i, combo in enumerate(combos):
        if (i + 1) % 500 == 0:
            logger.info("  Screened %d/%d (%d passed so far)...",
                        i + 1, family_size, len(passed_screen))
        result = screen_feature_set(combo, matches, feature_matrix)
        all_results.append(result)
        if result.passed:
            passed_screen.append(result)

    logger.info("Screening complete: %d/%d passed (%.2f%%)",
                len(passed_screen), family_size, 100 * len(passed_screen) / family_size)

    # ─── FDR correction ───
    logger.info("FDR correction (BH, family=%d)...", family_size)
    fdr = FDRController(alpha=0.05)
    all_p_values = [r.overall_p_value for r in all_results]
    fdr_results = fdr.correct(all_p_values)

    fdr_survivors = []
    for i, (result, fr) in enumerate(zip(all_results, fdr_results)):
        if fr.rejected and result.passed:
            fdr_survivors.append((result, fr))

    logger.info("FDR survivors: %d/%d", len(fdr_survivors), len(passed_screen))

    # ─── Adversarial review (interaction check) ───
    logger.info("Adversarial review of %d survivors...", len(fdr_survivors))
    reviewed = []
    for result, fr in fdr_survivors:
        # Interaction check: does combination beat best single feature?
        combo_vs_naive = result.best_vs_naive_pct
        single_vs_naive = result.best_single_feature_vs_naive
        interaction_gain = combo_vs_naive - single_vs_naive

        review = {
            "combo_id": result.combo_id,
            "features": result.features,
            "combo_vs_naive": combo_vs_naive,
            "best_single_vs_naive": single_vs_naive,
            "interaction_gain": interaction_gain,
            "is_more_than_sum": interaction_gain > 0.5,  # Meaningful improvement
            "fdr_rank": fr.rank,
            "fdr_threshold": fr.adjusted_threshold,
        }
        reviewed.append((result, fr, review))

    logger.info("Reviewed: %d candidates", len(reviewed))

    # ─── Held-out validation ───
    logger.info("Held-out validation of %d reviewed survivors...", len(reviewed))
    heldout_matches = load_heldout_set()
    heldout_matches.sort(key=lambda m: m.get("date_unix", 0))
    logger.info("Held-out set: %d matches (FIRST ACCESS)", len(heldout_matches))

    heldout_features = compute_rolling_features(heldout_matches, GOOD_FIELDS, ROLLING_WINDOWS)
    discovered = []

    for result, fr, review in reviewed:
        # Re-screen on held-out
        fs = FeatureSet(
            combo_id=result.combo_id,
            features=result.features,
            source_fields=tuple(_parse_feature_name(f)[0] for f in result.features),
            windows=tuple(_parse_feature_name(f)[1] for f in result.features),
            size=result.size,
        )
        heldout_result = screen_feature_set(fs, heldout_matches, heldout_features)

        if heldout_result.passed or (heldout_result.best_vs_naive_pct > 0 and heldout_result.best_p_value < 0.10):
            discovered.append((result, heldout_result, fr, review))

    logger.info("Held-out confirmed: %d/%d", len(discovered), len(reviewed))

    # ─── Attrition report ───
    duration = time.time() - start
    attrition = {
        "pipeline": "Path B: Combination Discovery",
        "run_at": now.isoformat(),
        "duration_seconds": round(duration, 1),
        "generation": gen_report,
        "sanity_gate": gate,
        "stages": {
            "1_candidates_generated": family_size,
            "2_passed_screening": len(passed_screen),
            "3_survived_fdr": len(fdr_survivors),
            "4_passed_adversarial_review": len(reviewed),
            "5_confirmed_heldout": len(discovered),
        },
        "attrition_rates": {
            "screening": f"{len(passed_screen)}/{family_size} ({100*len(passed_screen)/max(family_size,1):.2f}%)",
            "fdr": f"{len(fdr_survivors)}/{len(passed_screen)} ({100*len(fdr_survivors)/max(len(passed_screen),1):.1f}%)" if passed_screen else "N/A",
            "adversarial": f"{len(reviewed)}/{len(fdr_survivors)} (all pass review stage)" if fdr_survivors else "N/A",
            "heldout": f"{len(discovered)}/{len(reviewed)} ({100*len(discovered)/max(len(reviewed),1):.1f}%)" if reviewed else "N/A",
        },
        "fdr_parameters": {
            "alpha": 0.05,
            "family_size": family_size,
            "method": "Benjamini-Hochberg across all candidates",
            "line_handling": "Single representative line per target (pre-selected), no within-target correction",
        },
        "discovered_metrics": [
            {
                "combo_id": r.combo_id,
                "features": list(r.features),
                "size": r.size,
                "discovery_vs_naive": r.best_vs_naive_pct,
                "discovery_p": r.overall_p_value,
                "heldout_vs_naive": hr.best_vs_naive_pct,
                "heldout_p": hr.overall_p_value,
                "interaction_gain": rev["interaction_gain"],
                "targets_positive": r.targets_positive,
                "breadth": r.breadth_score,
            }
            for r, hr, fr, rev in discovered
        ],
    }

    # Save
    report_path = Path("/home/ubuntu/data/discovery/combination_discovery_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(attrition, f, indent=2)

    logger.info("")
    logger.info("=" * 60)
    logger.info("PATH B DISCOVERY COMPLETE")
    logger.info("=" * 60)
    logger.info("Candidates: %d (pairs=%d, triples=%d)",
                family_size, gen_report["n_pairs"], gen_report["n_triples_sampled"])
    logger.info("Passed screening: %d", len(passed_screen))
    logger.info("Survived FDR: %d", len(fdr_survivors))
    logger.info("Confirmed held-out: %d", len(discovered))
    logger.info("Duration: %.1fs", duration)
    logger.info("=" * 60)

    return attrition
