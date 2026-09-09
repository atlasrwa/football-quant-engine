# Prospective capture — operations report

Branch `research/price-discovery-prospective` · baseline `main 57e80ffa6`
(PR #7 merge). This report describes the operational pipeline that turns the
PR #7 capture infrastructure into a continuously-running, leakage-safe
information-capture system. It is regenerated from live state and the
operational run log; no model is fitted here and the champion is untouched.

## Collector status: COLLECTOR_OPERATIONAL

The prospective collector runs on a schedule, captures only due work, records
one operational run entry per invocation, and reports health independently of
the API being up.

## Scheduler

| Property | Value |
|---|---|
| Mechanism | systemd **user** timer (`prospective-capture.timer`) |
| Command | `python -m src.research.prospective.cli capture-due --hours 96` |
| Cadence | every 15 min (`OnCalendar=*:3/15`, offset from the :00/:15 broadcast jobs) |
| Reboot survival | `OnBootSec=3min`, `Persistent=true`, user linger enabled |
| Interpreter | `/home/ubuntu/.venv/bin/python` (explicit) |
| Working dir | `/home/ubuntu` (explicit) |
| Secrets | `.env` sourced by the runner without echo; key never printed/logged |
| Runner | `scripts/prospective_capture_run.sh` |
| Units (vendored) | `deploy/systemd/prospective-capture.{service,timer}` + installer |

Manual control:

```
systemctl --user list-timers prospective-capture.timer
systemctl --user start   prospective-capture.service   # run once now
systemctl --user stop    prospective-capture.timer     # pause
systemctl --user start   prospective-capture.timer     # resume
journalctl --user -u prospective-capture.service -n 50  # logs
```

## Single-instance lock

The 15-minute cadence must never launch a second collector while one is still
running. The runner holds `flock -n /tmp/prospective_capture.lock` on FD 9 for
its lifetime. A second invocation while the first is active exits cleanly
(code 0) and logs `previous run still active; skipping this tick` — verified by
`tests/research/prospective/test_capture_lock.py` and by a live concurrent
invocation.

## Bounded runtime

`timeout --signal=TERM --kill-after=30 600` wraps the collector so a stalled run
cannot occupy the slot past one cadence; systemd `TimeoutStartSec=660` is the
backstop. The real exit code (incl. 124/137 on timeout) is propagated to
systemd so failures are visible.

## Operational logging

Per-run metadata is appended to `data/prospective/ops_runs.jsonl` — a file kept
**separate** from the research capture store so it can never become a model
input. Fields: `run_started_at`, `run_finished_at`, `duration_seconds`,
`exit_status`, `health_state`, `fixtures_discovered`, `fixtures_inside_horizon`,
`fixtures_due`, `odds_captured`, `lineups_captured`, `availability_captured`,
`referees_captured`, `errors`, `quota_remaining`, `quota_limited`,
`competitions_active`, `hostname`. The log is size-rotated (5 MB × 3 backups)
for bounded growth; systemd's journal bounds the stdout/stderr copy.

## Scheduler health

`python -m src.research.prospective.cli scheduler-health` reads only the ops log
(no network) and returns one of `HEALTHY`, `STALE_SCHEDULER`, `QUOTA_LIMITED`,
`AUTH_FAILED`, `SCHEMA_DRIFT`, `PARTIAL_FAILURE`. A functioning API with a dead
timer reads **STALE_SCHEDULER**, not HEALTHY (staleness dominates all other
states). Exit code is 0 only when HEALTHY.

## Failure handling (fail-closed)

- **No API key** → the collector never issues a request; records an
  `AUTH_FAILED` ops entry and exits non-zero.
- **429 / 5xx / timeout** → client retries with backoff; persistent failure is
  a per-fixture error, counted (`errors`), other fixtures continue.
- **Quota reserve threatened** → `QuotaGuard` stops issuing work
  (`QUOTA_LIMITED`); the 20% monthly reserve is protected.
- **Lineup/referee/injury not yet posted** → normalizers return neutral
  None/empty; never fabricated (endpoint-supported ≠ data-available).
- **Process restart / reboot** → due work is recomputed from the persisted
  store; timer catches up one missed tick.

## Quota

Monthly limit **100,000**, 20% hard reserve → usable ~80,000/month. Planned
cost ≈ **17.3 requests/fixture** (full lifecycle). Rolling actual usage will be
tracked from the ops log's `quota_remaining` deltas as runs accumulate; with
only two runs so far the rolling per-fixture estimate is not yet stable and is
reported as such rather than asserted.

## Weekly coverage refresh

`python scripts/prospective_coverage_scan.py` remains a weekly job; league
classification stays **data-availability driven** and is never promoted/demoted
on predictive performance.

See `research/evaluation/prospective_data_quality.json` for the machine-readable
snapshot (scheduler health, recent runs, capture-store counts, coverage funnel).
