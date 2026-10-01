from __future__ import annotations
import hashlib,json,os,time
from datetime import datetime,timezone
from src.research.evidence_v32.settlement import cached_score_evidence,stable_regulation_score
from src.research.v3_pilot.market import _bet365,_ou_pair,devig
from .config import *
from .provider import Provider,BudgetStop
from .runtime import predict_pair,v38_freeze
from .market import compare_family
from .telegram import send,paired_message,paired_settlement
from src.research.v37_future50.clv import closing_clv

def iso(ts=None): return datetime.fromtimestamp(time.time() if ts is None else ts,timezone.utc).isoformat()
def atomic(p,o):
    p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+'.tmp'); t.write_text(json.dumps(o,sort_keys=True,indent=2,default=str)+'\n'); os.replace(t,p)
def append(p,o):
    p.parent.mkdir(parents=True,exist_ok=True)
    with open(p,'a') as f: f.write(json.dumps(o,sort_keys=True,separators=(',',':'),default=str)+'\n'); f.flush(); os.fsync(f.fileno())
def readj(p):
    if not p.exists(): return []
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
def state():
    if STATE.exists(): return json.loads(STATE.read_text())
    return {'last_discovery_at':0,'fixtures':{},'vintages':{},'enrolled':[],'messages':{},'settled':{}}
def save(s): atomic(STATE,s)
def event(s,kind,**fields):
    prev=s.get('chain_head',''); body={'event_type':kind,'recorded_at_utc':iso(),'prev_hash':prev,**fields}
    body['event_hash']=hashlib.sha256(json.dumps(body,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    append(EVENTS,body); s['chain_head']=body['event_hash']; return body

def discover(p,s,force=False):
    now=time.time()
    if not force and now-s.get('last_discovery_at',0)<DISCOVERY_REFRESH:return 0
    n=0
    for comp in scope():
        try: rows=p.upcoming(comp['competition_id'],DISCOVERY_HOURS)
        except BudgetStop: break
        for fx in rows:
            n+=1
            if fx['match_id'] not in s['fixtures']: append(FIXTURES,{'event_type':'FIXTURE_DISCOVERED','observed_at_utc':iso(),**fx})
            s['fixtures'][fx['match_id']]=fx
    s['last_discovery_at']=now; save(s); return n

def due(s,fx,name,now):
    win={'EARLY':EARLY,'MID':MID,'FINAL':FINAL}[name]; sec=fx['ts']-now
    return win[0]<=sec<=win[1] and not s['vintages'].get(f"{fx['match_id']}:{name}")

def fpath(mid): return FREEZES/mid/'pair.json'
def freeze_pair(s,fx):
    p=fpath(fx['match_id'])
    if p.exists(): return json.loads(p.read_text())
    pair=predict_pair(fx)
    obj={'record_type':'V38_PAIRED_MODEL_FREEZE','fixture':fx,'frozen_at':time.time(),'frozen_at_utc':iso(),
         'v38_freeze_sha256':v38_freeze()['freeze_sha256'],**pair}
    obj['pair_freeze_hash']=hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
    atomic(p,obj); event(s,'PAIR_FROZEN',fixture_id=fx['match_id'],pair_freeze_hash=obj['pair_freeze_hash']); save(s); return obj

def _market_over_prob(odds,family,line):
    bk=_bet365(odds)
    if not bk:return None
    m=(bk.get('markets') or {}).get('total_goals' if family=='goals' else 'match_corners') or {}
    pair=_ou_pair(m.get(str(line)) or {},'last_seen')
    if not pair:return None
    po,_=devig(*pair); return float(po)

def select_paired_line(control_comps,challenger_comps,odds,family):
    byc={float(x['line']):x for x in control_comps}; byh={float(x['line']):x for x in challenger_comps}
    candidates=[]
    for line in sorted(set(byc)&set(byh)):
        pm=_market_over_prob(odds,family,line)
        if pm is not None: candidates.append((abs(pm-.5),line,pm))
    if not candidates:return None
    _,line,pm=min(candidates)
    return line,pm,byc[line],byh[line]

def enroll(s,fx,has_comparison):
    if fx['match_id'] in s['enrolled']: return s['enrolled'].index(fx['match_id'])+1
    if len(s['enrolled'])>=TARGET_FIXTURES or not has_comparison:return None
    s['enrolled'].append(fx['match_id']); n=len(s['enrolled'])
    event(s,'FIXTURE_ENROLLED',fixture_id=fx['match_id'],fixture_number=n,fixture=f"{fx['home_name']} vs {fx['away_name']}",kickoff_utc=fx['utc_date']); return n

def maybe_message(s,fx,num,pair,odds,vintage):
    made=0
    for family in ('goals','corners'):
        key=f"{fx['match_id']}:{family}"
        if key in s['messages']:continue
        cd=(pair['control'].get(family)); hd=(pair['challenger'].get(family))
        if not cd or not hd:continue
        cc=compare_family(cd,odds,family); hc=compare_family(hd,odds,family)
        sel=select_paired_line(cc,hc,odds,family)
        if not sel:continue
        line,pm,c,h=sel
        if not(c['qualifies'] or h['qualifies']):continue
        # Market side/price is only a neutral display anchor; each model keeps its own side.
        anchor=c if c['p_model']>=h['p_model'] else h
        rec={'fixture_number':num,'fixture_id':fx['match_id'],'fixture':f"{fx['home_name']} vs {fx['away_name']}",
             'kickoff_utc':fx['utc_date'],'family':family,'line':line,'market_p':pm,
             'market_side':anchor['side'],'market_price':anchor['price'],'vintage':vintage,
             'pair_freeze_hash':pair['pair_freeze_hash'],
             'control':{k:c[k] for k in ['side','p_model','p_market','delta','price','raw_break_even','qualifies']},
             'challenger':{k:h[k] for k in ['side','p_model','p_market','delta','price','raw_break_even','qualifies']}}
        ev=event(s,'PAIRED_DECLARATION',**rec); s['messages'][key]=ev['event_hash']
        ok,detail=send(paired_message(rec)); append(TELEGRAM,{'event_type':'PAIRED_TELEGRAM','fixture_id':fx['match_id'],'family':family,'ok':ok,'detail':detail,'observed_at_utc':iso()}); made+=1
    return made

def observe(p,s):
    now=time.time(); obs=msgs=0
    for fx in sorted(s['fixtures'].values(),key=lambda x:(x['ts'],x['match_id'])):
        if not(now<fx['ts']<=now+32*3600):continue
        enrolled=fx['match_id'] in s['enrolled']
        if len(s['enrolled'])>=TARGET_FIXTURES and not enrolled:continue
        pair=freeze_pair(s,fx)
        for vintage in ('EARLY','MID'):
            if not due(s,fx,vintage,now):continue
            try: odds,seen,ph=p.odds(fx['match_id'])
            except BudgetStop:return {'market_observations':obs,'messages':msgs}
            s['vintages'][f"{fx['match_id']}:{vintage}"]=seen; save(s)
            if not odds:continue
            fams={}
            for family in ('goals','corners'):
                cd=pair['control'].get(family); hd=pair['challenger'].get(family)
                if cd and hd:
                    fams[family]={'control':compare_family(cd,odds,family),'challenger':compare_family(hd,odds,family)}
            has=any(select_paired_line(v['control'],v['challenger'],odds,f) for f,v in fams.items())
            append(MARKET,{'event_type':'PAIRED_MARKET_OBSERVED','fixture_id':fx['match_id'],'fixture':f"{fx['home_name']} vs {fx['away_name']}",
                           'kickoff_utc':fx['utc_date'],'observed_at':seen,'observed_at_utc':iso(seen),'vintage':vintage,
                           'odds_payload_hash':ph,'pair_freeze_hash':pair['pair_freeze_hash'],'families':fams})
            obs+=1
            num=enroll(s,fx,has) if vintage=='EARLY' else (s['enrolled'].index(fx['match_id'])+1 if enrolled else None); save(s)
            if num: msgs+=maybe_message(s,fx,num,pair,odds,vintage); save(s)
    return {'market_observations':obs,'messages':msgs}

def capture_final(p,s):
    now=time.time(); n=0
    for mid in list(s['enrolled']):
        fx=s['fixtures'][mid]
        if not due(s,fx,'FINAL',now):continue
        try: odds,seen,ph=p.odds(mid)
        except BudgetStop:break
        s['vintages'][f'{mid}:FINAL']=seen; save(s)
        if odds:
            pair=json.loads(fpath(mid).read_text()); fams={}
            for family in ('goals','corners'):
                cd=pair['control'].get(family); hd=pair['challenger'].get(family)
                if cd and hd:fams[family]={'control':compare_family(cd,odds,family),'challenger':compare_family(hd,odds,family)}
            append(MARKET,{'event_type':'PAIRED_MARKET_OBSERVED','fixture_id':mid,'fixture':f"{fx['home_name']} vs {fx['away_name']}",'kickoff_utc':fx['utc_date'],
                           'observed_at':seen,'observed_at_utc':iso(seen),'vintage':'FINAL','odds_payload_hash':ph,'pair_freeze_hash':pair['pair_freeze_hash'],'families':fams}); n+=1
    return n

def corner_total(payload):
    try:
        a=payload['data']['overview']['corner_kicks']['all']; return int(a['home'])+int(a['away'])
    except Exception:return None

def _paired_declaration_record(s,mid,fam):
    h=s.get('messages',{}).get(f"{mid}:{fam}")
    if not h:return None
    return next((r for r in reversed(readj(EVENTS)) if r.get('event_hash')==h),None)

def _paired_clv(s,mid,fam):
    d=_paired_declaration_record(s,mid,fam)
    if not d:return {'control':{'status':'UNAVAILABLE','reason':'NO_DECLARATION'},'challenger':{'status':'UNAVAILABLE','reason':'NO_DECLARATION'}}
    out={}
    for name in ('control','challenger'):
        arm=d[name]
        out[name]=closing_clv(market_path=MARKET,cache=CACHE,fixture_id=mid,family=fam,line=d['line'],side=arm['side'],entry_market_p=arm['p_market'],model_p=arm['p_model'])
    return out

def _paired_results(d,value):
    out={}
    for name in ('control','challenger'):
        side=d[name]['side']; won=value>d['line'] if side=='OVER' else value<d['line']
        out[name]='PUSH' if value==d['line'] else ('WIN' if won else 'LOSS')
    return out

def settle(p,s):
    now=time.time(); n=0
    for mid in list(s['enrolled']):
        fx=s['fixtures'][mid]; st=s['settled'].setdefault(mid,{})
        if now<fx['ts']+4*3600 or (st.get('goals') and st.get('corners')):continue
        try:p.detail(mid)
        except BudgetStop:break
        stable=stable_regulation_score(cached_score_evidence(CACHE/'match_detail'/mid,kickoff_ts=fx['ts']))
        if not stable:continue
        if not st.get('goals'):
            value=stable.home+stable.away; clv=_paired_clv(s,mid,'goals'); ev=event(s,'FAMILY_SETTLED',fixture_id=mid,family='goals',value=value,home=stable.home,away=stable.away,source='V32.1_STABLE_SCORE',clv=clv); st['goals']=ev['event_hash']; n+=1; _paired_settlement_telegram(s,fx,'goals',value,clv)
        if not st.get('corners'):
            try:stats,_,_=p.stats(mid)
            except BudgetStop:break
            ct=corner_total(stats or {})
            if ct is not None:
                clv=_paired_clv(s,mid,'corners'); ev=event(s,'FAMILY_SETTLED',fixture_id=mid,family='corners',value=ct,source='V32.1_STABLE_SCORE_PLUS_PROVIDER_STATS',clv=clv); st['corners']=ev['event_hash']; n+=1; _paired_settlement_telegram(s,fx,'corners',ct,clv)
        save(s)
    return n

def _paired_settlement_telegram(s,fx,fam,value,clv):
    d=_paired_declaration_record(s,fx['match_id'],fam)
    if not d:return
    e={'value':value,'clv':clv,'results':_paired_results(d,value)}
    ok,detail=send(paired_settlement(e,d)); append(TELEGRAM,{'event_type':'PAIRED_SETTLEMENT_TELEGRAM','fixture_id':fx['match_id'],'family':fam,'ok':ok,'detail':detail,'clv':clv,'results':e['results'],'observed_at_utc':iso()})

def tick(force=False):
    s=state(); p=Provider(); found=discover(p,s,force); o=observe(p,s); final=capture_final(p,s); settled=settle(p,s); save(s)
    return {'discovered':found,'enrolled':len(s['enrolled']),'remaining':TARGET_FIXTURES-len(s['enrolled']),'paired_messages':len(s['messages']),
            'final_captures':final,'settlement_events':settled,'requests':p.requests,**o}
def status():
    s=state(); return {'enrolled':len(s['enrolled']),'remaining':TARGET_FIXTURES-len(s['enrolled']),'paired_messages':len(s['messages']),
                       'settled_goals':sum(bool(x.get('goals')) for x in s['settled'].values()),'settled_corners':sum(bool(x.get('corners')) for x in s['settled'].values()),
                       'chain_head':s.get('chain_head'),'v38_freeze_sha256':v38_freeze()['freeze_sha256']}
