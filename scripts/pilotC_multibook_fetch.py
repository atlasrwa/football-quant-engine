"""
Pilot C — forward multi-book odds collection. ZERO historical value by design:
Betfair/Pinnacle/openings are only retained for recent/upcoming matches (verified),
so this seeds a PROSPECTIVE dataset that becomes a backtest as games settle.

One call per (match, book). Books: bet365, betfair-exchange, pinnacle.
Cache-first (idempotent), hard local cap via THESTATS_MAX_REQUESTS, client pacing.
Priority order: finished (settle first) -> live -> scheduled, so the cap spends on
the most immediately useful games. Skips a book for a match once budget is tight.

Cache key: pilotC_odds_<mid>_<book>. Raw response saved unmodified by the client.
"""
import sys, json, os
sys.path.insert(0,'/home/ubuntu/scripts')
import thestatsapi_client as api

LIST='/home/ubuntu/data/thestatsapi/championship/_pilotC_fixture_list.json'
BOOKS=['bet365','betfair-exchange','pinnacle']
PROGRESS='/home/ubuntu/data/thestatsapi/championship/_pilotC_progress.json'


def main():
    fx=json.load(open(LIST)); meta=fx['meta']
    order={'finished':0,'live':1,'scheduled':2}
    ids=sorted(fx['match_ids'], key=lambda m: order.get(meta[m]['status'],3))
    stats={'live_calls':0,'cached':0,'empty':0,'populated':0,'by_book':{b:0 for b in BOOKS}}
    saved=[]
    for mid in ids:
        for bk in BOOKS:
            ck=f"pilotC_odds_{mid}_{bk}"
            was=api.is_cached(ck)
            try:
                data,m=api.get_json(f"/football/matches/{mid}/odds",
                                    params={"bookmaker":bk}, cache_key=ck,
                                    allow_status=(200,404,422))
            except SystemExit:
                print("CAP/così budget stop reached — halting cleanly.")
                _dump(stats,saved); return
            if m.get('from_cache'): stats['cached']+=1
            elif m.get('http_status')==200: stats['live_calls']+=1
            bks=(data or {}).get('data',{}).get('bookmakers',[]) if data else []
            if bks and isinstance(bks[0],dict) and bks[0].get('markets'):
                stats['populated']+=1; stats['by_book'][bk]+=1
                saved.append((mid,bk))
            else:
                stats['empty']+=1
        rem=api.budget_snapshot().get('last_monthly_remaining')
        if (len(saved)) and len(saved)%20==0:
            print(f"progress: populated={stats['populated']} empty={stats['empty']} "
                  f"live_calls={stats['live_calls']} remaining={rem}")
    _dump(stats,saved)


def _dump(stats,saved):
    print("\n=== Pilot C fetch summary ===")
    print(json.dumps(stats, indent=2))
    json.dump({'stats':stats,'populated_pairs':saved,
               'live_requests_made':api.live_requests_made(),
               'budget':api.budget_snapshot()},
              open(PROGRESS,'w'), indent=2, default=str)
    print("saved", PROGRESS)


if __name__=='__main__':
    main()
