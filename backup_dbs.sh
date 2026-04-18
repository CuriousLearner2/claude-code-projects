#!/bin/bash
# Daily backup for listings.db and nyt.db.
# Keeps 30 days of backups in ~/.local/share/db-backups/.

BACKUP_DIR="$HOME/.local/share/db-backups"
TODAY=$(date +%Y-%m-%d)
RETENTION_DAYS=30
JOB="backup_dbs"

LISTINGS_DB="/Users/gautambiswas/Claude Code/real-estate/listings/listings.db"
NYT_DB="/Users/gautambiswas/Claude Code/nyt/nyt.db"
ALERT_PY="/Users/gautambiswas/Claude Code/send_alert.py"
ALERT_PYTHON="/Users/gautambiswas/Claude Code/real-estate/venv/bin/python"

LOG="$HOME/.local/share/job-logs/backup_dbs_${TODAY}.log"
mkdir -p "$BACKUP_DIR" "$HOME/.local/share/job-logs"
exec >> "$LOG" 2>&1

send_alert() {
    "$ALERT_PYTHON" "$ALERT_PY" "$JOB" "$1" "$LOG" 2>&1 || true
}

echo "=== $(date) === backup_dbs starting ==="

ERRORS=0

backup_db() {
    local src="$1"
    local name="$2"
    local dest="$BACKUP_DIR/${name}_${TODAY}.db"

    if [[ ! -f "$src" ]]; then
        echo "ERROR: $src not found"
        send_alert "$name DB not found at $src"
        ERRORS=$((ERRORS + 1))
        return
    fi
    if [[ ! -s "$src" ]]; then
        echo "ERROR: $src is empty (0 bytes)"
        send_alert "$name DB is empty at $src"
        ERRORS=$((ERRORS + 1))
        return
    fi
    sqlite3 "$src" ".backup '$dest'"
    if [[ $? -ne 0 ]]; then
        echo "ERROR: sqlite3 backup failed for $name"
        send_alert "$name DB backup failed"
        ERRORS=$((ERRORS + 1))
        return
    fi
    SIZE=$(du -h "$dest" | cut -f1)
    echo "  ✓ $name → $dest ($SIZE)"
}

backup_db "$LISTINGS_DB" "listings"
backup_db "$NYT_DB" "nyt"

# Rotate old backups
find "$BACKUP_DIR" -name "*.db" -mtime +$RETENTION_DAYS -delete 2>/dev/null
echo "  Rotated backups older than $RETENTION_DAYS days"

if [[ $ERRORS -gt 0 ]]; then
    echo "=== $(date) === backup_dbs FAILED ($ERRORS errors) ==="
    exit 1
fi

echo "=== $(date) === backup_dbs complete ==="
