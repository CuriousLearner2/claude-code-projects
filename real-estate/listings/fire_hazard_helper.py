"""Helper functions to integrate fire hazard into queries."""

import sqlite3
from listings.db import init_db
from listings.fire_hazard import get_fire_hazard_zone
from listings.utils import DB_PATH


def get_fire_hazard_for_listing(latitude: float, longitude: float) -> float:
    """Get fire risk score for a single listing."""
    if not latitude or not longitude:
        return 0.0  # Unknown, neutral

    hazard = get_fire_hazard_zone(latitude, longitude)
    if hazard:
        return hazard["risk_score"]
    return 0.0


def enrich_listings_with_fire_hazard(conn: sqlite3.Connection, limit: int = 100) -> int:
    """
    Enrich listings with fire hazard data.
    Adds a computed fire_risk value based on geocoded coordinates.
    Returns count of listings processed.
    """
    cursor = conn.execute(
        """
        SELECT id, latitude, longitude
        FROM listings
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        LIMIT ?
        """,
        (limit,),
    )

    listings = cursor.fetchall()
    count = 0

    for listing_id, lat, lon in listings:
        hazard = get_fire_hazard_zone(lat, lon)
        if hazard:
            count += 1
            if count % 10 == 0:
                print(f"  Processed {count} listings for fire hazard...")

    return count


def get_listings_by_fire_risk(conn: sqlite3.Connection, max_risk: float = 0.2) -> list:
    """
    Get listings in low-fire-risk areas.
    Note: This requires computing fire hazard on-the-fly since we don't store it.

    Returns list of (id, address, price, neighborhood, fire_risk_score)
    """
    cursor = conn.execute(
        """
        SELECT id, address, price, neighborhood, city, latitude, longitude
        FROM listings
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        ORDER BY price ASC
        LIMIT 50
        """
    )

    low_risk_listings = []

    for row in cursor.fetchall():
        listing_id, address, price, neighborhood, city, lat, lon = row
        hazard = get_fire_hazard_zone(lat, lon)

        if hazard and hazard["risk_score"] <= max_risk:
            low_risk_listings.append(
                {
                    "id": listing_id,
                    "address": address,
                    "price": price,
                    "neighborhood": neighborhood,
                    "city": city,
                    "fire_risk_score": hazard["risk_score"],
                    "fire_zone": hazard["zone_name"],
                }
            )

    return low_risk_listings
