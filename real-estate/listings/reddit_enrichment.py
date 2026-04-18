"""Fetch Reddit posts and analyze neighborhood sentiment."""

import json
import os
import sqlite3
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import praw

from listings.db import (
    get_distinct_neighborhoods,
    delete_reddit_posts_for_neighborhood,
    insert_reddit_post,
    upsert_neighborhood_sentiment,
)
from listings.utils import get_anthropic_client


# Hardcoded metro/state subreddit mapping
METRO_TO_SUBREDDIT = {
    "Los Angeles": "r/losangeles",
    "San Francisco": "r/sanfrancisco",
    "New York": "r/nyc",
    "Chicago": "r/chicago",
    "Houston": "r/houston",
    "Phoenix": "r/phoenix",
    "Philadelphia": "r/philadelphia",
    "San Antonio": "r/sanantonio",
    "San Diego": "r/sandiego",
    "Dallas": "r/dallas",
    "Denver": "r/denver",
    "Seattle": "r/seattle",
    "Boston": "r/boston",
    "Miami": "r/miami",
}

STATE_TO_SUBREDDIT = {
    "CA": "r/california",
    "TX": "r/texas",
    "NY": "r/newyork",
    "FL": "r/florida",
    "AZ": "r/arizona",
    "CO": "r/colorado",
    "PA": "r/pennsylvania",
    "WA": "r/washington",
}


def get_reddit_client() -> praw.Reddit:
    """Get authenticated Reddit client."""
    client_id = os.environ.get("REDDIT_CLIENT_ID")
    client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
    username = os.environ.get("REDDIT_USERNAME")

    if not all([client_id, client_secret, username]):
        raise ValueError(
            "REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, and REDDIT_USERNAME must be set"
        )

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=f"house_listings_system (by {username})",
        username=username,
        password=os.environ.get("REDDIT_PASSWORD")  # May be None if using OAuth
    )


def fetch_reddit_posts(
    neighborhood: str, city: str, state: str
) -> List[Dict]:
    """Fetch Reddit posts about a neighborhood."""
    try:
        reddit = get_reddit_client()
    except ValueError as e:
        print(f"Reddit credentials not configured: {e}")
        return []

    posts = []
    three_years_ago = int(time.time() - 3 * 365 * 24 * 3600)

    # Query variations
    queries = [
        f"{neighborhood} {city} crime safety",
        f"{neighborhood} {city} neighborhood",
        f'"{neighborhood}" {city} living',
    ]

    # Subreddit fallback chain
    subreddits = []

    # Try city-specific subreddit
    city_sub = f"r/{city.lower().replace(' ', '')}"
    subreddits.append(city_sub)

    # Try state subreddit
    if state in STATE_TO_SUBREDDIT:
        subreddits.append(STATE_TO_SUBREDDIT[state])

    # Try metro subreddit if found
    for metro, sub in METRO_TO_SUBREDDIT.items():
        if metro.lower() in city.lower() or city.lower() in metro.lower():
            subreddits.append(sub)
            break

    # Add r/all as final fallback
    subreddits.append("r/all")

    for subreddit_name in subreddits:
        for query in queries:
            try:
                # Remove 'r/' prefix if present
                sub_name = subreddit_name.lstrip("r/")

                subreddit = reddit.subreddit(sub_name)
                search_results = subreddit.search(query, time_filter="year", limit=50)

                for submission in search_results:
                    # Filter to 3-year posts
                    if submission.created_utc < three_years_ago:
                        continue

                    post = {
                        "neighborhood": neighborhood,
                        "city": city,
                        "state": state,
                        "reddit_post_id": submission.id,
                        "subreddit": submission.subreddit.display_name,
                        "title": submission.title,
                        "body": submission.selftext,
                        "score": submission.score,
                        "created_utc": int(submission.created_utc),
                        "post_type": "discussion" if submission.selftext else "link",
                    }
                    posts.append(post)

                    if len(posts) >= 100:
                        return posts

            except Exception as e:
                print(f"Error searching {subreddit_name} for '{query}': {e}")
                continue

    return posts[:100]  # Cap at 100


def analyze_sentiment(
    neighborhood: str, city: str, state: str, posts: List[Dict]
) -> Dict:
    """Analyze sentiment of Reddit posts about a neighborhood."""
    if not posts:
        return {
            "neighborhood": neighborhood,
            "city": city,
            "state": state,
            "crime_score": 0.0,
            "safety_score": 0.0,
            "character_score": 0.0,
            "overall_score": 0.0,
            "reddit_post_count": 0,
            "sentiment_summary": "No Reddit posts found",
        }

    client = get_anthropic_client()

    # Prepare posts for analysis
    posts_text = "\n\n".join([
        f"Title: {p['title']}\nBody: {p['body'][:500]}"
        for p in posts[:20]  # Analyze first 20 posts
    ])

    prompt = f"""Analyze the following Reddit posts about {neighborhood}, {city}, {state} and provide sentiment scores.

Posts:
{posts_text}

Return JSON with these fields (float values -1 to 1):
- crime_score: sentiment about crime (-1 = very unsafe, 1 = very safe)
- safety_score: sentiment about neighborhood safety (-1 = unsafe, 1 = very safe)
- character_score: sentiment about neighborhood character (-1 = negative, 1 = very positive)
- overall_score: overall neighborhood sentiment (-1 = very negative, 1 = very positive)
- sentiment_summary: brief summary (max 100 chars)

Return ONLY valid JSON."""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()

        # Extract JSON from response
        import re
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            sentiment = json.loads(json_match.group(0))
        else:
            sentiment = {}

        # Ensure all required fields exist
        result = {
            "neighborhood": neighborhood,
            "city": city,
            "state": state,
            "crime_score": sentiment.get("crime_score", 0.0),
            "safety_score": sentiment.get("safety_score", 0.0),
            "character_score": sentiment.get("character_score", 0.0),
            "overall_score": sentiment.get("overall_score", 0.0),
            "reddit_post_count": len(posts),
            "sentiment_summary": sentiment.get("sentiment_summary", ""),
        }

        return result

    except Exception as e:
        print(f"Error analyzing sentiment: {e}")
        return {
            "neighborhood": neighborhood,
            "city": city,
            "state": state,
            "crime_score": 0.0,
            "safety_score": 0.0,
            "character_score": 0.0,
            "overall_score": 0.0,
            "reddit_post_count": len(posts),
            "sentiment_summary": f"Analysis failed: {str(e)[:50]}",
        }


def run_reddit_enrichment(conn: sqlite3.Connection) -> int:
    """Analyze sentiment for all neighborhoods."""
    neighborhoods = get_distinct_neighborhoods(conn)

    if not neighborhoods:
        print("No neighborhoods found")
        return 0

    count = 0
    for neighborhood, city, state in neighborhoods:
        print(f"Analyzing {neighborhood}, {city}, {state}...")

        # Delete old posts for this neighborhood
        delete_reddit_posts_for_neighborhood(conn, neighborhood, city, state)

        # Fetch new posts
        posts = fetch_reddit_posts(neighborhood, city, state)

        if not posts:
            print(f"  No Reddit posts found")
            continue

        print(f"  Fetched {len(posts)} posts")

        # Insert posts
        for post in posts:
            insert_reddit_post(conn, post)

        # Analyze sentiment
        sentiment = analyze_sentiment(neighborhood, city, state, posts)

        # Upsert sentiment
        upsert_neighborhood_sentiment(conn, sentiment)

        print(f"  Overall sentiment: {sentiment['overall_score']:.2f}")
        count += 1

    if count > 0:
        print(f"\nAnalyzed sentiment for {count} neighborhoods")

    return count
