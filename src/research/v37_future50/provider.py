from __future__ import annotations
import datetime as dt, json, time
from pathlib import Path
from src.research.prospective.api_contract import Endpoint, ProspectiveClientConfig
from src.research.prospective.capture import ProspectiveApiClient, payload_hash
from .config import CACHE,REQUEST_CAP,MONTHLY_RESERVE,MIN_INTERVAL
class BudgetStop(RuntimeError): pass

def _atomic(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True); t=p.with_suffix(p.suffix+'.tmp'); t.write_text(json.dumps(obj,sort_keys=True,indent=2,default=str)+'\n'); t.replace(p)
def _ts(s): return dt.datetime.fromisoformat(str(s).replace('Z','+00:00')).timestamp()
class Provider:
    def __init__(self):
        self.client=ProspectiveApiClient(config=ProspectiveClientConfig(rate_limit_seconds=MIN_INTERVAL,max_retries=2,timeout_seconds=30)); self.requests=0
    def _guard(self):
        if self.requests>=REQUEST_CAP: raise BudgetStop('request cap reached')
        rl=self.client.last_rate_limit; rem=getattr(rl,'monthly_remaining',None) if rl else None
        if rem not in (None,-1) and int(rem)<=MONTHLY_RESERVE: raise BudgetStop('monthly reserve reached')
    def _get(self,ep,kind,entity,params=None,**path):
        self._guard(); obs=time.time(); payload=self.client.get(ep,params=params,**path); self.requests+=1
        if payload is None:return None,obs,''
        ph=payload_hash(payload); p=CACHE/kind/entity/f'{int(obs)}_{ph}.json'
        if not p.exists(): _atomic(p,payload)
        return payload,obs,ph
    def upcoming(self,comp,hours=48):
        now=time.time(); end=now+hours*3600
        p,obs,ph=self._get(Endpoint.MATCHES,'upcoming',comp,params={'status':'scheduled','competition_id':comp,'date_from':dt.datetime.fromtimestamp(now,dt.timezone.utc).date().isoformat(),'date_to':dt.datetime.fromtimestamp(end,dt.timezone.utc).date().isoformat(),'per_page':100})
        out=[]
        for m in list((p or {}).get('data',[])):
            try:
                ts=_ts(m['utc_date']); neutral=m.get('is_neutral') if isinstance(m.get('is_neutral'),bool) else None
                if now<=ts<=end: out.append({'match_id':str(m['id']),'competition_id':str(m['competition_id']),'season_id':str(m['season_id']),'ts':ts,'kickoff_ts':ts,'utc_date':str(m['utc_date']),'kickoff':str(m['utc_date']),'home_id':str(m['home_team']['id']),'home_name':str(m['home_team'].get('name') or ''),'away_id':str(m['away_team']['id']),'away_name':str(m['away_team'].get('name') or ''),'is_neutral':neutral,'context':{'is_neutral':neutral},'provider_observed_at':obs,'provider_payload_hash':ph})
            except Exception: continue
        return sorted(out,key=lambda x:(x['ts'],x['match_id']))
    def odds(self,mid): return self._get(Endpoint.MATCH_ODDS,'odds',mid,match_id=mid)
    def detail(self,mid): return self._get(Endpoint.MATCH_DETAIL,'match_detail',mid,match_id=mid)
    def stats(self,mid): return self._get(Endpoint.MATCH_STATS,'stats',mid,match_id=mid)
