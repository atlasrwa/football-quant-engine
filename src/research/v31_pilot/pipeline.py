from __future__ import annotations
import hashlib, json, os, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .config import (DATA_ROOT,PREDICTION_ROOT,OBSERVATION_LOG,SHADOW_LOG,LEDGER_PATH,SETTLEMENT_LOG,STATE_PATH,
                     DISCOVERY_HOURS,DISCOVERY_REFRESH_SECONDS,EARLY_WINDOW,MID_WINDOW,FINAL_WINDOW,load_scope)
from .freeze import freeze_hash, load_freeze
from .market import goal_comparisons, btts_comparison
from .model import InsufficientRichHistory, canonical_hash, fit_predict, rich_history_row
from .provider import V31Provider
from .telegram import declaration_message, settlement_message, send
from src.research.v3_pilot.provider import ProviderBudgetStop
from src.research.prospective.capture import ProspectiveTransportError

FREEZE=load_freeze(); G=FREEZE['goals_btts']

def _now_iso(ts=None): return datetime.fromtimestamp(time.time() if ts is None else ts,timezone.utc).isoformat()
def _atomic_json(path:Path,obj:Any):
    path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp'); tmp.write_text(json.dumps(obj,sort_keys=True,indent=2,default=str)+'\n'); os.replace(tmp,path)
def _append(path:Path,obj:dict):
    path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,'a',encoding='utf-8') as f: f.write(json.dumps(obj,sort_keys=True,separators=(',',':'),default=str)+'\n'); f.flush(); os.fsync(f.fileno())
def _read(path:Path):
    if not path.exists(): return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
def _state():
    if not STATE_PATH.exists(): return {'last_discovery_at':0.0,'fixtures':{},'vintages':{}}
    return json.loads(STATE_PATH.read_text())
def _save(s): _atomic_json(STATE_PATH,s)

def _ledger_append(event:dict):
    rows=_read(LEDGER_PATH); prev=rows[-1]['event_hash'] if rows else None
    body={**event,'previous_hash':prev,'appended_at_utc':_now_iso()}; body['event_hash']=canonical_hash(body); _append(LEDGER_PATH,body); return body

def _declarations(): return [r for r in _read(LEDGER_PATH) if r.get('event_type')=='V31_DISAGREEMENT_DECLARATION']
def _declared_ids(): return {r['signal_id'] for r in _declarations()}
def _settled_ids(): return {r['signal_id'] for r in _read(LEDGER_PATH) if r.get('event_type')=='V31_SETTLEMENT'}
def _telegram_sent_ids(): return {r['signal_id'] for r in _read(LEDGER_PATH) if r.get('event_type')=='V31_TELEGRAM_SENT'}

def discover(provider:V31Provider,force=False):
    state=_state(); now=time.time()
    if not force and now-float(state.get('last_discovery_at',0))<DISCOVERY_REFRESH_SECONDS: return {'skipped':True,'fixtures':len(state.get('fixtures',{}))}
    found=0
    for comp in load_scope():
        try: rows=provider.upcoming(comp['competition_id'],hours=DISCOVERY_HOURS)
        except ProviderBudgetStop: break
        for fx in rows:
            found+=1; state.setdefault('fixtures',{})[fx['match_id']]=fx
    state['last_discovery_at']=now; _save(state); return {'skipped':False,'fixtures_discovered':found,'requests':provider.requests}

def _vintage(fx,now):
    stk=float(fx['ts'])-now
    for name,(lo,hi) in (('EARLY',EARLY_WINDOW),('MID',MID_WINDOW),('FINAL',FINAL_WINDOW)):
        if lo<=stk<=hi: return name
    return None

def _freeze_path(mid): return PREDICTION_ROOT/str(mid)/'goals_btts.json'
def _load_art(mid):
    p=_freeze_path(mid); return json.loads(p.read_text()) if p.exists() else None

def _rich_rows(provider,history,target):
    maxn=int(G['history_max_matches']); base=[m for m in history.get('matches',[]) if float(m['ts'])<float(target['ts'])][-maxn:]
    got=[]
    for m in reversed(base):
        try:
            payload,_,_=provider.stats(str(m['match_id']))
        except ProviderBudgetStop:
            raise
        except ProspectiveTransportError as exc:
            # The provider returns 404/409 for some finished matches whose detailed
            # stats are unavailable. Missing raw evidence is skipped, never zero-filled.
            if 'HTTP 404' in str(exc) or 'HTTP 409' in str(exc):
                continue
            raise
        if payload is None: continue
        row=rich_history_row(m,payload)
        if row is not None: got.append(row)
    return sorted(got,key=lambda r:(r['ts'],r['match_id']))

def _freeze_distribution(provider,fx):
    existing=_load_art(fx['match_id'])
    if existing: return existing
    history=provider.refresh_history(fx['competition_id']); rows=_rich_rows(provider,history,fx); dist=fit_predict(rows,fx); observed=time.time()
    art={'record_type':'V31_FROZEN_DISTRIBUTION','family':'goals_btts','fixture':fx,'frozen_at':observed,'frozen_at_utc':_now_iso(observed),
         'information_cutoff':observed,'freeze_contract_sha256':freeze_hash(),'parent_v3_freeze_sha256':FREEZE['parent']['v3_freeze_sha256'],
         'provider':'THESTATSAPI_ONLY','history_snapshot_hash':history['history_hash'],'rich_rows_count':len(rows),'distribution':dist}
    art['artifact_hash']=canonical_hash(art); p=_freeze_path(fx['match_id']); p.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(art,sort_keys=True,indent=2,default=str).encode()
    if p.exists():
        if p.read_bytes()!=raw: raise RuntimeError('immutable V3.1 freeze collision')
    else:
        tmp=p.with_suffix('.json.tmp'); tmp.write_bytes(raw); os.replace(tmp,p)
    _append(SHADOW_LOG,{'event_type':'V31_MODEL_DISTRIBUTION_FROZEN',**art}); return art

def _signal_id(fx,cmp):
    line='BTTS' if cmp['market_family']=='btts' else str(cmp['line']).replace('.','p')
    return f"V31:{fx['match_id']}:{cmp['market_family']}:{line}:{cmp['side']}"

def _declaration(fx,cmp,art,observed,odds_hash,vintage):
    model=art['distribution']; evidence={'fixture':fx,'family_freeze':art,'comparison':cmp,'market_observed_at':observed,'odds_payload_hash':odds_hash,'vintage':vintage}
    ehash=canonical_hash(evidence)
    return {'event_type':'V31_DISAGREEMENT_DECLARATION','signal_id':_signal_id(fx,cmp),'fixture_id':fx['match_id'],'fixture':f"{fx['home_name']} vs {fx['away_name']}",
        'kickoff_utc':fx['utc_date'],'market_family':cmp['market_family'],'market':cmp['market'],'side':cmp['side'],'line':cmp.get('line'),'price_decimal':cmp['price_decimal'],
        'market_observed_at_utc':_now_iso(observed),'vintage':vintage,'model':{'version':model['version'],'p_selected':cmp['p_model_selected'],'p_btts_yes':model['p_btts_yes'],
        'lambda_home':model['lambda_home'],'lambda_away':model['lambda_away'],'distribution_hash':model['distribution_hash'],'research_state':model['research_state']},
        'market_benchmark':{'bookmaker':'Bet365','no_vig_selected':cmp['p_market_novig_selected'],'model_minus_no_vig':cmp['model_minus_market_novig'],
        'raw_break_even_selected':cmp['raw_break_even_selected'],'selected_odds':cmp['price_decimal'],'opposite_odds':cmp['opposite_price_decimal'],'opening':cmp.get('opening'),'odds_payload_hash':odds_hash},
        'evidence_sha256':ehash,'counting_status':'V31_SHADOW_DOES_NOT_COUNT_TOWARD_V3_40'}

def _send_pending():
    sent=_telegram_sent_ids(); count=0; failures=[]
    for d in _declarations():
        if d['signal_id'] in sent: continue
        ok,detail=send(declaration_message(d))
        if ok: _ledger_append({'event_type':'V31_TELEGRAM_SENT','signal_id':d['signal_id'],'detail':detail}); sent.add(d['signal_id']); count+=1
        else: failures.append({'signal_id':d['signal_id'],'detail':detail})
    return {'sent':count,'failures':failures}

def evaluate_due(provider:V31Provider):
    state=_state(); now=time.time(); scope={r['competition_id']:r for r in load_scope()}; observations=0; declared=0; abstained=[]
    fixtures=[fx for fx in state.get('fixtures',{}).values() if now<float(fx['ts'])<=now+DISCOVERY_HOURS*3600 and fx.get('competition_id') in scope]
    for fx in sorted(fixtures,key=lambda x:(x['ts'],x['match_id'])):
        vintage=_vintage(fx,now)
        if not vintage: continue
        vk=f"{fx['match_id']}:{vintage}"
        if state.setdefault('vintages',{}).get(vk): continue
        try: art=_freeze_distribution(provider,fx)
        except ProviderBudgetStop: break
        except InsufficientRichHistory as e:
            abstained.append({'fixture_id':fx['match_id'],'reason':str(e)}); state['vintages'][vk]={'state':'ABSTAIN','reason':str(e),'at':now}; continue
        try: odds,observed,oh=provider.odds(fx['match_id'])
        except ProviderBudgetStop: break
        comps=goal_comparisons(art['distribution'],odds or {}); bc=btts_comparison(art['distribution'],odds or {})
        if bc: comps.append(bc)
        _append(OBSERVATION_LOG,{'event_type':'V31_MARKET_OBSERVED','fixture_id':fx['match_id'],'fixture':f"{fx['home_name']} vs {fx['away_name']}",
                                'kickoff_utc':fx['utc_date'],'observed_at':observed,'observed_at_utc':_now_iso(observed),'vintage':vintage,'odds_payload_hash':oh,'comparisons':comps})
        observations+=1; existing=_declared_ids()
        for cmp in comps:
            if cmp['qualifies']:
                d=_declaration(fx,cmp,art,observed,oh,vintage)
                if d['signal_id'] not in existing: _ledger_append(d); existing.add(d['signal_id']); declared+=1
        state['vintages'][vk]={'state':'OBSERVED','at':observed,'odds_hash':oh}
    _save(state); return {'observations':observations,'declared':declared,'abstained':abstained,'requests':provider.requests,'telegram':_send_pending()}

def settle_due(provider:V31Provider):
    settled=_settled_ids(); done=0
    for d in _declarations():
        if d['signal_id'] in settled or float(datetime.fromisoformat(d['kickoff_utc'].replace('Z','+00:00')).timestamp())>=time.time(): continue
        try: detail,_,ph=provider.match_detail(d['fixture_id'])
        except ProviderBudgetStop: break
        data=(detail or {}).get('data') or detail or {}; status=str(data.get('status') or '').lower()
        if status not in ('finished','complete','played'): continue
        score=data.get('score') or {}; reg=score.get('regulation') or {}; h=reg.get('home'); a=reg.get('away')
        if h is None or a is None: continue
        h,a=int(h),int(a); total=h+a
        if d['market_family']=='btts': event=(h>0 and a>0); selected=(d['side']=='YES')
        else: event=total>float(d['line']); selected=(d['side']=='OVER')
        ev={'event_type':'V31_SETTLEMENT','signal_id':d['signal_id'],'result':'WIN' if event==selected else 'LOSS','home_goals':h,'away_goals':a,'match_detail_payload_hash':ph}
        row=_ledger_append(ev); _append(SETTLEMENT_LOG,row); send(settlement_message(row,d)); settled.add(d['signal_id']); done+=1
    return {'settled':done,'requests':provider.requests}

def tick(force_discovery=False):
    provider=V31Provider(); return {'freeze_sha256':freeze_hash(),'discovery':discover(provider,force=force_discovery),'evaluation':evaluate_due(provider),'settlement':settle_due(provider),'requests':provider.requests}
