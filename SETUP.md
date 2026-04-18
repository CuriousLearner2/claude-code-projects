# House Listings Intelligence System - Setup Guide

## Overview

This system ingests Redfin house listing emails from Gmail, scrapes full property details, geocodes addresses to neighborhoods, enriches neighborhoods with Reddit crime/safety sentiment, and exposes a natural-language command-line query interface. All data is stored in SQLite.

## Prerequisites

- Python 3.8+ (with venv already set up in `./venv`)
- Gmail API credentials (`credentials.json` already in place)
- Gmail account with Redfin listing emails
- (Optional) Reddit API credentials for sentiment analysis

## Installation

Dependencies are already installed. To verify:

```bash
source venv/bin/activate
pip list | grep -E "playwright|beautifulsoup|geopy|praw|anthropic"
```

All required packages should be listed.

## Configuration

### Step 1: Verify Gmail Setup

Gmail OAuth credentials are already configured via `credentials.json` and `token.json`.

To re-authenticate:
```bash
rm token.json
python3 gmail_search.py "test"
# Follow the browser OAuth flow
```

### Step 2: Set Anthropic API Key

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

Verify:
```bash
python3 -c "from listings.utils import get_anthropic_client; c = get_anthropic_client(); print('✓ Connected')"
```

### Step 3: (Optional) Set Up Reddit Credentials

For neighborhood sentiment analysis via Reddit, set up Reddit API credentials:

```bash
python3 setup_reddit.py
```

This wizard will:
1. Guide you through creating a Reddit app at https://reddit.com/prefs/apps
2. Test your credentials
3. Optionally add environment variables to `~/.zshrc`

Required environment variables:
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USERNAME`

Verify:
```bash
python3 -c "from listings.reddit_enrichment import get_reddit_client; r = get_reddit_client(); print('✓ Connected')"
```

## Usage

### Full Sync Pipeline

Ingest emails → Scrape Redfin pages → Geocode addresses → Analyze Reddit sentiment:

```bash
python3 sync.py
```

Options:
- `--skip-scrape`: Skip Redfin page scraping
- `--skip-reddit`: Skip Reddit sentiment analysis
- `--verbose`: Print detailed output

Examples:
```bash
python3 sync.py --skip-reddit  # Skip Reddit, just ingest and geocode
python3 sync.py --skip-scrape --skip-reddit  # Just ingest
```

### Query Interface

Natural language search interface:

```bash
# Interactive REPL mode
python3 query.py

# Single-shot query
python3 query.py "Show me safe 3-bed listings under 500k"
```

Examples:
```
> Show safe neighborhoods
> List 2-bed homes with high character scores
> Compare crime sentiment across neighborhoods
> Listings with good price and high safety score in downtown
```

## Database

SQLite database location: `listings.db`

### Schema

**listings**: House listing data from emails
- `id` (Gmail message ID)
- `address`, `price`, `beds`, `baths`
- `neighborhood`, `city`, `state`, `latitude`, `longitude`
- `about_home` (scraped text from Redfin)
- `redfin_url` (property link)
- Timestamps: `received_at`, `geocoded_at`, `scraped_at`

**neighborhood_sentiment**: Reddit-based neighborhood analysis
- `neighborhood`, `city`, `state`
- Scores (-1 to 1): `crime_score`, `safety_score`, `character_score`, `overall_score`
- `reddit_post_count`, `sentiment_summary`
- `analyzed_at` (timestamp)

**reddit_posts**: Individual Reddit posts for neighborhoods
- Post content: `title`, `body`, `score`
- `subreddit`, `post_type` (discussion/link)
- `created_utc`, `fetched_at`

**geocode_cache**: Cached Nominatim geocoding results for speed
- `address_key` → `(neighborhood, city, state, latitude, longitude)`

**sync_state**: Pipeline state tracking
- `last_email_timestamp`: For incremental email sync

## Troubleshooting

### Gmail: "credentials.json not found"
```bash
# Recreate credentials.json via Gmail API console
# https://console.cloud.google.com/
# Then re-run sync.py
```

### Geocoding: Nominatim rate limiting
- Geocoder respects Nominatim's rate limits (1+ second between requests)
- Cache is persistent in database — subsequent runs are faster
- If rate-limited, geocoding picks up where it left off

### Scraping: Timeout or "Failed to scrape"
- Playwright requires Chromium (installed via `playwright install chromium`)
- Network issues may cause timeouts; re-run sync.py to retry
- Some Redfin pages may not have "About this home" sections

### Reddit: "Credentials not configured"
```bash
# Run setup wizard
python3 setup_reddit.py

# Or set env vars manually
export REDDIT_CLIENT_ID="..."
export REDDIT_CLIENT_SECRET="..."
export REDDIT_USERNAME="..."
```

### Query: "Query failed: OperationalError"
- SQL translation sometimes needs rephrasing
- Try alternative phrasing:
  - "safe neighborhoods" → "Show neighborhoods with high safety scores"
  - "expensive listings" → "List homes over 750k"

## Performance Notes

- **First sync**: Will ingest all emails, scrape pages (slow), geocode addresses
  - Estimate: 30 minutes for 50 listings (Redfin scraping is rate-limited)
- **Incremental syncs**: Only new emails are processed
  - Estimate: 2-5 minutes for 5-10 new listings
- **Reddit enrichment**: Fetches and analyzes 100 posts per neighborhood
  - Estimate: 2-3 minutes per neighborhood

## Data Privacy

- All data stored locally in `listings.db`
- Gmail API: read-only (no emails modified)
- Reddit: public posts only, no credentials stored
- Anthropic: NL queries sent to Claude (not user data)

## Next Steps

1. Run `python3 sync.py --skip-reddit` to ingest and geocode
2. Try `python3 query.py "Show listings in my city"`
3. Once satisfied with data, run `python3 setup_reddit.py` and then `python3 sync.py`

## Architecture

```
sync.py → listings/gmail_ingest.py → Gmail API
        → listings/scraper.py → Playwright (Redfin pages)
        → listings/geocoder.py → Nominatim (OpenStreetMap)
        → listings/reddit_enrichment.py → PRAW (Reddit) → Claude API

query.py → listings/query_interface.py → Claude API (NL to SQL)
         → listings/db.py → SQLite
```

All data flows through `listings/db.py` for SQLite access.
