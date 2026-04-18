import client.api as api
from client import display as d
from client.session import save_session, update_session


def run_onboarding(session: dict) -> dict | None:
    d.header("REPLATE — Choose Your NPO Partner")
    d.blank()
    d.info("Select the nonprofit organization you'll be delivering to.")
    d.blank()

    try:
        partners = api.get("/api/partners", token=session["token"])
    except api.ApiError as e:
        d.error(str(e))
        return None

    if not partners:
        d.error("No NPO partners are currently available. Contact Replate staff.")
        return None

    while True:
        search = input("  Search (or press Enter to list all): ").strip().lower()
        filtered = [p for p in partners if search in p["name"].lower()] if search else partners

        if not filtered:
            d.info("No matches. Try a different term.")
            continue

        d.blank()
        names = [p["name"] for p in filtered]
        idx = d.choose("Select your NPO", names)
        if idx is None:
            return None

        chosen = filtered[idx]
        try:
            updated = api.patch(
                f"/api/drivers/{session['id']}",
                token=session["token"],
                json={"partner_id": chosen["id"]},
            )
        except api.ApiError as e:
            d.error(str(e))
            return None

        session = {**session, **updated, "token": session["token"]}
        save_session(session)
        d.success(f"Partner set to: {chosen['name']}")
        return session
