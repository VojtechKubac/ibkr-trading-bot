#!/usr/bin/env bash
# Install the trading-bot systemd user timer.
# Run from anywhere; the script locates the project root automatically.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SYSTEMD_USER_DIR="${HOME}/.config/systemd/user"

echo "Project root : ${PROJECT_DIR}"
echo "Systemd dir  : ${SYSTEMD_USER_DIR}"

mkdir -p "${SYSTEMD_USER_DIR}"

for unit in trading-bot.service trading-bot.timer; do
    sed "s|{PROJECTDIR}|${PROJECT_DIR}|g" \
        "${SCRIPT_DIR}/${unit}" \
        > "${SYSTEMD_USER_DIR}/${unit}"
    echo "Installed    : ${SYSTEMD_USER_DIR}/${unit}"
done

systemctl --user daemon-reload
systemctl --user enable --now trading-bot.timer

echo ""
echo "Next scheduled run:"
systemctl --user list-timers trading-bot.timer
