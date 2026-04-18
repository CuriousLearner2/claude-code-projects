"""Geocode addresses and extract neighborhoods."""

import os
import sqlite3
from typing import Dict, Optional

import googlemaps

from listings.db import (
    get_listings_needing_geocode,
    get_geocode_cache,
    set_geocode_cache,
    upsert_listing,
)


def geocode_address(conn: sqlite3.Connection, address: str) -> Optional[Dict]:
    """Geocode address with caching using Google Maps API."""
    if not address:
        return None

    # Check cache first
    cache_result = get_geocode_cache(conn, address)
    if cache_result:
        return cache_result

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("Error: GOOGLE_MAPS_API_KEY environment variable not set")
        return None

    try:
        gmaps = googlemaps.Client(key=api_key)
        results = gmaps.geocode(address)
    except Exception as e:
        print(f"Geocoding error for '{address}': {e}")
        return None

    if not results:
        return None

    result_data = results[0]
    latitude = result_data["geometry"]["location"]["lat"]
    longitude = result_data["geometry"]["location"]["lng"]

    # Extract components from address_components
    address_components = result_data.get("address_components", [])

    neighborhood = None
    city = None
    state = None
    zip_code = None

    for component in address_components:
        types = component.get("types", [])
        short_name = component.get("short_name", "")
        long_name = component.get("long_name", "")

        if "neighborhood" in types:
            neighborhood = long_name
        elif "locality" in types:
            city = long_name
        elif "administrative_area_level_1" in types:
            state = short_name
        elif "postal_code" in types:
            zip_code = long_name

    result = {
        "neighborhood": neighborhood,
        "city": city,
        "state": state,
        "zip_code": zip_code,
        "latitude": latitude,
        "longitude": longitude,
    }

    # Cache the result
    set_geocode_cache(conn, address, result)

    return result


def populate_missing_neighborhoods(conn: sqlite3.Connection) -> int:
    """Fill in missing neighborhoods by reverse geocoding coordinates."""
    cursor = conn.execute("""
        SELECT id, latitude, longitude
        FROM listings
        WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            AND (neighborhood IS NULL OR neighborhood = '')
        LIMIT 100
    """)

    listings = cursor.fetchall()
    count = 0

    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("Error: GOOGLE_MAPS_API_KEY environment variable not set")
        return 0

    gmaps = googlemaps.Client(key=api_key)

    for row in listings:
        if hasattr(row, 'keys'):
            listing_id, lat, lon = row['id'], row['latitude'], row['longitude']
        else:
            listing_id, lat, lon = row

        try:
            results = gmaps.reverse_geocode((lat, lon))
            if results:
                result_data = results[0]
                address_components = result_data.get("address_components", [])

                neighborhood = ""
                city = ""
                state = ""

                sublocality = ""
                for component in address_components:
                    types = component.get("types", [])
                    long_name = component.get("long_name", "")
                    short_name = component.get("short_name", "")

                    if "neighborhood" in types:
                        neighborhood = long_name
                    elif any(t in types for t in ("sublocality_level_1", "sublocality")):
                        if not sublocality:
                            sublocality = long_name
                    elif "locality" in types:
                        city = long_name
                    elif "administrative_area_level_1" in types:
                        state = short_name

                # Fall back to sublocality, then city if no neighborhood returned
                if not neighborhood and sublocality:
                    neighborhood = sublocality
                if not neighborhood and city:
                    neighborhood = city

                # Only update neighborhood — never overwrite email-parsed city
                cursor.execute("""
                    UPDATE listings
                    SET neighborhood = ?, updated_at = datetime('now')
                    WHERE id = ?
                """, (neighborhood or "", listing_id))
                conn.commit()
                count += 1
                if count % 10 == 0:
                    print(f"  Populated {count} neighborhoods...")
        except Exception as e:
            # Skip on errors (rate limit, timeout, etc)
            pass

    if count > 0:
        print(f"\nPopulated {count} missing neighborhoods")

    return count


def run_geocoder(conn: sqlite3.Connection) -> int:
    """Geocode all listings without coordinates."""
    listings = get_listings_needing_geocode(conn)

    if not listings:
        print("No listings need geocoding")
        return 0

    count = 0
    for listing in listings:
        address = listing.get("address")
        if not address:
            continue

        # Build complete address string with city/state for better geocoding
        # Google Maps API works better with full context
        full_address = address
        city = listing.get("city")
        state = listing.get("state")

        if city and state:
            full_address = f"{address}, {city}, {state}"
        elif city:
            full_address = f"{address}, {city}"
        elif state:
            full_address = f"{address}, {state}"

        print(f"Geocoding: {full_address}")
        result = geocode_address(conn, full_address)

        if result:
            # Validate geocoded city — if the actual city is not in the allowed list, skip this listing
            ALLOWED_CITIES = {'Oakland', 'Berkeley', 'Albany', 'Piedmont', 'Kensington', 'El Cerrito'}
            geocoded_city = result.get("city")
            if geocoded_city and geocoded_city not in ALLOWED_CITIES:
                print(f"  Skipping {full_address}: geocoded city '{geocoded_city}' not allowed")
                conn.execute("DELETE FROM listings WHERE id = ?", (listing["id"],))
                conn.commit()
                continue

            # Preserve existing city — don't let geocoder overwrite a city
            # already parsed from the email (Google Maps can return wrong city
            # for ambiguous street names, e.g. "936 Fillmore St" → San Francisco
            # instead of Albany)
            resolved_city = listing.get("city") or geocoded_city

            # Update listing with geocoding data
            listing_update = {
                "id": listing["id"],
                "gmail_message_id": listing["gmail_message_id"],
                "neighborhood": result["neighborhood"],
                "city": resolved_city,
                "state": result["state"],
                "zip_code": result.get("zip_code"),
                "latitude": result["latitude"],
                "longitude": result["longitude"],
                "geocoded_at": __import__("datetime").datetime.utcnow().isoformat(),
            }
            # Preserve existing fields
            for key in listing:
                if key not in listing_update:
                    listing_update[key] = listing[key]

            upsert_listing(conn, listing_update)
            count += 1
        else:
            print(f"  Failed to geocode: {full_address}")

    if count > 0:
        print(f"\nGeocoded {count} listings")

    return count
