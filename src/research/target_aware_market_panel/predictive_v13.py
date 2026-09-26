"""V1.3 exploratory nested stability selection over frozen Sol feature matrices.

No network or provider access. Selection is fit inside each outer training fold only.
"""
from __future__ import annotations
import warnings
from typing import Any, Dict, List, Sequence

import numpy as np

from src.research.item6.stage2 import model_specs as MS
from src.research.item6.stage2.executor import make_pipeline

STABILITY_SPLITS = 3
MIN_STABILITY_VOTES = 2
NONZERO_COEF = 1e-8
MIN_SUCCESSFUL_SUBFITS = 2
OUTER_COVERAGE = 0.60

def coverage_keep(X: np.ndarray, min_rate: float = OUTER_COVERAGE) -> List[int]:
    if X.shape[0] == 0:
        return []
    rate = np.mean(~np.isnan(X), axis=0)
    return [int(i) for i in np.where(rate >= min_rate)[0]]

def fit_selection_model(Xtr: np.ndarray, ytr: np.ndarray) -> Dict[str, Any]:
    """Fit only the penalized model needed for coefficient support/sign.

    Uses the same pipeline/grid/chronological tuning rule as the frozen fitter.
    Calibration is deliberately omitted because it cannot affect coefficient selection.
    """
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.model_selection import GridSearchCV, TimeSeriesSplit

    if len(set(np.asarray(ytr).tolist())) < 2:
        return {"status": "UNFIT_SINGLE_CLASS"}
    cv = TimeSeriesSplit(n_splits=MS.INNER_CV_SPLITS)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        try:
            search = GridSearchCV(
                make_pipeline(),
                {"model__C": list(MS.C_GRID), "model__l1_ratio": list(MS.L1_RATIO_GRID)},
                cv=cv, scoring="neg_log_loss", refit=True, n_jobs=1, error_score="raise")
            search.fit(Xtr, ytr)
        except Exception as exc:
            return {"status": "UNFIT_EXCEPTION", "error": f"{type(exc).__name__}: {exc}"}
    imp = search.best_estimator_.named_steps["imputer"]
    kept_mask = ~np.isnan(imp.statistics_)
    coef = np.zeros(Xtr.shape[1], dtype=float)
    coef[kept_mask] = search.best_estimator_.named_steps["model"].coef_[0]
    return {
        "status": "FIT",
        "coef": coef,
        "selected_C": float(search.best_params_["model__C"]),
        "selected_l1_ratio": float(search.best_params_["model__l1_ratio"]),
        "cv_best_mean_neg_log_loss": float(search.best_score_),
        "n_convergence_warnings": int(sum(
            1 for w in caught if issubclass(w.category, ConvergenceWarning))),
    }

def stable_llm_selection(
    X0tr: np.ndarray,
    XLtr: np.ndarray,
    ytr: np.ndarray,
    m0_indices: Sequence[int],
    llm_indices: Sequence[int],
) -> Dict[str, Any]:
    """Return LLM indices stable across expanding chronological training subfits."""
    from sklearn.model_selection import TimeSeriesSplit

    k0 = list(map(int, m0_indices))
    kl = list(map(int, llm_indices))
    if not kl:
        return {
            "status": "NO_ELIGIBLE_LLM",
            "successful_subfits": 0,
            "selected_llm_indices": [],
            "vote_counts": {},
            "signs": {},
            "subfits": [],
        }
    A = np.column_stack([X0tr[:, k0], XLtr[:, kl]])
    splitter = TimeSeriesSplit(n_splits=STABILITY_SPLITS)
    votes = np.zeros(len(kl), dtype=int)
    signs: List[List[int]] = [[] for _ in kl]
    subfits = []
    successful = 0
    for split_id, (itr, _iva) in enumerate(splitter.split(A)):
        r = fit_selection_model(A[itr], np.asarray(ytr)[itr])
        rec = {"split": int(split_id), "n_train": int(len(itr)), "status": r["status"]}
        if r["status"] == "FIT":
            successful += 1
            coef = np.asarray(r["coef"], float)[len(k0):]
            nz = np.abs(coef) > NONZERO_COEF
            for j in np.where(nz)[0]:
                votes[j] += 1
                signs[j].append(1 if coef[j] > 0 else -1)
            rec.update({
                "selected_C": r["selected_C"],
                "selected_l1_ratio": r["selected_l1_ratio"],
                "cv_best_mean_neg_log_loss": r["cv_best_mean_neg_log_loss"],
                "n_llm_nonzero": int(nz.sum()),
                "n_convergence_warnings": r["n_convergence_warnings"],
            })
        else:
            rec["error"] = r.get("error")
        subfits.append(rec)

    if successful < MIN_SUCCESSFUL_SUBFITS:
        selected_local: List[int] = []
        status = "INSUFFICIENT_SUCCESSFUL_SUBFITS"
    else:
        selected_local = []
        for j in range(len(kl)):
            same_sign = len(set(signs[j])) <= 1 and bool(signs[j])
            if votes[j] >= MIN_STABILITY_VOTES and same_sign:
                selected_local.append(j)
        status = "SELECTED" if selected_local else "ZERO_STABLE_LLM"

    return {
        "status": status,
        "successful_subfits": int(successful),
        "selected_llm_indices": [kl[j] for j in selected_local],
        "vote_counts": {str(kl[j]): int(votes[j]) for j in range(len(kl))},
        "signs": {str(kl[j]): signs[j] for j in range(len(kl)) if signs[j]},
        "subfits": subfits,
    }

def version_stamp() -> Dict[str, Any]:
    return {
        "artifact_version": "target_aware_predictive_v1_3_nested_stability_v1",
        "stability_splits": STABILITY_SPLITS,
        "min_stability_votes": MIN_STABILITY_VOTES,
        "nonzero_coef": NONZERO_COEF,
        "min_successful_subfits": MIN_SUCCESSFUL_SUBFITS,
        "outer_coverage": OUTER_COVERAGE,
        "network_calls": 0,
    }
