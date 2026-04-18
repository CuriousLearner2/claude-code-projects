"""
End-to-end: new driver signs up, completes onboarding, claims a task,
logs it as complete, and logs out.
"""


def test_new_driver_full_journey(backend):
    # 1. Signup
    resp = backend.post("/api/drivers", json={
        "email": "carol@example.com",
        "password": "CarolPass1",
        "first_name": "Carol",
        "last_name": "Volunteer",
        "phone": "5105550010",
    })
    assert resp.status_code == 201
    data = resp.get_json()
    token = data["token"]
    driver_id = data["driver"]["id"]
    assert data["driver"]["partner_id"] is None
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Fetch partners for onboarding
    partners = backend.get("/api/partners", headers=headers).get_json()
    assert len(partners) == 3

    # 3. Select NPO
    update = backend.patch(f"/api/drivers/{driver_id}", headers=headers,
                            json={"partner_id": partners[0]["id"]})
    assert update.get_json()["partner_id"] == partners[0]["id"]

    # 4. Browse available tasks for today
    tasks = backend.get("/api/tasks?date=2026-04-18", headers=headers).get_json()
    assert len(tasks) == 2

    # 5. View task detail
    task = backend.get(f"/api/tasks/{tasks[0]['encrypted_id']}", headers=headers).get_json()
    assert task["donor_name"]
    assert task["address"]
    assert task["contact_name"]

    # 6. Claim task
    claimed = backend.post(f"/api/tasks/{task['encrypted_id']}/claim", headers=headers)
    assert claimed.status_code == 200
    task_id = claimed.get_json()["id"]

    # 7. Task appears in My Tasks
    my = backend.get("/api/my_tasks", headers=headers).get_json()
    assert any(t["id"] == task_id for t in my)

    # 8. Task no longer in available list
    available = backend.get("/api/tasks?date=2026-04-18", headers=headers).get_json()
    assert all(t["id"] != task_id for t in available)

    # 9. Complete the task
    done = backend.patch(f"/api/tasks/{task_id}/update_completion_details",
                         headers=headers,
                         json={"outcome": "completed", "weight": 42.5, "partner_id": partners[0]["id"]})
    assert done.status_code == 200
    assert done.get_json()["status"] == "completed"

    # 10. Task moves to history
    history = backend.get("/api/my_tasks", headers=headers).get_json()
    completed_task = next(t for t in history if t["id"] == task_id)
    assert completed_task["status"] == "completed"
    assert completed_task["completion_details"]["weight"] == 42.5


def test_new_driver_claim_then_miss(backend):
    resp = backend.post("/api/drivers", json={
        "email": "dave@example.com", "password": "DavePass1",
        "first_name": "Dave", "last_name": "V", "phone": "5105550020",
    })
    token = resp.get_json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    backend.patch(f"/api/drivers/{resp.get_json()['driver']['id']}",
                  headers=headers, json={"partner_id": 1})

    backend.post("/api/tasks/enc_abc123/claim", headers=headers)
    miss = backend.patch("/api/tasks/101/update_completion_details",
                         headers=headers, json={"outcome": "missed"})
    assert miss.get_json()["status"] == "missed"
