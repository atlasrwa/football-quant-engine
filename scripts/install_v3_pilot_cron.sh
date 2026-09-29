#!/usr/bin/env bash
set -euo pipefail

MARKER_BEGIN="# >>> qfe v3 prospective pilot >>>"
MARKER_END="# <<< qfe v3 prospective pilot <<<"
WORKTREE="/home/ubuntu/handoff_out/v3_live_pilot"
LOG="/home/ubuntu/logs/v3_pilot.log"

mkdir -p /home/ubuntu/logs
current="$(crontab -l 2>/dev/null || true)"
cleaned="$(printf '%s\n' "$current" | awk -v b="$MARKER_BEGIN" -v e="$MARKER_END" '
  $0==b {skip=1; next}
  $0==e {skip=0; next}
  !skip {print}
')"

{
  printf '%s\n' "$cleaned"
  printf '%s\n' "$MARKER_BEGIN"
  printf '%s\n' "*/15 * * * * cd $WORKTREE && /usr/bin/flock -n /tmp/qfe_v3_pilot_cron.lock /home/ubuntu/.venv/bin/python scripts/v3_pilot.py tick >> $LOG 2>&1"
  printf '%s\n' "$MARKER_END"
} | crontab -

echo "Installed QFE V3 pilot cron block."
crontab -l | sed -n "/$MARKER_BEGIN/,/$MARKER_END/p"
