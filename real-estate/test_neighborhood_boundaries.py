#!/usr/bin/env python3
"""Test neighborhood boundary detection."""

import sqlite3
import json
import requests
from shapely.geometry import Polygon, Point, shape
from scipy.spatial import ConvexHull
import numpy as np
from listings.geocoder import populate_missing_neighborhoods

DB_PATH = "/Users/gautambiswas/Claude Code/real-estate/listings.db"

def get_neighborhood_listings(neighborhood: str):
    """Get all listings for a neighborhood from database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT id, address, latitude, longitude, price, beds
        FROM listings
        WHERE neighborhood = ?
            AND latitude IS NOT NULL
            AND longitude IS NOT NULL
        ORDER BY price DESC
    """, (neighborhood,))
    listings = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return listings

def get_osm_neighborhood_boundary(name: str, city: str = "Oakland"):
    """Query Overpass API for neighborhood boundary."""
    print(f"Querying OpenStreetMap for '{name}' in {city}...")

    # Use Overpass API to find neighborhood relations
    query = f"""
    [out:json];
    area[name="{city}"][boundary=administrative]->.searcharea;
    (
      relation["name"="{name}"]["boundary"="administrative"](area.searcharea);
      relation["name"="{name}"]["place"="neighbourhood"](area.searcharea);
    );
    out geom;
    """

    try:
        response = requests.get(
            "https://overpass-api.de/api/interpreter",
            params={"data": query},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        # Extract polygon from first matching relation
        if data.get("elements"):
            for element in data["elements"]:
                if element.get("type") == "relation" and "geometry" in element:
                    coords = element["geometry"]
                    if coords and len(coords) > 2:
                        return Polygon([(c["lon"], c["lat"]) for c in coords])
        return None
    except Exception as e:
        print(f"  OSM query failed: {e}")
        return None

def get_listing_convex_hull(listings):
    """Compute convex hull from listing coordinates."""
    if len(listings) < 3:
        print(f"  Only {len(listings)} listings - cannot compute convex hull")
        return None

    coords = np.array([[l["longitude"], l["latitude"]] for l in listings])
    try:
        hull = ConvexHull(coords)
        polygon_coords = [tuple(coords[i]) for i in hull.vertices]
        return Polygon(polygon_coords)
    except Exception as e:
        print(f"  Convex hull failed: {e}")
        return None

def print_polygon_bounds(polygon, name):
    """Print polygon bounds and center."""
    if polygon is None:
        return
    bounds = polygon.bounds  # (minx, miny, maxx, maxy)
    center_x = (bounds[0] + bounds[2]) / 2
    center_y = (bounds[1] + bounds[3]) / 2
    area_km2 = polygon.area * 111 * 111  # rough conversion to km²
    print(f"  {name}:")
    print(f"    Bounds: ({bounds[0]:.4f}, {bounds[1]:.4f}) to ({bounds[2]:.4f}, {bounds[3]:.4f})")
    print(f"    Center: ({center_x:.4f}, {center_y:.4f})")
    print(f"    Area: ~{area_km2:.2f} km²")

def compute_intersection(poly1, poly2):
    """Compute intersection and overlap percentage."""
    if poly1 is None or poly2 is None:
        return None, None

    intersection = poly1.intersection(poly2)
    union = poly1.union(poly2)

    overlap_pct_1 = (intersection.area / poly1.area * 100) if poly1.area > 0 else 0
    overlap_pct_2 = (intersection.area / poly2.area * 100) if poly2.area > 0 else 0
    iou = (intersection.area / union.area * 100) if union.area > 0 else 0

    return {
        "overlap_osm": overlap_pct_1,
        "overlap_listings": overlap_pct_2,
        "iou": iou,
        "intersection_area": intersection.area
    }

def main():
    # First, populate missing neighborhoods
    print("=" * 70)
    print("NEIGHBORHOOD BOUNDARY TEST")
    print("=" * 70)

    print("\n0. POPULATING MISSING NEIGHBORHOODS")
    conn = sqlite3.connect(DB_PATH)
    filled = populate_missing_neighborhoods(conn)
    conn.close()
    print(f"   Filled {filled} missing neighborhoods")

    # Find which neighborhoods have listings
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.execute("""
        SELECT neighborhood, COUNT(*) as count
        FROM listings
        WHERE latitude IS NOT NULL AND neighborhood IS NOT NULL AND neighborhood != ''
        GROUP BY neighborhood
        ORDER BY count DESC
        LIMIT 5
    """)
    top_neighborhoods = [(row[0], row[1]) for row in cursor.fetchall()]
    conn.close()

    if not top_neighborhoods:
        print("   No neighborhoods with listings found after population")
        return

    # Use the neighborhood with most listings
    test_neighborhood, count = top_neighborhoods[0]
    print(f"   Testing with '{test_neighborhood}' ({count} listings)")

    # 1. Get listings
    print(f"\n1. EXTRACTING LISTINGS FROM DATABASE")
    listings = get_neighborhood_listings(test_neighborhood)
    print(f"   Found {len(listings)} '{test_neighborhood}' listings with coordinates")

    if listings:
        prices = [l["price"] for l in listings if l["price"]]
        beds = [l["beds"] for l in listings if l["beds"]]
        print(f"   Price range: ${min(prices):,} - ${max(prices):,}")
        print(f"   Avg beds: {sum(beds)/len(beds):.1f}")
        print(f"   Sample addresses:")
        for l in listings[:3]:
            print(f"     - {l['address']}: ${l['price']:,} ({l['beds']} bed)")

    # 2. Get OSM boundary (try multiple cities)
    print(f"\n2. QUERYING OPENSTREETMAP")
    osm_polygon = None
    for city in ["Oakland", "Berkeley", "California"]:
        osm_polygon = get_osm_neighborhood_boundary(test_neighborhood, city)
        if osm_polygon:
            print(f"   ✓ Found in {city}")
            break

    if osm_polygon:
        print("   ✓ Found OSM boundary")
        print_polygon_bounds(osm_polygon, "OSM Boundary")
    else:
        print("   ✗ No OSM boundary found (neighborhood may not be in OSM)")

    # 3. Compute listing-based convex hull
    print("\n3. COMPUTING LISTING-BASED CONVEX HULL")
    listing_polygon = get_listing_convex_hull(listings)
    if listing_polygon:
        print("   ✓ Computed convex hull from listings")
        print_polygon_bounds(listing_polygon, "Listing Convex Hull")

    # 4. Compare
    if osm_polygon and listing_polygon:
        print("\n4. COMPARING BOUNDARIES")
        overlap = compute_intersection(osm_polygon, listing_polygon)
        print(f"   OSM-to-Hull overlap: {overlap['overlap_osm']:.1f}%")
        print(f"   Hull-to-OSM overlap: {overlap['overlap_listings']:.1f}%")
        print(f"   Intersection over Union: {overlap['iou']:.1f}%")

        if overlap['iou'] > 80:
            print("   → Boundaries align well ✓")
        elif overlap['iou'] > 50:
            print("   → Partial overlap (hull captures some OSM area)")
        else:
            print("   → Poor overlap (may be different neighborhoods)")

    # 5. Recommendation
    print("\n5. RECOMMENDATION")
    if osm_polygon and listing_polygon:
        if overlap['iou'] > 80:
            print("   Use OSM boundary (more authoritative)")
        else:
            print("   Use listing-based hull (matches actual listings)")
    elif osm_polygon:
        print("   Use OSM boundary (only option with enough data)")
    elif listing_polygon:
        print("   Use listing-based hull (direct from your data)")
    else:
        print("   Manual boundary definition recommended (no data sources)")

    # 6. GeoJSON export
    if listing_polygon:
        print(f"\n6. GEOJSON EXPORT (LISTING-BASED HULL)")
        geojson = {
            "type": "Feature",
            "properties": {
                "name": test_neighborhood,
                "state": "CA",
                "source": "listing_convex_hull",
                "listing_count": len(listings)
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [list(listing_polygon.exterior.coords)]
            }
        }
        print(json.dumps(geojson, indent=2))

if __name__ == "__main__":
    main()
