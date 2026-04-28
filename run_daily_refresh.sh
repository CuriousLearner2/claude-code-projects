#!/bin/bash
# Wrapper for daily_refresh.py
# Resilience: dated logs, already-ran guard, retry on failure, email alerts.

JOB="daily_refresh"
SCRIPT_DIR="/Users/gautambiswas/Claude Code/real-estate"
PYTHON="$SCRIPT_DIR/venv/bin/python"
SCRIPT="$SCRIPT_DIR/daily_refresh.py"
ALERT_PY="/Users/gautambiswas/Claude Code/send_alert.py"
LOG_DIR="$HOME/.local/share/job-logs"
TODAY=$(date +%Y-%m-%d)
LOG="$LOG_DIR/${JOB}_${TODAY}.log"
STAMP="$LOG_DIR/${JOB}_last_run"
MAX_ATTEMPTS=3
RETRY_DELAY=300  # 5 minutes

mkdir -p "$LOG_DIR"
exec >> "$LOG" 2>&1

# Load .env so iCloud credentials are available
ENV_FILE="/Users/gautambiswas/Claude Code/.env"
if [[ -f "$ENV_FILE" ]]; then
    set -a; source "$ENV_FILE"; set +a
fi

echo "=== $(date) === $JOB starting ==="

send_alert() {
    "$PYTHON" "$ALERT_PY" "$JOB" "$1" "$LOG" 2>&1 || true
}

# ── Already-ran guard ─────────────────────────────────────────────────────────
if [[ -f "$STAMP" && "$(cat "$STAMP")" == "$TODAY" ]]; then
    echo "Already ran today ($TODAY), skipping."
    exit 0
fi

# ── Pre-flight checks ─────────────────────────────────────────────────────────
if [[ ! -f "$PYTHON" ]]; then
    echo "ERROR: Python not found at $PYTHON"
    send_alert "Python not found at $PYTHON"
    exit 1
fi
if [[ ! -f "$SCRIPT" ]]; then
    echo "ERROR: Script not found at $SCRIPT"
    send_alert "Script not found at $SCRIPT"
    exit 1
fi

cd "$SCRIPT_DIR" || { echo "ERROR: Cannot cd to $SCRIPT_DIR"; send_alert "Cannot cd to $SCRIPT_DIR"; exit 1; }

# ── Retry loop ────────────────────────────────────────────────────────────────
for attempt in $(seq 1 $MAX_ATTEMPTS); do
    echo "--- Attempt $attempt/$MAX_ATTEMPTS ---"
    PYTHONUNBUFFERED=1 "$PYTHON" -u "$SCRIPT"
    EXIT_CODE=$?
    if [[ $EXIT_CODE -eq 0 ]]; then
        echo "$TODAY" > "$STAMP"
        echo "=== $(date) === $JOB succeeded (attempt $attempt) ==="
        find "$LOG_DIR" -name "${JOB}_*.log" -mtime +7 -delete 2>/dev/null

        # Commit and push DB snapshot to GitHub
        REPO_DIR="/Users/gautambiswas/Claude Code"
        cd "$REPO_DIR" || true
        if /usr/bin/git diff --quiet real-estate/listings/listings.db 2>/dev/null; then
            echo "DB unchanged, skipping git push."
        else
            /usr/bin/git add real-estate/listings/listings.db nyt/nyt.db 2>/dev/null
            /usr/bin/git commit -m "chore: DB snapshot $(date +%Y-%m-%d)" 2>/dev/null
            /usr/bin/git push origin main 2>/dev/null && echo "DB pushed to GitHub." || echo "WARN: git push failed."
        fi

        exit 0
    fi
    echo "Attempt $attempt failed (exit $EXIT_CODE)"
    if [[ $attempt -lt $MAX_ATTEMPTS ]]; then
        echo "Retrying in ${RETRY_DELAY}s..."
        sleep $RETRY_DELAY
    fi
done

echo "=== $(date) === $JOB FAILED after $MAX_ATTEMPTS attempts ==="
send_alert "Failed after $MAX_ATTEMPTS attempts (last exit $EXIT_CODE)"
exit 1
