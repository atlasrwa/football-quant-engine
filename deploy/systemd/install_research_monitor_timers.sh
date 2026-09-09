#!/usr/bin/env bash
# Install the research-monitor systemd USER timers (heartbeat/alerts/weekly).
#
# These report collector health + research readiness to Telegram during DATA
# ACCUMULATION MODE. They read persisted state only (no TheStatsAPI calls) and
# never publish betting signals.
#
# Usage:
#   bash deploy/systemd/install_research_monitor_timers.sh
#   systemctl --user list-timers 'research-monitor-*'
#   journalctl --user -u 'research-monitor@*' -n 50
set -euo pipefail

UNIT_DIR="${HOME}/.config/systemd/user"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "${UNIT_DIR}"
install -m 0644 "${SRC_DIR}/research-monitor@.service"          "${UNIT_DIR}/research-monitor@.service"
install -m 0644 "${SRC_DIR}/research-monitor-heartbeat.timer"   "${UNIT_DIR}/research-monitor-heartbeat.timer"
install -m 0644 "${SRC_DIR}/research-monitor-alerts.timer"      "${UNIT_DIR}/research-monitor-alerts.timer"
install -m 0644 "${SRC_DIR}/research-monitor-weekly.timer"      "${UNIT_DIR}/research-monitor-weekly.timer"

systemctl --user daemon-reload
systemctl --user enable --now research-monitor-heartbeat.timer
systemctl --user enable --now research-monitor-alerts.timer
systemctl --user enable --now research-monitor-weekly.timer

echo "Installed research-monitor timers:"
systemctl --user list-timers 'research-monitor-*' --no-pager || true
