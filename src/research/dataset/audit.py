"""Read-only cached-corpus audit for QFE V2.

The audit is descriptive, deterministic and network-free. A season audit binds
one canonical fixture file to the canonical stats-file family implied by that
fixture filename, then fingerprints only stats payloads whose match ids are
actually present in that season. Unrelated cache files therefore cannot change
a frozen season report.

Duplicate/conflicting stats are never silently resolved. Identical aliases are
reported and one lexicographically stable file is selected; conflicting
payloads are excluded from the stats map and surfaced as blocking anomalies.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from src.research.contracts.provider import (
    CapabilityAudit,
    ProviderCapabilityRegistry,
    THESTATSAPI_CAPABILITIES_V1,
)
from src.research.contracts.target import TARGET_REGISTRY_V1, TargetRegistry
from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.dataset.pit import PITDatasetArtifact, PITDatasetBuilder, PITDatasetSpec
from src.research.thestatsapi.adapter import TheStatsAPIDataSource
from src.research.thestatsapi.corpus_loader import TheStatsAPICorpusLoader
from src.research.thestatsapi.normalizer import TheStatsAPINormalizer


AUDIT_VERSION = "qfe-cached-corpus-audit-v2"


@dataclass(frozen=True, slots=True)
class SourceFileFingerprint:
    relative_path: str
    size_bytes: int
    sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "relative_path": self.relative_path,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class CachedCorpusSpec:
    label: str
    fixture_files: tuple[str, ...]
    stats_globs: tuple[str, ...]
    source_root_id: str = "cache://thestatsapi/championship"

    def __post_init__(self) -> None:
        if not self.label:
            raise ValueError("Corpus label cannot be empty")
        if not self.fixture_files:
            raise ValueError("At least one fixture file is required")
        if not self.stats_globs:
            raise ValueError("At least one stats glob is required")
        if self.source_root_id.startswith("/"):
            raise ValueError("source_root_id must be machine-independent")


@dataclass(frozen=True, slots=True)
class CachedSeasonDiscovery:
    fixture_file: str
    label: str
    competition_refs: tuple[str, ...]
    season_refs: tuple[str, ...]
    stats_glob: str
    raw_fixture_count: int
    finished_fixture_count: int
    usable_for_audit: bool
    blocking_anomalies: tuple[str, ...]

    def to_spec(self) -> CachedCorpusSpec:
        if not self.usable_for_audit:
            raise ValueError(f"Season {self.fixture_file} is not audit-usable")
        return CachedCorpusSpec(
            label=self.label,
            fixture_files=(self.fixture_file,),
            stats_globs=(self.stats_glob,),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture_file": self.fixture_file,
            "label": self.label,
            "competition_refs": list(self.competition_refs),
            "season_refs": list(self.season_refs),
            "stats_glob": self.stats_glob,
            "raw_fixture_count": self.raw_fixture_count,
            "finished_fixture_count": self.finished_fixture_count,
            "usable_for_audit": self.usable_for_audit,
            "blocking_anomalies": list(self.blocking_anomalies),
        }


@dataclass(frozen=True, slots=True)
class GlobalStatsAliasAudit:
    indexed_files: int
    indexed_match_refs: int
    identical_duplicate_refs: tuple[str, ...]
    conflicting_duplicate_refs: tuple[str, ...]
    identical_duplicate_files: dict[str, tuple[str, ...]]
    conflicting_duplicate_files: dict[str, tuple[str, ...]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "indexed_files": self.indexed_files,
            "indexed_match_refs": self.indexed_match_refs,
            "identical_duplicate_refs": list(self.identical_duplicate_refs),
            "conflicting_duplicate_refs": list(self.conflicting_duplicate_refs),
            "identical_duplicate_files": {
                key: list(value)
                for key, value in sorted(self.identical_duplicate_files.items())
            },
            "conflicting_duplicate_files": {
                key: list(value)
                for key, value in sorted(self.conflicting_duplicate_files.items())
            },
        }


@dataclass(frozen=True, slots=True)
class HistorySupportReport:
    thresholds: dict[str, int]
    fractions: dict[str, float]
    min_support: int
    median_support: float
    max_support: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "thresholds": self.thresholds,
            "fractions": self.fractions,
            "min_support": self.min_support,
            "median_support": self.median_support,
            "max_support": self.max_support,
        }


@dataclass(frozen=True, slots=True)
class CachedCorpusAuditReport:
    audit_version: str
    label: str
    source_root_id: str
    source_files: tuple[SourceFileFingerprint, ...]
    source_bundle_hash: str
    fixture_files: tuple[str, ...]
    stats_globs: tuple[str, ...]
    raw_fixture_count: int
    raw_status_counts: dict[str, int]
    duplicate_fixture_refs: tuple[str, ...]
    stats_payloads_selected: int
    stats_joined_to_raw_fixtures: int
    stats_join_rate: float
    stats_missing_match_refs: tuple[str, ...]
    stats_identical_duplicate_refs: tuple[str, ...]
    stats_conflicting_match_refs: tuple[str, ...]
    normalized_match_count: int
    skipped_fixture_count: int
    competition_refs: tuple[str, ...]
    season_refs: tuple[str, ...]
    first_kickoff_ts: int | None
    last_kickoff_ts: int | None
    provider_capability: CapabilityAudit
    pit_manifest_hash: str
    pit_rows: int
    pit_feature_fields: int
    target_status_counts: dict[str, dict[str, int]]
    target_unavailable_match_refs: dict[str, tuple[str, ...]]
    history_support: HistorySupportReport
    extra_time_history_exclusions: int
    audit_usable: bool
    blocking_anomalies: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_version": self.audit_version,
            "label": self.label,
            "source_root_id": self.source_root_id,
            "source_files": [row.to_dict() for row in self.source_files],
            "source_bundle_hash": self.source_bundle_hash,
            "fixture_files": list(self.fixture_files),
            "stats_globs": list(self.stats_globs),
            "raw_fixture_count": self.raw_fixture_count,
            "raw_status_counts": self.raw_status_counts,
            "duplicate_fixture_refs": list(self.duplicate_fixture_refs),
            "stats_payloads_selected": self.stats_payloads_selected,
            "stats_joined_to_raw_fixtures": self.stats_joined_to_raw_fixtures,
            "stats_join_rate": self.stats_join_rate,
            "stats_missing_match_refs": list(self.stats_missing_match_refs),
            "stats_identical_duplicate_refs": list(self.stats_identical_duplicate_refs),
            "stats_conflicting_match_refs": list(self.stats_conflicting_match_refs),
            "normalized_match_count": self.normalized_match_count,
            "skipped_fixture_count": self.skipped_fixture_count,
            "competition_refs": list(self.competition_refs),
            "season_refs": list(self.season_refs),
            "first_kickoff_ts": self.first_kickoff_ts,
            "last_kickoff_ts": self.last_kickoff_ts,
            "provider_capability": self.provider_capability.to_dict(),
            "pit_manifest_hash": self.pit_manifest_hash,
            "pit_rows": self.pit_rows,
            "pit_feature_fields": self.pit_feature_fields,
            "target_status_counts": self.target_status_counts,
            "target_unavailable_match_refs": {
                key: list(value)
                for key, value in self.target_unavailable_match_refs.items()
            },
            "history_support": self.history_support.to_dict(),
            "extra_time_history_exclusions": self.extra_time_history_exclusions,
            "audit_usable": self.audit_usable,
            "blocking_anomalies": list(self.blocking_anomalies),
        }

    @property
    def report_hash(self) -> str:
        return sha256_json(self.to_dict())


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _hash_file(path: Path, *, base: Path) -> SourceFileFingerprint:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return SourceFileFingerprint(
        relative_path=path.relative_to(base).as_posix(),
        size_bytes=path.stat().st_size,
        sha256=digest.hexdigest(),
    )


def _canonical_stats_glob(fixture_filename: str) -> str:
    generic_prefix = "_all_fixtures_sn_"
    if fixture_filename.startswith(generic_prefix) and fixture_filename.endswith(".json"):
        return "stats_mt_*.json"

    prefix = "_all_fixtures_"
    suffix_marker = "_sn_"
    if not fixture_filename.startswith(prefix) or suffix_marker not in fixture_filename:
        raise ValueError(f"Unrecognized canonical fixture filename {fixture_filename!r}")
    body = fixture_filename[len(prefix):].split(suffix_marker, 1)[0]
    if not body:
        raise ValueError(f"Unrecognized canonical fixture filename {fixture_filename!r}")
    return f"{body}_stats_mt_*.json"


def discover_cached_seasons(
    base_dir: Path,
    *,
    fixture_glob: str = "_all_fixtures*.json",
) -> tuple[CachedSeasonDiscovery, ...]:
    base = Path(base_dir)
    out: list[CachedSeasonDiscovery] = []
    for path in sorted(base.glob(fixture_glob)):
        data = _read_json(path)
        anomalies: list[str] = []
        fixtures = data.get("fixtures") if data else None
        if not isinstance(fixtures, list):
            fixtures = []
            anomalies.append("fixture_file_missing_fixtures_list")

        competition_refs = tuple(sorted({
            str(row.get("competition_id"))
            for row in fixtures
            if isinstance(row, dict) and row.get("competition_id")
        }))
        season_refs = tuple(sorted({
            str(row.get("season_id"))
            for row in fixtures
            if isinstance(row, dict) and row.get("season_id")
        }))
        finished = sum(
            str(row.get("status", "")).lower() in {"finished", "complete", "completed"}
            for row in fixtures
            if isinstance(row, dict)
        )
        if len(competition_refs) != 1:
            anomalies.append("fixture_file_not_single_competition")
        if len(season_refs) != 1:
            anomalies.append("fixture_file_not_single_season")
        if not fixtures:
            anomalies.append("fixture_file_empty")
        if finished == 0:
            anomalies.append("no_finished_fixtures")

        try:
            stats_glob = _canonical_stats_glob(path.name)
        except ValueError:
            stats_glob = ""
            anomalies.append("unrecognized_fixture_filename")

        label = (
            f"{competition_refs[0]}:{season_refs[0]}"
            if len(competition_refs) == 1 and len(season_refs) == 1
            else path.stem
        )
        out.append(CachedSeasonDiscovery(
            fixture_file=path.name,
            label=label,
            competition_refs=competition_refs,
            season_refs=season_refs,
            stats_glob=stats_glob,
            raw_fixture_count=len(fixtures),
            finished_fixture_count=finished,
            usable_for_audit=not anomalies,
            blocking_anomalies=tuple(anomalies),
        ))
    return tuple(out)


def inspect_global_stats_aliases(
    base_dir: Path,
    *,
    stats_glob: str = "*stats_mt_*.json",
) -> GlobalStatsAliasAudit:
    base = Path(base_dir)
    index: dict[str, list[tuple[str, str]]] = defaultdict(list)
    files = sorted(base.glob(stats_glob))
    for path in files:
        data = _read_json(path)
        match_ref = ((data or {}).get("data") or {}).get("match_id")
        if not isinstance(match_ref, str) or not match_ref:
            continue
        index[match_ref].append((path.name, sha256_json(data)))

    identical: list[str] = []
    conflicting: list[str] = []
    identical_files: dict[str, tuple[str, ...]] = {}
    conflicting_files: dict[str, tuple[str, ...]] = {}
    for match_ref, candidates in index.items():
        if len(candidates) <= 1:
            continue
        hashes = {digest for _, digest in candidates}
        names = tuple(sorted(name for name, _ in candidates))
        if len(hashes) == 1:
            identical.append(match_ref)
            identical_files[match_ref] = names
        else:
            conflicting.append(match_ref)
            conflicting_files[match_ref] = names
    return GlobalStatsAliasAudit(
        indexed_files=len(files),
        indexed_match_refs=len(index),
        identical_duplicate_refs=tuple(sorted(identical)),
        conflicting_duplicate_refs=tuple(sorted(conflicting)),
        identical_duplicate_files=identical_files,
        conflicting_duplicate_files=conflicting_files,
    )


def _select_exact_stats(
    *,
    base: Path,
    globs: Iterable[str],
    raw_refs: set[str],
) -> tuple[
    dict[str, dict[str, Any]],
    tuple[Path, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
]:
    candidates: dict[str, list[tuple[Path, dict[str, Any], str]]] = defaultdict(list)
    for pattern in globs:
        matched = sorted(base.glob(pattern))
        if not matched:
            raise FileNotFoundError(f"Stats glob {pattern!r} matched no files under {base}")
        for path in matched:
            data = _read_json(path)
            match_ref = ((data or {}).get("data") or {}).get("match_id")
            if not isinstance(match_ref, str) or match_ref not in raw_refs:
                continue
            candidates[match_ref].append((path, data, sha256_json(data)))

    selected: dict[str, dict[str, Any]] = {}
    selected_paths: list[Path] = []
    identical: list[str] = []
    conflicting: list[str] = []
    for match_ref in sorted(raw_refs):
        rows = candidates.get(match_ref, [])
        if not rows:
            continue
        distinct_hashes = {digest for _, _, digest in rows}
        if len(distinct_hashes) > 1:
            conflicting.append(match_ref)
            continue
        if len(rows) > 1:
            identical.append(match_ref)
        path, data, _ = sorted(rows, key=lambda item: item[0].name)[0]
        selected[match_ref] = data
        selected_paths.append(path)

    missing = sorted(raw_refs - set(selected) - set(conflicting))
    return (
        selected,
        tuple(sorted(set(selected_paths))),
        tuple(missing),
        tuple(sorted(identical)),
        tuple(sorted(conflicting)),
    )


def _duplicate_refs(fixtures: Iterable[dict[str, Any]]) -> tuple[str, ...]:
    counts = Counter(
        row.get("id")
        for row in fixtures
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    )
    return tuple(sorted(ref for ref, count in counts.items() if count > 1))


def _history_support(artifact: PITDatasetArtifact) -> HistorySupportReport:
    supports = [
        min(
            int(row.features["home_history_matches"] or 0),
            int(row.features["away_history_matches"] or 0),
        )
        for row in artifact.rows
    ]
    if not supports:
        return HistorySupportReport(
            thresholds={str(t): 0 for t in (0, 1, 3, 5, 10, 20)},
            fractions={str(t): 0.0 for t in (0, 1, 3, 5, 10, 20)},
            min_support=0,
            median_support=0.0,
            max_support=0,
        )
    ordered = sorted(supports)
    n = len(ordered)
    median = (
        float(ordered[n // 2])
        if n % 2
        else (ordered[n // 2 - 1] + ordered[n // 2]) / 2.0
    )
    thresholds = {
        str(threshold): sum(value >= threshold for value in supports)
        for threshold in (0, 1, 3, 5, 10, 20)
    }
    return HistorySupportReport(
        thresholds=thresholds,
        fractions={key: count / n for key, count in thresholds.items()},
        min_support=min(ordered),
        median_support=median,
        max_support=max(ordered),
    )


def audit_cached_corpus(
    *,
    base_dir: Path,
    corpus_spec: CachedCorpusSpec,
    pit_spec: PITDatasetSpec,
    provider_registry: ProviderCapabilityRegistry = THESTATSAPI_CAPABILITIES_V1,
    target_registry: TargetRegistry = TARGET_REGISTRY_V1,
) -> CachedCorpusAuditReport:
    """Audit one explicit cached season without network access."""
    base = Path(base_dir)
    loader = TheStatsAPICorpusLoader(base)
    raw_fixtures = loader.load_fixtures(corpus_spec.fixture_files)
    duplicate_fixture_refs = _duplicate_refs(raw_fixtures)
    status_counts = Counter(
        str(fixture.get("status", "")).strip().lower() or "<missing>"
        for fixture in raw_fixtures
    )
    raw_refs = {
        fixture.get("id")
        for fixture in raw_fixtures
        if isinstance(fixture.get("id"), str)
    }
    (
        stats_map,
        selected_stats_paths,
        missing_stats_refs,
        identical_duplicate_refs,
        conflicting_stats_refs,
    ) = _select_exact_stats(
        base=base,
        globs=corpus_spec.stats_globs,
        raw_refs=raw_refs,
    )

    fixture_paths = tuple(base / name for name in corpus_spec.fixture_files)
    for path in fixture_paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    source_paths = tuple(sorted(set(fixture_paths + selected_stats_paths)))
    source_files = tuple(_hash_file(path, base=base) for path in source_paths)

    normalizer = TheStatsAPINormalizer()
    source = TheStatsAPIDataSource(
        fixtures=raw_fixtures,
        stats_by_match_ref=stats_map,
        normalizer=normalizer,
    )
    matches = source.get_matches()
    capability = provider_registry.audit(matches)
    pit = PITDatasetBuilder(
        spec=pit_spec,
        provider_registry=provider_registry,
        target_registry=target_registry,
    ).build(matches)

    competition_refs = tuple(sorted({
        match.competition_ref for match in matches if match.competition_ref
    }))
    season_refs = tuple(sorted({
        match.season_ref for match in matches if match.season_ref
    }))
    kickoffs = [match.date_unix for match in matches]

    target_unavailable: dict[str, tuple[str, ...]] = {}
    for target_id in target_registry.contracts:
        refs = tuple(sorted(
            row.source_match_ref
            for row in pit.rows
            if row.target_status.get(target_id.target_id) != "AVAILABLE"
        ))
        if refs:
            target_unavailable[target_id.target_id] = refs

    blocking: list[str] = []
    if duplicate_fixture_refs:
        blocking.append("duplicate_fixture_refs")
    if conflicting_stats_refs:
        blocking.append("conflicting_stats_payloads")
    if len(competition_refs) != 1:
        blocking.append("normalized_rows_not_single_competition")
    if len(season_refs) != 1:
        blocking.append("normalized_rows_not_single_season")
    if not matches:
        blocking.append("no_normalized_finished_matches")

    return CachedCorpusAuditReport(
        audit_version=AUDIT_VERSION,
        label=corpus_spec.label,
        source_root_id=corpus_spec.source_root_id,
        source_files=source_files,
        source_bundle_hash=sha256_json([
            fingerprint.to_dict() for fingerprint in source_files
        ]),
        fixture_files=corpus_spec.fixture_files,
        stats_globs=corpus_spec.stats_globs,
        raw_fixture_count=len(raw_fixtures),
        raw_status_counts=dict(sorted(status_counts.items())),
        duplicate_fixture_refs=duplicate_fixture_refs,
        stats_payloads_selected=len(stats_map),
        stats_joined_to_raw_fixtures=len(set(raw_refs).intersection(stats_map)),
        stats_join_rate=(len(set(raw_refs).intersection(stats_map)) / len(raw_refs)) if raw_refs else 0.0,
        stats_missing_match_refs=missing_stats_refs,
        stats_identical_duplicate_refs=identical_duplicate_refs,
        stats_conflicting_match_refs=conflicting_stats_refs,
        normalized_match_count=len(matches),
        skipped_fixture_count=normalizer.skipped_count,
        competition_refs=competition_refs,
        season_refs=season_refs,
        first_kickoff_ts=min(kickoffs) if kickoffs else None,
        last_kickoff_ts=max(kickoffs) if kickoffs else None,
        provider_capability=capability,
        pit_manifest_hash=pit.manifest.manifest_hash,
        pit_rows=len(pit.rows),
        pit_feature_fields=pit.manifest.n_feature_fields,
        target_status_counts=pit.manifest.target_status_counts,
        target_unavailable_match_refs=target_unavailable,
        history_support=_history_support(pit),
        extra_time_history_exclusions=pit.manifest.excluded_history_counts.get(
            "extra_time_or_shootout", 0
        ),
        audit_usable=not blocking,
        blocking_anomalies=tuple(blocking),
    )


def write_audit_report(path: Path, report: CachedCorpusAuditReport) -> None:
    """Write canonical audit JSON; refuse to overwrite different evidence."""
    path = Path(path)
    payload = canonical_json(report.to_dict()) + "\n"
    if path.exists():
        if path.read_text() != payload:
            raise FileExistsError(
                f"Audit report {path} already exists with different content"
            )
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload)
