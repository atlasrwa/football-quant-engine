"""Append-only research ledger for SHADOW_SETTLEMENT records.

Mirrors the provenance discipline of
:class:`src.research.prospective.shadow_store.ShadowResidualStore`:

- A settlement is appended once; earlier lines are NEVER rewritten.
- Idempotency is enforced on ``settlement_id`` so re-running against the same
  final result does not duplicate a settlement.
- A later provider *correction* that changes the graded statistic produces a
  DIFFERENT ``settlement_id`` and is appended as a new record — the earlier one
  is never overwritten (immutable-ledger convention).

This ledger is downstream of the shadow/evaluation ledgers and NEVER mutates
them. It lives under ``data/prospective/`` which is git-ignored.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from src.research.prospective.shadow_settlement import ShadowSettlementRecord

DEFAULT_SHADOW_ROOT = Path("data/prospective")
SHADOW_SETTLEMENTS_FILE = "shadow_settlements.jsonl"


@dataclass
class ShadowSettlementStore:
    """Append-only, idempotent store for shadow settlements."""

    path: Path
    _seen_ids: set = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.path = Path(self.path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen_ids = set()
        for rec in self.read_all_dicts():
            sid = rec.get("settlement_id")
            if sid:
                self._seen_ids.add(sid)

    def contains(self, settlement_id: str) -> bool:
        return settlement_id in self._seen_ids

    def append(self, record: ShadowSettlementRecord) -> bool:
        """Append a finalized settlement. Returns False if already present."""
        if not record.settlement_id:
            raise ValueError("refusing to persist a non-finalized settlement record")
        if record.settlement_id in self._seen_ids:
            return False
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), separators=(",", ":")) + "\n")
        self._seen_ids.add(record.settlement_id)
        return True

    def extend(self, records: Iterable[ShadowSettlementRecord]) -> int:
        return sum(1 for r in records if self.append(r))

    def read_all_dicts(self) -> Iterator[dict]:
        if not self.path.exists():
            return
        with open(self.path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)

    def settled_shadow_ids(self) -> set:
        """Shadow ids that already have at least one settlement (for skipping)."""
        return {d.get("shadow_id") for d in self.read_all_dicts() if d.get("shadow_id")}

    def count(self) -> int:
        return sum(1 for _ in self.read_all_dicts())


def default_settlement_store(root: Path = DEFAULT_SHADOW_ROOT) -> ShadowSettlementStore:
    return ShadowSettlementStore(path=Path(root) / SHADOW_SETTLEMENTS_FILE)
