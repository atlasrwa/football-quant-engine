from __future__ import annotations
import json
from pathlib import Path
from src.research.v3_pilot.market import _bet365, _ou_pair, devig

def _final_record(market_path: Path, fixture_id: str):
    if not market_path.exists():
        return None
    rows=[]
    for line in market_path.read_text().splitlines():
        if not line.strip():
            continue
        row=json.loads(line)
        if row.get('fixture_id')==fixture_id and row.get('vintage')=='FINAL':
            rows.append(row)
    return max(rows,key=lambda r:float(r.get('observed_at') or 0)) if rows else None

def _payload(cache: Path, fixture_id: str, payload_hash: str):
    matches=sorted((cache/'odds'/fixture_id).glob(f'*_{payload_hash}.json'))
    if not matches:
        return None
    return json.loads(matches[-1].read_text())
def market_probability(payload, family: str, line: float, side: str):
    book=_bet365(payload)
    if not book:
        return None
    key='total_goals' if family=='goals' else 'match_corners'
    node=((book.get('markets') or {}).get(key) or {}).get(str(float(line)))
    if node is None:
        node=((book.get('markets') or {}).get(key) or {}).get(str(line))
    pair=_ou_pair(node or {},'last_seen')
    if not pair:
        return None
    p_over,p_under=devig(*pair)
    return float(p_over if side=='OVER' else p_under)

def closing_clv(*, market_path: Path, cache: Path, fixture_id: str,
                family: str, line: float, side: str,
                entry_market_p: float, model_p: float):
    rec=_final_record(market_path,fixture_id)
    if rec is None:
        return {'status':'UNAVAILABLE','reason':'NO_FINAL_MARKET_SNAPSHOT'}
    payload=_payload(cache,fixture_id,str(rec.get('odds_payload_hash') or ''))
    if payload is None:
        return {'status':'UNAVAILABLE','reason':'FINAL_ODDS_PAYLOAD_NOT_FOUND'}
    close_p=market_probability(payload,family,line,side)
    if close_p is None:
        return {'status':'UNAVAILABLE','reason':'DECLARED_LINE_NOT_QUOTED_AT_FINAL'}
    entry=float(entry_market_p); model=float(model_p); close=float(close_p)
    entry_gap=abs(model-entry); close_gap=abs(model-close)
    gap_closed=entry_gap-close_gap
    eps=0.0005
    direction='TOWARD_MODEL' if gap_closed>eps else ('AWAY_FROM_MODEL' if gap_closed<-eps else 'FLAT')
    return {
        'status':'OK',
        'final_observed_at':float(rec.get('observed_at') or 0),
        'final_observed_at_utc':rec.get('observed_at_utc'),
        'entry_market_p':entry,
        'closing_market_p':close,
        'market_move_pp':100.0*(close-entry),
        'entry_model_market_gap_pp':100.0*entry_gap,
        'closing_model_market_gap_pp':100.0*close_gap,
        'gap_closed_pp':100.0*gap_closed,
        'direction':direction,
    }
