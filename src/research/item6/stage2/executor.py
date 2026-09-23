"""ITEM 6 STAGE 2 executor (`item6_stage2_executor_v1`).

Mechanically executes the FROZEN Stage-2 design (design HEAD f3b7d332, protocol canonical
sha256 77384b9b...). It adds no design choice of its own beyond those recorded, before any fit,
in ITEM6_STAGE2_EXECUTION_BINDING_V1.json (`EXECUTOR_DECISIONS` below). Those are choices the
frozen artifacts left implicit; each is resolved by the frozen generator's own rule or by
inheriting the champion fitter, never by looking at a result.

Phases
------
  bind      write the binding artifact (hashes + executor decisions). Reads no outcome.
  predict   GATED. Fit every arm on every fold and freeze raw + calibrated predictions.
  evaluate  GATED. Score the frozen predictions and apply the frozen decision rule.

The gate refuses to fit or score unless: HEAD == --authorized-head, the worktree is clean,
every change since the design HEAD is an ADDED file (no frozen file modified), every frozen
artifact hash verifies, the executor file matches the binding, the corpus digest matches the
binding, the champion is unchanged, and every imported module resolves inside this checkout.

No LLM call. No network. CHAMPION is read (hashed) only, never written.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[4]
for _p in (str(ROOT / "scripts"), str(ROOT)):
    if _p in sys.path:
        sys.path.remove(_p)
    sys.path.insert(0, _p)

import numpy as np  # noqa: E402

from src.research.item6.stage2 import evaluation as EV  # noqa: E402
from src.research.item6.stage2 import feature_generator as FG  # noqa: E402
from src.research.item6.stage2 import feature_spec as FS  # noqa: E402
from src.research.item6.stage2 import model_specs as MS  # noqa: E402
from src.research.item6.stage2 import similarity_policy as SP  # noqa: E402
from src.research.item6.stage2 import threshold_policy as TP  # noqa: E402

EXECUTOR_VERSION = "item6_stage2_executor_v1"

DESIGN_HEAD = "f3b7d3322e2a208f2739ca4790b023cba4cd73bc"
PROTOCOL_CANONICAL_SHA256 = "77384b9b5f3374123dcd01a710c6c09f93a9b1d019a8817c16869e39d58f584f"
STAGE1_REGISTRY_CANONICAL_SHA256 = (
    "037281432c8969345d6103636076c903668da0105acbddb908590d76f4f12d70")
FOLD_MANIFEST_ROW_SHA256 = "9fc0f2b5c58210d27d57948c17538c6ff3489771473c9d2c369c29b5429141c3"
CHAMPION_PATH = "data/discovery/pilotC_stat_mixer.json"
CHAMPION_SHA256 = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

STAGE2_DIR = ROOT / "research" / "item6" / "stage2"
OUT_DIR = STAGE2_DIR / "execution"
BINDING_NAME = "ITEM6_STAGE2_EXECUTION_BINDING_V1.json"
PREDICTIONS_NAME = "ITEM6_STAGE2_OOS_PREDICTIONS_V1.jsonl"
FOLD_DIAG_NAME = "ITEM6_STAGE2_FOLD_DIAGNOSTICS_V1.json"
FEATSEL_NAME = "ITEM6_STAGE2_FEATURE_SELECTION_DIAGNOSTICS_V1.json"
PRIMARY_NAME = "ITEM6_STAGE2_PRIMARY_EVALUATION_V1.json"
SECONDARY_NAME = "ITEM6_STAGE2_SECONDARY_EVALUATION_V1.json"
EVIDENCE_NAME = "ITEM6_STAGE2_EXECUTION_EVIDENCE_MANIFEST_V1.json"

PRIMARY_TARGET = ("goals", 2.5)
SECONDARY_TARGETS: Tuple[Tuple[str, float], ...] = (("corners", 9.5), ("cards", 3.5))

ABLATION_FAMILY: Dict[str, str] = {
    "M1_THRESHOLD_ONLY": "SF_THRESHOLD_NONLINEARITY",
    "M1_MULTIMETRIC_ONLY": "SF_MULTIMETRIC_INTERACTION",
    "M1_HALF_STATE_ONLY": "SF_HALF_OR_GAME_STATE_INTERACTION",
    "M1_PROFILE_ONLY": "SF_TWO_AXIS_OPPONENT_PROFILE_INTERSECTION",
}
PRIMARY_ARMS: Tuple[str, ...] = ("M0", "M1_ALL") + tuple(ABLATION_FAMILY)
SECONDARY_ARMS: Tuple[str, ...] = ("M0", "M1_ALL")

NONZERO_COEF = 1e-8          # champion selection threshold
N_OUTER_JOBS = 4             # compute-only parallelism across (target, arm, fold) jobs

#: Choices the frozen artifacts left implicit, resolved here BEFORE any fit and bound into the
#: execution binding. None of them was informed by any result.
EXECUTOR_DECISIONS: Dict[str, str] = {
    "feature_history":
        "every feature (M0 and LLM-derived) for every fixture, training or test, is computed "
        "from ALL completed corpus matches with date_unix < that fixture's kickoff, via the "
        "frozen roll()/generate_features() PIT rule. A test fixture late in a test block "
        "therefore uses matches completed earlier in the same block, as the frozen generator's "
        "pit_rule requires. Only thresholds, standardisation, similarity banding, coverage "
        "screen, model and calibrator are frozen at the fold's train cutoff.",
    "training_rows":
        "champion rule: all completed corpus matches with date_unix < the fold's "
        "train_end_unix whose target label is resolvable by mix.outcome(); ordered by "
        "(date_unix, fixture_key) because TimeSeriesSplit depends on row order.",
    "test_rows":
        "the frozen fold manifest's TEST rows for that fold whose label is resolvable; mapped "
        "to corpus matches by fixture_key (verified 1:1).",
    "threshold_and_similarity_fit_rows":
        "all completed corpus matches with date_unix < train_end_unix (target-independent), "
        "both team slots, including the 2H_SHARE statistics, exactly the build script's "
        "pattern; the build's 2500/5000-row samples were for its coverage estimate only.",
    "coverage_screen":
        "per fold and target, a column is kept iff its non-missing rate over that fold's "
        "training rows >= 0.60; applied identically to M0 and LLM-derived columns; fewer than "
        "3 kept M0 columns = unfit fold (champion rule).",
    "m0_pool_per_target":
        "mix.feat_names(market) for each target's market: goals 72, corners 96, cards 48; "
        "M1_ALL = that pool + the same 108 LLM-derived columns.",
    "arms_per_target":
        "primary goals_2.5: M0, M1_ALL and the 4 single-family ablations. Secondary targets: "
        "M0 and M1_ALL only.",
    "final_model":
        "GridSearchCV(refit=True).best_estimator_, i.e. the (imputer->scaler->model) pipeline "
        "refit on all training rows with the selected (C, l1_ratio). GridSearchCV "
        "error_score='raise'; n_jobs=1 inside each job.",
    "convergence_warnings":
        "a ConvergenceWarning still yields a fitted model: counted and reported, not a fold "
        "failure. Only an exception or single-class labels make a fold unfit.",
    "calibration_oof":
        "for each of the 4 inner TimeSeriesSplit splits of the training rows, clone the "
        "pipeline with the selected params, fit on the inner train split, predict the inner "
        "validation split; isotonic is fit on the pooled pairs. A split with single-class "
        "inner training labels makes the fold unfit (calibration inability).",
    "bootstrap_draw":
        "rng = numpy.random.default_rng(0) created afresh for each comparison; one call "
        "rng.integers(0, n_blocks, size=(10000, n_blocks)); blocks sorted by ISO-week label.",
    "one_sided_p": "fraction of bootstrap replicate deltas <= 0.",
    "bh":
        "standard Benjamini-Hochberg step-up adjusted q-values, capped at 1; pass iff q <= 0.10.",
    "scored_set_per_comparison":
        "for each comparison (M0 vs one arm, same target), fixtures with a finite final "
        "probability from BOTH arms in folds fit by BOTH arms.",
    "single_run":
        "all arms, targets and folds are fit in ONE predict invocation; no partial rerun, no "
        "second seed.",
    "power_reading":
        "realised SE = sd(ddof=1) of the bootstrap replicates; the 80%-power effect size is "
        "max(1.96*SE, MPI) + 0.8416*SE; a FAIL whose 80%-power effect size exceeds MPI is "
        "labelled FAIL_AT_FROZEN_GATE_WITH_LIMITED_POWER_AT_0.0010. The gate is unchanged by it.",
}


# ─────────────────────────────── hashing / git gate ───────────────────────────────
def canon(o) -> bytes:
    return json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def canonical_sha(o: Dict) -> str:
    return hashlib.sha256(canon({k: v for k, v in o.items() if k != "artifact_sha256"})
                          ).hexdigest()


def file_sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True,
                          text=True).stdout.strip()


class GateError(RuntimeError):
    pass


def corpus_digest(corpus_dir: str) -> Dict[str, object]:
    import glob
    files = sorted(glob.glob(f"{corpus_dir}/league-matches_*.json"))
    lines = [f"{Path(f).name}:{file_sha(Path(f))}" for f in files]
    return {"corpus_dir": corpus_dir, "n_files": len(files),
            "digest_sha256": hashlib.sha256("\n".join(lines).encode()).hexdigest()}


def verify_git_state(authorized_head: str, *, since: str = DESIGN_HEAD) -> Dict[str, object]:
    head = _git("rev-parse", "HEAD")
    if head != authorized_head:
        raise GateError(f"HEAD {head} != authorized {authorized_head}")
    if _git("status", "--porcelain"):
        raise GateError("worktree is not clean")
    subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", since, head],
                   check=True)
    changes = [ln for ln in _git("diff", "--name-status", since, head).splitlines() if ln]
    modified = [ln for ln in changes if not ln.startswith("A\t")]
    if modified:
        raise GateError(f"frozen files changed since {since}: {modified}")
    return {"head": head, "clean": True, "descends_from": since,
            "changes_since_design_head": changes}


def verify_frozen_artifacts() -> Dict[str, object]:
    prot = json.loads((STAGE2_DIR / "ITEM6_STAGE2_PROTOCOL_V1.json").read_text())
    if prot["artifact_sha256"] != PROTOCOL_CANONICAL_SHA256 or \
            canonical_sha(prot) != PROTOCOL_CANONICAL_SHA256:
        raise GateError("protocol canonical hash mismatch")
    checked = {}
    for name, rec in sorted(prot["artifacts"].items()):
        o = json.loads((STAGE2_DIR / name).read_text())
        h = canonical_sha(o)
        if h != rec["sha256"] or o.get("artifact_sha256") != h:
            raise GateError(f"{name} canonical hash mismatch")
        checked[name] = h
    for name in ("ITEM6_STAGE2_RUN_MANIFEST_V1.json",
                 "ITEM6_STAGE2_OUTCOME_BLINDNESS_AUDIT_V1.json"):
        o = json.loads((STAGE2_DIR / name).read_text())
        if canonical_sha(o) != o["artifact_sha256"]:
            raise GateError(f"{name} canonical hash mismatch")
        checked[name] = o["artifact_sha256"]
    run_man = json.loads((STAGE2_DIR / "ITEM6_STAGE2_RUN_MANIFEST_V1.json").read_text())
    expected = {k: v["sha256"] for k, v in prot["artifacts"].items()}
    expected["ITEM6_STAGE2_PROTOCOL_V1.json"] = PROTOCOL_CANONICAL_SHA256
    if {k: v["sha256"] for k, v in run_man["artifacts"].items()} != expected:
        raise GateError("run manifest does not bind exactly the protocol + its artifacts")
    fm = json.loads((STAGE2_DIR / "ITEM6_STAGE2_FOLD_MANIFEST_V1.json").read_text())
    row_hash = hashlib.sha256(canon({k: v for k, v in fm.items()
                                     if k not in ("fold_manifest_sha256", "artifact_sha256")})
                              ).hexdigest()
    if fm["fold_manifest_sha256"] != FOLD_MANIFEST_ROW_SHA256 or row_hash != \
            FOLD_MANIFEST_ROW_SHA256:
        raise GateError("fold manifest row-level hash mismatch")
    reg = json.loads(Path(prot["stage1_inputs"]["stage1_result_path"]).with_name(
        "ITEM6_STAGE1_NOVEL_FAMILY_REGISTRY_V1.json").read_text())
    if reg["novel_family_registry_sha256"] != STAGE1_REGISTRY_CANONICAL_SHA256 or \
            prot["stage1_inputs"]["stage1_novel_family_registry_sha256"] != \
            STAGE1_REGISTRY_CANONICAL_SHA256:
        raise GateError("stage-1 registry hash mismatch")
    champ = champion_sha()
    if champ != CHAMPION_SHA256:
        raise GateError("CHAMPION hash mismatch")
    return {"protocol_canonical_sha256": PROTOCOL_CANONICAL_SHA256,
            "run_manifest_canonical_sha256": run_man["artifact_sha256"],
            "fold_manifest_row_sha256": FOLD_MANIFEST_ROW_SHA256,
            "fold_manifest_canonical_sha256": fm["artifact_sha256"],
            "stage1_registry_sha256": STAGE1_REGISTRY_CANONICAL_SHA256,
            "artifact_canonical_sha256": checked, "champion_sha256": champ}


def champion_sha() -> str:
    """CHAMPION hash; the checkout copy and the live /home/ubuntu copy must agree."""
    hs = {file_sha(p) for p in (ROOT / CHAMPION_PATH, Path("/home/ubuntu") / CHAMPION_PATH)
          if p.exists()}
    if len(hs) != 1:
        raise GateError(f"CHAMPION copies disagree or are missing: {hs}")
    return hs.pop()


def verify_imports(mix_module) -> None:
    for mod in (mix_module, EV, FG, FS, MS, SP, TP, sys.modules[__name__]):
        f = Path(mod.__file__).resolve()
        if ROOT not in f.parents:
            raise GateError(f"{mod.__name__} imported from outside this checkout: {f}")


# ─────────────────────────────── fitting machinery ───────────────────────────────
def make_pipeline():
    from sklearn.impute import SimpleImputer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    e = MS.ESTIMATOR
    return Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
        ("model", LogisticRegression(penalty=e["penalty"], solver=e["solver"],
                                     max_iter=e["max_iter"], tol=e["tol"],
                                     random_state=e["random_state"],
                                     fit_intercept=e["fit_intercept"],
                                     class_weight=e["class_weight"])),
    ])


def fit_arm(Xtr: np.ndarray, ytr: np.ndarray, Xte: np.ndarray) -> Dict[str, object]:
    """The ONE fitting routine every arm uses. Arms differ only in the columns passed in."""
    from sklearn.base import clone
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.isotonic import IsotonicRegression
    from sklearn.model_selection import GridSearchCV, TimeSeriesSplit

    if len(set(ytr.tolist())) < 2:
        return {"status": "UNFIT_SINGLE_CLASS_TRAINING_LABELS"}
    cv = TimeSeriesSplit(n_splits=MS.INNER_CV_SPLITS)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        try:
            search = GridSearchCV(make_pipeline(),
                                  {"model__C": list(MS.C_GRID),
                                   "model__l1_ratio": list(MS.L1_RATIO_GRID)},
                                  cv=cv, scoring="neg_log_loss", refit=True, n_jobs=1,
                                  error_score="raise")
            search.fit(Xtr, ytr)
            best = dict(search.best_params_)
            oof_p, oof_y = [], []
            for tr, va in cv.split(Xtr):
                if len(set(ytr[tr].tolist())) < 2:
                    return {"status": "UNFIT_CALIBRATION_SINGLE_CLASS_INNER_SPLIT"}
                est = clone(make_pipeline()).set_params(**best).fit(Xtr[tr], ytr[tr])
                oof_p.append(est.predict_proba(Xtr[va])[:, 1])
                oof_y.append(ytr[va])
        except Exception as exc:  # frozen policy: unfit fold, no refit with other settings
            return {"status": "UNFIT_EXCEPTION", "error": f"{type(exc).__name__}: {exc}"}
    n_conv = sum(1 for w in caught if issubclass(w.category, ConvergenceWarning))
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0, increasing=True)
    op, oy = np.concatenate(oof_p), np.concatenate(oof_y)
    iso.fit(op, oy)
    raw = search.best_estimator_.predict_proba(Xte)[:, 1] if len(Xte) else np.array([])
    cal = iso.predict(raw) if len(raw) else np.array([])
    lo, hi = MS.PROBABILITY_CLIP
    final = np.clip(cal, lo, hi)
    imp = search.best_estimator_.named_steps["imputer"]
    kept_mask = ~np.isnan(imp.statistics_)
    coef_full = np.zeros(Xtr.shape[1])
    coef_full[kept_mask] = search.best_estimator_.named_steps["model"].coef_[0]
    return {
        "status": "FIT",
        "selected_C": float(best["model__C"]),
        "selected_l1_ratio": float(best["model__l1_ratio"]),
        "cv_best_mean_neg_log_loss": float(search.best_score_),
        "n_convergence_warnings": int(n_conv),
        "n_calibration_pairs": int(len(op)),
        "n_train": int(len(ytr)),
        "raw": raw, "calibrated": cal, "final": final,
        "coef": coef_full,
        "n_clipped_low": int(np.sum(cal <= lo)), "n_clipped_high": int(np.sum(cal >= hi)),
    }


def coverage_keep(X: np.ndarray, min_rate: float = MS.MIN_NONMISSING_RATE) -> List[int]:
    if X.shape[0] == 0:
        return []
    rate = np.mean(~np.isnan(X), axis=0)
    return [i for i in range(X.shape[1]) if rate[i] >= min_rate]


def arm_columns(arm: str, m0_kept: Sequence[str], llm_kept: Sequence[str],
                family_of: Dict[str, str]) -> List[str]:
    if arm == "M0":
        return list(m0_kept)
    if arm == "M1_ALL":
        return list(m0_kept) + list(llm_kept)
    fam = ABLATION_FAMILY[arm]
    return list(m0_kept) + [c for c in llm_kept if family_of[c] == fam]


# ─────────────────────────────── evaluation machinery ───────────────────────────────
def ece(p: np.ndarray, y: np.ndarray, n_bins: int = EV.ECE_N_BINS) -> float:
    """Champion ECE (scripts/pilotC_stat_mixer.py:340), verbatim semantics."""
    e = 0.0
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        mk = (p >= lo) & (p < hi if b < n_bins - 1 else p <= hi)
        if mk.sum():
            e += (mk.sum() / len(p)) * abs(p[mk].mean() - y[mk].mean())
    return float(e)


def calibration_table(p: np.ndarray, y: np.ndarray, n_bins: int = EV.ECE_N_BINS) -> List[Dict]:
    rows = []
    for b in range(n_bins):
        lo, hi = b / n_bins, (b + 1) / n_bins
        mk = (p >= lo) & (p < hi if b < n_bins - 1 else p <= hi)
        rows.append({"bin": b, "lo": lo, "hi": hi, "n": int(mk.sum()),
                     "mean_p": (float(p[mk].mean()) if mk.sum() else None),
                     "mean_y": (float(y[mk].mean()) if mk.sum() else None)})
    return rows


def block_bootstrap(delta: np.ndarray, blocks: Sequence[str]) -> Dict[str, object]:
    labels = sorted(set(blocks))
    ix = {b: i for i, b in enumerate(labels)}
    bi = np.array([ix[b] for b in blocks])
    nb = len(labels)
    bsum = np.bincount(bi, weights=delta, minlength=nb)
    bcnt = np.bincount(bi, minlength=nb).astype(float)
    rng = np.random.default_rng(EV.BOOTSTRAP_SEED)
    draw = rng.integers(0, nb, size=(EV.BOOTSTRAP_RESAMPLES, nb))
    reps = bsum[draw].sum(axis=1) / bcnt[draw].sum(axis=1)
    lo, hi = np.percentile(reps, [2.5, 97.5])
    return {"n_blocks": nb, "ci_lower": float(lo), "ci_upper": float(hi),
            "bootstrap_se": float(np.std(reps, ddof=1)),
            "one_sided_p_delta_le_0": float(np.mean(reps <= 0.0)),
            "n_resamples": int(EV.BOOTSTRAP_RESAMPLES), "seed": int(EV.BOOTSTRAP_SEED)}


def bh_adjust(pvals: Sequence[float]) -> List[float]:
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    q = [0.0] * m
    running = 1.0
    for rank in range(m, 0, -1):
        i = order[rank - 1]
        running = min(running, pvals[i] * m / rank)
        q[i] = min(1.0, running)
    return q


def _phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def compare(rows_a: Dict[str, Dict], rows_b: Dict[str, Dict]) -> Dict[str, object]:
    """Paired comparison of arm A (M0) vs arm B on the intersection of scoreable fixtures."""
    keys = sorted(k for k in rows_a if k in rows_b
                  and np.isfinite(rows_a[k]["p_final"]) and np.isfinite(rows_b[k]["p_final"]))
    y = np.array([rows_a[k]["y"] for k in keys], float)
    if any(rows_a[k]["y"] != rows_b[k]["y"] for k in keys):
        raise AssertionError("label mismatch between arms")
    pa = np.array([rows_a[k]["p_final"] for k in keys])
    pb = np.array([rows_b[k]["p_final"] for k in keys])
    lla = np.array([EV.logloss(p, t) for p, t in zip(pa, y)])
    llb = np.array([EV.logloss(p, t) for p, t in zip(pb, y)])
    d = lla - llb
    bs = block_bootstrap(d, [rows_a[k]["iso_week_block"] for k in keys])
    ece_a, ece_b = ece(pa, y), ece(pb, y)
    delta = float(d.mean())
    return {
        "n_paired": len(keys),
        "n_dropped_from_a": len(rows_a) - len(keys), "n_dropped_from_b": len(rows_b) - len(keys),
        "logloss_a": float(lla.mean()), "logloss_b": float(llb.mean()),
        "delta_logloss_a_minus_b": delta,
        "brier_a": float(np.mean((pa - y) ** 2)), "brier_b": float(np.mean((pb - y) ** 2)),
        "brier_delta_a_minus_b": float(np.mean((pa - y) ** 2) - np.mean((pb - y) ** 2)),
        "residual_deviance_delta": float(2.0 * len(keys) * delta),
        "ece_a": ece_a, "ece_b": ece_b, "ece_delta_b_minus_a": ece_b - ece_a,
        "bootstrap": bs, "base_rate": float(y.mean()),
        "calibration_table_a": calibration_table(pa, y),
        "calibration_table_b": calibration_table(pb, y),
    }


def decision(cmp: Dict[str, object]) -> Dict[str, object]:
    d = cmp["delta_logloss_a_minus_b"]
    s1 = d > 0
    s2 = cmp["bootstrap"]["ci_lower"] > 0
    s3 = d >= EV.MINIMUM_PRACTICAL_LOGLOSS_IMPROVEMENT
    s4 = cmp["ece_b"] <= cmp["ece_a"] + EV.MAX_ECE_DETERIORATION
    return {"S2P1_DELTA_POSITIVE": bool(s1), "S2P2_CI_LOWER_GT_ZERO": bool(s2),
            "S2P3_DELTA_GTE_0_001": bool(s3), "S2P4_CALIBRATION_PASS": bool(s4),
            "ITEM6_STAGE2_PRIMARY_GATE": "PASS" if (s1 and s2 and s3 and s4) else "FAIL"}


def precision_reading(cmp: Dict[str, object], gate: str) -> Dict[str, object]:
    mpi = EV.MINIMUM_PRACTICAL_LOGLOSS_IMPROVEMENT
    se = cmp["bootstrap"]["bootstrap_se"]
    bar = max(1.959963985 * se, mpi)
    eff80 = bar + 0.841621234 * se
    p_at_mpi = 1.0 - _phi((bar - mpi) / se) if se > 0 else float("nan")
    out = {
        "REALIZED_DELTA": cmp["delta_logloss_a_minus_b"],
        "REALIZED_CI_WIDTH": cmp["bootstrap"]["ci_upper"] - cmp["bootstrap"]["ci_lower"],
        "REALIZED_BOOTSTRAP_SE": se,
        "CAN_EXCLUDE_ZERO": cmp["bootstrap"]["ci_lower"] > 0 or cmp["bootstrap"]["ci_upper"] < 0,
        "CAN_EXCLUDE_NEGATIVE_0_001": cmp["bootstrap"]["ci_lower"] > -mpi,
        "CI_HALF_WIDTH_AT_OR_BELOW_MPI": (cmp["bootstrap"]["ci_upper"]
                                          - cmp["bootstrap"]["ci_lower"]) / 2 <= mpi,
        "TRUE_DELTA_FOR_80PCT_POWER_UNDER_REALIZED_SE": eff80,
        "POWER_AT_TRUE_DELTA_EQUAL_MPI_UNDER_REALIZED_SE": p_at_mpi,
        "CAN_RELIABLY_DETECT_0_001_UNDER_REALIZED_SE": bool(p_at_mpi >= 0.8),
    }
    if gate == "FAIL":
        out["FAIL_INTERPRETATION"] = (
            "FAIL_AT_FROZEN_GATE_WITH_LIMITED_POWER_AT_0.0010" if eff80 > mpi
            else "FAIL_AT_FROZEN_GATE_WITH_ADEQUATE_POWER_AT_0.0010")
    return out


# ─────────────────────────────── phases ───────────────────────────────
def _load_mix():
    import pilotC_stat_mixer as mix
    return mix


def _write_json(path: Path, obj: Dict) -> str:
    obj = dict(obj)
    obj["artifact_sha256"] = canonical_sha(obj)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True))
    return obj["artifact_sha256"]


def phase_bind() -> None:
    mix = _load_mix()
    verify_imports(mix)
    frozen = verify_frozen_artifacts()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    h = _write_json(OUT_DIR / BINDING_NAME, {
        "binding_version": "item6_stage2_execution_binding_v1",
        "executor_version": EXECUTOR_VERSION,
        "design_head": DESIGN_HEAD,
        "executor_path": "src/research/item6/stage2/executor.py",
        "executor_sha256": file_sha(Path(__file__)),
        "frozen": frozen,
        "corpus": corpus_digest(mix.CORPUS),
        "executor_decisions": dict(EXECUTOR_DECISIONS),
        "targets": {"primary": list(PRIMARY_TARGET),
                    "secondary": [list(t) for t in SECONDARY_TARGETS]},
        "arms": {"primary": list(PRIMARY_ARMS), "secondary": list(SECONDARY_ARMS)},
        "outcomes_read_to_build_binding": False,
        "model_fits_before_binding": 0,
        "llm_calls": 0,
    })
    print(f"binding written sha256={h}")


def _gate(authorized_head: str):
    git = verify_git_state(authorized_head)
    mix = _load_mix()
    verify_imports(mix)
    frozen = verify_frozen_artifacts()
    binding = json.loads((OUT_DIR / BINDING_NAME).read_text())
    if canonical_sha(binding) != binding["artifact_sha256"]:
        raise GateError("binding hash mismatch")
    if binding["executor_sha256"] != file_sha(Path(__file__)):
        raise GateError("executor differs from the bound executor")
    if binding["frozen"] != frozen:
        raise GateError("frozen artifact hashes differ from the binding")
    if corpus_digest(mix.CORPUS) != binding["corpus"]:
        raise GateError("corpus differs from the bound corpus")
    return mix, git, frozen, binding


def _fit_job(job):
    (target, arm, fold, Xtr, ytr, Xte, cols) = job
    if not cols:
        return target, arm, fold, cols, {"status": "UNFIT_FEWER_THAN_3_M0_COLUMNS"}
    t0 = time.time()
    r = fit_arm(Xtr, ytr, Xte)
    r["seconds"] = round(time.time() - t0, 2)
    return target, arm, fold, cols, r


def phase_predict(authorized_head: str) -> None:
    from joblib import Parallel, delayed
    mix, git, frozen, binding = _gate(authorized_head)
    champion_before = frozen["champion_sha256"]
    t_start = time.time()
    spec = json.loads((STAGE2_DIR / "ITEM6_STAGE2_FEATURE_SPEC_V1.json").read_text())
    fm = json.loads((STAGE2_DIR / "ITEM6_STAGE2_FOLD_MANIFEST_V1.json").read_text())
    m1spec = json.loads((STAGE2_DIR / "ITEM6_STAGE2_AUGMENTED_MODEL_SPEC_V1.json").read_text())
    m0spec = json.loads((STAGE2_DIR / "ITEM6_STAGE2_BASELINE_MODEL_SPEC_V1.json").read_text())
    par = MS.parity_assertions(m0spec, m1spec)
    if not par["only_difference_is_llm_feature_availability"]:
        raise GateError(f"parity violated: {par}")
    llm_names = [str(c["name"]) for c in spec["columns"]]
    if llm_names != list(m1spec["llm_derived_feature_names"]) or len(llm_names) != 108:
        raise GateError("LLM column set differs from the frozen M1 spec")
    family_of = {str(c["name"]): str(c["structural_family"]) for c in spec["columns"]}
    if mix.feat_names("goals") != list(m0spec["feature_universe"]):
        raise GateError("goals M0 pool differs from the frozen M0 spec")

    ms = mix.load_corpus()
    key_of = lambda m: f"{m.get('home_name')}|{m.get('away_name')}|{int(m['date_unix'])}"  # noqa
    by_key: Dict[str, dict] = {}
    for m in ms:
        by_key.setdefault(key_of(m), m)
    hist = mix.build_histories(ms)
    targets = [PRIMARY_TARGET] + list(SECONDARY_TARGETS)
    usable = [f for f in fm["folds"] if not f["skipped"]]
    rows_by_fold = {f["fold_index"]: [r for r in fm["rows"] if r["fold"] == f["fold_index"]]
                    for f in usable}

    # M0 raw features: PIT, fold-independent.
    m0_cache: Dict[Tuple[str, str], List[Optional[float]]] = {}

    # Caches are keyed by object identity, not fixture_key: the corpus holds one duplicated
    # (home, away, kickoff) pair with distinct provider ids, and each row keeps its own label.
    def m0_row(m, market):
        k = (id(m), market)
        if k not in m0_cache:
            m0_cache[k] = mix.match_features(hist, m, market)
        return m0_cache[k]

    labels: Dict[Tuple[str, str], Optional[float]] = {}

    def label(m, market, line):
        k = (id(m), market)
        if k not in labels:
            labels[k] = mix.outcome(m, market, line)
        return labels[k]

    jobs = []
    fold_meta: Dict[int, Dict] = {}
    test_meta: Dict[Tuple[str, int], List[Dict]] = {}
    for f in usable:
        fi, te = f["fold_index"], f["train_end_unix"]
        train_all = sorted((m for m in ms if m["date_unix"] < te),
                           key=lambda m: (m["date_unix"], key_of(m)))
        if train_all and not max(m["date_unix"] for m in train_all) < te:
            raise GateError("training row at/after cutoff")
        # thresholds / standardisation: training-period matches only
        acc = {sk: [] for sk in spec["required_rolling_statistics"]}
        stats_cache = {}
        for m in train_all:
            s = FG.compute_required_stats(hist, m["home_name"], m["away_name"], m["date_unix"],
                                          spec["required_rolling_statistics"],
                                          season_key_fn=mix)
            stats_cache[id(m)] = s
            for sk, d in s.items():
                acc[sk] += [v for v in d.values() if v is not None]
            for c in spec["columns"]:
                if c["kind"] == FS.KIND_HALF_SHARE:
                    sk = f"{c['metric']}.{c['perspective']}.2H_SHARE.STD"
                    t = m["home_name"] if c["team_slot"] == "h" else m["away_name"]
                    sv = FG.second_half_share(hist, t, c["metric"], c["perspective"],
                                              m["date_unix"],
                                              season=mix.current_season_key(hist, t,
                                                                            m["date_unix"]),
                                              season_key_fn=mix._season_key)
                    if sv is not None:
                        acc.setdefault(sk, []).append(sv)
        ft = TP.fit(acc, fold_index=fi, train_end_unix=te)
        pairs = sorted({FG.banding_key(list(c["axis_stat_keys"])) for c in spec["columns"]
                        if c["kind"] == FS.KIND_PROFILE_DUMMY})
        prof = {k: [] for k in pairs}
        for m in train_all:
            s = stats_cache[id(m)]
            for k in pairs:
                aks = k.split("||")
                for slot in ("h", "a"):
                    prof[k].append([(ak, ft.bin_of(ak, s.get(ak, {}).get(slot)))
                                    for ak in aks])
        pb = {k: SP.fit(v, fold_index=fi) for k, v in prof.items()}

        def llm_row(m):
            g = FG.generate_features(hist=hist, home=m["home_name"], away=m["away_name"],
                                     before=m["date_unix"], spec=spec, fitted_thresholds=ft,
                                     profile_banding=pb, season_key_fn=mix)
            return [g["values"][n] for n in llm_names]

        llm_train = {id(m): llm_row(m) for m in train_all}
        test_ms = []
        for r in rows_by_fold[fi]:
            m = by_key[r["fixture_key"]]
            if not (f["test_start_unix"] <= m["date_unix"] < f["test_end_unix"]):
                raise GateError("test row outside its test block")
            test_ms.append((r, m))
        llm_test = {r["fixture_key"]: llm_row(m) for r, m in test_ms}
        fold_meta[fi] = {"train_end_unix": te, "n_threshold_fit_matches": len(train_all),
                         "n_statistics_with_edges": len(ft.edges),
                         "n_profile_bandings": len(pb)}

        for market, line in targets:
            tname = f"{market}_{line}"
            tr = [m for m in train_all if label(m, market, line) is not None]
            ytr = np.array([label(m, market, line) for m in tr], float)
            m0n = mix.feat_names(market)
            X0 = np.array([[np.nan if v is None else v for v in m0_row(m, market)] for m in tr],
                          float).reshape(len(tr), len(m0n))
            XL = np.array([[np.nan if v is None else v for v in llm_train[id(m)]]
                           for m in tr], float).reshape(len(tr), len(llm_names))
            k0 = [m0n[i] for i in coverage_keep(X0)]
            kl = [llm_names[i] for i in coverage_keep(XL)]
            te_rows = [(r, m) for r, m in test_ms if label(m, market, line) is not None]
            test_meta[(tname, fi)] = [
                {"fixture_key": r["fixture_key"], "kickoff_unix": r["kickoff_unix"],
                 "competition_id": r["competition_id"], "iso_week_block": r["iso_week_block"],
                 "fold": fi, "y": label(m, market, line)} for r, m in te_rows]
            T0 = np.array([[np.nan if v is None else v for v in m0_row(m, market)]
                           for _, m in te_rows], float).reshape(len(te_rows), len(m0n))
            TL = np.array([[np.nan if v is None else v for v in llm_test[r["fixture_key"]]]
                           for r, _ in te_rows], float).reshape(len(te_rows), len(llm_names))
            full_tr = {n: X0[:, i] for i, n in enumerate(m0n)}
            full_tr.update({n: XL[:, i] for i, n in enumerate(llm_names)})
            full_te = {n: T0[:, i] for i, n in enumerate(m0n)}
            full_te.update({n: TL[:, i] for i, n in enumerate(llm_names)})
            arms = PRIMARY_ARMS if (market, line) == PRIMARY_TARGET else SECONDARY_ARMS
            for arm in arms:
                cols = arm_columns(arm, k0, kl, family_of)
                if len(k0) < 3:
                    cols = []
                Xa = np.column_stack([full_tr[c] for c in cols]) if cols else \
                    np.zeros((len(tr), 0))
                Ta = np.column_stack([full_te[c] for c in cols]) if cols else \
                    np.zeros((len(te_rows), 0))
                jobs.append((tname, arm, fi, Xa, ytr, Ta, cols))
        print(f"[fold {fi}] features ready; jobs so far={len(jobs)} "
              f"elapsed={time.time()-t_start:.0f}s", flush=True)

    results = Parallel(n_jobs=N_OUTER_JOBS, verbose=5)(delayed(_fit_job)(j) for j in jobs)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pred_lines, fold_diag, featsel = [], [], {}
    for tname, arm, fi, cols, r in results:
        meta = test_meta[(tname, fi)]
        fsid = hashlib.sha256("\n".join(cols).encode()).hexdigest()
        n_llm = sum(1 for c in cols if c in family_of)
        diag = {"target": tname, "arm": arm, "fold": fi, "status": r["status"],
                "n_columns": len(cols), "n_llm_columns": n_llm, "feature_set_sha256": fsid,
                "n_test": len(meta)}
        if r["status"] == "FIT":
            nz = [c for c, b in zip(cols, r["coef"]) if abs(b) > NONZERO_COEF]
            diag.update({k: r[k] for k in ("selected_C", "selected_l1_ratio",
                                           "cv_best_mean_neg_log_loss",
                                           "n_convergence_warnings", "n_calibration_pairs",
                                           "n_train", "n_clipped_low", "n_clipped_high",
                                           "seconds")})
            diag["C_at_min_grid_edge"] = r["selected_C"] == min(MS.C_GRID)
            diag["C_at_max_grid_edge"] = r["selected_C"] == max(MS.C_GRID)
            diag["n_nonzero"] = len(nz)
            diag["n_llm_nonzero"] = sum(1 for c in nz if c in family_of)
            featsel[f"{tname}|{arm}|{fi}"] = {
                "columns": cols,
                "coef": {c: round(float(b), 8) for c, b in zip(cols, r["coef"])},
                "nonzero": nz}
            for i, mrow in enumerate(meta):
                pred_lines.append({**mrow, "target": tname, "arm": arm,
                                   "p_raw": float(r["raw"][i]),
                                   "p_calibrated": float(r["calibrated"][i]),
                                   "p_final": float(r["final"][i]),
                                   "selected_C": r["selected_C"],
                                   "selected_l1_ratio": r["selected_l1_ratio"],
                                   "feature_set_sha256": fsid})
        else:
            diag["error"] = r.get("error")
        fold_diag.append(diag)
    pred_lines.sort(key=lambda d: (d["target"], d["arm"], d["fold"], d["kickoff_unix"],
                                   d["fixture_key"]))
    fold_diag.sort(key=lambda d: (d["target"], d["arm"], d["fold"]))
    pred_path = OUT_DIR / PREDICTIONS_NAME
    pred_path.write_text("".join(json.dumps(d, sort_keys=True) + "\n" for d in pred_lines))
    fd_sha = _write_json(OUT_DIR / FOLD_DIAG_NAME, {
        "executor_version": EXECUTOR_VERSION, "fold_meta": {str(k): v for k, v in
                                                            fold_meta.items()},
        "fits": fold_diag})
    fs_sha = _write_json(OUT_DIR / FEATSEL_NAME, {
        "executor_version": EXECUTOR_VERSION, "nonzero_threshold": NONZERO_COEF,
        "family_of_llm_column": family_of, "by_target_arm_fold": featsel})
    champion_after = champion_sha()
    ev_sha = _write_json(OUT_DIR / EVIDENCE_NAME, {
        "phase": "PREDICT_FROZEN_BEFORE_EVALUATION",
        "executor_version": EXECUTOR_VERSION,
        "authorized_execution_head": authorized_head, "git": git,
        "binding_sha256": binding["artifact_sha256"],
        "frozen": frozen,
        "predictions": {"path": PREDICTIONS_NAME, "file_sha256": file_sha(pred_path),
                        "n_rows": len(pred_lines)},
        "fold_diagnostics_sha256": fd_sha, "feature_selection_diagnostics_sha256": fs_sha,
        "n_fit_jobs": len(jobs),
        "champion_before": champion_before, "champion_after": champion_after,
        "champion_unchanged": champion_before == champion_after,
        "llm_calls": 0, "metrics_computed": False,
        "wall_seconds": round(time.time() - t_start, 1),
    })
    print(f"predictions frozen rows={len(pred_lines)} evidence={ev_sha}")


def phase_evaluate(authorized_head: str) -> None:
    git = verify_git_state(authorized_head, since=DESIGN_HEAD)
    ev = json.loads((OUT_DIR / EVIDENCE_NAME).read_text())
    subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor",
                    ev["authorized_execution_head"], git["head"]], check=True)
    if canonical_sha(ev) != ev["artifact_sha256"]:
        raise GateError("evidence manifest hash mismatch")
    if ev.get("phase") not in ("PREDICT_FROZEN_BEFORE_EVALUATION",):
        raise GateError("evidence manifest is not the frozen predict-phase manifest")
    pred_path = OUT_DIR / PREDICTIONS_NAME
    if file_sha(pred_path) != ev["predictions"]["file_sha256"]:
        raise GateError("predictions differ from the frozen predictions")
    fdiag = json.loads((OUT_DIR / FOLD_DIAG_NAME).read_text())
    fsel = json.loads((OUT_DIR / FEATSEL_NAME).read_text())
    rows: Dict[Tuple[str, str], Dict[str, Dict]] = {}
    for ln in pred_path.read_text().splitlines():
        d = json.loads(ln)
        rows.setdefault((d["target"], d["arm"]), {})[d["fixture_key"]] = d
    prim = f"{PRIMARY_TARGET[0]}_{PRIMARY_TARGET[1]}"

    main = compare(rows[(prim, "M0")], rows[(prim, "M1_ALL")])
    if main["n_dropped_from_a"] or main["n_dropped_from_b"]:
        pass  # reported; the intersection rule is the frozen scored set
    gate = decision(main)
    # feature-selection stability for M1_ALL on the primary target
    fits = [d for d in fdiag["fits"] if d["target"] == prim and d["arm"] == "M1_ALL"
            and d["status"] == "FIT"]
    fam = fsel["family_of_llm_column"]
    ever, per_fold, stab = set(), {}, {}
    for d in fits:
        nz = fsel["by_target_arm_fold"][f"{prim}|M1_ALL|{d['fold']}"]["nonzero"]
        per_fold[d["fold"]] = sum(1 for c in nz if c in fam)
        ever |= {c for c in nz if c in fam}
        for c in fsel["by_target_arm_fold"][f"{prim}|M1_ALL|{d['fold']}"]["columns"]:
            stab.setdefault(c, 0)
            if c in nz:
                stab[c] += 1
    stability = {c: n / max(1, len(fits)) for c, n in sorted(stab.items())}

    def hp(target, arm):
        return {d["fold"]: {"C": d.get("selected_C"), "l1_ratio": d.get("selected_l1_ratio"),
                            "C_min_edge": d.get("C_at_min_grid_edge"),
                            "C_max_edge": d.get("C_at_max_grid_edge"), "status": d["status"],
                            "n_convergence_warnings": d.get("n_convergence_warnings"),
                            "n_llm_nonzero": d.get("n_llm_nonzero"),
                            "n_columns": d["n_columns"]}
                for d in fdiag["fits"] if d["target"] == target and d["arm"] == arm}

    clip = {}
    for arm in ("M0", "M1_ALL"):
        ff = [d for d in fdiag["fits"] if d["target"] == prim and d["arm"] == arm
              and d["status"] == "FIT"]
        clip[arm] = {"n_clipped_to_0_01": sum(d["n_clipped_low"] for d in ff),
                     "n_clipped_to_0_99": sum(d["n_clipped_high"] for d in ff)}
    primary = {
        "executor_version": EXECUTOR_VERSION, "target": prim,
        "primary_metric": EV.PRIMARY_METRIC, "sign_convention": EV.PRIMARY_SIGN_CONVENTION,
        "comparison": "M0_vs_M1_ALL", "result": main, "decision": gate,
        "decision_rule": EV.decision_rule(),
        "precision_reading": precision_reading(main, gate["ITEM6_STAGE2_PRIMARY_GATE"]),
        "hyperparameters": {"M0": hp(prim, "M0"), "M1_ALL": hp(prim, "M1_ALL")},
        "n_llm_features_nonzero_by_fold": per_fold,
        "n_llm_features_ever_nonzero": len(ever),
        "llm_features_ever_nonzero": sorted(ever),
        "clipping": clip,
        "predictions_file_sha256": ev["predictions"]["file_sha256"],
        "evidence_manifest_sha256": ev["artifact_sha256"],
    }
    abl = {}
    for arm in ABLATION_FAMILY:
        c = compare(rows[(prim, "M0")], rows[(prim, arm)])
        abl[arm] = {"family": ABLATION_FAMILY[arm], "n_llm_columns_by_fold": {
            d["fold"]: d["n_llm_columns"] for d in fdiag["fits"]
            if d["target"] == prim and d["arm"] == arm},
            "delta": c["delta_logloss_a_minus_b"],
            "ci": [c["bootstrap"]["ci_lower"], c["bootstrap"]["ci_upper"]],
            "raw_p": c["bootstrap"]["one_sided_p_delta_le_0"], "n_paired": c["n_paired"],
            "ece_m0": c["ece_a"], "ece_arm": c["ece_b"]}
    qs = bh_adjust([abl[a]["raw_p"] for a in ABLATION_FAMILY])
    for a, q in zip(ABLATION_FAMILY, qs):
        abl[a]["bh_q"] = q
        abl[a]["pass_secondary_fdr"] = bool(q <= EV.FAMILY_LEVEL_FDR_Q)
    sec = {}
    for market, line in SECONDARY_TARGETS:
        t = f"{market}_{line}"
        c = compare(rows[(t, "M0")], rows[(t, "M1_ALL")])
        sec[t] = {"m0_logloss": c["logloss_a"], "m1_logloss": c["logloss_b"],
                  "delta": c["delta_logloss_a_minus_b"],
                  "ci": [c["bootstrap"]["ci_lower"], c["bootstrap"]["ci_upper"]],
                  "raw_p": c["bootstrap"]["one_sided_p_delta_le_0"], "n_paired": c["n_paired"],
                  "ece_m0": c["ece_a"], "ece_m1": c["ece_b"],
                  "brier_delta": c["brier_delta_a_minus_b"],
                  "hyperparameters": {"M0": hp(t, "M0"), "M1_ALL": hp(t, "M1_ALL")}}
    qs = bh_adjust([sec[t]["raw_p"] for t in sec])
    for t, q in zip(sec, qs):
        sec[t]["bh_q"] = q
        sec[t]["pass_secondary_fdr"] = bool(q <= EV.FAMILY_LEVEL_FDR_Q)
    p_sha = _write_json(OUT_DIR / PRIMARY_NAME, primary)
    s_sha = _write_json(OUT_DIR / SECONDARY_NAME, {
        "executor_version": EXECUTOR_VERSION, "secondary_only": True,
        "does_not_affect_primary_gate": True,
        "primary_target_secondary_metrics": {
            "brier_m0": main["brier_a"], "brier_m1": main["brier_b"],
            "brier_delta": main["brier_delta_a_minus_b"],
            "residual_deviance_delta": main["residual_deviance_delta"],
            "llm_feature_selection_stability": stability},
        "family_ablations": abl, "family_level_method": EV.FAMILY_LEVEL_MULTIPLICITY_METHOD,
        "secondary_targets": sec, "secondary_target_method": EV.SECONDARY_TARGET_ADJUSTMENT,
        "fdr_q": EV.FAMILY_LEVEL_FDR_Q})
    print(json.dumps({"gate": gate, "primary_sha256": p_sha, "secondary_sha256": s_sha,
                      "evaluate_head": git["head"]}, indent=1))


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=("bind", "predict", "evaluate"))
    ap.add_argument("--authorized-head")
    a = ap.parse_args(argv)
    if a.phase == "bind":
        phase_bind()
        return
    if not a.authorized_head:
        raise GateError("--authorized-head is required for predict/evaluate")
    (phase_predict if a.phase == "predict" else phase_evaluate)(a.authorized_head)


if __name__ == "__main__":
    main()
