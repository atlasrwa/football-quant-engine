#!/usr/bin/env python3
"""Pilot C Heartbeat — RETIRED 2026-09-05. Superseded, kept as history.

    ┌──────────────────────────────────────────────────────────────────────────┐
    │ DEPRECATED. DO NOT RE-ENABLE.                                            │
    │                                                                          │
    │ Pilot C was closed on 2026-09-05 (public_site/failure_ledger.json F024,  │
    │ quarantine_enrollments.json experiment "pilot_c" status CLOSED). Its     │
    │ collection cron entries were removed and this watchdog's systemd timer   │
    │ (pilotc-heartbeat.timer) was stopped and disabled. A deprecated          │
    │ experiment must not page a human.                                        │
    │                                                                          │
    │ Three of its four checks are now meaningless: FLAT REVEALS and REPEATED  │
    │ EMPTY DISCOVERY describe a loop that no longer runs, and STALE LEDGER    │
    │ watches ledgers that are intentionally frozen — it would fire forever.   │
    │                                                                          │
    │ SUCCESSOR: scripts/forecast_broadcast_heartbeat.py                       │
    │            (forecast-broadcast-heartbeat.timer)                          │
    │                                                                          │
    │ This file is retained unmodified below because it is the component that  │
    │ actually caught the outage: its STALE LEDGER check was the only one of   │
    │ the four that did not consume a self-report, and it is the reason the    │
    │ successor's primary monitor is also stale-ledger. Deleting it would      │
    │ discard the evidence of what worked.                                     │
    └──────────────────────────────────────────────────────────────────────────┘

Original documentation follows.

Pilot C Heartbeat — independent watchdog + Telegram alerter.

This runs on its OWN schedule (systemd --user timer), completely independent of the
collection cron (scripts/pilotC_forward_loop.py). Its job is to answer one question
on every tick: "is the forward-collection loop silently broken?" and to shout over
Telegram the moment it is — because the single failure mode this whole pilot fears is
a working-LOOKING system that has quietly stopped collecting.

It observes the SAME artifacts the loop writes (ledgers, discovery status, budget
state) but never mutates them. Read-only against the pipeline; the only state it owns
is its own alert-dedup file (data/discovery/pilotC_heartbeat_state.json).

Four alerts (each de-duplicated so an ongoing condition does not spam every tick, and
each auto-resolves with a recovery notice when the condition clears):

  1. FLAT REVEALS      — finished, committed fixtures exist that should be settling,
                         but the reveal ledger has not grown for too long. The loop
                         looks alive (commits happen) yet nothing settles => the
                         readout will never arrive. Silent.
  2. STALE LEDGER      — neither ledger (commitments nor reveals) has been appended to
                         within the staleness window. The loop has stopped writing.
  3. REPEATED EMPTY    — fixture discovery has returned "empty" (reached the API, found
     DISCOVERY          zero settleable covered fixtures) for N consecutive discovery
                         runs. One empty run is legitimate (international break); a
                         persistent run of them means inflow has dried up and the
                         universe will drain.
  4. LOW QUOTA         — API-AUTHORITATIVE monthly remaining (from x-monthly-quota-limit
                         / x-monthly-quota-remaining, anchored to the x-monthly-quota-
                         reset window) has dropped below threshold. NOT the local
                         lifetime request counter, which drifts from the API's own
                         monthly reset.

A heartbeat is also emitted (throttled) so absence-of-heartbeat is itself detectable:
if Telegram goes quiet for longer than the heartbeat interval, the watchdog itself is
down.

Usage:
    python3 scripts/pilotC_heartbeat.py            # normal tick (send alerts + heartbeat)
    python3 scripts/pilotC_heartbeat.py --dry-run  # evaluate + print, send nothing
    python3 scripts/pilotC_heartbeat.py --test-telegram   # send one test message, exit
    python3 scripts/pilotC_heartbeat.py --force-heartbeat # always send the heartbeat line
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ── paths (read-only against the pipeline; we own only our own state file) ───
HOME = Path("/home/ubuntu")
ENV_PATH = HOME / ".env"
DATA_FWD = HOME / "data" / "forward"
COMMIT_LEDGER = Path(os.environ.get(
    "HEARTBEAT_COMMIT_LEDGER", str(DATA_FWD / "pilotC_commitments.jsonl")))
REVEAL_LEDGER = Path(os.environ.get(
    "HEARTBEAT_REVEAL_LEDGER", str(DATA_FWD / "pilotC_reveals.jsonl")))
DISCOVERY_STATUS = Path(os.environ.get(
    "HEARTBEAT_DISCOVERY_STATUS_PATH",
    str(HOME / "data" / "discovery" / "pilotC_discovery_status.json")))
DISCOVERY_LOG = Path(os.environ.get(
    "HEARTBEAT_DISCOVERY_LOG_PATH",
    str(HOME / "data" / "discovery" / "pilotC_discovery_log.jsonl")))
FIXTURE_LIST = Path(os.environ.get(
    "HEARTBEAT_FIXTURE_LIST",
    str(HOME / "data" / "thestatsapi" / "championship" / "_pilotC_fixture_list.json")))
BUDGET_STATE = Path(os.environ.get(
    "HEARTBEAT_BUDGET_STATE",
    str(HOME / "data" / "thestatsapi" / "championship" / "_budget_state.json")))
STATE_PATH = Path(os.environ.get(
    "HEARTBEAT_STATE_PATH",
    str(HOME / "data" / "discovery" / "pilotC_heartbeat_state.json")))

# ── thresholds (all env-overridable so verification can force conditions) ────
# Reveal-flatness: if committed+finished fixtures are waiting to settle and the reveal
# ledger has not grown in this many hours, the settle path is silently stuck.
FLAT_REVEAL_HOURS = float(os.environ.get("HEARTBEAT_FLAT_REVEAL_HOURS", "12"))
# Ledger staleness: neither ledger appended within this many hours => loop stopped.
STALE_LEDGER_HOURS = float(os.environ.get("HEARTBEAT_STALE_LEDGER_HOURS", "12"))
# Empty-discovery run of this length (consecutive "empty" discovery states) => inflow
# has dried up (one empty run is legitimate; a run of them is not).
EMPTY_DISCOVERY_STREAK = int(os.environ.get("HEARTBEAT_EMPTY_DISCOVERY_STREAK", "3"))
# Low-quota threshold against the API-authoritative monthly remaining.
LOW_QUOTA_THRESHOLD = int(os.environ.get("HEARTBEAT_LOW_QUOTA_THRESHOLD", "500"))
# Re-alert for an ongoing (un-resolved) condition at most this often (hours).
RENOTIFY_HOURS = float(os.environ.get("HEARTBEAT_RENOTIFY_HOURS", "6"))
# Emit the routine "all clear" heartbeat at most this often (hours).
HEARTBEAT_EVERY_HOURS = float(os.environ.get("HEARTBEAT_EVERY_HOURS", "24"))

TELEGRAM_TIMEOUT = 15


# ── env / io helpers ─────────────────────────────────────────────────────────

def load_env(path: Path = ENV_PATH) -> None:
    """Load KEY=VALUE lines into os.environ without overriding existing values."""
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _now() -> float:
    return time.time()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iso_to_unix(s) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _file_mtime(p: Path) -> float | None:
    try:
        return p.stat().st_mtime if p.exists() else None
    except Exception:
        return None


def _last_jsonl_record(p: Path) -> dict | None:
    """Return the last non-empty JSON object in a .jsonl file, or None."""
    if not p.exists():
        return None
    last = None
    try:
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line:
                    last = line
    except Exception:
        return None
    if last is None:
        return None
    try:
        return json.loads(last)
    except Exception:
        return None


def _count_lines(p: Path) -> int:
    if not p.exists():
        return 0
    n = 0
    with open(p) as f:
        for line in f:
            if line.strip():
                n += 1
    return n


def _count_unique_fixtures(p: Path) -> int:
    """Distinct fixture_ids in a ledger.

    The ledgers carry one line per prediction CELL (a fixture fans out into 5-6
    market/line cells), so raw line counts are not fixture counts. Operators reason
    in fixtures, so we report both and never let the line count masquerade as the
    fixture count.
    """
    if not p.exists():
        return 0
    seen = set()
    with open(p) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                fid = json.loads(line).get("fixture_id")
                if fid is not None:
                    seen.add(fid)
            except Exception:
                pass
    return len(seen)


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.load(open(STATE_PATH))
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    state["_updated_at"] = _now_iso()
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, STATE_PATH)


# ── ledger-latest helpers ─────────────────────────────────────────────────────

def _latest_commit_unix() -> float | None:
    rec = _last_jsonl_record(COMMIT_LEDGER)
    if rec:
        u = _iso_to_unix(rec.get("committed_at")) or rec.get("anchor_unix")
        if u:
            return float(u)
    return _file_mtime(COMMIT_LEDGER)


def _latest_reveal_unix() -> float | None:
    rec = _last_jsonl_record(REVEAL_LEDGER)
    if rec:
        u = (_iso_to_unix(rec.get("revealed_at"))
             or _iso_to_unix(rec.get("settled_at"))
             or rec.get("anchor_unix"))
        if u:
            return float(u)
    return _file_mtime(REVEAL_LEDGER)


_FINISHED = {"finished", "complete", "completed", "ft", "full-time", "ended"}


def _finished_committed_awaiting_reveal() -> int:
    """Count committed fixtures that appear finished but are not yet revealed.

    This is the precondition for the FLAT-REVEALS alert: reveal-flatness only matters
    when there is something that SHOULD be settling. If nothing is waiting, a flat
    reveal ledger is expected, not a fault.
    """
    committed = set()
    try:
        with open(COMMIT_LEDGER) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        committed.add(json.loads(line)["fixture_id"])
                    except Exception:
                        pass
    except Exception:
        return 0
    revealed = set()
    try:
        with open(REVEAL_LEDGER) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        revealed.add(json.loads(line)["fixture_id"])
                    except Exception:
                        pass
    except Exception:
        pass

    awaiting = committed - revealed
    if not awaiting:
        return 0

    # Cross-reference the fixture list for finished status / past kickoff.
    finished_awaiting = 0
    try:
        fx = json.load(open(FIXTURE_LIST))
        meta = fx.get("meta", {})
        now = _now()
        for mid in awaiting:
            row = meta.get(mid)
            if not row:
                continue
            status = str(row.get("status", "")).lower()
            ts = row.get("ts", 0) or 0
            # finished if the API says so, or kickoff is comfortably in the past (3h)
            if status in _FINISHED or (ts and ts < now - 3 * 3600):
                finished_awaiting += 1
    except Exception:
        # If we cannot read the fixture list, fall back to "there is a backlog waiting"
        return len(awaiting)
    return finished_awaiting


# ── quota (API-authoritative) ─────────────────────────────────────────────────

def _read_monthly_quota() -> dict:
    """Read the API-authoritative monthly quota window from budget state.

    Source of truth is x-monthly-quota-remaining / x-monthly-quota-limit anchored to
    x-monthly-quota-reset, recorded by thestatsapi_client on every live response — NOT
    the lifetime total_live_requests counter.
    """
    out = {"remaining": None, "limit": None, "reset": None, "updated_at": None,
           "source": "monthly_quota_headers"}
    if not BUDGET_STATE.exists():
        return out
    try:
        st = json.load(open(BUDGET_STATE))
    except Exception:
        return out

    def _to_int(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    out["remaining"] = _to_int(st.get("last_monthly_remaining"))
    out["limit"] = _to_int(st.get("last_monthly_limit"))
    out["reset"] = st.get("last_monthly_reset")
    out["updated_at"] = st.get("monthly_quota_updated_at") or st.get("updated_at")
    return out


# ── alert detectors ───────────────────────────────────────────────────────────

def check_flat_reveals(state: dict) -> dict | None:
    awaiting = _finished_committed_awaiting_reveal()
    last_reveal = _latest_reveal_unix()
    now = _now()
    if awaiting <= 0:
        return None  # nothing should be settling => flat ledger is not a fault
    age_h = (now - last_reveal) / 3600.0 if last_reveal else None
    if age_h is not None and age_h > FLAT_REVEAL_HOURS:
        return {
            "title": "FLAT REVEALS",
            "detail": (f"{awaiting} finished+committed fixture(s) are waiting to settle "
                       f"but the reveal ledger has not grown in {age_h:.1f}h "
                       f"(> {FLAT_REVEAL_HOURS:g}h). Commits look alive, settlement is "
                       f"silently stuck — the readout will never arrive."),
            "metrics": {"finished_committed_awaiting": awaiting,
                        "reveal_ledger_age_hours": round(age_h, 1),
                        "threshold_hours": FLAT_REVEAL_HOURS},
        }
    return None


def check_stale_ledger(state: dict) -> dict | None:
    lc = _latest_commit_unix()
    lr = _latest_reveal_unix()
    newest = max([t for t in (lc, lr) if t], default=None)
    now = _now()
    if newest is None:
        return {
            "title": "STALE LEDGER",
            "detail": ("Neither the commitment nor the reveal ledger exists / is "
                       "readable. The collection loop has written nothing."),
            "metrics": {"commit_ledger_exists": COMMIT_LEDGER.exists(),
                        "reveal_ledger_exists": REVEAL_LEDGER.exists()},
        }
    age_h = (now - newest) / 3600.0
    if age_h > STALE_LEDGER_HOURS:
        return {
            "title": "STALE LEDGER",
            "detail": (f"No ledger activity for {age_h:.1f}h (> {STALE_LEDGER_HOURS:g}h). "
                       f"Neither commitments nor reveals have been appended — the "
                       f"collection loop appears to have stopped running."),
            "metrics": {"ledger_age_hours": round(age_h, 1),
                        "threshold_hours": STALE_LEDGER_HOURS,
                        "last_commit": datetime.fromtimestamp(lc, timezone.utc).isoformat() if lc else None,
                        "last_reveal": datetime.fromtimestamp(lr, timezone.utc).isoformat() if lr else None},
        }
    return None


def _empty_discovery_streak() -> tuple[int, int]:
    """Return (consecutive_empty_at_tail, total_runs_considered) from the discovery log.

    Walks the discovery log newest-first and counts how many of the most recent runs
    are "empty" before hitting a non-empty ("found"/"failed") run. Falls back to the
    single current status file if the log is unavailable.
    """
    states: list[str] = []
    if DISCOVERY_LOG.exists():
        try:
            with open(DISCOVERY_LOG) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        states.append(json.loads(line).get("state", ""))
                    except Exception:
                        pass
        except Exception:
            states = []
    if not states:
        st = {}
        try:
            if DISCOVERY_STATUS.exists():
                st = json.load(open(DISCOVERY_STATUS))
        except Exception:
            st = {}
        s = st.get("state")
        states = [s] if s else []

    streak = 0
    for s in reversed(states):
        if s == "empty":
            streak += 1
        else:
            break
    return streak, len(states)


def check_repeated_empty_discovery(state: dict) -> dict | None:
    streak, total = _empty_discovery_streak()
    if streak >= EMPTY_DISCOVERY_STREAK:
        return {
            "title": "REPEATED EMPTY DISCOVERY",
            "detail": (f"Fixture discovery has returned EMPTY (API reached, zero "
                       f"settleable covered fixtures) for {streak} consecutive runs "
                       f"(>= {EMPTY_DISCOVERY_STREAK}). One empty run is legitimate "
                       f"(international break); this many means inflow has dried up and "
                       f"the fixture universe will drain."),
            "metrics": {"consecutive_empty_runs": streak,
                        "threshold": EMPTY_DISCOVERY_STREAK,
                        "discovery_runs_logged": total},
        }
    return None


def check_low_quota(state: dict) -> dict | None:
    q = _read_monthly_quota()
    rem = q["remaining"]
    if rem is None:
        return None  # cannot assert low quota without the API's own number
    if rem < LOW_QUOTA_THRESHOLD:
        pct = (100.0 * rem / q["limit"]) if q["limit"] else None
        return {
            "title": "LOW QUOTA",
            "detail": (f"API-authoritative monthly quota is low: {rem} requests "
                       f"remaining (< {LOW_QUOTA_THRESHOLD})"
                       + (f" of {q['limit']} ({pct:.1f}% left)" if q["limit"] else "")
                       + (f", resets {q['reset']}" if q["reset"] else "")
                       + ". Source: x-monthly-quota-* headers (not the lifetime "
                         "counter)."),
            "metrics": {"monthly_remaining": rem, "monthly_limit": q["limit"],
                        "monthly_reset": q["reset"], "threshold": LOW_QUOTA_THRESHOLD,
                        "source": "x-monthly-quota-* (API-authoritative)"},
        }
    return None


ALERT_CHECKS = [
    ("flat_reveals", check_flat_reveals),
    ("stale_ledger", check_stale_ledger),
    ("repeated_empty_discovery", check_repeated_empty_discovery),
    ("low_quota", check_low_quota),
]


# ── Telegram ───────────────────────────────────────────────────────────────

def send_telegram(text: str) -> tuple[bool, str]:
    token = os.environ.get("HEARTBEAT_TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("HEARTBEAT_TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "HEARTBEAT_TELEGRAM_BOT_TOKEN / HEARTBEAT_TELEGRAM_CHAT_ID not set"
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "disable_web_page_preview": "true",
    }).encode()
    req = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TELEGRAM_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        obj = json.loads(body)
        if obj.get("ok"):
            mid = obj.get("result", {}).get("message_id")
            return True, f"ok message_id={mid}"
        return False, f"telegram not ok: {body[:200]}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:200]}"


def _fmt_alert(a: dict, firing: bool) -> str:
    head = ("\U0001F534 ALERT" if firing else "\u2705 RESOLVED")  # 🔴 / ✅
    lines = [f"{head}: Pilot C — {a['title']}", "", a["detail"]]
    m = a.get("metrics")
    if m:
        lines.append("")
        lines.append("• " + "  ".join(f"{k}={v}" for k, v in m.items()))
    lines.append("")
    lines.append(f"host={os.uname().nodename}  at={_now_iso()}")
    return "\n".join(lines)


# ── main tick ──────────────────────────────────────────────────────────────

def run_tick(dry_run: bool = False, force_heartbeat: bool = False) -> dict:
    load_env()
    state = load_state()
    alerts_state = state.setdefault("alerts", {})
    now = _now()
    summary = {"fired": [], "resolved": [], "ongoing": [], "sent": [], "errors": []}

    active_titles = []
    for key, fn in ALERT_CHECKS:
        try:
            result = fn(state)
        except Exception as e:
            summary["errors"].append(f"{key}: {type(e).__name__}: {str(e)[:150]}")
            continue

        prev = alerts_state.get(key, {})
        was_active = bool(prev.get("active"))

        if result is not None:
            active_titles.append(result["title"])
            last_notified = prev.get("last_notified_unix", 0) or 0
            should_send = (not was_active) or (now - last_notified >= RENOTIFY_HOURS * 3600)
            if not was_active:
                summary["fired"].append(key)
            else:
                summary["ongoing"].append(key)
            if should_send:
                text = _fmt_alert(result, firing=True)
                if dry_run:
                    summary["sent"].append(f"[dry-run] {key}")
                    print(text)
                    print("-" * 40)
                else:
                    ok, info = send_telegram(text)
                    if ok:
                        summary["sent"].append(f"{key} ({info})")
                        prev["last_notified_unix"] = now
                    else:
                        summary["errors"].append(f"send {key}: {info}")
            prev["active"] = True
            prev["last_detail"] = result["detail"]
            prev["last_seen_unix"] = now
            alerts_state[key] = prev
        else:
            if was_active:
                # condition cleared -> recovery notice
                summary["resolved"].append(key)
                rec = {"title": prev.get("title") or key.replace("_", " ").upper(),
                       "detail": "Condition has cleared.",
                       "metrics": {}}
                # fill a readable title
                title_map = {
                    "flat_reveals": "FLAT REVEALS",
                    "stale_ledger": "STALE LEDGER",
                    "repeated_empty_discovery": "REPEATED EMPTY DISCOVERY",
                    "low_quota": "LOW QUOTA",
                }
                rec["title"] = title_map.get(key, key)
                text = _fmt_alert(rec, firing=False)
                if dry_run:
                    summary["sent"].append(f"[dry-run resolved] {key}")
                    print(text)
                    print("-" * 40)
                else:
                    ok, info = send_telegram(text)
                    if ok:
                        summary["sent"].append(f"resolved {key} ({info})")
                    else:
                        summary["errors"].append(f"send resolved {key}: {info}")
            alerts_state[key] = {"active": False, "last_seen_unix": now,
                                 "last_notified_unix": prev.get("last_notified_unix", 0)}

    # ── heartbeat (throttled) so silence itself is a signal ──────────────────
    last_hb = state.get("last_heartbeat_unix", 0) or 0
    due = force_heartbeat or (now - last_hb >= HEARTBEAT_EVERY_HOURS * 3600)
    if due and not active_titles:
        q = _read_monthly_quota()
        lc, lr = _latest_commit_unix(), _latest_reveal_unix()
        commit_cells = _count_lines(COMMIT_LEDGER)
        reveal_cells = _count_lines(REVEAL_LEDGER)
        commit_fixtures = _count_unique_fixtures(COMMIT_LEDGER)
        reveal_fixtures = _count_unique_fixtures(REVEAL_LEDGER)
        streak, _ = _empty_discovery_streak()
        if q["limit"] is not None:
            quota_line = (f"monthly_quota_remaining={q['remaining']} "
                          f"(limit={q['limit']}, resets={q['reset']})")
        else:
            # Limit/reset are recorded from x-monthly-quota-* headers on the next live
            # API request; until then only 'remaining' is known. Say so plainly rather
            # than printing a misleading null.
            quota_line = (f"monthly_quota_remaining={q['remaining']} "
                          f"(limit/reset not yet captured — populated on next live "
                          f"API request)")
        hb = "\n".join([
            "\U0001F49A Pilot C heartbeat — all clear",  # 💚
            "",
            f"commitments={commit_fixtures} fixtures ({commit_cells} cells)  "
            f"reveals={reveal_fixtures} fixtures ({reveal_cells} cells)",
            f"last_commit={datetime.fromtimestamp(lc, timezone.utc).isoformat() if lc else 'n/a'}",
            f"last_reveal={datetime.fromtimestamp(lr, timezone.utc).isoformat() if lr else 'n/a'}",
            quota_line,
            f"empty_discovery_streak={streak}",
            "",
            f"host={os.uname().nodename}  at={_now_iso()}",
        ])
        if dry_run:
            summary["sent"].append("[dry-run] heartbeat")
            print(hb)
        else:
            ok, info = send_telegram(hb)
            if ok:
                summary["sent"].append(f"heartbeat ({info})")
                state["last_heartbeat_unix"] = now
            else:
                summary["errors"].append(f"send heartbeat: {info}")
    elif due and active_titles:
        # Don't send a routine "all clear" while something is actively firing; the
        # alert itself is the signal. Defer the next clear heartbeat.
        summary["heartbeat_suppressed_active"] = active_titles

    if not dry_run:
        save_state(state)
    summary["active_titles"] = active_titles
    return summary


def main():
    ap = argparse.ArgumentParser(description="Pilot C heartbeat watchdog + Telegram alerter")
    ap.add_argument("--dry-run", action="store_true",
                    help="evaluate and print; send nothing, persist nothing")
    ap.add_argument("--force-heartbeat", action="store_true",
                    help="always emit the routine heartbeat this tick (if no alert active)")
    ap.add_argument("--test-telegram", action="store_true",
                    help="send a single test message to confirm delivery, then exit")
    args = ap.parse_args()

    load_env()

    if args.test_telegram:
        ok, info = send_telegram(
            f"\U0001F9EA Pilot C heartbeat test message — {_now_iso()} "
            f"(host={os.uname().nodename}). If you can read this, delivery works.")
        print(f"telegram test: ok={ok} info={info}")
        sys.exit(0 if ok else 1)

    summary = run_tick(dry_run=args.dry_run, force_heartbeat=args.force_heartbeat)
    print(json.dumps(summary, indent=2, default=str))
    if summary.get("errors"):
        sys.exit(1)


if __name__ == "__main__":
    main()
