#!/usr/bin/env bash
# Install the Pilot C forward-loop cron entries — idempotently.
#
# Pilot C is a SEPARATE experiment from Pipeline A (corners/cards). It has its own
# ledger and pre-registration and must never be pooled with Pipeline A. This script
# ADDS Pilot C entries and leaves Pipeline A's entry (quarantine_forward_loop.py)
# untouched.
#
# CRITICAL: Pilot C's predictor uses scikit-learn, which lives ONLY in the project
# virtualenv (/home/ubuntu/.venv), NOT in /usr/bin/python3. The cron entries below
# therefore invoke the venv interpreter explicitly. (Pipeline A uses /usr/bin/python3
# because its model has no sklearn dependency.)
#
# Schedule:
#   - full loop every 6 hours (fetch odds -> predict+commit -> settle+reveal).
#     6-hourly gives margin to recover a failed run before a fixture's pre-kickoff
#     window (2h) closes. A missed pre-kickoff window is PERMANENT sample loss.
#   - a dedicated daily settle-only pass at 03:30 so reveals bind promptly even if
#     a full run was skipped.
#   - an EXTRA settle-only pass at 20:00 UTC to close the 18:00->00:00 gap so
#     afternoon kickoffs (which finish ~late afternoon/early evening UTC) settle the
#     SAME day rather than waiting for the 03:30 pass the next morning.
#   - a weekly health report Monday 08:00 (early warning for projection slippage).
#
# Re-running this script is safe: it removes any prior Pilot C block (delimited by
# the markers below) before re-adding the current one. It never touches other lines.

set -euo pipefail

PY="/home/ubuntu/.venv/bin/python"
REPO="/home/ubuntu"
LOG="${REPO}/logs/pilotC_loop.log"
BEGIN="# >>> pilotC forward loop (managed by install_pilotC_cron.sh) >>>"
END="# <<< pilotC forward loop <<<"

if [[ ! -x "${PY}" ]]; then
  echo "ERROR: venv python not found at ${PY} (Pilot C needs sklearn from the venv)." >&2
  exit 1
fi

mkdir -p "${REPO}/logs"

# Current crontab (empty string if none), with any existing Pilot C block stripped.
current="$(crontab -l 2>/dev/null || true)"
stripped="$(printf '%s\n' "${current}" | sed "/${BEGIN}/,/${END}/d")"

block="$(cat <<EOF
${BEGIN}
# Full cycle every 6 hours: fetch odds -> predict+commit(before kickoff) -> settle+reveal
0 */6 * * * cd ${REPO} && ${PY} scripts/pilotC_forward_loop.py >> ${LOG} 2>&1
# Daily settle-only pass so reveals bind promptly
30 3 * * * cd ${REPO} && ${PY} scripts/pilotC_forward_loop.py --settle-only >> ${LOG} 2>&1
# Extra settle-only pass at 20:00 UTC — closes the 18:00->00:00 gap so afternoon
# kickoffs settle the SAME day instead of waiting for the 03:30 pass next morning.
0 20 * * * cd ${REPO} && ${PY} scripts/pilotC_forward_loop.py --settle-only >> ${LOG} 2>&1
# Weekly health report (Mon 08:00 UTC)
0 8 * * 1 cd ${REPO} && ${PY} scripts/pilotC_forward_loop.py --health >> ${LOG} 2>&1
${END}
EOF
)"

# Reassemble: stripped crontab + our block. Trim leading blank lines.
{
  printf '%s\n' "${stripped}" | sed '/^[[:space:]]*$/d'
  printf '%s\n' "${block}"
} | crontab -

echo "Installed Pilot C cron entries. Current crontab:"
crontab -l
