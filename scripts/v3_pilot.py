#!/usr/bin/env python3
"""Operator entry point for the frozen QFE V3 prospective pilot."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from pathlib import Path

ROOT = Path("/home/ubuntu/handoff_out/v3_live_pilot")
sys.path.insert(0, str(ROOT))

PROTOTYPE_ENV = Path("/home/ubuntu/.config/qfe-v3/prototype.env")
LOCK_PATH = Path("/tmp/qfe_v3_pilot.lock")

def load_prototype_env() -> None:
    if not PROTOTYPE_ENV.exists():
        raise SystemExit("V3 prototype env missing; refusing live operation")
    for line in PROTOTYPE_ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ[key.strip()] = value.strip().strip('"').strip("'")

def _locked():
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fh = open(LOCK_PATH, "a+")
    try:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("V3 pilot already running; clean skip")
    return fh

def cmd_status() -> int:
    from src.research.v3_pilot import ledger
    from src.research.v3_pilot.config import load_scope
    from src.research.v3_pilot.freeze import freeze_hash
    print(json.dumps({
        "freeze_sha256": freeze_hash(),
        "competitions": len(load_scope()),
        "pilot": ledger.pilot_status(),
    }, indent=2, sort_keys=True))
    return 0

def cmd_canary() -> int:
    from src.research.prospective.api_contract import Endpoint, ProspectiveClientConfig
    from src.research.prospective.capture import ProspectiveApiClient
    from src.research.v3_pilot.config import MIN_REQUEST_INTERVAL_SECONDS
    from src.research.v3_pilot.provider import V3Provider
    cfg = ProspectiveClientConfig(
        rate_limit_seconds=MIN_REQUEST_INTERVAL_SECONDS,
        max_retries=1,
        timeout_seconds=30.0,
    )
    client = ProspectiveApiClient(config=cfg)
    payload = client.get(Endpoint.COVERAGE_LEAGUES)
    provider = V3Provider(request_cap=2)
    nations = provider.upcoming("comp_574977", hours=14*24)
    rl = client.last_rate_limit
    print(json.dumps({
        "auth_configured": client.is_configured,
        "coverage_rows": len((payload or {}).get("data", [])),
        "uefa_nations_upcoming_14d": len(nations),
        "monthly_remaining_after_canary": getattr(rl, "monthly_remaining", None),
        "minute_remaining_after_canary": getattr(rl, "minute_remaining", None),
    }, indent=2, sort_keys=True))
    return 0

def cmd_tick(force_discovery: bool) -> int:
    from src.research.v3_pilot.pipeline import tick
    with _locked():
        result = tick(force_discovery=force_discovery)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0

def cmd_settle() -> int:
    from src.research.v3_pilot.audit import refresh_audit_map
    from src.research.v3_pilot.legacy_settlement import settle_legacy_due
    from src.research.v3_pilot.pipeline import settle_due
    from src.research.v3_pilot.provider import V3Provider
    with _locked():
        provider = V3Provider()
        result = {
            "legacy": settle_legacy_due(provider),
            "v3": settle_due(provider),
            "audit": refresh_audit_map(),
        }
    print(json.dumps(result, indent=2, sort_keys=True, default=str))
    return 0

def cmd_audit() -> int:
    from src.research.v3_pilot.audit import build_map, refresh_audit_map
    refreshed = refresh_audit_map()
    obj = build_map()
    print(json.dumps({
        "artifact": refreshed,
        "summary": obj["summary"],
        "integrity": obj["integrity"],
    }, indent=2, sort_keys=True, default=str))
    return 0 if obj["integrity"]["status"] == "PASS" else 3

def cmd_telegram_test() -> int:
    from src.research.v3_pilot.telegram import send
    ok, detail = send(
        "QFE V3 PROTOTYPE\n"
        "Telegram route canary only — no prediction, no market signal."
    )
    print(json.dumps({"ok": ok, "detail": detail}, indent=2))
    return 0 if ok else 2

def main() -> int:
    load_prototype_env()
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("canary")
    tick_p = sub.add_parser("tick")
    tick_p.add_argument("--force-discovery", action="store_true")
    sub.add_parser("settle")
    sub.add_parser("audit")
    sub.add_parser("telegram-test")
    args = parser.parse_args()
    if args.cmd == "status":
        return cmd_status()
    if args.cmd == "canary":
        return cmd_canary()
    if args.cmd == "tick":
        return cmd_tick(args.force_discovery)
    if args.cmd == "settle":
        return cmd_settle()
    if args.cmd == "audit":
        return cmd_audit()
    if args.cmd == "telegram-test":
        return cmd_telegram_test()
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
