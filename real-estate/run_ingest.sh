#!/bin/bash
# Reliable ingest script - runs email ingest with explicit environment setup

set -e

# Project directory
PROJECT_DIR="/Users/gautambiswas/Claude Code/real-estate"
cd "$PROJECT_DIR"

# Source environment (loads Google Maps API key and other env vars)
source ~/.zshrc

# Run the ingest
echo "Starting email ingest..."
python3 << 'EOPYTHON'
from listings.db import init_db
from listings.utils import get_gmail_service
from listings.batch_ingest import run_batch_ingest

conn = init_db("listings/listings.db")
try:
    service = get_gmail_service()
    count = run_batch_ingest(conn, service)
    if count > 0:
        print(f"\n✓ Successfully ingested {count} new listings")
    else:
        print("\nℹ No new listings found")
    exit(0)
except Exception as e:
    print(f"\n✗ Error: {e}")
    import traceback; traceback.print_exc()
    exit(1)
finally:
    conn.close()
EOPYTHON
