"""Outcome-blind support diagnostics for frozen target-aware class-C templates.

This module never settles a target and never fits a model.  It summarizes feature availability,
PIT support, temporal/competition coverage, similarity-neighbour support and feature-feature
redundancy.  It deliberately does NOT prune the frozen class-C registry: the preregistered 60%
training-fold coverage screen remains the only M1 availability gate during OOS fitting.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np

SUPPORT_VERSION = "target_aware_panel_support_v1"
GLOBAL_COVERAGE_REFERENCE = 0.60  # diagnostic only; OOS applies 60% on each training fold
NEAR_DUPLICATE_ABS_R = 0.95       # diagnostic only
VERY_NEAR_DUPLICATE_ABS_R = 0.99  # diagnostic only
MIN_CORR_OVERLAP = 200


def _finite(v: Optional[float]) -> bool:
    return v is not None and np.isfinite(float(v))


def vector_sha256(match_ids: Sequence[str], values: Sequence[Optional[float]]) -> str:
    payload = [[m, None if not _finite(v) else round(float(v), 12)]
               for m, v in zip(match_ids, values)]
    return hashlib.sha256(json.dumps(payload, sort_keys=False, separators=(",", ":"))
                          .encode()).hexdigest()


def _distribution(vals: Sequence[float]) -> Dict[str, Optional[float]]:
    if not vals:
        return {"mean": None, "std": None, "p05": None, "p50": None, "p95": None}
    a = np.asarray(vals, dtype=float)
    return {"mean": float(np.mean(a)), "std": float(np.std(a)),
            "p05": float(np.percentile(a, 5)), "p50": float(np.percentile(a, 50)),
            "p95": float(np.percentile(a, 95))}


def _bucket_summary(indices: Iterable[int], values: Sequence[Optional[float]]) -> Dict[str, Any]:
    idx = list(indices)
    good = [float(values[i]) for i in idx if _finite(values[i])]
    n = len(idx)
    return {"n_rows": n, "n_nonnull": len(good),
            "coverage": (len(good) / n if n else None), **_distribution(good)}


def summarize_column(match_ids: Sequence[str], fixtures: Sequence[Mapping[str, Any]],
                     values: Sequence[Optional[float]],
                     fold_rows: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    if not (len(match_ids) == len(fixtures) == len(values)):
        raise ValueError("column inputs have inconsistent lengths")
    n = len(values)
    good_idx = [i for i, v in enumerate(values) if _finite(v)]
    by_comp: Dict[str, List[int]] = defaultdict(list)
    by_time: Dict[str, List[int]] = defaultdict(list)
    primary_oos: List[int] = []
    for i, (mid, fx) in enumerate(zip(match_ids, fixtures)):
        by_comp[str(fx["competition_id"])].append(i)
        fr = fold_rows[mid]
        bucket = "TRAIN_ONLY" if fr["fold"] is None else f"FOLD_{fr['fold']}"
        by_time[bucket].append(i)
        if fr["fold"] is not None and not fr["involves_cohort_team"]:
            primary_oos.append(i)
    cov = len(good_idx) / n if n else 0.0
    status = ("ZERO_SUPPORT" if not good_idx else
              "GLOBAL_COVERAGE_GE_60_DIAGNOSTIC" if cov >= GLOBAL_COVERAGE_REFERENCE else
              "GLOBAL_COVERAGE_LT_60_DIAGNOSTIC")
    return {
        "n_rows": n,
        "n_nonnull": len(good_idx),
        "coverage_all": cov,
        "coverage_primary_oos": _bucket_summary(primary_oos, values),
        "support_status": status,
        "selection_effect": "NONE; OOS uses the frozen training-fold 60% coverage screen",
        "distribution": _distribution([float(values[i]) for i in good_idx]),
        "first_nonnull_match_id": match_ids[good_idx[0]] if good_idx else None,
        "last_nonnull_match_id": match_ids[good_idx[-1]] if good_idx else None,
        "by_competition": {k: _bucket_summary(v, values) for k, v in sorted(by_comp.items())},
        "by_time_bucket": {k: _bucket_summary(v, values) for k, v in sorted(by_time.items())},
        "value_vector_sha256": vector_sha256(match_ids, values),
    }


def summarize_similarity_details(details: Sequence[Optional[Mapping[str, Any]]]) -> Dict[str, Any]:
    ok = [d for d in details if d is not None]
    hist = [float(d["n_history"]) for d in ok]
    nei = [float(d["n_neighbors"]) for d in ok]
    gaps = []
    for d in ok:
        q = d.get("diagnostic") or {}
        a, b = q.get("neighbor_opponent_strength_mean"), q.get("all_opponent_strength_mean")
        if a is not None and b is not None:
            gaps.append(float(a) - float(b))
    return {
        "n_supported_rows": len(ok),
        "n_history": _distribution(hist),
        "n_neighbors": _distribution(nei),
        "neighbor_minus_all_opponent_strength": _distribution(gaps),
        "n_rows_with_strength_gap": len(gaps),
    }


def pairwise_near_duplicates(columns: Mapping[str, Sequence[Optional[float]]],
                             metadata: Mapping[str, Mapping[str, Any]],
                             threshold: float = NEAR_DUPLICATE_ABS_R,
                             min_overlap: int = MIN_CORR_OVERLAP) -> List[Dict[str, Any]]:
    """Report, never prune, highly correlated feature columns within a model family."""
    keys = sorted(columns)
    out: List[Dict[str, Any]] = []
    for ai, a in enumerate(keys):
        for b in keys[ai + 1:]:
            if metadata[a]["family"] != metadata[b]["family"]:
                continue
            pairs = [(float(x), float(y)) for x, y in zip(columns[a], columns[b])
                     if _finite(x) and _finite(y)]
            if len(pairs) < min_overlap:
                continue
            x = np.asarray([p[0] for p in pairs], float)
            y = np.asarray([p[1] for p in pairs], float)
            if np.std(x) <= 0 or np.std(y) <= 0:
                continue
            r = float(np.corrcoef(x, y)[0, 1])
            if abs(r) >= threshold:
                out.append({"a": a, "b": b, "family": metadata[a]["family"],
                            "n_overlap": len(pairs), "pearson_r": r,
                            "abs_r_ge_0_99": abs(r) >= VERY_NEAR_DUPLICATE_ABS_R,
                            "selection_effect": "NONE; diagnostic only"})
    return sorted(out, key=lambda d: (-abs(d["pearson_r"]), d["family"], d["a"], d["b"]))
