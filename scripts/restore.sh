#!/usr/bin/env bash
# Restore a backup into a NEW database by default, so a restore drill cannot
# destroy live data. Use --in-place only with an explicit typed confirmation.
set -euo pipefail
cd "$(dirname "$0")/.."

usage() {
  cat <<'TXT'
usage: scripts/restore.sh <backup.sql.gz> [--database NAME] [--in-place]

  default target: <source>_restore   (creates it; never touches the live database)
  --database     restore into this database name instead
  --in-place     replace the live <source> database (prompts for the name)
TXT
  exit 1
}

[[ $# -ge 1 ]] || usage
FILE="$1"; shift
IN_PLACE=0
TARGET=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --in-place) IN_PLACE=1; shift ;;
    --database) TARGET="${2:?}"; shift 2 ;;
    *) usage ;;
  esac
done

[[ -f "$FILE" ]] || { echo "no such file: $FILE" >&2; exit 1; }
gzip -t "$FILE"

BASE="$(basename "$FILE")"
SOURCE="${BASE%%-*}"
[[ "$SOURCE" == "conductor" || "$SOURCE" == "orchestra" ]] || { echo "unrecognised backup name: $BASE" >&2; exit 1; }

if (( IN_PLACE )); then
  TARGET="${TARGET:-$SOURCE}"
  printf 'This will REPLACE the live "%s" database. Type the name to continue: ' "$TARGET"
  read -r typed
  [[ "$typed" == "$TARGET" ]] || { echo "aborted"; exit 1; }
  docker compose exec -T postgres psql -U conductor -d "$TARGET" -c 'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
else
  TARGET="${TARGET:-${SOURCE}_restore}"
fi

docker compose exec -T postgres psql -U conductor -d postgres -tAc \
  "SELECT 1 FROM pg_database WHERE datname='${TARGET}'" | grep -q 1 \
  || docker compose exec -T postgres psql -U conductor -d postgres -c "CREATE DATABASE \"${TARGET}\""

gunzip -c "$FILE" | docker compose exec -T postgres psql -U conductor -d "$TARGET" -v ON_ERROR_STOP=1 >/dev/null
docker compose exec -T postgres psql -U conductor -d "$TARGET" -c 'ANALYZE' >/dev/null
printf 'restored %s into %s\n' "$BASE" "$TARGET"
(( IN_PLACE )) || printf 'verify it, then drop it: docker compose exec postgres psql -U conductor -d postgres -c "DROP DATABASE \\"%s\\""\n' "$TARGET"
