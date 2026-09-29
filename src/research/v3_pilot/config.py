"""V3 pilot paths and frozen operational constants."""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA_ROOT = Path("/home/ubuntu/data/v3_pilot")
PROVIDER_CACHE = DATA_ROOT / "provider_cache"
HISTORY_ROOT = DATA_ROOT / "history"
PREDICTION_ROOT = DATA_ROOT / "prediction_freezes"
OBSERVATION_LOG = DATA_ROOT / "market_observations.jsonl"
SHADOW_LOG = DATA_ROOT / "shadow_predictions.jsonl"
SETTLEMENT_LOG = DATA_ROOT / "settlements.jsonl"
STATE_PATH = DATA_ROOT / "state.json"
LOCK_PATH = Path("/tmp/qfe_v3_pilot.lock")
PROTOTYPE_ENV = Path("/home/ubuntu/.config/qfe-v3/prototype.env")
LEAN_LEDGER_REPO = Path("/home/ubuntu/handoff_out/lean_hypothesis_ledger")
LEAN_LEDGER = LEAN_LEDGER_REPO / "research/lean_hypothesis_ledger/ledger_v1.jsonl"
EVIDENCE_DIR = LEAN_LEDGER_REPO / "research/lean_hypothesis_ledger/v3_evidence"
SCOPE_PATH = ROOT / "research/v3_live_pilot/competition_scope_v1.json"

DISCOVERY_HOURS = 48
DISCOVERY_REFRESH_SECONDS = 6 * 3600
HISTORY_REFRESH_SECONDS = 12 * 3600
EARLY_WINDOW = (16 * 3600, 32 * 3600)
MID_WINDOW = (3 * 3600, 9 * 3600)
FINAL_WINDOW = (5 * 60, 20 * 60)
MONTHLY_RESERVE = 10_000
PER_RUN_REQUEST_CAP = 160
MIN_REQUEST_INTERVAL_SECONDS = 2.1

def load_scope() -> list[dict]:
    obj = json.loads(SCOPE_PATH.read_text(encoding="utf-8"))
    rows = obj.get("competitions", [])
    if len(rows) < int(obj.get("minimum_competitions", 25)):
        raise RuntimeError("V3 scope below frozen minimum competition count")
    return rows
