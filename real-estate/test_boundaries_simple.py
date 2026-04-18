#!/usr/bin/env python3
"""Test boundary detection with a geographic cluster of listings."""

import sqlite3
import json
import requests
from shapely.geometry import Polygon, box
from scipy.spatial import ConvexHull
import numpy as np

DB_PATH = "/Users/gautambiswas/Claude Code/real-estate/listings.db"

def get_berkeley_listings():
    """Get listings in Berkeley area (latitude around 37.87, longitude around -122.27)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT id, address, latitude, longitude, price, beds
        FROM listings
        WHERE latitude BETWEEN 37.85 AND 37.90
            AND longitude BETWEEN -122.31 AND -122.23
        ORDER BY price DESC
    """)
    listings = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return listings

def get_osm_boundary(name: str):
    """Query Overpass API for boundary relation."""
    print(f"Querying OpenStreetMap for '{name}'...")

    query = f"""
    [out:json];
    (
      relation["name"="{name}"]["boundary"="administrative"];
      relation["name"="{name}"]["place"="city"];
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

def compute_convex_hull(listings):
    """Compute convex hull from listing coordinates."""
    if len(listings) < 3:
        return None

    coords = np.array([[l["longitude"], l["latitude"]] for l in listings])
    try:
        hull = ConvexHull(coords)
        polygon_coords = [tuple(coords[i]) for i in hull.vertices]
        return Polygon(polygon_coords)
    except Exception as e:
        print(f"Convex hull failed: {e}")
        return None

def compute_bounding_box(listings):
    """Compute simple bounding box from listings."""
    lats = [l["latitude"] for l in listings]
    lons = [l["longitude"] for l in listings]
    return box(min(lons), min(lats), max(lons), max(lats))

def main():
    print("=" * 70)
    print("GEOGRAPHIC CLUSTER BOUNDARY TEST - BERKELEY AREA")
    print("=" * 70)

    # 1. Get listings
    print("\n1. EXTRACTING LISTINGS FROM DATABASE")
    listings = get_berkeley_listings()
    print(f"   Found {len(listings)} listings in Berkeley cluster")

    if listings:
        prices = [l["price"] for l in listings if l["price"]]
        print(f"   Price range: ${min(prices):,} - ${max(prices):,}")
        print(f"   Sample locations:")
        for l in listings[:3]:
            print(f"     - ({l['latitude']:.4f}, {l['longitude']:.4f}): ${l['price']:,}")

    # 2. Compute bounding box
    print("\n2. COMPUTING BOUNDING BOX")
    bbox = compute_bounding_box(listings)
    bounds = bbox.bounds
    print(f"   Bounds: ({bounds[0]:.4f}, {bounds[1]:.4f}) to ({bounds[2]:.4f}, {bounds[3]:.4f})")
    print(f"   Center: ({(bounds[0]+bounds[2])/2:.4f}, {(bounds[1]+bounds[3])/2:.4f})")

    # 3. Compute convex hull
    print("\n3. COMPUTING CONVEX HULL")
    hull = compute_convex_hull(listings)
    if hull:
        hull_bounds = hull.bounds
        hull_area = hull.area * 111 * 111  # rough km²
        bbox_area = bbox.area * 111 * 111
        print(f"   Hull area: ~{hull_area:.2f} km²")
        print(f"   Bbox area: ~{bbox_area:.2f} km²")
        print(f"   Hull is {(hull_area/bbox_area*100):.1f}% of bbox")

    # 4. Get OSM boundary for Berkeley
    print("\n4. QUERYING OPENSTREETMAP")
    osm_berkeley = get_osm_boundary("Berkeley")
    if osm_berkeley:
        print("   ✓ Found Berkeley boundary")
        osm_bounds = osm_berkeley.bounds
        osm_area = osm_berkeley.area * 111 * 111
        print(f"   OSM area: ~{osm_area:.2f} km²")

        # Compare with our cluster
        if hull:
            intersection = hull.intersection(osm_berkeley)
            overlap_hull = (intersection.area / hull.area * 100) if hull.area > 0 else 0
            overlap_osm = (intersection.area / osm_berkeley.area * 100) if osm_berkeley.area > 0 else 0
            print(f"   Overlap: {overlap_hull:.1f}% of cluster, {overlap_osm:.1f}% of Berkeley")
    else:
        print("   ✗ No OSM Berkeley boundary found")

    # 5. GeoJSON export
    print("\n5. GEOJSON EXPORT")
    if hull:
        geojson = {
            "type": "Feature",
            "properties": {
                "name": "Berkeley_Cluster",
                "type": "listing_convex_hull",
                "listing_count": len(listings),
                "approx_area_km2": round(hull_area, 2)
            },
            "geometry": {
                "type": "Polygon",
                "coordinates": [list(hull.exterior.coords)]
            }
        }
        print(json.dumps(geojson, indent=2)[:500] + "...[truncated]")

if __name__ == "__main__":
    main()
