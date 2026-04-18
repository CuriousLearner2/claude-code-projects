"""SQLite database operations for house listings."""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple


def _row_to_dict(cursor, row) -> Dict:
    """Convert a row (tuple or Row object) to a dict."""
    if hasattr(row, 'keys'):
        return dict(row)
    else:
        columns = [d[0] for d in cursor.description]
        return dict(zip(columns, row))


def init_db(db_path: str) -> sqlite3.Connection:
    """Initialize database with schema and return connection."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Disable WAL mode (it causes issues with transaction isolation)
    # Use default ROLLBACK journal mode instead
    conn.execute("PRAGMA journal_mode=DELETE;")

    # Create tables
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS sync_state (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS listings (
        id TEXT PRIMARY KEY,
        gmail_message_id TEXT NOT NULL,
        subject TEXT,
        received_at TEXT NOT NULL,
        address TEXT,
        price INTEGER,
        beds REAL,
        baths REAL,
        house_sqft INTEGER,
        lot_size_sqft INTEGER,
        hoa_monthly INTEGER,
        garage_spots INTEGER,
        redfin_url TEXT,
        neighborhood TEXT,
        city TEXT,
        state TEXT,
        latitude REAL,
        longitude REAL,
        geocoded_at TEXT,
        about_home TEXT,
        scraped_at TEXT,
        source TEXT DEFAULT 'Redfin',
        zip_code TEXT,
        seismic_zone TEXT,
        seismic_risk_score REAL,
        fire_zone TEXT,
        fire_risk_score REAL,
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS geocode_cache (
        address_key TEXT PRIMARY KEY,
        neighborhood TEXT,
        city TEXT,
        state TEXT,
        zip_code TEXT,
        latitude REAL,
        longitude REAL,
        cached_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS neighborhood_sentiment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        neighborhood TEXT NOT NULL,
        city TEXT NOT NULL,
        state TEXT NOT NULL,
        crime_score REAL,
        safety_score REAL,
        character_score REAL,
        overall_score REAL,
        reddit_post_count INTEGER,
        sentiment_summary TEXT,
        analyzed_at TEXT NOT NULL,
        UNIQUE(neighborhood, city, state)
    );

    CREATE TABLE IF NOT EXISTS reddit_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        neighborhood TEXT NOT NULL,
        city TEXT NOT NULL,
        state TEXT NOT NULL,
        reddit_post_id TEXT NOT NULL,
        subreddit TEXT,
        title TEXT,
        body TEXT,
        score INTEGER,
        created_utc INTEGER,
        post_type TEXT,
        fetched_at TEXT NOT NULL,
        UNIQUE(reddit_post_id, neighborhood)
    );

    CREATE TABLE IF NOT EXISTS matched_properties (
        id TEXT PRIMARY KEY,
        address TEXT NOT NULL,
        price INTEGER NOT NULL,
        beds REAL NOT NULL,
        baths REAL NOT NULL,
        city TEXT,
        state TEXT,
        neighborhood TEXT,
        description TEXT,
        listing_url TEXT,
        latitude REAL,
        longitude REAL,
        source_email_id TEXT,
        extracted_from TEXT,
        matched_at TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_matched_city ON matched_properties(city);
    CREATE INDEX IF NOT EXISTS idx_matched_price ON matched_properties(price);
    CREATE INDEX IF NOT EXISTS idx_matched_neighborhood ON matched_properties(neighborhood);
    """)

    # Seed sync_state if empty
    cursor = conn.execute("SELECT COUNT(*) FROM sync_state")
    if cursor.fetchone()[0] == 0:
        conn.execute(
            "INSERT INTO sync_state (key, value) VALUES (?, ?)",
            ("last_email_timestamp", "0")
        )
        conn.commit()

    return conn


def get_sync_state(conn: sqlite3.Connection, key: str) -> Optional[str]:
    """Get sync state value."""
    cursor = conn.execute(
        "SELECT value FROM sync_state WHERE key = ?",
        (key,)
    )
    row = cursor.fetchone()
    return row[0] if row else None


def set_sync_state(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Set sync state value."""
    conn.execute(
        "INSERT OR REPLACE INTO sync_state (key, value) VALUES (?, ?)",
        (key, value)
    )
    conn.commit()


def upsert_listing(conn: sqlite3.Connection, listing: Dict) -> None:
    """Insert or replace listing."""
    cursor = conn.execute("""
        INSERT OR REPLACE INTO listings (
            id, gmail_message_id, subject, received_at, address, price, beds,
            baths, house_sqft, lot_size_sqft, hoa_monthly, garage_spots,
            redfin_url, neighborhood, city, state, zip_code, latitude, longitude,
            geocoded_at, about_home, scraped_at, source, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        listing.get("id"),
        listing.get("gmail_message_id"),
        listing.get("subject"),
        listing.get("received_at"),
        listing.get("address"),
        listing.get("price"),
        listing.get("beds"),
        listing.get("baths"),
        listing.get("house_sqft"),
        listing.get("lot_size_sqft"),
        listing.get("hoa_monthly"),
        listing.get("garage_spots"),
        listing.get("redfin_url"),
        listing.get("neighborhood"),
        listing.get("city"),
        listing.get("state"),
        listing.get("zip_code"),
        listing.get("latitude"),
        listing.get("longitude"),
        listing.get("geocoded_at"),
        listing.get("about_home"),
        listing.get("scraped_at"),
        listing.get("source", "Redfin"),
        datetime.utcnow().isoformat()
    ))
    conn.commit()


def get_listings_needing_scrape(conn: sqlite3.Connection) -> List[Dict]:
    """Get listings without scraped content."""
    cursor = conn.execute(
        "SELECT * FROM listings WHERE scraped_at IS NULL AND redfin_url IS NOT NULL"
    )
    return [dict(row) for row in cursor.fetchall()]


def get_listings_needing_geocode(conn: sqlite3.Connection) -> List[Dict]:
    """Get listings without geocoding."""
    cursor = conn.execute(
        "SELECT * FROM listings WHERE geocoded_at IS NULL AND address IS NOT NULL"
    )
    return [_row_to_dict(cursor, row) for row in cursor.fetchall()]


def get_geocode_cache(conn: sqlite3.Connection, address_key: str) -> Optional[Dict]:
    """Get cached geocoding result."""
    cursor = conn.execute(
        "SELECT neighborhood, city, state, zip_code, latitude, longitude FROM geocode_cache WHERE address_key = ?",
        (address_key,)
    )
    row = cursor.fetchone()
    if row:
        # Handle both tuple and Row objects
        if hasattr(row, 'keys'):
            return dict(row)
        else:
            return {
                'neighborhood': row[0],
                'city': row[1],
                'state': row[2],
                'zip_code': row[3],
                'latitude': row[4],
                'longitude': row[5],
            }
    return None


def set_geocode_cache(conn: sqlite3.Connection, address_key: str, result: Dict) -> None:
    """Cache geocoding result."""
    conn.execute("""
        INSERT OR REPLACE INTO geocode_cache (
            address_key, neighborhood, city, state, zip_code, latitude, longitude, cached_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        address_key,
        result.get("neighborhood"),
        result.get("city"),
        result.get("state"),
        result.get("zip_code"),
        result.get("latitude"),
        result.get("longitude"),
        datetime.utcnow().isoformat()
    ))
    conn.commit()


def upsert_neighborhood_sentiment(conn: sqlite3.Connection, data: Dict) -> None:
    """Insert or replace neighborhood sentiment."""
    conn.execute("""
        INSERT OR REPLACE INTO neighborhood_sentiment (
            neighborhood, city, state, crime_score, safety_score,
            character_score, overall_score, reddit_post_count,
            sentiment_summary, analyzed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        data.get("neighborhood"),
        data.get("city"),
        data.get("state"),
        data.get("crime_score"),
        data.get("safety_score"),
        data.get("character_score"),
        data.get("overall_score"),
        data.get("reddit_post_count"),
        data.get("sentiment_summary"),
        datetime.utcnow().isoformat()
    ))
    conn.commit()


def delete_reddit_posts_for_neighborhood(
    conn: sqlite3.Connection, neighborhood: str, city: str, state: str
) -> None:
    """Delete all Reddit posts for a neighborhood."""
    conn.execute(
        "DELETE FROM reddit_posts WHERE neighborhood = ? AND city = ? AND state = ?",
        (neighborhood, city, state)
    )
    conn.commit()


def insert_reddit_post(conn: sqlite3.Connection, post: Dict) -> None:
    """Insert Reddit post."""
    conn.execute("""
        INSERT OR IGNORE INTO reddit_posts (
            neighborhood, city, state, reddit_post_id, subreddit,
            title, body, score, created_utc, post_type, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        post.get("neighborhood"),
        post.get("city"),
        post.get("state"),
        post.get("reddit_post_id"),
        post.get("subreddit"),
        post.get("title"),
        post.get("body"),
        post.get("score"),
        post.get("created_utc"),
        post.get("post_type"),
        datetime.utcnow().isoformat()
    ))
    conn.commit()


def get_distinct_neighborhoods(conn: sqlite3.Connection) -> List[Tuple[str, str, str]]:
    """Get distinct neighborhoods that need sentiment analysis."""
    cursor = conn.execute("""
        SELECT DISTINCT neighborhood, city, state FROM listings
        WHERE neighborhood IS NOT NULL AND city IS NOT NULL AND state IS NOT NULL
        ORDER BY neighborhood, city, state
    """)
    return cursor.fetchall()


def get_listing_by_gmail_id(conn: sqlite3.Connection, gmail_id: str) -> Optional[Dict]:
    """Get listing by Gmail message ID."""
    cursor = conn.execute(
        "SELECT * FROM listings WHERE gmail_message_id = ?",
        (gmail_id,)
    )
    row = cursor.fetchone()
    return _row_to_dict(cursor, row) if row else None


def get_all_listings(conn: sqlite3.Connection) -> List[Dict]:
    """Get all listings."""
    cursor = conn.execute("SELECT * FROM listings ORDER BY received_at DESC")
    return [dict(row) for row in cursor.fetchall()]


def property_exists(conn: sqlite3.Connection, address: str, price: Optional[int], beds: Optional[float]) -> bool:
    """Check if a property with same address, price, and beds already exists."""
    cursor = conn.execute(
        "SELECT id FROM listings WHERE address = ? AND price = ? AND beds = ? LIMIT 1",
        (address, price, beds)
    )
    return cursor.fetchone() is not None


def get_listing_by_property(conn: sqlite3.Connection, address: str, price: Optional[int], beds: Optional[float]) -> Optional[Dict]:
    """Get existing listing by address, price, and beds (for dedup/update)."""
    cursor = conn.execute(
        "SELECT id FROM listings WHERE address = ? AND price = ? AND beds = ? LIMIT 1",
        (address, price, beds)
    )
    row = cursor.fetchone()
    return {"id": row[0]} if row else None


def get_listing_by_address(conn: sqlite3.Connection, address: str) -> Optional[Dict]:
    """Get existing listing by address only (for cross-source dedup)."""
    cursor = conn.execute(
        "SELECT id, gmail_message_id, received_at, source, price, lot_size_sqft, hoa_monthly, garage_spots FROM listings WHERE address = ? ORDER BY received_at DESC LIMIT 1",
        (address,)
    )
    row = cursor.fetchone()
    if row:
        return {
            "id": row[0], "gmail_message_id": row[1], "received_at": row[2], "source": row[3],
            "price": row[4], "lot_size_sqft": row[5], "hoa_monthly": row[6], "garage_spots": row[7]
        }
    return None


def insert_matched_property(conn: sqlite3.Connection, prop: Dict) -> None:
    """Insert a matched property with complete data. Deduplicates by address."""
    # Check if property with this address already exists
    existing = conn.execute(
        "SELECT id FROM matched_properties WHERE address = ?",
        (prop.get("address"),)
    ).fetchone()

    if existing:
        # Update existing property with new data if provided
        updates = []
        values = []
        for field in ['price', 'beds', 'baths', 'city', 'state', 'neighborhood',
                      'description', 'listing_url', 'latitude', 'longitude']:
            if prop.get(field) is not None:
                updates.append(f"{field} = ?")
                values.append(prop.get(field))

        if updates:
            values.append(existing[0])
            conn.execute(f"UPDATE matched_properties SET {', '.join(updates)} WHERE id = ?", values)
            conn.commit()
    else:
        # Insert new property
        conn.execute("""
            INSERT INTO matched_properties (
                id, address, price, beds, baths, city, state, neighborhood,
                description, listing_url, latitude, longitude,
                source_email_id, extracted_from, matched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            prop.get("id"),
            prop.get("address"),
            prop.get("price"),
            prop.get("beds"),
            prop.get("baths"),
            prop.get("city"),
            prop.get("state"),
            prop.get("neighborhood"),
            prop.get("description"),
            prop.get("listing_url"),
            prop.get("latitude"),
            prop.get("longitude"),
            prop.get("source_email_id"),
            prop.get("extracted_from"),
            datetime.utcnow().isoformat()
        ))
        conn.commit()
