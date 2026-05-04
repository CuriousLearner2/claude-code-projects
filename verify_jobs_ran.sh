#!/bin/bash
# Verify that scheduled jobs ran today (runs via cron as backup)
# This is independent of launchd, so it catches launchd failures
# Usage: crontab -e, then add line for this script

LOG_FILE="/Users/gautambiswas/Claude Code/.run_log"
TODAY=$(date +%Y-%m-%d)
ALERT_EMAIL="gautambiswas2004@gmail.com"

echo "=== Job Verification Check ($(date)) ==="

# Check if today's health check ran
if grep -q "$TODAY.*job-health-check.*OK" "$LOG_FILE"; then
    echo "✓ Health check ran today"
else
    echo "⚠ Health check did NOT run today"
    echo "This could indicate launchd is not working properly"

    # Send alert
    echo "Missing job-health-check on $TODAY. This may indicate launchd failure." | \
        mail -s "⚠️ Job Health Check Missed on $TODAY" "$ALERT_EMAIL"
fi

# Check if nyt-digest ran
if grep -q "$TODAY.*nyt-digest.*OK" "$LOG_FILE"; then
    echo "✓ NY Times digest ran today"
else
    echo "⚠ NY Times digest did NOT run today"
fi

# Check if listings-refresh ran
if grep -q "$TODAY.*listings-refresh.*OK" "$LOG_FILE"; then
    echo "✓ Listings refresh ran today"
else
    echo "⚠ Listings refresh did NOT run today"
fi

echo "Done."
