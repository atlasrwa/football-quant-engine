#!/usr/bin/env bash
# Install the prospective-capture systemd USER timer (runs capture-due every 15m).
#
# systemd user units survive reboot when linger is enabled for the user:
#   sudo loginctl enable-linger "$USER"
# (On this host linger is already enabled.)
#
# Usage:
#   bash deploy/systemd/install_prospective_capture_timer.sh
#   systemctl --user list-timers prospective-capture.timer
#   journalctl --user -u prospective-capture.service -n 50
#   systemctl --user stop  prospective-capture.timer     # pause
#   systemctl --user start prospective-capture.timer     # resume
#   systemctl --user disable --now prospective-capture.timer  # remove
set -euo pipefail

UNIT_DIR="${HOME}/.config/systemd/user"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

mkdir -p "${UNIT_DIR}"
install -m 0644 "${SRC_DIR}/prospective-capture.service" "${UNIT_DIR}/prospective-capture.service"
install -m 0644 "${SRC_DIR}/prospective-capture.timer"   "${UNIT_DIR}/prospective-capture.timer"

systemctl --user daemon-reload
systemctl --user enable --now prospective-capture.timer

echo "Installed and started prospective-capture.timer:"
systemctl --user list-timers prospective-capture.timer --no-pager || true
