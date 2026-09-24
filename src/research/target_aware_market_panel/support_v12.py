"""Deterministic V1.2 evaluability gate helpers. No outcomes or model code."""
from __future__ import annotations

from typing import Any, Mapping, Sequence

import numpy as np

COVERAGE_THRESHOLD = 0.60
SIMILARITY_TYPE = "OPPONENT_SIMILARITY_CONDITIONAL"


def _finite(v: Any) -> bool:
    return v is not None and np.isfinite(float(v))


def training_coverage(values: Sequence[Any], fixtures: Sequence[Mapping[str, Any]],
                      fold: Mapping[str, Any]) -> dict[str, Any]:
    if len(values) != len(fixtures):
        raise ValueError("values/fixtures length mismatch")
    idx = [i for i, fx in enumerate(fixtures)
           if int(fx["kickoff"]) < int(fold["test_start"])]
    if len(idx) != int(fold["n_train"]):
        raise ValueError(f"training denominator mismatch: {len(idx)} != {fold['n_train']}")
    good = sum(_finite(values[i]) for i in idx)
    n = len(idx)
    return {"n_train": n, "n_nonnull": good, "coverage": good / n if n else 0.0}


def evaluability_gate(per_template: Sequence[Mapping[str, Any]], folds: Mapping[str, Any],
                       threshold: float = COVERAGE_THRESHOLD) -> tuple[dict[str, Any], bool]:
    if float(threshold) != COVERAGE_THRESHOLD:
        raise ValueError("V1.2 coverage threshold is frozen at 0.60")
    families = sorted({str(x["family"]) for x in per_template})
    details: dict[str, Any] = {}
    passed = True
    for family in families:
        details[family] = {}
        for fold_id in sorted(folds["folds"], key=int):
            eligible = [x for x in per_template
                        if str(x["family"]) == family
                        and float(x["training_fold_coverage"][fold_id]["coverage"]) >= threshold]
            similarity = [x for x in eligible if x["template_type"] == SIMILARITY_TYPE]
            rec = {
                "n_class_c_pass": len(eligible),
                "n_similarity_pass": len(similarity),
                "class_c_signatures": sorted(str(x["canonical_signature_sha256"]) for x in eligible),
                "similarity_signatures": sorted(
                    str(x["canonical_signature_sha256"]) for x in similarity),
            }
            details[family][fold_id] = rec
            passed = passed and rec["n_class_c_pass"] > 0 and rec["n_similarity_pass"] > 0
    return details, passed
