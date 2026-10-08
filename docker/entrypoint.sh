#!/bin/sh
set -eu

mkdir -p /app/data

if [ "$(id -u)" = "0" ]; then
  chown -R app:app /app/data
  exec gosu app "$@"
fi

exec "$@"
