"""Compare BS4 vs Visual extractor on Zillow emails from the last ingest run."""

import base64
import json
import os
import re
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Zillow email IDs from the last ingest run
ZILLOW_EMAIL_IDS = [
    "19d71c6c7b902e4b",
    "19d47efbebd365d7",
    "19d71e76fd8c4a42",
    "19d728451d3b28d1",
    "19d72aeac35a65d9",
    "19d72b7bc5750f7a",
    "19d72d47deb604e6",
    "19d72d481621a4d7",
    "19d73099c12ef104",
    "19d43c568c633c52",
    "19d68d25f331cb8c",
]

PROJECT_DIR = Path("/Users/gautambiswas/Claude Code/real-estate")
DB_PATH = PROJECT_DIR / "listings" / "listings.db"


# ─── DB helpers ──────────────────────────────────────────────────────────────

def get_bs4_listings_for_emails(email_ids: List[str]) -> List[Dict]:
    """Fetch stored listings whose gmail_message_id is in email_ids."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" * len(email_ids))
    rows = conn.execute(
        f"SELECT * FROM listings WHERE gmail_message_id IN ({placeholders})",
        email_ids
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── Gmail fetch ─────────────────────────────────────────────────────────────

def fetch_html_bodies(email_ids: List[str]) -> Dict[str, Dict]:
    """Return {email_id: {subject, html_body}} for each id."""
    sys.path.insert(0, str(PROJECT_DIR))
    from listings.gmail_ingest import get_full_email
    from listings.utils import get_gmail_service

    service = get_gmail_service()
    result = {}
    for eid in email_ids:
        email = get_full_email(service, eid)
        if email:
            result[eid] = {
                "subject": email.get("subject", ""),
                "html_body": email.get("html_body", ""),
            }
            print(f"  Fetched: {eid[:16]}  subject={email.get('subject','')[:60]}")
        else:
            print(f"  FAILED:  {eid}")
    return result


# ─── Playwright rendering + card screenshots ─────────────────────────────────

def render_and_crop_cards(html_body: str, email_id: str, tmpdir: str) -> List[str]:
    """
    Render HTML with Playwright, crop individual listing card elements to PNG files.
    Returns list of file paths for card images.
    """
    from playwright.sync_api import sync_playwright

    card_paths = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 800, "height": 4000})
        page.set_content(html_body, wait_until="networkidle")

        # Zillow card selectors — try multiple
        selectors = [
            "[class*='listing-card']",
            "[class*='listingCard']",
            "[class*='property-card']",
            "[class*='propertyCard']",
            "table[class*='listing']",
            # Generic: table rows that contain a price-like pattern
        ]

        cards = []
        for sel in selectors:
            cards = page.query_selector_all(sel)
            if cards:
                break

        # Fallback: find <td> elements containing price pattern
        if not cards:
            cards = page.evaluate_handle("""() => {
                const tds = Array.from(document.querySelectorAll('td, div'));
                return tds.filter(el => /\\$[\\d,]+/.test(el.innerText) && el.innerText.length < 2000);
            }""")
            # query_selector_all returns element handles; evaluate_handle returns JSHandle
            # Use a different approach
            cards = []
            all_els = page.query_selector_all("td, div")
            for el in all_els:
                try:
                    text = el.inner_text()
                    if re.search(r'\$[\d,]+', text) and 50 < len(text) < 2000:
                        box = el.bounding_box()
                        if box and box["width"] > 150 and box["height"] > 80:
                            cards.append(el)
                except Exception:
                    pass

        if not cards:
            print(f"    No cards found for {email_id}")
            browser.close()
            return []

        for i, card in enumerate(cards[:20]):
            path = os.path.join(tmpdir, f"{email_id}_card_{i:02d}.png")
            try:
                card.screenshot(path=path)
                # Verify file has content
                if os.path.getsize(path) > 500:
                    card_paths.append(path)
            except Exception as e:
                print(f"    Card {i} screenshot error: {e}")

        browser.close()

    return card_paths


# ─── Resize helper ───────────────────────────────────────────────────────────

def resize_image(src_path: str, max_width: int = 600) -> str:
    """Resize image to max_width while preserving aspect ratio. Returns new path."""
    from PIL import Image
    img = Image.open(src_path)
    w, h = img.size
    if w > max_width:
        ratio = max_width / w
        img = img.resize((max_width, int(h * ratio)), Image.LANCZOS)
    out_path = src_path.replace(".png", "_resized.png")
    img.save(out_path)
    return out_path


# ─── Visual extraction ───────────────────────────────────────────────────────

def extract_from_card_image(client, image_path: str) -> Optional[Dict]:
    """Send a card image to Claude vision and extract listing fields."""
    with open(image_path, "rb") as f:
        img_data = base64.b64encode(f.read()).decode()

    prompt = """Extract the property listing data visible in this image.
Return ONLY valid JSON with these fields (use null if not visible):
{
  "address": "street address only, no city/state",
  "city": "city name",
  "state": "state abbreviation",
  "price": <integer, sale price only>,
  "beds": <float>,
  "baths": <float>,
  "sqft": <integer, interior sqft>,
  "lot_sqft": <integer or null>,
  "garage_spots": <integer or null>,
  "walkability": <string or null>
}

Rules:
- price must be integer (no $ or commas)
- If this is not a property listing card, return null
- Do NOT include city/state in address field"""

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": img_data,
                    }
                },
                {"type": "text", "text": prompt}
            ]
        }]
    )

    text = resp.content[0].text.strip()
    if text.lower() == "null":
        return None

    # Strip markdown fences
    text = re.sub(r'^```(?:json)?\n?', '', text)
    text = re.sub(r'\n?```$', '', text)

    try:
        data = json.loads(text)
        return data
    except json.JSONDecodeError:
        # Try to extract JSON object
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return None


ALLOWED_CITIES = {"berkeley", "oakland", "albany"}

def is_allowed(listing: Dict) -> bool:
    city = (listing.get("city") or "").strip().lower()
    state = (listing.get("state") or "").strip().upper()
    return city in ALLOWED_CITIES and state == "CA"


def run_visual_extractor(email_ids: List[str], email_data: Dict[str, Dict]) -> List[Dict]:
    """Run visual extraction on HTML bodies. Returns list of extracted listings."""
    from listings.utils import get_anthropic_client
    client = get_anthropic_client()

    all_listings = []

    with tempfile.TemporaryDirectory() as tmpdir:
        for eid in email_ids:
            edata = email_data.get(eid)
            if not edata or not edata.get("html_body"):
                print(f"  [Visual] No HTML for {eid}")
                continue

            subject = edata["subject"]
            print(f"  [Visual] Rendering {eid[:16]} — {subject[:55]}")

            card_paths = render_and_crop_cards(edata["html_body"], eid, tmpdir)
            if not card_paths:
                print(f"    -> 0 cards found")
                continue

            print(f"    -> {len(card_paths)} cards cropped")

            email_listings = []
            for cp in card_paths:
                try:
                    resized = resize_image(cp)
                    listing = extract_from_card_image(client, resized)
                    if listing and is_allowed(listing):
                        listing["_email_id"] = eid
                        listing["_subject"] = subject
                        email_listings.append(listing)
                except Exception as e:
                    print(f"    Card error: {e}")

            print(f"    -> {len(email_listings)} listings after geo filter")
            all_listings.extend(email_listings)

    return all_listings


# ─── Normalization ────────────────────────────────────────────────────────────

def norm_address(addr: Optional[str]) -> str:
    if not addr:
        return ""
    return re.sub(r'[^A-Z0-9 ]', '', addr.upper().strip())


def norm_price(val) -> Optional[int]:
    if val is None:
        return None
    s = str(val)
    s = re.sub(r'[^\d]', '', s.split('.')[0])
    return int(s) if s else None


def norm_int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(float(str(val).replace(',', '')))
    except Exception:
        return None


def norm_float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        return float(str(val).replace(',', ''))
    except Exception:
        return None


def parse_bs4_beds_baths(beds_baths: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """Parse 'N bed / N bath' string."""
    if not beds_baths:
        return None, None
    m = re.search(r'([\d.]+)\s*bed', beds_baths, re.IGNORECASE)
    beds = float(m.group(1)) if m else None
    m = re.search(r'([\d.]+)\s*bath', beds_baths, re.IGNORECASE)
    baths = float(m.group(1)) if m else None
    return beds, baths


def normalize_bs4(row: Dict) -> Dict:
    """Normalize a BS4/SQLite row into comparison fields."""
    beds, baths = parse_bs4_beds_baths(row.get("Beds/Baths") or row.get("beds_baths"))
    # If beds/baths stored as separate columns already
    if beds is None and row.get("beds") is not None:
        beds = norm_float(row["beds"])
    if baths is None and row.get("baths") is not None:
        baths = norm_float(row["baths"])

    # Parse address for zip
    addr = row.get("Address") or row.get("address") or ""
    zip_match = re.search(r'\b(\d{5})\b', addr)
    zip_code = zip_match.group(1) if zip_match else None

    # Normalize price (strip $ commas and annotations like "(unchanged)")
    raw_price = str(row.get("Price") or row.get("price") or "")
    raw_price = re.sub(r'\(.*?\)', '', raw_price)
    price = norm_price(raw_price)

    return {
        "address": norm_address(addr.split(',')[0] if ',' in addr else addr),
        "zip_code": zip_code,
        "price": price,
        "beds": beds,
        "baths": baths,
        "sqft": norm_int(row.get("House sqft") or row.get("house_sqft")),
        "lot_sqft": norm_int(row.get("Lot sqft") or row.get("lot_size_sqft")),
        "garage_spots": norm_int(row.get("Garage") or row.get("garage_spots")),
        "_raw": row,
    }


def normalize_visual(v: Dict) -> Dict:
    """Normalize a visual extractor result into comparison fields."""
    addr_raw = v.get("address") or ""
    return {
        "address": norm_address(addr_raw),
        "zip_code": v.get("zip_code"),
        "price": norm_price(v.get("price")),
        "beds": norm_float(v.get("beds")),
        "baths": norm_float(v.get("baths")),
        "sqft": norm_int(v.get("sqft")),
        "lot_sqft": norm_int(v.get("lot_sqft")),
        "garage_spots": norm_int(v.get("garage_spots")),
        "_raw": v,
    }


# ─── Matching ─────────────────────────────────────────────────────────────────

COMPARE_FIELDS = ["address", "zip_code", "price", "beds", "baths", "sqft", "lot_sqft", "garage_spots"]


def match_listings(bs4_norm: List[Dict], vis_norm: List[Dict]) -> Tuple[List, List, List]:
    """
    Returns (matched_pairs, bs4_only, vis_only).
    Each matched pair is (bs4_norm_dict, vis_norm_dict).
    """
    matched = []
    bs4_unmatched = list(bs4_norm)
    vis_unmatched = list(vis_norm)

    for v in list(vis_unmatched):
        best = None
        for b in bs4_unmatched:
            if v["address"] and b["address"] and v["address"] == b["address"]:
                best = b
                break
        if best is None:
            # Fallback: price + beds + baths
            for b in bs4_unmatched:
                if (v["price"] and b["price"] and v["price"] == b["price"]
                        and v["beds"] == b["beds"] and v["baths"] == b["baths"]):
                    best = b
                    break
        if best:
            matched.append((best, v))
            bs4_unmatched.remove(best)
            vis_unmatched.remove(v)

    return matched, bs4_unmatched, vis_unmatched


# ─── Report ───────────────────────────────────────────────────────────────────

def compute_coverage(listings: List[Dict], label: str) -> Dict[str, float]:
    """Coverage = % of listings where field is non-null."""
    if not listings:
        return {f: 0.0 for f in COMPARE_FIELDS}
    result = {}
    for f in COMPARE_FIELDS:
        non_null = sum(1 for l in listings if l.get(f) is not None)
        result[f] = 100.0 * non_null / len(listings)
    return result


def print_report(
    bs4_raw: List[Dict],
    vis_raw: List[Dict],
    matched: List,
    bs4_only: List,
    vis_only: List,
    email_ids: List[str],
):
    print("\n" + "=" * 70)
    print("EXTRACTOR COMPARISON REPORT — ZILLOW EMAILS (LAST INGEST RUN)")
    print("=" * 70)
    print(f"Emails processed by BS4: {len(email_ids)}")
    print(f"Listings in DB (BS4):    {len(bs4_raw)}")
    print(f"Listings found (Visual): {len(vis_raw)}")

    # ── RECALL ──
    print("\nRECALL")
    print(f"  Found by both:             {len(matched)}")
    print(f"  Found by BS4 only:         {len(bs4_only)}")
    print(f"  Found by Visual only:      {len(vis_only)}")
    print(f"  Total unique:              {len(matched) + len(bs4_only) + len(vis_only)}")

    if bs4_only:
        print("  BS4-only listings:")
        for b in bs4_only:
            raw = b.get("_raw", {})
            addr = raw.get("Address") or raw.get("address") or "?"
            price = raw.get("Price") or raw.get("price") or "?"
            print(f"    - {addr}  ${price}")

    if vis_only:
        print("  Visual-only listings:")
        for v in vis_only:
            raw = v.get("_raw", {})
            addr = raw.get("address") or "?"
            price = raw.get("price") or "?"
            print(f"    - {addr} {raw.get('city','')} CA  ${price}")

    # ── COVERAGE ──
    bs4_norm_all = [normalize_bs4(r) for r in bs4_raw]
    vis_norm_all = [normalize_visual(r) for r in vis_raw]

    bs4_cov = compute_coverage(bs4_norm_all, "BS4")
    vis_cov = compute_coverage(vis_norm_all, "Visual")

    print("\nCOVERAGE")
    print(f"{'Field':<15} | {'BS4':>10} | {'Visual':>10}")
    print("-" * 42)
    for f in COMPARE_FIELDS:
        print(f"  {f:<13} | {bs4_cov[f]:>9.0f}% | {vis_cov[f]:>9.0f}%")

    # ── ACCURACY ──
    if matched:
        agree_counts = {f: 0 for f in COMPARE_FIELDS}
        compared_counts = {f: 0 for f in COMPARE_FIELDS}
        discrepancies = []

        for b, v in matched:
            diffs = {}
            for f in COMPARE_FIELDS:
                bv = b.get(f)
                vv = v.get(f)
                if bv is None and vv is None:
                    continue
                compared_counts[f] += 1
                if bv == vv:
                    agree_counts[f] += 1
                else:
                    diffs[f] = (bv, vv)
            if diffs:
                addr = b.get("address") or v.get("address") or "unknown"
                discrepancies.append((addr, diffs))

        print("\nACCURACY (matched listings only)")
        print(f"{'Field':<15} | {'Agreement':>12}")
        print("-" * 32)
        for f in COMPARE_FIELDS:
            if compared_counts[f] == 0:
                print(f"  {f:<13} | {'n/a':>11}")
            else:
                pct = 100.0 * agree_counts[f] / compared_counts[f]
                print(f"  {f:<13} | {pct:>10.0f}%")

        if discrepancies:
            print("\nDISCREPANCY LOG")
            for addr, diffs in discrepancies:
                print(f"\n  DISCREPANCY: {addr}")
                print(f"    {'Field':<15} | {'BS4':>15} | {'Visual':>15}")
                print("    " + "-" * 50)
                for f, (bv, vv) in diffs.items():
                    print(f"    {f:<15} | {str(bv):>15} | {str(vv):>15}")
        else:
            print("\nNo discrepancies found among matched listings.")
    else:
        print("\nACCURACY: No matched listings to compare.")

    print("\n" + "=" * 70)


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    print("Step 1: Loading BS4 results from DB...")
    bs4_raw = get_bs4_listings_for_emails(ZILLOW_EMAIL_IDS)
    print(f"  {len(bs4_raw)} listings loaded from DB")
    for r in bs4_raw:
        addr = r.get("address") or r.get("Address") or "?"
        price = r.get("price") or r.get("Price") or "?"
        print(f"  BS4: {addr}  ${price}")

    print("\nStep 2: Fetching HTML email bodies...")
    email_data = fetch_html_bodies(ZILLOW_EMAIL_IDS)
    print(f"  Fetched {len(email_data)} emails")

    print("\nStep 3: Running visual extractor...")
    vis_raw = run_visual_extractor(ZILLOW_EMAIL_IDS, email_data)
    print(f"  Visual: {len(vis_raw)} listings extracted (after geo filter)")

    print("\nStep 4: Normalizing and matching...")
    bs4_norm = [normalize_bs4(r) for r in bs4_raw]
    vis_norm = [normalize_visual(r) for r in vis_raw]
    matched, bs4_only, vis_only = match_listings(bs4_norm, vis_norm)

    print_report(bs4_raw, vis_raw, matched, bs4_only, vis_only, ZILLOW_EMAIL_IDS)


if __name__ == "__main__":
    main()
