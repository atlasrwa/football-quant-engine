"""Canonical multi-season point-in-time corpus for QFE V2 Layer 2.

Foundation V1 audited each canonical season independently. This module composes
those accepted season slices into one continuous chronological corpus so team
history may legitimately carry across season boundaries and competition
transitions.

No market data are loaded here. The corpus is football-evidence only.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.research.data_source import ResearchMatch
from src.research.dataset.audit import (
    CachedCorpusAuditReport,
    audit_cached_corpus,
    discover_cached_seasons,
)
from src.research.dataset.manifest import sha256_json
from src.research.dataset.pit import (
    PITDatasetArtifact,
    PITDatasetBuilder,
    PITDatasetSpec,
)
from src.research.thestatsapi.adapter import TheStatsAPIDataSource
from src.research.thestatsapi.corpus_loader import TheStatsAPICorpusLoader


MULTISEASON_CORPUS_VERSION = "qfe-multiseason-corpus-v1"


@dataclass(frozen=True, slots=True)
class MultiSeasonCorpusManifest:
    version: str
    source_root_id: str
    season_audit_hashes: tuple[tuple[str, str], ...]
    unique_source_files: int
    unique_source_bundle_hash: str
    competition_refs: tuple[str, ...]
    season_refs: tuple[str, ...]
    n_matches: int
    first_kickoff_ts: int | None
    last_kickoff_ts: int | None
    match_content_hash: str
    pit_manifest_hash: str
    decision_horizon_seconds: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "source_root_id": self.source_root_id,
            "season_audit_hashes": [
                {"label": label, "report_hash": report_hash}
                for label, report_hash in self.season_audit_hashes
            ],
            "unique_source_files": self.unique_source_files,
            "unique_source_bundle_hash": self.unique_source_bundle_hash,
            "competition_refs": list(self.competition_refs),
            "season_refs": list(self.season_refs),
            "n_matches": self.n_matches,
            "first_kickoff_ts": self.first_kickoff_ts,
            "last_kickoff_ts": self.last_kickoff_ts,
            "match_content_hash": self.match_content_hash,
            "pit_manifest_hash": self.pit_manifest_hash,
            "decision_horizon_seconds": self.decision_horizon_seconds,
        }

    @property
    def manifest_hash(self) -> str:
        return sha256_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class MultiSeasonPITCorpus:
    manifest: MultiSeasonCorpusManifest
    matches: tuple[ResearchMatch, ...]
    pit: PITDatasetArtifact
    season_reports: tuple[CachedCorpusAuditReport, ...]


def _json_file(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return value


def _stats_map_from_report(
    *,
    base_dir: Path,
    report: CachedCorpusAuditReport,
) -> dict[str, dict[str, Any]]:
    """Reconstruct exactly the stats payload set fingerprinted by the audit."""
    fixture_names = set(report.fixture_files)
    stats: dict[str, dict[str, Any]] = {}
    for fingerprint in report.source_files:
        if fingerprint.relative_path in fixture_names:
            continue
        path = Path(base_dir) / fingerprint.relative_path
        payload = path.read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != fingerprint.sha256:
            raise ValueError(
                f"Source file changed since season audit: {fingerprint.relative_path}"
            )
        data = json.loads(payload)
        match_ref = ((data or {}).get("data") or {}).get("match_id")
        if not isinstance(match_ref, str) or not match_ref:
            raise ValueError(
                f"Selected stats file lacks match_id: {fingerprint.relative_path}"
            )
        if match_ref in stats:
            raise ValueError(f"Duplicate selected stats match_ref {match_ref}")
        stats[match_ref] = data
    return stats


def _load_matches_for_report(
    *,
    base_dir: Path,
    report: CachedCorpusAuditReport,
) -> tuple[ResearchMatch, ...]:
    loader = TheStatsAPICorpusLoader(base_dir)
    fixtures = loader.load_fixtures(report.fixture_files)
    stats = _stats_map_from_report(base_dir=base_dir, report=report)
    source = TheStatsAPIDataSource(
        fixtures=fixtures,
        stats_by_match_ref=stats,
    )
    matches = tuple(source.get_matches())
    if len(matches) != report.normalized_match_count:
        raise ValueError(
            f"Normalized match count drift for {report.label}: "
            f"{len(matches)} != {report.normalized_match_count}"
        )
    return matches


def _unique_source_bundle(
    reports: tuple[CachedCorpusAuditReport, ...],
) -> tuple[int, str]:
    seen: dict[str, dict[str, Any]] = {}
    for report in reports:
        for row in report.source_files:
            current = row.to_dict()
            prior = seen.get(row.relative_path)
            if prior is not None and prior != current:
                raise ValueError(
                    f"Inconsistent source fingerprint for {row.relative_path}"
                )
            seen[row.relative_path] = current
    ordered = [seen[name] for name in sorted(seen)]
    return len(ordered), sha256_json(ordered)


def build_multiseason_pit_corpus(
    *,
    base_dir: Path,
    pit_spec: PITDatasetSpec,
) -> MultiSeasonPITCorpus:
    """Compose every audit-usable canonical season into one PIT corpus.

    The function reruns the Foundation season audit against current cached bytes,
    then loads exactly the source files selected by each accepted report.
    """
    base = Path(base_dir)
    discovery = discover_cached_seasons(base)
    if not discovery:
        raise ValueError(f"No canonical cached seasons discovered under {base}")

    reports: list[CachedCorpusAuditReport] = []
    all_matches: list[ResearchMatch] = []

    for season in discovery:
        if not season.usable_for_audit:
            raise ValueError(
                f"Discovered season is not audit-usable: {season.fixture_file} "
                f"{season.blocking_anomalies}"
            )
        report = audit_cached_corpus(
            base_dir=base,
            corpus_spec=season.to_spec(),
            pit_spec=pit_spec,
        )
        if not report.audit_usable:
            raise ValueError(
                f"Canonical season audit blocked: {report.label} "
                f"{report.blocking_anomalies}"
            )
        reports.append(report)
        all_matches.extend(_load_matches_for_report(base_dir=base, report=report))

    fixture_keys = [match.stable_fixture_key for match in all_matches]
    if any(key is None for key in fixture_keys):
        raise ValueError("Multi-season corpus contains unstable fixture identity")
    if len(fixture_keys) != len(set(fixture_keys)):
        raise ValueError("Duplicate fixture identity across canonical seasons")

    ordered = tuple(
        sorted(
            all_matches,
            key=lambda match: (
                match.date_unix,
                match.stable_fixture_key or "",
            ),
        )
    )

    pit = PITDatasetBuilder(spec=pit_spec).build(ordered)
    source_count, source_bundle_hash = _unique_source_bundle(tuple(reports))
    competition_refs = tuple(
        sorted({match.competition_ref for match in ordered if match.competition_ref})
    )
    season_refs = tuple(
        sorted({match.season_ref for match in ordered if match.season_ref})
    )
    kickoffs = [match.date_unix for match in ordered]

    match_content_hash = sha256_json(
        [match.to_dict() for match in ordered]
    )
    season_hashes = tuple(
        sorted((report.label, report.report_hash) for report in reports)
    )

    manifest = MultiSeasonCorpusManifest(
        version=MULTISEASON_CORPUS_VERSION,
        source_root_id=reports[0].source_root_id,
        season_audit_hashes=season_hashes,
        unique_source_files=source_count,
        unique_source_bundle_hash=source_bundle_hash,
        competition_refs=competition_refs,
        season_refs=season_refs,
        n_matches=len(ordered),
        first_kickoff_ts=min(kickoffs) if kickoffs else None,
        last_kickoff_ts=max(kickoffs) if kickoffs else None,
        match_content_hash=match_content_hash,
        pit_manifest_hash=pit.manifest.manifest_hash,
        decision_horizon_seconds=pit_spec.decision_horizon_seconds,
    )
    return MultiSeasonPITCorpus(
        manifest=manifest,
        matches=ordered,
        pit=pit,
        season_reports=tuple(reports),
    )
