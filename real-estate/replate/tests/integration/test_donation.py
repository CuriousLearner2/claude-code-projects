import pytest


@pytest.fixture
def claimed_task(backend, auth_headers):
    backend.post("/api/tasks/enc_abc123/claim", headers=auth_headers)
    return 101  # task id


def test_complete_task(backend, auth_headers, claimed_task):
    resp = backend.patch(
        f"/api/tasks/{claimed_task}/update_completion_details",
        headers=auth_headers,
        json={"outcome": "completed", "weight": 45.5, "partner_id": 1, "photo_url": None},
    )
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "completed"
    assert data["completion_details"]["weight"] == 45.5
    assert data["completion_details"]["partner_id"] == 1


def test_complete_task_with_photo(backend, auth_headers, claimed_task):
    resp = backend.patch(
        f"/api/tasks/{claimed_task}/update_completion_details",
        headers=auth_headers,
        json={
            "outcome": "completed",
            "weight": 30,
            "partner_id": 2,
            "photo_url": "https://storage.replate.org/mock/photo.jpg",
        },
    )
    assert resp.get_json()["completion_details"]["photo_url"] is not None


def test_miss_task(backend, auth_headers, claimed_task):
    resp = backend.patch(
        f"/api/tasks/{claimed_task}/update_completion_details",
        headers=auth_headers,
        json={"outcome": "missed"},
    )
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "missed"


def test_cannot_finalize_already_completed(backend, auth_headers, claimed_task):
    payload = {"outcome": "completed", "weight": 10, "partner_id": 1}
    backend.patch(f"/api/tasks/{claimed_task}/update_completion_details",
                  headers=auth_headers, json=payload)
    resp = backend.patch(f"/api/tasks/{claimed_task}/update_completion_details",
                         headers=auth_headers, json=payload)
    assert resp.status_code == 409


def test_cannot_complete_other_drivers_task(backend, auth_headers):
    # Create second driver and have them claim a task
    signup = backend.post("/api/drivers", json={
        "email": "bob@example.com", "password": "BobPass1",
        "first_name": "Bob", "last_name": "V", "phone": "5105550099",
    })
    bob_token = signup.get_json()["token"]
    bob_headers = {"Authorization": f"Bearer {bob_token}"}
    backend.post("/api/tasks/enc_def456/claim", headers=bob_headers)

    # Alice tries to complete Bob's task
    resp = backend.patch("/api/tasks/102/update_completion_details",
                         headers=auth_headers,
                         json={"outcome": "completed", "weight": 20, "partner_id": 1})
    assert resp.status_code == 403


def test_complete_nonexistent_task(backend, auth_headers):
    resp = backend.patch("/api/tasks/9999/update_completion_details",
                         headers=auth_headers, json={"outcome": "completed", "weight": 10, "partner_id": 1})
    assert resp.status_code == 404
