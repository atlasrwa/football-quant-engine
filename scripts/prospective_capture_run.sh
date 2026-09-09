#!/usr/bin/env bash
# Prospective capture runner — invoked by the systemd user timer every 15 min.
#
# Responsibilities (mission section 2/3):
#   - explicit working directory and interpreter
#   - load THESTATS_API_KEY from .env WITHOUT exposing it (no echo/set -x of env)
#   - single-instance via flock: a second invocation exits cleanly (code 0),
#     never racing the first
#   - bounded runtime (timeout) so a stalled run cannot wedge the timer
#   - stdout/stderr appended to a rotated-by-caller log; secrets never printed
#   - failure exit codes remain visible to systemd
#
# This is a plain oneshot script, NOT a daemon: it runs, records one operational
# run entry (via the CLI), and exits. Restart-safety and reboot-survival come
# from the systemd timer (Persistent=true, OnBootSec), not a long-lived process.

set -euo pipefail

WORKDIR="/home/ubuntu"
PYTHON="/home/ubuntu/.venv/bin/python"
ENV_FILE="${WORKDIR}/.env"
LOCK_FILE="/tmp/prospective_capture.lock"
LOG_FILE="${WORKDIR}/logs/prospective_capture.log"
HOURS="${PROSPECTIVE_HOURS:-96}"
MAX_REQUESTS="${PROSPECTIVE_MAX_REQUESTS:-400}"
# Hard runtime bound. A 15-min cadence must never be wedged by a stalled run.
RUN_TIMEOUT="${PROSPECTIVE_RUN_TIMEOUT:-600}"

cd "${WORKDIR}"

# Load the API key without exposing it: never enable `set -x` around this, and
# only export the keys we need. `set -a` auto-exports sourced vars; we scope it
# tightly and immediately turn it back off.
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "${ENV_FILE}"
  set +a
fi

# flock -n: non-blocking. If another run holds the lock, exit 0 quietly so the
# timer does not treat an expected overlap-skip as a failure. The FD-based form
# keeps the lock for the lifetime of this shell.
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "$(date -u +%FT%TZ) prospective_capture: previous run still active; skipping this tick" >>"${LOG_FILE}"
  exit 0
fi

TS="$(date -u +%FT%TZ)"
echo "${TS} prospective_capture: start (hours=${HOURS} max_requests=${MAX_REQUESTS} timeout=${RUN_TIMEOUT}s)" >>"${LOG_FILE}"

set +e
timeout --signal=TERM --kill-after=30 "${RUN_TIMEOUT}" \
  "${PYTHON}" -m src.research.prospective.cli capture-due --hours "${HOURS}" --max-requests "${MAX_REQUESTS}" \
  >>"${LOG_FILE}" 2>&1
rc=$?
set -e

echo "$(date -u +%FT%TZ) prospective_capture: finished rc=${rc}" >>"${LOG_FILE}"
# Propagate the real exit code so systemd records failures. A timeout kill
# surfaces as 124 (TERM) or 137 (KILL); both are visible failures.
exit "${rc}"
