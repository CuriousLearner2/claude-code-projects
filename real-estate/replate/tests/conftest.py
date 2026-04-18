import pytest

from dummy_backend.server import app as flask_app
from dummy_backend.store import store


@pytest.fixture(autouse=True)
def reset_store():
    """Reset in-memory store before every test."""
    store.reset()
    yield
    store.reset()


@pytest.fixture
def app():
    flask_app.config["TESTING"] = True
    return flask_app


@pytest.fixture
def backend(app):
    return app.test_client()


@pytest.fixture
def alice_token(backend):
    """Return an auth token for the pre-seeded driver Alice."""
    resp = backend.post("/api/drivers/login", json={
        "email": "alice@example.com",
        "password": "Password1",
    })
    return resp.get_json()["token"]


@pytest.fixture
def auth_headers(alice_token):
    return {"Authorization": f"Bearer {alice_token}"}
