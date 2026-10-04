"""Layer 2 development-only evidence for QFE V2.

This module evaluates the first dynamic hierarchical count baseline against a
competition-only dynamic climatology on the canonical multi-season corpus.

It is deliberately *not* a protected model-selection report:
- benchmark hyperparameters are not claimed optimal;
- no market odds are used;
- no calibration or binary market log loss is assessed here;
- the report exists to verify chronology, support behavior and whether the
  hierarchy adds basic count-predictive information before more complex models.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.dataset.multiseason import (
    MultiSeasonCorpusManifest,
    build_multiseason_pit_corpus,
)
from src.research.dataset.pit import PITDatasetSpec
from src.research.models.dynamic_count_strength import (
    CORNERS_TARGET,
    GOALS_TARGET,
    CountTargetSpec,
    DynamicCountConfig,
    DynamicHierarchicalCountBaseline,
    poisson_count_nll,
)


LAYER2_EVIDENCE_VERSION = "qfe-layer2-development-smoke-v2-pit-horizon"
LAYER2_FROZEN_ON = "2026-10-03"

_IMPLEMENTATION_FILES = (
    "src/research/dataset/multiseason.py",
    "src/research/models/dynamic_count_strength.py",
    "src/research/evaluation/layer2_report.py",
)


@dataclass(frozen=True, slots=True)
class FileFingerprint:
    relative_path: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SliceMetrics:
    n: int
    dynamic_nll: float
    climatology_nll: float
    nll_delta_climatology_minus_dynamic: float
    dynamic_mae: float
    climatology_mae: float
    mae_delta_climatology_minus_dynamic: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class TargetDevelopmentReport:
    target: str
    model_version: str
    dynamic_config: dict[str, Any]
    dynamic_config_hash: str
    climatology_config: dict[str, Any]
    climatology_config_hash: str
    predictions: int
    usable_outcomes: int
    missing_or_excluded_outcomes: int
    supported_predictions: int
    supported_fraction: float
    first_supported_kickoff_ts: int | None
    effective_support_mean: float
    effective_support_max: float
    all_rows: SliceMetrics
    supported_rows: SliceMetrics | None
    by_competition: dict[str, SliceMetrics]
    by_season: dict[str, SliceMetrics]
    by_support_bucket: dict[str, SliceMetrics]

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "model_version": self.model_version,
            "dynamic_config": self.dynamic_config,
            "dynamic_config_hash": self.dynamic_config_hash,
            "climatology_config": self.climatology_config,
            "climatology_config_hash": self.climatology_config_hash,
            "predictions": self.predictions,
            "usable_outcomes": self.usable_outcomes,
            "missing_or_excluded_outcomes": self.missing_or_excluded_outcomes,
            "supported_predictions": self.supported_predictions,
            "supported_fraction": self.supported_fraction,
            "first_supported_kickoff_ts": self.first_supported_kickoff_ts,
            "effective_support_mean": self.effective_support_mean,
            "effective_support_max": self.effective_support_max,
            "all_rows": self.all_rows.to_dict(),
            "supported_rows": (
                self.supported_rows.to_dict()
                if self.supported_rows is not None
                else None
            ),
            "by_competition": {
                key: value.to_dict()
                for key, value in sorted(self.by_competition.items())
            },
            "by_season": {
                key: value.to_dict()
                for key, value in sorted(self.by_season.items())
            },
            "by_support_bucket": {
                key: value.to_dict()
                for key, value in self.by_support_bucket.items()
            },
        }


@dataclass(frozen=True, slots=True)
class Layer2EvidenceBundle:
    version: str
    frozen_on: str
    scientific_status: str
    corpus_manifest: MultiSeasonCorpusManifest
    implementation_files: tuple[FileFingerprint, ...]
    target_reports: tuple[TargetDevelopmentReport, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "frozen_on": self.frozen_on,
            "scientific_status": self.scientific_status,
            "corpus_manifest": self.corpus_manifest.to_dict(),
            "implementation_files": [
                row.to_dict() for row in self.implementation_files
            ],
            "target_reports": [
                report.to_dict() for report in self.target_reports
            ],
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


def _slice_metrics(rows: list[tuple[float, float, float, float]]) -> SliceMetrics:
    """Rows are dynamic_nll, climatology_nll, dynamic_abs, climatology_abs."""
    if not rows:
        raise ValueError("cannot summarize empty metric slice")
    dn = mean(row[0] for row in rows)
    cn = mean(row[1] for row in rows)
    dm = mean(row[2] for row in rows)
    cm = mean(row[3] for row in rows)
    return SliceMetrics(
        n=len(rows),
        dynamic_nll=dn,
        climatology_nll=cn,
        nll_delta_climatology_minus_dynamic=cn - dn,
        dynamic_mae=dm,
        climatology_mae=cm,
        mae_delta_climatology_minus_dynamic=cm - dm,
    )


def _support_bucket(value: float) -> str:
    if value < 3.0:
        return "0-<3"
    if value < 5.0:
        return "3-<5"
    if value < 10.0:
        return "5-<10"
    return "10+"


def _target_report(
    *,
    matches,
    target: CountTargetSpec,
    config: DynamicCountConfig,
) -> TargetDevelopmentReport:
    climatology_config = DynamicCountConfig(
        **{
            **asdict(config),
            "team_influence": 0.0,
        }
    )
    dynamic = DynamicHierarchicalCountBaseline(target, config)
    climatology = DynamicHierarchicalCountBaseline(
        target,
        climatology_config,
    )
    dynamic_predictions = dynamic.walk_forward(matches)
    climatology_predictions = climatology.walk_forward(matches)
    if len(dynamic_predictions) != len(climatology_predictions):
        raise AssertionError("prediction count mismatch")

    by_fixture = {match.stable_fixture_key: match for match in matches}
    all_rows: list[tuple[float, float, float, float]] = []
    supported_rows: list[tuple[float, float, float, float]] = []
    by_comp: dict[str, list[tuple[float, float, float, float]]] = defaultdict(list)
    by_season: dict[str, list[tuple[float, float, float, float]]] = defaultdict(list)
    by_support: dict[str, list[tuple[float, float, float, float]]] = defaultdict(list)
    supports: list[float] = []
    missing = 0

    for dp, cp in zip(
        dynamic_predictions,
        climatology_predictions,
        strict=True,
    ):
        match = by_fixture[dp.fixture_key]
        supports.append(dp.effective_support)
        counts = target.observed_counts(match)
        if counts is None:
            missing += 1
            continue
        home, away = counts
        dynamic_nll = (
            poisson_count_nll(home, dp.lambda_home)
            + poisson_count_nll(away, dp.lambda_away)
        ) / 2.0
        climatology_nll = (
            poisson_count_nll(home, cp.lambda_home)
            + poisson_count_nll(away, cp.lambda_away)
        ) / 2.0
        dynamic_abs = (
            abs(home - dp.lambda_home)
            + abs(away - dp.lambda_away)
        ) / 2.0
        climatology_abs = (
            abs(home - cp.lambda_home)
            + abs(away - cp.lambda_away)
        ) / 2.0
        row = (
            dynamic_nll,
            climatology_nll,
            dynamic_abs,
            climatology_abs,
        )
        all_rows.append(row)
        if dp.supported:
            supported_rows.append(row)
        by_comp[match.competition_ref or "<missing>"].append(row)
        by_season[match.season_ref or "<missing>"].append(row)
        by_support[_support_bucket(dp.effective_support)].append(row)

    supported_count = sum(p.supported for p in dynamic_predictions)
    first_supported = next(
        (
            p.kickoff_ts
            for p in dynamic_predictions
            if p.supported
        ),
        None,
    )

    support_order = ("0-<3", "3-<5", "5-<10", "10+")
    return TargetDevelopmentReport(
        target=target.name,
        model_version=dynamic.model_version,
        dynamic_config=asdict(config),
        dynamic_config_hash=config.identity_hash,
        climatology_config=asdict(climatology_config),
        climatology_config_hash=climatology_config.identity_hash,
        predictions=len(dynamic_predictions),
        usable_outcomes=len(all_rows),
        missing_or_excluded_outcomes=missing,
        supported_predictions=supported_count,
        supported_fraction=(
            supported_count / len(dynamic_predictions)
            if dynamic_predictions else 0.0
        ),
        first_supported_kickoff_ts=first_supported,
        effective_support_mean=mean(supports) if supports else 0.0,
        effective_support_max=max(supports) if supports else 0.0,
        all_rows=_slice_metrics(all_rows),
        supported_rows=(
            _slice_metrics(supported_rows)
            if supported_rows
            else None
        ),
        by_competition={
            key: _slice_metrics(value)
            for key, value in sorted(by_comp.items())
        },
        by_season={
            key: _slice_metrics(value)
            for key, value in sorted(by_season.items())
        },
        by_support_bucket={
            key: _slice_metrics(by_support[key])
            for key in support_order
            if by_support.get(key)
        },
    )


def build_layer2_evidence(
    *,
    base_dir: Path,
    repo_root: Path,
    pit_spec: PITDatasetSpec,
    config: DynamicCountConfig = DynamicCountConfig(),
) -> Layer2EvidenceBundle:
    corpus = build_multiseason_pit_corpus(
        base_dir=base_dir,
        pit_spec=pit_spec,
    )
    reports = tuple(
        _target_report(
            matches=corpus.matches,
            target=target,
            config=config,
        )
        for target in (GOALS_TARGET, CORNERS_TARGET)
    )
    return Layer2EvidenceBundle(
        version=LAYER2_EVIDENCE_VERSION,
        frozen_on=LAYER2_FROZEN_ON,
        scientific_status=(
            "DEVELOPMENT_SMOKE_ONLY_NOT_PROMOTED_NOT_CALIBRATED_"
            "NO_MARKET_COMPARISON"
        ),
        corpus_manifest=corpus.manifest,
        implementation_files=tuple(
            _fingerprint(Path(repo_root), relative)
            for relative in _IMPLEMENTATION_FILES
        ),
        target_reports=reports,
    )


def render_layer2_markdown(bundle: Layer2EvidenceBundle) -> str:
    lines = [
        "# QFE V2 Layer 2 — Development Smoke Evidence",
        "",
        f"Frozen on: {bundle.frozen_on}",
        f"Bundle hash: `{bundle.bundle_hash}`",
        "",
        "> **DEVELOPMENT ONLY.** This is not a promoted model, calibration result,",
        "> protected OOS result, market-edge claim, or commercial validation.",
        "",
        "## Multi-season corpus",
        "",
        f"- Matches: **{bundle.corpus_manifest.n_matches}**",
        f"- Competitions: **{len(bundle.corpus_manifest.competition_refs)}**",
        f"- Seasons: **{len(bundle.corpus_manifest.season_refs)}**",
        f"- Source files: **{bundle.corpus_manifest.unique_source_files}**",
        f"- Corpus manifest: `{bundle.corpus_manifest.manifest_hash}`",
        f"- PIT manifest: `{bundle.corpus_manifest.pit_manifest_hash}`",
        "",
        "## Benchmark design",
        "",
        "The dynamic hierarchy is compared with a competition-only dynamic",
        "climatology using the same decay/prior settings but `team_influence=0`.",
        "Both are availability-gated at the registered T-6h horizon with a 6h",
        "reconstructed post-match embargo, and same-kickoff batched. No odds are inputs.",
        "",
        "The current distribution is independent Poisson and exists only as the",
        "first conservative benchmark. Goals dependence and corners",
        "overdispersion are later Layer 3 candidates.",
        "",
    ]

    for report in bundle.target_reports:
        a = report.all_rows
        lines += [
            f"## {report.target.title()}",
            "",
            f"- Predictions: **{report.predictions}**",
            f"- Usable outcomes: **{report.usable_outcomes}**",
            f"- Missing/excluded outcomes: **{report.missing_or_excluded_outcomes}**",
            f"- Supported: **{report.supported_predictions} "
            f"({report.supported_fraction:.2%})**",
            f"- Mean effective support: **{report.effective_support_mean:.3f}**",
            f"- Side-count Poisson NLL — dynamic: **{a.dynamic_nll:.6f}**",
            f"- Side-count Poisson NLL — climatology: **{a.climatology_nll:.6f}**",
            f"- NLL delta (climatology - dynamic): "
            f"**{a.nll_delta_climatology_minus_dynamic:+.6f}**",
            f"- Side-count MAE — dynamic: **{a.dynamic_mae:.6f}**",
            f"- Side-count MAE — climatology: **{a.climatology_mae:.6f}**",
            f"- MAE delta (climatology - dynamic): "
            f"**{a.mae_delta_climatology_minus_dynamic:+.6f}**",
            "",
            "### By competition",
            "",
            "| Competition | N | NLL dynamic | NLL climatology | Delta |",
            "|---|---:|---:|---:|---:|",
        ]
        for competition, metric in report.by_competition.items():
            lines.append(
                f"| {competition} | {metric.n} | {metric.dynamic_nll:.6f} | "
                f"{metric.climatology_nll:.6f} | "
                f"{metric.nll_delta_climatology_minus_dynamic:+.6f} |"
            )

        lines += [
            "",
            "### By support bucket",
            "",
            "| Effective support | N | NLL dynamic | NLL climatology | Delta |",
            "|---|---:|---:|---:|---:|",
        ]
        for bucket, metric in report.by_support_bucket.items():
            lines.append(
                f"| {bucket} | {metric.n} | {metric.dynamic_nll:.6f} | "
                f"{metric.climatology_nll:.6f} | "
                f"{metric.nll_delta_climatology_minus_dynamic:+.6f} |"
            )

        worst = sorted(
            report.by_season.items(),
            key=lambda item: item[1].nll_delta_climatology_minus_dynamic,
        )[:5]
        lines += [
            "",
            "### Weakest season deltas (preserved, not tuned away)",
            "",
            "| Season | N | Delta |",
            "|---|---:|---:|",
        ]
        for season, metric in worst:
            lines.append(
                f"| {season} | {metric.n} | "
                f"{metric.nll_delta_climatology_minus_dynamic:+.6f} |"
            )
        lines.append("")

    lines += [
        "## Interpretation",
        "",
        "A positive NLL delta means the dynamic hierarchy had lower side-count",
        "Poisson NLL than the competition-only climatology on this development",
        "walk-forward. This is useful evidence that team/opponent state contains",
        "signal, but it is not sufficient for model promotion.",
        "",
        "Next scientific gate: freeze chronological development/calibration/protected",
        "folds, then compare structured distribution families and candidate",
        "hyperparameters without using protected outcomes for selection.",
        "",
    ]
    return "\n".join(lines)


def write_layer2_evidence(
    *,
    json_path: Path,
    markdown_path: Path,
    bundle: Layer2EvidenceBundle,
) -> None:
    payloads = (
        (
            Path(json_path),
            canonical_json(bundle.to_dict()) + "\n",
        ),
        (
            Path(markdown_path),
            render_layer2_markdown(bundle),
        ),
    )
    for path, payload in payloads:
        if path.exists():
            if path.read_text() != payload:
                raise FileExistsError(
                    f"Layer 2 evidence already exists with different content: {path}"
                )
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload)
