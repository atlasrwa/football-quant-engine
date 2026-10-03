from __future__ import annotations
import gzip, hashlib, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'research/qfe_v2_historical_expansion'
CUTOFF=1785542400
FORBIDDEN={'shots','shots_on_target','possession','fouls','yellow_cards','xg','odds','potential'}

def load(name):
    return json.loads((D/name).read_text())

def test_candidate_freeze_and_protected_boundary():
    m=load('QFE_V2_HISTORICAL_CANDIDATE_V1.json')
    assert m['status']=='FROZEN_RESEARCH_CANDIDATE_NOT_MODEL_INPUT'
    assert m['created_from_network_calls']==0
    assert m['protected_outcomes_opened'] is False
    assert m['counts']['candidate_total']==13885
    assert m['counts']['candidate_corner_complete']==13840
    assert m['scope']['covered_competitions']==18
    assert m['scope']['missing_competitions']==['England EFL League One','England EFL League Two']
    assert m['governance']['implicit_provider_blending'] is False
    assert m['governance']['layer4_frozen_model_unchanged'] is True
    assert m['governance']['champion_unchanged'] is True

def test_auxiliary_extension_integrity_and_no_forbidden_fields():
    man=load('CACHED_FOOTYSTATS_COUNT_EXTENSION_V1_MANIFEST.json')
    raw=(D/'CACHED_FOOTYSTATS_COUNT_EXTENSION_V1.jsonl.gz').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==man['data_gzip_sha256']
    assert man['network_calls']==0 and man['protected_outcomes_opened'] is False
    assert man['row_count']==8562 and man['corner_complete_rows']==8548
    assert man['competition_count']==12 and man['source_file_count']==52
    assert len(man['source_files'])==52
    with gzip.open(D/'CACHED_FOOTYSTATS_COUNT_EXTENSION_V1.jsonl.gz','rt') as f:
        rows=[json.loads(x) for x in f if x.strip()]
    assert len(rows)==man['row_count']
    assert all(r['provider']=='FOOTYSTATS_CACHED' for r in rows)
    assert all(r['kickoff_unix']<CUTOFF for r in rows)
    allowed=set(rows[0])
    assert not (FORBIDDEN & allowed)
    assert all(r['goals_home'] is not None and r['goals_away'] is not None for r in rows)

def test_cross_provider_validation_blocks_implicit_harmonization():
    v=load('CROSS_PROVIDER_SEMANTIC_VALIDATION_V1.json')
    assert v['network_calls']==0 and v['protected_outcomes_opened'] is False
    assert v['join_counts']['matched_identity_only']==2413
    assert 0.99 < v['goals']['exact_rate'] < 1.0
    assert 0.99 < v['fields']['corners']['exact_rate'] < 1.0
    assert abs(v['fields']['corners']['mean_signed_difference']) < 0.01
    assert v['fields']['shots']['exact_rate'] < 0.80
    assert v['fields']['xg']['exact_rate'] < 0.02
    assert v['interpretation']['implicit_blending_allowed'] is False

def test_cached_provider_contract_is_narrow():
    c=load('FOOTYSTATS_CACHED_CAPABILITIES_V1.json')
    assert c['implicit_cross_provider_blending'] is False
    by={x['field']:x for x in c['fields']}
    assert by['goals_home/away']['historical_model_eligible'] is True
    assert by['corners_home/away']['historical_model_eligible'] is True
    for k in ['shots','shots_on_target','possession','fouls','yellow_cards','xg']:
        assert by[k]['historical_model_eligible'] is False
