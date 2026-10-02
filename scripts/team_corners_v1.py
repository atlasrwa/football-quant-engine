#!/usr/bin/env python3
from __future__ import annotations
import argparse
import fcntl
import json
import os
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/handoff_out/team_corners_v1")
sys.path.insert(0, str(ROOT))
ENV = Path("/home/ubuntu/.config/qfe-v3/prototype.env")
LOCK = Path("/tmp/qfe_team_corners_v1.lock")

def load_env():
    if not ENV.exists():
        raise SystemExit("prototype env missing")
    for line in ENV.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, _, value = s.partition("=")
        os.environ[key.strip()] = value.strip().strip('"').strip("'")

def locked():
    fh = open(LOCK, "a+")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("QFE Team Corners V1 already running; clean skip")
    return fh
def main():
    load_env()
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    tick = sub.add_parser("tick")
    tick.add_argument("--force-discovery", action="store_true")
    sub.add_parser("status")
    args = parser.parse_args()
    from src.research.team_corners_v1.pipeline import status, tick as run_tick
    with locked():
        if args.cmd == "status":
            out = status()
        else:
            out = run_tick(force=args.force_discovery)
    print(json.dumps(out, indent=2, sort_keys=True, default=str))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
