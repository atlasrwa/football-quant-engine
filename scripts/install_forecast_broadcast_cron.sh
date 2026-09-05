#!/usr/bin/env bash
# Install the T-8h forecast broadcast cron entries — idempotently.
#
# WHY A SCHEDULER AT ALL
# ----------------------
# The horizon is the trigger. A forecast is only a pre-kickoff forecast if it was
# generated at a fixed distance before kickoff, decided by the clock rather than by
# an operator who chose that moment. Running this on demand would let the send time
# become a judgement call, which is exactly what the published record is supposed to
# rule out. So the broadcaster is evaluated on a timer and never invoked by hand.
#
# TICK FREQUENCY
# --------------
# Every 15 minutes. The horizon for a fixture is a single instant (kickoff minus the
# declared hours), so a coarser tick would systematically publish late; a 15-minute
# tick bounds lateness at 15 minutes. A fixture becomes due at its horizon and stays
# due until it fires exactly once, so a tick that lands late still publishes rather
# than skipping — being late is recorded, never used as a reason to drop a fixture.
#
# Ticks are cheap when there is nothing to do: the runner only fits the model after
# it has found at least one due fixture, so an idle tick just reads the fixture list.
#
# THE TIMER RUNS THROUGH QUIET HOURS TOO
# --------------------------------------
# Quiet hours (declared in config/forecast_broadcast_scope.json) delay a send; they
# never cancel it. Ticking every 15 minutes right through the quiet window means a
# suppressed forecast is queued immediately and flushed on the first tick after the
# window closes, carrying its original generated_at_utc and commitment hash. The
# queue flush runs at the start of every tick, before any new forecast is generated,
# so a delayed message is never stuck behind new work.
#
# DAILY COVERAGE AUDIT
# --------------------
# A separate 07:10 UTC entry re-reads the append-only record and compares it against
# declared scope, after quiet hours have ended and the queue has drained. It exits
# non-zero when a fixture in declared scope has no row at all, or when a committed
# forecast was never delivered. Coverage that is never checked is only an assumption.
#
# The runner needs scikit-learn, which lives only in the project virtualenv, so the
# entries invoke the venv interpreter explicitly.
#
# Re-running this script is safe: it removes any prior forecast-broadcast block
# (delimited by the markers below) before re-adding the current one, and never
# touches other lines — including the Pilot C block and Pipeline A's entry.

set -euo pipefail

PY="/home/ubuntu/.venv/bin/python"
REPO="/home/ubuntu"
LOG="${REPO}/logs/forecast_broadcast.log"
COVERAGE_LOG="${REPO}/logs/forecast_broadcast_coverage.log"
BEGIN="# >>> forecast broadcast T-8h (managed by install_forecast_broadcast_cron.sh) >>>"
END="# <<< forecast broadcast T-8h <<<"

if [[ ! -x "${PY}" ]]; then
  echo "ERROR: venv python not found at ${PY} (the forecast engine needs sklearn from the venv)." >&2
  exit 1
fi

mkdir -p "${REPO}/logs"

current="$(crontab -l 2>/dev/null || true)"
stripped="$(printf '%s\n' "${current}" | sed "/${BEGIN}/,/${END}/d")"

block="$(cat <<EOF
${BEGIN}
CRON_TZ=UTC
# Evaluate the T-8h horizon every 15 minutes. Runs through quiet hours as well, so a
# suppressed forecast is queued at once and flushed on the first tick after the window
# closes with its original generated_at_utc and commitment hash. flock keeps a slow
# model fit from overlapping the next tick.
*/15 * * * * cd ${REPO} && /usr/bin/flock -n /tmp/forecast_broadcast.lock ${PY} scripts/forecast_broadcast.py >> ${LOG} 2>&1
# Daily coverage audit at 07:10 UTC — after quiet hours end and the queue has drained.
# Exits non-zero if a fixture in declared scope has no row, or a commitment was never delivered.
10 7 * * * cd ${REPO} && /usr/bin/flock -n /tmp/forecast_broadcast.lock ${PY} scripts/forecast_broadcast.py --coverage >> ${COVERAGE_LOG} 2>&1
${END}
EOF
)"

{
  printf '%s\n' "${stripped}" | sed '/^[[:space:]]*$/d'
  printf '%s\n' "${block}"
} | crontab -

echo "Installed forecast broadcast cron entries. Current crontab:"
crontab -l
