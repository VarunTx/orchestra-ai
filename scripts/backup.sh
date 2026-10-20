#!/usr/bin/env bash
# Back up both PostgreSQL databases (Conductor history + platform inventory).
# Runs on the host that owns the Compose project. Never uploads anything unless
# RCLONE_REMOTE is set explicitly.
set -euo pipefail
cd "$(dirname "$0")/.."

BACKUP_DIR="${BACKUP_DIR:-backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
COMPOSE="${COMPOSE_CMD:-docker compose}"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

for db in conductor orchestra; do
  target="$BACKUP_DIR/${db}-${STAMP}.sql.gz"
  if $COMPOSE exec -T postgres pg_dump -U conductor -d "$db" --no-owner --clean --if-exists \
      | gzip -c > "$target"; then
    gzip -t "$target"
    printf 'backup ok  %s  (%s)\n' "$target" "$(du -h "$target" | cut -f1)"
  else
    printf 'backup FAILED for %s\n' "$db" >&2
    rm -f "$target"
    exit 1
  fi
done

find "$BACKUP_DIR" -name '*.sql.gz' -type f -mtime "+${KEEP_DAYS}" -delete

if [[ -n "${RCLONE_REMOTE:-}" ]]; then
  rclone copy "$BACKUP_DIR" "$RCLONE_REMOTE" --include '*.sql.gz'
  printf 'copied to %s\n' "$RCLONE_REMOTE"
else
  printf 'local only; set RCLONE_REMOTE to copy offsite (Oracle Object Storage is free)\n'
fi
