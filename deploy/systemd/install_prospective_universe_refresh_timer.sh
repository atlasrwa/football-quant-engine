#!/usr/bin/env bash
# Install the fixture-universe-refresh systemd USER timer (runs discovery every 6h).
#
# WHY: the shared discovered fixture universe (_pilotC_fixture_list.json) lost its
# only frequent refresher when Pilot C was deprecated. The surviving twice-weekly
# cron entry (Mon & Thu 06:00 UTC) leaves a 72h gap and cannot keep the universe
# under the heartbeat's 36h stale-inflow threshold. This timer restores a
# conservative 6-hourly INDEPENDENT refresh that reuses the existing, tested
# discovery command unchanged. It is failure-isolated from the 15-minute
# prospective-capture timer (separate unit) and shares the discovery lock so it can
# never race the legacy cron entry.
#
# systemd user units survive reboot when linger is enabled for the user:
#   sudo loginctl enable-linger "$USER"
# (On this host linger is already enabled.)
#
# Usage:
#   bash deploy/systemd/install_prospective_universe_refresh_timer.sh
#   systemctl --user list-timers prospective-universe-refresh.timer
#   journalctl --user -u prospective-universe-refresh.service -n 50
#   systemctl --user stop  prospective-universe-refresh.timer     # pause
#   systemctl --user start prospective-universe-refresh.timer     # resume
#   systemctl --user disable --now prospective-universe-refresh.timer  # remove
#
# NOTE: once this timer is active you may remove the legacy Mon/Thu discovery cron
# entry (managed by install_forecast_broadcast_cron.sh) to avoid two schedulers for
# the same artifact. Leaving both is safe (shared lock) but redundant; this script
# does NOT touch crontab.
set -euo pipefail

UNIT_DIR="${HOME}/.config/systemd/user"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "${UNIT_DIR}"
install -m 0644 "${SRC_DIR}/prospective-universe-refresh.service" "${UNIT_DIR}/prospective-universe-refresh.service"
install -m 0644 "${SRC_DIR}/prospective-universe-refresh.timer"   "${UNIT_DIR}/prospective-universe-refresh.timer"

systemctl --user daemon-reload
systemctl --user enable --now prospective-universe-refresh.timer

echo "Installed and started prospective-universe-refresh.timer:"
systemctl --user list-timers prospective-universe-refresh.timer --no-pager || true
