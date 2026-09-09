#!/usr/bin/env python3
"""Research-status Telegram monitor for DATA ACCUMULATION MODE.

Reads ALREADY-PERSISTED operational/research state and sends compact status
messages to Telegram. It never calls TheStatsAPI (no quota cost) and never
publishes betting signals. Telegram failure never affects the collector.

Subcommands:
    heartbeat   Send the daily research heartbeat (deduped per UTC day) and any
                newly-crossed milestones + the readiness transition (once).
    alerts      Send event-driven CRITICAL alerts only when an operational
                condition is present (STALE_SCHEDULER / AUTH_FAILED /
                SCHEMA_DRIFT / QUOTA_LIMITED / dead collector). Deduplicated.
    weekly      Send the weekly coverage summary (deduped per ISO week).
    status      Print the current status snapshot as JSON (no send).

Usage:
    python3 scripts/research_monitor.py heartbeat
    python3 scripts/research_monitor.py alerts
    python3 scripts/research_monitor.py weekly
    python3 scripts/research_monitor.py status
    (add --dry-run to any send to print without sending / recording)

Credentials come from the environment (SIGNALS_/HEARTBEAT_ Telegram vars) via
the shared TelegramTransport; this script never reads or prints them.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.research.prospective.research_notify import (  # noqa: E402
    MessageType,
    ResearchStatus,
    collect_status,
    format_critical_alert,
    format_daily_heartbeat,
    format_milestone,
    format_readiness_transition,
    milestones_crossed,
)
from src.research.prospective.research_notify_delivery import (  # noqa: E402
    NotifyLedger,
    deliver,
)
from src.research.prospective.research_weekly import format_weekly_summary  # noqa: E402


#: Collector health states that warrant an immediate CRITICAL alert.
_CRITICAL_HEALTH = {"STALE_SCHEDULER", "AUTH_FAILED", "SCHEMA_DRIFT"}


def _emit(msg, *, ledger, dry_run):
    res = deliver(msg, ledger=ledger, dry_run=dry_run)
    tag = "DRY-RUN" if dry_run else ("SENT" if res.sent else ("DEDUP" if res.deduped else "NOT-SENT"))
    print(f"[{tag}] {res.message_type} {res.event_id}: {res.detail}")
    return res


def cmd_heartbeat(status: ResearchStatus, *, ledger: NotifyLedger, dry_run: bool) -> int:
    _emit(format_daily_heartbeat(status), ledger=ledger, dry_run=dry_run)
    # Milestones (deterministic + deduped by event id) for anything crossed.
    for metric, threshold in milestones_crossed(status):
        _emit(format_milestone(status, metric=metric, threshold=threshold),
              ledger=ledger, dry_run=dry_run)
    # Readiness transition ONLY when the frozen gate is fully met.
    if status.gate_met:
        _emit(format_readiness_transition(status), ledger=ledger, dry_run=dry_run)
    return 0


def cmd_alerts(status: ResearchStatus, *, ledger: NotifyLedger, dry_run: bool) -> int:
    reason: Optional[str] = None
    if status.collector_health in _CRITICAL_HEALTH:
        reason = status.collector_health
    elif status.collector_health == "QUOTA_LIMITED":
        reason = "QUOTA_LIMITED"
    if reason is None:
        print(f"[OK] collector={status.collector_health}; no critical condition")
        return 0
    _emit(format_critical_alert(status, reason=reason), ledger=ledger, dry_run=dry_run)
    return 0


def cmd_weekly(status: ResearchStatus, *, ledger: NotifyLedger, dry_run: bool) -> int:
    _emit(format_weekly_summary(status), ledger=ledger, dry_run=dry_run)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="research-monitor", description=__doc__)
    p.add_argument("--capture-root", type=Path, default=Path("data/prospective"))
    p.add_argument("--dry-run", action="store_true", help="print, do not send or record")
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("heartbeat", help="daily heartbeat + milestones + readiness transition")
    sub.add_parser("alerts", help="event-driven critical alerts only")
    sub.add_parser("weekly", help="weekly coverage summary")
    sub.add_parser("status", help="print status JSON (no send)")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    status = collect_status(capture_root=args.capture_root)
    if args.command == "status":
        print(json.dumps(status.to_dict(), indent=2, sort_keys=True))
        return 0
    ledger = NotifyLedger(path=Path(args.capture_root) / "notify_ledger.json")
    if args.command == "heartbeat":
        return cmd_heartbeat(status, ledger=ledger, dry_run=args.dry_run)
    if args.command == "alerts":
        return cmd_alerts(status, ledger=ledger, dry_run=args.dry_run)
    if args.command == "weekly":
        return cmd_weekly(status, ledger=ledger, dry_run=args.dry_run)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
