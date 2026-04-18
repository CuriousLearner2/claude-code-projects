import os
from typing import Any, Optional

import requests as _requests
from requests.exceptions import ConnectionError as _ConnError, Timeout as _Timeout

BASE_URL = os.getenv("REPLATE_API_URL", "http://localhost:5001")
TIMEOUT = 30


# ── Exceptions ─────────────────────────────────────────────────────────────────

class ApiError(Exception):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


class AuthError(ApiError):
    pass


class NotFoundError(ApiError):
    pass


class ConflictError(ApiError):
    pass


class ValidationError(ApiError):
    def __init__(self, message: str, errors: Optional[list] = None):
        super().__init__(message)
        self.errors = errors or [message]


# ── Sanitization ───────────────────────────────────────────────────────────────

def _sanitize(obj: Any) -> Any:
    """Strip keys that could pollute object prototypes."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items() if not k.startswith("__")}
    if isinstance(obj, list):
        return [_sanitize(item) for item in obj]
    return obj


# ── Core request wrapper ───────────────────────────────────────────────────────

def request(method: str, path: str, token: Optional[str] = None, **kwargs) -> Any:
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = _requests.request(
            method,
            f"{BASE_URL}{path}",
            headers=headers,
            timeout=TIMEOUT,
            **kwargs,
        )
    except _ConnError:
        raise ApiError("Cannot connect to server. Is the backend running?")
    except _Timeout:
        raise ApiError("Request timed out. Please try again.")

    if resp.status_code == 204:
        return None

    try:
        data = resp.json()
    except ValueError:
        raise ApiError(f"Invalid response from server (status {resp.status_code})")

    data = _sanitize(data)

    if resp.status_code == 401:
        raise AuthError(data.get("error", "Authentication required"))
    if resp.status_code == 403:
        raise AuthError(data.get("error", "Access denied"))
    if resp.status_code == 404:
        raise NotFoundError(data.get("error", "Not found"))
    if resp.status_code == 409:
        raise ConflictError(data.get("error", "Conflict"))
    if resp.status_code == 422:
        raw = data.get("errors") or data.get("error") or "Validation failed"
        errors = raw if isinstance(raw, list) else [raw]
        raise ValidationError(errors[0], errors=errors)
    if not resp.ok:
        raise ApiError(
            data.get("error", f"Server error ({resp.status_code})"),
            status=resp.status_code,
        )

    return data


# ── Convenience methods ────────────────────────────────────────────────────────

def get(path: str, token: Optional[str] = None, **kwargs) -> Any:
    return request("GET", path, token=token, **kwargs)


def post(path: str, token: Optional[str] = None, **kwargs) -> Any:
    return request("POST", path, token=token, **kwargs)


def patch(path: str, token: Optional[str] = None, **kwargs) -> Any:
    return request("PATCH", path, token=token, **kwargs)
