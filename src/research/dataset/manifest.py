"""Deterministic manifests and immutable artifact I/O for QFE V2 datasets."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_rows_jsonl(rows: Iterable[dict[str, Any]]) -> bytes:
    return "".join(canonical_json(row) + "\n" for row in rows).encode("utf-8")


def rows_digest(rows: Iterable[dict[str, Any]]) -> str:
    """Order-sensitive chain digest over canonical row dictionaries."""
    digest = hashlib.sha256(b"qfe-pit-rows-v1").digest()
    for row in rows:
        payload = canonical_json(row).encode("utf-8")
        digest = hashlib.sha256(digest + b"\n" + payload).digest()
    return digest.hex()


@dataclass(frozen=True, slots=True)
class PITDatasetManifest:
    schema_version: str
    provider: str
    provider_registry_version: str
    provider_contract_source_url: str
    provider_contract_source_sha256: str
    provider_contract_verified_on: str
    target_registry_version: str
    decision_horizon_seconds: int
    historical_availability_policy: str
    reconstructed_post_match_embargo_seconds: int
    exclude_extra_time_history: bool
    n_input_matches: int
    n_rows: int
    n_feature_fields: int
    first_cutoff_ts: float | None
    last_cutoff_ts: float | None
    source_data_hash: str
    rows_hash: str
    rows_file_sha256: str
    feature_schema_hash: str
    target_status_counts: dict[str, dict[str, int]]
    excluded_history_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "provider_registry_version": self.provider_registry_version,
            "provider_contract_source_url": self.provider_contract_source_url,
            "provider_contract_source_sha256": self.provider_contract_source_sha256,
            "provider_contract_verified_on": self.provider_contract_verified_on,
            "target_registry_version": self.target_registry_version,
            "decision_horizon_seconds": self.decision_horizon_seconds,
            "historical_availability_policy": self.historical_availability_policy,
            "reconstructed_post_match_embargo_seconds": self.reconstructed_post_match_embargo_seconds,
            "exclude_extra_time_history": self.exclude_extra_time_history,
            "n_input_matches": self.n_input_matches,
            "n_rows": self.n_rows,
            "n_feature_fields": self.n_feature_fields,
            "first_cutoff_ts": self.first_cutoff_ts,
            "last_cutoff_ts": self.last_cutoff_ts,
            "source_data_hash": self.source_data_hash,
            "rows_hash": self.rows_hash,
            "rows_file_sha256": self.rows_file_sha256,
            "feature_schema_hash": self.feature_schema_hash,
            "target_status_counts": self.target_status_counts,
            "excluded_history_counts": self.excluded_history_counts,
        }

    @property
    def manifest_hash(self) -> str:
        return sha256_json(self.to_dict())


@dataclass(frozen=True, slots=True)
class ArtifactWriteResult:
    path: Path
    manifest_hash: str
    already_existed: bool


def _read_verified_existing(
    artifact_dir: Path,
    manifest: PITDatasetManifest,
) -> ArtifactWriteResult:
    verified = verify_immutable_dataset(artifact_dir)
    if verified.manifest_hash != manifest.manifest_hash:
        raise FileExistsError(
            f"Existing artifact at {artifact_dir} has a different manifest"
        )
    return ArtifactWriteResult(
        path=artifact_dir,
        manifest_hash=manifest.manifest_hash,
        already_existed=True,
    )


def _fsync_file(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_immutable_dataset(
    *,
    root: Path,
    manifest: PITDatasetManifest,
    rows: Iterable[dict[str, Any]],
) -> ArtifactWriteResult:
    """Atomically publish a content-addressed immutable dataset artifact.

    The complete artifact is written and fsynced in a temporary directory on
    the same filesystem, verified, and then atomically renamed into its final
    manifest-hash path. A crash before rename cannot expose a partial final
    artifact. Re-running an identical artifact is idempotent.
    """
    row_list = list(rows)
    expected_rows_hash = rows_digest(row_list)
    rows_payload = canonical_rows_jsonl(row_list)
    if expected_rows_hash != manifest.rows_hash:
        raise ValueError("rows_hash does not match manifest")
    if sha256_bytes(rows_payload) != manifest.rows_file_sha256:
        raise ValueError("rows_file_sha256 does not match manifest")

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    artifact_dir = root / manifest.manifest_hash
    if artifact_dir.exists():
        return _read_verified_existing(artifact_dir, manifest)

    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{manifest.manifest_hash}.staging-",
            dir=root,
        )
    )
    published = False
    try:
        manifest_payload = (
            canonical_json(manifest.to_dict()) + "\n"
        ).encode("utf-8")
        _fsync_file(staging / "manifest.json", manifest_payload)
        _fsync_file(staging / "rows.jsonl", rows_payload)
        _fsync_directory(staging)

        # Validate staged bytes before making them visible at the final path.
        staged_manifest = json.loads((staging / "manifest.json").read_text())
        if sha256_json(staged_manifest) != manifest.manifest_hash:
            raise ValueError("Staged manifest hash mismatch")
        if sha256_bytes((staging / "rows.jsonl").read_bytes()) != manifest.rows_file_sha256:
            raise ValueError("Staged rows byte hash mismatch")

        try:
            os.rename(staging, artifact_dir)
            published = True
            _fsync_directory(root)
        except OSError:
            # A concurrent identical publisher may have won the race. Never
            # replace an existing final directory; verify it instead.
            if artifact_dir.exists():
                return _read_verified_existing(artifact_dir, manifest)
            raise

        return ArtifactWriteResult(
            path=artifact_dir,
            manifest_hash=manifest.manifest_hash,
            already_existed=False,
        )
    finally:
        if not published and staging.exists():
            shutil.rmtree(staging)


def verify_immutable_dataset(path: Path) -> PITDatasetManifest:
    """Byte- and semantic-verify a persisted content-addressed artifact."""
    path = Path(path)
    expected_names = {"manifest.json", "rows.jsonl"}
    actual_names = {child.name for child in path.iterdir()}
    if actual_names != expected_names:
        raise ValueError(
            f"Artifact file set mismatch: expected {sorted(expected_names)}, "
            f"got {sorted(actual_names)}"
        )

    manifest_path = path / "manifest.json"
    rows_path = path / "rows.jsonl"
    manifest_raw_text = manifest_path.read_text()
    manifest_raw = json.loads(manifest_raw_text)
    manifest = PITDatasetManifest(**manifest_raw)

    if path.name != manifest.manifest_hash:
        raise ValueError("Artifact directory name does not match manifest hash")
    expected_manifest_bytes = (
        canonical_json(manifest.to_dict()) + "\n"
    ).encode("utf-8")
    if manifest_path.read_bytes() != expected_manifest_bytes:
        raise ValueError("Persisted manifest is not canonical byte representation")

    rows_payload = rows_path.read_bytes()
    if sha256_bytes(rows_payload) != manifest.rows_file_sha256:
        raise ValueError("Persisted rows byte hash mismatch")
    rows = [
        json.loads(line)
        for line in rows_payload.decode("utf-8").splitlines()
        if line.strip()
    ]
    if rows_digest(rows) != manifest.rows_hash:
        raise ValueError("Persisted rows semantic hash mismatch")
    if canonical_rows_jsonl(rows) != rows_payload:
        raise ValueError("Persisted rows are not canonical JSONL representation")
    if len(rows) != manifest.n_rows:
        raise ValueError("Persisted row count mismatch")
    return manifest
