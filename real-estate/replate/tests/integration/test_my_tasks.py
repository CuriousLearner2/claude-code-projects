import pytest


def _claim(backend, auth_headers, encrypted_id="enc_abc123"):
    return backend.post(f"/api/tasks/{encrypted_id}/claim", headers=auth_headers)


def test_my_tasks_empty_initially(backend, auth_headers):
    resp = backend.get("/api/my_tasks", headers=auth_headers)
    assert resp.get_json() == []


def test_claimed_task_appears_in_my_tasks(backend, auth_headers):
    _claim(backend, auth_headers)
    resp = backend.get("/api/my_tasks", headers=auth_headers)
    tasks = resp.get_json()
    assert len(tasks) == 1
    assert tasks[0]["encrypted_id"] == "enc_abc123"


def test_multiple_claimed_tasks(backend, auth_headers):
    _claim(backend, auth_headers, "enc_abc123")
    _claim(backend, auth_headers, "enc_def456")
    tasks = backend.get("/api/my_tasks", headers=auth_headers).get_json()
    assert len(tasks) == 2


def test_completed_task_in_my_tasks(backend, auth_headers):
    _claim(backend, auth_headers)
    backend.patch("/api/tasks/101/update_completion_details", headers=auth_headers, json={
        "outcome": "completed", "weight": 42.5, "partner_id": 1
    })
    tasks = backend.get("/api/my_tasks", headers=auth_headers).get_json()
    assert tasks[0]["status"] == "completed"


def test_missed_task_in_my_tasks(backend, auth_headers):
    _claim(backend, auth_headers)
    backend.patch("/api/tasks/101/update_completion_details", headers=auth_headers, json={
        "outcome": "missed"
    })
    tasks = backend.get("/api/my_tasks", headers=auth_headers).get_json()
    assert tasks[0]["status"] == "missed"
