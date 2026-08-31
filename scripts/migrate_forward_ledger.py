#!/usr/bin/env python3
"""One-time migration: convert the legacy data/forward commit/reveal JSONL files
into the tamper-evident hash-chained format used by AttestationLedger.

Why this is NOT backdating:
- Each migrated record keeps its ORIGINAL ``committed_at`` / ``committed_unix``
  as the ``anchor_unix`` attestation timestamp. We do not invent or move any
  timestamp; we only add the chain fields (``prev_hash`` / ``link_hash``) and a
  canonical ``commitment_hash`` binding the prediction content + fixture +
  reference_price(null for the corners/cards loop) + prediction_timestamp.
- Records are processed in their existing on-file order, which is already sorted
  by ``committed_unix`` (verified before writing).

After migration, ``AttestationLedger.verify_chain`` passes and the loop can keep
appending without hitting the tamper guard.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/ubuntu")

from src.research.forward.attestation_ledger import (
    compute_commitment_hash,
    _record_link_hash,
    GENESIS_PREV_HASH,
)

DATA = Path("/home/ubuntu/data/forward")
COMMIT = DATA / "commitments.jsonl"
PRED = DATA / "predictions.jsonl"


def _load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in open(p) if l.strip()]


def migrate() -> None:
    commits = _load_jsonl(COMMIT)
    preds = {p["prediction_id"]: p for p in _load_jsonl(PRED)}
    if not commits:
        print("no commitments to migrate")
        return
    if all("link_hash" in c for c in commits):
        print("already migrated (all records chained)")
        return

    # Preserve on-file order but assert monotonic anchors.
    anchors = [c.get("committed_unix", 0) for c in commits]
    assert anchors == sorted(anchors), "legacy commitments not time-ordered; abort"

    out = []
    prev = GENESIS_PREV_HASH
    for c in commits:
        pid = c["prediction_id"]
        p = preds.get(pid, {})
        pred_ts = p.get("prediction_timestamp", c.get("committed_at"))
        chash = compute_commitment_hash(
            prediction_id=pid,
            fixture_id=c["fixture_id"],
            model=c["model"],
            p_over=p.get("p_over"),
            p_under=p.get("p_under"),
            reference_price=None,  # corners/cards loop logged no odds
            prediction_timestamp=pred_ts,
        )
        rec = {
            "prediction_id": pid,
            "fixture_id": str(c["fixture_id"]),
            "model": c["model"],
            "commitment_hash": chash,
            "reference_price": None,
            "prediction_timestamp": pred_ts,
            "kickoff_timestamp": float(c.get("kickoff_timestamp", 0)),
            # ORIGINAL timestamp preserved as the anchor — no backdating.
            "anchor_unix": float(c["committed_unix"]),
            "committed_at": c["committed_at"],
            "pre_kickoff": bool(c.get("pre_kickoff", True)),
            "prev_hash": prev,
        }
        if c.get("backfilled"):
            rec["backfilled"] = True
        rec["migrated_from_legacy"] = True
        rec["link_hash"] = _record_link_hash(rec)
        out.append(rec)
        prev = rec["link_hash"]

    backup = COMMIT.with_suffix(".jsonl.legacy_bak")
    COMMIT.rename(backup)
    with open(COMMIT, "w") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    print(f"migrated {len(out)} commitments -> chained format")
    print(f"legacy backup: {backup}")


if __name__ == "__main__":
    migrate()
