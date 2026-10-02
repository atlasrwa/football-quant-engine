import hashlib,json
import src.research.v381_paired50.pipeline as pl
import src.research.v381_paired50.provider as pr

def test_market_observation_hash_binds_exact_record(tmp_path,monkeypatch):
    monkeypatch.setattr(pl,'MARKET',tmp_path/'market.jsonl')
    body={'event_type':'PAIRED_MARKET_OBSERVED','fixture_id':'m1','observed_at':123.0,'odds_payload_hash':'abc','families':{}}
    rec=pl.persist_market(dict(body))
    expected=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
    assert rec['market_observation_hash']==expected

def test_anchor_market_probability_is_oriented_to_displayed_side():
    control={'side':'UNDER','p_model':.72,'p_market':.64,'price':1.55}
    challenger={'side':'OVER','p_model':.61,'p_market':.36,'price':2.60}
    side,price,p=pl._anchor_fields(control,challenger)
    assert side=='UNDER' and price==1.55 and p==.64

def test_paired_declaration_binds_shared_snapshot_and_pair(tmp_path,monkeypatch):
    monkeypatch.setattr(pl,'EVENTS',tmp_path/'ledger.jsonl')
    monkeypatch.setattr(pl,'TELEGRAM',tmp_path/'telegram.jsonl')
    monkeypatch.setattr(pl,'send',lambda _: (True,'ok'))
    c={'line':3.5,'side':'UNDER','p_model':.72,'p_market':.64,'delta':.08,'price':1.70,'raw_break_even':1/1.70,'qualifies':True}
    h={'line':3.5,'side':'UNDER','p_model':.69,'p_market':.64,'delta':.05,'price':1.70,'raw_break_even':1/1.70,'qualifies':True}
    monkeypatch.setattr(pl,'compare_family',lambda dist,odds,family:[c] if dist['tag']=='c' else [h])
    monkeypatch.setattr(pl,'select_paired_line',lambda cc,hc,odds,family:(3.5,.36,c,h))
    odds={'data':{'bookmakers':[{'bookmaker':'Bet365','markets':{'total_goals':{'3.5':{'over':{'last_seen':2.20},'under':{'last_seen':1.70}}}}}]}}
    pair={'pair_freeze_hash':'pf1','control':{'goals':{'tag':'c'},'corners':None},'challenger':{'goals':{'tag':'h'},'corners':None}}
    mr={'odds_payload_hash':'payload1','market_observation_hash':'obs1','observed_at':100.5,'observed_at_utc':'x','request_started_at':100.0,'request_started_at_utc':'y'}
    fx={'match_id':'m1','home_name':'A','away_name':'B','utc_date':'2030-01-01T20:00:00Z'}
    s={'messages':{}}
    assert pl.maybe_message(s,fx,1,pair,odds,'EARLY',mr)==1
    d=[json.loads(x) for x in (tmp_path/'ledger.jsonl').read_text().splitlines()][0]
    assert d['odds_payload_hash']=='payload1' and d['market_observation_hash']=='obs1'
    assert d['entry_over_odds']==2.20 and d['entry_under_odds']==1.70
    assert d['market_side']=='UNDER' and d['market_p']==.64
    assert d['control']['p_market']==d['challenger']['p_market']==.64

def test_empty_response_does_not_consume_vintage(monkeypatch):
    now=1_800_000_000.0
    fx={'match_id':'m1','home_name':'A','away_name':'B','utc_date':'2030-01-01T00:00:00Z','ts':now+20*3600}
    s={'fixtures':{'m1':fx},'enrolled':[],'vintages':{},'messages':{}}
    monkeypatch.setattr(pl.time,'time',lambda:now)
    monkeypatch.setattr(pl,'freeze_pair',lambda s,fx:{'control':{'goals':None,'corners':None},'challenger':{'goals':None,'corners':None}})
    monkeypatch.setattr(pl,'save',lambda s:None)
    monkeypatch.setattr(pl,'attempt',lambda *a,**k:None)
    class P:
        requests=1
        def odds(self,mid): return None,now+1,'',now
    pl.observe(P(),s)
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
    s={'fixtures':{'m1':fx},'enrolled':[],'vintages':{},'messages':{}}
    monkeypatch.setattr(pl.time,'time',lambda:now)
    monkeypatch.setattr(pl,'freeze_pair',lambda s,fx:{'control':{'goals':None,'corners':None},'challenger':{'goals':None,'corners':None}})
    monkeypatch.setattr(pl,'save',lambda s:None)
    seen=[]
    monkeypatch.setattr(pl,'attempt',lambda *a,**k:seen.append(a[2]))
    class P:
        requests=1
        def odds(self,mid): return {'data':{}},now+2,'ph',now
    pl.observe(P(),s)
    assert 'm1:EARLY' not in s['vintages']
    assert 'RESPONSE_OUTSIDE_WINDOW' in seen
