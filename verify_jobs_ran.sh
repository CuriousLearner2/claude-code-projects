#!/bin/bash
# Verify that scheduled jobs ran today (runs via cron as backup)
# This is independent of launchd, so it catches launchd failures
# Auto-repairs jobs that didn't run
# Usage: crontab -e, then add line for this script

LOG_FILE="/Users/gautambiswas/Claude Code/.run_log"
TODAY=$(date +%Y-%m-%d)
ALERT_EMAIL="gautambiswas2004@gmail.com"
REPAIRS=()

echo "=== Job Verification Check ($(date)) ==="

# Function to repair a failed job
repair_job() {
    local job_name=$1
    local plist_path=$2
    local run_script=$3

    echo "Attempting to repair $job_name..."
    REPAIRS+=("$job_name")

    # Reload the launchd job
    launchctl unload "$plist_path" 2>/dev/null
    launchctl load "$plist_path"
    if [ $? -ne 0 ]; then
        echo "❌ Failed to reload $job_name"
        return 1
    fi

    # Manually trigger the job
    if [ -n "$run_script" ] && [ -f "$run_script" ]; then
        bash "$run_script" >> "$LOG_FILE" 2>&1 &
        echo "✓ Reloaded and triggered $job_name"
    else
        echo "✓ Reloaded $job_name (script not available for manual trigger)"
    fi
    return 0
}

# Check if today's health check ran
if grep -q "$TODAY.*job-health-check.*OK" "$LOG_FILE"; then
    echo "✓ Health check ran today"
else
    echo "⚠ Health check did NOT run today"
    repair_job "job-health-check" \
        "$HOME/Library/LaunchAgents/com.gautambiswas.job-health-check.plist" \
        "/Users/gautambiswas/Claude Code/check_launchd_jobs.sh"
fi

# Check if nyt-digest ran
if grep -q "$TODAY.*nyt-digest.*OK" "$LOG_FILE"; then
    echo "✓ NY Times digest ran today"
else
    echo "⚠ NY Times digest did NOT run today"
    repair_job "nyt-digest" \
        "$HOME/Library/LaunchAgents/com.gautambiswas.nyt-digest.plist" \
        ""
fi

# Check if listings-refresh ran
if grep -q "$TODAY.*listings-refresh.*OK" "$LOG_FILE"; then
    echo "✓ Listings refresh ran today"
else
    echo "⚠ Listings refresh did NOT run today"
    repair_job "listings-refresh" \
        "$HOME/Library/LaunchAgents/com.gautambiswas.listings-refresh.plist" \
        "/Users/gautambiswas/Claude Code/run_daily_refresh.sh"
fi

# Send alert if repairs were made
if [ ${#REPAIRS[@]} -gt 0 ]; then
    echo ""
    echo "⚙️ Auto-repairs completed:"
    for job in "${REPAIRS[@]}"; do
        echo "  - $job"
    done

    # Email alert about repairs
    {
        echo "Jobs that failed to run were auto-repaired on $TODAY:"
        echo ""
        for job in "${REPAIRS[@]}"; do
            echo "  ✓ $job"
        done
        echo ""
        echo "The jobs have been reloaded and manually triggered."
        echo "Check the run log for details: tail -20 /Users/gautambiswas/Claude\ Code/.run_log"
    } | mail -s "✓ Auto-Repaired Failed Jobs on $TODAY" "$ALERT_EMAIL"
fi

echo "Done."
