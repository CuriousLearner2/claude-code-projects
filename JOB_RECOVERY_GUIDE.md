# Job Recovery Guide

If scheduled jobs are disabled or not running, use this guide to restore them.

## Quick Diagnosis

Check if jobs are running:
```bash
launchctl list | grep gautambiswas
```

Expected output:
```
-	0	com.gautambiswas.nyt-digest
-	0	com.gautambiswas.listings-refresh
-	0	com.gautambiswas.job-health-check
```

The first number is the exit code (0 = healthy, non-zero = failed).

## Manual Health Check (Anytime)

```bash
/Users/gautambiswas/Claude\ Code/check_launchd_jobs.sh
```

## If Jobs Are Disabled

### Option 1: Auto-Recovery (Recommended)
The health check can auto-repair most issues:
```bash
# This will detect and fix disabled jobs
/Users/gautambiswas/Claude\ Code/check_launchd_jobs.sh
```

### Option 2: Manual Re-enable

**For listings-refresh:**
```bash
launchctl unload ~/Library/LaunchAgents/com.gautambiswas.listings-refresh.plist
launchctl load ~/Library/LaunchAgents/com.gautambiswas.listings-refresh.plist
```

**For nyt-digest:**
```bash
launchctl unload ~/Library/LaunchAgents/com.gautambiswas.nyt-digest.plist
launchctl load ~/Library/LaunchAgents/com.gautambiswas.nyt-digest.plist
```

**For job-health-check:**
```bash
launchctl unload ~/Library/LaunchAgents/com.gautambiswas.job-health-check.plist
launchctl load ~/Library/LaunchAgents/com.gautambiswas.job-health-check.plist
```

### Option 3: Force Restore All
If multiple jobs are broken:
```bash
cd ~/Library/LaunchAgents
for plist in com.gautambiswas.*.plist; do
    launchctl unload "$plist" 2>/dev/null
    launchctl load "$plist"
    echo "Loaded $plist"
done
```

## Prevention Measures in Place

✅ **Read-only plist files** (chmod 444)
- Prevents accidental modification
- Can only be changed by explicitly changing permissions

✅ **Cron verification with auto-repair** (independent of launchd)
- Runs at 7:10 AM (10 minutes after scheduled jobs at 7:00 AM)
- Detects job status: completed, still running, or failed
- Sends email if jobs are still running (normal) or if auto-repairs were needed
- Auto-repairs failed jobs by reloading launchd and manually triggering them
- Fast failure detection: know within 10 minutes if something went wrong

## If All Else Fails

**Contact:** The person who set this up (see memory: feedback_launchd_job_monitoring.md)

**Logs to check:**
```bash
tail -50 /Users/gautambiswas/.local/share/job-logs/nyt-digest-launchd.log
tail -50 /Users/gautambiswas/.local/share/job-logs/listings-refresh-launchd.log
tail -50 /Users/gautambiswas/.local/share/job-logs/job-health-check.log
tail -50 /Users/gautambiswas/.local/share/job-logs/verify-jobs.log
```

**Last resort - manual trigger:**
```bash
# Run listings refresh manually
cd /Users/gautambiswas/Claude\ Code/real-estate
/Users/gautambiswas/Claude\ Code/run_daily_refresh.sh

# Run NY Times digest manually
cd /Users/gautambiswas/Claude\ Code/nyt
python3 nyt_digest.py
```

## Monitoring Status

Check the run log to see job history:
```bash
tail -20 /Users/gautambiswas/Claude\ Code/.run_log
```

Recent entries should show:
```
2026-05-04 06:55  job-health-check  ✓ OK
2026-05-04 07:00  nyt-digest        ✓ OK
2026-05-04 07:00  listings-refresh  ✓ OK
```

## Security Notes

Plist files are read-only to prevent accidental disabling:
```bash
ls -l ~/Library/LaunchAgents/com.gautambiswas.*.plist
# Should show: -r--r--r--
```

To modify a plist, you'd need to explicitly change permissions first:
```bash
chmod 644 ~/Library/LaunchAgents/com.gautambiswas.nyt-digest.plist
# Then edit...
# Then restore read-only:
chmod 444 ~/Library/LaunchAgents/com.gautambiswas.nyt-digest.plist
```

This prevents accidental modification from scripts or tools.
