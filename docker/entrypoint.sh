#!/bin/sh
set -eu

mkdir -p /app/data

if [ "$(id -u)" = "0" ]; then
  # 仅在目录属主不是 app(1000) 时才递归修正权限，避免每次启动都全量 chown
  owner="$(stat -c '%u' /app/data 2>/dev/null || echo 0)"
  if [ "$owner" != "1000" ]; then
    chown -R app:app /app/data
  fi
  exec gosu app "$@"
fi

exec "$@"
