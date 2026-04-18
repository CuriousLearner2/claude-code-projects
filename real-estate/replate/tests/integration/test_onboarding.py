import pytest


def test_get_partners(backend, auth_headers):
    resp = backend.get("/api/partners", headers=auth_headers)
    assert resp.status_code == 200
    partners = resp.get_json()
    assert len(partners) == 3
    names = [p["name"] for p in partners]
    assert "SF-Marin Food Bank" in names


def test_set_partner_id(backend, auth_headers):
    resp = backend.patch("/api/drivers/1", headers=auth_headers, json={"partner_id": 2})
    assert resp.status_code == 200
    assert resp.get_json()["partner_id"] == 2


def test_partner_id_persists_on_profile(backend, auth_headers):
    backend.patch("/api/drivers/1", headers=auth_headers, json={"partner_id": 3})
    profile = backend.get("/api/drivers/1", headers=auth_headers).get_json()
    assert profile["partner_id"] == 3


def test_new_driver_no_partner(backend):
    signup = backend.post("/api/drivers", json={
        "email": "newdriver@example.com", "password": "Secure123",
        "first_name": "New", "last_name": "Driver", "phone": "5105550001",
    })
    assert signup.get_json()["driver"]["partner_id"] is None


def test_cannot_update_other_driver(backend, auth_headers):
    # Create a second driver
    backend.post("/api/drivers", json={
        "email": "other@example.com", "password": "OtherPass1",
        "first_name": "Other", "last_name": "Driver", "phone": "5105550002",
    })
    resp = backend.patch("/api/drivers/2", headers=auth_headers, json={"partner_id": 1})
    assert resp.status_code == 403
