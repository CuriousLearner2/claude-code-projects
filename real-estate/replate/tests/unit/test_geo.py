"""Unit tests for the Haversine distance calculation and proximity ranking."""

import math
import pytest

from dummy_backend.server import haversine_km

# Reference coordinates
SF        = (37.7749, -122.4194)   # SF downtown (Alice's home base)
LINKEDIN  = (37.7877, -122.3974)   # LinkedIn Café, SoMa SF
SALESFORCE= (37.7895, -122.3963)   # Salesforce Tower, SF
GOOGLE    = (37.4220, -122.0841)   # Google Cafeteria, Mountain View
NYC       = (40.7128,  -74.0060)   # New York City


# ── Correctness ────────────────────────────────────────────────────────────────

def test_same_point_is_zero():
    assert haversine_km(*SF, *SF) == 0.0


def test_sf_to_mountain_view_approx_48km():
    dist = haversine_km(*SF, *GOOGLE)
    assert 45 < dist < 52, f"Expected ~48 km, got {dist:.1f}"


def test_sf_to_linkedin_under_5km():
    dist = haversine_km(*SF, *LINKEDIN)
    assert dist < 5.0, f"Expected < 5 km, got {dist:.1f}"


def test_sf_to_salesforce_under_5km():
    dist = haversine_km(*SF, *SALESFORCE)
    assert dist < 5.0


def test_sf_to_nyc_approx_4100km():
    dist = haversine_km(*SF, *NYC)
    assert 4000 < dist < 4200, f"Expected ~4100 km, got {dist:.1f}"


def test_symmetry():
    d1 = haversine_km(*SF, *LINKEDIN)
    d2 = haversine_km(*LINKEDIN, *SF)
    assert abs(d1 - d2) < 0.001


def test_triangle_inequality():
    sf_to_linkedin  = haversine_km(*SF, *LINKEDIN)
    sf_to_salesforce = haversine_km(*SF, *SALESFORCE)
    linkedin_to_salesforce = haversine_km(*LINKEDIN, *SALESFORCE)
    assert sf_to_linkedin + linkedin_to_salesforce >= sf_to_salesforce


# ── Ranking order ──────────────────────────────────────────────────────────────

def test_linkedin_closer_to_sf_than_google():
    sf_to_linkedin = haversine_km(*SF, *LINKEDIN)
    sf_to_google   = haversine_km(*SF, *GOOGLE)
    assert sf_to_linkedin < sf_to_google


def test_linkedin_closer_to_sf_than_salesforce():
    """LinkedIn (SoMa) is slightly closer to SF downtown than Salesforce (FiDi)."""
    sf_to_linkedin   = haversine_km(*SF, *LINKEDIN)
    sf_to_salesforce = haversine_km(*SF, *SALESFORCE)
    assert sf_to_linkedin < sf_to_salesforce


def test_google_is_farthest_from_sf():
    distances = {
        "linkedin":   haversine_km(*SF, *LINKEDIN),
        "salesforce": haversine_km(*SF, *SALESFORCE),
        "google":     haversine_km(*SF, *GOOGLE),
    }
    assert distances["google"] == max(distances.values())


def test_from_mountain_view_google_is_nearest():
    """From Mountain View, Google Cafeteria should be the nearest of the three."""
    mv = GOOGLE  # use Google coords as the driver location
    distances = {
        "google":     haversine_km(*mv, *GOOGLE),
        "linkedin":   haversine_km(*mv, *LINKEDIN),
        "salesforce": haversine_km(*mv, *SALESFORCE),
    }
    assert distances["google"] == min(distances.values())
    assert distances["google"] < 1.0   # driver is at pickup — essentially 0
