# OAuth Credentials Management Guide

## Overview

The Gmail and Google Calendar APIs use OAuth 2.0 for authentication. This guide explains how credentials work and how to avoid authentication failures.

## File Roles

### `credentials.json`
- **What it is**: OAuth app configuration (client ID, client secret)
- **Where it comes from**: Google Cloud Console
- **Lifespan**: Permanent until you regenerate it
- **Generated on**: First setup OR when you regenerate credentials in Google Cloud Console

### `token.json`
- **What it is**: User authentication token that proves your identity
- **Where it comes from**: Generated automatically when you go through OAuth login flow
- **Lifespan**: Long-lasting (doesn't expire unless revoked or unused for 6+ months)
- **Generated on**: First OAuth login OR when token becomes invalid

## The Mismatch Problem

**Critical Issue**: If you regenerate `credentials.json` in Google Cloud Console, the old `token.json` becomes **invalid**.

### Why This Happens
1. You regenerate credentials in Google Cloud Console (new client ID, client secret)
2. The old `token.json` was created with the OLD client ID/secret
3. Google no longer recognizes the token with the new credentials
4. Authentication fails until you re-generate the token

### How to Detect
```bash
# Check if credentials and token are in sync
/Users/gautambiswas/Claude\ Code/validate_oauth_credentials.sh
```

If `credentials.json` is newer than `token.json`, they're out of sync.

## Prevention: Automatic Detection

The `get_gmail_service()` function in `listings/utils.py` now automatically:
1. Checks if `credentials.json` is newer than `token.json`
2. If so, deletes the stale `token.json`
3. Forces re-authentication on the next job run

**You don't need to do anything** — it's handled automatically.

## Manual Fix (if needed)

If you regenerate credentials and want to immediately fix the mismatch:

```bash
# Option 1: Run the validation script
/Users/gautambiswas/Claude\ Code/validate_oauth_credentials.sh

# Option 2: Manual delete (forces re-auth on next run)
rm ~/Claude\ Code/token.json
```

Then run any job that uses Gmail (listings-refresh or nyt-digest). It will prompt you through the OAuth flow once.

## When You Regenerate Credentials

If you regenerate credentials in Google Cloud Console for any reason:

1. Nothing breaks immediately
2. The automatic detection (in `get_gmail_service()`) will handle it
3. Next time a job runs, you'll be prompted to re-authenticate
4. You'll see the OAuth login screen (one-time only)

**You don't need to manually delete token.json** — it's automatic.

## Troubleshooting

### "Token has been expired or revoked"

**Cause**: Usually a credentials/token mismatch (not actual expiration)

**Fix**:
```bash
/Users/gautambiswas/Claude\ Code/validate_oauth_credentials.sh
```

### Job requires interactive authentication but runs scheduled

**Cause**: Token became invalid, script needs re-auth but can't do it in background

**Fix**: 
1. Run the validation script above
2. Run any job manually once to complete OAuth flow
3. Scheduled jobs will work again

### Token.json gets deleted repeatedly

**Cause**: `credentials.json` keeps being regenerated

**Fix**: Stop regenerating credentials in Google Cloud Console. Leave them as-is.

## Best Practices

✅ **Do**:
- Keep `credentials.json` unchanged unless explicitly regenerating
- Let the automatic detection handle mismatches
- Run `validate_oauth_credentials.sh` if you suspect a problem

❌ **Don't**:
- Manually delete `token.json` (let the automatic detection handle it)
- Regenerate credentials repeatedly without reason
- Share `credentials.json` or `token.json` with anyone

## Files Involved

- `credentials.json` - OAuth app configuration (in `/Users/gautambiswas/Claude Code/`)
- `token.json` - User authentication token (in `/Users/gautambiswas/Claude Code/`)
- `validate_oauth_credentials.sh` - Manual validation script
- `listings/utils.py` - Contains automatic mismatch detection
