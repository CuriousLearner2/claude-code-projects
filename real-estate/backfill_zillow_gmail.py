#!/usr/bin/env python3
"""Backfill Zillow listings from Gmail. Fetches all Zillow emails and ingests them."""
import sys
import hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from listings.utils import get_gmail_service, get_anthropic_client
from listings.gmail_ingest import fetch_emails_by_query, get_full_email, parse_zillow_email
from listings.db import init_db, upsert_listing

DB_PATH = str(Path(__file__).parent / "listings" / "listings.db")
ZILLOW_QUERY = "from:mail.zillow.com"


def main():
    conn = init_db(DB_PATH)
    service = get_gmail_service()

    print("Fetching Zillow email list from Gmail...")
    msg_refs = fetch_emails_by_query(service, ZILLOW_QUERY, "0")
    print(f"Found {len(msg_refs)} Zillow emails")

    total_inserted = 0
    total_skipped = 0

    for i, ref in enumerate(msg_refs, 1):
        msg_id = ref["id"]
        try:
            em = get_full_email(service, msg_id)
        except Exception as exc:
            print(f"  WARN {msg_id}: {exc}")
            continue

        subject = em.get("subject", "")
        received_at = em.get("received_at", "")
        plain_body = em.get("plain_body", "")
        html_body = em.get("html_body", "")

        props = parse_zillow_email(plain_body, html_body, received_at, subject)
        if not props:
            total_skipped += 1
            continue

        for prop in props:
            if not prop.get("address") or not prop.get("price"):
                continue
            prop["received_at"] = received_at
            prop["subject"] = subject
            prop["source"] = "Zillow"
            prop["gmail_message_id"] = msg_id
            key = ((prop.get("address") or "") + (prop.get("city") or "") + "Zillow").encode()
            prop["id"] = hashlib.sha1(key).hexdigest()
            prop.setdefault("state", "CA")
            upsert_listing(conn, prop)
            total_inserted += 1

        conn.commit()

        if i % 20 == 0:
            print(f"  {i}/{len(msg_refs)} emails processed, {total_inserted} listings upserted")

    print(f"\nDone. {total_inserted} Zillow listings upserted, {total_skipped} emails skipped (no parseable listings).")
    conn.close()


if __name__ == "__main__":
    main()
