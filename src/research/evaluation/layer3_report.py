"""Frozen Layer 3 structured-model development evidence.

This report freezes development-only selection evidence. Calibration and
protected partitions remain unscored.
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Sequence

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.dataset.multiseason import MultiSeasonCorpusManifest
from src.research.evaluation.chronology import ChronologyManifest
from src.research.evaluation.model_tournament import (
    DevelopmentOOFRow,
    Layer3DevelopmentTournament,
    write_oof_rows,
)

LAYER3_EVIDENCE_VERSION = "qfe-layer3-structured-development-v3-pit-horizon"
LAYER3_FROZEN_ON = "2026-10-03"

_IMPLEMENTATION_FILES = (
    "src/research/evaluation/chronology.py",
    "src/research/evaluation/model_tournament.py",
    "src/research/evaluation/layer3_report.py",
    "src/research/models/distribution_candidates.py",
    "src/research/models/dynamic_count_strength.py",
    "src/research/dataset/multiseason.py",
)


@dataclass(frozen=True, slots=True)
class FileFingerprint:
    relative_path: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Layer3StructuredEvidence:
    version: str
    frozen_on: str
    scientific_status: str
    chronology_manifest_hash: str
    corpus_manifest_hash: str
    implementation_files: tuple[FileFingerprint, ...]
    tournament: Layer3DevelopmentTournament
    decisions: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "frozen_on": self.frozen_on,
            "scientific_status": self.scientific_status,
            "chronology_manifest_hash": self.chronology_manifest_hash,
            "corpus_manifest_hash": self.corpus_manifest_hash,
            "implementation_files": [
                row.to_dict() for row in self.implementation_files
            ],
            "tournament": self.tournament.to_dict(),
            "decisions": list(self.decisions),
        }

    @property
    def bundle_hash(self) -> str:
        return sha256_json(self.to_dict())


def _fingerprint(repo_root: Path, relative_path: str) -> FileFingerprint:
    path = repo_root / relative_path
    payload = path.read_bytes()
    return FileFingerprint(
        relative_path=relative_path,
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def _decision_records(
    tournament: Layer3DevelopmentTournament,
) -> tuple[dict[str, Any], ...]:
    intensity = {row.target: row for row in tournament.intensity_results}
    distribution = {row.target: row for row in tournament.distribution_results}

    goals_i = intensity["goals"]
    corners_i = intensity["corners"]
    goals_d = distribution["goals"]
    corners_d = distribution["corners"]

    return (
        {
            "component": "GOALS_INTENSITY",
            "development_decision": "SELECT_FOR_NEXT_STAGE",
            "selected_candidate_id": goals_i.selected_candidate_id,
            "selected_config_hash": goals_i.selected_config_hash,
        },
        {
            "component": "CORNERS_INTENSITY",
            "development_decision": "SELECT_FOR_NEXT_STAGE",
            "selected_candidate_id": corners_i.selected_candidate_id,
            "selected_config_hash": corners_i.selected_config_hash,
        },
        {
            "component": "GOALS_DIXON_COLES",
            "development_decision": "REJECT_CURRENT_CANDIDATE",
            "joint_nll_delta": goals_d.joint_nll_improvement.mean_delta,
            "joint_nll_ci95": [
                goals_d.joint_nll_improvement.lower_95,
                goals_d.joint_nll_improvement.upper_95,
            ],
            "event_log_loss_delta": (
                goals_d.event_log_loss_improvement.mean_delta
            ),
        },
        {
            "component": "CORNERS_NB2",
            "development_decision": "SELECT_FOR_NEXT_STAGE",
            "joint_nll_delta": corners_d.joint_nll_improvement.mean_delta,
            "joint_nll_ci95": [
                corners_d.joint_nll_improvement.lower_95,
                corners_d.joint_nll_improvement.upper_95,
            ],
            "event_log_loss_delta": (
                corners_d.event_log_loss_improvement.mean_delta
            ),
            "event_log_loss_ci95": [
                corners_d.event_log_loss_improvement.lower_95,
                corners_d.event_log_loss_improvement.upper_95,
            ],
        },
    )


def build_layer3_structured_evidence(
    *,
    repo_root: Path,
    corpus_manifest: MultiSeasonCorpusManifest,
    chronology: ChronologyManifest,
    tournament: Layer3DevelopmentTournament,
) -> Layer3StructuredEvidence:
    if tournament.calibration_rows_scored != 0:
        raise ValueError("calibration outcomes were scored during selection")
    if tournament.protected_rows_scored != 0:
        raise ValueError("protected outcomes were scored during selection")
    if tournament.chronology_manifest_hash != chronology.manifest_hash:
        raise ValueError("tournament/chronology hash mismatch")
    if tournament.corpus_manifest_hash != corpus_manifest.manifest_hash:
        raise ValueError("tournament/corpus hash mismatch")

    return Layer3StructuredEvidence(
        version=LAYER3_EVIDENCE_VERSION,
        frozen_on=LAYER3_FROZEN_ON,
        scientific_status=(
            "DEVELOPMENT_SELECTION_ONLY_"
            "CALIBRATION_UNTOUCHED_PROTECTED_UNTOUCHED"
        ),
        chronology_manifest_hash=chronology.manifest_hash,
        corpus_manifest_hash=corpus_manifest.manifest_hash,
        implementation_files=tuple(
            _fingerprint(Path(repo_root), relative)
            for relative in _IMPLEMENTATION_FILES
        ),
        tournament=tournament,
        decisions=_decision_records(tournament),
    )


def render_markdown(evidence: Layer3StructuredEvidence) -> str:
    intensity = {
        row.target: row for row in evidence.tournament.intensity_results
    }
    distribution = {
        row.target: row for row in evidence.tournament.distribution_results
    }
    lines = [
        "# QFE V2 Layer 3 — Structured Model Development Evidence",
        "",
        f"Frozen on: {evidence.frozen_on}",
        f"Bundle hash: {evidence.bundle_hash}",
        f"Chronology hash: {evidence.chronology_manifest_hash}",
        f"Corpus hash: {evidence.corpus_manifest_hash}",
        "",
        "> DEVELOPMENT SELECTION ONLY.",
        "> Calibration rows scored during selection: 0.",
        "> Protected rows scored during selection: 0.",
        "",
        "## Intensity grid",
        "",
        "3 decay horizons × 3 team-influence levels × 3",
        "team-in-competition prior strengths = 27 candidates per target.",
        "",
    ]

    for target in ("goals", "corners"):
        result = intensity[target]
        selected = next(
            row for row in result.candidates
            if row.candidate_id == result.selected_candidate_id
        )
        anchor = next(
            row for row in result.candidates
            if row.candidate_id == result.anchor_candidate_id
        )
        ci = selected.improvement_vs_anchor
        lines += [
            f"### {target.title()} intensity",
            "",
            f"- Anchor {result.anchor_candidate_id}: {anchor.mean_poisson_nll:.6f}",
            f"- Selected {result.selected_candidate_id}: {selected.mean_poisson_nll:.6f}",
            f"- Selected MAE: {selected.mean_mae:.6f}",
        ]
        if ci is not None:
            lines.append(
                "- Improvement vs anchor: "
                f"{ci.mean_delta:+.6f} "
                f"(95% CI {ci.lower_95:+.6f} to {ci.upper_95:+.6f})"
            )
        lines.append("")

    goals = distribution["goals"]
    corners = distribution["corners"]
    lines += [
        "## Goals distribution: Poisson vs Dixon–Coles",
        "",
        f"- N: {goals.n_scored}",
        f"- Poisson joint NLL: {goals.poisson_joint_nll:.6f}",
        f"- Dixon–Coles joint NLL: {goals.structured_joint_nll:.6f}",
        "- Joint NLL delta Poisson - Dixon–Coles: "
        f"{goals.joint_nll_improvement.mean_delta:+.6f} "
        f"(95% CI {goals.joint_nll_improvement.lower_95:+.6f} "
        f"to {goals.joint_nll_improvement.upper_95:+.6f})",
        "- Event LL delta Poisson - Dixon–Coles: "
        f"{goals.event_log_loss_improvement.mean_delta:+.6f}",
        "- Decision: reject current Dixon–Coles candidate.",
        "",
        "## Corners distribution: Poisson vs NB2",
        "",
        f"- N: {corners.n_scored}",
        f"- Poisson joint NLL: {corners.poisson_joint_nll:.6f}",
        f"- NB2 joint NLL: {corners.structured_joint_nll:.6f}",
        "- Joint NLL delta Poisson - NB2: "
        f"{corners.joint_nll_improvement.mean_delta:+.6f} "
        f"(95% CI {corners.joint_nll_improvement.lower_95:+.6f} "
        f"to {corners.joint_nll_improvement.upper_95:+.6f})",
        "- Event LL delta Poisson - NB2: "
        f"{corners.event_log_loss_improvement.mean_delta:+.6f} "
        f"(95% CI {corners.event_log_loss_improvement.lower_95:+.6f} "
        f"to {corners.event_log_loss_improvement.upper_95:+.6f})",
        "- Decision: select NB2 for the next stage.",
        "",
        "### Corners joint-NLL delta by competition",
        "",
        "| Competition | Poisson - NB2 |",
        "|---|---:|",
    ]
    for competition, delta in corners.by_competition_joint_nll_delta.items():
        lines.append(f"| {competition} | {delta:+.6f} |")

    lines += [
        "",
        "## Scientific interpretation",
        "",
        "Development evidence supports stronger dynamic intensities for both",
        "targets and NB2 overdispersion for corners. It does not support the",
        "tested Dixon–Coles correction for goals on this development window.",
        "",
        "This is not protected OOS evidence. Additional DEVELOPMENT candidates",
        "must be evaluated under the same frozen chronology before the",
        "standalone component set is frozen for CALIBRATION.",
        "",
    ]
    return "\n".join(lines)


def write_layer3_structured_evidence(
    *,
    json_path: Path,
    markdown_path: Path,
    evidence: Layer3StructuredEvidence,
    goals_oof_path: Path,
    goals_oof: Sequence[DevelopmentOOFRow],
    corners_oof_path: Path,
    corners_oof: Sequence[DevelopmentOOFRow],
) -> None:
    payloads = (
        (Path(json_path), canonical_json(evidence.to_dict()) + "\n"),
        (Path(markdown_path), render_markdown(evidence)),
    )
    for output, payload in payloads:
        if output.exists():
            if output.read_text() != payload:
                raise FileExistsError(
                    f"Layer 3 evidence exists with different content: {output}"
                )
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload)

    write_oof_rows(path=goals_oof_path, rows=goals_oof)
    write_oof_rows(path=corners_oof_path, rows=corners_oof)
