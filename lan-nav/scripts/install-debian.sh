#!/usr/bin/env bash
# Debian 12+ 安装辅助脚本（需 root）
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/lan-nav}"
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "请使用 root 运行：sudo bash scripts/install-debian.sh" >&2
  exit 1
fi

apt update
apt install -y python3 python3-venv python3-pip nginx rsync

id -u lan-nav >/dev/null 2>&1 || useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin lan-nav

mkdir -p "$APP_DIR"
rsync -a --delete \
  --exclude '.venv' \
  --exclude '.env' \
  --exclude 'data/navigation.yml' \
  --exclude 'data/navigation.yml.bak' \
  --exclude '__pycache__' \
  --exclude '.pytest_cache' \
  "$SRC_DIR/" "$APP_DIR/"

cd "$APP_DIR"
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

if [[ ! -f .env ]]; then
  cp .env.example .env
  sed -i 's/^DEBUG=.*/DEBUG=false/' .env
fi

mkdir -p data
chown -R lan-nav:lan-nav "$APP_DIR"
chmod 750 "$APP_DIR"
chmod 640 "$APP_DIR/.env"

cp deploy/lan-nav.service /etc/systemd/system/lan-nav.service
systemctl daemon-reload
systemctl enable --now lan-nav

cp deploy/nginx.conf.example /etc/nginx/sites-available/lan-nav
ln -sfn /etc/nginx/sites-available/lan-nav /etc/nginx/sites-enabled/lan-nav
nginx -t
systemctl reload nginx

echo
echo "安装完成。"
echo "服务状态：systemctl status lan-nav"
echo "访问：在客户端 /etc/hosts 添加「<Debian内网IP> nav.lan」后打开 http://nav.lan"
echo "请确认 $APP_DIR/data 对 lan-nav 用户可写。"
