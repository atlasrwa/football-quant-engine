"""Offline-safe V3.5 prediction bundle for a supplied future fixture."""
from __future__ import annotations

import json
from pathlib import Path

from .features import FrontierUnsupported
from .model import load_artifact, predict_corners, predict_goals

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ARTIFACT = ROOT / "research/v35_frontier/V35_MODEL_ARTIFACT_V1.json"
DEFAULT_EVIDENCE = ROOT / "research/evidence_v32/out/evidence_v2/evidence.jsonl"


def load_evidence(path: str | Path = DEFAULT_EVIDENCE) -> list[dict]:
    p = Path(path)
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]


def predict_bundle(fixture: dict, *, evidence_rows: list[dict] | None = None,
                   artifact: dict | None = None) -> dict:
    rows = load_evidence() if evidence_rows is None else evidence_rows
    art = load_artifact(DEFAULT_ARTIFACT) if artifact is None else artifact
    result = {
        "fixture_id": str(fixture["match_id"]),
        "artifact_hash": art["artifact_sha256"],
        "goals": None, "corners": None, "abstentions": [],
    }
    try:
        result["goals"] = predict_goals(rows, fixture, art)
    except FrontierUnsupported as exc:
        result["abstentions"].append({"family": "goals", "reason": str(exc)})
    try:
        result["corners"] = predict_corners(rows, fixture, art)
    except (FrontierUnsupported, RuntimeError) as exc:
        result["abstentions"].append({"family": "corners", "reason": str(exc)})
    return result
