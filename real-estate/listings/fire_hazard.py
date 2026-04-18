"""Fire hazard zone assessment using Cal Fire FHSZ data."""

import requests
import sqlite3
from typing import Optional, Dict
from datetime import datetime


# CAL FIRE hazard class to risk score mapping
FIRE_HAZARD_SCORES = {
    "Very High": 0.8,
    "High": 0.6,
    "Moderate": 0.3,
    "Low": 0.0,
}


def get_fire_hazard_zone(latitude: float, longitude: float) -> Optional[Dict]:
    """
    Query Cal Fire FHSZ using CA State GIS service.
    Returns fire zone info based on coordinates.

    Uses the authoritative CA State GIS service which has both:
    - Layer 0: State Responsibility Areas (SRA)
    - Layer 1: Local Responsibility Areas (LRA)
    """
    if not latitude or not longitude:
        return None

    try:
        base_url = "https://services.gis.ca.gov/arcgis/rest/services/Environment/Fire_Severity_Zones/MapServer"

        # Try Local Responsibility Areas first (Layer 1), then State (Layer 0)
        for layer_idx in [1, 0]:
            url = f"{base_url}/{layer_idx}/query"

            params = {
                "geometry": f"{longitude},{latitude}",
                "geometryType": "esriGeometryPoint",
                "inSR": "4326",
                "spatialRel": "esriSpatialRelIntersects",
                "outFields": "HAZ_CLASS,SRA,INCORP",
                "returnGeometry": "false",
                "f": "json",
            }

            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()

            if data.get("features") and len(data["features"]) > 0:
                feature = data["features"][0]
                attributes = feature.get("attributes", {})
                haz_class = attributes.get("HAZ_CLASS", "Unknown")
                sra_type = attributes.get("SRA", "")

                # Get risk score
                risk_score = FIRE_HAZARD_SCORES.get(haz_class, 0.2)

                return {
                    "zone_name": haz_class,
                    "area_type": "Local" if layer_idx == 1 else "State",
                    "sra": sra_type,
                    "risk_score": risk_score,
                    "latitude": latitude,
                    "longitude": longitude,
                }

        # No feature found in either layer - low risk
        return {
            "zone_name": "Low",
            "area_type": None,
            "sra": None,
            "risk_score": 0.0,
            "latitude": latitude,
            "longitude": longitude,
        }

    except requests.RequestException as e:
        print(f"Error querying Cal Fire data: {e}")
        return None
    except Exception as e:
        print(f"Error processing fire hazard data: {e}")
        return None


def assess_neighborhood_fire_hazard(listings_coords: list) -> Optional[Dict]:
    """
    Assess fire hazard for a neighborhood based on listings coordinates.
    Returns average risk score for the neighborhood.
    """
    if not listings_coords:
        return None

    hazard_scores = []
    zone_names = []

    for lat, lon in listings_coords:
        hazard = get_fire_hazard_zone(lat, lon)
        if hazard:
            hazard_scores.append(hazard["risk_score"])
            zone_names.append(hazard["zone_name"])

    if not hazard_scores:
        return None

    avg_score = sum(hazard_scores) / len(hazard_scores)
    most_common_zone = max(set(zone_names), key=zone_names.count) if zone_names else "Unknown"

    return {
        "fire_risk_score": avg_score,
        "primary_zone": most_common_zone,
        "assessment_count": len(hazard_scores),
    }


def format_fire_risk(risk_score: float) -> str:
    """Format fire risk score as human-readable text."""
    if risk_score < -0.3:
        return "Very Low Risk ✅"
    elif risk_score < 0.2:
        return "Low Risk ✅"
    elif risk_score < 0.5:
        return "Moderate Risk ⚠️"
    elif risk_score < 0.7:
        return "High Risk 🔴"
    else:
        return "Very High Risk 🔴"


def enrich_properties_with_fire_data(conn: sqlite3.Connection) -> Dict:
    """
    Add fire hazard zone and risk data to all properties in listings table.

    Returns:
        Dict with enrichment statistics
    """
    stats = {'enriched': 0, 'errors': 0}

    # Add fire_risk_score column if it doesn't exist
    try:
        conn.execute("ALTER TABLE listings ADD COLUMN fire_risk_score REAL")
    except sqlite3.OperationalError:
        pass  # Column already exists

    try:
        conn.execute("ALTER TABLE listings ADD COLUMN fire_zone TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Get all properties without fire data
    cursor = conn.execute("""
        SELECT id, address, latitude, longitude
        FROM listings
        WHERE fire_risk_score IS NULL
        ORDER BY city
    """)

    properties = cursor.fetchall()
    print(f"Enriching {len(properties)} properties with fire hazard data...\n")

    for i, prop in enumerate(properties):
        try:
            if (i + 1) % 50 == 0:
                print(f"  [{i + 1}/{len(properties)}] processed...")

            prop_id, address, latitude, longitude = prop

            if not (latitude and longitude):
                continue

            # Assess fire hazard
            hazard = get_fire_hazard_zone(latitude, longitude)

            # Update database
            conn.execute("""
                UPDATE listings
                SET fire_zone = ?, fire_risk_score = ?
                WHERE id = ?
            """, (hazard['zone_name'], hazard['risk_score'], prop_id))

            stats['enriched'] += 1

        except Exception as e:
            stats['errors'] += 1
            print(f"  Error enriching {address}: {e}")

    conn.commit()
    return stats
