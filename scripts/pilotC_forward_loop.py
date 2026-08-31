#!/usr/bin/env python3
"""Pilot C Forward Loop — scheduled orchestrator for the near-fair-reference edge test.

This is the cron-triggered entry point for Pilot C. It runs the full cycle:

    discover upcoming covered-league fixtures (INFLOW) -> refresh fixture statuses
    -> fetch multi-book odds (covered-league biased) -> predict + COMMIT before
    kickoff -> SETTLE + REVEAL finished fixtures

It is a thin orchestrator: the real work lives in the existing, tested modules
(pilotC_fixture_discovery, pilotC_multibook_fetch, pilotC_forward_predict,
pilotC_settle). This file wires them into one idempotent, quota-capped,
crash-recoverable, LOUDLY-observable loop — mirroring the corners/cards Pipeline A
(scripts/quarantine_forward_loop.py).

FIXTURE DISCOVERY (Phase 0) is the inflow that keeps the loop from draining its
fixture universe to empty. Without it, cron fires every 6 hours, finds nothing, and
reports zero activity indefinitely — a working-looking system with no fixtures. It
runs on a weekly/twice-weekly cadence (Mon/Thu by default), is cache-first, and is
restricted to the four covered leagues (Championship, EPL, Ligue 2, La Liga 2). Its
three outcomes — found / empty / failed — are reported distinctly in the health
report so a silent inflow failure can never masquerade as a quiet-but-healthy week.

DISTINCT FROM PIPELINE A. Pilot C is a separate experiment with its own
pre-registration and its own ledger (data/forward/pilotC_commitments.jsonl /
pilotC_reveals.jsonl). Nothing here touches Pipeline A's ledger
(data/forward/commitments.jsonl). The two must never be pooled.

NON-NEGOTIABLE: the pre-kickoff commit window is unrecoverable. The ledger refuses
to commit after kickoff and never backdates. A missed window is permanent sample
loss, logged as such. Predict+commit must run comfortably before kickoff — a
6-hourly schedule gives margin for a failed run without losing the window.

Guarantees:
  * Idempotent — re-running commits no duplicates (predict skips already-committed
    pred_ids; settle skips already-revealed), and all fetches are cache-first.
  * Quota-capped — a hard per-run live-request cap via THESTATS_MAX_REQUESTS; the
    client aborts cleanly (SystemExit) rather than exhausting the monthly budget.
  * Crash-recoverable — each phase is isolated; a phase that dies is logged and the
    run continues to the next phase and the next scheduled run picks up cleanly.
  * Loud — every phase logs counts; WARNING/ERROR on run failure, missed pre-kickoff
    windows, low quota, or a ledger chain-verification failure. A zero-fixture run
    says so explicitly (silence is the failure mode we refuse).

Usage:
    python3 scripts/pilotC_forward_loop.py                 # full cycle
    python3 scripts/pilotC_forward_loop.py --settle-only   # daily settle pass
    python3 scripts/pilotC_forward_loop.py --health        # emit health report only

Cron (see also install: scripts/install_pilotC_cron.sh):
    # NOTE: use the VENV python (/home/ubuntu/.venv/bin/python) — Pilot C's predictor
    # AND the discovery settleability gate both need sklearn, which lives only in the
    # venv, NOT in /usr/bin/python3. Running under system python silently DISABLES the
    # corpus/settleability gate. install_pilotC_cron.sh wires the venv interpreter.
    0 */6 * * *  cd /home/ubuntu && /home/ubuntu/.venv/bin/python scripts/pilotC_forward_loop.py              >> logs/pilotC_loop.log 2>&1
    30 3 * * *   cd /home/ubuntu && /home/ubuntu/.venv/bin/python scripts/pilotC_forward_loop.py --settle-only >> logs/pilotC_loop.log 2>&1
    0 8 * * 1    cd /home/ubuntu && /home/ubuntu/.venv/bin/python scripts/pilotC_forward_loop.py --health      >> logs/pilotC_loop.log 2>&1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

# Load environment (same pattern as Pipeline A) so cron has API keys.
_ENV_PATH = "/home/ubuntu/.env"
if os.path.exists(_ENV_PATH):
    with open(_ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# ── configuration ──────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] pilotC_loop: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pilotC_loop")

CH = Path("/home/ubuntu/data/thestatsapi/championship")
FIXTURE_LIST = CH / "_pilotC_fixture_list.json"
DATA_FWD = Path("/home/ubuntu/data/forward")
RUN_LOG = DATA_FWD / "pilotC_run_log.jsonl"
HEALTH_REPORT = Path("/home/ubuntu/data/discovery/pilotC_health_report.json")
COMMIT_LEDGER = DATA_FWD / "pilotC_commitments.jsonl"
REVEAL_LEDGER = DATA_FWD / "pilotC_reveals.jsonl"
# Discovery status file (written by pilotC_fixture_discovery) — the health report
# reads this to distinguish "found" / "empty" / "failed", which must never look alike.
DISCOVERY_STATUS = Path("/home/ubuntu/data/discovery/pilotC_discovery_status.json")
# Discovery runs on a subset of cycles (it is a weekly/twice-weekly concern, not
# every 6 hours). By default run discovery when the current UTC weekday is Monday or
# Thursday (twice weekly) — cheap and cache-first, so a stray extra run is harmless.
# Set PILOTC_DISCOVERY_EVERY_RUN=1 to discover on every cycle (also fine — cache-first).
DISCOVERY_WEEKDAYS = {0, 3}  # Mon, Thu
# If the last successful discovery is older than this, discovery is considered STALE
# and the health report flags it (the loop is running but inflow may have stopped).
DISCOVERY_STALE_HOURS = int(os.environ.get("PILOTC_DISCOVERY_STALE_HOURS", "96"))

# Per-run hard cap on LIVE API requests. Covered upcoming fixtures are ~10/week
# across 3 books = ~30 requests, plus settlement fetches (2/finished fixture). A
# 6-hourly cadence means each run only needs a small slice; 120 is generous headroom
# while still protecting the monthly budget. Overridable via env.
PER_RUN_REQUEST_CAP = int(os.environ.get("PILOTC_RUN_CAP", "120"))
# Fixtures (not requests) to attempt fetching odds for per run.
MAX_FIXTURES_PER_RUN = int(os.environ.get("PILOTC_MAX_FIXTURES", "40"))
# Warn when the monthly budget dips below this.
LOW_QUOTA_WARN = int(os.environ.get("PILOTC_LOW_QUOTA_WARN", "500"))
# Pre-kickoff safety margin (hours) — matches Pipeline A. A covered fixture inside
# this window that is still uncommitted is flagged as an (imminent) missed window.
MIN_HOURS_BEFORE_KICKOFF = 2

# The 9 pre-registered market/line cells and the per-cell target (do NOT change —
# these mirror data/results/pilotC_preregistration.json).
PREREG_CELLS = [
    ("goals", 1.5), ("goals", 2.5), ("goals", 3.5),
    ("corners", 8.5), ("corners", 9.5), ("corners", 10.5),
    ("cards", 3.5), ("cards", 4.5), ("btts", None),
]
TARGET_N_PER_CELL = 385
ORIGINAL_WEEKS_PROJECTION = 38.5  # from the hardening plan, for slippage comparison
# The hardening plan's projection assumed ~10 covered fixtures/week of inflow. We
# measure the ACTUAL inflow (from the discovery window) and compare, because the
# ~38.5-week estimate depends on this assumption holding.
ASSUMED_COVERED_INFLOW_PER_WEEK = float(
    os.environ.get("PILOTC_ASSUMED_INFLOW_PER_WEEK", "10"))
# Loop commit start (first commitment made under the scheduler). The "first full
# week after discovery is live" ratio is the real steady-state measure — the 0.18
# in the plan reflects the UNSCHEDULED gap, not steady-state performance.
DISCOVERY_LIVE_SINCE = os.environ.get("PILOTC_DISCOVERY_LIVE_SINCE")  # ISO date, optional

_FINISHED = {"finished", "complete", "completed", "ft", "full-time", "ended"}


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _iso_to_unix(s):
    """Parse an ISO-8601 timestamp to a unix float, tolerant of a trailing Z."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def _persist_run_log(record: dict) -> None:
    RUN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(RUN_LOG, "a") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _quota_remaining():
    try:
        import thestatsapi_client as api
        rem = api.budget_snapshot().get("last_monthly_remaining")
        return int(rem) if rem is not None else None
    except Exception:
        return None


def _verify_ledger_chain() -> tuple[bool, list[str]]:
    from src.research.forward.attestation_ledger import AttestationLedger
    led = AttestationLedger(commit_path=COMMIT_LEDGER, reveal_path=REVEAL_LEDGER)
    ok_c, prob_c = led.verify_chain(COMMIT_LEDGER)
    ok_r, prob_r = led.verify_chain(REVEAL_LEDGER)
    return (ok_c and ok_r), (prob_c + prob_r)


# ── phase: pre-kickoff window audit (LOUD about permanent sample loss) ───────

def _audit_missed_windows(stats: dict) -> None:
    """Flag covered fixtures whose kickoff has passed with no commitment.

    These are permanent sample loss — the ledger will never backdate them. Being
    loud here is the whole point: a silently-missed window is discovered months
    later as an inexplicably small sample.
    """
    if not FIXTURE_LIST.exists():
        return
    from src.research.forward.attestation_ledger import AttestationLedger
    import pilotC_stat_mixer as mix

    led = AttestationLedger(commit_path=COMMIT_LEDGER, reveal_path=REVEAL_LEDGER)
    committed_fixtures = {c["fixture_id"] for c in led.load_commitments()}

    try:
        ms = mix.load_corpus(); hist = mix.build_histories(ms)
        corpus_teams = set(hist.keys())
    except Exception as e:
        logger.warning("could not load corpus for window audit: %s", str(e)[:100])
        corpus_teams = set()

    meta = json.load(open(FIXTURE_LIST)).get("meta", {})
    now = time.time()
    missed = []
    imminent = []
    for mid, row in meta.items():
        home, away = row.get("home"), row.get("away")
        if corpus_teams and (home not in corpus_teams or away not in corpus_teams):
            continue  # only covered fixtures matter for the pre-reg sample
        ts = row.get("ts", 0)
        if mid in committed_fixtures:
            continue
        if ts and ts < now:
            missed.append((mid, home, away, ts))
        elif ts and ts < now + MIN_HOURS_BEFORE_KICKOFF * 3600:
            imminent.append((mid, home, away, ts))

    stats["covered_fixtures_missed_window"] = len(missed)
    stats["covered_fixtures_imminent_uncommitted"] = len(imminent)
    if missed:
        logger.warning(
            "PERMANENT SAMPLE LOSS: %d covered fixture(s) passed kickoff with NO "
            "pre-kickoff commitment (never backdated). Examples: %s",
            len(missed),
            ", ".join(f"{h} v {a}" for _, h, a, _ in missed[:3]),
        )
    if imminent:
        logger.warning(
            "%d covered fixture(s) kick off within %dh and are NOT yet committed — "
            "this run must commit them or the window is lost.",
            len(imminent), MIN_HOURS_BEFORE_KICKOFF,
        )


# ── phase runners (each isolated for crash-safety) ───────────────────────────

def _should_discover() -> bool:
    """Whether to run fixture discovery this cycle.

    Discovery is a weekly/twice-weekly concern (fixtures cluster on weekends), not a
    per-6-hour one. Default: run on Mon/Thu. It is cheap and cache-first, so running
    it more often is harmless — override with PILOTC_DISCOVERY_EVERY_RUN=1.
    """
    if os.environ.get("PILOTC_DISCOVERY_EVERY_RUN") == "1":
        return True
    return datetime.now(timezone.utc).weekday() in DISCOVERY_WEEKDAYS


def _phase_discover(stats: dict) -> None:
    """Discover upcoming covered-league fixtures and merge them into the universe.

    This is the inflow that keeps the loop from draining the universe to empty. It is
    isolated for crash-safety: a discovery failure is logged LOUDLY (a stalled inflow
    is exactly the silent failure this whole loop exists to prevent) but does not stop
    the rest of the cycle from processing whatever is already in the universe.
    """
    import pilotC_fixture_discovery as disc
    try:
        d = disc.discover(dry_run=False)
        stats["discovery"] = {
            "state": d.get("state"),
            "upcoming_in_window_seen": d.get("upcoming_fixtures_in_window_seen"),
            "covered_settleable_in_window": d.get("covered_settleable_fixtures_in_window"),
            "added": d.get("fixtures_added"),
            "refreshed": d.get("fixtures_refreshed_in_place"),
            "universe_size_after": d.get("universe_size_after"),
            "requests_used": d.get("requests", {}).get("live_requests_used_this_run"),
            "projected_weekly_requests": d.get("requests", {}).get("projected_weekly_request_consumption"),
        }
        state = d.get("state")
        if state == "found":
            logger.info("DISCOVERY: found %s upcoming covered fixtures in window "
                        "(added=%s, refreshed=%s, universe=%s, requests=%s).",
                        d.get("covered_settleable_fixtures_in_window"),
                        d.get("fixtures_added"), d.get("fixtures_refreshed_in_place"),
                        d.get("universe_size_after"),
                        d.get("requests", {}).get("live_requests_used_this_run"))
        elif state == "empty":
            logger.warning("DISCOVERY: ran and reached the API but found ZERO settleable "
                           "covered fixtures in the %s-day window. This CAN be legitimate "
                           "(e.g. international break) — it is NOT a failure, but watch for "
                           "it persisting.", d.get("window_days"))
        else:  # failed
            logger.error("DISCOVERY FAILED: did not complete a clean discovery run "
                         "(errors=%s). Inflow to the fixture universe may have STOPPED — "
                         "investigate before the universe drains.", d.get("errors", [])[:3])
            stats["errors"].append(f"discovery failed: {d.get('errors', [])[:2]}")
    except SystemExit as e:
        stats["discovery"] = {"state": "failed", "reason": f"SystemExit {e.code} (quota cap)"}
        logger.error("DISCOVERY stopped (SystemExit %s) — likely quota cap. Inflow at risk.", e.code)
        stats["errors"].append(f"discovery SystemExit {e.code}")
    except Exception as e:
        stats["discovery"] = {"state": "failed", "reason": f"{type(e).__name__}: {str(e)[:120]}"}
        logger.error("DISCOVERY crashed: %s — inflow at risk.", str(e)[:200])
        stats["errors"].append(f"discovery crash: {type(e).__name__}: {str(e)[:120]}")


def _phase_fetch_odds(stats: dict) -> None:
    """Fetch multi-book odds for covered-league fixtures, cache-first and capped."""
    os.environ["PILOTC_COVERED_ONLY"] = "1"
    os.environ["PILOTC_MAX_FIXTURES"] = str(MAX_FIXTURES_PER_RUN)
    os.environ["THESTATS_MAX_REQUESTS"] = str(PER_RUN_REQUEST_CAP)
    # thestatsapi_client reads the cap from env at import; ensure it reflects ours.
    import thestatsapi_client as api
    api.MAX_LIVE_REQUESTS = PER_RUN_REQUEST_CAP
    import pilotC_multibook_fetch as fetch
    try:
        fetch.main()
        stats["fetch_ok"] = True
    except SystemExit as e:
        # client hit the cap or an abort code — clean stop, not a crash
        stats["fetch_ok"] = False
        stats["errors"].append(f"fetch stopped (SystemExit {e.code}) — quota cap or API abort")
        logger.warning("odds fetch stopped cleanly (SystemExit %s) — likely quota cap", e.code)
    stats["live_requests_after_fetch"] = api.live_requests_made()


def _phase_predict_commit(stats: dict) -> None:
    """Predict covered fixtures and commit each before kickoff (idempotent)."""
    import pilotC_forward_predict as predict
    attest = predict.main()  # returns attest_stats dict
    if isinstance(attest, dict):
        stats["committed_pre_kickoff"] = attest.get("committed", 0)
        stats["unattestable_past_kickoff"] = attest.get("unattestable_past_kickoff", 0)
        stats["commit_failed"] = attest.get("commit_failed", 0)
        stats["skipped_already_committed"] = attest.get("skipped_already_committed", 0)
        if attest.get("unattestable_past_kickoff", 0) > 0:
            logger.warning(
                "%d prediction(s) were past kickoff at predict time — UNATTESTED, "
                "not backdated (permanent loss for those fixtures).",
                attest["unattestable_past_kickoff"],
            )
        if attest.get("commit_failed", 0) > 0:
            logger.error("%d commitment(s) FAILED (not past-kickoff) — investigate.",
                         attest["commit_failed"])


def _phase_settle(stats: dict) -> None:
    """Grade finished fixtures and reveal outcomes against commitments."""
    import pilotC_settle as settle
    s = settle.score(verbose=False)
    stats["settlement"] = {
        "graded": s.get("graded", 0),
        "revealed": s.get("revealed", 0),
        "already_revealed": s.get("skipped_already_revealed", 0),
        "not_finished": s.get("skipped_not_finished", 0),
        "no_commitment": s.get("reveal_declined_no_commitment", 0),
        "ungradeable": s.get("ungradeable_missing_result", 0),
        "per_cell_settled_added": s.get("per_cell_settled_added", {}),
    }
    if s.get("reveal_declined_no_commitment", 0) > 0:
        logger.warning(
            "%d finished fixture(s) had NO prior commitment and cannot be revealed "
            "(never backdated).", s["reveal_declined_no_commitment"],
        )
    for err in s.get("errors", [])[:5]:
        logger.warning("settlement: %s", err)


# ── health report (weekly early-warning) ─────────────────────────────────────

def _discovery_health() -> dict:
    """Interpret the discovery status file into a health block.

    The whole point is that these three outcomes are NOT interchangeable:
      * healthy   — discovery ran and found upcoming covered fixtures ("found")
      * empty     — discovery ran, reached the API, found zero in the window
                    ("empty"); possibly legitimate (international break)
      * broken    — discovery did not run or failed ("failed"), OR the last
                    successful discovery is STALE (older than DISCOVERY_STALE_HOURS)
                    — inflow may have stopped and the universe will drain
    A missing status file entirely is treated as "broken" (never run).
    """
    if not DISCOVERY_STATUS.exists():
        return {
            "discovery_state": "never_ran",
            "interpretation": "broken",
            "note": "No discovery status file — fixture discovery has never run. "
                    "The universe will drain and the loop will report zero activity. "
                    "Run scripts/pilotC_fixture_discovery.py / check the cron entry.",
            "last_discovery": None,
            "age_hours": None,
        }
    try:
        d = json.load(open(DISCOVERY_STATUS))
    except Exception as e:
        return {"discovery_state": "unreadable", "interpretation": "broken",
                "note": f"discovery status file unreadable: {str(e)[:80]}",
                "last_discovery": None, "age_hours": None}

    state = d.get("state", "failed")
    gen = d.get("generated")
    age_hours = None
    try:
        if gen:
            age_hours = round(
                (datetime.now(timezone.utc)
                 - datetime.fromisoformat(gen)).total_seconds() / 3600.0, 1)
    except Exception:
        pass

    stale = (age_hours is not None and age_hours > DISCOVERY_STALE_HOURS)
    if state == "found":
        interp = "stale_but_last_run_found" if stale else "healthy"
    elif state == "empty":
        interp = "empty_possibly_legitimate" if not stale else "stale_empty"
    else:
        interp = "broken"

    note = {
        "healthy": "Discovery ran and found upcoming covered fixtures. Inflow is live.",
        "stale_but_last_run_found": f"Last discovery FOUND fixtures but was {age_hours}h "
            f"ago (> {DISCOVERY_STALE_HOURS}h) — it may have stopped running. Check cron.",
        "empty_possibly_legitimate": "Discovery ran and reached the API but found ZERO "
            "settleable covered fixtures in the window. Can be legitimate (international "
            "break, off-season). NOT the same as a failure — but watch for persistence.",
        "stale_empty": f"Discovery last ran {age_hours}h ago and found zero — both stale "
            "AND empty; likely not running. Check cron.",
        "broken": "Discovery DID NOT complete (failed/never-ran). Inflow has stopped; the "
            "universe will drain and the loop will fall silent. Investigate immediately.",
    }[interp]

    return {
        "discovery_state": state,
        "interpretation": interp,
        "healthy": interp == "healthy",
        "last_discovery": gen,
        "age_hours": age_hours,
        "stale_threshold_hours": DISCOVERY_STALE_HOURS,
        "window_days": d.get("window_days"),
        "upcoming_in_window_seen": d.get("upcoming_fixtures_in_window_seen"),
        "covered_settleable_in_window": d.get("covered_settleable_fixtures_in_window"),
        "fixtures_added_last_run": d.get("fixtures_added"),
        "per_league": d.get("per_league"),
        "requests_last_run": (d.get("requests") or {}).get("live_requests_used_this_run"),
        "projected_weekly_request_consumption": (d.get("requests") or {}).get(
            "projected_weekly_request_consumption"),
        "note": note,
    }


def _per_cell_settled_counts() -> dict:
    """Count settled+revealed observations per pre-registered cell."""
    counts = {f"{m}@{l}": 0 for m, l in PREREG_CELLS}
    log_path = Path("/home/ubuntu/data/discovery/pilotC_settled_log.json")
    if log_path.exists():
        try:
            data = json.load(open(log_path))
            for r in data.get("settled", []):
                cell = f"{r['market']}@{r['line']}"
                if cell in counts:
                    counts[cell] += 1
        except Exception:
            pass
    return counts


def emit_health_report() -> dict:
    """Weekly health summary — the early-warning system for projection slippage."""
    from src.research.forward.attestation_ledger import AttestationLedger
    import pilotC_stat_mixer as mix
    from src.research.forward.covered_league_topup import build_topup_plan

    led = AttestationLedger(commit_path=COMMIT_LEDGER, reveal_path=REVEAL_LEDGER)
    commitments = led.load_commitments()
    reveals = led.load_reveals()
    committed_fixtures = {c["fixture_id"] for c in commitments}

    # covered fixtures available now (via the same top-up policy)
    covered_available = None
    missed_windows = 0
    try:
        ms = mix.load_corpus(); hist = mix.build_histories(ms)
        corpus_teams = set(hist.keys())
        if FIXTURE_LIST.exists():
            fx = json.load(open(FIXTURE_LIST))
            meta = fx["meta"]
            plan = build_topup_plan(meta, fx["match_ids"], corpus_teams, time.time())
            covered_available = plan.n_upcoming_both_covered + plan.n_settle_finished_covered
            now = time.time()
            for mid, row in meta.items():
                if row.get("home") in corpus_teams and row.get("away") in corpus_teams:
                    if row.get("ts", 0) < now and mid not in committed_fixtures:
                        missed_windows += 1
    except Exception:
        corpus_teams = set()

    per_cell = _per_cell_settled_counts()
    n_cells_at_target = sum(1 for v in per_cell.values() if v >= TARGET_N_PER_CELL)
    total_settled = sum(per_cell.values())

    # committed/available ratio — the key health metric
    n_covered_committed = len(committed_fixtures)
    ratio = None
    if covered_available and covered_available > 0:
        # ratio of fixtures committed vs the covered fixtures currently visible
        ratio = round(n_covered_committed / max(covered_available + n_covered_committed, 1), 3)

    # observed weekly settle rate -> weeks to readout at current pace
    # (use reveals with timestamps over the observation window)
    reveal_times = [r.get("anchor_unix") for r in reveals if r.get("anchor_unix")]
    weeks_to_readout_observed = None
    observed_weekly_settle = None
    if reveal_times:
        span_days = max((max(reveal_times) - min(reveal_times)) / 86400.0, 1.0)
        weeks_elapsed = max(span_days / 7.0, 1.0)
        observed_weekly_settle = round(len(reveals) / weeks_elapsed, 2)
        # per-cell rate ~ total/9 spread; conservatively use min cell need
        remaining_to_power = max(TARGET_N_PER_CELL * len(PREREG_CELLS) - total_settled, 0)
        if observed_weekly_settle > 0:
            weeks_to_readout_observed = round(remaining_to_power / observed_weekly_settle, 1)

    # ── inflow analysis (the binding constraint early on) ────────────────────
    # Weeks-to-readout is gated by the SLOWER of two rates: how fast covered fixtures
    # arrive (inflow) and how fast they settle. This early, the settle rate is a noisy
    # extrapolation from a handful of reveals; the inflow rate is the meaningful signal
    # and it is exactly the ~10/week assumption the ~38.5-week estimate rests on.
    #
    # Observed inflow = settleable covered fixtures seen in the discovery window,
    # scaled to a weekly rate. This is fixtures/week; each fixture yields observations
    # across the pre-registered market cells (a fixture contributes to goals/btts/etc).
    disc_status = {}
    try:
        if DISCOVERY_STATUS.exists():
            disc_status = json.load(open(DISCOVERY_STATUS))
    except Exception:
        disc_status = {}
    settleable_in_window = disc_status.get("covered_settleable_fixtures_in_window")
    window_days = disc_status.get("window_days") or 10
    observed_inflow_per_week = None
    if settleable_in_window is not None and window_days:
        observed_inflow_per_week = round(settleable_in_window / (window_days / 7.0), 1)
    inflow_holds = None
    inflow_shortfall_pct = None
    if observed_inflow_per_week is not None and ASSUMED_COVERED_INFLOW_PER_WEEK > 0:
        inflow_holds = observed_inflow_per_week >= ASSUMED_COVERED_INFLOW_PER_WEEK
        inflow_shortfall_pct = round(
            100.0 * (ASSUMED_COVERED_INFLOW_PER_WEEK - observed_inflow_per_week)
            / ASSUMED_COVERED_INFLOW_PER_WEEK, 1)

    # First-full-week ratio: commitments made vs covered fixtures that became
    # available in the 7 days since discovery went live. This is the steady-state
    # measure the task asks for — distinct from the all-time ratio which is dragged
    # down by the unscheduled-gap backlog and the 22 permanently-missed windows.
    first_week_ratio = None
    committed_first_week = None
    available_first_week = None
    live_since_unix = None
    try:
        if DISCOVERY_LIVE_SINCE:
            live_since_unix = datetime.fromisoformat(DISCOVERY_LIVE_SINCE).timestamp()
    except Exception:
        live_since_unix = None
    if live_since_unix is None:
        # Fall back to the earliest discovery-log entry as "discovery live since".
        try:
            log_path = Path("/home/ubuntu/data/discovery/pilotC_discovery_log.jsonl")
            if log_path.exists():
                first = None
                for ln in open(log_path):
                    r = json.loads(ln)
                    g = r.get("generated")
                    if g:
                        first = g
                        break
                if first:
                    live_since_unix = datetime.fromisoformat(first).timestamp()
        except Exception:
            live_since_unix = None
    if live_since_unix is not None:
        week_end = live_since_unix + 7 * 86400
        committed_first_week = sum(
            1 for c in commitments
            if c.get("committed_at") and _iso_to_unix(c["committed_at"]) is not None
            and live_since_unix <= _iso_to_unix(c["committed_at"]) < week_end)
        # available in first week ~ inflow rate over one week (best estimate we have)
        if observed_inflow_per_week is not None:
            available_first_week = observed_inflow_per_week
            denom = committed_first_week + max(available_first_week - committed_first_week, 0)
            if denom > 0:
                first_week_ratio = round(committed_first_week / denom, 3)

    # Revised weeks-to-readout using the INFLOW rate (fixtures/week -> observations).
    # Each committed+settled fixture contributes to multiple cells; conservatively we
    # track the per-cell target across 9 cells. Inflow-limited weeks = remaining
    # cell-observations / (inflow_per_week * cells_touched_per_fixture ~ len(cells)).
    weeks_to_readout_inflow = None
    if observed_inflow_per_week and observed_inflow_per_week > 0:
        # obs added per week ~ inflow fixtures * cells each fixture can populate
        obs_per_week = observed_inflow_per_week * len(PREREG_CELLS)
        remaining_obs = max(TARGET_N_PER_CELL * len(PREREG_CELLS) - total_settled, 0)
        weeks_to_readout_inflow = round(remaining_obs / obs_per_week, 1)

    quota = _quota_remaining()
    ledger_ok, ledger_problems = _verify_ledger_chain()
    discovery = _discovery_health()

    report = {
        "generated": _now_iso(),
        "STATUS": "Pilot C forward-collection health. MEASUREMENT ONLY — no edge claim. "
                  "No edge conclusion may be drawn from unsettled fixtures.",
        "ledger_chain_verifies": ledger_ok,
        "ledger_problems": ledger_problems[:5],
        "discovery_health": discovery,
        "attestation": {
            "total_commitments": len(commitments),
            "total_reveals": len(reveals),
            "covered_fixtures_committed": n_covered_committed,
        },
        "collection_health": {
            "covered_fixtures_available_now": covered_available,
            "fixtures_committed": n_covered_committed,
            "committed_over_available_ratio": ratio,
            "ratio_note": "Ratio materially below 1.0 means we are NOT capturing "
                          "available covered fixtures — investigate scheduling/coverage. "
                          "Should be visible by week three, not at the readout date.",
            "covered_fixtures_lost_to_missed_prekickoff_window": missed_windows,
            "missed_window_note": "Permanent sample loss — never backdated.",
        },
        "sample_progress": {
            "per_cell_settled_revealed": per_cell,
            "target_n_per_cell": TARGET_N_PER_CELL,
            "cells_at_target": n_cells_at_target,
            "cells_needed_to_trigger_analysis": 5,
            "total_settled_revealed": total_settled,
        },
        "timeline": {
            "observed_weekly_settle_rate": observed_weekly_settle,
            "estimated_weeks_to_readout_at_observed_settle_rate": weeks_to_readout_observed,
            "settle_rate_note": "Weeks-to-readout from the SETTLE rate is a noisy "
                                "extrapolation until many fixtures have settled; treat "
                                "it as indicative only while total_settled is small.",
            "observed_covered_inflow_per_week": observed_inflow_per_week,
            "assumed_covered_inflow_per_week": ASSUMED_COVERED_INFLOW_PER_WEEK,
            "inflow_assumption_holds": inflow_holds,
            "inflow_shortfall_pct_vs_assumption": inflow_shortfall_pct,
            "estimated_weeks_to_readout_at_observed_inflow": weeks_to_readout_inflow,
            "original_projection_weeks": ORIGINAL_WEEKS_PROJECTION,
            "inflow_note": "Inflow is the binding constraint early on. The ~"
                           f"{ORIGINAL_WEEKS_PROJECTION}-week projection assumes ~"
                           f"{ASSUMED_COVERED_INFLOW_PER_WEEK:g} covered fixtures/week. "
                           "If observed inflow is materially below that, the timeline "
                           "slips — surfaced here, not at the readout date.",
            "slippage_note": "If weeks-to-readout at the observed rate exceeds the "
                             f"original ~{ORIGINAL_WEEKS_PROJECTION}-week projection, "
                             "collection is running slower than planned.",
        },
        "ratio_recovery": {
            "all_time_committed_over_available_ratio": ratio,
            "all_time_ratio_note": "Dragged down by the unscheduled-gap backlog and the "
                "22 permanently-missed windows (sunk, never backdated). NOT the "
                "steady-state measure.",
            "first_full_week_ratio": first_week_ratio,
            "first_week_committed": committed_first_week,
            "first_week_available_estimate": available_first_week,
            "discovery_live_since": (datetime.fromtimestamp(live_since_unix, timezone.utc)
                                     .isoformat() if live_since_unix else None),
            "first_week_ratio_note": "This is the real measure of steady-state capture "
                "once discovery+scheduler are live. Should recover toward 1.0; the 0.18 "
                "baseline reflects the unscheduled gap, not steady-state performance.",
        },
        "quota": {
            "monthly_remaining": quota,
            "low_quota_threshold": LOW_QUOTA_WARN,
            "low_quota": (quota is not None and quota < LOW_QUOTA_WARN),
        },
    }
    HEALTH_REPORT.parent.mkdir(parents=True, exist_ok=True)
    json.dump(report, open(HEALTH_REPORT, "w"), indent=2, default=str)

    # LOUD summary line
    logger.info("HEALTH: committed=%d reveals=%d settled=%d/%d cells_at_target=%d "
                "committed/available=%s missed_windows=%d quota=%s chain_ok=%s",
                len(commitments), len(reveals), total_settled,
                TARGET_N_PER_CELL * len(PREREG_CELLS), n_cells_at_target,
                ratio, missed_windows, quota, ledger_ok)
    # Discovery is the inflow — its three states must be distinguishable and loud.
    logger.info("HEALTH DISCOVERY: state=%s interpretation=%s last_run=%s age=%sh "
                "settleable_in_window=%s added_last_run=%s",
                discovery.get("discovery_state"), discovery.get("interpretation"),
                discovery.get("last_discovery"), discovery.get("age_hours"),
                discovery.get("covered_settleable_in_window"),
                discovery.get("fixtures_added_last_run"))
    # Inflow vs assumption + first-week ratio recovery — surface slippage early.
    logger.info("HEALTH INFLOW: observed=%s/wk assumed=%s/wk holds=%s shortfall=%s%% "
                "weeks_to_readout(inflow)=%s vs original~%s | first_week_ratio=%s "
                "(committed=%s) all_time_ratio=%s",
                observed_inflow_per_week, ASSUMED_COVERED_INFLOW_PER_WEEK, inflow_holds,
                inflow_shortfall_pct, weeks_to_readout_inflow, ORIGINAL_WEEKS_PROJECTION,
                first_week_ratio, committed_first_week, ratio)
    if inflow_holds is False:
        logger.warning("INFLOW BELOW PROJECTION: observed ~%s covered fixtures/week vs "
                       "assumed ~%s (%s%% short). The ~%s-week readout estimate depends "
                       "on this — timeline is slipping.", observed_inflow_per_week,
                       ASSUMED_COVERED_INFLOW_PER_WEEK, inflow_shortfall_pct,
                       ORIGINAL_WEEKS_PROJECTION)
    interp = discovery.get("interpretation")
    if interp == "broken":
        logger.error("DISCOVERY BROKEN: %s", discovery.get("note"))
    elif interp in ("stale_but_last_run_found", "stale_empty"):
        logger.warning("DISCOVERY STALE: %s", discovery.get("note"))
    elif interp == "empty_possibly_legitimate":
        logger.warning("DISCOVERY EMPTY (may be legitimate): %s", discovery.get("note"))
    if not ledger_ok:
        logger.error("LEDGER CHAIN FAILED VERIFICATION: %s", ledger_problems[:3])
    if ratio is not None and ratio < 0.5 and covered_available:
        logger.warning("committed/available ratio %.2f is well below 1.0 — "
                       "collection is missing available covered fixtures.", ratio)
    if quota is not None and quota < LOW_QUOTA_WARN:
        logger.warning("LOW QUOTA: %d monthly requests remaining (< %d).",
                       quota, LOW_QUOTA_WARN)
    logger.info("saved health report -> %s", HEALTH_REPORT)
    return report


# ── main cycle ───────────────────────────────────────────────────────────────

def run_cycle(settle_only: bool = False) -> dict:
    run_start = time.time()
    stats = {
        "run_timestamp": _now_iso(),
        "mode": "settle_only" if settle_only else "full",
        "errors": [],
    }
    logger.info("=" * 64)
    logger.info("PILOT C FORWARD LOOP — %s (%s)", stats["run_timestamp"], stats["mode"])
    logger.info("=" * 64)

    # 0. Verify ledger integrity before doing anything that appends to it.
    try:
        ok, problems = _verify_ledger_chain()
        stats["ledger_chain_ok_at_start"] = ok
        if not ok:
            logger.error("LEDGER CHAIN VERIFICATION FAILED at start: %s — "
                         "refusing to append this run.", problems[:3])
            stats["errors"].append(f"ledger chain failed: {problems[:3]}")
            stats["aborted"] = True
            stats["duration_seconds"] = round(time.time() - run_start, 1)
            _persist_run_log(stats)
            return stats
    except Exception as e:
        logger.error("ledger verification errored: %s", str(e)[:120])
        stats["errors"].append(f"ledger verify error: {str(e)[:120]}")

    quota_before = _quota_remaining()
    stats["quota_before"] = quota_before
    if quota_before is not None and quota_before < LOW_QUOTA_WARN:
        logger.warning("LOW QUOTA at start: %d remaining (< %d).", quota_before, LOW_QUOTA_WARN)

    if not settle_only:
        # 0. Discover upcoming covered-league fixtures (the inflow) BEFORE fetching
        #    odds, so this cycle's fetch/predict can act on anything newly discovered.
        #    Runs on a weekly/twice-weekly cadence (see _should_discover); cache-first.
        if _should_discover():
            logger.info("Phase 0: discover upcoming covered-league fixtures "
                        "(merge into universe, cache-first)...")
            try:
                _phase_discover(stats)
                d = stats.get("discovery", {})
                logger.info("  discovery state=%s settleable_in_window=%s added=%s "
                            "universe=%s requests=%s",
                            d.get("state"), d.get("covered_settleable_in_window"),
                            d.get("added"), d.get("universe_size_after"),
                            d.get("requests_used"))
            except Exception as e:
                logger.error("Phase 0 (discovery) crashed: %s", str(e)[:200])
                stats["errors"].append(f"discovery phase: {type(e).__name__}: {str(e)[:150]}")
        else:
            logger.info("Phase 0: discovery skipped this cycle (runs Mon/Thu; set "
                        "PILOTC_DISCOVERY_EVERY_RUN=1 to force). Universe unchanged.")
            stats["discovery"] = {"state": "skipped_this_cycle"}

        # 1. Fetch odds (cache-first, covered-league biased, capped).
        logger.info("Phase 1: fetch multi-book odds for covered-league fixtures "
                    "(cap=%d requests, <=%d fixtures)...",
                    PER_RUN_REQUEST_CAP, MAX_FIXTURES_PER_RUN)
        try:
            _phase_fetch_odds(stats)
        except Exception as e:
            logger.error("Phase 1 (fetch) crashed: %s", str(e)[:200])
            stats["errors"].append(f"fetch phase: {type(e).__name__}: {str(e)[:150]}")

        # 2. Predict + commit before kickoff (idempotent).
        logger.info("Phase 2: predict + commit (before kickoff)...")
        try:
            _phase_predict_commit(stats)
            logger.info("  committed=%s skipped_already=%s unattestable_past_kickoff=%s failed=%s",
                        stats.get("committed_pre_kickoff"), stats.get("skipped_already_committed"),
                        stats.get("unattestable_past_kickoff"), stats.get("commit_failed"))
        except Exception as e:
            logger.error("Phase 2 (predict/commit) crashed: %s", str(e)[:200])
            stats["errors"].append(f"predict phase: {type(e).__name__}: {str(e)[:150]}")

        # 2.5 Audit missed pre-kickoff windows (LOUD).
        try:
            _audit_missed_windows(stats)
        except Exception as e:
            stats["errors"].append(f"window audit: {str(e)[:120]}")

    # 3. Settle + reveal finished fixtures (idempotent, cache-first).
    logger.info("Phase 3: settle + reveal finished fixtures...")
    try:
        _phase_settle(stats)
        st = stats.get("settlement", {})
        logger.info("  graded=%s revealed=%s already=%s not_finished=%s no_commitment=%s",
                    st.get("graded"), st.get("revealed"), st.get("already_revealed"),
                    st.get("not_finished"), st.get("no_commitment"))
    except Exception as e:
        logger.error("Phase 3 (settle) crashed: %s", str(e)[:200])
        stats["errors"].append(f"settle phase: {type(e).__name__}: {str(e)[:150]}")

    quota_after = _quota_remaining()
    stats["quota_after"] = quota_after
    if quota_before is not None and quota_after is not None:
        stats["quota_used_this_run"] = quota_before - quota_after

    # Zero-fixture / zero-activity runs must say so explicitly.
    committed = stats.get("committed_pre_kickoff", 0)
    revealed = stats.get("settlement", {}).get("revealed", 0)
    if not settle_only and committed == 0 and revealed == 0:
        logger.info("NOTE: this run committed 0 and revealed 0. If this persists across "
                    "runs, collection has effectively stopped — check fixture list "
                    "freshness and covered-league coverage. (Not a silent success.)")

    stats["duration_seconds"] = round(time.time() - run_start, 1)
    _persist_run_log(stats)
    logger.info("Run complete in %.1fs: committed=%s revealed=%s quota_used=%s errors=%d",
                stats["duration_seconds"], committed, revealed,
                stats.get("quota_used_this_run"), len(stats["errors"]))
    logger.info("=" * 64)
    return stats


def main():
    ap = argparse.ArgumentParser(description="Pilot C forward loop orchestrator")
    ap.add_argument("--settle-only", action="store_true",
                    help="run only the settle+reveal pass (daily cadence)")
    ap.add_argument("--health", action="store_true",
                    help="emit the weekly health report only")
    args = ap.parse_args()

    if args.health:
        emit_health_report()
        return
    run_cycle(settle_only=args.settle_only)
    # Always refresh the health snapshot after a run so it's current between weekly emits.
    try:
        emit_health_report()
    except Exception as e:
        logger.warning("health report after run failed: %s", str(e)[:120])


if __name__ == "__main__":
    main()
