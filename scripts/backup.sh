#!/bin/sh
# Copia diaria de la base (pg_dump) y de los archivos de facturas en /backups.
# Borra las copias de más de BACKUP_DIAS días. Corre dentro del servicio `backup` de docker compose.
# Cómo restaurar: ver la sección "Backups" del README.
set -eu

BACKUP_DIAS="${BACKUP_DIAS:-30}"
BACKUP_HORA="${BACKUP_HORA:-03}"

copiar() {
  fecha=$(date +%Y%m%d_%H%M%S)
  echo "[backup] $fecha: base de datos"
  pg_dump -Fc -f "/backups/agro_$fecha.dump.tmp" && mv "/backups/agro_$fecha.dump.tmp" "/backups/agro_$fecha.dump"
  echo "[backup] $fecha: archivos"
  tar czf "/backups/archivos_$fecha.tar.gz.tmp" -C /data archivos && mv "/backups/archivos_$fecha.tar.gz.tmp" "/backups/archivos_$fecha.tar.gz"
  find /backups -maxdepth 1 \( -name 'agro_*.dump' -o -name 'archivos_*.tar.gz' \) -mtime +"$BACKUP_DIAS" -delete
  echo "[backup] listo"
}

if [ "${1:-}" = "ahora" ]; then
  copiar
  exit 0
fi

# Una copia al arrancar y después una por día a la hora BACKUP_HORA.
copiar
while true; do
  ahora=$(date +%s)
  proxima=$(date -d "$(date +%Y-%m-%d) $BACKUP_HORA:00:00" +%s)
  [ "$proxima" -le "$ahora" ] && proxima=$((proxima + 86400))
  sleep $((proxima - ahora))
  copiar || echo "[backup] ERROR: la copia falló"
done
