#!/usr/bin/env python3
"""Ingest exactly 50 Redfin emails starting from Jan 1, 2024 (oldest first)."""

import sys
sys.path.insert(0, '/Users/gautambiswas/Claude Code/real-estate')

from datetime import datetime, timezone
from listings.utils import get_gmail_service, DB_PATH
from listings.gmail_ingest import (
    get_full_email,
    extract_properties_from_batch_email,
    is_rental_listing,
    is_allowed_city
)
from listings.db import init_db


def fetch_oldest_n_emails(service, query, n):
    """Paginate through all matching emails and return the oldest n."""
    all_messages = []
    page_token = None

    while True:
        kwargs = {'userId': 'me', 'q': query, 'maxResults': 500}
        if page_token:
            kwargs['pageToken'] = page_token
        results = service.users().messages().list(**kwargs).execute()
        msgs = results.get('messages', [])
        all_messages.extend(msgs)
        page_token = results.get('nextPageToken')
        if not page_token:
            break

    # Gmail returns newest-first; reverse to get oldest-first
    all_messages.reverse()
    return all_messages[:n]


def ingest_50_redfin():
    """Fetch and ingest 50 oldest Redfin emails from Jan 1, 2024 onward."""
    conn = init_db(DB_PATH)
    service = get_gmail_service()

    print("Paginating Redfin emails from Jan 1, 2024 (oldest first)...")
    messages = fetch_oldest_n_emails(
        service,
        'from:listings@redfin.com after:2024-01-01',
        50
    )
    print(f"Found {len(messages)} emails to process")

    count = 0
    skipped = 0

    for i, msg_info in enumerate(messages):
        print(f"Processing email {i+1}/{len(messages)}...", end='\r')

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

                placeholders = ', '.join(f":{k}" for k in listing.keys())
                cols = ', '.join(listing.keys())
                cursor.execute(
                    f"INSERT OR REPLACE INTO listings ({cols}) VALUES ({placeholders})",
                    listing
                )
                conn.commit()

                count += 1
                price = f"${prop.get('price'):,}" if prop.get('price') else ""
                print(f"  + {address} {price}  [{received_at[:10] if received_at else 'no date'}]")

        except Exception as e:
            print(f"Error processing email {i+1}: {e}")
            skipped += 1
            continue

    print(f"\n✓ Ingest complete: {count} new Redfin listings, {skipped} skipped")

    # Report final state
    cursor = conn.cursor()
    cursor.execute("SELECT source, COUNT(*) FROM listings GROUP BY source")
    print("\nFinal database state:")
    for source, cnt in cursor.fetchall():
        print(f"  {source}: {cnt}")

    cursor.execute("SELECT MIN(received_at), MAX(received_at) FROM listings WHERE source='Redfin'")
    row = cursor.fetchone()
    print(f"\nRedfin date range: {row[0][:10] if row[0] else 'N/A'} to {row[1][:10] if row[1] else 'N/A'}")


if __name__ == '__main__':
    ingest_50_redfin()
