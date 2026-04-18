#!/usr/bin/env python3
"""Fetch and parse the N most recent Redfin listing emails, output JSON."""

import json
import sys

from listings.gmail_ingest import fetch_emails_by_query, get_full_email, extract_properties_from_batch_email
from listings.utils import get_gmail_service


def fetch_redfin_listings(n: int = 2) -> list:
    service = get_gmail_service()
    messages = fetch_emails_by_query(service, "from:listings@redfin.com", "0")
    messages = messages[:n]

    all_listings = []
    for msg in messages:
        email = get_full_email(service, msg["id"])
        if not email:
            continue
        props = extract_properties_from_batch_email(email["html_body"], email["subject"])
        for p in props:
            all_listings.append({
                "address": p.get("address"),
                "city": p.get("city"),
                "state": p.get("state"),
                "price": p.get("price"),
                "beds": p.get("beds"),
                "baths": p.get("baths"),
                "house_sqft": p.get("house_sqft"),
                "lot_size_sqft": p.get("lot_size_sqft"),
                "hoa_monthly": p.get("hoa_monthly"),
                "garage_spots": p.get("garage_spots"),
                "listing_url": p.get("redfin_url"),
            })

    # Deduplicate by (address, price)
    seen = set()
    deduped = []
    for listing in all_listings:
        key = (listing.get("address"), listing.get("price"))
        if key not in seen:
            seen.add(key)
            deduped.append(listing)

    return deduped


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    print(json.dumps(fetch_redfin_listings(n), indent=2))
