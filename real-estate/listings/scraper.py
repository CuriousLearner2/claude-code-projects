"""
DEAD CODE — Redfin actively blocks Playwright/headless browser requests (returns
403 or empty pages). This module is no longer called by the active pipeline
(refresh_db.py, daily_refresh.py). It is only referenced in sync.py, which
exposes a --skip-scrape flag for this reason.

Do not install playwright or attempt to revive this without a working bypass
(e.g. a residential proxy + stealth plugin). Kept for reference only.

Original purpose: Scrape Redfin listing pages for "About this home" details.
"""

import asyncio
import sqlite3
import time
from datetime import datetime
from typing import Optional

from playwright.async_api import async_playwright, Browser, Page

from listings.db import get_listings_needing_scrape, upsert_listing


async def scrape_about_home(url: str) -> Optional[str]:
    """Scrape 'About this home' text from Redfin page."""
    if not url:
        return None

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)

        # Create context with blocked resources for speed
        context = await browser.new_context()

        async def handle_route(route):
            if route.request.resource_type in ["image", "font", "stylesheet"]:
                await route.abort()
            else:
                await route.continue_()

        await context.route("**/*", handle_route)

        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(2)  # Rate limiting sleep

            # Try to click "Show more" button if present
            try:
                show_more_selectors = [
                    'button:has-text("Show more")',
                    'button:contains("Show more")',
                    '[data-testid="show-more-button"]',
                ]
                for selector in show_more_selectors:
                    try:
                        await page.click(selector, timeout=5000)
                        await asyncio.sleep(1)
                        break
                    except Exception:
                        continue
            except Exception:
                pass

            # Try selector fallback chain for "About this home" section
            about_text = None
            selectors = [
                '[data-rf-test-id="publicRemarks"]',
                '.listingRemarks',
                'section:has(h2:text("About this home")) p',
                'div:has(h2:text("About this home")) + div',
            ]

            for selector in selectors:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        about_text = await element.text_content()
                        if about_text and about_text.strip():
                            break
                except Exception:
                    continue

            # Fallback: try to find any substantial text block
            if not about_text:
                try:
                    all_text = await page.text_content()
                    # Extract text between "About this home" markers if present
                    if "About this home" in all_text:
                        start = all_text.find("About this home") + len("About this home")
                        # Take next 1000 chars of meaningful text
                        about_text = all_text[start:start + 1000].strip()
                except Exception:
                    pass

            await context.close()
            await browser.close()

            return about_text if about_text else None

        except Exception as e:
            print(f"Error scraping {url}: {e}")
            await context.close()
            await browser.close()
            return None


def scrape_listing(url: str) -> Optional[str]:
    """Sync wrapper for async scraping."""
    if not url:
        return None

    try:
        return asyncio.run(scrape_about_home(url))
    except Exception as e:
        print(f"Async scraping failed for {url}: {e}")
        return None


def run_scraper(conn: sqlite3.Connection) -> int:
    """Scrape all listings without content."""
    listings = get_listings_needing_scrape(conn)

    if not listings:
        print("No listings need scraping")
        return 0

    count = 0
    for listing in listings:
        url = listing.get("redfin_url")
        if not url:
            continue

        print(f"Scraping: {url}")
        about_home = scrape_listing(url)

        if about_home:
            # Update listing with scraped content
            listing_update = {
                "id": listing["id"],
                "gmail_message_id": listing["gmail_message_id"],
                "about_home": about_home,
                "scraped_at": datetime.utcnow().isoformat(),
            }
            # Preserve existing fields
            for key in listing:
                if key not in listing_update:
                    listing_update[key] = listing[key]

            upsert_listing(conn, listing_update)
            count += 1
            print(f"  Scraped successfully")
        else:
            print(f"  Failed to scrape")

    if count > 0:
        print(f"\nScraped {count} listings")

    return count
