"""
One-off script: ingest historical El Cerrito listings from Gmail since 2023-01-01.

Searches Gmail for Redfin/Zillow emails mentioning El Cerrito, bypasses the
gmail_id dedup gate, and relies on address-level dedup to avoid duplicates.
"""
import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from listings.db import upsert_listing, get_listing_by_address
from listings.utils import get_anthropic_client, get_gmail_service
from listings.gmail_ingest import (
    fetch_emails_by_query,
    get_full_email,
    extract_properties_from_batch_email,
    parse_listing_email,
    parse_zillow_email,
    is_rental_listing,
    is_allowed_city,
)
from listings.batch_ingest import (
    _normalize_email,
    _try_regex_parse,
    _needs_claude,
    _build_batch_requests,
    _submit_and_poll_batch,
    _parse_batch_results,
    _coerce_property_types,
)

DB_PATH = "listings/listings.db"
SINCE_DATE = "2023/01/01"


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ingest_el_cerrito():
    conn = get_conn()
    service = get_gmail_service()
    client = get_anthropic_client()

    all_emails = []

    # Search for El Cerrito emails from Redfin and Zillow
    for source, sender in [
        ("Redfin", "from:listings@redfin.com"),
        ("Zillow", "from:instant-updates@mail.zillow.com"),
    ]:
        query = f'{sender} "El Cerrito" after:{SINCE_DATE}'
        print(f"Searching Gmail: {query}")
        msgs = fetch_emails_by_query(service, query, "0")
        print(f"  Found {len(msgs)} messages")
        for msg_info in msgs:
            email = get_full_email(service, msg_info["id"])
            if email:
                email["source"] = source
                all_emails.append(_normalize_email(email))

    print(f"\nTotal emails to process: {len(all_emails)}")
    if not all_emails:
        print("No El Cerrito emails found.")
        return

    # Regex parse
    regex_results = {}
    emails_needing_claude = {}
    for email in all_emails:
        gmail_id = email["id"]
        props = _try_regex_parse(email)
        if _needs_claude(props):
            emails_needing_claude[gmail_id] = email
        else:
            regex_results[gmail_id] = props

    # Claude batch for emails needing it
    claude_results = {}
    if emails_needing_claude:
        print(f"Submitting {len(emails_needing_claude)} emails to batch API...")
        batch_reqs = _build_batch_requests(emails_needing_claude)
        batch_results = _submit_and_poll_batch(client, batch_reqs)
        claude_results = _parse_batch_results(batch_results, emails_needing_claude)

    # Merge + upsert — bypass gmail_id dedup, use address-level dedup only
    email_by_id = {e["id"]: e for e in all_emails}
    count = 0

    for gmail_id, email in email_by_id.items():
        props = claude_results.get(gmail_id) or regex_results.get(gmail_id, [])

        for prop in props:
            # Only process El Cerrito listings
            if prop.get("city", "").lower() != "el cerrito":
                continue

            if is_rental_listing(prop, prop.get("redfin_url")):
                continue

            if not is_allowed_city(prop.get("city")):
                continue

            address = prop.get("address")
            if not address:
                continue

            if not all([prop.get("beds"), prop.get("baths"), prop.get("house_sqft"), prop.get("city")]):
                continue

            # Address-level dedup
            existing = get_listing_by_address(conn, address)
            if existing:
                continue  # already in DB

            prop["id"] = f"{gmail_id}_{address.replace(' ', '_').replace(',', '')[:20]}"

            listing = {
                "id": prop["id"],
                "gmail_message_id": gmail_id,
                "subject": email.get("subject", ""),
                "received_at": email.get("received_at"),
                "source": email.get("source", ""),
                **prop,
            }

            upsert_listing(conn, listing)
            count += 1
            price_str = f"(${prop.get('price'):,})" if prop.get("price") else ""
            print(f"  + {address}, El Cerrito {price_str}")

    print(f"\nDone. {count} El Cerrito listings ingested.")
    conn.close()


if __name__ == "__main__":
    ingest_el_cerrito()
