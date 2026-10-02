import hashlib,json
from pathlib import Path
import src.research.v371_future50.pipeline as pl
import src.research.v371_future50.provider as pr

def test_market_observation_hash_binds_exact_record(tmp_path,monkeypatch):
    monkeypatch.setattr(pl,'MARKET',tmp_path/'market.jsonl')
    body={'event_type':'MARKET_OBSERVED','fixture_id':'m1','observed_at':123.0,'odds_payload_hash':'abc','comparisons':[{'line':3.5}]}
    rec=pl.persist_market(dict(body))
    expected=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
    assert rec['market_observation_hash']==expected
    saved=json.loads((tmp_path/'market.jsonl').read_text())
    assert saved==rec

def test_declaration_binds_snapshot_and_raw_pair(tmp_path,monkeypatch):
    monkeypatch.setattr(pl,'EVENTS',tmp_path/'ledger.jsonl')
    monkeypatch.setattr(pl,'TELEGRAM',tmp_path/'telegram.jsonl')
    monkeypatch.setattr(pl,'send',lambda _: (True,'ok'))
    fx={'match_id':'m1','home_name':'A','away_name':'B','utc_date':'2030-01-01T20:00:00Z'}
    bundle={'freeze_hash':'freeze1','goals':{'version':'MODEL1'},'corners':None}
    comp={'market_family':'goals','qualifies':True,'model_minus_market_novig':.12,'line':3.5,'side':'UNDER','price_decimal':1.70,'opposite_price_decimal':2.20,'p_model_selected':.72,'p_market_novig_selected':.60,'raw_break_even_selected':1/1.70}
    mr={'odds_payload_hash':'payload1','market_observation_hash':'obs1','observed_at':100.5,'observed_at_utc':'x','request_started_at':100.0,'request_started_at_utc':'y'}
    s={'declarations':{}}
    made=pl.maybe_declare(s,fx,1,bundle,[comp],'EARLY',mr)
    assert len(made)==1
    d=made[0]
    assert d['odds_payload_hash']=='payload1' and d['market_observation_hash']=='obs1'
    assert d['market_request_started_at']==100.0 and d['market_observed_at']==100.5
    assert d['entry_over_odds']==2.20 and d['entry_under_odds']==1.70

def test_empty_response_does_not_consume_vintage(monkeypatch):
    now=1_800_000_000.0
    fx={'match_id':'m1','home_name':'A','away_name':'B','utc_date':'2030-01-01T00:00:00Z','ts':now+20*3600}
    s={'fixtures':{'m1':fx},'enrolled':[],'vintages':{},'declarations':{}}
    monkeypatch.setattr(pl.time,'time',lambda:now)
    monkeypatch.setattr(pl,'freeze_fixture',lambda s,fx:{'goals':None,'corners':None})
    monkeypatch.setattr(pl,'save',lambda s:None)
    monkeypatch.setattr(pl,'attempt',lambda *a,**k:None)
    class P:
        requests=1
        def odds(self,mid): return None,now+1,'',now
    pl.evaluate(P(),s)
    assert 'm1:EARLY' not in s['vintages']

def test_provider_uses_response_received_as_observation_time(tmp_path,monkeypatch):
    monkeypatch.setattr(pr,'CACHE',tmp_path)
    p=pr.Provider()
    monkeypatch.setattr(p,'_guard',lambda:None)
    monkeypatch.setattr(p.client,'get',lambda *a,**k:{'data':{'x':1}})
    it=iter([100.0,101.0]); monkeypatch.setattr(pr.time,'time',lambda:next(it))
    payload,received,ph,started=p._get('x','odds','m1')
    assert started==100.0 and received==101.0
    assert list((tmp_path/'odds'/'m1').glob('101_*.json'))


def test_response_received_time_controls_window(monkeypatch):
    now=1_800_000_000.0
    fx={'match_id':'m1','home_name':'A','away_name':'B','utc_date':'2030-01-01T00:00:00Z','ts':now+16*3600}
    s={'fixtures':{'m1':fx},'enrolled':[],'vintages':{},'declarations':{}}
    monkeypatch.setattr(pl.time,'time',lambda:now)
    monkeypatch.setattr(pl,'freeze_fixture',lambda s,fx:{'goals':None,'corners':None})
    monkeypatch.setattr(pl,'save',lambda s:None)
    seen=[]
    monkeypatch.setattr(pl,'attempt',lambda *a,**k:seen.append(a[2]))
    class P:
        requests=1
        def odds(self,mid): return {'data':{}},now+2,'ph',now
    pl.evaluate(P(),s)
    assert 'm1:EARLY' not in s['vintages']
    assert 'RESPONSE_OUTSIDE_WINDOW' in seen
