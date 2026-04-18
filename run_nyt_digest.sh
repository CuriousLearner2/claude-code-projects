#!/bin/bash
# Wrapper for nyt_digest.py
# Resilience: dated logs, already-ran guard, retry on failure, email alerts.

JOB="nyt_digest"
SCRIPT_DIR="/Users/gautambiswas/Claude Code/nyt"
PYTHON="/opt/homebrew/bin/python3"
SCRIPT="$SCRIPT_DIR/nyt_digest.py"
ALERT_PY="/Users/gautambiswas/Claude Code/send_alert.py"
ALERT_PYTHON="/Users/gautambiswas/Claude Code/real-estate/venv/bin/python"
LOG_DIR="$HOME/.local/share/job-logs"
TODAY=$(date +%Y-%m-%d)
LOG="$LOG_DIR/${JOB}_${TODAY}.log"
STAMP="$LOG_DIR/${JOB}_last_run"
MAX_ATTEMPTS=3
RETRY_DELAY=300  # 5 minutes

mkdir -p "$LOG_DIR"
exec >> "$LOG" 2>&1

echo "=== $(date) === $JOB starting ==="

send_alert() {
    "$ALERT_PYTHON" "$ALERT_PY" "$JOB" "$1" "$LOG" 2>&1 || true
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
    PYTHONUNBUFFERED=1 PYTHONPATH="/Users/gautambiswas/Claude Code/real-estate" \
        "$PYTHON" -u "$SCRIPT"
    EXIT_CODE=$?
    if [[ $EXIT_CODE -eq 0 ]]; then
        echo "$TODAY" > "$STAMP"
        echo "=== $(date) === $JOB succeeded (attempt $attempt) ==="
        find "$LOG_DIR" -name "${JOB}_*.log" -mtime +7 -delete 2>/dev/null
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
