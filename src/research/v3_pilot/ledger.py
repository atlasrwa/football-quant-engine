"""Append-only bridge into the existing 40-test lean ledger."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import EVIDENCE_DIR, LEAN_LEDGER, LEAN_LEDGER_REPO
from .freeze import freeze_hash

PILOT_TARGET = 40
V3_FIRST_TEST = 21
V3_LAST_TEST = 40
ACTIVATION_EVENT = "V3_PILOT_ACTIVATED"

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _canonical(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()

def _rows() -> list[dict]:
    if not LEAN_LEDGER.exists():
        return []
    out = []
    for line in LEAN_LEDGER.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out

def declarations() -> list[dict]:
    # Legacy tests 1-11 predate the explicit counts_toward_40 field. Every
    # HYPOTHESIS_DECLARED row in this pilot ledger counts unless it explicitly
    # opts out; this preserves the already-frozen 20-test history exactly.
    return [
        r for r in _rows()
        if r.get("event_type") == "HYPOTHESIS_DECLARED"
        and r.get("counts_toward_40") is not False
        and r.get("hypothesis_id")
    ]

def settlements() -> dict[str, dict]:
    out = {}
    for r in _rows():
        if r.get("event_type") == "SETTLEMENT_RECORDED" and r.get("hypothesis_id"):
            out[str(r["hypothesis_id"])] = r
    return out

def pilot_status() -> dict:
    dec = declarations()
    settled = settlements()
    wins = sum(1 for d in dec if settled.get(str(d.get("hypothesis_id")), {}).get("result") == "WIN")
    losses = sum(1 for d in dec if settled.get(str(d.get("hypothesis_id")), {}).get("result") == "LOSS")
    pushes = sum(1 for d in dec if settled.get(str(d.get("hypothesis_id")), {}).get("result") == "PUSH")
    return {
        "declared": len(dec), "wins": wins, "losses": losses, "pushes": pushes,
        "pending": len(dec) - wins - losses - pushes,
        "remaining": max(PILOT_TARGET - len(dec), 0),
    }

def _v3_prev_hash(rows: list[dict]) -> str | None:
    for r in reversed(rows):
        if r.get("v3_event_hash"):
            return str(r["v3_event_hash"])
    return None

def _chain_event(event: dict[str, Any], rows: list[dict]) -> dict[str, Any]:
    ev = dict(event)
    ev["v3_prev_hash"] = _v3_prev_hash(rows)
    ev["v3_freeze_sha256"] = freeze_hash()
    ev["v3_event_hash"] = _sha256_bytes(_canonical(ev))
    return ev

def _append_locked(event: dict[str, Any]) -> dict[str, Any]:
    LEAN_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEAN_LEDGER, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        fh.seek(0)
        rows = [json.loads(line) for line in fh if line.strip()]
        chained = _chain_event(event, rows)
        fh.seek(0, os.SEEK_END)
        fh.write(json.dumps(chained, sort_keys=True, separators=(",", ":"), default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    return chained

def ensure_activation() -> dict | None:
    rows = _rows()
    for r in rows:
        if r.get("event_type") == ACTIVATION_EVENT:
            return r
    legacy_bytes = LEAN_LEDGER.read_bytes() if LEAN_LEDGER.exists() else b""
    status = pilot_status()
    event = {
        "event_type": ACTIVATION_EVENT,
        "recorded_at_utc": _now_iso(),
        "counts_toward_40": False,
        "legacy_ledger_sha256_before_v3": _sha256_bytes(legacy_bytes),
        "legacy_declared_before_v3": status["declared"],
        "v3_test_range": [V3_FIRST_TEST, V3_LAST_TEST],
        "note": "Tests 1-20 remain byte-for-byte historical methodology; V3 appends only.",
    }
    return _append_locked(event)

def _write_evidence(hypothesis_id: str, evidence: dict[str, Any]) -> tuple[Path, str]:
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(evidence, sort_keys=True, indent=2, default=str).encode()
    h = _sha256_bytes(raw)
    path = EVIDENCE_DIR / f"{hypothesis_id}.json"
    if path.exists():
        existing = path.read_bytes()
        if existing != raw:
            raise RuntimeError(f"immutable evidence collision for {hypothesis_id}")
    else:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_bytes(raw)
        os.replace(tmp, path)
    return path, h

def append_declaration(signal: dict[str, Any], evidence: dict[str, Any]) -> dict | None:
    ensure_activation()
    status = pilot_status()
    if status["declared"] >= PILOT_TARGET:
        return None
    test_number = status["declared"] + 1
    if not (V3_FIRST_TEST <= test_number <= V3_LAST_TEST):
        raise RuntimeError(f"V3 attempted unexpected test_number={test_number}")
    hypothesis_id = str(signal["hypothesis_id"])
    if any(str(d.get("hypothesis_id")) == hypothesis_id for d in declarations()):
        return None
    evidence_path, evidence_hash = _write_evidence(hypothesis_id, evidence)
    event = {
        "event_type": "HYPOTHESIS_DECLARED",
        "hypothesis_id": hypothesis_id,
        "fixture": signal["fixture"],
        "fixture_id": signal["fixture_id"],
        "test_number": test_number,
        "counts_toward_40": True,
        "market_family": signal["market_family"],
        "market": signal["market"],
        "side": signal["side"],
        "line": signal["line"],
        "price_decimal": signal["price_decimal"],
        "opposite_price_decimal": signal["opposite_price_decimal"],
        "origin": "V3_AUTOMATED_THESTATSAPI_PROSPECTIVE",
        "originated_pre_settlement": True,
        "status_at_repo_freeze": "PENDING",
        "kickoff_utc": signal["kickoff_utc"],
        "prediction_observed_at_utc": signal["prediction_observed_at_utc"],
        "market_observed_at_utc": signal["market_observed_at_utc"],
        "methodology_status": (
            "V3_FROZEN_PROSPECTIVE_PILOT; NOT_CHAMPION; "
            "FOOTBALL_DISTRIBUTION_FROZEN_BEFORE_MARKET_COMPARISON"
        ),
        "model": signal["model"],
        "market_benchmark": signal["market_benchmark"],
        "immutable_evidence": {
            "relative_path": str(evidence_path.relative_to(LEAN_LEDGER_REPO)),
            "sha256": evidence_hash,
        },
        "cluster_id": signal.get("cluster_id"),
        "recorded_at_utc": _now_iso(),
    }
    return _append_locked(event)

def append_settlement(hypothesis_id: str, settlement: dict[str, Any]) -> dict | None:
    if hypothesis_id in settlements():
        return None
    event = {
        "event_type": "SETTLEMENT_RECORDED",
        "hypothesis_id": hypothesis_id,
        "result": settlement["result"],
        "settled_value": settlement.get("settled_value"),
        "settled_unit": settlement["settled_unit"],
        "final_score": settlement.get("final_score"),
        "verification_class": "THESTATSAPI_AUTOMATED_PROSPECTIVE",
        "closing_benchmark": settlement.get("closing_benchmark"),
        "source_payload_hashes": settlement.get("source_payload_hashes", {}),
        "recorded_at_utc": _now_iso(),
    }
    return _append_locked(event)

def git_commit(paths: list[Path], message: str) -> str | None:
    rels = [str(p.relative_to(LEAN_LEDGER_REPO)) for p in paths]
    subprocess.run(["git", "add", "--", *rels], cwd=LEAN_LEDGER_REPO, check=True)
    diff = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=LEAN_LEDGER_REPO
    )
    if diff.returncode == 0:
        return None
    subprocess.run(["git", "commit", "-m", message], cwd=LEAN_LEDGER_REPO, check=True)
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=LEAN_LEDGER_REPO, text=True
    ).strip()
