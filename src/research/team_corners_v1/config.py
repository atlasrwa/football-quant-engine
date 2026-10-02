from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = Path("/home/ubuntu/data/qfe_team_corners_v1")
CACHE = DATA / "provider_cache"
FREEZES = DATA / "prediction_freezes"
STATE = DATA / "state.json"
FIXTURES = DATA / "fixtures.jsonl"
MARKET = DATA / "market_observations.jsonl"
MARKET_ATTEMPTS = DATA / "market_attempts.jsonl"
EVENTS = DATA / "ledger.jsonl"
TELEGRAM = DATA / "telegram_delivery.jsonl"
ERRORS = DATA / "ops_errors.jsonl"
SETTLEMENT_EVIDENCE = DATA / "settlement_evidence.jsonl"
ENV = Path("/home/ubuntu/.config/qfe-v3/prototype.env")
SPEC = ROOT / "research/team_corners_v1/SPEC.json"
MODEL_FREEZE = ROOT / "research/team_corners_v1/MODEL_FREEZE.json"
SCOPE = ROOT / "research/v37_future50/competition_scope_v1.json"
EVIDENCE = ROOT / "research/evidence_v32/out/evidence_v2/evidence.jsonl"

DISCOVERY_HOURS = 48
DISCOVERY_REFRESH = 6 * 3600
EARLY = (16 * 3600, 32 * 3600)
MID = (3 * 3600, 9 * 3600)
FINAL = (5 * 60, 20 * 60)
REQUEST_CAP = 160
MONTHLY_RESERVE = 10000
MIN_INTERVAL = 2.1
TARGET_FIXTURES = 50
RETRY_BACKOFF = 45 * 60
PRIMARY_LINES = (2.5, 3.5, 4.5, 5.5, 6.5, 7.5)

def scope() -> list[dict]:
    obj = json.loads(SCOPE.read_text(encoding="utf-8"))
    rows = obj.get("competitions", [])
    if len(rows) < 25:
        raise RuntimeError("scope below 25 competitions")
    return rows

def spec() -> dict:
    return json.loads(SPEC.read_text(encoding="utf-8"))
