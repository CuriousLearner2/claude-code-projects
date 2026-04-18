import getpass

import client.api as api
from client import display as d
from client.session import clear_session, save_session
from client.validation import (
    validate_email,
    validate_name,
    validate_password,
    validate_phone,
)


def _make_session(driver: dict, token: str, persist: bool) -> dict:
    session = {**driver, "token": token}
    if persist:
        save_session(session)
    return session


# ── Login ──────────────────────────────────────────────────────────────────────

def run_login() -> dict | None:
    d.header("REPLATE — Log In")
    try:
        email = input("  Email: ").strip()
        password = getpass.getpass("  Password: ")
    except (KeyboardInterrupt, EOFError):
        return None

    try:
        validate_email(email)
    except ValueError as e:
        d.error(str(e))
        return None

    try:
        resp = api.post("/api/drivers/login", json={"email": email, "password": password})
    except api.AuthError:
        d.error("Invalid email or password.")
        return None
    except api.ApiError as e:
        d.error(str(e))
        return None

    persist = d.confirm("Stay signed in?")
    return _make_session(resp["driver"], resp["token"], persist)


# ── Signup ─────────────────────────────────────────────────────────────────────

def run_signup() -> dict | None:
    d.header("REPLATE — Create Account")
    try:
        first = input("  First name: ")
        last = input("  Last name: ")
        phone = input("  Phone: ")
        email = input("  Email: ")
        password = getpass.getpass("  Password (min 8 chars, 1 uppercase): ")
        confirm = getpass.getpass("  Confirm password: ")
    except (KeyboardInterrupt, EOFError):
        return None

    try:
        first = validate_name(first, "First name")
        last = validate_name(last, "Last name")
        phone = validate_phone(phone)
        email = validate_email(email)
        validate_password(password)
        if password != confirm:
            raise ValueError("Passwords do not match")
    except ValueError as e:
        d.error(str(e))
        return None

    try:
        resp = api.post("/api/drivers", json={
            "first_name": first,
            "last_name": last,
            "phone": phone,
            "email": email,
            "password": password,
        })
    except api.ValidationError as e:
        d.error(e.errors[0])
        return None
    except api.ApiError as e:
        d.error(str(e))
        return None

    d.success("Account created!")
    persist = d.confirm("Stay signed in?")
    return _make_session(resp["driver"], resp["token"], persist)


# ── Forgot / reset password ────────────────────────────────────────────────────

def run_forgot_password():
    d.header("REPLATE — Reset Password")
    try:
        email = input("  Enter your account email: ").strip()
    except (KeyboardInterrupt, EOFError):
        return

    try:
        validate_email(email)
    except ValueError as e:
        d.error(str(e))
        return

    try:
        resp = api.post("/api/drivers/password", json={"email": email})
    except api.NotFoundError:
        d.error("No account found for that email.")
        return
    except api.ApiError as e:
        d.error(str(e))
        return

    # In production the token would arrive by email; for the CLI/dummy backend we show it
    reset_token = resp.get("reset_token", "")
    if reset_token:
        d.info(f"[DEV] Reset token: {reset_token}")

    try:
        token = input("  Enter reset token: ").strip()
        new_pass = getpass.getpass("  New password: ")
        confirm = getpass.getpass("  Confirm new password: ")
    except (KeyboardInterrupt, EOFError):
        return

    try:
        validate_password(new_pass, "New password")
        if new_pass != confirm:
            raise ValueError("Passwords do not match")
    except ValueError as e:
        d.error(str(e))
        return

    try:
        api.patch("/api/drivers/password", json={
            "email": email,
            "reset_token": token,
            "password": new_pass,
        })
    except api.ValidationError as e:
        d.error(e.errors[0])
        return
    except api.ApiError as e:
        d.error(str(e))
        return

    d.success("Password updated. Please log in with your new password.")


# ── Landing menu ───────────────────────────────────────────────────────────────

def run_auth_menu() -> dict | None:
    while True:
        d.header("REPLATE — Food Rescue Platform")
        d.blank()
        d.info("Connecting volunteer drivers with food donors.")
        choice = d.menu(["Log in", "Create account", "Forgot password"], back_label="Quit")

        if choice == "1":
            session = run_login()
            if session:
                return session
        elif choice == "2":
            session = run_signup()
            if session:
                return session
        elif choice == "3":
            run_forgot_password()
        elif choice in ("b", "q", "quit"):
            return None


# ── Logout ─────────────────────────────────────────────────────────────────────

def logout(token: str):
    clear_session()
    d.success("You have been logged out.")
