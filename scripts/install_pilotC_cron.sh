#!/usr/bin/env bash
# Install the shared data-pipeline cron entries — idempotently.
#
# HISTORY: this script used to install the Pilot C forward loop as well. Pilot C was
# deprecated on 2026-09-05 (see public_site/failure_ledger.json F024) and its four
# entries — the 6-hourly full cycle, the 03:30 and 20:20 settle-only passes, and the
# Monday 08:20 health report — were REMOVED. Its ledgers are preserved untouched;
# only the collection schedule is gone. A deprecated experiment must not keep
# spending budget or paging a human.
#
# The entries below are NOT Pilot C's. They serve the shared fixture/odds data
# pipeline and the daily signals delivery, and are retained.
#
# CRITICAL — CREDENTIALS: these entries invoke the venv interpreter directly, and
# cron runs with a minimal environment. THESTATS_API_KEY is currently exported only
# from ~/.bashrc, which returns early for non-interactive shells, so cron cannot see
# it. Scripts here call load_env() to read /home/ubuntu/.env, so the key belongs in
# .env alongside FOOTYSTATS_API_KEY. Until it is there, every TheStatsAPI call from
# cron aborts with SystemExit 2. That is exactly what killed Pilot C, and it is why
# thestatsapi_client.is_clean_stop() now exists: an auth failure must never be
# recorded as a tidy budget stop.
#
# Schedule (UTC):
#   - daily simple-model signals + Telegram delivery at 00:00.
#   - hourly raw-provider and price-change scan; flock prevents a slow scan from
#     overlapping the next invocation. Only fully gated candidates are alerted.
#   - provider league identity/capability registry refresh daily at 00:30. Metadata
#     only; it never promotes research leagues.
#
# Re-running this script is safe: it removes any prior block (both the legacy Pilot C
# marker and the current one) before re-adding the current block. It never touches
# other lines, including Pipeline A's quarantine_forward_loop entry and the forecast
# broadcast block managed by install_forecast_broadcast_cron.sh.

set -euo pipefail

PY="/home/ubuntu/.venv/bin/python"
REPO="/home/ubuntu"
LOG="${REPO}/logs/daily_signals_telegram.log"
ALERT_LOG="${REPO}/logs/fixture_alert_watcher.log"
SYNC_LOG="${REPO}/logs/provider_league_sync.log"

# Current marker.
BEGIN="# >>> shared data pipeline (managed by install_pilotC_cron.sh) >>>"
END="# <<< shared data pipeline <<<"
# Legacy marker from when this block also carried Pilot C. Stripped so a re-run
# cleanly migrates an existing crontab instead of leaving both blocks installed.
LEGACY_BEGIN="# >>> pilotC forward loop (managed by install_pilotC_cron.sh) >>>"
LEGACY_END="# <<< pilotC forward loop <<<"

if [[ ! -x "${PY}" ]]; then
  echo "ERROR: venv python not found at ${PY}." >&2
  exit 1
fi

mkdir -p "${REPO}/logs"

# Current crontab (empty string if none), with both the legacy and current blocks
# stripped. sed addresses are literal comment lines, so nothing else is touched.
current="$(crontab -l 2>/dev/null || true)"
stripped="$(printf '%s\n' "${current}" \
  | sed "\\|${LEGACY_BEGIN}|,\\|${LEGACY_END}|d" \
  | sed "\\|${BEGIN}|,\\|${END}|d")"

block="$(cat <<EOF
${BEGIN}
CRON_TZ=UTC
# NOTE: Pilot C's four entries were removed here on 2026-09-05 (deprecated, see F024).
# Its ledgers are preserved; only the collection schedule was withdrawn.
# Generate the daily simple-model signals and deliver any new Telegram messages at 00:00 UTC.
0 0 * * * cd ${REPO} && /usr/bin/flock -n /tmp/daily_signals_telegram.lock /bin/bash -lc '${PY} -m src.cli daily-signals && ${PY} scripts/signals_telegram_bot.py' >> ${LOG} 2>&1
# Revalidate today's fixtures every 60 minutes, starting at 00:00 UTC; alert only EV candidates that pass every gate.
0 * * * * cd ${REPO} && /usr/bin/flock -n /tmp/fixture_alert_watcher.lock ${PY} scripts/fixture_alert_watcher.py >> ${ALERT_LOG} 2>&1
# Refresh the fail-closed FootyStats <-> TheStatsAPI league registry daily.
30 0 * * * cd ${REPO} && /usr/bin/flock -n /tmp/provider_league_sync.lock ${PY} scripts/sync_provider_leagues.py --refresh >> ${SYNC_LOG} 2>&1
${END}
EOF
)"

# Reassemble: stripped crontab + our block. Trim leading blank lines.
{
  printf '%s\n' "${stripped}" | sed '/^[[:space:]]*$/d'
  printf '%s\n' "${block}"
} | crontab -

echo "Installed shared data-pipeline cron entries (Pilot C entries removed). Current crontab:"
crontab -l
