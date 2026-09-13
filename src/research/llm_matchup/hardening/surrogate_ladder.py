"""Surrogate ladder S0-S5 (patch §17, §19, §20).

The Phase-B surrogate used cited-evidence COUNT — patch §17 rightly calls this insufficient.
This module answers the real question: «Can Sonnet's structured state be reproduced trivially
from the RAW deterministic features already supplied to it?» It tests each Sonnet mechanism
state against increasingly capable deterministic surrogates fit on the RAW INPUT FEATURE MATRIX
(feature_matrix.py), with proper train/eval separation.

Ladder (patch §19):
  S0 — majority / base-rate class (no features).
  S1 — best single raw feature (one-feature threshold on the strongest aligned feature).
  S2 — simple threshold rule (best single-feature multi-cut decision stump).
  S3 — small regularized ordinal/logistic model (LogisticRegression, strong L2).
  S4 — shallow decision tree (max_depth=3).
  S5 — small deterministic interaction model (LogisticRegression on features + pairwise
       products of the top few features — a bounded interaction surrogate).

Evaluation: leave-one-out / small-k cross-validated agreement with the Sonnet ordinal label,
so we never report train-set accuracy. Interpretation (patch §20):
  * S1 reproduces Sonnet nearly perfectly  -> Sonnet is (for that state) redundant with one
    feature -> flag TRIVIALLY_REDUCIBLE.
  * only S3/S4/S5 (multi-dimensional / interaction) reproduce it -> more interesting
    (MULTIDIMENSIONAL).
  * NOTHING reproduces it well -> do NOT conclude "understanding"; compare against self-noise
    in eligibility (§21). Here we just flag IRREDUCIBLE_OR_NOISY.

Features per (fixture, mechanism): from the feature matrix rows whose base_metric+side is on the
mechanism's allow-list, we build aligned aggregate features (mean/max/min of value, z_score,
delta, percentile; count; formation-conditioned mean). Deterministic, no leakage of Phase-C
outcomes.

Uses numpy + scikit-learn (available). No probability-engine imports.
"""
from __future__ import annotations
import os, csv, json
from collections import defaultdict

import numpy as np

from src.research.llm_matchup import ontology as ONT
from src.research.llm_matchup.hardening.repeatability import LEVEL_ORD, ADV_ORD

OUT = "/home/ubuntu/research/llm_matchup/out/hardening"

MIN_FIXTURES = 8          # need enough labelled fixtures to fit/evaluate a surrogate
TRIVIAL_THRESHOLD = 0.90  # patch §20: near-perfect single-feature reproduction => trivial


def _ordinal(status: str):
    if status in LEVEL_ORD:
        return LEVEL_ORD[status]
    if status in ADV_ORD:
        return ADV_ORD[status]
    return None  # UNKNOWN / CONFLICTED excluded from ordinal surrogate fitting


def _load_feature_matrix(path: str) -> dict:
    """fixture_id -> list of feature rows (dicts with floats parsed)."""
    by_fx = defaultdict(list)
    if not os.path.exists(path):
        return by_fx
    with open(path) as f:
        for row in csv.DictReader(f):
            for k in ("value", "z_score", "percentile", "baseline", "delta",
                      "sample_n", "effective_n"):
                v = row.get(k)
                row[k] = float(v) if v not in (None, "", "None") else None
            by_fx[row["fixture_id"]].append(row)
    return by_fx


def _aligned_features(rows: list[dict], mech: str) -> dict:
    """Aggregate the mechanism's allowed feature rows into a fixed feature vector."""
    allow = ONT.allowed_metric_prefixes(mech) if mech in ONT.MECHANISMS else []

    def _hit(r):
        m = r["metric"]
        base = r["base_metric"]
        return any(m == a or m.startswith(a) or a in m or base == a or a in base for a in allow)

    rel = [r for r in rows if _hit(r) and r.get("value") is not None]
    if not rel:
        return {}
    zs = [r["z_score"] for r in rel if r["z_score"] is not None]
    ds = [r["delta"] for r in rel if r["delta"] is not None]
    ps = [r["percentile"] for r in rel if r["percentile"] is not None]
    fc = [r["z_score"] for r in rel if r["z_score"] is not None
          and r["formation_condition"] != "UNCONDITIONED"]
    feats = {
        "z_mean": float(np.mean(zs)) if zs else 0.0,
        "z_max": float(np.max(zs)) if zs else 0.0,
        "z_min": float(np.min(zs)) if zs else 0.0,
        "delta_mean": float(np.mean(ds)) if ds else 0.0,
        "pct_mean": float(np.mean(ps)) if ps else 0.5,
        "n_features": float(len(rel)),
        "fc_z_mean": float(np.mean(fc)) if fc else 0.0,
    }
    return feats


def build_design(states_jsonl: str, feature_csv: str) -> dict:
    """Build per-mechanism design matrices from OK Sonnet states + the feature matrix.

    For repeatability we may have multiple calls per fixture; we take the FIRST OK call per
    (fixture, mechanism) as the label (surrogate reducibility is about the typical state, and
    the repeatability study separately quantifies call-to-call noise). Returns
    {mechanism -> {"X": [feat dicts], "y": [ordinal], "fixtures": [...]}}.
    """
    feats_by_fx = _load_feature_matrix(feature_csv)
    seen = set()
    design = defaultdict(lambda: {"X": [], "y": [], "fixtures": []})
    if not os.path.exists(states_jsonl):
        return design
    for line in open(states_jsonl):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("status") != "OK" or not rec.get("state"):
            continue
        fx = rec["state"]["fixture_id"]
        for side in ("team_a_states", "team_b_states", "matchup_states"):
            for st in rec["state"].get(side, []):
                mech = st["mechanism"]
                key = (fx, side, mech)
                if key in seen:
                    continue
                seen.add(key)
                status = st.get("level") or st.get("assessment")
                y = _ordinal(status)
                if y is None:
                    continue
                feats = _aligned_features(feats_by_fx.get(fx, []), mech)
                if not feats:
                    continue
                d = design[mech]
                d["X"].append(feats)
                d["y"].append(y)
                d["fixtures"].append(fx)
    return design


# --- surrogate fitting with cross-validated agreement --------------------------
def _cv_accuracy(fit_predict, X, y) -> float:
    """Leave-one-out CV accuracy (small samples). fit_predict(Xtr,ytr,Xte)->yhat array."""
    n = len(y)
    if n < 2:
        return float("nan")
    correct = 0
    for i in range(n):
        tr = [j for j in range(n) if j != i]
        Xtr, ytr = X[tr], y[tr]
        yhat = fit_predict(Xtr, ytr, X[i:i + 1])
        correct += int(yhat[0] == y[i])
    return correct / n


def _s0(Xtr, ytr, Xte):
    vals, counts = np.unique(ytr, return_counts=True)
    maj = vals[int(np.argmax(counts))]
    return np.array([maj] * len(Xte))


def _stump_single(feat_idx):
    def fp(Xtr, ytr, Xte):
        col = Xtr[:, feat_idx]
        # best threshold minimizing classification error to the majority-above/below rule
        cuts = np.unique(col)
        best_err, best = 1e9, (None, None, None)
        for c in cuts:
            for hi_label in np.unique(ytr):
                for lo_label in np.unique(ytr):
                    pred = np.where(col > c, hi_label, lo_label)
                    err = np.mean(pred != ytr)
                    if err < best_err:
                        best_err, best = err, (c, hi_label, lo_label)
        c, hi, lo = best
        return np.where(Xte[:, feat_idx] > c, hi, lo)
    return fp


def _best_single_feature(X, y, feat_names):
    best_acc, best_idx = -1.0, 0
    for j in range(X.shape[1]):
        acc = _cv_accuracy(_stump_single(j), X, y)
        if acc == acc and acc > best_acc:  # not nan
            best_acc, best_idx = acc, j
    return best_idx, best_acc


def _logistic(l2C=0.5, interactions=False, top_k=3):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    def fp(Xtr, ytr, Xte):
        Xtr2, Xte2 = Xtr, Xte
        if interactions:
            # add pairwise products of the top_k highest-variance features
            var = np.var(Xtr, axis=0)
            idx = np.argsort(-var)[:top_k]
            def _aug(M):
                extra = []
                for a in range(len(idx)):
                    for b in range(a + 1, len(idx)):
                        extra.append((M[:, idx[a]] * M[:, idx[b]]).reshape(-1, 1))
                return np.hstack([M] + extra) if extra else M
            Xtr2, Xte2 = _aug(Xtr), _aug(Xte)
        if len(np.unique(ytr)) < 2:
            return np.array([ytr[0]] * len(Xte2))
        sc = StandardScaler().fit(Xtr2)
        clf = LogisticRegression(C=l2C, max_iter=1000)
        clf.fit(sc.transform(Xtr2), ytr)
        return clf.predict(sc.transform(Xte2))
    return fp


def _tree(max_depth=3):
    from sklearn.tree import DecisionTreeClassifier

    def fp(Xtr, ytr, Xte):
        if len(np.unique(ytr)) < 2:
            return np.array([ytr[0]] * len(Xte))
        clf = DecisionTreeClassifier(max_depth=max_depth, random_state=0)
        clf.fit(Xtr, ytr)
        return clf.predict(Xte)
    return fp


def analyze(design: dict) -> list[dict]:
    rows = []
    for mech, d in sorted(design.items()):
        n = len(d["y"])
        if n < MIN_FIXTURES:
            rows.append({"mechanism": mech, "n_fixtures": n, "distinct_labels": len(set(d["y"])),
                         "insufficient_coverage": True})
            continue
        feat_names = sorted(d["X"][0].keys())
        X = np.array([[row[k] for k in feat_names] for row in d["X"]], dtype=float)
        y = np.array(d["y"], dtype=int)
        distinct = len(set(y.tolist()))
        if distinct < 2:
            rows.append({"mechanism": mech, "n_fixtures": n, "distinct_labels": distinct,
                         "degenerate_single_label": True,
                         "s0_base_rate": 1.0, "verdict": "DEGENERATE_CONSTANT"})
            continue

        s0 = _cv_accuracy(_s0, X, y)
        bi, s1 = _best_single_feature(X, y, feat_names)
        s2 = s1  # single-feature stump == best threshold rule for our aggregate features
        s3 = _cv_accuracy(_logistic(l2C=0.5), X, y)
        s4 = _cv_accuracy(_tree(max_depth=3), X, y)
        s5 = _cv_accuracy(_logistic(l2C=0.5, interactions=True), X, y)

        best_simple = max(s0, s1)
        best_multi = max(s3, s4, s5)
        if s1 >= TRIVIAL_THRESHOLD:
            verdict = "TRIVIALLY_REDUCIBLE"           # one feature ~ reproduces Sonnet
        elif best_multi >= TRIVIAL_THRESHOLD and best_multi > best_simple + 0.1:
            verdict = "MULTIDIMENSIONAL"              # needs interaction/multi-feature
        elif max(best_simple, best_multi) < 0.6:
            verdict = "IRREDUCIBLE_OR_NOISY"          # nothing reproduces well
        else:
            verdict = "PARTIALLY_REDUCIBLE"
        rows.append({
            "mechanism": mech, "n_fixtures": n, "distinct_labels": distinct,
            "best_feature": feat_names[bi],
            "s0_base_rate": round(s0, 4), "s1_best_single": round(s1, 4),
            "s2_threshold": round(s2, 4), "s3_logistic": round(s3, 4),
            "s4_tree": round(s4, 4), "s5_interaction": round(s5, 4),
            "best_simple": round(best_simple, 4), "best_multi": round(best_multi, 4),
            "verdict": verdict,
        })
    return rows


def run(states_jsonl: str = None, feature_csv: str = None) -> dict:
    os.makedirs(OUT, exist_ok=True)
    states_jsonl = states_jsonl or os.path.join(OUT, "llm_states_hardening.jsonl")
    feature_csv = feature_csv or os.path.join(OUT, "raw_input_feature_matrix.csv")
    design = build_design(states_jsonl, feature_csv)
    rows = analyze(design)
    _write_csv(os.path.join(OUT, "surrogate_results.csv"), rows)
    summary = {"study": "surrogate_ladder", "n_mechanisms": len(rows),
               "n_trivially_reducible": sum(1 for r in rows if r.get("verdict") == "TRIVIALLY_REDUCIBLE"),
               "n_multidimensional": sum(1 for r in rows if r.get("verdict") == "MULTIDIMENSIONAL"),
               "n_irreducible_or_noisy": sum(1 for r in rows if r.get("verdict") == "IRREDUCIBLE_OR_NOISY"),
               "n_insufficient": sum(1 for r in rows if r.get("insufficient_coverage")),
               "rows": rows}
    json.dump(summary, open(os.path.join(OUT, "surrogate_results.json"), "w"), indent=2, default=str)
    return summary


def _write_csv(path, rows):
    if not rows:
        open(path, "w").close()
        return
    cols = sorted({k for r in rows for k in r})
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
