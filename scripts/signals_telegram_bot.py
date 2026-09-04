#!/usr/bin/env python3
"""Football Quant Engine — live signals Telegram broadcaster.

Reads the signals the engine produces (``data/results/live_signals.jsonl``,
written by ``python -m src.cli daily-signals``) and pushes any NEW ones to a
Telegram chat/channel. Read-only against the pipeline: it never mutates the
signals file; the only state it owns is its own dedup file
(``data/results/_signals_telegram_state.json``), so each signal is sent exactly
once across runs.

Designed to run on a schedule (cron / systemd timer) right after the
``daily-signals`` job, or ad-hoc. Uses only the Python standard library — same
transport pattern as ``scripts/pilotC_heartbeat.py``.

Signal record schema (from cli.cmd_daily_signals):
    match_id, date_unix, generated_at, league_id, season, prediction
    ("OVER"/"UNDER"), condition_strength, home_xg_eff, away_xg_eff, home_form,
    away_form, referee_volatility, over_odds, under_odds, status,
    production_enabled, forward_attested, immutable_price_provenance

Only records with a forward-validated delivery status and all three explicit
provenance gates are allowed to leave the research environment.

Config (env, loaded from /home/ubuntu/.env if present):
    SIGNALS_TELEGRAM_BOT_TOKEN   — bot token (required)
    SIGNALS_TELEGRAM_CHAT_ID     — destination chat id (falls back to
                                   HEARTBEAT_TELEGRAM_CHAT_ID)
    SIGNALS_FILE                 — override path to live_signals.jsonl
    SIGNALS_STATE_PATH           — override path to the dedup state file
    SIGNALS_MIN_STRENGTH         — only broadcast signals at/above this strength

Usage:
    python3 scripts/signals_telegram_bot.py                # send new signals
    python3 scripts/signals_telegram_bot.py --dry-run      # print, send nothing
    python3 scripts/signals_telegram_bot.py --test-telegram  # one test msg, exit
    python3 scripts/signals_telegram_bot.py --resend-all    # ignore dedup state
    python3 scripts/signals_telegram_bot.py --limit N       # cap messages this run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# ── paths ────────────────────────────────────────────────────────────────────
HOME = Path("/home/ubuntu")
ENV_PATH = HOME / ".env"
DATA_RESULTS = HOME / "data" / "results"
SIGNALS_FILE = Path(os.environ.get(
    "SIGNALS_FILE", str(DATA_RESULTS / "live_signals.jsonl")))
STATE_PATH = Path(os.environ.get(
    "SIGNALS_STATE_PATH", str(DATA_RESULTS / "_signals_telegram_state.json")))

TELEGRAM_TIMEOUT = 15


# ── env / io helpers ───────────────────────────────────────────────────────

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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def read_signals(path: Path) -> list[dict]:
    """Read all signal records from the JSONL file (skips malformed lines)."""
    if not path.exists():
        return []
    out: list[dict] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                # A malformed line should never sink the whole broadcast.
                continue
    return out


# ── signal identity + formatting ─────────────────────────────────────────────

def signal_key(sig: dict) -> str:
    """Stable, unique key for a signal so we send it exactly once.

    Combines match, prediction and generation time — regenerating the same match
    at a later time (fresh odds/features) is legitimately a new signal.
    """
    return "|".join(str(sig.get(k, "")) for k in (
        "match_id", "prediction", "generated_at"))


APPROVED_SIGNAL_STATUSES = frozenset({"FORWARD_VALIDATED", "PRODUCTION_VALIDATED"})


def delivery_eligibility(sig: dict) -> tuple[bool, tuple[str, ...]]:
    """Return whether a signal has the minimum evidence for bettor delivery.

    A condition-strength threshold is not validation.  Delivery is fail-closed:
    the producing path must explicitly attest to forward validation, production
    enablement, immutable pre-match price provenance, and a pre-kickoff commit.
    Historical/research records may remain in the JSONL file but are never sent.
    """
    reasons: list[str] = []
    if str(sig.get("status") or "") not in APPROVED_SIGNAL_STATUSES:
        reasons.append("unapproved_status")
    if sig.get("production_enabled") is not True:
        reasons.append("production_not_enabled")
    if sig.get("forward_attested") is not True:
        reasons.append("missing_forward_attestation")
    if sig.get("immutable_price_provenance") is not True:
        reasons.append("missing_immutable_price_provenance")
    generated_at = sig.get("generated_at")
    kickoff = sig.get("date_unix")
    try:
        generated = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
        if generated.tzinfo is None:
            raise ValueError("naive generated_at")
        if generated.timestamp() >= float(kickoff):
            reasons.append("not_committed_pre_kickoff")
    except (TypeError, ValueError, OSError):
        reasons.append("invalid_commit_timing")
    return not reasons, tuple(reasons)


def _fmt_number(value: object, places: int = 2, *, signed: bool = False) -> str:
    try:
        return f"{float(value):{ '+' if signed else ''}.{places}f}"
    except (TypeError, ValueError):
        return "n/a"


def _fmt_kickoff(date_unix: object) -> str:
    try:
        return datetime.fromtimestamp(int(date_unix), timezone.utc).strftime(
            "%a %d %b, %H:%M UTC")
    except (TypeError, ValueError, OSError):
        return "n/a"


def _fmt_generated_at(value: object) -> str:
    try:
        generated = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        return generated.astimezone(timezone.utc).strftime("%d %b, %H:%M UTC")
    except (TypeError, ValueError):
        return "n/a"


def _fmt_teams(sig: dict) -> str:
    home = str(sig.get("home_team") or sig.get("home") or "").strip()
    away = str(sig.get("away_team") or sig.get("away") or "").strip()
    if home and away:
        return f"{home} vs {away}"
    return f"Match {sig.get('match_id', 'n/a')}"


def format_signal(sig: dict) -> str:
    """Render a concise, bettor-facing Telegram message for one model signal."""
    pred = str(sig.get("prediction", "?")).upper()
    line = _fmt_number(sig.get("market_line", 2.5), 1)
    selected_odds = sig.get("over_odds") if pred == "OVER" else sig.get("under_odds")
    other_odds = sig.get("under_odds") if pred == "OVER" else sig.get("over_odds")
    other_side = "UNDER" if pred == "OVER" else "OVER"
    icon = "🟢" if pred == "OVER" else "🔵"
    try:
        strength_str = f"{float(sig.get('condition_strength')) * 100:.1f}%"
    except (TypeError, ValueError):
        strength_str = "n/a"

    lines = [
        f"{icon} BET SIGNAL",
        f"{_fmt_teams(sig)}",
        f"Kick-off: {_fmt_kickoff(sig.get('date_unix'))}",
        "",
        f"BET: {pred} {line} GOALS",
        f"PRICE: {_fmt_number(selected_odds)} decimal",
        f"Other side: {other_side} {line} @ {_fmt_number(other_odds)}",
        f"Model signal strength: {strength_str} (not a win probability)",
        "",
        "MODEL CONTEXT",
        f"xG trend (home / away): {_fmt_number(sig.get('home_xg_eff'), 3, signed=True)} / {_fmt_number(sig.get('away_xg_eff'), 3, signed=True)}",
        f"Form (home / away): {_fmt_number(sig.get('home_form'), 2)} / {_fmt_number(sig.get('away_form'), 2)}",
        f"Referee volatility: {_fmt_number(sig.get('referee_volatility'), 2)}",
        "",
        "Recheck the price, line-ups, and team news before betting.",
        f"Signal {sig.get('match_id', 'n/a')} • generated {_fmt_generated_at(sig.get('generated_at'))}",
    ]
    return "\n".join(lines)


# ── Telegram ─────────────────────────────────────────────────────────────────

def _chat_id() -> str | None:
    return (os.environ.get("SIGNALS_TELEGRAM_CHAT_ID")
            or os.environ.get("HEARTBEAT_TELEGRAM_CHAT_ID"))


def send_telegram(text: str) -> tuple[bool, str]:
    token = os.environ.get("SIGNALS_TELEGRAM_BOT_TOKEN")
    chat_id = _chat_id()
    if not token or not chat_id:
        return False, "SIGNALS_TELEGRAM_BOT_TOKEN / SIGNALS_TELEGRAM_CHAT_ID not set"
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


# ── main run ─────────────────────────────────────────────────────────────────

def run(dry_run: bool = False, resend_all: bool = False,
        limit: int | None = None) -> dict:
    load_env()
    min_strength = float(os.environ.get("SIGNALS_MIN_STRENGTH", "0") or 0)

    state = load_state()
    sent_keys = set(state.get("sent_keys", []))

    summary = {
        "signals_file": str(SIGNALS_FILE),
        "total_signals": 0,
        "already_sent": 0,
        "below_threshold": 0,
        "ineligible": 0,
        "ineligible_reasons": {},
        "to_send": 0,
        "sent": [],
        "errors": [],
    }

    signals = read_signals(SIGNALS_FILE)
    summary["total_signals"] = len(signals)
    if not signals:
        summary["note"] = f"No signals found at {SIGNALS_FILE}."
        return summary

    pending: list[tuple[str, dict]] = []
    for sig in signals:
        key = signal_key(sig)
        if not resend_all and key in sent_keys:
            summary["already_sent"] += 1
            continue
        eligible, reasons = delivery_eligibility(sig)
        if not eligible:
            summary["ineligible"] += 1
            for reason in reasons:
                summary["ineligible_reasons"][reason] = (
                    summary["ineligible_reasons"].get(reason, 0) + 1
                )
            continue
        try:
            strength = float(sig.get("condition_strength", 0) or 0)
        except (TypeError, ValueError):
            strength = 0.0
        if strength < min_strength:
            summary["below_threshold"] += 1
            continue
        pending.append((key, sig))

    if limit is not None:
        pending = pending[:limit]
    summary["to_send"] = len(pending)

    for key, sig in pending:
        text = format_signal(sig)
        if dry_run:
            summary["sent"].append(f"[dry-run] {key}")
            print(text)
            print("-" * 48)
            continue
        ok, info = send_telegram(text)
        if ok:
            summary["sent"].append(f"{key} ({info})")
            sent_keys.add(key)
        else:
            summary["errors"].append(f"send {key}: {info}")
            # Stop on first send failure so we don't hammer a broken endpoint;
            # unsent signals stay pending for the next run.
            break

    if not dry_run:
        state["sent_keys"] = sorted(sent_keys)
        state["last_run_at"] = _now_iso()
        save_state(state)

    return summary


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Broadcast football quant engine signals to Telegram.")
    ap.add_argument("--dry-run", action="store_true",
                    help="format and print pending signals; send nothing, persist nothing")
    ap.add_argument("--resend-all", action="store_true",
                    help="ignore dedup state and (re)send every signal in the file")
    ap.add_argument("--limit", type=int, default=None,
                    help="cap the number of messages sent this run")
    ap.add_argument("--test-telegram", action="store_true",
                    help="send a single test message to confirm delivery, then exit")
    args = ap.parse_args()

    load_env()

    if args.test_telegram:
        ok, info = send_telegram(
            f"\U0001F9EA Football signals bot test — {_now_iso()} "
            f"(host={os.uname().nodename}). If you can read this, delivery works.")
        print(f"telegram test: ok={ok} info={info}")
        sys.exit(0 if ok else 1)

    summary = run(dry_run=args.dry_run, resend_all=args.resend_all, limit=args.limit)
    print(json.dumps(summary, indent=2, default=str))
    sys.exit(1 if summary.get("errors") else 0)


if __name__ == "__main__":
    main()
