#!/usr/bin/env bash
# Daily SQLite backup, run inside the CarCatcher LXC via cron.
# Mirrors the lunch-planner backup convention: consistent online .backup,
# timestamped, 14-day retention.
set -euo pipefail

DB_PATH="${DATABASE_PATH:-/data/db/carcatcher.db}"
BACKUP_DIR="${BACKUP_DIR:-/data/backups}"
RETENTION_DAYS="${RETENTION_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="$BACKUP_DIR/carcatcher-$STAMP.db"

if [[ ! -f "$DB_PATH" ]]; then
  echo "[backup] DB not found at $DB_PATH — skipping" >&2
  exit 0
fi

# Online-consistent copy (safe while the app is running).
sqlite3 "$DB_PATH" ".backup '$OUT'"
gzip -f "$OUT"
echo "[backup] wrote ${OUT}.gz"

# Prune old backups.
find "$BACKUP_DIR" -name 'carcatcher-*.db.gz' -mtime "+$RETENTION_DAYS" -delete
echo "[backup] pruned backups older than ${RETENTION_DAYS}d"
