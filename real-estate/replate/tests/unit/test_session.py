import json
import os
import tempfile
from pathlib import Path
from unittest import mock

import pytest

import client.session as session_mod

SAMPLE_SESSION = {
    "id": 1,
    "email": "alice@example.com",
    "first_name": "Alice",
    "last_name": "Driver",
    "phone": "4155550001",
    "partner_id": 1,
    "token": "abc123",
}


@pytest.fixture(autouse=True)
def tmp_session_dir(tmp_path):
    """Redirect session file to a temp directory for every test."""
    session_file = tmp_path / "session.json"
    with mock.patch.object(session_mod, "SESSION_DIR", tmp_path), \
         mock.patch.object(session_mod, "SESSION_FILE", session_file):
        yield session_file


def test_save_and_load():
    session_mod.save_session(SAMPLE_SESSION)
    loaded = session_mod.load_session()
    assert loaded == SAMPLE_SESSION


def test_load_no_file():
    assert session_mod.load_session() is None


def test_load_corrupt_file(tmp_session_dir):
    tmp_session_dir.write_text("not json")
    assert session_mod.load_session() is None


def test_clear_session():
    session_mod.save_session(SAMPLE_SESSION)
    session_mod.clear_session()
    assert session_mod.load_session() is None


def test_load_missing_required_field(tmp_session_dir):
    incomplete = {k: v for k, v in SAMPLE_SESSION.items() if k != "token"}
    tmp_session_dir.write_text(json.dumps(incomplete))
    assert session_mod.load_session() is None


def test_update_session():
    session_mod.save_session(SAMPLE_SESSION)
    updated = session_mod.update_session({"partner_id": 2})
    assert updated["partner_id"] == 2
    assert session_mod.load_session()["partner_id"] == 2


def test_update_session_no_existing():
    result = session_mod.update_session({"partner_id": 2})
    assert result is None


def test_session_file_permissions(tmp_session_dir):
    session_mod.save_session(SAMPLE_SESSION)
    mode = oct(tmp_session_dir.stat().st_mode)[-3:]
    assert mode == "600"
