#!/usr/bin/env python3
"""Backfill zip codes for all listings using reverse geocoding from existing lat/lon."""

import os
import sqlite3
import time
from pathlib import Path

import requests

DB_PATH = "listings/listings.db"


def source_env():
    zshrc = Path.home() / ".zshrc"
    if zshrc.exists():
        for line in zshrc.read_text().splitlines():
            line = line.strip()
            if line.startswith("export "):
                assignment = line[7:]
                if "=" in assignment:
                    key, value = assignment.split("=", 1)
                    key, value = key.strip(), value.strip()
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    if key and value:
                        os.environ[key] = value


def reverse_geocode_zip(lat: float, lon: float, api_key: str) -> str | None:
    """Return zip code for coordinates via Google Maps reverse geocoding."""
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    resp = requests.get(url, params={"latlng": f"{lat},{lon}", "key": api_key}, timeout=10)
    if resp.status_code != 200:
        return None
    data = resp.json()
    if data.get("status") != "OK":
        return None
    for result in data.get("results", []):
        for component in result.get("address_components", []):
            if "postal_code" in component.get("types", []):
                return component["long_name"]
    return None


def main():
    source_env()
    api_key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_MAPS_API_KEY not set")
        return 1

    conn = sqlite3.connect(DB_PATH)

    # Get all listings needing zip codes, grouped by unique lat/lon
    cursor = conn.execute("""
        SELECT DISTINCT latitude, longitude
        FROM listings
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL AND zip_code IS NULL
        ORDER BY latitude, longitude
    """)
    coords = cursor.fetchall()
    print(f"Found {len(coords)} unique coordinate pairs needing zip codes")

    updated = 0
    failed = 0
    for i, (lat, lon) in enumerate(coords):
        zip_code = reverse_geocode_zip(lat, lon, api_key)
        if zip_code:
            conn.execute(
                "UPDATE listings SET zip_code = ? WHERE latitude = ? AND longitude = ? AND zip_code IS NULL",
                (zip_code, lat, lon)
            )
            conn.commit()
            updated += conn.total_changes
            if (i + 1) % 50 == 0:
                print(f"  [{i+1}/{len(coords)}] {lat},{lon} → {zip_code}")
        else:
            failed += 1
        time.sleep(0.05)  # ~20 req/s, well under quota

    conn.close()

    # Summary
    conn2 = sqlite3.connect(DB_PATH)
    row = conn2.execute("SELECT COUNT(*), COUNT(zip_code) FROM listings WHERE latitude IS NOT NULL").fetchone()
    conn2.close()
    print(f"\nDone. {row[1]}/{row[0]} geocoded listings now have zip codes ({failed} failed)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
