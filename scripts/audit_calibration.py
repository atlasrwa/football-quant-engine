#!/usr/bin/env python3
"""Independent audit: why does the model score worse on ECE than climatology?

Three candidate explanations, each measured rather than argued:

A. **Measurement artifact.** Expected calibration error is biased upward for a
   sharper forecaster. A constant predictor puts all its mass in one bin, so its
   ECE has one noise term; a spread-out forecaster has ten, each estimated on a
   tenth of the data. Comparing the two raw numbers penalises sharpness. The fix
   is to compare each against its own null: the ECE a *perfectly calibrated*
   forecaster with that exact probability spread and sample size would produce.

B. **Miscalibrated spread** — over- or under-confidence. Diagnosed by fitting a
   logistic recalibration ``logit(y) ~ a + b logit(p)``. ``b < 1`` means the
   forecasts are too extreme, ``b > 1`` too timid, ``b = 1`` correctly scaled.
   Also reports the mean-bias ``mean(p) - mean(y)``.

C. **A broken conditional-independence assumption.** The match total is the
   convolution of two side distributions, which assumes the two sides are
   independent given their fitted means. If they are positively correlated — both
   sides high in an open game — the convolution understates the variance of the
   total, and the published tails are too thin. Measured directly as the residual
   correlation between the two sides and as observed-versus-implied variance of
   the total.

Writes ``data/results/calibration_audit.json`` and prints a verdict per candidate.
Zero API calls.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Sequence

import numpy as np
from scipy.optimize import minimize

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.discovery.corpus import load_discovery_set, load_heldout_set  # noqa: E402
from src.research.evaluation.hierarchical_lines import (  # noqa: E402
    expected_calibration_error,
)
from src.research.models.hierarchical_market_model import (  # noqa: E402
    HierarchicalConfig,
    HierarchicalCountModel,
)
from src.research.models.market_family import (  # noqa: E402
    ALL_FAMILY_NAMES,
    family_by_name,
)
from src.research.models.side_rows import build_fixture_rows, training_rows  # noqa: E402

BINS = 10
OUT_PATH = REPO_ROOT / "data" / "results" / "calibration_audit.json"


# ─────────────────────────────────────────────────────────────────────────────
# Metric helpers
# ─────────────────────────────────────────────────────────────────────────────
def null_ece(
    probabilities: np.ndarray, *, draws: int = 400, seed: int = 11
) -> tuple[float, float]:
    """Mean and 95th percentile of ECE under perfect calibration.

    This is the floor: outcomes are generated *from the stated probabilities*, so
    any ECE at or below this level is indistinguishable from perfect calibration
    at this sample size and probability spread.
    """
    rng = np.random.default_rng(seed)
    values = np.empty(draws, dtype=float)
    for index in range(draws):
        simulated = (rng.random(len(probabilities)) < probabilities).astype(float)
        values[index] = expected_calibration_error(probabilities, simulated, BINS)
    return float(values.mean()), float(np.quantile(values, 0.95))


def reliability_slope(
    probabilities: np.ndarray, outcomes: np.ndarray
) -> tuple[float, float]:
    """Fit ``logit(y) ~ a + b logit(p)``. ``b`` is the confidence scale."""
    clipped = np.clip(probabilities, 1e-6, 1 - 1e-6)
    logit = np.log(clipped / (1 - clipped))

    def negative_log_likelihood(params: np.ndarray) -> float:
        z = np.clip(params[0] + params[1] * logit, -30, 30)
        p = 1 / (1 + np.exp(-z))
        p = np.clip(p, 1e-12, 1 - 1e-12)
        return -float(
            np.sum(outcomes * np.log(p) + (1 - outcomes) * np.log(1 - p))
        )

    result = minimize(
        negative_log_likelihood, np.array([0.0, 1.0]), method="Nelder-Mead"
    )
    return float(result.x[0]), float(result.x[1])


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def log_loss(p: np.ndarray, y: np.ndarray) -> float:
    c = np.clip(p, 1e-12, 1 - 1e-12)
    return float(-np.mean(y * np.log(c) + (1 - y) * np.log(1 - c)))


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward capture
# ─────────────────────────────────────────────────────────────────────────────
def capture(
    family, fixtures, *, min_train: int, refit_every: int, min_league: int
) -> dict:
    """Re-run the walk-forward, keeping every raw probability and side count."""
    ordered = sorted(fixtures, key=lambda f: (f.kickoff_unix, f.fixture_id))
    batches: list[list] = []
    cursor = 0
    while cursor < len(ordered):
        kickoff = ordered[cursor].kickoff_unix
        end = cursor + 1
        while end < len(ordered) and ordered[end].kickoff_unix == kickoff:
            end += 1
        batches.append(ordered[cursor:end])
        cursor = end

    rows: list[dict] = []
    sides: list[dict] = []
    training: list = []
    league_counts: dict[str, int] = defaultdict(int)
    model = None
    climatology: dict[tuple[str, float], float] = {}
    since_refit = 0

    for batch in batches:
        labelled = training_rows(training)
        if len(labelled) >= min_train and (model is None or since_refit >= refit_every):
            candidate = HierarchicalCountModel(family, HierarchicalConfig())
            try:
                candidate.fit(labelled)
                model = candidate
                totals: dict[str, list[float]] = defaultdict(list)
                for f in training:
                    if f.total_count is not None:
                        totals[f.league].append(f.total_count)
                climatology = {}
                for league, counts in totals.items():
                    for line in family.lines:
                        over = sum(1 for v in counts if v > line)
                        climatology[(league, line)] = (over + 1.0) / (len(counts) + 2.0)
                since_refit = 0
            except (ValueError, RuntimeError):
                pass

        if model is not None:
            for f in batch:
                if league_counts[f.league] < min_league or f.total_count is None:
                    continue
                if f.gate_reason is not None:
                    continue
                try:
                    dist = model.predict_match(f.home_row, f.away_row)
                except Exception:
                    continue
                sides.append(
                    {
                        "league": f.league,
                        "home_obs": f.home_count,
                        "away_obs": f.away_count,
                        "home_mean": dist.home.mean,
                        "away_mean": dist.away.mean,
                        "total_obs": f.total_count,
                        "total_var_implied": float(
                            np.sum(
                                (
                                    np.arange(len(dist.total_pmf))
                                    - dist.expected_total
                                )
                                ** 2
                                * np.asarray(dist.total_pmf)
                            )
                        ),
                    }
                )
                for line in family.lines:
                    ref = climatology.get((f.league, line))
                    if ref is None:
                        continue
                    rows.append(
                        {
                            "league": f.league,
                            "line": line,
                            "y": 1.0 if f.total_count > line else 0.0,
                            "p_model": dist.p_over(line),
                            "p_clim": ref,
                        }
                    )
        training.extend(batch)
        for f in batch:
            league_counts[f.league] += 1
        since_refit += 1

    return {"rows": rows, "sides": sides}


# ─────────────────────────────────────────────────────────────────────────────
# Analysis
# ─────────────────────────────────────────────────────────────────────────────
def analyse_arm(rows: Sequence[dict], key: str, label: str) -> dict:
    p = np.array([r[key] for r in rows], dtype=float)
    y = np.array([r["y"] for r in rows], dtype=float)
    observed = expected_calibration_error(p, y, BINS)
    floor, floor_p95 = null_ece(p)
    intercept, slope = reliability_slope(p, y)
    occupied = len({min(BINS - 1, int(v * BINS)) for v in p})
    return {
        "arm": label,
        "n": len(rows),
        "ece": round(observed, 5),
        "ece_null_mean": round(floor, 5),
        "ece_null_p95": round(floor_p95, 5),
        "ece_excess": round(observed - floor, 5),
        "ece_ratio_to_null": round(observed / floor, 3) if floor > 0 else None,
        "within_null": bool(observed <= floor_p95),
        "sharpness_sd": round(float(p.std()), 5),
        "occupied_bins": occupied,
        "mean_predicted": round(float(p.mean()), 5),
        "observed_rate": round(float(y.mean()), 5),
        "mean_bias": round(float(p.mean() - y.mean()), 5),
        "reliability_slope": round(slope, 4),
        "reliability_intercept": round(intercept, 4),
        "brier": round(brier(p, y), 5),
        "log_loss": round(log_loss(p, y), 5),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--families", nargs="+", default=list(ALL_FAMILY_NAMES))
    parser.add_argument("--leagues", type=int, default=6)
    parser.add_argument("--min-train", type=int, default=1200)
    parser.add_argument("--refit-every", type=int, default=100)
    parser.add_argument("--min-league", type=int, default=60)
    args = parser.parse_args(argv)

    matches = load_discovery_set() + load_heldout_set()
    leagues = sorted({str(m.get("_league") or "") for m in matches if m.get("_league")})
    keep = set(leagues[: args.leagues]) if args.leagues else set(leagues)
    matches = [m for m in matches if str(m.get("_league") or "") in keep]
    print(f"corpus: {len(matches)} fixtures, {len(keep)} leagues", flush=True)

    families = [family_by_name(name) for name in args.families]
    built = build_fixture_rows(matches, families)

    report: dict = {
        "schema_version": "calibration-audit/v1",
        "bins": BINS,
        "leagues": sorted(keep),
        "candidates": {
            "A_measurement_artifact": "ECE is biased upward for sharper forecasters",
            "B_miscalibrated_spread": "reliability slope != 1 means over/under-confident",
            "C_conditional_independence": "correlated sides understate total variance",
        },
        "families": {},
    }

    for family in families:
        print(f"\n=== {family.name} ===", flush=True)
        captured = capture(
            family,
            built[family.name],
            min_train=args.min_train,
            refit_every=args.refit_every,
            min_league=args.min_league,
        )
        rows, sides = captured["rows"], captured["sides"]
        if not rows:
            report["families"][family.name] = {"status": "no_predictions"}
            continue

        model = analyse_arm(rows, "p_model", "model")
        clim = analyse_arm(rows, "p_clim", "climatology")

        # Candidate C: is the conditional independence assumption holding?
        home_obs = np.array([s["home_obs"] for s in sides], dtype=float)
        away_obs = np.array([s["away_obs"] for s in sides], dtype=float)
        home_mu = np.array([s["home_mean"] for s in sides], dtype=float)
        away_mu = np.array([s["away_mean"] for s in sides], dtype=float)
        # Pearson residuals: what the model has not explained on each side.
        home_res = (home_obs - home_mu) / np.sqrt(np.clip(home_mu, 1e-9, None))
        away_res = (away_obs - away_mu) / np.sqrt(np.clip(away_mu, 1e-9, None))
        residual_correlation = float(np.corrcoef(home_res, away_res)[0, 1])
        total_obs = np.array([s["total_obs"] for s in sides], dtype=float)
        implied = np.array([s["total_var_implied"] for s in sides], dtype=float)
        expected_total = home_mu + away_mu
        observed_variance = float(np.mean((total_obs - expected_total) ** 2))
        implied_variance = float(np.mean(implied))

        family_report = {
            "status": "audited",
            "model": model,
            "climatology": clim,
            "conditional_independence": {
                "side_residual_correlation": round(residual_correlation, 4),
                "observed_total_variance": round(observed_variance, 4),
                "convolution_implied_variance": round(implied_variance, 4),
                "variance_ratio": round(observed_variance / implied_variance, 4),
                "understated": bool(observed_variance > implied_variance * 1.02),
            },
        }
        report["families"][family.name] = family_report

        print(
            f"  model       ECE {model['ece']:.4f}  null {model['ece_null_mean']:.4f}  "
            f"excess {model['ece_excess']:+.4f}  bins {model['occupied_bins']}  "
            f"sd {model['sharpness_sd']:.3f}  slope {model['reliability_slope']:.3f}"
        )
        print(
            f"  climatology  ECE {clim['ece']:.4f}  null {clim['ece_null_mean']:.4f}  "
            f"excess {clim['ece_excess']:+.4f}  bins {clim['occupied_bins']}  "
            f"sd {clim['sharpness_sd']:.3f}  slope {clim['reliability_slope']:.3f}"
        )
        ci = family_report["conditional_independence"]
        print(
            f"  sides: residual corr {ci['side_residual_correlation']:+.3f}  "
            f"var observed/implied {ci['variance_ratio']:.3f}"
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"\nwrote {OUT_PATH.relative_to(REPO_ROOT)}")
    _verdict(report)
    return 0


def _verdict(report: dict) -> None:
    audited = {k: v for k, v in report["families"].items() if v.get("status") == "audited"}
    if not audited:
        return
    print("\n" + "=" * 74)
    print("VERDICT")
    print("=" * 74)

    print("\nA. Measurement artifact — excess ECE over each arm's own null floor")
    print(f"  {'family':22s} {'model':>18s} {'climatology':>18s}")
    for name, f in sorted(audited.items()):
        m, c = f["model"], f["climatology"]
        print(
            f"  {name:22s} {m['ece']:.4f}/{m['ece_null_mean']:.4f}"
            f"={m['ece_excess']:+.4f} {c['ece']:.4f}/{c['ece_null_mean']:.4f}"
            f"={c['ece_excess']:+.4f}"
        )
    model_floor = np.mean([f["model"]["ece_null_mean"] for f in audited.values()])
    clim_floor = np.mean([f["climatology"]["ece_null_mean"] for f in audited.values()])
    print(
        f"  mean null floor: model {model_floor:.4f} vs climatology {clim_floor:.4f} "
        f"({model_floor / clim_floor:.1f}x)"
    )

    print("\nB. Confidence scale — reliability slope (1.0 = correctly scaled)")
    for name, f in sorted(audited.items()):
        slope = f["model"]["reliability_slope"]
        reading = (
            "too extreme" if slope < 0.9 else "too timid" if slope > 1.1 else "well scaled"
        )
        print(
            f"  {name:22s} slope {slope:6.3f}  bias {f['model']['mean_bias']:+.4f}  "
            f"{reading}"
        )

    print("\nC. Conditional independence of the two sides")
    for name, f in sorted(audited.items()):
        ci = f["conditional_independence"]
        print(
            f"  {name:22s} residual corr {ci['side_residual_correlation']:+.3f}  "
            f"variance observed/implied {ci['variance_ratio']:.3f}  "
            f"{'UNDERSTATED' if ci['understated'] else 'ok'}"
        )
    print("=" * 74)


if __name__ == "__main__":
    raise SystemExit(main())
