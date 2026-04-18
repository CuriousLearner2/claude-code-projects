import copy
import secrets

from dummy_backend.fixtures import DRIVERS, PARTNERS, TASKS


class Store:
    def reset(self):
        self.partners = copy.deepcopy(PARTNERS)
        self.tasks = copy.deepcopy(TASKS)
        self.drivers = copy.deepcopy(DRIVERS)
        self.tokens: dict[str, int] = {}           # token → driver_id
        self.reset_tokens: dict[str, str] = {}     # email → reset_token
        self._next_driver_id = max(d["id"] for d in self.drivers) + 1

    def __init__(self):
        self.reset()

    # ── Drivers ──────────────────────────────────────────────────────────────

    def get_driver_by_email(self, email: str):
        return next((d for d in self.drivers if d["email"] == email), None)

    def get_driver_by_id(self, driver_id: int):
        return next((d for d in self.drivers if d["id"] == driver_id), None)

    def create_driver(self, data: dict) -> dict:
        driver = {**data, "id": self._next_driver_id, "partner_id": None}
        self._next_driver_id += 1
        self.drivers.append(driver)
        return driver

    def update_driver(self, driver_id: int, updates: dict):
        driver = self.get_driver_by_id(driver_id)
        if driver:
            driver.update(updates)
        return driver

    # ── Auth tokens ──────────────────────────────────────────────────────────

    def issue_token(self, driver_id: int) -> str:
        token = secrets.token_hex(32)
        self.tokens[token] = driver_id
        return token

    def revoke_token(self, token: str):
        self.tokens.pop(token, None)

    def get_driver_id_for_token(self, token: str):
        return self.tokens.get(token)

    # ── Password reset ────────────────────────────────────────────────────────

    def issue_reset_token(self, email: str) -> str:
        token = secrets.token_hex(16)
        self.reset_tokens[email] = token
        return token

    def consume_reset_token(self, email: str, token: str) -> bool:
        stored = self.reset_tokens.get(email)
        if stored and secrets.compare_digest(stored, token):
            del self.reset_tokens[email]
            return True
        return False

    # ── Tasks ────────────────────────────────────────────────────────────────

    def get_task_by_encrypted_id(self, encrypted_id: str):
        return next((t for t in self.tasks if t["encrypted_id"] == encrypted_id), None)

    def get_task_by_id(self, task_id: int):
        return next((t for t in self.tasks if t["id"] == task_id), None)

    def get_available_tasks_for_date(self, date: str) -> list:
        return [t for t in self.tasks if t["date"] == date and t["status"] == "available"]

    def get_tasks_for_driver(self, driver_id: int) -> list:
        return [t for t in self.tasks if t["driver_id"] == driver_id]


store = Store()
