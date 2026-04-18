#!/usr/bin/env python3
"""Ingest the next 50 listing emails (Redfin + Zillow), oldest first, with offset support."""

import sys
import json
import os
sys.path.insert(0, '/Users/gautambiswas/Claude Code/real-estate')

from datetime import datetime, timezone

STATS_FILE = '/Users/gautambiswas/Claude Code/real-estate/.ingest_stats.json'

def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE) as f:
            return json.load(f)
    return {'Redfin': 0, 'Zillow': 0}

def save_stats(stats):
    with open(STATS_FILE, 'w') as f:
        json.dump(stats, f)
from listings.utils import get_gmail_service, DB_PATH
from listings.gmail_ingest import (
    get_full_email,
    extract_properties_from_batch_email,
    parse_zillow_email,
    is_rental_listing,
    is_allowed_city
)
from listings.db import init_db


def fetch_all_emails(service, query):
    """Paginate through all matching emails, return list with internalDate."""
    all_messages = []
    page_token = None
    while True:
        kwargs = {'userId': 'me', 'q': query, 'maxResults': 500}
        if page_token:
            kwargs['pageToken'] = page_token
        results = service.users().messages().list(**kwargs).execute()
        all_messages.extend(results.get('messages', []))
        page_token = results.get('nextPageToken')
        if not page_token:
            break
    return all_messages


def insert_listing(conn, prop, gmail_id, subject, received_at, source):
    """Validate minimal set and insert listing. Returns True if inserted."""
    address = prop.get('address')
    if not address:
        return False

    if not all([prop.get('beds'), prop.get('baths'), prop.get('house_sqft'), prop.get('city')]):
        return False

    if is_rental_listing(prop, prop.get("redfin_url")):
        return False

    if not is_allowed_city(prop.get("city")):
        return False

    cursor = conn.cursor()
    cursor.execute("SELECT id, received_at FROM listings WHERE address = ?", (address,))
    existing = cursor.fetchone()
    ts = received_at or datetime.now(timezone.utc).isoformat()

    if existing:
        existing_id, existing_ts = existing
        # Only update if this email is more recent
        if ts <= existing_ts:
            return False
        # Update existing record with newer data
        listing = {
            "id": existing_id,
            "gmail_message_id": gmail_id,
            "subject": subject,
            "received_at": ts,
            "source": source,
            **prop
        }
    else:
        listing = {
            "id": f"{gmail_id}_{address.replace(' ', '_').replace(',', '')[:20]}",
            "gmail_message_id": gmail_id,
            "subject": subject,
            "received_at": ts,
            "source": source,
            **prop
        }

    placeholders = ', '.join(f":{k}" for k in listing.keys())
    cols = ', '.join(listing.keys())
    conn.execute(
        f"INSERT OR REPLACE INTO listings ({cols}) VALUES ({placeholders})",
        listing
    )
    conn.commit()
    return True


def ingest_next_50(offset=0, count=50):
    conn = init_db(DB_PATH)
    service = get_gmail_service()

    print("Fetching all listing emails (oldest first)...")
    redfin_msgs = fetch_all_emails(service, 'from:listings@redfin.com after:2024-01-01')
    zillow_msgs = fetch_all_emails(service, 'from:instant-updates@mail.zillow.com after:2024-01-01')

    # Tag each with source
    for m in redfin_msgs:
        m['source'] = 'Redfin'
    for m in zillow_msgs:
        m['source'] = 'Zillow'

    # We need internalDate to sort — fetch lightweight metadata
    all_msgs = redfin_msgs + zillow_msgs
    print(f"Found {len(redfin_msgs)} Redfin + {len(zillow_msgs)} Zillow = {len(all_msgs)} total emails")
    print(f"Processing emails {offset+1}–{offset+count} (oldest first)...")

    # Get internalDate for sorting via metadata fetch
    print("Loading timestamps for sorting...")
    dated = []
    for m in all_msgs:
        meta = service.users().messages().get(
            userId='me', id=m['id'], format='metadata',
            metadataHeaders=['Date']
        ).execute()
        dated.append((int(meta.get('internalDate', 0)), m))

    dated.sort(key=lambda x: x[0])
    batch = dated[offset:offset + count]
    print(f"Processing {len(batch)} emails...")

    added = 0
    skipped = 0

    for ts, msg_info in batch:
        source = msg_info['source']
        email = get_full_email(service, msg_info['id'])
        if not email:
            skipped += 1
            continue

        html = email.get('html_body', '')
        plain = email.get('plain_body', '')
        subject = email.get('subject', '')
        gmail_id = email.get('id')
        received_at = email.get('date')

        if source == 'Redfin':
            props = extract_properties_from_batch_email(html, subject)
        else:
            props = parse_zillow_email(plain, html, received_at or '', subject)
            if not isinstance(props, list):
                props = [props] if props else []

        for prop in props:
            if insert_listing(conn, prop, gmail_id, subject, received_at, source):
                added += 1
                price = f"${prop.get('price'):,}" if prop.get('price') else ""
                date_str = received_at[:10] if received_at else 'no date'
                print(f"  + [{source}] {prop.get('address')} {price}  [{date_str}]")
            else:
                skipped += 1

    print(f"\n✓ Done: {added} new listings, {skipped} skipped")

    cursor = conn.cursor()
    cursor.execute("SELECT source, COUNT(*) FROM listings GROUP BY source")
    totals = {src: cnt for src, cnt in cursor.fetchall()}

    prev = load_stats()
    save_stats(totals)

    print("\nDatabase state:")
    for src in ('Redfin', 'Zillow'):
        total = totals.get(src, 0)
        new = total - prev.get(src, 0)
        print(f"  {src}: {total} total (+{new} new)")

    cursor.execute("SELECT MIN(received_at), MAX(received_at) FROM listings")
    row = cursor.fetchone()
    print(f"\nDate range: {row[0][:10] if row[0] else 'N/A'} to {row[1][:10] if row[1] else 'N/A'}")


if __name__ == '__main__':
    offset = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    ingest_next_50(offset=offset, count=count)
