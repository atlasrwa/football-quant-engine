"""Frozen Foundation V1 capability/coverage audit bundle.

This module aggregates deterministic per-season audits into one immutable,
human-reviewable evidence package. It does not fit models, score predictions,
or choose favorable competitions.
"""

from __future__ import annotations

import hashlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from src.research.contracts.bookmaker import (
    BOOKMAKER_SETTLEMENT_REGISTRY_V1,
    Bookmaker,
)
from src.research.contracts.target import TARGET_REGISTRY_V1
from src.research.dataset.audit import (
    AUDIT_VERSION,
    CachedCorpusAuditReport,
    CachedSeasonDiscovery,
    GlobalStatsAliasAudit,
    audit_cached_corpus,
    discover_cached_seasons,
    inspect_global_stats_aliases,
)
from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.dataset.pit import PITDatasetSpec

FOUNDATION_AUDIT_VERSION = "qfe-foundation-v1-capability-coverage-v1"
FOUNDATION_FROZEN_ON = "2026-10-01"
HISTORY_SUPPORT_SCOPE = "WITHIN_AUDITED_SEASON_ONLY"

_IMPLEMENTATION_FILES = (
    "src/research/contracts/provider.py",
    "src/research/contracts/target.py",
    "src/research/contracts/bookmaker.py",
    "src/research/dataset/manifest.py",
    "src/research/dataset/pit.py",
    "src/research/dataset/audit.py",
    "src/research/dataset/foundation_report.py",
    "src/research/dataset/__init__.py",
    "src/research/thestatsapi/normalizer.py",
    "src/research/prospective/api_contract.py",
    "src/research/prospective/odds_capture.py",
)


@dataclass(frozen=True, slots=True)
class ImplementationFingerprint:
    relative_path: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True, slots=True)
class FoundationAuditBundle:
    foundation_audit_version: str
    frozen_on: str
    season_audit_version: str
    history_support_scope: str
    pit_spec: dict[str, Any]
    implementation_files: tuple[ImplementationFingerprint, ...]
    global_stats_alias_audit: GlobalStatsAliasAudit
    discovery: tuple[CachedSeasonDiscovery, ...]
    season_reports: tuple[CachedCorpusAuditReport, ...]
    aggregate: dict[str, Any]
    anomaly_findings: tuple[dict[str, Any], ...]
    contract_readiness: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "foundation_audit_version": self.foundation_audit_version,
            "frozen_on": self.frozen_on,
            "season_audit_version": self.season_audit_version,
            "history_support_scope": self.history_support_scope,
            "pit_spec": self.pit_spec,
            "implementation_files": [
                row.to_dict() for row in self.implementation_files
            ],
            "global_stats_alias_audit": self.global_stats_alias_audit.to_dict(),
            "discovery": [row.to_dict() for row in self.discovery],
            "season_reports": [row.to_dict() for row in self.season_reports],
            "aggregate": self.aggregate,
            "anomaly_findings": list(self.anomaly_findings),
            "contract_readiness": self.contract_readiness,
        }

    @property
    def bundle_hash(self) -> str:
        return sha256_json(self.to_dict())


def _file_fingerprint(repo_root: Path, relative_path: str) -> ImplementationFingerprint:
    path = repo_root / relative_path
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = path.read_bytes()
    return ImplementationFingerprint(
        relative_path=relative_path,
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
    )


def _sum_provider_coverage(
    reports: Iterable[CachedCorpusAuditReport],
) -> dict[str, dict[str, Any]]:
    totals: dict[str, dict[str, Any]] = {}
    for report in reports:
        for row in report.provider_capability.fields:
            out = totals.setdefault(
                row.canonical_field,
                {
                    "available": 0,
                    "missing": 0,
                    "semantic_status": row.semantic_status.value,
                    "historical_model_eligible": row.historical_model_eligible,
                    "target_source_eligible": row.target_source_eligible,
                },
            )
            out["available"] += row.available
            out["missing"] += row.missing
    for out in totals.values():
        denom = out["available"] + out["missing"]
        out["coverage"] = (out["available"] / denom) if denom else 0.0
    return dict(sorted(totals.items()))


def _sum_target_statuses(
    reports: Iterable[CachedCorpusAuditReport],
) -> dict[str, dict[str, int]]:
    totals: dict[str, Counter[str]] = defaultdict(Counter)
    for report in reports:
        for target_id, counts in report.target_status_counts.items():
            totals[target_id].update(counts)
    return {
        target_id: dict(sorted(counter.items()))
        for target_id, counter in sorted(totals.items())
    }


def _sum_history_support(
    reports: Iterable[CachedCorpusAuditReport],
) -> dict[str, Any]:
    rows = list(reports)
    total_n = sum(report.pit_rows for report in rows)
    thresholds: Counter[str] = Counter()
    for report in rows:
        thresholds.update(report.history_support.thresholds)
    ordered = sorted(thresholds.items(), key=lambda x: int(x[0]))
    return {
        "scope": HISTORY_SUPPORT_SCOPE,
        "total_rows": total_n,
        "threshold_counts": dict(ordered),
        "threshold_fractions": {
            key: (count / total_n) if total_n else 0.0
            for key, count in ordered
        },
        "note": (
            "Per-season audits intentionally reset history at season start. "
            "These figures are not the eventual multi-season modeling support."
        ),
    }


def _unique_source_bundle(reports: Iterable[CachedCorpusAuditReport]) -> dict[str, Any]:
    unique: dict[str, dict[str, Any]] = {}
    for report in reports:
        for row in report.source_files:
            existing = unique.get(row.relative_path)
            current = row.to_dict()
            if existing is not None and existing != current:
                raise ValueError(
                    f"Source path {row.relative_path} has inconsistent fingerprints"
                )
            unique[row.relative_path] = current
    ordered = [unique[name] for name in sorted(unique)]
    return {
        "unique_source_files": len(ordered),
        "unique_source_bundle_hash": sha256_json(ordered),
    }


def _contract_readiness() -> dict[str, Any]:
    return {
        "model_eligible_targets": list(TARGET_REGISTRY_V1.model_eligible_ids()),
        "provider_market_available_targets": list(
            TARGET_REGISTRY_V1.provider_market_available_ids()
        ),
        "provider_market_mapped_targets": list(
            TARGET_REGISTRY_V1.provider_market_mapped_ids()
        ),
        "market_comparison_eligible_targets": list(
            TARGET_REGISTRY_V1.market_comparison_eligible_ids()
        ),
        "bet365_commercially_comparable_targets": list(
            BOOKMAKER_SETTLEMENT_REGISTRY_V1.eligible_target_ids(
                bookmaker=Bookmaker.BET365,
                target_registry=TARGET_REGISTRY_V1,
            )
        ),
        "pinnacle_commercially_comparable_targets": list(
            BOOKMAKER_SETTLEMENT_REGISTRY_V1.eligible_target_ids(
                bookmaker=Bookmaker.PINNACLE,
                target_registry=TARGET_REGISTRY_V1,
            )
        ),
        "bookings_status": (
            "BLOCKED: aggregate provider card counts cannot reconstruct "
            "bookmaker second-yellow/participant settlement semantics."
        ),
        "corners_status": (
            "MODELABLE but bookmaker commercial comparison remains blocked "
            "pending provider corner_kicks equivalence to bookmaker "
            "corners-taken rules."
        ),
    }


def _anomaly_findings(
    *,
    global_alias: GlobalStatsAliasAudit,
    reports: tuple[CachedCorpusAuditReport, ...],
) -> tuple[dict[str, Any], ...]:
    findings: list[dict[str, Any]] = []
    findings.append({
        "code": "GLOBAL_LEGACY_STATS_ALIAS_CONFLICTS",
        "severity": "INFORMATIONAL_NONBLOCKING",
        "count": len(global_alias.conflicting_duplicate_refs),
        "match_refs": list(global_alias.conflicting_duplicate_refs),
        "files_by_match_ref": {
            key: list(value)
            for key, value in sorted(global_alias.conflicting_duplicate_files.items())
        },
        "interpretation": (
            "Conflicting duplicate stats payloads exist in legacy cache families. "
            "Canonical per-season audits do not use those aliases and reported "
            "zero canonical conflicts."
        ),
    })

    missing_stats = [
        {"season": report.label, "match_ref": ref}
        for report in reports
        for ref in report.stats_missing_match_refs
    ]
    findings.append({
        "code": "MISSING_CANONICAL_STATS_PAYLOADS",
        "severity": "COVERAGE",
        "count": len(missing_stats),
        "items": missing_stats,
        "interpretation": (
            "Fixture/result rows remain usable for goals; stats-derived features "
            "and targets are unavailable for these matches."
        ),
    })

    corner_missing = [
        {"season": report.label, "match_ref": ref}
        for report in reports
        for ref in report.target_unavailable_match_refs.get(
            "corners_total_regulation", ()
        )
    ]
    findings.append({
        "code": "MISSING_CORNER_TARGETS",
        "severity": "COVERAGE",
        "count": len(corner_missing),
        "items": corner_missing,
        "interpretation": (
            "Four cases lack canonical stats files; remaining cases have provider "
            "corner_kicks.all = null. Missing labels must be excluded, never imputed."
        ),
    })

    zero_xg: list[str] = []
    partial_xg: list[dict[str, Any]] = []
    for report in reports:
        coverage = report.provider_capability.by_field()["home_xg"].coverage
        if coverage == 0.0:
            zero_xg.append(report.label)
        elif coverage < 1.0:
            partial_xg.append({"season": report.label, "coverage": coverage})
    findings.append({
        "code": "XG_HETEROGENEOUS_COVERAGE",
        "severity": "CAPABILITY",
        "zero_coverage_seasons": zero_xg,
        "partial_coverage_seasons": partial_xg,
        "interpretation": (
            "xG cannot be a mandatory universal feature. Models must use explicit "
            "capability/missingness handling or a target-specific optional branch."
        ),
    })

    red_available = sum(
        report.provider_capability.by_field()["red_cards_home"].available
        + report.provider_capability.by_field()["red_cards_away"].available
        for report in reports
    )
    red_missing = sum(
        report.provider_capability.by_field()["red_cards_home"].missing
        + report.provider_capability.by_field()["red_cards_away"].missing
        for report in reports
    )
    red_denom = red_available + red_missing
    findings.append({
        "code": "RED_CARD_SPARSE_COVERAGE",
        "severity": "CAPABILITY",
        "available_side_observations": red_available,
        "missing_side_observations": red_missing,
        "coverage": (red_available / red_denom) if red_denom else 0.0,
        "interpretation": (
            "Provider red-card nulls are preserved as missing, never zero. Any later "
            "use as historical evidence must be optional/missingness-aware; bookings "
            "targets remain blocked independently."
        ),
    })

    blockers = [
        {"season": report.label, "blocking_anomalies": list(report.blocking_anomalies)}
        for report in reports
        if not report.audit_usable
    ]
    findings.append({
        "code": "CANONICAL_SEASON_BLOCKERS",
        "severity": "BLOCKING" if blockers else "NONE",
        "count": len(blockers),
        "items": blockers,
    })
    return tuple(findings)


def build_foundation_audit_bundle(
    *,
    base_dir: Path,
    repo_root: Path,
    pit_spec: PITDatasetSpec,
) -> FoundationAuditBundle:
    discovery = discover_cached_seasons(base_dir)
    usable = tuple(row for row in discovery if row.usable_for_audit)
    reports = tuple(
        audit_cached_corpus(
            base_dir=base_dir,
            corpus_spec=row.to_spec(),
            pit_spec=pit_spec,
        )
        for row in usable
    )
    global_alias = inspect_global_stats_aliases(base_dir)

    aggregate_target = _sum_target_statuses(reports)
    aggregate_provider = _sum_provider_coverage(reports)
    source_bundle = _unique_source_bundle(reports)
    competition_refs = sorted({
        ref for report in reports for ref in report.competition_refs
    })
    season_refs = sorted({
        ref for report in reports for ref in report.season_refs
    })

    aggregate = {
        "discovered_seasons": len(discovery),
        "discovery_usable_seasons": len(usable),
        "audited_seasons": len(reports),
        "audit_usable_seasons": sum(report.audit_usable for report in reports),
        "competition_refs": competition_refs,
        "season_refs": season_refs,
        "normalized_finished_matches": sum(
            report.normalized_match_count for report in reports
        ),
        "skipped_fixture_rows": sum(
            report.skipped_fixture_count for report in reports
        ),
        "canonical_stats_payloads_selected": sum(
            report.stats_payloads_selected for report in reports
        ),
        "canonical_stats_missing": sum(
            len(report.stats_missing_match_refs) for report in reports
        ),
        "canonical_stats_conflicts": sum(
            len(report.stats_conflicting_match_refs) for report in reports
        ),
        "extra_time_history_exclusions": sum(
            report.extra_time_history_exclusions for report in reports
        ),
        "provider_field_coverage": aggregate_provider,
        "target_status_counts": aggregate_target,
        "history_support": _sum_history_support(reports),
        **source_bundle,
    }

    return FoundationAuditBundle(
        foundation_audit_version=FOUNDATION_AUDIT_VERSION,
        frozen_on=FOUNDATION_FROZEN_ON,
        season_audit_version=AUDIT_VERSION,
        history_support_scope=HISTORY_SUPPORT_SCOPE,
        pit_spec={
            "schema_version": pit_spec.schema_version,
            "decision_horizon_seconds": pit_spec.decision_horizon_seconds,
            "historical_availability_policy": pit_spec.availability_policy,
            "reconstructed_post_match_embargo_seconds": (
                pit_spec.reconstructed_post_match_embargo_seconds
            ),
            "exclude_extra_time_history": pit_spec.exclude_extra_time_history,
        },
        implementation_files=tuple(
            _file_fingerprint(Path(repo_root), relative)
            for relative in _IMPLEMENTATION_FILES
        ),
        global_stats_alias_audit=global_alias,
        discovery=discovery,
        season_reports=reports,
        aggregate=aggregate,
        anomaly_findings=_anomaly_findings(
            global_alias=global_alias,
            reports=reports,
        ),
        contract_readiness=_contract_readiness(),
    )


def render_foundation_audit_markdown(bundle: FoundationAuditBundle) -> str:
    a = bundle.aggregate
    fields = a["provider_field_coverage"]
    targets = a["target_status_counts"]

    lines = [
        "# QFE Foundation V1 — Frozen Capability & Coverage Audit",
        "",
        f"Frozen on: {bundle.frozen_on}",
        f"Bundle hash: `{bundle.bundle_hash}`",
        "",
        "## Scope",
        "",
        "Read-only audit of every canonical cached TheStatsAPI season discovered in "
        "the local historical corpus. No network calls, model fitting, market "
        "optimization, or protected-pilot tuning were performed.",
        "",
        "## Corpus summary",
        "",
        f"- Canonical seasons discovered: **{a['discovered_seasons']}**",
        f"- Seasons audit-usable: **{a['audit_usable_seasons']} / {a['audited_seasons']}**",
        f"- Competitions: **{len(a['competition_refs'])}**",
        f"- Normalized finished matches: **{a['normalized_finished_matches']}**",
        f"- Canonical stats payloads selected: **{a['canonical_stats_payloads_selected']}**",
        f"- Canonical stats payloads missing: **{a['canonical_stats_missing']}**",
        f"- Canonical stats conflicts: **{a['canonical_stats_conflicts']}**",
        f"- Unique source files fingerprinted: **{a['unique_source_files']}**",
        "",
        "## Per-season audit summary",
        "",
        "| Season | Matches | Stats join | Corner labels | xG coverage | Within-season history median |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for report in bundle.season_reports:
        corner_counts = report.target_status_counts["corners_total_regulation"]
        corner_available = corner_counts.get("AVAILABLE", 0)
        xg_coverage = report.provider_capability.by_field()["home_xg"].coverage
        lines.append(
            f"| {report.label} | {report.normalized_match_count} | "
            f"{report.stats_join_rate:.3%} | {corner_available} | "
            f"{xg_coverage:.3%} | {report.history_support.median_support:.1f} |"
        )

    lines += [
        "",
        "## Aggregate target coverage",
        "",
        "| Target | Available | Missing/blocked |",
        "|---|---:|---:|",
    ]
    for target_id, counts in sorted(targets.items()):
        available = counts.get("AVAILABLE", 0)
        unavailable = sum(v for k, v in counts.items() if k != "AVAILABLE")
        lines.append(f"| {target_id} | {available} | {unavailable} |")

    lines += [
        "",
        "## Selected provider-field coverage",
        "",
        "| Field | Available | Missing | Coverage |",
        "|---|---:|---:|---:|",
    ]
    for field_name in (
        "corners_home",
        "shots_home",
        "shots_on_target_home",
        "yellow_cards_home",
        "red_cards_home",
        "home_xg",
    ):
        row = fields[field_name]
        lines.append(
            f"| {field_name} | {row['available']} | {row['missing']} | "
            f"{row['coverage']:.4%} |"
        )

    lines += [
        "",
        "## Contract readiness",
        "",
        "- Goals: modelable; Bet365/Pinnacle regulation-time comparison contracts "
        "are verified for current goal target definitions.",
        "- Corners: modelable, but commercial bookmaker comparison remains blocked "
        "until provider `corner_kicks` is proven equivalent to bookmaker "
        "corners-taken settlement.",
        "- Bookings: blocked. Aggregate yellow/red counts cannot reconstruct "
        "second-yellow and participant-eligibility settlement semantics.",
        "",
        "## Anomalies reviewed",
        "",
    ]
    for finding in bundle.anomaly_findings:
        code = finding["code"]
        severity = finding["severity"]
        count = finding.get("count")
        suffix = f" — count {count}" if count is not None else ""
        lines.append(f"- **{code}** [{severity}]{suffix}")
        interpretation = finding.get("interpretation")
        if interpretation:
            lines.append(f"  - {interpretation}")
        if code == "XG_HETEROGENEOUS_COVERAGE":
            lines.append(
                "  - Zero-coverage seasons: "
                + ", ".join(finding["zero_coverage_seasons"])
            )
            partial = ", ".join(
                f"{row['season']}={row['coverage']:.2%}"
                for row in finding["partial_coverage_seasons"]
            )
            lines.append("  - Partial-coverage seasons: " + (partial or "none"))
        if code == "RED_CARD_SPARSE_COVERAGE":
            lines.append(f"  - Aggregate side coverage: {finding['coverage']:.2%}")

    lines += [
        "",
        "## History-support interpretation",
        "",
        "History-support figures in this audit are **within each audited season only**. "
        "They intentionally reset at season boundaries and therefore understate the "
        "support available to the eventual multi-season point-in-time training corpus.",
        "",
        "## Scientific interpretation",
        "",
        "This audit validates data identity, semantics, coverage, target availability, "
        "point-in-time construction, and immutable provenance. It does **not** establish "
        "predictive superiority, calibration quality, market edge, or profitability.",
        "",
    ]
    return "\n".join(lines)


def write_frozen_foundation_audit(
    *,
    json_path: Path,
    markdown_path: Path,
    bundle: FoundationAuditBundle,
) -> None:
    json_payload = canonical_json(bundle.to_dict()) + "\n"
    markdown_payload = render_foundation_audit_markdown(bundle)

    for path, payload in (
        (Path(json_path), json_payload),
        (Path(markdown_path), markdown_payload),
    ):
        if path.exists():
            if path.read_text() != payload:
                raise FileExistsError(
                    f"Frozen audit artifact {path} exists with different content"
                )
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(payload)
