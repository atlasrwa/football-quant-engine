"""Append-only research ledger for SHADOW_RESIDUAL candidates + evaluations.

Two strictly append-only newline-delimited JSON ledgers, mirroring the
provenance discipline of :class:`src.research.prospective.storage.CaptureStore`:

- shadow candidates      (``shadow_residuals.jsonl``)
- movement evaluations   (``shadow_evaluations.jsonl``)

Immutability rules (mission sections 9, 10):
- A candidate is appended once; earlier lines are NEVER rewritten. Idempotency
  is enforced on ``shadow_id`` so re-running against unchanged state does not
  duplicate a candidate.
- Later market movement produces a SEPARATE evaluation record (idempotent on
  ``evaluation_id``) that references the frozen candidate by
  ``shadow_id`` / ``shadow_payload_hash``. The candidate is never mutated.

These ledgers are research-critical runtime data and live under
``data/prospective/`` which is git-ignored (see data/prospective/.gitignore);
they must never be committed or staged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Optional

from src.research.prospective.shadow_residual import (
    ShadowMovementEvaluation,
    ShadowResidualRecord,
)

#: Default ledger locations (git-ignored research data dir).
DEFAULT_SHADOW_ROOT = Path("data/prospective")
SHADOW_CANDIDATES_FILE = "shadow_residuals.jsonl"
SHADOW_EVALUATIONS_FILE = "shadow_evaluations.jsonl"


def _open_append(path: Path):
    return open(path, "a", encoding="utf-8")


def _open_read(path: Path):
    return open(path, "r", encoding="utf-8")


@dataclass
class ShadowResidualStore:
    """Append-only, idempotent store for shadow candidates.

    Attributes:
        path: JSONL file candidates are appended to.
    """

    path: Path
    _seen_ids: set = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen_ids = set()
        for rec in self.read_all_dicts():
            sid = rec.get("shadow_id")
            if sid:
                self._seen_ids.add(sid)

    def contains(self, shadow_id: str) -> bool:
        return shadow_id in self._seen_ids

    def append(self, record: ShadowResidualRecord) -> bool:
        """Append a finalized candidate. Returns False if already present.

        Never overwrites or mutates an earlier line.
        """
        if not record.shadow_id or not record.shadow_payload_hash:
            raise ValueError("refusing to persist a non-finalized shadow record")
        if record.shadow_id in self._seen_ids:
            return False
        with _open_append(self.path) as fh:
            fh.write(json.dumps(record.to_dict(), separators=(",", ":")) + "\n")
        self._seen_ids.add(record.shadow_id)
        return True

    def extend(self, records: Iterable[ShadowResidualRecord]) -> int:
        return sum(1 for r in records if self.append(r))

    def read_all_dicts(self) -> Iterator[dict]:
        if not self.path.exists():
            return
        with _open_read(self.path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)

    def count(self) -> int:
        return sum(1 for _ in self.read_all_dicts())

    def count_by_provenance(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for d in self.read_all_dicts():
            k = d.get("provenance_kind", "UNKNOWN")
            out[k] = out.get(k, 0) + 1
        return out


@dataclass
class ShadowEvaluationStore:
    """Append-only, idempotent store for movement evaluations."""

    path: Path
    _seen_ids: set = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen_ids = set()
        for rec in self.read_all_dicts():
            eid = rec.get("evaluation_id")
            if eid:
                self._seen_ids.add(eid)

    def contains(self, evaluation_id: str) -> bool:
        return evaluation_id in self._seen_ids

    def append(self, record: ShadowMovementEvaluation) -> bool:
        if not record.evaluation_id:
            raise ValueError("refusing to persist a non-finalized evaluation record")
        if record.evaluation_id in self._seen_ids:
            return False
        with _open_append(self.path) as fh:
            fh.write(json.dumps(record.to_dict(), separators=(",", ":")) + "\n")
        self._seen_ids.add(record.evaluation_id)
        return True

    def extend(self, records: Iterable[ShadowMovementEvaluation]) -> int:
        return sum(1 for r in records if self.append(r))

    def read_all_dicts(self) -> Iterator[dict]:
        if not self.path.exists():
            return
        with _open_read(self.path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)

    def count(self) -> int:
        return sum(1 for _ in self.read_all_dicts())


def default_candidate_store(root: Path = DEFAULT_SHADOW_ROOT) -> ShadowResidualStore:
    return ShadowResidualStore(path=Path(root) / SHADOW_CANDIDATES_FILE)


def default_evaluation_store(root: Path = DEFAULT_SHADOW_ROOT) -> ShadowEvaluationStore:
    return ShadowEvaluationStore(path=Path(root) / SHADOW_EVALUATIONS_FILE)
