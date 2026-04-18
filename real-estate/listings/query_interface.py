"""Natural language query interface for house listings."""

import sqlite3
from typing import List, Dict

from listings.utils import get_anthropic_client
from listings.fire_hazard import get_fire_hazard_zone, format_fire_risk


def enrich_results_with_fire_hazard(results: List[Dict]) -> List[Dict]:
    """Add fire hazard assessment to query results that have latitude/longitude."""
    enriched = []
    for row in results:
        if row.get('latitude') and row.get('longitude'):
            hazard = get_fire_hazard_zone(row['latitude'], row['longitude'])
            if hazard:
                row['fire_risk_score'] = hazard['risk_score']
                row['fire_zone'] = hazard['zone_name']
                row['fire_risk_text'] = format_fire_risk(hazard['risk_score'])
        enriched.append(row)
    return enriched


SCHEMA_PROMPT = """You have access to a SQLite database with the following schema:

listings (id, gmail_message_id, subject, received_at, address, price, beds, baths,
    house_sqft, lot_size_sqft, hoa_monthly, garage_spots, redfin_url, neighborhood,
    city, state, zip_code, latitude, longitude, geocoded_at, about_home, scraped_at,
    source, seismic_zone, seismic_risk_score, fire_zone, fire_risk_score,
    created_at, updated_at)

neighborhood_sentiment (id, neighborhood, city, state, crime_score, safety_score,
    character_score, overall_score, reddit_post_count, sentiment_summary, analyzed_at)

redis_posts (id, neighborhood, city, state, reddit_post_id, subreddit, title, body,
    score, created_utc, post_type, fetched_at)

Column semantics:
- price: listing price in USD (integer)
- beds, baths: bedroom/bathroom count (float)
- lot_size_sqft: lot size in square feet (integer)
- hoa_monthly: HOA fee per month in USD (integer)
- garage_spots: number of garage spaces (integer)
- latitude, longitude: coordinates for fire hazard lookup
- Sentiment scores: -1 (very negative) to 1 (very positive)
  - crime_score > 0.3: positive/safe regarding crime
  - safety_score > 0.3: positive regarding safety
  - character_score > 0.3: positive neighborhood character
  - overall_score > 0.3: overall positive neighborhood
FIRE HAZARD ASSESSMENT:
- Use latitude/longitude for Cal Fire FHSZ zone lookup (on-demand, no stored column)
- Fire risk scores computed from Cal Fire public data:
  - -0.5 to -0.3: Very Low Risk ✅ (outside fire hazard zones)
  - -0.3 to 0.2: Low Risk ✅
  - 0.2 to 0.5: Moderate Risk ⚠️
  - 0.5 to 0.7: High Risk 🔴
  - > 0.7: Very High Risk 🔴 (Very High Fire Hazard Severity Zone)
- SELECT l.latitude, l.longitude in queries to enable fire hazard assessment in results

Common JOINs:
- listings JOIN neighborhood_sentiment ON listings.neighborhood = neighborhood_sentiment.neighborhood
    AND listings.city = neighborhood_sentiment.city AND listings.state = neighborhood_sentiment.state

Examples of natural language → SQL:
1. "Show safe 3-bed listings under 500k"
   SELECT l.address, l.price, l.beds, l.neighborhood, n.safety_score
   FROM listings l
   LEFT JOIN neighborhood_sentiment n ON l.neighborhood = n.neighborhood
       AND l.city = n.city AND l.state = n.state
   WHERE l.beds >= 3 AND l.price < 500000 AND n.safety_score > 0.3

2. "Best neighborhoods for seniors with low fire risk"
   SELECT DISTINCT l.neighborhood, l.city, n.safety_score, n.character_score, l.latitude, l.longitude
   FROM listings l
   LEFT JOIN neighborhood_sentiment n ON l.neighborhood = n.neighborhood
       AND l.city = n.city AND l.state = n.state
   WHERE l.latitude IS NOT NULL AND l.longitude IS NOT NULL
       AND n.safety_score > 0.5 AND n.character_score > 0.5
   ORDER BY n.overall_score DESC

3. "Listings with high character scores and good price"
   SELECT l.address, l.price, l.neighborhood, n.character_score
   FROM listings l
   LEFT JOIN neighborhood_sentiment n ON l.neighborhood = n.neighborhood
       AND l.city = n.city AND l.state = n.state
   WHERE n.character_score > 0.5
   ORDER BY l.price ASC

4. "Affordable homes in low-fire-risk areas"
   SELECT l.address, l.price, l.beds, l.neighborhood, l.latitude, l.longitude
   FROM listings l
   WHERE l.price < 1000000 AND l.latitude IS NOT NULL AND l.longitude IS NOT NULL
   ORDER BY l.price ASC
   (Fire hazard will be computed from latitude/longitude in results)

5. "Safe neighborhoods with low fire hazard"
   SELECT DISTINCT l.neighborhood, l.city, n.safety_score, COUNT(l.id) as listing_count,
          AVG(l.latitude) as center_lat, AVG(l.longitude) as center_lon
   FROM listings l
   LEFT JOIN neighborhood_sentiment n ON l.neighborhood = n.neighborhood
       AND l.city = n.city AND l.state = n.state
   WHERE n.safety_score > 0.5 AND l.latitude IS NOT NULL
   GROUP BY l.neighborhood, l.city, n.safety_score
   ORDER BY n.safety_score DESC

Note: Fire hazard assessment uses latitude/longitude columns. For fire-risk aware queries,
include l.latitude and l.longitude in SELECT for on-demand fire hazard lookup on results.

Always return the most relevant columns for the user's question. Always use WHERE/JOIN
to filter appropriately based on the query intent."""


def nl_to_sql(query: str) -> str:
    """Convert natural language query to SQL."""
    client = get_anthropic_client()

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=512,
        system=SCHEMA_PROMPT,
        messages=[{
            "role": "user",
            "content": f"Convert this query to SQL: {query}\n\nRespond with ONLY the SQL query, no explanation."
        }]
    )

    sql = response.content[0].text.strip()

    # Remove markdown code blocks if present
    if sql.startswith("```"):
        sql = sql.split("```")[1]
        if sql.startswith("sql"):
            sql = sql[3:]
        sql = sql.strip()

    return sql


def execute_query(conn: sqlite3.Connection, sql: str) -> List[Dict]:
    """Execute SQL query and return results."""
    # Validate that query is SELECT
    if not sql.strip().upper().startswith("SELECT"):
        raise ValueError("Only SELECT queries are allowed")

    try:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(sql)
        results = [dict(row) for row in cursor.fetchall()]
        return results
    except sqlite3.OperationalError as e:
        raise ValueError(f"Query failed: {e}\n\nSQL: {sql}")


def format_results(results: List[Dict]) -> str:
    """Format query results as a fixed-width table."""
    if not results:
        return "No results found."

    # Get column names from first result
    columns = list(results[0].keys())

    # Calculate column widths
    col_widths = {}
    for col in columns:
        max_width = len(col)
        for row in results:
            val = str(row.get(col, ""))
            max_width = max(max_width, len(val))
        col_widths[col] = min(max_width, 50)  # Cap at 50 chars

    # Build header
    header = " | ".join(col.ljust(col_widths[col]) for col in columns)
    separator = "-+-".join("-" * col_widths[col] for col in columns)

    # Build rows
    lines = [header, separator]
    for row in results:
        line = " | ".join(
            str(row.get(col, "")).ljust(col_widths[col]) for col in columns
        )
        lines.append(line)

    return "\n".join(lines)


def run_query_interface(conn: sqlite3.Connection, single_query: str = None):
    """Run interactive query interface or execute single query."""
    if single_query:
        # Single-shot mode
        print(f"\nQuery: {single_query}\n")

        try:
            sql = nl_to_sql(single_query)
            print(f"SQL: {sql}\n")

            results = execute_query(conn, sql)
            # Enrich results with fire hazard data if coordinates are present
            results = enrich_results_with_fire_hazard(results)
            output = format_results(results)
            print(output)
        except Exception as e:
            print(f"Error: {e}")

    else:
        # Interactive REPL mode
        print("\nHouse Listings Query Interface")
        print("Type 'quit' or 'exit' to exit\n")

        while True:
            try:
                query = input("Query: ").strip()

                if query.lower() in ["quit", "exit", "q"]:
                    break

                if not query:
                    continue

                print(f"\nConverting to SQL...")
                sql = nl_to_sql(query)
                print(f"SQL: {sql}\n")

                print("Executing...")
                results = execute_query(conn, sql)
                # Enrich results with fire hazard data if coordinates are present
                results = enrich_results_with_fire_hazard(results)
                output = format_results(results)
                print(output)
                print()

            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except Exception as e:
                print(f"Error: {e}\n")
