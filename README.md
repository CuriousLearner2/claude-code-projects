# 🏠 House Listings Intelligence System

A comprehensive system for ingesting Redfin house listing emails from Gmail, scraping property details, enriching with neighborhood sentiment from Reddit, and querying with natural language.

## Features

✨ **Email Ingestion** — Automatically fetch Redfin listing emails from Gmail with incremental sync

🔍 **Web Scraping** — Extract "About this home" descriptions from Redfin pages using Playwright

🗺️ **Geocoding** — Convert addresses to coordinates and extract neighborhood names using Nominatim

💬 **Reddit Enrichment** — Fetch Reddit posts about neighborhoods and analyze sentiment with Claude

🔮 **Natural Language Queries** — Search listings with conversational queries ("Show me safe neighborhoods")

💾 **Local SQLite** — All data stored locally with no external dependencies

## Quick Start

### 1. Verify Setup

```bash
python3 verify.py
```

### 2. Ingest and Geocode

```bash
python3 sync.py --skip-reddit
```

This will:
- Fetch new Redfin listing emails from Gmail
- Scrape property details from Redfin pages
- Geocode addresses and extract neighborhoods

### 3. Query Your Data

```bash
python3 query.py "Show me safe 3-bed listings under 500k"
```

Or use interactive mode:
```bash
python3 query.py
```

## Installation & Setup

See [SETUP.md](SETUP.md) for detailed setup instructions including:
- Gmail API configuration
- Anthropic API key
- Optional Reddit credentials
- Troubleshooting

## System Architecture

```
┌─────────────────────────────────────────┐
│         Email & Web Ingestion           │
├─────────────────────────────────────────┤
│  sync.py                                │
│  ├─ gmail_ingest.py    (Gmail API)      │
│  ├─ scraper.py         (Playwright)     │
│  ├─ geocoder.py        (Nominatim)      │
│  └─ reddit_enrichment.py (PRAW/Claude)  │
├─────────────────────────────────────────┤
│         SQLite Database                 │
│  (listings.db)                          │
└─────────────────────────────────────────┘
            ↓
┌─────────────────────────────────────────┐
│     Natural Language Query Interface    │
├─────────────────────────────────────────┤
│  query.py                               │
│  └─ query_interface.py (Claude NL→SQL)  │
└─────────────────────────────────────────┘
```

## Usage Examples

### Sync Pipeline

```bash
# Full pipeline (ingest, scrape, geocode, Reddit analysis)
python3 sync.py

# Skip Reddit for faster sync
python3 sync.py --skip-reddit

# Skip scraping (faster, but no "About this home")
python3 sync.py --skip-scrape

# Verbose output
python3 sync.py --verbose
```

### Query Interface

```bash
# Interactive REPL
python3 query.py

# Single query
python3 query.py "List 2-bed homes under 400k in safe neighborhoods"

# Examples:
python3 query.py "Show listings with high character scores"
python3 query.py "Compare safety across neighborhoods"
python3 query.py "3-bed, 2-bath in walkable area"
python3 query.py "Neighborhoods with low crime sentiment"
```

### Setup Reddit Credentials

```bash
python3 setup_reddit.py
```

## Database Schema

### listings
House listing data from email + web scraping + geocoding

```
id (Gmail message ID, primary key)
subject, received_at
address, city, state
price, beds, baths
lot_size_sqft, hoa_monthly, garage_spots
redfin_url
neighborhood, latitude, longitude
about_home (scraped from Redfin)
geocoded_at, scraped_at
created_at, updated_at
```

### neighborhood_sentiment
Neighborhood analysis from Reddit

```
neighborhood, city, state (unique constraint)
crime_score, safety_score, character_score, overall_score (-1 to 1)
reddit_post_count, sentiment_summary
analyzed_at
```

### reddit_posts
Individual Reddit posts for enrichment

```
neighborhood, city, state
reddit_post_id (unique)
subreddit, title, body, score
created_utc, post_type (discussion/link)
fetched_at
```

### geocode_cache
Cached Nominatim results for performance

```
address_key (primary key)
neighborhood, city, state, latitude, longitude
cached_at
```

### sync_state
Pipeline state for incremental operations

```
key (primary key)
value (e.g., last_email_timestamp)
```

## File Structure

```
/Users/gautambiswas/Claude Code/
├── listings/                    # Core package
│   ├── __init__.py
│   ├── db.py                   # SQLite operations
│   ├── utils.py                # Shared utilities
│   ├── gmail_ingest.py         # Email parsing
│   ├── scraper.py              # Redfin scraping
│   ├── geocoder.py             # Address geocoding
│   ├── reddit_enrichment.py    # Sentiment analysis
│   └── query_interface.py      # NL query interface
│
├── sync.py                      # Sync entry point
├── query.py                     # Query entry point
├── setup_reddit.py              # Reddit credential wizard
├── verify.py                    # Verification script
│
├── listings.db                  # SQLite database
├── credentials.json             # Gmail API (from setup)
├── token.json                   # Gmail auth token
├── SETUP.md                     # Setup instructions
└── README.md                    # This file
```

## Performance

- **First sync**: 30 min for 50 listings (includes Redfin scraping)
- **Incremental sync**: 2-5 min for 5-10 new listings
- **Reddit enrichment**: 2-3 min per neighborhood
- **Caching**: Geocoding results cached; subsequent syncs are faster

## Environment Variables

**Required:**
- `ANTHROPIC_API_KEY` — Claude API key

**Optional (for Reddit):**
- `REDDIT_CLIENT_ID`
- `REDDIT_CLIENT_SECRET`
- `REDDIT_USERNAME`
- `REDDIT_PASSWORD` (if not using OAuth)

## Troubleshooting

- **"credentials.json not found"** → Set up Gmail API (see SETUP.md)
- **"ANTHROPIC_API_KEY not set"** → `export ANTHROPIC_API_KEY="sk-..."`
- **Scraping timeout** → Network issue; re-run sync.py to retry
- **Rate limiting** → Geocoder auto-respects Nominatim limits
- **Query translation fails** → Rephrase the query

See [SETUP.md](SETUP.md) for more troubleshooting.

## Key Technologies

- **Gmail API** — Fetch Redfin listing emails
- **Playwright** — Headless browser scraping
- **Nominatim/geopy** — Address geocoding with caching
- **PRAW** — Reddit API client
- **Claude Haiku** — NL→SQL translation, sentiment analysis
- **SQLite** — Local persistent storage with WAL mode

## Data Privacy

- All data stored locally in `listings.db`
- Gmail API access is read-only
- Reddit searches are public posts only
- No credentials or PII logged

## Limitations

- Redfin scraping is rate-limited for politeness (2s between requests)
- Nominatim geocoding is rate-limited (1.1s between requests)
- Reddit sentiment analysis limited to 100 posts per neighborhood
- NL queries require rephrasing if Claude can't translate them to SQL

## Future Enhancements

- Multi-user support with separate databases
- Price trend tracking over time
- Commute time analysis (Google Maps API)
- Virtual tour integration
- Email notifications for new listings
- Web UI instead of CLI

## License

Personal project. Use at your own risk.

## Support

- Check [SETUP.md](SETUP.md) for setup and troubleshooting
- Run `python3 verify.py` to diagnose issues
- Review database schema above for query help
