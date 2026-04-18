#!/bin/bash
# Daily backup for listings.db and nyt.db.
# Keeps 30 days of backups in ~/.local/share/db-backups/.

BACKUP_DIR="$HOME/.local/share/db-backups"
TODAY=$(date +%Y-%m-%d)
RETENTION_DAYS=30

LISTINGS_DB="/Users/gautambiswas/Claude Code/real-estate/listings/listings.db"
NYT_DB="/Users/gautambiswas/Claude Code/nyt/nyt.db"

LOG="$HOME/.local/share/job-logs/backup_dbs_${TODAY}.log"
mkdir -p "$BACKUP_DIR" "$HOME/.local/share/job-logs"
exec >> "$LOG" 2>&1

echo "=== $(date) === backup_dbs starting ==="

backup_db() {
    local src="$1"
    local name="$2"
    local dest="$BACKUP_DIR/${name}_${TODAY}.db"

    if [[ ! -f "$src" ]]; then
        echo "WARNING: $src not found, skipping"
        return
    fi
    if [[ ! -s "$src" ]]; then
        echo "WARNING: $src is empty (0 bytes), skipping"
        return
    fi
    # Use SQLite online backup via .dump to handle live DBs safely
    sqlite3 "$src" ".backup '$dest'"
    SIZE=$(du -h "$dest" | cut -f1)
    echo "  ✓ $name → $dest ($SIZE)"
}

backup_db "$LISTINGS_DB" "listings"
backup_db "$NYT_DB" "nyt"

# Rotate old backups
find "$BACKUP_DIR" -name "*.db" -mtime +$RETENTION_DAYS -delete 2>/dev/null
echo "  Rotated backups older than $RETENTION_DAYS days"

echo "=== $(date) === backup_dbs complete ==="
