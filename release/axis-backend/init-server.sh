#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-axis}"
APP_DIR="${APP_DIR:-/opt/axis}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root: sudo bash deploy/linux/init-server.sh"
  exit 1
fi

apt-get update
apt-get install -y nginx unzip curl ca-certificates mysql-client python3 python3-venv python3-pip

if ! id "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "${APP_USER}"
fi

mkdir -p "${APP_DIR}/backend"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo "Base server packages installed."
echo "App directory: ${APP_DIR}"
echo "App user: ${APP_USER}"
echo "Next: upload backend/, then install Python dependencies and systemd/nginx templates."
