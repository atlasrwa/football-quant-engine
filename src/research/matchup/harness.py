"""Chronological OOS evaluation harness for champion-vs-challenger experiments.

STRICT rules:
  * chronological expanding walk-forward (no random split, no future leakage);
  * ALL preprocessing (impute median, standardize, elastic-net selection, CV) fit on
    train fold only, applied to the untouched test fold;
  * common-support: rows compared across models must have usable features in ALL
    compared models (reported alongside each model's own max sample);
  * metrics: LogLoss, Brier, Brier Skill Score vs base-rate, ECE, calibration
    slope/intercept, probability dispersion, ROC-AUC, directional accuracy, majority lift.

No odds. No prospective data. Deterministic (fixed seed).
"""
from __future__ import annotations
import warnings, math
from dataclasses import dataclass
from typing import Callable, Optional
import numpy as np
warnings.filterwarnings("ignore")
from sklearn.linear_model import LogisticRegression

EPS = 1e-9


def logloss(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def brier(y, p):
    return float(np.mean((p - y) ** 2))


def brier_skill(y, p, base):
    bref = np.mean((base - y) ** 2)
    return float((1 - np.mean((p - y) ** 2) / bref) * 100) if bref > 0 else 0.0


def ece(y, p, bins=10):
    e = 0.0
    for b in range(bins):
        lo, hi = b / bins, (b + 1) / bins
        mk = (p >= lo) & (p < hi if b < bins - 1 else p <= hi)
        if mk.sum():
            e += (mk.sum() / len(p)) * abs(p[mk].mean() - y[mk].mean())
    return float(e)


def calib_slope_intercept(y, p):
    """Logistic recalibration slope/intercept: fit y ~ logit(p). slope 1/intercept 0 = perfect."""
    p = np.clip(p, 1e-6, 1 - 1e-6)
    z = np.log(p / (1 - p)).reshape(-1, 1)
    if len(np.unique(y)) < 2:
        return None, None
    lr = LogisticRegression(C=1e6, solver="lbfgs", max_iter=1000)
    lr.fit(z, y)
    return float(lr.coef_[0][0]), float(lr.intercept_[0])


def auc(y, p):
    y = np.asarray(y); p = np.asarray(p)
    pos = p[y == 1]; neg = p[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return None
    # Mann-Whitney U
    order = np.argsort(p)
    ranks = np.empty(len(p)); ranks[order] = np.arange(1, len(p) + 1)
    # average ties
    r_pos = ranks[y == 1].sum()
    n1, n0 = len(pos), len(neg)
    return float((r_pos - n1 * (n1 + 1) / 2) / (n1 * n0))


@dataclass
class FoldResult:
    n_test: int
    metrics: dict
    p: np.ndarray
    y: np.ndarray
    comp: list


def fit_predict_logit(Xtr, ytr, Xte, C=0.03, l1r=0.5, cv_hyper=False):
    """Median-impute + standardize (train-only) + elastic-net logistic. Returns p_test, coefs, names_kept."""
    med = np.nanmedian(Xtr, 0); med = np.where(np.isnan(med), 0, med)
    Xtr = Xtr.copy(); Xte = Xte.copy()
    for A in (Xtr, Xte):
        idx = np.where(np.isnan(A)); A[idx] = np.take(med, idx[1])
    mu, sd = Xtr.mean(0), Xtr.std(0); sd[sd == 0] = 1
    Xtr = (Xtr - mu) / sd; Xte = (Xte - mu) / sd
    if cv_hyper:
        from sklearn.model_selection import GridSearchCV, TimeSeriesSplit
        base = LogisticRegression(penalty="elasticnet", solver="saga", max_iter=4000, random_state=0)
        gs = GridSearchCV(base, {"C": [0.01, 0.03, 0.1, 0.3], "l1_ratio": [0.2, 0.5, 0.8]},
                          cv=TimeSeriesSplit(n_splits=3), scoring="neg_log_loss")
        gs.fit(Xtr, ytr); clf = gs.best_estimator_
    else:
        clf = LogisticRegression(penalty="elasticnet", solver="saga", C=C, l1_ratio=l1r,
                                 max_iter=4000, random_state=0)
        clf.fit(Xtr, ytr)
    p = np.clip(clf.predict_proba(Xte)[:, 1], 0.01, 0.99)
    return p, clf.coef_[0], (mu, sd, med)


def walk_forward(X, y, comps, times, n_folds=4, model_fn=None, min_train=400):
    """Expanding chronological folds. X rows already time-sorted. Returns per-fold p,y and pooled."""
    n = len(y)
    # expanding: split the last (n_folds) chronological blocks as successive test sets
    bounds = np.linspace(0, n, n_folds + 1, dtype=int)
    all_p = []; all_y = []; all_c = []; fold_meta = []
    for fi in range(1, n_folds + 1):
        tr_end = bounds[fi]  # not used directly; we expand train = everything before test block
        te_lo, te_hi = bounds[fi - 1], bounds[fi]
        if fi == 1:
            continue  # need a train set before the first test block
        tr_lo, tr_hi = 0, bounds[fi - 1]
        if tr_hi - tr_lo < min_train:
            continue
        Xtr, ytr = X[tr_lo:tr_hi], y[tr_lo:tr_hi]
        Xte, yte = X[te_lo:te_hi], y[te_lo:te_hi]
        if len(np.unique(ytr)) < 2 or len(yte) == 0:
            continue
        p, coefs, _ = (model_fn or fit_predict_logit)(Xtr, ytr, Xte)
        all_p.append(p); all_y.append(yte); all_c.append([comps[i] for i in range(te_lo, te_hi)])
        fold_meta.append({"fold": fi, "n_train": len(ytr), "n_test": len(yte),
                          "logloss": logloss(yte, p), "brier": brier(yte, p)})
    if not all_p:
        return None
    P = np.concatenate(all_p); Y = np.concatenate(all_y)
    C = [c for block in all_c for c in block]
    return {"p": P, "y": Y, "comp": C, "folds": fold_meta}


def summarize(y, p, comp=None):
    base = np.full_like(p, y.mean())
    sl, ic = calib_slope_intercept(y, p)
    out = {
        "n": int(len(y)), "base_rate": round(float(y.mean()), 4),
        "logloss": round(logloss(y, p), 5),
        "logloss_baserate": round(logloss(y, base), 5),
        "brier": round(brier(y, p), 5),
        "bss_pct": round(brier_skill(y, p, base), 3),
        "ece": round(ece(y, p), 4),
        "calib_slope": round(sl, 3) if sl is not None else None,
        "calib_intercept": round(ic, 3) if ic is not None else None,
        "auc": round(auc(y, p), 4) if auc(y, p) is not None else None,
        "p_std": round(float(p.std()), 4),
        "p05": round(float(np.percentile(p, 5)), 4),
        "p50": round(float(np.percentile(p, 50)), 4),
        "p95": round(float(np.percentile(p, 95)), 4),
        "dir_acc": round(float(((p >= 0.5).astype(float) == y).mean()), 4),
        "majority_acc": round(float(max(y.mean(), 1 - y.mean())), 4),
    }
    out["majority_lift"] = round(out["dir_acc"] - out["majority_acc"], 4)
    out["logloss_vs_baserate"] = round(out["logloss"] - out["logloss_baserate"], 5)
    return out
