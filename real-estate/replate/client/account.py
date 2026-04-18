import client.api as api
from client import display as d
from client.auth import logout


def run_account(session: dict) -> str | None:
    """Display profile and options. Returns 'logout' if user logs out."""
    d.header("REPLATE — My Account")
    d.blank()

    # Resolve partner name
    partner_name = "Not set"
    if session.get("partner_id"):
        try:
            partners = api.get("/api/partners", token=session["token"])
            match = next((p for p in partners if p["id"] == session["partner_id"]), None)
            if match:
                partner_name = match["name"]
        except api.ApiError:
            partner_name = f"Partner #{session['partner_id']}"

    d.info(f"Name:     {d.fmt_name(session)}")
    d.info(f"Email:    {session.get('email', '')}")
    d.info(f"Phone:    {session.get('phone', '')}")
    d.info(f"NPO:      {partner_name}")
    d.blank()

    choice = d.menu(["Log out"], back_label="Main menu")

    if choice == "1":
        if d.confirm("Are you sure you want to log out?"):
            logout(session.get("token", ""))
            return "logout"

    return None
