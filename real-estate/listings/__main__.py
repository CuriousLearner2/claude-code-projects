"""Entrypoint for listings module - supports running ingest with 'python3 -m listings.gmail_ingest'"""

import sqlite3
import sys
from listings.gmail_ingest import run_ingest
from listings.db import init_db
from listings.utils import get_gmail_service


def main():
    """Run the email ingest."""
    db_path = "listings.db"
    conn = init_db(db_path)

    try:
        service = get_gmail_service()
        count = run_ingest(conn, service)

        if count > 0:
            print(f"\n✓ Successfully ingested {count} new listings")
        else:
            print("\nNo new listings found")

    except Exception as e:
        print(f"Error during ingest: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
