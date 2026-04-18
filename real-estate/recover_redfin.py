#!/usr/bin/env python3
"""Direct Redfin recovery: fetch and parse emails, upsert to DB without batch pipeline."""

import sys
sys.path.insert(0, '/Users/gautambiswas/Claude Code/real-estate')

import sqlite3
from datetime import datetime, timezone
from listings.utils import get_gmail_service, DB_PATH
from listings.gmail_ingest import (
    get_full_email,
    extract_properties_from_batch_email,
    is_rental_listing,
    is_allowed_city
)
from listings.db import init_db, get_listing_by_address

def recover_redfin_direct():
    """Fetch Redfin emails and parse directly without batch API."""
    conn = init_db(DB_PATH)
    service = get_gmail_service()

    # Fetch Redfin emails
    print("Fetching Redfin emails...")
    results = service.users().messages().list(
        userId='me',
        q='from:listings@redfin.com',
        maxResults=500
    ).execute()

    messages = results.get('messages', [])
    print(f"Found {len(messages)} Redfin emails")

    count = 0
    skipped = 0

    for i, msg_info in enumerate(messages):
        if i % 50 == 0:
            print(f"Processing email {i+1}/{len(messages)}...")

        try:
            email = get_full_email(service, msg_info['id'])
            if not email:
                continue

            html = email.get('html_body', '')
            subject = email.get('subject', '')
            gmail_id = email.get('id')
            received_at = email.get('date')

            # Parse properties (pass subject for city extraction)
            props = extract_properties_from_batch_email(html, subject)

            for prop in props:
                # Apply filters
                if is_rental_listing(prop, prop.get("redfin_url")):
                    skipped += 1
                    continue

                if not is_allowed_city(prop.get("city")):
                    skipped += 1
                    continue

                address = prop.get('address')
                if not address:
                    skipped += 1
                    continue

                # Require minimal set: address, city, beds, baths, sqft
                if not all([prop.get('beds'), prop.get('baths'), prop.get('house_sqft'), prop.get('city')]):
                    skipped += 1
                    continue

                # Dedup: one record per address, keep most recent
                ts = received_at or datetime.now(timezone.utc).isoformat()
                cursor = conn.cursor()
                cursor.execute("SELECT id, received_at FROM listings WHERE address = ?", (address,))
                existing = cursor.fetchone()

                if existing:
                    existing_id, existing_ts = existing
                    if ts <= existing_ts:
                        skipped += 1
                        continue
                    listing_id = existing_id
                else:
                    listing_id = f"{gmail_id}_{address.replace(' ', '_').replace(',', '')[:20]}"

                listing = {
                    "id": listing_id,
                    "gmail_message_id": gmail_id,
                    "subject": subject,
                    "received_at": ts,
                    "source": "Redfin",
                    **prop
                }

                # Insert into database
                cursor = conn.cursor()
                placeholders = ', '.join(f":{k}" for k in listing.keys())
                cols = ', '.join(listing.keys())
                query = f"""
                    INSERT OR REPLACE INTO listings ({cols})
                    VALUES ({placeholders})
                """
                cursor.execute(query, listing)
                conn.commit()

                count += 1
                if count % 10 == 0:
                    price = f"${prop.get('price'):,}" if prop.get('price') else ""
                    print(f"  + {address} {price}")

        except Exception as e:
            print(f"Error processing email {i}: {e}")
            skipped += 1
            continue

    print(f"\n✓ Recovery complete: {count} Redfin listings ingested, {skipped} skipped")

    # Report final state
    cursor = conn.cursor()
    cursor.execute("SELECT source, COUNT(*) FROM listings GROUP BY source")
    print("\nFinal database state:")
    for source, cnt in cursor.fetchall():
        print(f"  {source}: {cnt}")

if __name__ == '__main__':
    recover_redfin_direct()
