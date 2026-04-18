#!/usr/bin/env python3
"""Sync listings: ingest → scrape → geocode → seismic → fire → BPN."""

import argparse
import sys

from listings.db import init_db
from listings.batch_ingest import run_batch_ingest
from listings.scraper import run_scraper  # DEAD — Redfin blocks Playwright; use --skip-scrape
from listings.geocoder import run_geocoder
from listings.earthquake_hazard import enrich_properties_with_seismic_data
from listings.fire_hazard import enrich_properties_with_fire_data
from listings.bpn_enrichment import run_bpn_enrichment
from listings.utils import DB_PATH, get_gmail_service


def main():
    parser = argparse.ArgumentParser(description="Sync house listings pipeline")
    parser.add_argument("--skip-scrape", action="store_true", help="Skip Redfin scraping")
    parser.add_argument("--skip-bpn", action="store_true", help="Skip BPN enrichment")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    print("🏠 House Listings Intelligence System\n")

    # Initialize database
    print("Initializing database...")
    conn = init_db(DB_PATH)
    print(f"✓ Database ready: {DB_PATH}\n")

    # Step 1: Ingest emails (Redfin + Zillow)
    print("Step 1: Fetching Redfin and Zillow listing emails...")
    try:
        service = get_gmail_service()
        count = run_batch_ingest(conn, service)
        print(f"✓ Ingested {count} listings\n")
    except Exception as e:
        print(f"✗ Ingest failed: {e}")
        sys.exit(1)

    # Step 2: Scrape listings
    # NOTE: --skip-scrape should always be passed — Redfin blocks Playwright requests.
    # This step is dead code in practice; kept for potential future bypass implementation.
    if not args.skip_scrape:
        print("Step 2: Scraping Redfin pages...")
        try:
            count = run_scraper(conn)
            print(f"✓ Scraped {count} listings\n")
        except Exception as e:
            print(f"✗ Scraping failed: {e}")
            if args.verbose:
                raise

    # Step 3: Geocode addresses
    print("Step 3: Geocoding addresses...")
    try:
        count = run_geocoder(conn)
        print(f"✓ Geocoded {count} listings\n")
    except Exception as e:
        print(f"✗ Geocoding failed: {e}")
        if args.verbose:
            raise

    # Step 3a: Seismic hazard assessment
    print("Step 3a: Assessing seismic risk...")
    try:
        result = enrich_properties_with_seismic_data(conn)
        print(f"✓ Seismic enrichment: {result['enriched']} listings\n")
    except Exception as e:
        print(f"✗ Seismic enrichment failed: {e}")
        if args.verbose:
            raise

    # Step 3b: Fire hazard assessment
    print("Step 3b: Assessing fire hazard risk...")
    try:
        result = enrich_properties_with_fire_data(conn)
        print(f"✓ Fire hazard enrichment: {result['enriched']} listings\n")
    except Exception as e:
        print(f"✗ Fire hazard enrichment failed: {e}")
        if args.verbose:
            raise

    # Step 5: BPN enrichment
    if not args.skip_bpn:
        print("Step 5: Scraping Berkeley Parents Network...")
        try:
            count = run_bpn_enrichment(conn)
            print(f"✓ Analyzed {count} neighborhoods\n")
        except Exception as e:
            print(f"✗ BPN enrichment failed: {e}")
            if args.verbose:
                raise

    print("✓ Sync complete!")
    conn.close()


if __name__ == "__main__":
    main()
