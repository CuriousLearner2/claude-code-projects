import json
import os
from pathlib import Path
from typing import Optional

SESSION_DIR = Path.home() / ".replate"
SESSION_FILE = SESSION_DIR / "session.json"

REQUIRED_FIELDS = {"id", "email", "first_name", "last_name", "phone", "token"}


def load_session() -> Optional[dict]:
    if not SESSION_FILE.exists():
        return None
    try:
        data = json.loads(SESSION_FILE.read_text())
        if not isinstance(data, dict) or not REQUIRED_FIELDS.issubset(data):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def save_session(session: dict):
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(json.dumps(session))
    SESSION_FILE.chmod(0o600)


def clear_session():
    try:
        SESSION_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def update_session(updates: dict) -> Optional[dict]:
    session = load_session()
    if session is None:
        return None
    session.update(updates)
    save_session(session)
    return session
