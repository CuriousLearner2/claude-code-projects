#!/bin/bash
# Validate OAuth credentials freshness
# If credentials.json has been regenerated, token.json becomes invalid
# This script detects the mismatch and forces re-authentication

BASE_DIR="/Users/gautambiswas/Claude Code"
CREDS_FILE="$BASE_DIR/credentials.json"
TOKEN_FILE="$BASE_DIR/token.json"

echo "=== OAuth Credentials Validation ==="

# Check if both files exist
if [ ! -f "$CREDS_FILE" ]; then
    echo "❌ credentials.json not found at $CREDS_FILE"
    exit 1
fi

if [ ! -f "$TOKEN_FILE" ]; then
    echo "⚠️  token.json not found — will be regenerated on next auth"
    exit 0
fi

# Get modification times
CREDS_MTIME=$(stat -f%m "$CREDS_FILE" 2>/dev/null || stat -c%Y "$CREDS_FILE")
TOKEN_MTIME=$(stat -f%m "$TOKEN_FILE" 2>/dev/null || stat -c%Y "$TOKEN_FILE")

# Format for display
CREDS_DATE=$(stat -f"%Sm -f %Y-%m-%d" "$CREDS_FILE" 2>/dev/null || date -d @$CREDS_MTIME "+%Y-%m-%d %H:%M:%S")
TOKEN_DATE=$(stat -f"%Sm -f %Y-%m-%d" "$TOKEN_FILE" 2>/dev/null || date -d @$TOKEN_MTIME "+%Y-%m-%d %H:%M:%S")

echo "credentials.json: $CREDS_DATE"
echo "token.json:       $TOKEN_DATE"

# If credentials.json is newer, token is stale
if [ $CREDS_MTIME -gt $TOKEN_MTIME ]; then
    echo ""
    echo "⚠️  MISMATCH DETECTED!"
    echo "credentials.json was regenerated after token.json was created."
    echo "The token is now invalid and needs to be regenerated."
    echo ""
    echo "Deleting stale token.json..."
    rm -f "$TOKEN_FILE"
    echo "✓ Deleted $TOKEN_FILE"
    echo ""
    echo "Next time a job runs, it will automatically re-authenticate."
    exit 0
else
    echo ""
    echo "✓ Credentials are fresh and in sync with token"
    exit 0
fi
