import pytest


# ── Login ──────────────────────────────────────────────────────────────────────

def test_login_valid_credentials(backend):
    resp = backend.post("/api/drivers/login", json={
        "email": "alice@example.com", "password": "Password1"
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert "token" in data
    assert data["driver"]["email"] == "alice@example.com"
    assert "password_hash" not in data["driver"]


def test_login_wrong_password(backend):
    resp = backend.post("/api/drivers/login", json={
        "email": "alice@example.com", "password": "wrong"
    })
    assert resp.status_code == 401


def test_login_unknown_email(backend):
    resp = backend.post("/api/drivers/login", json={
        "email": "nobody@example.com", "password": "Password1"
    })
    assert resp.status_code == 401


def test_login_case_insensitive_email(backend):
    resp = backend.post("/api/drivers/login", json={
        "email": "ALICE@EXAMPLE.COM", "password": "Password1"
    })
    assert resp.status_code == 200


# ── Signup ─────────────────────────────────────────────────────────────────────

def test_signup_new_driver(backend):
    resp = backend.post("/api/drivers", json={
        "email": "bob@example.com",
        "password": "SecurePass1",
        "first_name": "Bob",
        "last_name": "Volunteer",
        "phone": "4155550002",
    })
    assert resp.status_code == 201
    data = resp.get_json()
    assert data["driver"]["email"] == "bob@example.com"
    assert data["driver"]["partner_id"] is None
    assert "token" in data


def test_signup_duplicate_email(backend):
    resp = backend.post("/api/drivers", json={
        "email": "alice@example.com",
        "password": "SecurePass1",
        "first_name": "Alice2",
        "last_name": "Test",
        "phone": "4155550003",
    })
    assert resp.status_code == 422
    assert "Email has already been taken" in resp.get_json()["errors"]


def test_new_driver_has_no_partner(backend):
    resp = backend.post("/api/drivers", json={
        "email": "new@example.com", "password": "NewPass1",
        "first_name": "New", "last_name": "User", "phone": "4155550099",
    })
    assert resp.get_json()["driver"]["partner_id"] is None


# ── Password reset ─────────────────────────────────────────────────────────────

def test_request_reset_known_email(backend):
    resp = backend.post("/api/drivers/password", json={"email": "alice@example.com"})
    assert resp.status_code == 200
    assert "reset_token" in resp.get_json()


def test_request_reset_unknown_email(backend):
    resp = backend.post("/api/drivers/password", json={"email": "ghost@example.com"})
    assert resp.status_code == 404


def test_reset_password_valid_token(backend):
    token_resp = backend.post("/api/drivers/password", json={"email": "alice@example.com"})
    token = token_resp.get_json()["reset_token"]

    reset_resp = backend.patch("/api/drivers/password", json={
        "email": "alice@example.com",
        "reset_token": token,
        "password": "NewSecure1",
    })
    assert reset_resp.status_code == 200

    login_resp = backend.post("/api/drivers/login", json={
        "email": "alice@example.com", "password": "NewSecure1"
    })
    assert login_resp.status_code == 200


def test_reset_password_old_password_fails_after_reset(backend):
    token_resp = backend.post("/api/drivers/password", json={"email": "alice@example.com"})
    token = token_resp.get_json()["reset_token"]
    backend.patch("/api/drivers/password", json={
        "email": "alice@example.com", "reset_token": token, "password": "NewSecure1"
    })
    resp = backend.post("/api/drivers/login", json={
        "email": "alice@example.com", "password": "Password1"
    })
    assert resp.status_code == 401


def test_reset_token_is_single_use(backend):
    token_resp = backend.post("/api/drivers/password", json={"email": "alice@example.com"})
    token = token_resp.get_json()["reset_token"]

    backend.patch("/api/drivers/password", json={
        "email": "alice@example.com", "reset_token": token, "password": "NewPass1"
    })
    second = backend.patch("/api/drivers/password", json={
        "email": "alice@example.com", "reset_token": token, "password": "AnotherPass1"
    })
    assert second.status_code == 422


def test_reset_invalid_token(backend):
    resp = backend.patch("/api/drivers/password", json={
        "email": "alice@example.com", "reset_token": "bad", "password": "NewPass1"
    })
    assert resp.status_code == 422


# ── Protected routes require auth ─────────────────────────────────────────────

def test_get_driver_requires_auth(backend):
    resp = backend.get("/api/drivers/1")
    assert resp.status_code == 401


def test_get_tasks_requires_auth(backend):
    resp = backend.get("/api/tasks?date=2026-04-18")
    assert resp.status_code == 401
