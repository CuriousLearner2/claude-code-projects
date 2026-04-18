import os

import client.api as api
from client import display as d
from client.validation import validate_weight


def _upload_photo(path: str) -> str | None:
    """Validate the local path and return a mock storage URL."""
    path = path.strip()
    if not path:
        return None
    if not os.path.isfile(path):
        raise ValueError(f"File not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"):
        raise ValueError("Unsupported file type. Use JPG, PNG, or HEIC.")
    # Dummy backend: return a mock URL instead of actually uploading
    filename = os.path.basename(path)
    return f"https://storage.replate.org/mock/{filename}"


def run_donation(task: dict, session: dict):
    d.header(f"Log Completion — {task['donor_name']}")
    d.blank()
    d.info(f"Date:  {d.fmt_date(task['date'])}")
    d.info(f"Time:  {d.fmt_time_range(task.get('start_time'), task.get('end_time'))}")
    d.blank()

    choice = d.menu(["Complete this pick-up", "Mark as missed"], back_label="Back")

    if choice == "b":
        return

    if choice == "2":
        if d.confirm("Mark this pick-up as missed?"):
            _submit(task, session, outcome="missed")
        return

    if choice != "1":
        d.error("Invalid choice.")
        return

    # Completion flow
    d.blank()
    d.info("Enter donation details:")
    d.blank()

    # Weight
    try:
        weight_str = input("  Donation weight (lbs): ").strip()
        weight = validate_weight(weight_str)
    except (ValueError, KeyboardInterrupt, EOFError) as e:
        d.error(str(e) if isinstance(e, ValueError) else "Cancelled.")
        return

    # NPO selection
    try:
        partners = api.get("/api/partners", token=session["token"])
    except api.ApiError as e:
        d.error(str(e))
        return

    d.blank()
    d.info("Recipient NPO:")
    names = [p["name"] for p in partners]
    idx = d.choose("Select NPO", names)
    if idx is None:
        return
    chosen_partner = partners[idx]

    # Photo (optional)
    d.blank()
    try:
        photo_path = input("  Photo path (optional, press Enter to skip): ").strip()
        photo_url = _upload_photo(photo_path) if photo_path else None
    except ValueError as e:
        d.error(str(e))
        return

    _submit(task, session, outcome="completed", weight=weight,
            partner_id=chosen_partner["id"], photo_url=photo_url)


def _submit(task: dict, session: dict, outcome: str, **details):
    payload = {"outcome": outcome, **details}
    try:
        api.patch(
            f"/api/tasks/{task['id']}/update_completion_details",
            token=session["token"],
            json=payload,
        )
        if outcome == "missed":
            d.success("Pick-up marked as missed.")
        else:
            d.success("Pick-up logged as completed. Thank you!")
    except api.ConflictError:
        d.error("This task has already been finalized.")
    except api.ApiError as e:
        d.error(str(e))
