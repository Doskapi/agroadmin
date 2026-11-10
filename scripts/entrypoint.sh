#!/bin/sh
# Si arranca como root: le da al usuario `app` el volumen de archivos y ejecuta el comando como `app`.
set -e
if [ "$(id -u)" = "0" ]; then
  dir="${STORAGE_DIR:-/data/archivos}"
  mkdir -p "$dir"
  if [ "$(stat -c %u "$dir")" != "10001" ]; then
    chown -R app:app "$dir"
  fi
  exec setpriv --reuid=app --regid=app --init-groups "$@"
fi
exec "$@"
