#!/usr/bin/env bash
# Research-monitor runner — invoked by systemd user timers.
#
# Sends research-status Telegram messages from ALREADY-PERSISTED state. It never
# calls TheStatsAPI (no quota cost) and never publishes betting signals. A
# Telegram failure exits non-zero for visibility but never affects the capture
# collector (a separate unit).
#
# Usage (mode passed as $1): heartbeat | alerts | weekly
#   heartbeat -> daily
#   alerts    -> low-frequency health check (event-triggered send, deduped)
#   weekly    -> once weekly
set -euo pipefail

MODE="${1:-heartbeat}"
WORKDIR="/home/ubuntu"
PYTHON="/home/ubuntu/.venv/bin/python"
ENV_FILE="${WORKDIR}/.env"
LOCK_FILE="/tmp/research_monitor_${MODE}.lock"
LOG_FILE="${WORKDIR}/logs/research_monitor.log"
RUN_TIMEOUT="${RESEARCH_MONITOR_TIMEOUT:-120}"

cd "${WORKDIR}"

# Load Telegram credentials without exposing them (never `set -x` here).
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "${ENV_FILE}"
  set +a
fi

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "$(date -u +%FT%TZ) research_monitor[${MODE}]: previous run active; skipping" >>"${LOG_FILE}"
  exit 0
fi

echo "$(date -u +%FT%TZ) research_monitor[${MODE}]: start" >>"${LOG_FILE}"
set +e
timeout --signal=TERM --kill-after=15 "${RUN_TIMEOUT}" \
  "${PYTHON}" scripts/research_monitor.py "${MODE}" >>"${LOG_FILE}" 2>&1
rc=$?
set -e
echo "$(date -u +%FT%TZ) research_monitor[${MODE}]: finished rc=${rc}" >>"${LOG_FILE}"
exit "${rc}"
