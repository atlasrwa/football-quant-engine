#!/usr/bin/env python3
from __future__ import annotations
import fcntl,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
ENV=Path('/home/ubuntu/.config/qfe-v3/prototype.env'); LOCK=Path('/tmp/qfe_v38_legacy_close_settle.lock')
def loadenv():
    if not ENV.exists(): raise SystemExit('prototype env missing')
    for line in ENV.read_text().splitlines():
        s=line.strip()
        if s and not s.startswith('#') and '=' in s:
            k,_,v=s.partition('='); os.environ[k.strip()]=v.strip().strip('"').strip("'")
def main():
    loadenv()
    f=open(LOCK,'a+'); fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    from src.research.v38_paired50.pipeline import state,save,capture_final,settle,Provider
    s=state(); p=Provider(); final=capture_final(p,s); settled=settle(p,s); save(s)
    print(json.dumps({'mode':'LEGACY_CLOSE_SETTLE_ONLY','final_captures':final,'settlement_events':settled,'requests':p.requests},sort_keys=True))
    return 0
if __name__=='__main__': raise SystemExit(main())
