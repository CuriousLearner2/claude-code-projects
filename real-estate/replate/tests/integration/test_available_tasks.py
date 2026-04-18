import pytest

# Alice's location: SF downtown (37.7749, -122.4194)
# LinkedIn Café:    SF SoMa   (37.7877, -122.3974)  ~2.4 km from Alice
# Google Cafeteria: Mtn View  (37.4220, -122.0841)  ~48 km from Alice

SF_PARAMS   = {"date": "2026-04-18", "lat": 37.7749, "lon": -122.4194}
NO_LOC_PARAMS = {"date": "2026-04-18"}


# ── Basic listing ──────────────────────────────────────────────────────────────

def test_list_tasks_today(backend, auth_headers):
    resp = backend.get("/api/tasks?date=2026-04-18", headers=auth_headers)
    assert resp.status_code == 200
    tasks = resp.get_json()
    assert len(tasks) == 2
    donor_names = {t["donor_name"] for t in tasks}
    assert "Google Cafeteria" in donor_names
    assert "LinkedIn Café" in donor_names


def test_list_tasks_tomorrow(backend, auth_headers):
    resp = backend.get("/api/tasks?date=2026-04-19", headers=auth_headers)
    tasks = resp.get_json()
    assert len(tasks) == 1
    assert tasks[0]["donor_name"] == "Salesforce Tower Café"


def test_list_tasks_empty_date(backend, auth_headers):
    resp = backend.get("/api/tasks?date=2026-01-01", headers=auth_headers)
    assert resp.get_json() == []


def test_list_tasks_missing_date_param(backend, auth_headers):
    resp = backend.get("/api/tasks", headers=auth_headers)
    assert resp.status_code == 400


def test_get_task_detail(backend, auth_headers):
    resp = backend.get("/api/tasks/enc_abc123", headers=auth_headers)
    assert resp.status_code == 200
    task = resp.get_json()
    assert task["donor_name"] == "Google Cafeteria"
    assert task["contact_name"] == "Jane Smith"
    assert task["tray_count"] == 8


def test_get_task_not_found(backend, auth_headers):
    resp = backend.get("/api/tasks/enc_xxxxxx", headers=auth_headers)
    assert resp.status_code == 404


def test_claimed_task_excluded_from_available(backend, auth_headers):
    backend.post("/api/tasks/enc_abc123/claim", headers=auth_headers)
    resp = backend.get("/api/tasks?date=2026-04-18", headers=auth_headers)
    tasks = resp.get_json()
    assert all(t["encrypted_id"] != "enc_abc123" for t in tasks)


def test_claim_task(backend, auth_headers):
    resp = backend.post("/api/tasks/enc_abc123/claim", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "claimed"
    assert resp.get_json()["driver_id"] == 1


def test_claim_already_claimed_task(backend, auth_headers):
    backend.post("/api/tasks/enc_abc123/claim", headers=auth_headers)
    resp = backend.post("/api/tasks/enc_abc123/claim", headers=auth_headers)
    assert resp.status_code == 409


# ── Geo-proximity: distance_km field ──────────────────────────────────────────

def test_distance_km_present_when_location_provided(backend, auth_headers):
    resp = backend.get("/api/tasks", query_string=SF_PARAMS, headers=auth_headers)
    for task in resp.get_json():
        assert "distance_km" in task
        assert isinstance(task["distance_km"], float)
        assert task["distance_km"] >= 0


def test_distance_km_absent_without_location(backend, auth_headers):
    resp = backend.get("/api/tasks", query_string=NO_LOC_PARAMS, headers=auth_headers)
    for task in resp.get_json():
        assert "distance_km" not in task


def test_distance_km_absent_when_only_lat_provided(backend, auth_headers):
    resp = backend.get("/api/tasks", query_string={"date": "2026-04-18", "lat": 37.7749},
                       headers=auth_headers)
    for task in resp.get_json():
        assert "distance_km" not in task


# ── Geo-proximity: sort order ──────────────────────────────────────────────────

def test_tasks_sorted_nearest_first_from_sf(backend, auth_headers):
    """From SF, LinkedIn Café (~2.4 km) must appear before Google (~48 km)."""
    resp = backend.get("/api/tasks", query_string=SF_PARAMS, headers=auth_headers)
    tasks = resp.get_json()
    assert tasks[0]["donor_name"] == "LinkedIn Café"
    assert tasks[1]["donor_name"] == "Google Cafeteria"


def test_tasks_sorted_nearest_first_from_mountain_view(backend, auth_headers):
    """From Mountain View, Google Cafeteria (~0 km) must appear before LinkedIn (~48 km)."""
    resp = backend.get("/api/tasks", query_string={
        "date": "2026-04-18", "lat": 37.4220, "lon": -122.0841
    }, headers=auth_headers)
    tasks = resp.get_json()
    assert tasks[0]["donor_name"] == "Google Cafeteria"
    assert tasks[1]["donor_name"] == "LinkedIn Café"


def test_sort_order_is_ascending_distance(backend, auth_headers):
    """distance_km values must be non-decreasing."""
    resp = backend.get("/api/tasks", query_string=SF_PARAMS, headers=auth_headers)
    distances = [t["distance_km"] for t in resp.get_json()]
    assert distances == sorted(distances)


def test_distance_values_are_plausible(backend, auth_headers):
    resp = backend.get("/api/tasks", query_string=SF_PARAMS, headers=auth_headers)
    tasks = resp.get_json()
    by_name = {t["donor_name"]: t["distance_km"] for t in tasks}
    assert by_name["LinkedIn Café"] < 5           # SF→SF: under 5 km
    assert by_name["Google Cafeteria"] > 40        # SF→Mountain View: over 40 km


def test_tomorrow_tasks_also_sorted_by_proximity(backend, auth_headers):
    resp = backend.get("/api/tasks", query_string={
        "date": "2026-04-19", "lat": 37.7749, "lon": -122.4194
    }, headers=auth_headers)
    tasks = resp.get_json()
    assert len(tasks) == 1
    assert "distance_km" in tasks[0]
    assert tasks[0]["distance_km"] < 5   # Salesforce Tower is in SF


# ── Geo-proximity: store immutability ─────────────────────────────────────────

def test_distance_km_not_persisted_in_store(backend, auth_headers):
    """Two calls with different locations must not pollute stored task objects."""
    backend.get("/api/tasks", query_string=SF_PARAMS, headers=auth_headers)
    resp2 = backend.get("/api/tasks", query_string={
        "date": "2026-04-18", "lat": 37.4220, "lon": -122.0841
    }, headers=auth_headers)
    # From Mountain View, Google should be first
    tasks = resp2.get_json()
    assert tasks[0]["donor_name"] == "Google Cafeteria"


def test_no_location_after_location_call_has_no_distance(backend, auth_headers):
    """Calling with location then without location must not return distance_km."""
    backend.get("/api/tasks", query_string=SF_PARAMS, headers=auth_headers)
    resp = backend.get("/api/tasks", query_string=NO_LOC_PARAMS, headers=auth_headers)
    for task in resp.get_json():
        assert "distance_km" not in task


# ── Driver location on profile ─────────────────────────────────────────────────

def test_driver_location_stored_on_profile(backend, auth_headers):
    backend.patch("/api/drivers/1", headers=auth_headers,
                  json={"lat": 37.7749, "lon": -122.4194})
    profile = backend.get("/api/drivers/1", headers=auth_headers).get_json()
    assert profile["lat"] == 37.7749
    assert profile["lon"] == -122.4194


def test_driver_location_not_required(backend, auth_headers):
    """Drivers with no lat/lon can still fetch tasks (unsorted)."""
    backend.patch("/api/drivers/1", headers=auth_headers,
                  json={"lat": None, "lon": None})
    resp = backend.get("/api/tasks?date=2026-04-18", headers=auth_headers)
    assert resp.status_code == 200
    assert len(resp.get_json()) == 2
