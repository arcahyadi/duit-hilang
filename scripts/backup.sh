#!/bin/sh
# Daily backup: dump postgres and upload to remote backup location.
# Set BACKUP_TARGET to e.g. user@backup-host:/backups/finance (scp) or leave empty for local-only.

set -e
TS=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/backups
mkdir -p "$BACKUP_DIR"

pg_dump -U finance -h db finance | gzip > "$BACKUP_DIR/finance_$TS.sql.gz"

# Keep 30 days locally
find "$BACKUP_DIR" -name "finance_*.sql.gz" -mtime +30 -delete

if [ -n "$BACKUP_TARGET" ]; then
  scp "$BACKUP_DIR/finance_$TS.sql.gz" "$BACKUP_TARGET"
fi
