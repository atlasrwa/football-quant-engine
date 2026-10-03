from __future__ import annotations
import gzip,hashlib,json
from pathlib import Path
from src.research.dataset.manifest import sha256_json

ROOT=Path(__file__).resolve().parents[2]
D=ROOT/'research/qfe_v2_expanded_history'

def j(name): return json.loads((D/name).read_text())

def test_spec_is_preregistered_and_reference_frozen():
    s=j('SPEC_V1.json')
    assert s['status']=='PREREGISTERED_RETROSPECTIVE_CHALLENGER'
    assert s['scientific_boundaries']['market_odds_used'] is False
    assert s['scientific_boundaries']['protected_outcomes_scored']==0
    assert s['challenger_change']['team_identity']=='provider-scoped FootyStats team refs; no cross-provider team mapping'
    assert s['challenger_change']['corner_dispersion']=='unchanged frozen Layer4 alpha'
    assert s['challenger_change']['calibration'].startswith('unchanged frozen Layer4')

def test_result_boundaries_reference_reproduction_and_negative_gate():
    r=j('RESULT_V1.json')
    assert r['boundaries']['network_calls']==0
    assert r['boundaries']['market_odds_used'] is False
    assert r['boundaries']['protected_outcomes_scored']==0
    assert r['boundaries']['champion_changed'] is False
    assert r['boundaries']['layer4_reference_changed'] is False
    assert r['primary_calibration_select']['fixture_count']==204
    v=r['implementation_verification']
    assert v['max_reference_component_probability_error']==0.0
    assert v['max_reference_calibration_probability_error']==0.0
    assert r['advance_decision']['goals']['status']=='DO_NOT_ADVANCE'
    assert r['advance_decision']['corners']['status']=='DO_NOT_ADVANCE'
    assert r['advance_decision']['promotion_authorized'] is False

def test_paired_rows_are_tsa_only_and_preprotected():
    r=j('RESULT_V1.json')
    raw=(D/'PAIRED_ROWS_V1.jsonl.gz').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==r['paired_rows']['sha256']
    rows=[json.loads(x) for x in gzip.decompress(raw).decode().splitlines() if x.strip()]
    assert len(rows)==r['paired_rows']['row_count']==18203
    assert len({x['fixture_key'] for x in rows})==959
    assert all(x['fixture_key'].startswith('THESTATSAPI:') for x in rows)
    assert all(x['kickoff_ts']<1785542400 for x in rows)
    assert sha256_json(rows)==r['paired_rows']['content_hash']

def test_challenger_did_not_clear_frozen_advance_gate():
    r=j('RESULT_V1.json')
    s=r['primary_calibration_select']
    g=s['groups']['GOALS_TOTAL']; c=s['corner_composite']
    assert g['challenger_raw']['log_loss']>g['reference_raw']['log_loss']
    assert g['challenger_raw']['brier']>g['reference_raw']['brier']
    assert c['challenger_raw']['log_loss']>c['reference_raw']['log_loss']
    assert c['challenger_raw']['brier']>c['reference_raw']['brier']
    assert g['raw_paired_log_loss']['ci_low']<0
    assert c['raw_paired_log_loss']['ci_low']<0
