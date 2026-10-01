from __future__ import annotations
import hashlib,json,os,time
from datetime import datetime,timezone
from pathlib import Path
from src.research.evidence_v32.settlement import cached_score_evidence,stable_regulation_score
from .config import *
from .model import predict_fixture,freeze as model_freeze
from .market import goals as goal_comparisons,corners as corner_comparison
from .provider import Provider,BudgetStop
from .telegram import send,declaration as decl_msg,settlement as set_msg

def iso(ts=None): return datetime.fromtimestamp(time.time() if ts is None else ts,timezone.utc).isoformat()
def atomic(p,o):
    p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+'.tmp'); t.write_text(json.dumps(o,sort_keys=True,indent=2,default=str)+'\n'); os.replace(t,p)
def readj(p):
    if not p.exists(): return []
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
def append(p,o):
    p.parent.mkdir(parents=True,exist_ok=True)
    with open(p,'a') as f:f.write(json.dumps(o,sort_keys=True,separators=(',',':'),default=str)+'\n');f.flush();os.fsync(f.fileno())
def state():
    if STATE.exists(): return json.loads(STATE.read_text())
    return {'last_discovery_at':0,'fixtures':{},'vintages':{},'enrolled':[],'declarations':{},'settled':{}}
def save(s): atomic(STATE,s)
def event(s,kind,**fields):
    prev=s.get('chain_head',''); body={'event_type':kind,'recorded_at_utc':iso(),'prev_hash':prev,**fields}; raw=json.dumps(body,sort_keys=True,separators=(',',':')).encode(); body['event_hash']=hashlib.sha256(raw).hexdigest(); append(EVENTS,body); s['chain_head']=body['event_hash']; return body

def discover(p,s,force=False):
    now=time.time()
    if not force and now-s.get('last_discovery_at',0)<DISCOVERY_REFRESH:return 0
    n=0
    for comp in scope():
        try: rows=p.upcoming(comp['competition_id'],DISCOVERY_HOURS)
        except BudgetStop: break
        for fx in rows:
            n+=1
            if fx['match_id'] not in s['fixtures']:
                append(FIXTURES,{'event_type':'FIXTURE_DISCOVERED','observed_at_utc':iso(),**fx})
            s['fixtures'][fx['match_id']]=fx
    s['last_discovery_at']=now; save(s); return n

def fpath(mid): return FREEZES/mid/'bundle.json'
def freeze_fixture(s,fx):
    p=fpath(fx['match_id'])
    if p.exists(): return json.loads(p.read_text())
    bundle=predict_fixture(fx); obj={'record_type':'V37_MODEL_FREEZE','fixture':fx,'frozen_at':time.time(),'frozen_at_utc':iso(),'model_freeze_sha256':model_freeze()['freeze_sha256'],**bundle}; obj['freeze_hash']=hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest(); atomic(p,obj); event(s,'MODEL_FROZEN',fixture_id=fx['match_id'],freeze_hash=obj['freeze_hash'],abstentions=obj['abstentions']); save(s); return obj

def due(s,fx,name,now):
    win={'EARLY':EARLY,'MID':MID,'FINAL':FINAL}[name]; sec=fx['ts']-now; return win[0]<=sec<=win[1] and not s['vintages'].get(f"{fx['match_id']}:{name}")
def comparisons(bundle,odds):
    out=[]
    if bundle.get('goals'):out.extend(goal_comparisons(bundle['goals'],odds))
    if bundle.get('corners'):
        c=corner_comparison(bundle['corners'],odds)
        if c:out.append(c)
    return out

def enroll(s,fx,comps):
    if fx['match_id'] in s['enrolled']: return s['enrolled'].index(fx['match_id'])+1
    if len(s['enrolled'])>=TARGET_FIXTURES or not comps:return None
    s['enrolled'].append(fx['match_id']); num=len(s['enrolled']); event(s,'FIXTURE_ENROLLED',fixture_id=fx['match_id'],fixture_number=num,fixture=f"{fx['home_name']} vs {fx['away_name']}",kickoff_utc=fx['utc_date']); return num

def maybe_declare(s,fx,num,bundle,comps,vintage):
    made=[]
    for fam in ('goals','corners'):
        key=f"{fx['match_id']}:{fam}"
        if key in s['declarations']: continue
        q=[c for c in comps if c['market_family']==fam and c['qualifies']]
        if not q: continue
        c=sorted(q,key=lambda x:(-x['model_minus_market_novig'],x['line']))[0]
        dist=bundle[fam]; d={'fixture_number':num,'fixture_id':fx['match_id'],'fixture':f"{fx['home_name']} vs {fx['away_name']}",'kickoff_utc':fx['utc_date'],'family':fam,'side':c['side'],'line':float(c['line']),'price_decimal':float(c['price_decimal']),'p_model':float(c['p_model_selected']),'p_market':float(c['p_market_novig_selected']),'delta':float(c['model_minus_market_novig']),'raw_break_even':float(c['raw_break_even_selected']),'vintage':vintage,'model_version':dist['version'],'freeze_hash':bundle['freeze_hash'],'declared_at_utc':iso()}
        ev=event(s,'DECLARATION',**d); s['declarations'][key]=ev['event_hash']; ok,detail=send(decl_msg(d)); append(TELEGRAM,{'event_type':'DECLARATION_TELEGRAM','fixture_id':fx['match_id'],'family':fam,'ok':ok,'detail':detail,'observed_at_utc':iso()}); made.append(d)
    return made

def evaluate(p,s):
    now=time.time(); obs=0; dec=0
    for fx in sorted(s['fixtures'].values(),key=lambda x:(x['ts'],x['match_id'])):
        if not(now<fx['ts']<=now+32*3600):continue
        enrolled=fx['match_id'] in s['enrolled']
        if len(s['enrolled'])>=TARGET_FIXTURES and not enrolled:continue
        bundle=freeze_fixture(s,fx)
        for vintage in ('EARLY','MID'):
            if not due(s,fx,vintage,now):continue
            try: odds,seen,ph=p.odds(fx['match_id'])
            except BudgetStop:return {'market_observations':obs,'declared':dec}
            s['vintages'][f"{fx['match_id']}:{vintage}"]=seen; save(s)
            if not odds:continue
            comps=comparisons(bundle,odds); append(MARKET,{'event_type':'MARKET_OBSERVED','fixture_id':fx['match_id'],'fixture':f"{fx['home_name']} vs {fx['away_name']}",'kickoff_utc':fx['utc_date'],'observed_at':seen,'observed_at_utc':iso(seen),'vintage':vintage,'odds_payload_hash':ph,'comparisons':comps}); obs+=1
            num=enroll(s,fx,comps) if vintage=='EARLY' else (s['enrolled'].index(fx['match_id'])+1 if enrolled else None)
            save(s)
            if num: dec+=len(maybe_declare(s,fx,num,bundle,comps,vintage)); save(s)
    return {'market_observations':obs,'declared':dec}

def capture_final(p,s):
    now=time.time(); n=0
    for mid in list(s['enrolled']):
        fx=s['fixtures'][mid]
        if due(s,fx,'FINAL',now):
            try: odds,seen,ph=p.odds(mid)
            except BudgetStop:break
            s['vintages'][f'{mid}:FINAL']=seen; save(s)
            if odds:
                b=json.loads(fpath(mid).read_text()); comps=comparisons(b,odds); append(MARKET,{'event_type':'MARKET_OBSERVED','fixture_id':mid,'fixture':f"{fx['home_name']} vs {fx['away_name']}",'kickoff_utc':fx['utc_date'],'observed_at':seen,'observed_at_utc':iso(seen),'vintage':'FINAL','odds_payload_hash':ph,'comparisons':comps}); n+=1
    return n

def corner_total(payload):
    try:
        a=payload['data']['overview']['corner_kicks']['all']; return int(a['home'])+int(a['away'])
    except Exception:return None

def settle(p,s):
    now=time.time(); done=0
    for mid in list(s['enrolled']):
        fx=s['fixtures'][mid]; st=s['settled'].setdefault(mid,{})
        if now<fx['ts']+4*3600 or st.get('goals') and st.get('corners'):continue
        try: p.detail(mid)
        except BudgetStop:break
        stable=stable_regulation_score(cached_score_evidence(CACHE/'match_detail'/mid,kickoff_ts=fx['ts']))
        if not stable:continue
        if not st.get('goals'):
            total=stable.home+stable.away; ev=event(s,'FAMILY_SETTLED',fixture_id=mid,family='goals',value=total,home=stable.home,away=stable.away,source='V32.1_STABLE_SCORE'); st['goals']=ev['event_hash']; done+=1; _settlement_telegram(s,fx,'goals',total)
        if not st.get('corners'):
            try: stats,_,_=p.stats(mid)
            except BudgetStop:break
            ct=corner_total(stats or {})
            if ct is not None:
                ev=event(s,'FAMILY_SETTLED',fixture_id=mid,family='corners',value=ct,source='V32.1_STABLE_SCORE_PLUS_PROVIDER_STATS'); st['corners']=ev['event_hash']; done+=1; _settlement_telegram(s,fx,'corners',ct)
        save(s)
    return done

def _settlement_telegram(s,fx,fam,value):
    key=f"{fx['match_id']}:{fam}"; h=s['declarations'].get(key)
    if not h:return
    d=next((r for r in reversed(readj(EVENTS)) if r.get('event_hash')==h),None)
    if not d:return
    won=value>d['line'] if d['side']=='OVER' else value<d['line']; result='PUSH' if value==d['line'] else ('WIN' if won else 'LOSS'); e={'result':result,'value':value}; ok,detail=send(set_msg(e,d)); append(TELEGRAM,{'event_type':'SETTLEMENT_TELEGRAM','fixture_id':fx['match_id'],'family':fam,'ok':ok,'detail':detail,'observed_at_utc':iso()})

def tick(force=False):
    s=state(); p=Provider(); found=discover(p,s,force); e=evaluate(p,s); final=capture_final(p,s); settled=settle(p,s); save(s); return {'discovered':found,'enrolled':len(s['enrolled']),'remaining':TARGET_FIXTURES-len(s['enrolled']),'declarations':len(s['declarations']),'final_captures':final,'settlement_events':settled,'requests':p.requests,**e}
def status():
    s=state(); return {'enrolled':len(s['enrolled']),'remaining':TARGET_FIXTURES-len(s['enrolled']),'declarations':len(s['declarations']),'settled_goals':sum(bool(v.get('goals')) for v in s['settled'].values()),'settled_corners':sum(bool(v.get('corners')) for v in s['settled'].values()),'chain_head':s.get('chain_head'),'model_freeze_sha256':model_freeze()['freeze_sha256']}
