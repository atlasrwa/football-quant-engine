"""Append-only persistence for prospective captures.

Captures are written as newline-delimited JSON (optionally gzip-compressed).
The store is strictly append-only: a new capture is appended; earlier lines
are never rewritten. Idempotency is enforced on the observation id derived
from the composed :class:`ProviderObservation`, so re-running a collector does
not duplicate a snapshot that was already recorded at the same ``observed_at``.

Large prospective capture directories are research-critical raw data and are
git-ignored (see research/evaluation/.gitignore and the capture root's own
.gitignore); only small schemas / example artifacts are committed.
"""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

from src.research.observation.store import ObservationStore
from src.research.prospective.capture import CaptureRecord


def _open_append(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "at", encoding="utf-8")
    return open(path, "a", encoding="utf-8")


def _open_read(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8")
    return open(path, "r", encoding="utf-8")


@dataclass
class CaptureStore:
    """Append-only file-backed capture store.

    Attributes:
        path: JSONL (or .jsonl.gz) file the captures are appended to.
    """

    path: Path
    _seen_ids: set = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen_ids = set()
        # Prime the idempotency set from any existing content.
        for rec in self.read_all():
            self._seen_ids.add(rec.to_observation().observation_id)

    def append(self, record: CaptureRecord) -> bool:
        """Append a capture. Returns False if already present (idempotent).

        Never overwrites or mutates an earlier line.
        """
        obs_id = record.to_observation().observation_id
        if obs_id in self._seen_ids:
            return False
        with _open_append(self.path) as fh:
            fh.write(json.dumps(record.to_dict(), separators=(",", ":")) + "\n")
        self._seen_ids.add(obs_id)
        return True

    def extend(self, records: Iterable[CaptureRecord]) -> int:
        return sum(1 for r in records if self.append(r))

    def read_all(self) -> Iterator[CaptureRecord]:
        """Yield captures from disk (empty if the file does not exist yet)."""
        if not self.path.exists():
            return
        with _open_read(self.path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                yield _record_from_dict(d)

    def to_observation_store(self, store: Optional[ObservationStore] = None) -> ObservationStore:
        """Replay all captures into an ObservationStore for PIT queries."""
        store = store or ObservationStore()
        for rec in self.read_all():
            store.append(rec.to_observation())
        return store


def _record_from_dict(d: dict) -> CaptureRecord:
    from src.research.observation.model import MISSING

    value = d.get("value")
    if value == "MISSING":
        value = MISSING
    return CaptureRecord(
        provider=d["provider"],
        provider_entity_id=d["provider_entity_id"],
        canonical_entity_id=d["canonical_entity_id"],
        concept=d["concept"],
        value=value,
        observed_at=d["observed_at"],
        retrieved_at=d["retrieved_at"],
        raw_payload_hash=d["raw_payload_hash"],
        raw_status=d.get("raw_status", "PROSPECTIVE_SNAPSHOT"),
        event_time=d.get("event_time"),
        forecast_cutoff=d.get("forecast_cutoff"),
        vintage=d.get("vintage"),
    )
