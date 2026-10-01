"""Immutable offline/prospective-shadow boundary for V3.5.

This module does not discover fixtures, call providers, publish Telegram messages,
or mutate V3 ledgers. Callers must supply pre-match fixture context and, for
market comparison, a timestamped odds payload after the model freeze exists.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.research.v3_pilot.model import canonical_hash

from .market import corner_comparison, goal_comparisons
from .model import load_artifact
from .runtime import DEFAULT_ARTIFACT, load_evidence, predict_bundle


def _now_iso(ts: float | None = None) -> str:
    value = time.time() if ts is None else float(ts)
    return datetime.fromtimestamp(value, timezone.utc).isoformat()


def _immutable_json(path: Path, obj: dict[str, Any]) -> None:
    raw = json.dumps(obj, sort_keys=True, indent=2, default=str).encode()
    if path.exists():
        if path.read_bytes() != raw:
            raise RuntimeError(f"immutable V35 freeze collision: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, path)


def freeze_fixture(
    fixture: dict,
    *,
    output_root: str | Path,
    evidence_rows: list[dict] | None = None,
    artifact: dict | None = None,
    observed_at: float | None = None,
) -> dict:
    rows = load_evidence() if evidence_rows is None else evidence_rows
    art = load_artifact(DEFAULT_ARTIFACT) if artifact is None else artifact
    bundle = predict_bundle(fixture, evidence_rows=rows, artifact=art)
    observed = time.time() if observed_at is None else float(observed_at)
    root = Path(output_root) / str(fixture["match_id"])

    frozen = {
        "record_type": "V35_SHADOW_MODEL_FREEZE",
        "fixture": fixture,
        "frozen_at": observed,
        "frozen_at_utc": _now_iso(observed),
        "model_artifact_hash": art["artifact_sha256"],
        "training_evidence_sha256": art["training_evidence_sha256"],
        "families": {},
        "abstentions": bundle["abstentions"],
    }
    for family in ("goals", "corners"):
        dist = bundle.get(family)
        if dist is None:
            continue
        family_art = {
            "record_type": "V35_FROZEN_DISTRIBUTION",
            "family": family,
            "fixture": fixture,
            "frozen_at": observed,
            "frozen_at_utc": _now_iso(observed),
            "model_artifact_hash": art["artifact_sha256"],
            "distribution": dist,
        }
        family_art["artifact_hash"] = canonical_hash(family_art)
        _immutable_json(root / f"{family}.json", family_art)
        frozen["families"][family] = family_art
    frozen["freeze_hash"] = canonical_hash(frozen)
    _immutable_json(root / "bundle.json", frozen)
    return frozen


def compare_frozen(bundle: dict, odds_payload: dict) -> dict:
    out = {"goals": [], "corners": None}
    goals = (bundle.get("families") or {}).get("goals")
    if goals is not None:
        out["goals"] = goal_comparisons(goals["distribution"], odds_payload)
    corners = (bundle.get("families") or {}).get("corners")
    if corners is not None:
        out["corners"] = corner_comparison(corners["distribution"], odds_payload)
    return out
