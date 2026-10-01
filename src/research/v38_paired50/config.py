from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
DATA=Path('/home/ubuntu/data/v38_paired50'); CACHE=DATA/'provider_cache'; FREEZES=DATA/'prediction_freezes'
STATE=DATA/'state.json'; FIXTURES=DATA/'fixtures.jsonl'; MARKET=DATA/'market_observations.jsonl'; EVENTS=DATA/'ledger.jsonl'; TELEGRAM=DATA/'telegram_delivery.jsonl'
ENV=Path('/home/ubuntu/.config/qfe-v3/prototype.env')
SPEC=ROOT/'research/v38_paired50/SPEC.json'; MODEL_FREEZE=ROOT/'research/v38_paired50/MODEL_FREEZE.json'; SCOPE=ROOT/'research/v38_paired50/competition_scope_v1.json'
DISCOVERY_HOURS=48; DISCOVERY_REFRESH=6*3600; EARLY=(16*3600,32*3600); MID=(3*3600,9*3600); FINAL=(300,1200); TARGET_FIXTURES=50
REQUEST_CAP=160; MONTHLY_RESERVE=10000; MIN_INTERVAL=2.1

def scope():
    import json
    o=json.loads(SCOPE.read_text()); rows=o.get('competitions',[])
    if len(rows)<25: raise RuntimeError('scope below 25 competitions')
    return rows
