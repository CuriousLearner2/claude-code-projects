"""Berkeley Parents Network neighborhood sentiment scraper."""

import sqlite3
import time
import re
import json
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from urllib.parse import urljoin
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from listings.db import upsert_neighborhood_sentiment
from listings.utils import get_anthropic_client

# Directory to store scraped posts by neighborhood
POSTS_DIR = Path(__file__).parent.parent / "bpn_posts"
POSTS_DIR.mkdir(exist_ok=True)


BPN_INDEXES = {
    "Berkeley": "https://www.berkeleyparentsnetwork.org/advice/berkeley-neighborhoods-0",
    "Oakland": "https://www.berkeleyparentsnetwork.org/advice/oakland-neighborhoods-0",
}
BASE_URL = "https://www.berkeleyparentsnetwork.org"

# Rate limiting to be polite to the server
REQUEST_DELAY = 1.0


def parse_bpn_date(text: str) -> Optional[datetime]:
    """Parse BPN date strings in various formats."""
    text = text.strip()
    # BPN uses "Sept" sometimes instead of "Sep"
    text = re.sub(r'\bSept\b', 'Sep', text)

    # Try common date formats
    for fmt in ('%B %d, %Y', '%b %d, %Y', '%B %Y', '%b %Y'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def discover_neighborhoods() -> List[Dict]:
    """Scrape index pages and discover neighborhoods."""
    neighborhoods = []

    for city, index_url in BPN_INDEXES.items():
        try:
            print(f"  Discovering {city} neighborhoods...")
            response = requests.get(index_url, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")

            # Find main content area
            main = soup.find("main") or soup.find("div", id="main-content")
            if not main:
                main = soup

            # Find all links that start with "Living in"
            for link in main.find_all("a", href=True):
                text = link.get_text(strip=True)

                # Look for neighborhood links with "Living in" prefix
                if text.startswith("Living in "):
                    name = text[len("Living in "):].strip()
                    href = link.get("href", "")

                    # Only include links that look like neighborhood pages
                    if href.startswith("/recommend/") or href.startswith("/advice/"):
                        url = urljoin(BASE_URL, href)
                        neighborhoods.append({
                            "name": name,
                            "city": city,
                            "url": url
                        })

            time.sleep(REQUEST_DELAY)

        except Exception as e:
            print(f"  Error discovering {city} neighborhoods: {e}")

    print(f"Discovered {len(neighborhoods)} neighborhoods")
    return neighborhoods


def scrape_full_discussion(discussion_url: str, cutoff: datetime) -> Optional[Dict]:
    """Scrape a full discussion thread including all replies.

    Returns:
        Dict with discussion details or None if failed/too old
    """
    try:
        response = requests.get(discussion_url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        # Extract title
        title_elem = soup.find("h1")
        title = title_elem.get_text(strip=True) if title_elem else "Untitled"

        # Extract date - look for submitted date in the header
        date_elem = soup.find(class_=lambda x: x and "submitted" in str(x).lower())
        date_text = None
        parsed_date = None
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            parsed_date = parse_bpn_date(date_text)

        # Fallback: search for date pattern in page
        if not parsed_date:
            page_text = soup.get_text()
            date_pattern = r'\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},?\s*\d{4}'
            date_match = re.search(date_pattern, page_text)
            if date_match:
                date_text = date_match.group(0)
                parsed_date = parse_bpn_date(date_text)

        # Skip if too old
        if not parsed_date or parsed_date < cutoff:
            return None

        # Extract all comments (original post + replies)
        all_comments = []

        # Get original post body - look for field with body text
        body_elem = soup.find(class_=lambda x: x and "field--name-body" in str(x))
        if body_elem:
            for p in body_elem.find_all("p"):
                text = p.get_text(strip=True)
                if text and len(text) > 10:
                    all_comments.append(text)

        # Get all comment bodies - look for comment-body fields
        comment_bodies = soup.find_all(class_=lambda x: x and "field--name-comment-body" in str(x))
        for comment_body in comment_bodies:
            for p in comment_body.find_all("p"):
                text = p.get_text(strip=True)
                if text and len(text) > 10:
                    all_comments.append(text)

        time.sleep(REQUEST_DELAY)

        if all_comments:
            return {
                "date": date_text or "Unknown",
                "date_parsed": parsed_date.isoformat() if parsed_date else None,
                "title": title,
                "comments": all_comments,
                "url": discussion_url
            }

    except Exception as e:
        pass

    return None


def scrape_neighborhood_page(url: str) -> tuple[List[str], int, List[Dict]]:
    """Scrape one neighborhood page and return text snippets, filtered count, and full posts.

    Returns:
        Tuple of (snippets list, count of skipped posts, full posts list with metadata)
    """
    snippets = []
    posts = []
    skipped_count = 0
    cutoff = datetime(2020, 1, 1)  # Only include posts from Jan 1, 2020 onwards

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "html.parser")

        # Find the main content container (try multiple selectors for page structure variations)
        main_node = (
            soup.find("div", class_="view-content") or
            soup.find("article") or
            soup.find("div", class_="node") or
            soup
        )

        # Find all question links within the main node
        question_links = main_node.find_all("a", href=lambda x: x and "/questions/" in str(x))

        for link in question_links:
            href = link.get("href", "")
            # Only process actual question links (avoid external links)
            if href.startswith("/questions/"):
                question_url = urljoin(BASE_URL, href)

                # Scrape the full discussion
                discussion = scrape_full_discussion(question_url, cutoff)

                if discussion:
                    # Create snippet for Claude analysis
                    snippet = ""
                    if discussion["title"]:
                        snippet += f"TITLE: {discussion['title']}\n"
                    for comment in discussion["comments"][:5]:  # Limit comments per node
                        snippet += f"COMMENT: {comment}\n"

                    if snippet:
                        snippets.append(snippet)
                        posts.append(discussion)
                else:
                    skipped_count += 1

        time.sleep(REQUEST_DELAY)

    except Exception as e:
        print(f"    Error scraping page: {e}")

    return snippets[:150], skipped_count, posts  # Cap at 150 snippets to avoid token overload


def analyze_bpn_sentiment(
    neighborhood: str, city: str, snippets: List[str]
) -> Optional[Dict]:
    """Analyze sentiment from BPN posts using Claude."""
    if not snippets:
        return None

    client = get_anthropic_client()

    # Concatenate snippets up to reasonable token limit
    concatenated = "\n".join(snippets)[:6000]

    prompt = f"""Analyze these parent discussions about {neighborhood}, {city} from Berkeley Parents Network.
Score these dimensions from -1.0 (very negative) to +1.0 (very positive):
- crime_score: perceptions of crime/safety incidents
- safety_score: overall feeling of safety for families/children
- character_score: neighborhood charm, walkability, community feel, schools
- overall_score: overall desirability as a place to live

Return ONLY valid JSON with these four keys plus "sentiment_summary" (2-3 sentence summary).
All scores must be floats between -1.0 and 1.0.

Discussions:
{concatenated}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()

        # Extract JSON from response
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group(0))

            # Ensure all required fields exist and are floats
            result = {
                "neighborhood": neighborhood,
                "city": city,
                "state": "CA",  # BPN is CA-focused
                "crime_score": float(data.get("crime_score", 0)),
                "safety_score": float(data.get("safety_score", 0)),
                "character_score": float(data.get("character_score", 0)),
                "overall_score": float(data.get("overall_score", 0)),
                "reddit_post_count": len(snippets),
                "sentiment_summary": str(data.get("sentiment_summary", ""))
            }
            return result

    except Exception as e:
        print(f"    Error analyzing sentiment: {e}")

    return None


def run_bpn_enrichment(conn: sqlite3.Connection, force: bool = False, since_timestamp: str = None) -> int:
    """Orchestrate BPN scraping and sentiment analysis.

    Args:
        conn: Database connection
        force: Force re-analysis (unused, for compatibility)
        since_timestamp: Only analyze neighborhoods in listings since this timestamp
    """
    print("\n🏘️  Berkeley Parents Network Enrichment\n")

    # First, find neighborhoods that need analysis (in new listings, not yet analyzed)
    cursor = conn.cursor()

    # Query neighborhoods from new listings that haven't been analyzed
    if since_timestamp:
        cursor.execute("""
            SELECT DISTINCT neighborhood FROM listings
            WHERE neighborhood IS NOT NULL
            AND received_at > ?
            AND neighborhood NOT IN (
                SELECT neighborhood FROM neighborhood_sentiment
            )
            ORDER BY neighborhood
        """, (since_timestamp,))
    else:
        cursor.execute("""
            SELECT DISTINCT neighborhood FROM listings
            WHERE neighborhood IS NOT NULL
            AND neighborhood NOT IN (
                SELECT neighborhood FROM neighborhood_sentiment
            )
            ORDER BY neighborhood
        """)

    neighborhoods_to_analyze = set(row[0] for row in cursor.fetchall())

    if not neighborhoods_to_analyze:
        print("✓ All neighborhoods already analyzed")
        return 0

    print(f"Analyzing {len(neighborhoods_to_analyze)} neighborhoods\n")

    # Discover all neighborhoods to map to URLs
    all_neighborhoods = discover_neighborhoods()
    if not all_neighborhoods:
        print("No neighborhoods discovered")
        return 0

    # Filter to only neighborhoods we need to analyze
    neighborhoods = [n for n in all_neighborhoods if n["name"] in neighborhoods_to_analyze]
    count = 0

    for neigh_info in neighborhoods:
        name = neigh_info["name"]
        city = neigh_info["city"]
        url = neigh_info["url"]

        print(f"Processing {city}: {name}")

        try:
            # Scrape the neighborhood page
            snippets, skipped_count, posts = scrape_neighborhood_page(url)
            if not snippets:
                print(f"  No content found")
                continue

            total_found = len(snippets) + skipped_count
            print(f"  Found {len(snippets)} recent snippets ({skipped_count} skipped: too old or undated)")

            # Save posts to JSON file by neighborhood
            posts_file = POSTS_DIR / f"{city}_{name.replace('/', '_').replace(' ', '_')}.json"
            with open(posts_file, 'w') as f:
                json.dump({
                    "neighborhood": name,
                    "city": city,
                    "scraped_at": datetime.now().isoformat(),
                    "posts": posts
                }, f, indent=2)
            print(f"    ✓ Saved {len(posts)} posts to {posts_file.name}")

            # Analyze sentiment
            sentiment = analyze_bpn_sentiment(name, city, snippets)
            if not sentiment:
                print(f"  Sentiment analysis failed")
                continue

            # Upsert into database
            upsert_neighborhood_sentiment(conn, sentiment)
            count += 1
            print(f"  ✓ Sentiment: {sentiment['overall_score']:.2f} "
                  f"(safety: {sentiment['safety_score']:.2f})")

        except Exception as e:
            print(f"  Error processing neighborhood: {e}")

    print(f"\n✓ BPN enrichment complete: {count} neighborhoods analyzed")
    return count
