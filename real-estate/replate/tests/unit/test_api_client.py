from unittest import mock

import pytest
import requests as real_requests

import client.api as api


def _mock_response(status: int, json_data=None, raise_for=None):
    resp = mock.MagicMock()
    resp.status_code = status
    resp.ok = 200 <= status < 300
    resp.json.return_value = json_data or {}
    return resp


@pytest.fixture(autouse=True)
def patch_requests(monkeypatch):
    monkeypatch.setattr(api, "_requests", mock.MagicMock())
    return api._requests


def test_successful_get(patch_requests):
    patch_requests.request.return_value = _mock_response(200, {"id": 1})
    result = api.get("/api/test")
    assert result == {"id": 1}


def test_204_returns_none(patch_requests):
    patch_requests.request.return_value = _mock_response(204)
    assert api.get("/api/test") is None


def test_401_raises_auth_error(patch_requests):
    patch_requests.request.return_value = _mock_response(401, {"error": "Unauthorized"})
    with pytest.raises(api.AuthError):
        api.get("/api/test")


def test_404_raises_not_found(patch_requests):
    patch_requests.request.return_value = _mock_response(404, {"error": "Not found"})
    with pytest.raises(api.NotFoundError):
        api.get("/api/test")


def test_409_raises_conflict(patch_requests):
    patch_requests.request.return_value = _mock_response(409, {"error": "Already claimed"})
    with pytest.raises(api.ConflictError):
        api.get("/api/test")


def test_422_raises_validation_error_with_errors_list(patch_requests):
    patch_requests.request.return_value = _mock_response(
        422, {"errors": ["Email taken", "Phone invalid"]}
    )
    with pytest.raises(api.ValidationError) as exc_info:
        api.post("/api/drivers")
    assert exc_info.value.errors == ["Email taken", "Phone invalid"]


def test_422_raises_validation_error_with_single_error(patch_requests):
    patch_requests.request.return_value = _mock_response(422, {"error": "Bad data"})
    with pytest.raises(api.ValidationError) as exc_info:
        api.post("/api/drivers")
    assert "Bad data" in exc_info.value.errors


def test_connection_error(patch_requests):
    patch_requests.request.side_effect = real_requests.exceptions.ConnectionError()
    with pytest.raises(api.ApiError, match="Cannot connect"):
        api.get("/api/test")


def test_timeout_error(patch_requests):
    patch_requests.request.side_effect = real_requests.exceptions.Timeout()
    with pytest.raises(api.ApiError, match="timed out"):
        api.get("/api/test")


def test_token_sent_in_header(patch_requests):
    patch_requests.request.return_value = _mock_response(200, {})
    api.get("/api/test", token="mytoken")
    _, kwargs = patch_requests.request.call_args
    assert kwargs["headers"]["Authorization"] == "Bearer mytoken"


def test_prototype_pollution_sanitized(patch_requests):
    patch_requests.request.return_value = _mock_response(
        200, {"__proto__": {"admin": True}, "name": "Alice"}
    )
    result = api.get("/api/test")
    assert "__proto__" not in result
    assert result["name"] == "Alice"
