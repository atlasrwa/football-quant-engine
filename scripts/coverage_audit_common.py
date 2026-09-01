"""
Coverage Matrix Audit — shared helpers (audit-only).

Idempotent JSON artifact read/write under data/coverage_audit/, a rate helper
with a meaningful-confidence threshold, and budget before/after snapshots that
read the TheStatsAPI client's budget state. Imports the existing client but does
NOT modify it or any engine/src module.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

ARTIFACT_DIR = "/home/ubuntu/data/coverage_audit"

# A rate computed from fewer than this many fixtures/records is low-confidence.
LOW_CONFIDENCE_N = 20


def artifact_dir() -> str:
    os.makedirs(ARTIFACT_DIR, exist_ok=True)
    return ARTIFACT_DIR


def artifact_path(name: str) -> str:
    return f"{artifact_dir()}/{name}"


def read_artifact(name: str):
    path = artifact_path(name)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def write_artifact(name: str, obj) -> str:
    path = artifact_path(name)
    with open(path, "w") as f:
        json.dump(obj, f, indent=2, default=str)
    return path


def rate(present: int, total: int) -> dict:
    pct = round(100.0 * present / total, 1) if total else None
    return {"present": present, "total": total, "pct": pct,
            "low_confidence": total < LOW_CONFIDENCE_N}


def budget_snapshot_raw() -> dict:
    try:
        import thestatsapi_client as api
        return api.budget_snapshot()
    except Exception as e:
        return {"error": str(e)}


def snapshot_budget(label: str) -> dict:
    snap = budget_snapshot_raw()
    snap["_label"] = label
    snap["_recorded_at"] = datetime.now(timezone.utc).isoformat()
    existing = read_artifact("budget.json") or {"snapshots": []}
    existing.setdefault("snapshots", []).append(snap)

    def _rem(s):
        try:
            return int(s.get("last_monthly_remaining"))
        except (TypeError, ValueError):
            return None

    snaps = existing["snapshots"]
    first_rem, last_rem = _rem(snaps[0]), _rem(snaps[-1])
    if first_rem is not None and last_rem is not None:
        existing["monthly_remaining_delta"] = first_rem - last_rem
        existing["monthly_remaining_first"] = first_rem
        existing["monthly_remaining_last"] = last_rem
    write_artifact("budget.json", existing)
    return snap


if __name__ == "__main__":
    print(json.dumps(snapshot_budget("manual"), indent=2))
