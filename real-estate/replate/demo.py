#!/usr/bin/env python3
"""
Replate CLI Demo
Walks through major use cases with mocked inputs.
Each use case shows the actual terminal output the driver would see.
"""

import os, sys, threading, time
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ── Start dummy backend ────────────────────────────────────────────────────────

def _start_backend():
    import requests as _r
    try:
        _r.get("http://localhost:5001/health", timeout=0.5)
        return
    except Exception:
        pass
    from dummy_backend.server import app
    threading.Thread(
        target=lambda: app.run(port=5001, debug=False, use_reloader=False),
        daemon=True,
    ).start()
    time.sleep(1.0)

_start_backend()

from dummy_backend.store import store
store.reset()

import client.api as api
from client.auth import run_login, run_signup
from client.onboarding import run_onboarding
from client.available_tasks import run_available_tasks
from client.my_tasks import run_my_tasks
from client.donation import run_donation
from client.account import run_account

# ── Helpers ────────────────────────────────────────────────────────────────────

class FakeInputs:
    """Replaces input() — prints the prompt + chosen answer so output is visible."""
    def __init__(self, responses):
        self._iter = iter(responses)

    def __call__(self, prompt=""):
        val = next(self._iter, "b")          # default 'b' safely exits any menu
        sys.stdout.write(prompt + val + "\n")
        sys.stdout.flush()
        return val


def run_with(fn, inputs, passwords=None):
    fake_input = FakeInputs(inputs)
    pw_iter = iter(passwords or [])

    def fake_getpass(prompt=""):
        val = next(pw_iter, "")
        sys.stdout.write(prompt + "****\n")
        sys.stdout.flush()
        return val

    with mock.patch("builtins.input", fake_input), \
         mock.patch("getpass.getpass", fake_getpass):
        return fn()


def banner(n, title, expected):
    sep = "▓" * 62
    print(f"\n{sep}")
    print(f"  USE CASE {n}: {title}")
    print(f"  Expected : {expected}")
    print(sep)

def result(label):
    print(f"\n  ──► RESULT: {label}")
    input("\n  Press Enter to continue to next use case...")


# ══════════════════════════════════════════════════════════════════════════════
#  DEMO
# ══════════════════════════════════════════════════════════════════════════════

# ── UC 1: Failed login ─────────────────────────────────────────────────────────
banner(1, "Login — Wrong Password",
       "Error message shown; no session returned")

session = run_with(run_login,
    inputs=["alice@example.com", "n"],
    passwords=["wrongpassword"])

result("No session" if not session else "Session returned (UNEXPECTED)")


# ── UC 2: Successful login ─────────────────────────────────────────────────────
banner(2, "Login — Valid Credentials (alice@example.com / Password1)",
       "Session returned; partner_id already set (skips onboarding)")

session = run_with(run_login,
    inputs=["alice@example.com", "n"],
    passwords=["Password1"])

if session:
    result(f"Logged in as {session['email']}, partner_id={session['partner_id']}, token=SET")
else:
    result("Login failed (UNEXPECTED)")


# ── UC 3: Browse available tasks ───────────────────────────────────────────────
banner(3, "Browse Available Pick-ups — Today",
       "2 tasks listed (Google Cafeteria, LinkedIn Café); back to menu")

run_with(lambda: run_available_tasks(session),
    inputs=["b"])

result("Task list shown; user pressed Back")


# ── UC 4: View task detail ─────────────────────────────────────────────────────
banner(4, "View Pick-up Detail",
       "Full details shown: address, contact, food desc, access instructions")

run_with(lambda: run_available_tasks(session),
    inputs=["2",   # View pick-up details
            "1",   # Select first task (Google Cafeteria)
            "b",   # Back from detail (don't claim)
            "b"])  # Back to main menu

result("Full task detail shown; user chose not to claim")


# ── UC 5: Claim a task ─────────────────────────────────────────────────────────
banner(5, "Claim a Pick-up",
       "Google Cafeteria claimed; confirmation shown; task removed from available list")

run_with(lambda: run_available_tasks(session),
    inputs=["2",   # View pick-up details
            "1",   # Select first task (Google Cafeteria)
            "1",   # Claim this pick-up
            "b"])  # Back to main menu

# Verify via API
available = api.get("/api/tasks", token=session["token"], params={"date": "2026-04-18"})
claimed   = api.get("/api/my_tasks", token=session["token"])
result(f"Available today: {len(available)} task(s) remaining | My Tasks: {len(claimed)} claimed")


# ── UC 6: View My Tasks — In Progress ─────────────────────────────────────────
banner(6, "My Tasks — In Progress",
       "Claimed task (Google Cafeteria) appears in In Progress list")

run_with(lambda: run_my_tasks(session),
    inputs=["b"])  # View, then back

result("In Progress task shown")


# ── UC 7: Complete a task ──────────────────────────────────────────────────────
banner(7, "Complete a Pick-up — Log Donation",
       "Weight 45.5 lbs, SF-Marin Food Bank; task marked completed; success message")

my = api.get("/api/my_tasks", token=session["token"])
in_progress = [t for t in my if t["status"] == "claimed"]

if in_progress:
    run_with(lambda: run_donation(in_progress[0], session),
        inputs=["1",     # Complete this pick-up
                "45.5",  # Weight in lbs
                "1",     # Select first NPO (SF-Marin Food Bank)
                ""])     # No photo
    task_check = api.get(f"/api/tasks/{in_progress[0]['encrypted_id']}", token=session["token"])
    result(f"Task status={task_check['status']}, weight={task_check['completion_details']['weight']} lbs")
else:
    result("No in-progress tasks found (UNEXPECTED)")


# ── UC 8: My Tasks — History ───────────────────────────────────────────────────
banner(8, "My Tasks — History",
       "Completed task now in History view; In Progress is empty")

run_with(lambda: run_my_tasks(session),
    inputs=["1",   # Switch to History
            "b"])  # Back to main menu

result("History view shown with completed task")


# ── UC 9: Signup — New Driver ──────────────────────────────────────────────────
banner(9, "Signup — New Driver (bob@example.com)",
       "Account created; partner_id=None (will trigger onboarding)")

store.reset()  # Fresh state; all above state is cleared

bob_session = run_with(run_signup,
    inputs=["Bob", "Volunteer", "4085550042", "bob@example.com", "n"],
    passwords=["BobSecure1", "BobSecure1"])

if bob_session:
    result(f"Account: {bob_session['email']}, partner_id={bob_session['partner_id']}")
else:
    result("Signup failed (UNEXPECTED)")


# ── UC 10: Onboarding — Select NPO ────────────────────────────────────────────
banner(10, "Onboarding — Select NPO Partner",
        "Partner list shown; Glide Memorial Kitchen selected; partner_id saved")

if bob_session:
    bob_session = run_with(lambda: run_onboarding(bob_session),
        inputs=["",    # List all (no search filter)
                "2"])  # Select Glide Memorial Kitchen (index 2)

    if bob_session:
        result(f"partner_id={bob_session['partner_id']} ({bob_session.get('partner_name', 'Glide Memorial Kitchen')})")
    else:
        result("Onboarding failed (UNEXPECTED)")


# ── UC 11: View Account ────────────────────────────────────────────────────────
banner(11, "View Account",
        "Name, email, phone, and NPO name displayed")

if bob_session:
    run_with(lambda: run_account(bob_session),
        inputs=["b"])  # View then back

    result("Profile displayed with all fields")


# ── UC 12: Logout ──────────────────────────────────────────────────────────────
banner(12, "Logout",
        "Confirmation prompt; session cleared; success message shown")

if bob_session:
    run_with(lambda: run_account(bob_session),
        inputs=["1",   # Log out
                "y"])  # Confirm

    result("Session cleared; logged out")


# ── Done ───────────────────────────────────────────────────────────────────────
print()
print("═" * 62)
print("  ALL USE CASES COMPLETE")
print("═" * 62)
print()
