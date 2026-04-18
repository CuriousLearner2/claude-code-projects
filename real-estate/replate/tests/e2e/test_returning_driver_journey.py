"""
End-to-end: returning driver (pre-seeded Alice) logs in, browses
tomorrow's tasks, claims one, marks it missed, resets password.
"""


def test_returning_driver_tomorrow_task(backend):
    # Login
    resp = backend.post("/api/drivers/login", json={
        "email": "alice@example.com", "password": "Password1"
    })
    token = resp.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Profile already has partner_id set — onboarding should be skipped
    profile = backend.get("/api/drivers/1", headers=headers).get_json()
    assert profile["partner_id"] is not None

    # View tomorrow's tasks
    tasks = backend.get("/api/tasks?date=2026-04-19", headers=headers).get_json()
    assert len(tasks) == 1
    task = tasks[0]
    assert task["donor_name"] == "Salesforce Tower Café"

    # Claim
    backend.post(f"/api/tasks/{task['encrypted_id']}/claim", headers=headers)

    # Mark as missed
    miss = backend.patch(f"/api/tasks/{task['id']}/update_completion_details",
                         headers=headers, json={"outcome": "missed"})
    assert miss.get_json()["status"] == "missed"

    # Appears in My Tasks history
    history = backend.get("/api/my_tasks", headers=headers).get_json()
    assert any(t["status"] == "missed" for t in history)


def test_password_reset_flow(backend):
    # Request reset
    req = backend.post("/api/drivers/password", json={"email": "alice@example.com"})
    token = req.get_json()["reset_token"]

    # Submit reset
    backend.patch("/api/drivers/password", json={
        "email": "alice@example.com",
        "reset_token": token,
        "password": "NewAlicePass1",
    })

    # Old password no longer works
    old = backend.post("/api/drivers/login", json={
        "email": "alice@example.com", "password": "Password1"
    })
    assert old.status_code == 401

    # New password works
    new = backend.post("/api/drivers/login", json={
        "email": "alice@example.com", "password": "NewAlicePass1"
    })
    assert new.status_code == 200


def test_concurrent_claim_race(backend):
    # Two drivers attempt to claim the same task
    alice_login = backend.post("/api/drivers/login", json={
        "email": "alice@example.com", "password": "Password1"
    })
    alice_headers = {"Authorization": f"Bearer {alice_login.get_json()['token']}"}

    bob_signup = backend.post("/api/drivers", json={
        "email": "bob@example.com", "password": "BobPass1",
        "first_name": "Bob", "last_name": "V", "phone": "5105550099",
    })
    bob_headers = {"Authorization": f"Bearer {bob_signup.get_json()['token']}"}

    # Alice claims first
    r1 = backend.post("/api/tasks/enc_abc123/claim", headers=alice_headers)
    assert r1.status_code == 200

    # Bob gets a 409
    r2 = backend.post("/api/tasks/enc_abc123/claim", headers=bob_headers)
    assert r2.status_code == 409

    # Bob can't see the claimed task in available list
    available = backend.get("/api/tasks?date=2026-04-18", headers=bob_headers).get_json()
    assert all(t["encrypted_id"] != "enc_abc123" for t in available)
