"""Frozen chronological evaluation protocol for QFE V2 Layer 3.

The split is calendar-based, not random:

- WARMUP: before 2024-08-01 UTC. State may be updated; rows are not scored.
- DEVELOPMENT: 2024-08-01 <= kickoff < 2026-02-01 UTC.
- CALIBRATION: 2026-02-01 <= kickoff < 2026-08-01 UTC.
- PROTECTED: kickoff >= 2026-08-01 UTC.

Candidate model/distribution/hyperparameter selection may use DEVELOPMENT only.
CALIBRATION is reserved for ensemble/calibration fitting after candidates are
frozen. PROTECTED is not available to selection or calibration code and may be
scored only after the complete standalone probability stack is frozen.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable

from src.research.data_source import ResearchMatch
from src.research.dataset.manifest import sha256_json


CHRONOLOGY_VERSION = "qfe-chronology-v1"


class EvaluationPartition(str, Enum):
    WARMUP = "WARMUP"
    DEVELOPMENT = "DEVELOPMENT"
    CALIBRATION = "CALIBRATION"
    PROTECTED = "PROTECTED"


def _utc_ts(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


WARMUP_END_TS = _utc_ts(2024, 8, 1)
DEVELOPMENT_END_TS = _utc_ts(2026, 2, 1)
CALIBRATION_END_TS = _utc_ts(2026, 8, 1)


@dataclass(frozen=True, slots=True)
class PartitionManifest:
    partition: EvaluationPartition
    n_fixtures: int
    first_kickoff_ts: int | None
    last_kickoff_ts: int | None
    competition_counts: dict[str, int]
    fixture_keys: tuple[str, ...]
    fixture_membership_hash: str

    def to_dict(self, *, include_fixture_keys: bool = True) -> dict[str, Any]:
        out: dict[str, Any] = {
            "partition": self.partition.value,
            "n_fixtures": self.n_fixtures,
            "first_kickoff_ts": self.first_kickoff_ts,
            "last_kickoff_ts": self.last_kickoff_ts,
            "competition_counts": dict(sorted(self.competition_counts.items())),
            "fixture_membership_hash": self.fixture_membership_hash,
        }
        if include_fixture_keys:
            out["fixture_keys"] = list(self.fixture_keys)
        return out


@dataclass(frozen=True, slots=True)
class ChronologyManifest:
    version: str
    warmup_end_ts: int
    development_end_ts: int
    calibration_end_ts: int
    corpus_manifest_hash: str
    partitions: tuple[PartitionManifest, ...]

    def partition(self, name: EvaluationPartition) -> PartitionManifest:
        for partition in self.partitions:
            if partition.partition == name:
                return partition
        raise KeyError(name)

    def to_dict(self, *, include_fixture_keys: bool = True) -> dict[str, Any]:
        return {
            "version": self.version,
            "warmup_end_ts": self.warmup_end_ts,
            "development_end_ts": self.development_end_ts,
            "calibration_end_ts": self.calibration_end_ts,
            "corpus_manifest_hash": self.corpus_manifest_hash,
            "partitions": [
                partition.to_dict(include_fixture_keys=include_fixture_keys)
                for partition in self.partitions
            ],
        }

    @property
    def manifest_hash(self) -> str:
        return sha256_json(self.to_dict(include_fixture_keys=True))


def partition_for_kickoff(kickoff_ts: int) -> EvaluationPartition:
    if kickoff_ts < WARMUP_END_TS:
        return EvaluationPartition.WARMUP
    if kickoff_ts < DEVELOPMENT_END_TS:
        return EvaluationPartition.DEVELOPMENT
    if kickoff_ts < CALIBRATION_END_TS:
        return EvaluationPartition.CALIBRATION
    return EvaluationPartition.PROTECTED


def build_chronology_manifest(
    *,
    matches: Iterable[ResearchMatch],
    corpus_manifest_hash: str,
) -> ChronologyManifest:
    grouped: dict[EvaluationPartition, list[ResearchMatch]] = {
        partition: [] for partition in EvaluationPartition
    }
    seen: set[str] = set()

    for match in sorted(
        matches,
        key=lambda item: (
            item.date_unix,
            item.stable_fixture_key or "",
        ),
    ):
        key = match.stable_fixture_key
        if not key:
            raise ValueError("stable fixture identity required for chronology")
        if key in seen:
            raise ValueError(f"duplicate fixture identity {key}")
        seen.add(key)
        grouped[partition_for_kickoff(match.date_unix)].append(match)

    manifests: list[PartitionManifest] = []
    for partition in EvaluationPartition:
        rows = grouped[partition]
        keys = tuple(match.stable_fixture_key or "" for match in rows)
        competition_counts: dict[str, int] = {}
        for match in rows:
            ref = match.competition_ref or "<missing>"
            competition_counts[ref] = competition_counts.get(ref, 0) + 1

        membership_payload = [
            {
                "fixture_key": match.stable_fixture_key,
                "kickoff_ts": match.date_unix,
                "competition_ref": match.competition_ref,
                "season_ref": match.season_ref,
            }
            for match in rows
        ]
        manifests.append(
            PartitionManifest(
                partition=partition,
                n_fixtures=len(rows),
                first_kickoff_ts=rows[0].date_unix if rows else None,
                last_kickoff_ts=rows[-1].date_unix if rows else None,
                competition_counts=dict(sorted(competition_counts.items())),
                fixture_keys=keys,
                fixture_membership_hash=sha256_json(membership_payload),
            )
        )

    return ChronologyManifest(
        version=CHRONOLOGY_VERSION,
        warmup_end_ts=WARMUP_END_TS,
        development_end_ts=DEVELOPMENT_END_TS,
        calibration_end_ts=CALIBRATION_END_TS,
        corpus_manifest_hash=corpus_manifest_hash,
        partitions=tuple(manifests),
    )


def assert_selection_partition_allowed(
    partition: EvaluationPartition,
) -> None:
    """Guard candidate/hyperparameter selection from calibration/protected data."""
    if partition != EvaluationPartition.DEVELOPMENT:
        raise PermissionError(
            f"candidate selection may use DEVELOPMENT only, not {partition.value}"
        )


def assert_calibration_partition_allowed(
    partition: EvaluationPartition,
) -> None:
    """Guard calibration fitting from development/protected data."""
    if partition != EvaluationPartition.CALIBRATION:
        raise PermissionError(
            f"calibration fitting may use CALIBRATION only, not {partition.value}"
        )


def write_chronology_manifest(path, manifest: ChronologyManifest) -> None:
    """Write canonical immutable chronology evidence."""
    from pathlib import Path
    from src.research.dataset.manifest import canonical_json

    output = Path(path)
    payload = canonical_json(manifest.to_dict(include_fixture_keys=True)) + "\n"
    if output.exists():
        if output.read_text() != payload:
            raise FileExistsError(
                f"chronology manifest already exists with different content: {output}"
            )
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload)
