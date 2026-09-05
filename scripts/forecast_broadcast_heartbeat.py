#!/usr/bin/env python3
"""Forecast broadcast heartbeat — independent watchdog + Telegram alerter.

Successor to ``scripts/pilotC_heartbeat.py``, which was retired when Pilot C was
deprecated (see public_site/failure_ledger.json F024). This watches the T-8h forecast
broadcast engine instead.

THE DESIGN LESSON THIS INHERITS
===============================
Pilot C died for 98.7 hours with four reasonable monitors running. Three of them
consumed *self-reports* from components that were sincerely reporting success: a
missing API key raised ``SystemExit 2``, callers caught every ``SystemExit`` without
inspecting the code, and the failure was filed as a tidy budget stop. Every layer
said it was fine.

The one check that worked was the one that trusted nothing: **has the record actually
grown?** A stopped pipeline cannot fake an append.

So every check here observes ARTIFACTS — the append-only ledger, the delivery log,
the pending queue, the fixture universe, the provider budget file — and never asks a
component whether it is healthy. It is read-only against all of them; the only state
it owns is its own alert-dedup file.

CHECKS
======
  1. STALE FORECAST LEDGER  — the primary monitor. In-scope horizons have passed but
                              nothing was appended to broadcasts.jsonl. This is the
                              Pilot C lesson applied directly: it does not care what
                              the broadcaster thinks it did.
  2. COVERAGE GAP           — in-scope fixtures whose horizon passed with NO row at
                              all, or NOT_PUBLISHED rows accumulating. Pilot C's
                              equivalent (22 permanently missed pre-kickoff windows)
                              went unnoticed for four days.
  3. DELIVERY FAILURES      — a committed forecast repeatedly failing to send. The
                              queue never expires an envelope by design, so without
                              this check a forecast could retry forever in silence.
                              Alerts at 3 attempts, well before the 8 the verification
                              harness exercises.
  4. QUIET-HOURS HELD       — a forecast is being held by quiet hours. Suppression is
                              legitimate and must never cancel a send, but it must be
                              OBSERVABLE, so a held publish is reported rather than
                              silent. Escalates if it is still held after the window
                              should have closed.
  5. STALE FIXTURE UNIVERSE — no fresh fixture inflow. Without this the engine simply
                              runs out of fixtures and goes quiet, which would look
                              identical to a calm week.
  6. PROVIDER AUTH FAILURE  — the price layer recorded a PROVIDER FAILURE rather than
                              a clean budget stop. This is the exact failure that
                              killed Pilot C, now surfaced instead of swallowed.
  7. LOW QUOTA              — API-authoritative monthly remaining below threshold,
                              read from the x-monthly-quota-* headers recorded by
                              thestatsapi_client, not from any local counter.

A throttled all-clear heartbeat is emitted so that SILENCE IS ITSELF A SIGNAL: if
this channel goes quiet for longer than the heartbeat interval, the watchdog is down.

Alerts go to the HEARTBEAT_TELEGRAM_* channel — an ops channel, deliberately separate
from the forecast publication channel. Operational noise must not land in the feed
that publishes forecasts.

Usage:
    python3 scripts/forecast_broadcast_heartbeat.py               # normal tick
    python3 scripts/forecast_broadcast_heartbeat.py --dry-run     # evaluate, send nothing
    python3 scripts/forecast_broadcast_heartbeat.py --test-telegram
    python3 scripts/forecast_broadcast_heartbeat.py --force-heartbeat
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# ── paths (read-only against the pipeline; we own only our own state file) ────
HOME = Path("/home/ubuntu")
ENV_PATH = HOME / ".env"
RECORD_ROOT = Path(os.environ.get(
    "FORECAST_HB_RECORD_ROOT", str(HOME / "data" / "forecast_broadcast")))
BROADCAST_LEDGER = RECORD_ROOT / "broadcasts.jsonl"
DELIVERY_LOG = RECORD_ROOT / "delivery_log.jsonl"
PENDING_QUEUE = RECORD_ROOT / "pending_queue.jsonl"
SCOPE_CONFIG = Path(os.environ.get(
    "FORECAST_HB_SCOPE_CONFIG",
    str(HOME / "config" / "forecast_broadcast_scope.json")))
FIXTURE_LIST = Path(os.environ.get(
    "FORECAST_HB_FIXTURE_LIST",
    str(HOME / "data" / "thestatsapi" / "championship" / "_pilotC_fixture_list.json")))
PRICE_GAP_LOG = Path(os.environ.get(
    "FORECAST_HB_PRICE_GAP_LOG",
    str(HOME / "data" / "clv_panel" / "price_capture_gaps.jsonl")))
BUDGET_STATE = Path(os.environ.get(
    "FORECAST_HB_BUDGET_STATE",
    str(HOME / "data" / "thestatsapi" / "championship" / "_budget_state.json")))
STATE_PATH = Path(os.environ.get(
    "FORECAST_HB_STATE_PATH", str(RECORD_ROOT / "heartbeat_state.json")))

# ── thresholds (env-overridable so verification can force conditions) ────────
# The broadcaster ticks every 15 minutes. If an in-scope horizon has passed inside
# this window and the ledger has not grown, the publisher is not running.
STALE_LEDGER_HOURS = float(os.environ.get("FORECAST_HB_STALE_LEDGER_HOURS", "6"))
# Any in-scope fixture past its horizon with no row at all is a coverage hole.
MISSING_ROW_THRESHOLD = int(os.environ.get("FORECAST_HB_MISSING_ROW_THRESHOLD", "1"))
# NOT_PUBLISHED rows appearing faster than this inside the window is a real problem
# even though each row is individually honest.
NOT_PUBLISHED_WINDOW_HOURS = float(
    os.environ.get("FORECAST_HB_NOT_PUBLISHED_WINDOW_HOURS", "24"))
NOT_PUBLISHED_THRESHOLD = int(os.environ.get("FORECAST_HB_NOT_PUBLISHED_THRESHOLD", "3"))
# Alert on a stuck delivery well before the queue's own escalation at 5 and long
# before the 8 consecutive failures the verification harness proves survivable.
DELIVERY_ATTEMPT_THRESHOLD = int(
    os.environ.get("FORECAST_HB_DELIVERY_ATTEMPT_THRESHOLD", "3"))
# A quiet-hours hold that outlives the window by this much is no longer a quiet-hours
# delay — it means the flush is not happening.
QUIET_HOLD_ESCALATE_HOURS = float(
    os.environ.get("FORECAST_HB_QUIET_HOLD_ESCALATE_HOURS", "3"))
# Fixture inflow: the universe must be refreshed or the engine runs dry.
STALE_UNIVERSE_HOURS = float(os.environ.get("FORECAST_HB_STALE_UNIVERSE_HOURS", "36"))
# Provider failures (auth/config) recorded in the price gap log inside this window.
PROVIDER_FAILURE_WINDOW_HOURS = float(
    os.environ.get("FORECAST_HB_PROVIDER_FAILURE_WINDOW_HOURS", "24"))
LOW_QUOTA_THRESHOLD = int(os.environ.get("FORECAST_HB_LOW_QUOTA_THRESHOLD", "500"))
# Re-alert an ongoing, unresolved condition at most this often.
RENOTIFY_HOURS = float(os.environ.get("FORECAST_HB_RENOTIFY_HOURS", "6"))
# Emit the routine all-clear at most this often.
HEARTBEAT_EVERY_HOURS = float(os.environ.get("FORECAST_HB_EVERY_HOURS", "24"))

TELEGRAM_TIMEOUT = 15

SEV_ALERT = "ALERT"
SEV_NOTICE = "NOTICE"


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


def _read_jsonl(p: Path) -> list[dict]:
    """Read a JSONL artifact. Never writes, never repairs."""
    if not p.exists():
        return []
    out = []
    with open(p) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def _read_json(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        with open(p) as f:
            return json.load(f) or {}
    except Exception:
        return {}


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


def _hours(seconds: float) -> float:
    return round(seconds / 3600.0, 1)


# ── declared scope + fixture universe (both read independently) ──────────────
def _scope() -> dict:
    """Declared scope. Read directly, so a broken loader cannot hide the scope."""
    cfg = _read_json(SCOPE_CONFIG)
    comps = {str(lg.get("comp_id")) for lg in cfg.get("leagues", [])
             if lg.get("comp_id")}
    markets = [
        f"{m.get('market')}@{m.get('line')}" for m in cfg.get("markets", [])
    ]
    quiet = cfg.get("quiet_hours_utc") or {}
    return {
        "comp_ids": comps,
        "markets": markets,
        "horizon_hours": cfg.get("horizon_hours_before_kickoff"),
        "quiet_start": quiet.get("start_hour"),
        "quiet_end": quiet.get("end_hour"),
        "present": bool(cfg),
    }


def _universe() -> dict[str, dict]:
    meta = _read_json(FIXTURE_LIST).get("meta")
    return meta if isinstance(meta, dict) else {}


def _in_scope_past_horizon(now: float) -> list[tuple[str, dict, float]]:
    """In-scope fixtures whose horizon moment has passed, with that moment.

    Computed from the declared scope and the fixture universe — NOT from anything the
    broadcaster wrote. This is what makes the coverage check independent.
    """
    sc = _scope()
    horizon_h = sc["horizon_hours"]
    if not sc["comp_ids"] or not isinstance(horizon_h, (int, float)):
        return []
    out = []
    for fid, info in _universe().items():
        if str(info.get("comp")) not in sc["comp_ids"]:
            continue
        try:
            kickoff = float(info["ts"])
        except (KeyError, TypeError, ValueError):
            continue
        horizon_at = kickoff - float(horizon_h) * 3600.0
        if now >= horizon_at:
            out.append((str(fid), info, horizon_at))
    return out


def _ledger_rows() -> list[dict]:
    return _read_jsonl(BROADCAST_LEDGER)


def _newest_row_unix(rows: list[dict]) -> float | None:
    stamps = []
    for r in rows:
        for key in ("committed_at_utc", "recorded_at_utc"):
            u = _iso_to_unix(r.get(key))
            if u:
                stamps.append(u)
                break
    return max(stamps) if stamps else None


# ── quota (API-authoritative) ────────────────────────────────────────────────
def _read_monthly_quota() -> dict:
    """API-authoritative monthly quota from the x-monthly-quota-* headers.

    Not the lifetime local request counter, which drifts from the API's own reset.
    """
    out = {"remaining": None, "limit": None, "reset": None, "updated_at": None}
    st = _read_json(BUDGET_STATE)
    if not st:
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


# ── checks ───────────────────────────────────────────────────────────────────
def check_stale_forecast_ledger(state: dict) -> dict | None:
    """THE primary monitor: horizons passed, but the record did not grow.

    Deliberately makes no use of any status file, exit code, or summary the
    broadcaster produced. It compares the independent fixture universe against the
    append-only ledger, because that is the only comparison a silently-broken
    component cannot fake.
    """
    now = _now()
    sc = _scope()
    if not sc["present"]:
        return {
            "severity": SEV_ALERT,
            "title": "SCOPE CONFIG MISSING",
            "detail": (f"Declared scope not readable at {SCOPE_CONFIG}. The "
                       "broadcaster cannot run and coverage cannot be verified."),
            "metrics": {"path": str(SCOPE_CONFIG)},
        }

    due = _in_scope_past_horizon(now)
    # Only judge staleness inside an ACTIVE fixture period. A genuinely empty slate
    # must not look like an outage, or the alert becomes noise and gets ignored —
    # which is how a real one gets missed.
    recent = [d for d in due if now - d[2] <= STALE_LEDGER_HOURS * 3600]
    if not recent:
        return None

    rows = _ledger_rows()
    newest = _newest_row_unix(rows)
    if newest is None:
        return {
            "severity": SEV_ALERT,
            "title": "STALE FORECAST LEDGER (nothing ever written)",
            "detail": (
                f"{len(recent)} in-scope fixture(s) passed the T-{sc['horizon_hours']}h "
                f"horizon in the last {STALE_LEDGER_HOURS:g}h, but "
                f"{BROADCAST_LEDGER.name} contains no rows at all. The publisher is "
                "not running. This is the check that eventually caught Pilot C — it "
                "does not depend on any component reporting its own health."
            ),
            "metrics": {"horizons_passed_recently": len(recent),
                        "ledger_rows": len(rows)},
        }

    age_h = _hours(now - newest)
    if age_h >= STALE_LEDGER_HOURS:
        return {
            "severity": SEV_ALERT,
            "title": "STALE FORECAST LEDGER",
            "detail": (
                f"{len(recent)} in-scope fixture(s) passed the T-{sc['horizon_hours']}h "
                f"horizon in the last {STALE_LEDGER_HOURS:g}h, but the newest row in "
                f"{BROADCAST_LEDGER.name} is {age_h}h old (> {STALE_LEDGER_HOURS:g}h). "
                "Forecasts that should exist do not. Do not trust a 'clean run' "
                "summary here — check that the scheduler fired and that the provider "
                "credential is present."
            ),
            "metrics": {"newest_row_age_h": age_h,
                        "horizons_passed_recently": len(recent),
                        "ledger_rows": len(rows)},
        }
    return None


def check_coverage_gap(state: dict) -> dict | None:
    """In-scope fixtures with no row, or NOT_PUBLISHED rows accumulating.

    A fixture that simply vanished is indistinguishable from one that was never in
    scope, so 'no row at all' is the serious case. A NOT_PUBLISHED row is honest by
    itself, but a rising count means the engine is systematically failing to price
    its declared scope.
    """
    now = _now()
    due = _in_scope_past_horizon(now)
    if not due:
        return None
    rows = _ledger_rows()
    have = {str(r.get("fixture_id")) for r in rows}
    missing = [fid for fid, _info, _h in due if fid not in have]

    recent_np = []
    for r in rows:
        if r.get("record_type") != "NOT_PUBLISHED":
            continue
        u = _iso_to_unix(r.get("recorded_at_utc"))
        if u and now - u <= NOT_PUBLISHED_WINDOW_HOURS * 3600:
            recent_np.append(r)

    problems = []
    if len(missing) >= MISSING_ROW_THRESHOLD:
        problems.append(
            f"{len(missing)} in-scope fixture(s) passed the horizon with NO row at "
            f"all (neither a forecast nor a NOT_PUBLISHED record): "
            f"{', '.join(missing[:8])}{' …' if len(missing) > 8 else ''}"
        )
    if len(recent_np) >= NOT_PUBLISHED_THRESHOLD:
        reasons = sorted({str(r.get("reason", ""))[:90] for r in recent_np})
        problems.append(
            f"{len(recent_np)} NOT_PUBLISHED row(s) in the last "
            f"{NOT_PUBLISHED_WINDOW_HOURS:g}h. Reasons: {'; '.join(reasons[:3])}"
        )
    if not problems:
        return None
    return {
        "severity": SEV_ALERT,
        "title": "COVERAGE GAP",
        "detail": (
            " | ".join(problems)
            + ". Declared scope is what the record must cover; a gap here means the "
              "published record under-covers what was promised. Pilot C lost 22 "
              "fixtures to missed pre-kickoff windows and nobody noticed for four days."
        ),
        "metrics": {"missing_rows": len(missing),
                    "not_published_recent": len(recent_np),
                    "in_scope_past_horizon": len(due)},
    }


def check_delivery_failures(state: dict) -> dict | None:
    """A committed forecast repeatedly failing to send.

    The queue never expires an envelope — that is deliberate, because a forecast must
    not be dropped. The consequence is that without this check a forecast could retry
    forever with nobody watching.
    """
    pending = _read_jsonl(PENDING_QUEUE)
    stuck = [e for e in pending
             if int(e.get("attempts") or 0) >= DELIVERY_ATTEMPT_THRESHOLD]
    if not stuck:
        return None
    worst = max(stuck, key=lambda e: int(e.get("attempts") or 0))
    return {
        "severity": SEV_ALERT,
        "title": "DELIVERY FAILING",
        "detail": (
            f"{len(stuck)} committed forecast(s) have failed delivery at least "
            f"{DELIVERY_ATTEMPT_THRESHOLD} times and are still queued. They are NOT "
            "lost — the queue never discards — but they are not reaching anyone. "
            f"Worst: {str(worst.get('commitment_hash'))[:16]} after "
            f"{worst.get('attempts')} attempts, last error: "
            f"{str(worst.get('last_error'))[:160]}"
        ),
        "metrics": {"stuck": len(stuck), "queue_depth": len(pending),
                    "max_attempts": int(worst.get("attempts") or 0)},
    }


def check_quiet_hours_hold(state: dict) -> dict | None:
    """A forecast held by quiet hours — legitimate, but it must be visible.

    Quiet hours may delay a send and may never cancel it. Reported as a NOTICE while
    the window is plausibly still open, and escalated to an ALERT if the hold outlives
    the window, because at that point the queue flush is not happening.
    """
    pending = _read_jsonl(PENDING_QUEUE)
    if not pending:
        return None
    events = _read_jsonl(DELIVERY_LOG)
    queued_hashes = {
        str(e.get("commitment_hash")) for e in events
        if e.get("status") == "QUEUED_QUIET_HOURS"
    }
    held = [e for e in pending
            if str(e.get("commitment_hash")) in queued_hashes
            and int(e.get("attempts") or 0) < DELIVERY_ATTEMPT_THRESHOLD]
    if not held:
        return None

    now = _now()
    sc = _scope()
    oldest = min((_iso_to_unix(e.get("enqueued_at_utc")) or now) for e in held)
    held_h = _hours(now - oldest)
    in_quiet = False
    qs, qe = sc.get("quiet_start"), sc.get("quiet_end")
    if isinstance(qs, int) and isinstance(qe, int) and qs != qe:
        hour = datetime.now(timezone.utc).hour
        in_quiet = (qs <= hour < qe) if qs <= qe else (hour >= qs or hour < qe)

    if not in_quiet and held_h >= QUIET_HOLD_ESCALATE_HOURS:
        return {
            "severity": SEV_ALERT,
            "title": "QUIET-HOURS HOLD NOT FLUSHING",
            "detail": (
                f"{len(held)} forecast(s) were held by quiet hours and are STILL "
                f"queued {held_h}h later, outside the {qs:02d}:00-{qe:02d}:00 UTC "
                "window. A suppressed forecast must be sent late, not left pending — "
                "the flush runs at the start of every tick, so either the scheduler "
                "is not firing or delivery is failing silently."
            ),
            "metrics": {"held": len(held), "held_hours": held_h,
                        "in_quiet_window": in_quiet},
        }
    return {
        "severity": SEV_NOTICE,
        "title": "QUIET-HOURS SUPPRESSION ACTIVE",
        "detail": (
            f"{len(held)} forecast(s) are held by quiet hours "
            f"({qs:02d}:00-{qe:02d}:00 UTC), oldest {held_h}h. They will be sent when "
            "the window closes, with their original generated_at_utc and commitment "
            "hash intact. Reported so a delayed publish is observable rather than "
            "silent; no action needed unless it persists past the window."
        ),
        "metrics": {"held": len(held), "held_hours": held_h,
                    "in_quiet_window": in_quiet},
    }


def check_stale_fixture_universe(state: dict) -> dict | None:
    """No fresh fixture inflow — the engine will quietly run dry.

    Pilot C's own warning was that a drained universe makes the loop fall silent while
    looking healthy. Without this check, 'no fixtures' and 'a quiet week' are the same
    observation.
    """
    meta = _read_json(FIXTURE_LIST)
    if not meta:
        return {
            "severity": SEV_ALERT,
            "title": "FIXTURE UNIVERSE MISSING",
            "detail": (f"No fixture universe at {FIXTURE_LIST}. The broadcaster has "
                       "nothing to publish and cannot detect its own emptiness."),
            "metrics": {"path": str(FIXTURE_LIST)},
        }
    generated = _iso_to_unix(meta.get("last_discovery") or meta.get("generated"))
    if generated is None:
        return None
    age_h = _hours(_now() - generated)
    if age_h < STALE_UNIVERSE_HOURS:
        return None
    sc = _scope()
    in_scope_future = 0
    now = _now()
    for info in (meta.get("meta") or {}).values():
        if str(info.get("comp")) in sc["comp_ids"]:
            try:
                if float(info["ts"]) > now:
                    in_scope_future += 1
            except (KeyError, TypeError, ValueError):
                continue
    return {
        "severity": SEV_ALERT,
        "title": "STALE FIXTURE UNIVERSE (no inflow)",
        "detail": (
            f"The fixture universe was last refreshed {age_h}h ago "
            f"(> {STALE_UNIVERSE_HOURS:g}h) and holds {in_scope_future} in-scope "
            "fixture(s) still ahead of kickoff. Inflow has stopped; once these drain "
            "the engine goes silent and that will look exactly like a calm week. NOTE: "
            "this universe was refreshed only by Pilot C's discovery phase, which was "
            "removed from cron on deprecation — it needs its own scheduled refresh."
        ),
        "metrics": {"universe_age_h": age_h,
                    "in_scope_upcoming": in_scope_future},
    }


def check_provider_auth_failure(state: dict) -> dict | None:
    """The price layer recorded a hard provider failure, not a clean budget stop.

    This is the Pilot C failure mode itself, promoted to a first-class alert. A clean
    budget stop is an accepted operational outcome and is NOT alerted; an auth or
    config failure is broken plumbing and is.
    """
    now = _now()
    rows = _read_jsonl(PRICE_GAP_LOG)
    recent = []
    for r in rows:
        u = _iso_to_unix(r.get("recorded_at_utc"))
        if not u or now - u > PROVIDER_FAILURE_WINDOW_HOURS * 3600:
            continue
        if "PROVIDER FAILURE" in str(r.get("reason", "")):
            recent.append(r)
    if not recent:
        return None
    reasons = sorted({str(r.get("reason"))[:120] for r in recent})
    return {
        "severity": SEV_ALERT,
        "title": "PROVIDER FAILURE (not a budget stop)",
        "detail": (
            f"{len(recent)} price capture(s) failed on auth/config in the last "
            f"{PROVIDER_FAILURE_WINDOW_HOURS:g}h — NOT a quota stop. "
            f"{'; '.join(reasons[:3])}. Forecasts still published (the layers are "
            "separate), but the CLV panel is not being filled. This is precisely the "
            "failure that killed Pilot C, except now it is labelled instead of being "
            "recorded as a clean stop. Most likely cause: THESTATS_API_KEY absent "
            "from cron's environment — it must be in /home/ubuntu/.env, not only in "
            "~/.bashrc."
        ),
        "metrics": {"provider_failures": len(recent)},
    }


def check_low_quota(state: dict) -> dict | None:
    """API-authoritative monthly remaining below threshold."""
    q = _read_monthly_quota()
    rem = q["remaining"]
    if rem is None:
        return None  # cannot assert low quota without the API's own number
    if rem >= LOW_QUOTA_THRESHOLD:
        return None
    return {
        "severity": SEV_ALERT,
        "title": "LOW QUOTA",
        "detail": (
            f"API-authoritative monthly remaining is {rem} (< {LOW_QUOTA_THRESHOLD}), "
            f"limit={q['limit']}, resets={q['reset']}. Source: x-monthly-quota-* "
            "headers, not a local counter. Price capture is the only metered consumer "
            "here; forecast publication is local and free, so forecasts continue "
            "regardless."
        ),
        "metrics": {"remaining": rem, "limit": q["limit"], "reset": q["reset"]},
    }


ALERT_CHECKS = [
    ("stale_forecast_ledger", check_stale_forecast_ledger),
    ("coverage_gap", check_coverage_gap),
    ("delivery_failures", check_delivery_failures),
    ("quiet_hours_hold", check_quiet_hours_hold),
    ("stale_fixture_universe", check_stale_fixture_universe),
    ("provider_auth_failure", check_provider_auth_failure),
    ("low_quota", check_low_quota),
]

TITLE_MAP = {
    "stale_forecast_ledger": "STALE FORECAST LEDGER",
    "coverage_gap": "COVERAGE GAP",
    "delivery_failures": "DELIVERY FAILING",
    "quiet_hours_hold": "QUIET-HOURS SUPPRESSION",
    "stale_fixture_universe": "STALE FIXTURE UNIVERSE",
    "provider_auth_failure": "PROVIDER FAILURE",
    "low_quota": "LOW QUOTA",
}


# ── Telegram ─────────────────────────────────────────────────────────────────
def send_telegram(text: str) -> tuple[bool, str]:
    """Send to the OPS channel. Never raises; the caller logs and moves on."""
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
            return True, f"ok message_id={obj.get('result', {}).get('message_id')}"
        return False, f"telegram not ok: {body[:200]}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"
    except Exception as e:  # noqa: BLE001 - transport must never raise
        return False, f"{type(e).__name__}: {str(e)[:200]}"


def _fmt_alert(a: dict, firing: bool) -> str:
    if not firing:
        head = "\u2705 RESOLVED"
    elif a.get("severity") == SEV_NOTICE:
        head = "\U0001F7E1 NOTICE"
    else:
        head = "\U0001F534 ALERT"
    lines = [f"{head}: forecast broadcast — {a['title']}", "", a["detail"]]
    if a.get("metrics"):
        lines += ["", "• " + "  ".join(f"{k}={v}" for k, v in a["metrics"].items())]
    lines += ["", f"host={os.uname().nodename}  at={_now_iso()}"]
    return "\n".join(lines)


# ── main tick ────────────────────────────────────────────────────────────────
def run_tick(dry_run: bool = False, force_heartbeat: bool = False) -> dict:
    load_env()
    state = load_state()
    alerts_state = state.setdefault("alerts", {})
    now = _now()
    summary: dict = {"fired": [], "resolved": [], "ongoing": [], "sent": [],
                     "errors": [], "notices": []}
    active_titles: list[str] = []

    for key, fn in ALERT_CHECKS:
        try:
            result = fn(state)
        except Exception as e:  # noqa: BLE001 - one check must not sink the tick
            summary["errors"].append(f"{key}: {type(e).__name__}: {str(e)[:150]}")
            continue

        prev = alerts_state.get(key, {})
        was_active = bool(prev.get("active"))

        if result is not None:
            if result.get("severity") == SEV_NOTICE:
                summary["notices"].append(key)
            else:
                active_titles.append(result["title"])
            last_notified = prev.get("last_notified_unix", 0) or 0
            should_send = (not was_active) or (
                now - last_notified >= RENOTIFY_HOURS * 3600)
            summary["fired" if not was_active else "ongoing"].append(key)
            if should_send:
                text = _fmt_alert(result, firing=True)
                if dry_run:
                    summary["sent"].append(f"[dry-run] {key}")
                    print(text)
                    print("-" * 60)
                else:
                    ok, info = send_telegram(text)
                    if ok:
                        summary["sent"].append(f"{key} ({info})")
                        prev["last_notified_unix"] = now
                    else:
                        summary["errors"].append(f"send {key}: {info}")
            prev.update({"active": True, "last_detail": result["detail"],
                         "last_severity": result.get("severity", SEV_ALERT),
                         "last_seen_unix": now})
            alerts_state[key] = prev
        else:
            if was_active:
                summary["resolved"].append(key)
                text = _fmt_alert(
                    {"title": TITLE_MAP.get(key, key),
                     "detail": "Condition has cleared.", "metrics": {}},
                    firing=False)
                if dry_run:
                    summary["sent"].append(f"[dry-run resolved] {key}")
                    print(text)
                    print("-" * 60)
                else:
                    ok, info = send_telegram(text)
                    if ok:
                        summary["sent"].append(f"resolved {key} ({info})")
                    else:
                        summary["errors"].append(f"send resolved {key}: {info}")
            alerts_state[key] = {
                "active": False, "last_seen_unix": now,
                "last_notified_unix": prev.get("last_notified_unix", 0)}

    # ── throttled all-clear, so silence is itself a signal ───────────────────
    last_hb = state.get("last_heartbeat_unix", 0) or 0
    due_hb = force_heartbeat or (now - last_hb >= HEARTBEAT_EVERY_HOURS * 3600)
    if due_hb and not active_titles:
        rows = _ledger_rows()
        committed = [r for r in rows if r.get("record_type") == "FORECAST_COMMITTED"]
        not_pub = [r for r in rows if r.get("record_type") == "NOT_PUBLISHED"]
        sent = [e for e in _read_jsonl(DELIVERY_LOG) if e.get("status") == "SENT"]
        newest = _newest_row_unix(rows)
        q = _read_monthly_quota()
        uni = _read_json(FIXTURE_LIST)
        uni_age = _iso_to_unix(uni.get("last_discovery") or uni.get("generated"))
        hb = "\n".join([
            "\U0001F49A forecast broadcast heartbeat — all clear",
            "",
            f"committed={len(committed)}  not_published={len(not_pub)}  "
            f"delivered={len(sent)}  queue={len(_read_jsonl(PENDING_QUEUE))}",
            f"newest_ledger_row="
            f"{datetime.fromtimestamp(newest, timezone.utc).isoformat() if newest else 'n/a'}",
            f"fixture_universe_age_h={_hours(now - uni_age) if uni_age else 'n/a'}",
            f"monthly_quota_remaining={q['remaining']}"
            + (f" (limit={q['limit']}, resets={q['reset']})" if q["limit"] is not None
               else " (limit/reset captured on next live API request)"),
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
    elif due_hb and active_titles:
        # Never send a routine all-clear while something is firing; the alert is the
        # signal, and an "all clear" beside it would teach the reader to ignore both.
        summary["heartbeat_suppressed_active"] = active_titles

    if not dry_run:
        save_state(state)
    summary["active_titles"] = active_titles
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Forecast broadcast heartbeat watchdog + Telegram alerter")
    ap.add_argument("--dry-run", action="store_true",
                    help="evaluate and print; send nothing, persist nothing")
    ap.add_argument("--force-heartbeat", action="store_true",
                    help="always emit the routine heartbeat if no alert is active")
    ap.add_argument("--test-telegram", action="store_true",
                    help="send one test message to confirm delivery, then exit")
    args = ap.parse_args()

    load_env()

    if args.test_telegram:
        ok, info = send_telegram(
            f"\U0001F9EA forecast broadcast heartbeat test — {_now_iso()} "
            f"(host={os.uname().nodename}). If you can read this, delivery works.")
        print(f"telegram test: ok={ok} info={info}")
        sys.exit(0 if ok else 1)

    summary = run_tick(dry_run=args.dry_run, force_heartbeat=args.force_heartbeat)
    print(json.dumps(summary, indent=2, default=str))
    if summary.get("errors"):
        sys.exit(1)


if __name__ == "__main__":
    main()
