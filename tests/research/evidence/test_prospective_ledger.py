import hashlib,json
from pathlib import Path
from src.research.evidence.prospective_ledger import verify_event_chain,verify_market_hashes,_selection_result,_proper_scores


def _event(prev,kind='X',**fields):
    b={'event_type':kind,'recorded_at_utc':'2026-01-01T00:00:00Z','prev_hash':prev,**fields}
    b['event_hash']=hashlib.sha256(json.dumps(b,sort_keys=True,separators=(',',':')).encode()).hexdigest(); return b

def test_event_chain_detects_mutation():
    a=_event(''); b=_event(a['event_hash'])
    assert verify_event_chain([a,b])==b['event_hash']
    b2=dict(b); b2['recorded_at_utc']='changed'
    try: verify_event_chain([a,b2])
    except ValueError: pass
    else: raise AssertionError('mutation must fail')

def test_market_hash_verification():
    b={'fixture_id':'x','vintage':'EARLY'}
    b['market_observation_hash']=hashlib.sha256(json.dumps(b,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    verify_market_hashes([b])

def test_binary_half_line_scoring():
    assert _selection_result('OVER',3.5,4)=='WIN'
    assert _selection_result('UNDER',3.5,4)=='LOSS'
    y,b,ll=_proper_scores(.7,'WIN')
    assert y is True and b < .1 and ll > 0

def test_integer_line_fails_closed():
    try: _selection_result('OVER',4.0,5)
    except ValueError: pass
    else: raise AssertionError('integer declaration must fail closed in snapshot v1')


def _write_jsonl(path, rows):
    path.write_text(''.join(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n' for row in rows))


def _market(body):
    row=dict(body)
    raw=json.dumps(row,sort_keys=True,separators=(',',':'),default=str).encode()
    row['market_observation_hash']=hashlib.sha256(raw).hexdigest()
    return row


def test_single_experiment_snapshot_normalizes_settlement_and_market(tmp_path):
    from src.research.evidence.prospective_ledger import ExperimentSourceSpec,build_snapshot
    data=tmp_path/'data'; runtime=tmp_path/'runtime'; data.mkdir(); runtime.mkdir()
    declaration_fields={
        'fixture_id':'mt_1','fixture':'A vs B','kickoff_utc':'2026-01-01T20:00:00Z',
        'family':'corners','line':8.5,'side':'OVER','p_model':0.60,'p_market':0.50,
        'delta':0.10,'price_decimal':2.0,'raw_break_even':0.50,'freeze_hash':'fh',
        'bookmaker':'Bet365','provider':'thestatsapi','model_version':'M1',
        'declared_at_utc':'2026-01-01T12:00:00Z','market_observed_at_utc':'2026-01-01T11:59:00Z',
    }
    decl=_event('',kind='DECLARATION',**declaration_fields)
    settlement=_event(decl['event_hash'],kind='FAMILY_SETTLED',fixture_id='mt_1',family='corners',value=10,source='TEST',clv={'status':'OK','closing_market_p':0.55,'market_move_pp':5.0})
    _write_jsonl(data/'ledger.jsonl',[decl,settlement])
    market=_market({'event_type':'MARKET_OBSERVED','fixture_id':'mt_1','vintage':'EARLY','observed_at_utc':'2026-01-01T11:59:00Z','odds_payload_hash':'ph','comparisons':[{'market_family':'corners','line':8.5,'side':'UNDER','p_market_novig_selected':0.50}]})
    _write_jsonl(data/'market_observations.jsonl',[market])
    _write_jsonl(data/'fixtures.jsonl',[])
    (data/'state.json').write_text(json.dumps({'chain_head':settlement['event_hash']}))
    spec=ExperimentSourceSpec('E1','SINGLE',data,runtime,'test://e1','missing_model.json','missing_spec.json')
    snap=build_snapshot((spec,),frozen_on='2026-01-01T13:00:00Z')
    assert len(snap.declarations)==1
    row=snap.declarations[0]
    assert row.selection_result=='WIN'
    assert row.outcome_selected_wins is True
    assert row.brier == (0.60-1.0)**2
    assert row.unit_pnl == 1.0
    assert row.closing_market_p == 0.55
    # Stored comparison is UNDER at 0.50, declaration is OVER; complement is 0.50.
    assert row.market_snapshots[0]['p_market_declared_side'] == 0.50
