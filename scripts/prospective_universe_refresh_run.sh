#!/usr/bin/env bash
# Fixture-universe refresh runner — invoked by the systemd user timer every 6h.
#
# WHY THIS EXISTS. The shared discovered fixture universe
# (data/thestatsapi/championship/_pilotC_fixture_list.json) is what the forecast
# broadcaster consumes and what the heartbeat's check_stale_fixture_universe()
# watches (36h stale threshold). Its ONLY scheduled refresher used to be Pilot
# C's 6-hourly forward loop. Pilot C was deprecated (F024, 2026-09-05) and the
# frequent refresh was lost; the twice-weekly cron entry that replaced it
# (Mon & Thu 06:00 UTC) leaves a 72h gap between runs and therefore cannot keep
# the universe under the 36h stale threshold — the alert fires every week by
# construction. This runner restores a conservative, frequent, INDEPENDENT
# refresh so inflow never goes silent.
#
# WHAT IT DOES / DOES NOT DO. It is a thin wrapper around the EXISTING, tested,
# idempotent discovery command (scripts/pilotC_fixture_discovery.py). It changes
# NO discovery logic, scope, competition crosswalk, or settleability gate. It is
# fixture-discovery ONLY — no odds / lineup / model / settle paths are invoked.
#
# SAFETY (mirrors scripts/prospective_capture_run.sh):
#   - explicit working directory and interpreter
#   - loads THESTATS_API_KEY from .env WITHOUT exposing it (no echo / no set -x)
#   - single-instance via flock; shares the discovery lock with the legacy cron
#     entry so the two schedulers can NEVER write the universe artifact at once
#   - bounded runtime (timeout) so a stalled run cannot wedge the timer
#   - failure exit codes remain visible to systemd; failure NEVER touches the
#     prospective capture timer (separate unit, separate lock)
#   - no Telegram dependency for execution
#
# This is a plain oneshot script, NOT a daemon. Restart/reboot survival comes
# from the systemd timer (Persistent=true, OnBootSec), not a long-lived process.

set -euo pipefail

WORKDIR="/home/ubuntu"
PYTHON="/home/ubuntu/.venv/bin/python"
ENV_FILE="${WORKDIR}/.env"
# Share the legacy discovery cron lock so a systemd run and a cron run of the
# SAME discovery script are mutually exclusive (no double-write, no race).
LOCK_FILE="/tmp/forecast_broadcast_discovery.lock"
LOG_FILE="${WORKDIR}/logs/prospective_universe_refresh.log"
# Discovery is cache-first and quota-capped inside the script itself
# (PILOTC_DISCOVERY_REQUEST_CAP, default 40). This bound is only a wall-clock
# guard so a stalled network call cannot wedge the 6-hourly timer.
RUN_TIMEOUT="${UNIVERSE_REFRESH_RUN_TIMEOUT:-300}"

cd "${WORKDIR}"

# Load the API key without exposing it: never enable `set -x` around this, and
# scope auto-export tightly. Discovery fails closed without THESTATS_API_KEY.
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "${ENV_FILE}"
  set +a
fi

mkdir -p "${WORKDIR}/logs"

# flock -n: non-blocking. If the legacy cron discovery run (or a previous refresh)
# holds the lock, exit 0 quietly so the timer does not treat an expected
# overlap-skip as a failure. FD-based lock held for this shell's lifetime.
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "$(date -u +%FT%TZ) universe_refresh: discovery lock held; skipping this tick" >>"${LOG_FILE}"
  exit 0
fi

TS="$(date -u +%FT%TZ)"
echo "${TS} universe_refresh: start (timeout=${RUN_TIMEOUT}s)" >>"${LOG_FILE}"

set +e
timeout --signal=TERM --kill-after=30 "${RUN_TIMEOUT}" \
  "${PYTHON}" scripts/pilotC_fixture_discovery.py \
  >>"${LOG_FILE}" 2>&1
rc=$?
set -e

echo "$(date -u +%FT%TZ) universe_refresh: finished rc=${rc}" >>"${LOG_FILE}"
# Propagate the real exit code so systemd records failures. A timeout kill
# surfaces as 124 (TERM) or 137 (KILL); both are visible failures.
exit "${rc}"
