"""Frozen V3 pilot contract loader."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FREEZE = ROOT / "research/v3_live_pilot/V3_FREEZE_V1.json"
EXPECTED_CONTRACT_SHA256 = "452daf38d7797a7f0cb530ee9882e87b02b002ccac19f330eb4733b252275aff"

class FreezeIntegrityError(RuntimeError):
    pass

def _canonical_contract(obj: dict[str, Any]) -> bytes:
    payload = {k: v for k, v in obj.items() if k != "freeze_sha256"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

def load_freeze(path: Path = DEFAULT_FREEZE) -> dict[str, Any]:
    obj = json.loads(Path(path).read_text(encoding="utf-8"))
    observed = hashlib.sha256(_canonical_contract(obj)).hexdigest()
    declared = str(obj.get("freeze_sha256") or "")
    if observed != declared or observed != EXPECTED_CONTRACT_SHA256:
        raise FreezeIntegrityError(
            f"V3 freeze mismatch: expected {EXPECTED_CONTRACT_SHA256}, "
            f"declared {declared}, observed {observed}"
        )
    return obj

def freeze_hash(path: Path = DEFAULT_FREEZE) -> str:
    load_freeze(path)
    return EXPECTED_CONTRACT_SHA256
