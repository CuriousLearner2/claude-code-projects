#!/usr/bin/env python3
"""Replate CLI — food rescue volunteer driver app."""

import os
import sys
import threading
import time

import requests

# ── Backend startup ────────────────────────────────────────────────────────────

def _start_backend():
    """Start the dummy Flask backend in a background daemon thread."""
    os.environ.setdefault("REPLATE_API_URL", "http://localhost:5001")
    from dummy_backend.server import app
    thread = threading.Thread(
        target=lambda: app.run(port=5001, debug=False, use_reloader=False),
        daemon=True,
    )
    thread.start()


def _wait_for_backend(retries: int = 10, delay: float = 0.3) -> bool:
    url = os.getenv("REPLATE_API_URL", "http://localhost:5001")
    for _ in range(retries):
        try:
            requests.get(f"{url}/health", timeout=1)
            return True
        except Exception:
            time.sleep(delay)
    return False


# ── App ────────────────────────────────────────────────────────────────────────

def main() -> int:
    # Allow connecting to an external backend by setting REPLATE_API_URL
    external = os.getenv("REPLATE_API_URL")
    if not external:
        _start_backend()
        if not _wait_for_backend():
            print("Error: backend failed to start.")
            return 1

    from client.auth import run_auth_menu, logout
    from client.onboarding import run_onboarding
    from client.available_tasks import run_available_tasks
    from client.my_tasks import run_my_tasks
    from client.account import run_account
    from client.session import load_session
    from client import display as d

    # Load or create session
    session = load_session()
    if not session:
        session = run_auth_menu()
        if not session:
            return 0

    # Onboarding gate
    if not session.get("partner_id"):
        session = run_onboarding(session)
        if not session:
            return 0

    # Main navigation loop
    while True:
        d.header("REPLATE — Main Menu")
        d.blank()
        d.info(f"Welcome, {session.get('first_name', 'Driver')}!")
        choice = d.menu(["Available Pick-ups", "My Tasks", "My Account"], back_label="Quit")

        if choice == "1":
            run_available_tasks(session)
        elif choice == "2":
            run_my_tasks(session)
        elif choice == "3":
            result = run_account(session)
            if result == "logout":
                break
        elif choice in ("b", "q", "quit"):
            break
        else:
            d.error("Invalid choice.")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n  Goodbye.")
        sys.exit(0)
