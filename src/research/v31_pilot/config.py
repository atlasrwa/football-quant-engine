from __future__ import annotations
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
DATA_ROOT=Path('/home/ubuntu/data/v31_pilot')
PREDICTION_ROOT=DATA_ROOT/'prediction_freezes'
OBSERVATION_LOG=DATA_ROOT/'market_observations.jsonl'
SHADOW_LOG=DATA_ROOT/'shadow_events.jsonl'
LEDGER_PATH=DATA_ROOT/'ledger.jsonl'
SETTLEMENT_LOG=DATA_ROOT/'settlements.jsonl'
STATE_PATH=DATA_ROOT/'state.json'
PROTOTYPE_ENV=Path('/home/ubuntu/.config/qfe-v3/prototype.env')
SCOPE_PATH=ROOT/'research/v3_1_live_pilot/competition_scope_v1.json'
LOCK_PATH=Path('/tmp/qfe_v31_pilot.lock')
DISCOVERY_HOURS=48
DISCOVERY_REFRESH_SECONDS=6*3600
EARLY_WINDOW=(16*3600,32*3600)
MID_WINDOW=(3*3600,9*3600)
FINAL_WINDOW=(5*60,20*60)

def load_scope() -> list[dict]:
    obj=json.loads(SCOPE_PATH.read_text(encoding='utf-8')); rows=obj.get('competitions',[])
    if len(rows)<int(obj.get('minimum_competitions',25)): raise RuntimeError('V3.1 scope below frozen minimum')
    if not any(r.get('competition_id')=='comp_720692' for r in rows): raise RuntimeError('Colombia Primera A missing from V3.1 scope')
    return rows
