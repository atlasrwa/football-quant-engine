#!/usr/bin/env python3
from __future__ import annotations
import argparse, fcntl, json, os, sys
from pathlib import Path
ROOT=Path('/home/ubuntu/handoff_out/v3_1_goals_btts'); sys.path.insert(0,str(ROOT))
ENV=Path('/home/ubuntu/.config/qfe-v3/prototype.env'); LOCK=Path('/tmp/qfe_v31_pilot.lock')

def load_env():
    if not ENV.exists(): raise SystemExit('prototype env missing')
    for line in ENV.read_text().splitlines():
        line=line.strip()
        if line and not line.startswith('#') and '=' in line:
            k,_,v=line.partition('='); os.environ[k.strip()]=v.strip().strip('"').strip("'")
def locked():
    f=open(LOCK,'a+');
    try: fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit('V3.1 already running; clean skip')
    return f
def main():
    load_env(); p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True); sub.add_parser('status'); t=sub.add_parser('tick'); t.add_argument('--force-discovery',action='store_true'); sub.add_parser('settle'); sub.add_parser('telegram-test'); a=p.parse_args()
    if a.cmd=='status':
        from src.research.v31_pilot.freeze import freeze_hash
        from src.research.v31_pilot.config import load_scope,LEDGER_PATH
        from src.research.v31_pilot.pipeline import _declarations,_settled_ids
        print(json.dumps({'freeze_sha256':freeze_hash(),'competitions':len(load_scope()),'declarations':len(_declarations()),'settled':len(_settled_ids()),'ledger':str(LEDGER_PATH)},indent=2)); return 0
    if a.cmd=='tick':
        from src.research.v31_pilot.pipeline import tick
        with locked(): out=tick(force_discovery=a.force_discovery)
        print(json.dumps(out,indent=2,sort_keys=True,default=str)); return 0
    if a.cmd=='settle':
        from src.research.v31_pilot.pipeline import settle_due
        from src.research.v31_pilot.provider import V31Provider
        with locked(): out=settle_due(V31Provider())
        print(json.dumps(out,indent=2,sort_keys=True)); return 0
    if a.cmd=='telegram-test':
        from src.research.v31_pilot.telegram import send
        ok,detail=send('QFE V3.1 route canary only — no prediction, no market signal.'); print(json.dumps({'ok':ok,'detail':detail},indent=2)); return 0 if ok else 2
    return 2
if __name__=='__main__': raise SystemExit(main())
