#!/bin/bash
# Health check for scheduled jobs
# Run periodically to ensure launchd jobs are enabled and healthy
# Usage: ./check_launchd_jobs.sh

LOG_FILE="$HOME/Claude Code/.run_log"
JOBS=(
    "com.gautambiswas.nyt-digest"
    "com.gautambiswas.listings-refresh"
)

echo "=== Launchd Job Health Check ==="
echo "Time: $(date)"

ISSUES=()

for job in "${JOBS[@]}"; do
    # Check if job is loaded
    if launchctl list | grep -q "$job"; then
        STATUS="✓ LOADED"
    else
        STATUS="❌ NOT LOADED"
        ISSUES+=("$job is not loaded")
    fi

    # Check if job is disabled
    plist_file="$HOME/Library/LaunchAgents/${job}.plist"
    if [ -f "$plist_file" ]; then
        if grep -q "<true/>" "$plist_file" | grep -B1 "Disabled"; then
            STATUS="$STATUS (DISABLED)"
            ISSUES+=("$job has Disabled=true in plist")
        fi
    fi

    echo "$job: $STATUS"
done

# Log health check result
if [ ${#ISSUES[@]} -eq 0 ]; then
    echo "✅ All jobs healthy"
    echo "$(date '+%Y-%m-%d %H:%M')  job-health-check  ✓ OK" >> "$LOG_FILE"
else
    echo "⚠️ Issues found:"
    for issue in "${ISSUES[@]}"; do
        echo "  - $issue"
    done
    echo "$(date '+%Y-%m-%d %H:%M')  job-health-check  ⚠ ISSUES" >> "$LOG_FILE"

    # Auto-fix: Re-enable disabled jobs
    for job in "${JOBS[@]}"; do
        plist_file="$HOME/Library/LaunchAgents/${job}.plist"
        if grep -q "<key>Disabled</key>" "$plist_file"; then
            echo "Attempting to re-enable $job..."
            sed -i.bak 's/<true\/>\s*<\/key>Disabled>/<false\/><\/key>Disabled>/' "$plist_file"
            launchctl unload "$plist_file" 2>/dev/null
            launchctl load "$plist_file"
            if [ $? -eq 0 ]; then
                echo "✓ Re-enabled $job"
            fi
        fi
    done
fi
