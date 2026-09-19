#!/usr/bin/env python3
"""Diagnose WHY corners is worse than climatology — defect vs mis-specification vs null.

Diagnose only. No fixes, no re-fitting of production artifacts, zero API calls.
Corners is the subject; cards is the control that isolates architecture from features
(same hierarchical machinery, only the feature block and count structure differ).

Answers, per league and never pooled-only:

  Q1 Degenerate vs actively wrong — per line: predicted-prob distribution (sd, range,
     mass within +/-0.05 of the base rate) and the correlation between predicted
     probability and realised outcome. A negative correlation is decisive.
  Q2 Reliability curve shape per line with bucket counts — tails vs spread, monotone
     mis-sloped vs non-monotone.
  Q3 Count structure — NB dispersion stability by league/fold, and the EMPIRICAL
     within-match correlation between home and away corner counts (raw, and residual
     after removing side means). Independent convolution cannot represent it.
  Q4 Feature informativeness — prior-only raw correlation of each corners feature with
     the realised side count, per league, against the same for cards.

Writes data/results/corners_diagnosis.json and prints a per-section summary.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

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
from src.research.models.market_family import family_by_name  # noqa: E402
from src.research.models.side_rows import build_fixture_rows, training_rows  # noqa: E402

BINS = 10
OUT_PATH = REPO_ROOT / "data" / "results" / "corners_diagnosis.json"

# Match audit_calibration.py defaults exactly, so this is the same walk-forward.
MIN_TRAIN = 1200
REFIT_EVERY = 100
MIN_LEAGUE = 60
N_LEAGUES = 6


def brier(p: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean((p - y) ** 2))


def safe_corr(a: np.ndarray, b: np.ndarray) -> float | None:
    if len(a) < 3 or np.std(a) < 1e-12 or np.std(b) < 1e-12:
        return None
    return float(np.corrcoef(a, b)[0, 1])


# ─────────────────────────────────────────────────────────────────────────────
# Walk-forward capture — identical discipline to scripts/audit_calibration.py,
# but retains per-(league,line) probabilities, per-fold dispersion, and per-match
# side counts so Q1-Q3 can be answered at league and line granularity.
# ─────────────────────────────────────────────────────────────────────────────
def capture(family, fixtures) -> dict:
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

    rows: list[dict] = []          # one per (fixture, line): p_model, p_clim, y, league, line
    sides: list[dict] = []         # one per scored fixture: home/away obs & means, league
    dispersion_folds: list[dict] = []  # per refit: global dispersion + per-league dispersion
    training: list = []
    league_counts: dict[str, int] = defaultdict(int)
    model = None
    climatology: dict[tuple[str, float], float] = {}
    since_refit = 0
    fold_index = 0

    for batch in batches:
        labelled = training_rows(training)
        if len(labelled) >= MIN_TRAIN and (model is None or since_refit >= REFIT_EVERY):
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
                # Record the count structure this fold selected.
                gl = model.global_layer
                dispersion_folds.append(
                    {
                        "fold": fold_index,
                        "n_train_rows": len(labelled),
                        "distribution": gl.distribution,
                        "global_dispersion_alpha": round(gl.dispersion, 5),
                        "residual_var_mean_ratio": round(
                            gl.residual_variance_mean_ratio, 4
                        ),
                        "signal_scale": round(model.signal_scale, 4),
                        "per_league_dispersion": {
                            lg: round(v, 4) for lg, v in model.league_dispersion.items()
                        },
                    }
                )
                fold_index += 1
                since_refit = 0
            except (ValueError, RuntimeError):
                pass

        if model is not None:
            for f in batch:
                if league_counts[f.league] < MIN_LEAGUE or f.total_count is None:
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
                        "expected_total": dist.expected_total,
                        "total_var_implied": float(
                            np.sum(
                                (np.arange(len(dist.total_pmf)) - dist.expected_total)
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
                            "line": float(line),
                            "y": 1.0 if f.total_count > line else 0.0,
                            "p_model": float(dist.p_over(line)),
                            "p_clim": float(ref),
                        }
                    )
        training.extend(batch)
        for f in batch:
            league_counts[f.league] += 1
        since_refit += 1

    return {"rows": rows, "sides": sides, "dispersion_folds": dispersion_folds}


# ─────────────────────────────────────────────────────────────────────────────
# Q1 + Q2: per line, degenerate-vs-wrong + reliability curve.
# ─────────────────────────────────────────────────────────────────────────────
def per_line_analysis(rows: list[dict], lines: list[float]) -> dict:
    out: dict[str, dict] = {}
    for line in lines:
        sub = [r for r in rows if r["line"] == line]
        if not sub:
            continue
        p = np.array([r["p_model"] for r in sub])
        y = np.array([r["y"] for r in sub])
        pc = np.array([r["p_clim"] for r in sub])
        base_rate = float(y.mean())
        near = float(np.mean(np.abs(p - base_rate) <= 0.05))
        # reliability curve, model
        curve = []
        edges = np.linspace(0.0, 1.0, BINS + 1)
        for i in range(BINS):
            lo, hi = edges[i], edges[i + 1]
            mask = (p >= lo) & (p <= hi) if i == BINS - 1 else (p >= lo) & (p < hi)
            n = int(mask.sum())
            curve.append(
                {
                    "bin": f"{lo:.1f}-{hi:.1f}",
                    "n": n,
                    "mean_pred": round(float(p[mask].mean()), 4) if n else None,
                    "obs_rate": round(float(y[mask].mean()), 4) if n else None,
                    "gap": round(float(p[mask].mean() - y[mask].mean()), 4) if n else None,
                }
            )
        out[str(line)] = {
            "n": len(sub),
            "base_rate": round(base_rate, 4),
            "pred_mean": round(float(p.mean()), 4),
            "pred_sd": round(float(p.std()), 4),
            "pred_min": round(float(p.min()), 4),
            "pred_max": round(float(p.max()), 4),
            "pred_iqr": [
                round(float(np.percentile(p, 25)), 4),
                round(float(np.percentile(p, 75)), 4),
            ],
            "mass_within_0.05_of_base": round(near, 4),
            "corr_pred_outcome": (
                round(safe_corr(p, y), 4) if safe_corr(p, y) is not None else None
            ),
            "clim_corr_pred_outcome": (
                round(safe_corr(pc, y), 4) if safe_corr(pc, y) is not None else None
            ),
            "clim_pred_sd": round(float(pc.std()), 4),
            "ece_model": round(expected_calibration_error(p, y, BINS), 5),
            "ece_clim": round(expected_calibration_error(pc, y, BINS), 5),
            "brier_model": round(brier(p, y), 5),
            "brier_clim": round(brier(pc, y), 5),
            "reliability_curve": curve,
        }
    return out


def per_league_line_corr(rows: list[dict], lines: list[float]) -> dict:
    """Correlation of predicted prob with outcome, per league per line."""
    out: dict[str, dict] = {}
    leagues = sorted({r["league"] for r in rows})
    for lg in leagues:
        out[lg] = {}
        for line in lines:
            sub = [r for r in rows if r["league"] == lg and r["line"] == line]
            if len(sub) < 20:
                continue
            p = np.array([r["p_model"] for r in sub])
            y = np.array([r["y"] for r in sub])
            pc = np.array([r["p_clim"] for r in sub])
            out[lg][str(line)] = {
                "n": len(sub),
                "base_rate": round(float(y.mean()), 4),
                "pred_sd": round(float(p.std()), 4),
                "corr_pred_outcome": (
                    round(safe_corr(p, y), 4) if safe_corr(p, y) is not None else None
                ),
                "brier_model": round(brier(p, y), 5),
                "brier_clim": round(brier(pc, y), 5),
                "brier_delta_vs_clim": round(brier(p, y) - brier(pc, y), 5),
            }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Q3: empirical within-match home/away correlation, per league.
# ─────────────────────────────────────────────────────────────────────────────
def side_dependence(sides: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for scope in ["POOLED"] + sorted({s["league"] for s in sides}):
        sub = sides if scope == "POOLED" else [s for s in sides if s["league"] == scope]
        if len(sub) < 30:
            continue
        home = np.array([s["home_obs"] for s in sub], dtype=float)
        away = np.array([s["away_obs"] for s in sub], dtype=float)
        hmu = np.array([s["home_mean"] for s in sub], dtype=float)
        amu = np.array([s["away_mean"] for s in sub], dtype=float)
        # raw within-match correlation of the two side counts
        raw = safe_corr(home, away)
        # residual (Pearson) correlation after removing fitted side means
        hres = (home - hmu) / np.sqrt(np.clip(hmu, 1e-9, None))
        ares = (away - amu) / np.sqrt(np.clip(amu, 1e-9, None))
        resid = safe_corr(hres, ares)
        total_obs = home + away
        implied = np.array([s["total_var_implied"] for s in sub], dtype=float)
        exp_total = hmu + amu
        obs_var = float(np.mean((total_obs - exp_total) ** 2))
        imp_var = float(np.mean(implied))
        out[scope] = {
            "n": len(sub),
            "raw_home_away_corr": round(raw, 4) if raw is not None else None,
            "residual_home_away_corr": round(resid, 4) if resid is not None else None,
            "observed_total_variance": round(obs_var, 4),
            "convolution_implied_variance": round(imp_var, 4),
            "variance_ratio_obs_over_implied": round(obs_var / imp_var, 4)
            if imp_var > 0
            else None,
        }
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Q4: prior-only raw feature-vs-realised-side-count correlation, per league.
# Uses the SideRow features (strictly-prior by construction) against the side count.
# ─────────────────────────────────────────────────────────────────────────────
def feature_informativeness(fixtures, family) -> dict:
    feature_names = list(family.feature_names)
    # collect per side row: features + realised count, tagged by league
    by_league: dict[str, dict[str, list]] = defaultdict(
        lambda: {"count": [], **{fn: [] for fn in feature_names}}
    )
    pooled: dict[str, list] = {"count": [], **{fn: [] for fn in feature_names}}
    for fx in fixtures:
        for row in (fx.home_row, fx.away_row):
            if row.count is None:
                continue
            by_league[row.league]["count"].append(float(row.count))
            pooled["count"].append(float(row.count))
            for fn in feature_names:
                v = float(row.features.get(fn, 0.0))
                by_league[row.league][fn].append(v)
                pooled[fn].append(v)

    def corr_block(store: dict[str, list]) -> dict:
        y = np.array(store["count"], dtype=float)
        block = {"n": len(y)}
        for fn in feature_names:
            x = np.array(store[fn], dtype=float)
            c = safe_corr(x, y)
            block[fn] = round(c, 4) if c is not None else None
        return block

    out = {"POOLED": corr_block(pooled)}
    for lg in sorted(by_league):
        if len(by_league[lg]["count"]) < 40:
            continue
        out[lg] = corr_block(by_league[lg])
    return out


def summarise_corr(feat: dict, feature_names: list[str]) -> dict:
    """Mean |corr| of the informative (produce/own) features across leagues."""
    prod_feats = [fn for fn in feature_names if fn.startswith("own_produce_")]
    per_league_absmax = []
    for lg, block in feat.items():
        if lg == "POOLED":
            continue
        vals = [abs(block[fn]) for fn in prod_feats if block.get(fn) is not None]
        if vals:
            per_league_absmax.append(max(vals))
    return {
        "produce_features": prod_feats,
        "pooled": {fn: feat["POOLED"].get(fn) for fn in prod_feats},
        "mean_max_abs_corr_across_leagues": round(
            float(np.mean(per_league_absmax)), 4
        )
        if per_league_absmax
        else None,
    }


def main() -> int:
    matches = load_discovery_set() + load_heldout_set()
    leagues = sorted({str(m.get("_league") or "") for m in matches if m.get("_league")})
    keep = set(leagues[:N_LEAGUES])
    matches = [m for m in matches if str(m.get("_league") or "") in keep]
    print(f"corpus: {len(matches)} fixtures, {len(keep)} leagues: {sorted(keep)}", flush=True)

    corners = family_by_name("corners")
    cards = family_by_name("cards")
    built = build_fixture_rows(matches, [corners, cards])

    report: dict = {
        "schema": "corners-diagnosis/v1",
        "leagues": sorted(keep),
        "walk_forward": {
            "min_train": MIN_TRAIN,
            "refit_every": REFIT_EVERY,
            "min_league": MIN_LEAGUE,
        },
        "families": {},
    }

    for family in (corners, cards):
        print(f"\n=== {family.name} ===", flush=True)
        cap = capture(family, built[family.name])
        rows, sides, folds = cap["rows"], cap["sides"], cap["dispersion_folds"]
        lines = list(family.lines)
        feat = feature_informativeness(built[family.name], family)
        report["families"][family.name] = {
            "lines": lines,
            "q1q2_per_line": per_line_analysis(rows, lines),
            "q1_per_league_line": per_league_line_corr(rows, lines),
            "q3_side_dependence": side_dependence(sides),
            "q3_dispersion_folds": folds,
            "q4_feature_corr": feat,
            "q4_summary": summarise_corr(feat, list(family.feature_names)),
        }
        # console summary
        pl = report["families"][family.name]["q1q2_per_line"]
        for line, d in pl.items():
            print(
                f"  line {line}: base {d['base_rate']:.3f} pred_sd {d['pred_sd']:.3f} "
                f"clim_sd {d['clim_pred_sd']:.3f} mass_near {d['mass_within_0.05_of_base']:.2f} "
                f"corr(p,y) {d['corr_pred_outcome']} clim_corr {d['clim_corr_pred_outcome']} "
                f"| ECE m/c {d['ece_model']:.4f}/{d['ece_clim']:.4f} "
                f"Brier m/c {d['brier_model']:.4f}/{d['brier_clim']:.4f}"
            )
        sd = report["families"][family.name]["q3_side_dependence"].get("POOLED", {})
        print(
            f"  Q3 pooled: raw home-away corr {sd.get('raw_home_away_corr')}  "
            f"residual {sd.get('residual_home_away_corr')}  "
            f"var obs/implied {sd.get('variance_ratio_obs_over_implied')}"
        )
        qs = report["families"][family.name]["q4_summary"]
        print(
            f"  Q4: produce-feature pooled corr {qs['pooled']}  "
            f"mean-max-abs across leagues {qs['mean_max_abs_corr_across_leagues']}"
        )

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"\nwrote {OUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
