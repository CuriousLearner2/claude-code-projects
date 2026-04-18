#!/usr/bin/env python3
"""Retry fire hazard enrichment. Intended to be called by launchd until all listings are enriched."""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from listings.db import init_db
from listings.fire_hazard import enrich_properties_with_fire_data

DB_PATH = str(Path(__file__).parent / "listings" / "listings.db")


def main():
    conn = init_db(DB_PATH)
    pending = conn.execute("SELECT COUNT(*) FROM listings WHERE fire_risk_score IS NULL").fetchone()[0]

    if pending == 0:
        print("All listings enriched — unloading launchd agent.")
        import subprocess
        subprocess.run([
            "launchctl", "unload",
            str(Path.home() / "Library/LaunchAgents/com.gautam.fire-hazard-enrichment.plist")
        ])
        sys.exit(0)

    print(f"{pending} listings need fire hazard enrichment, running...")
    stats = enrich_properties_with_fire_data(conn)
    print(f"Done: {stats}")

    # Check if fully done now
    remaining = conn.execute("SELECT COUNT(*) FROM listings WHERE fire_risk_score IS NULL").fetchone()[0]
    if remaining == 0:
        print("All listings enriched — unloading launchd agent.")
        import subprocess
        subprocess.run([
            "launchctl", "unload",
            str(Path.home() / "Library/LaunchAgents/com.gautam.fire-hazard-enrichment.plist")
        ])
    elif stats["errors"] > 0 and stats["enriched"] == 0:
        # API still down — exit non-zero so launchd logs the failure
        sys.exit(1)


if __name__ == "__main__":
    main()
