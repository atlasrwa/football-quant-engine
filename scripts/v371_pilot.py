#!/usr/bin/env python3
from __future__ import annotations
import argparse,fcntl,json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT))
ENV=Path('/home/ubuntu/.config/qfe-v3/prototype.env'); LOCK=Path('/tmp/qfe_v371_future50.lock')
def loadenv():
    if not ENV.exists(): raise SystemExit('prototype env missing')
    for line in ENV.read_text().splitlines():
        s=line.strip()
        if s and not s.startswith('#') and '=' in s:
            k,_,v=s.partition('='); os.environ[k.strip()]=v.strip().strip('"').strip("'")
def lock():
    f=open(LOCK,'a+'); fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB); return f
def main():
    loadenv(); ap=argparse.ArgumentParser(); sp=ap.add_subparsers(dest='cmd',required=True); sp.add_parser('status'); t=sp.add_parser('tick'); t.add_argument('--force-discovery',action='store_true'); sp.add_parser('telegram-test'); a=ap.parse_args()
    if a.cmd=='status':
        from src.research.v371_future50.pipeline import status; print(json.dumps(status(),indent=2,sort_keys=True)); return 0
    if a.cmd=='telegram-test':
        from src.research.v371_future50.telegram import send; ok,detail=send('QFE V3.7.1 FUTURE-50\nTelegram route canary only — no prediction or market signal.'); print(json.dumps({'ok':ok,'detail':detail},indent=2)); return 0 if ok else 2
    from src.research.v371_future50.pipeline import tick
    with lock(): r=tick(force=a.force_discovery)
    print(json.dumps(r,indent=2,sort_keys=True,default=str)); return 0
if __name__=='__main__': raise SystemExit(main())
