import gzip,hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'research/qfe_v2_competition_isolation'
def j(n): return json.loads((D/n).read_text())
def test_boundaries_and_negative_gate():
    r=j('RESULT_V1.json')
    assert r['boundaries']=={'champion_changed':False,'layer4_reference_changed':False,'market_odds_used':False,'network_calls':0,'protected_outcomes_scored':0}
    assert r['goals_selection']['selected_weight'] is None
    assert r['corners_selection']['selected_weight']==40.0
    assert r['corners_selection']['d4']['confirmed'] is False
    assert r['advance_gate']['goals']['status']=='DO_NOT_ADVANCE'
    assert r['advance_gate']['corners']['status']=='DO_NOT_ADVANCE'
    assert r['advance_gate']['promotion_authorized'] is False
def test_paired_artifact_integrity():
    r=j('RESULT_V1.json'); p=D/'CALIBRATION_PAIRED_ROWS_V1.jsonl.gz'; raw=p.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==r['paired_rows']['sha256']
    rows=[json.loads(x) for x in gzip.decompress(raw).decode().splitlines() if x.strip()]
    assert len(rows)==r['paired_rows']['rows']
    assert all(x['fixture'].startswith('THESTATSAPI:') for x in rows)
    assert all(x['ts']<1785542400 for x in rows)
