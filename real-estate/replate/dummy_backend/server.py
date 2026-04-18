import copy
import math
import os
from functools import wraps

from flask import Flask, g, jsonify, request
from werkzeug.security import check_password_hash, generate_password_hash

from dummy_backend.store import store


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in kilometres between two (lat, lon) points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

app = Flask(__name__)
app.config["TESTING"] = False


# ── Auth middleware ────────────────────────────────────────────────────────────

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401
        token = auth[7:]
        driver_id = store.get_driver_id_for_token(token)
        if not driver_id:
            return jsonify({"error": "Unauthorized"}), 401
        g.driver_id = driver_id
        return f(*args, **kwargs)
    return decorated


def _public_driver(driver: dict) -> dict:
    return {k: v for k, v in driver.items() if k != "password_hash"}


# ── Auth ───────────────────────────────────────────────────────────────────────

@app.post("/api/drivers/login")
def login():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    password = body.get("password") or ""

    driver = store.get_driver_by_email(email)
    if not driver or not check_password_hash(driver["password_hash"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    token = store.issue_token(driver["id"])
    return jsonify({"driver": _public_driver(driver), "token": token})


@app.post("/api/drivers")
def signup():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()

    if store.get_driver_by_email(email):
        return jsonify({"errors": ["Email has already been taken"]}), 422

    driver = store.create_driver({
        "email": email,
        "password_hash": generate_password_hash(body.get("password", "")),
        "first_name": (body.get("first_name") or "").strip(),
        "last_name": (body.get("last_name") or "").strip(),
        "phone": (body.get("phone") or "").strip(),
    })
    token = store.issue_token(driver["id"])
    return jsonify({"driver": _public_driver(driver), "token": token}), 201


@app.post("/api/drivers/password")
def request_password_reset():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    if not store.get_driver_by_email(email):
        return jsonify({"error": "No account found for that email"}), 404
    token = store.issue_reset_token(email)
    return jsonify({"message": "Reset token issued", "reset_token": token})


@app.patch("/api/drivers/password")
def reset_password():
    body = request.get_json(silent=True) or {}
    email = (body.get("email") or "").strip().lower()
    token = body.get("reset_token") or ""
    new_password = body.get("password") or ""

    if not store.consume_reset_token(email, token):
        return jsonify({"errors": ["Invalid or expired reset token"]}), 422

    driver = store.get_driver_by_email(email)
    store.update_driver(driver["id"], {"password_hash": generate_password_hash(new_password)})
    return jsonify({"message": "Password updated"})


# ── Driver profile ─────────────────────────────────────────────────────────────

@app.get("/api/drivers/<int:driver_id>")
@require_auth
def get_driver(driver_id):
    if driver_id != g.driver_id:
        return jsonify({"error": "Forbidden"}), 403
    driver = store.get_driver_by_id(driver_id)
    if not driver:
        return jsonify({"error": "Not found"}), 404
    return jsonify(_public_driver(driver))


@app.patch("/api/drivers/<int:driver_id>")
@require_auth
def update_driver(driver_id):
    if driver_id != g.driver_id:
        return jsonify({"error": "Forbidden"}), 403
    body = request.get_json(silent=True) or {}
    allowed = {"first_name", "last_name", "phone", "partner_id", "lat", "lon"}
    updates = {k: v for k, v in body.items() if k in allowed}
    driver = store.update_driver(driver_id, updates)
    if not driver:
        return jsonify({"error": "Not found"}), 404
    return jsonify(_public_driver(driver))


# ── Partners ───────────────────────────────────────────────────────────────────

@app.get("/api/partners")
@require_auth
def get_partners():
    return jsonify(store.partners)


# ── Tasks ──────────────────────────────────────────────────────────────────────

@app.get("/api/tasks")
@require_auth
def list_tasks():
    date = request.args.get("date", "")
    if not date:
        return jsonify({"error": "date parameter required"}), 400

    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)

    tasks = copy.deepcopy(store.get_available_tasks_for_date(date))

    if lat is not None and lon is not None:
        for task in tasks:
            if task.get("lat") is not None and task.get("lon") is not None:
                task["distance_km"] = round(haversine_km(lat, lon, task["lat"], task["lon"]), 2)
        tasks.sort(key=lambda t: t.get("distance_km", float("inf")))

    return jsonify(tasks)


@app.get("/api/tasks/<encrypted_id>")
@require_auth
def get_task(encrypted_id):
    task = store.get_task_by_encrypted_id(encrypted_id)
    if not task:
        return jsonify({"error": "Not found"}), 404
    return jsonify(task)


@app.post("/api/tasks/<encrypted_id>/claim")
@require_auth
def claim_task(encrypted_id):
    task = store.get_task_by_encrypted_id(encrypted_id)
    if not task:
        return jsonify({"error": "Not found"}), 404
    if task["status"] != "available":
        return jsonify({"error": "Task already claimed"}), 409
    task["status"] = "claimed"
    task["driver_id"] = g.driver_id
    return jsonify(task)


@app.get("/api/my_tasks")
@require_auth
def my_tasks():
    tasks = store.get_tasks_for_driver(g.driver_id)
    return jsonify(tasks)


@app.patch("/api/tasks/<int:task_id>/update_completion_details")
@require_auth
def complete_task(task_id):
    task = store.get_task_by_id(task_id)
    if not task:
        return jsonify({"error": "Not found"}), 404
    if task["driver_id"] != g.driver_id:
        return jsonify({"error": "Forbidden"}), 403
    if task["status"] in ("completed", "missed"):
        return jsonify({"error": "Task already finalized"}), 409

    body = request.get_json(silent=True) or {}
    outcome = body.get("outcome", "completed")

    if outcome == "missed":
        task["status"] = "missed"
    else:
        task["status"] = "completed"
        task["completion_details"] = {
            "weight": body.get("weight"),
            "partner_id": body.get("partner_id"),
            "photo_url": body.get("photo_url"),
        }
    return jsonify(task)


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return jsonify({"status": "ok"})


if __name__ == "__main__":
    port = int(os.getenv("REPLATE_PORT", 5001))
    app.run(port=port, debug=False)
