"""Final Layer 3 DEVELOPMENT-only component evaluation bundle.

This report reconciles two intentionally different diagnostics:

1. Structured-development side-joint likelihood diagnostics from the full
   DEVELOPMENT walk-forward.
2. Immutable fold-based OOF total-market diagnostics used to compare candidate
   components on total-count NLL, binary log loss, and Brier.

Those metrics are not interchangeable. The report names them explicitly and
never uses CALIBRATION or PROTECTED outcomes.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.evaluation.chronology import CALIBRATION_END_TS, DEVELOPMENT_END_TS
from src.research.evaluation.paired_uncertainty import paired_block_bootstrap

COMPONENT_EVALUATION_VERSION = "qfe-layer3-component-evaluation-v1"
FROZEN_ON = "2026-10-02"


@dataclass(frozen=True, slots=True)
class ArtifactRef:
    relative_path: str
    file_sha256: str
    semantic_sha256: str
    bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "file_sha256": self.file_sha256,
            "semantic_sha256": self.semantic_sha256,
            "bytes": self.bytes,
        }


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"expected object: {path}")
    return value


def _ref(repo_root: Path, path: Path) -> ArtifactRef:
    payload = path.read_bytes()
    data = json.loads(payload)
    return ArtifactRef(
        relative_path=path.relative_to(repo_root).as_posix(),
        file_sha256=hashlib.sha256(payload).hexdigest(),
        semantic_sha256=sha256_json(data),
        bytes=len(payload),
    )


def _source_ref(repo_root: Path, path: Path) -> ArtifactRef:
    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    return ArtifactRef(
        relative_path=path.relative_to(repo_root).as_posix(),
        file_sha256=digest,
        semantic_sha256=digest,
        bytes=len(payload),
    )


def _index(rows: list[dict[str, Any]], target: str, candidate: str | None = None):
    out = {}
    for row in rows:
        if row.get("target") != target:
            continue
        if candidate is not None and row.get("candidate") != candidate:
            continue
        key = row["fixture_key"]
        if key in out:
            raise ValueError(f"duplicate OOF row for {target}/{candidate}/{key}")
        out[key] = row
    return out


def _paired(base: dict, cand: dict) -> dict[str, Any]:
    keys = sorted(set(base).intersection(cand))
    if not keys:
        raise ValueError("no paired OOF rows")
    output: dict[str, Any] = {"n_pairs": len(keys)}
    for field, metric in (
        ("count_log_probability", "total_count_nll"),
        ("binary_log_loss", "binary_log_loss"),
        ("brier", "brier"),
    ):
        rows = []
        for key in keys:
            b = base[key]
            c = cand[key]
            if b["kickoff_ts"] >= DEVELOPMENT_END_TS or c["kickoff_ts"] >= DEVELOPMENT_END_TS:
                raise ValueError("non-development outcome entered component comparison")
            base_loss = -b[field] if field == "count_log_probability" else b[field]
            cand_loss = -c[field] if field == "count_log_probability" else c[field]
            rows.append((b["kickoff_ts"], base_loss, cand_loss))
        output[metric] = paired_block_bootstrap(rows, metric=metric).to_dict()
    return output


def _decision(metrics: dict[str, Any]) -> str:
    count = metrics["total_count_nll"]
    ll = metrics["binary_log_loss"]
    brier = metrics["brier"]
    if ll["ci_low"] > 0 and brier["ci_low"] > 0 and count["ci_high"] < 0:
        return "BINARY_MARKET_CANDIDATE_MIXED_TOTAL_DISTRIBUTION"
    if count["ci_low"] > 0 and ll["ci_low"] > 0 and brier["ci_low"] > 0:
        return "DEVELOPMENT_CANDIDATE_CONSISTENT"
    if count["mean_improvement"] > 0 and ll["mean_improvement"] > 0 and brier["mean_improvement"] > 0:
        return "WEAK_MIXED_SIGNAL_CIS_CROSS_ZERO"
    if count["ci_high"] < 0 and ll["ci_high"] < 0 and brier["ci_high"] < 0:
        return "REJECT_MATERIALLY_WORSE"
    return "NOT_SUPPORTED_OR_INCONCLUSIVE"


def build_component_evaluation(*, repo_root: Path) -> dict[str, Any]:
    root = Path(repo_root)
    evidence = root / "evidence/layer3"
    chronology = _read(evidence / "QFE_LAYER3_CHRONOLOGY_V1.json")
    structured_dev = _read(evidence / "QFE_LAYER3_STRUCTURED_DEVELOPMENT.json")
    structured = _read(evidence / "STRUCTURED_DEVELOPMENT_OOF.json")
    tabular = _read(evidence / "TABULAR_DEVELOPMENT_OOF.json")
    similar = _read(evidence / "SIMILAR_CONTEXT_DEVELOPMENT_OOF.json")

    chronology_hash = sha256_json(chronology)
    corpus_hashes = {
        structured_dev["corpus_manifest_hash"],
        structured["corpus_manifest_hash"],
        tabular["corpus_manifest_hash"],
        similar["corpus_manifest_hash"],
        chronology["corpus_manifest_hash"],
    }
    if len(corpus_hashes) != 1:
        raise ValueError("component artifacts do not share one corpus manifest")
    if structured_dev["chronology_manifest_hash"] != chronology_hash:
        raise ValueError("structured report chronology hash mismatch")

    fold_hashes = {
        structured["development_fold_manifest"]["manifest_hash"],
        tabular["development_fold_manifest"]["manifest_hash"],
        similar["development_fold_manifest"]["manifest_hash"],
    }
    if len(fold_hashes) != 1:
        raise ValueError("OOF artifacts do not share one development fold manifest")

    for artifact in (structured, tabular, similar):
        for row in artifact["rows"]:
            if row["kickoff_ts"] >= DEVELOPMENT_END_TS:
                raise ValueError("calibration/protected row found in development OOF")
    if structured_dev["tournament"]["calibration_rows_scored"] != 0:
        raise ValueError("calibration outcomes were scored during selection")
    if structured_dev["tournament"]["protected_rows_scored"] != 0:
        raise ValueError("protected outcomes were scored during selection")

    comparisons: list[dict[str, Any]] = []
    for target in ("goals", "corners"):
        base = _index(structured["rows"], target, "dynamic_poisson")
        candidates: list[tuple[str, dict]] = []
        if target == "goals":
            for name in ("dynamic_dixon_coles", "dynamic_nb2", "competition_dixon_coles"):
                candidates.append((name, _index(structured["rows"], target, name)))
        else:
            candidates.append(("dynamic_side_nb2", _index(structured["rows"], target, "dynamic_side_nb2")))
        candidates.append(("tabular_hist_gradient_boosting", _index(tabular["rows"], target)))
        candidates.append(("similar_context", _index(similar["rows"], target)))
        for name, candidate_rows in candidates:
            paired = _paired(base, candidate_rows)
            comparisons.append({
                "target": target,
                "baseline": "dynamic_poisson",
                "candidate": name,
                "paired_metrics": paired,
                "development_decision": _decision(paired),
            })

    evaluator_refs = tuple(
        _source_ref(root, root / name)
        for name in (
            "src/research/evaluation/component_evaluation.py",
            "src/research/evaluation/paired_uncertainty.py",
        )
    )

    refs = tuple(
        _ref(root, evidence / name)
        for name in (
            "QFE_LAYER3_CHRONOLOGY_V1.json",
            "QFE_LAYER3_STRUCTURED_DEVELOPMENT.json",
            "STRUCTURED_DEVELOPMENT_OOF.json",
            "TABULAR_DEVELOPMENT_OOF.json",
            "SIMILAR_CONTEXT_DEVELOPMENT_OOF.json",
        )
    )
    bundle = {
        "version": COMPONENT_EVALUATION_VERSION,
        "frozen_on": FROZEN_ON,
        "scientific_status": "DEVELOPMENT_OOF_ONLY_CALIBRATION_AND_PROTECTED_UNSCORED",
        "chronology_manifest_hash": chronology_hash,
        "corpus_manifest_hash": next(iter(corpus_hashes)),
        "development_fold_manifest_hash": next(iter(fold_hashes)),
        "evaluation_implementation_refs": [
            ref.to_dict() for ref in evaluator_refs
        ],
        "artifact_refs": [ref.to_dict() for ref in refs],
        "structured_side_joint_diagnostics": structured_dev["tournament"]["distribution_results"],
        "oof_component_comparisons": comparisons,
        "metric_contract": {
            "side_joint_nll": "joint home/away side-count likelihood; not the same object as total-count NLL",
            "total_count_nll": "negative log probability of realized match total in fold OOF",
            "binary_log_loss": "proper score for fixed development total line (goals 2.5, corners 9.5)",
            "brier": "squared probability error for the same fixed development total line",
        },
    }
    bundle["bundle_hash"] = sha256_json(bundle)
    return bundle


def render_markdown(bundle: dict[str, Any]) -> str:
    lines = [
        "# QFE V2 Layer 3 — Component Evaluation",
        "",
        f"Frozen on: {bundle['frozen_on']}",
        f"Bundle hash: `{bundle['bundle_hash']}`",
        f"Chronology hash: `{bundle['chronology_manifest_hash']}`",
        f"Development fold hash: `{bundle['development_fold_manifest_hash']}`",
        "",
        "> **DEVELOPMENT OOF ONLY. Calibration and protected outcomes are unscored.**",
        "",
        "## Metric distinction",
        "",
        "The earlier structured tournament's `side_joint_nll` evaluates the joint",
        "home/away side-count likelihood. The fold OOF `total_count_nll` evaluates",
        "the probability of the realized match total. They are different scoring",
        "objects and are reported separately.",
        "",
        "## Paired OOF component comparisons vs dynamic Poisson",
        "",
        "| Target | Candidate | Total-count NLL Δ | Binary LL Δ | Brier Δ | Decision |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in bundle["oof_component_comparisons"]:
        m = row["paired_metrics"]
        lines.append(
            f"| {row['target']} | {row['candidate']} | "
            f"{m['total_count_nll']['mean_improvement']:+.6f} "
            f"[{m['total_count_nll']['ci_low']:+.6f}, {m['total_count_nll']['ci_high']:+.6f}] | "
            f"{m['binary_log_loss']['mean_improvement']:+.6f} "
            f"[{m['binary_log_loss']['ci_low']:+.6f}, {m['binary_log_loss']['ci_high']:+.6f}] | "
            f"{m['brier']['mean_improvement']:+.6f} "
            f"[{m['brier']['ci_low']:+.6f}, {m['brier']['ci_high']:+.6f}] | "
            f"{row['development_decision']} |"
        )
    lines += [
        "",
        "## Interpretation",
        "",
        "- Goals: tested Dixon-Coles/NB2 replacements are not supported; tabular is materially worse; similar-context remains a weak possible ensemble diversifier because mean gains are positive but CIs cross zero.",
        "- Corners: side-NB2 improves binary over/under Log Loss and Brier with positive paired CIs, but worsens fold OOF total-count NLL. It is therefore retained only as a mixed binary-market candidate, not declared a universally superior count distribution.",
        "- Corners similar-context is weak/inconclusive; tabular is materially worse.",
        "- No calibration fitting, ensemble fitting, market comparison, or protected scoring is authorized by this evidence.",
        "",
    ]
    return "\n".join(lines)


def write_component_evaluation(*, json_path: Path, markdown_path: Path, bundle: dict[str, Any]) -> None:
    payloads = (
        (Path(json_path), canonical_json(bundle) + "\n"),
        (Path(markdown_path), render_markdown(bundle)),
    )
    for path, payload in payloads:
        if path.exists():
            if path.read_text() != payload:
                raise FileExistsError(f"component evaluation exists with different content: {path}")
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload)
