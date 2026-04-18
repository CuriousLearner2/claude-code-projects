#!/usr/bin/env python3
"""Backfill redfin_url for existing listings by re-fetching email HTML from Gmail."""
import base64
import re
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from listings.utils import get_gmail_service
from listings.db import init_db

DB_PATH = str(Path(__file__).parent / "listings" / "listings.db")


def decode_body(payload: dict) -> str:
    """Recursively extract HTML body from Gmail payload."""
    mime = payload.get("mimeType", "")
    if mime == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    for part in payload.get("parts", []):
        result = decode_body(part)
        if result:
            return result
    return ""


def find_redfin_url(html: str) -> str | None:
    """Find the first redfin.com/CA property URL in raw HTML."""
    match = re.search(r'href="(https?://(?:www\.)?redfin\.com/CA/[^"]+)"', html)
    return match.group(1) if match else None


def main():
    conn = init_db(DB_PATH)
    rows = conn.execute(
        "SELECT id, gmail_message_id FROM listings "
        "WHERE (redfin_url IS NULL OR redfin_url = '') AND gmail_message_id IS NOT NULL"
    ).fetchall()
    total = len(rows)
    print(f"Backfilling URLs for {total} listings…")
    sys.stdout.flush()

    # Single service, sequential — avoids thread-safety crash in Apple TLS
    service = get_gmail_service()
    updated = 0

    for i, row in enumerate(rows, 1):
        listing_id, msg_id = row[0], row[1]
        url = None
        for attempt in range(3):
            try:
                msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
                html = decode_body(msg.get("payload", {}))
                url = find_redfin_url(html)
                break
            except Exception as exc:
                if attempt == 2:
                    print(f"  WARN {msg_id}: {exc}")
                    sys.stdout.flush()
                else:
                    time.sleep(2 ** attempt)

        if url:
            conn.execute(
                "UPDATE listings SET redfin_url = ?, updated_at = datetime('now') WHERE id = ?",
                (url, listing_id)
            )
            conn.commit()
            updated += 1

        if i % 100 == 0:
            print(f"  {i}/{total} processed, {updated} URLs found")
            sys.stdout.flush()

    print(f"Done. {updated}/{total} listings now have a redfin_url.")


if __name__ == "__main__":
    main()
