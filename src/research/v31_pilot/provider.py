from __future__ import annotations
import datetime as dt, time
from src.research.prospective.api_contract import Endpoint
from src.research.v3_pilot.provider import V3Provider, _ts

class V31Provider(V3Provider):
    """V3 provider with richer upcoming context; raw cache/provenance remains shared and immutable."""
    def upcoming(self, competition_id: str, *, hours: int = 48) -> list[dict]:
        now=time.time(); horizon=now+hours*3600
        date_from=dt.datetime.fromtimestamp(now,dt.timezone.utc).date().isoformat()
        date_to=dt.datetime.fromtimestamp(horizon,dt.timezone.utc).date().isoformat()
        payload, observed, ph=self._get(Endpoint.MATCHES,kind='upcoming',entity=competition_id,
            params={'status':'scheduled','competition_id':competition_id,'date_from':date_from,'date_to':date_to,'per_page':100})
        out=[]
        for m in list((payload or {}).get('data',[])):
            try:
                ts=_ts(str(m['utc_date']))
                if not(now<=ts<=horizon): continue
                out.append({'match_id':str(m['id']),'competition_id':str(m['competition_id']),'season_id':str(m['season_id']),
                    'ts':ts,'utc_date':str(m['utc_date']),'home_id':str(m['home_team']['id']),'home_name':str(m['home_team'].get('name') or ''),
                    'away_id':str(m['away_team']['id']),'away_name':str(m['away_team'].get('name') or ''),'is_neutral':m.get('is_neutral'),
                    'home_manager':m.get('home_manager'),'away_manager':m.get('away_manager'),'matchday':m.get('matchday'),'stage_name':m.get('stage_name'),
                    'group_label':m.get('group_label'),'xg_available':m.get('xg_available'),'odds_available':m.get('odds_available'),
                    'provider_observed_at':observed,'provider_payload_hash':ph})
            except (KeyError,TypeError,ValueError): continue
        return sorted(out,key=lambda r:(r['ts'],r['match_id']))
