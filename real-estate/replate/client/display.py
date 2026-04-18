from datetime import datetime

WIDTH = 60


# ── Layout ─────────────────────────────────────────────────────────────────────

def header(title: str):
    print()
    print("═" * WIDTH)
    print(f"  {title}")
    print("═" * WIDTH)


def divider():
    print("─" * WIDTH)


def blank():
    print()


def error(msg: str):
    print(f"\n  ✗ {msg}")


def success(msg: str):
    print(f"\n  ✓ {msg}")


def info(msg: str):
    print(f"  {msg}")


# ── Menus ──────────────────────────────────────────────────────────────────────

def menu(options: list[str], back_label: str = "Back") -> str:
    """Print a numbered list and return the user's raw input."""
    blank()
    for i, opt in enumerate(options, 1):
        print(f"  [{i}] {opt}")
    print(f"  [b] {back_label}")
    blank()
    return input("  Choice: ").strip().lower()


def choose(prompt_text: str, options: list[str]) -> int | None:
    """
    Show a numbered list, return the 0-based index of the chosen item
    or None if the user pressed 'b'.
    """
    for i, opt in enumerate(options, 1):
        print(f"  {i:>2}. {opt}")
    blank()
    raw = input(f"  {prompt_text} (or b to go back): ").strip().lower()
    if raw == "b":
        return None
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            return idx
        print("  Invalid selection.")
        return None
    except ValueError:
        print("  Invalid selection.")
        return None


def confirm(prompt_text: str) -> bool:
    raw = input(f"  {prompt_text} [y/n]: ").strip().lower()
    return raw in ("y", "yes")


# ── Formatting helpers ─────────────────────────────────────────────────────────

def fmt_time(t: str) -> str:
    """'14:00' → '2:00 PM'"""
    if not t:
        return "TBD"
    try:
        dt = datetime.strptime(t, "%H:%M")
        return dt.strftime("%-I:%M %p")
    except ValueError:
        return t


def fmt_time_range(start: str, end: str) -> str:
    if not start:
        return "Time TBD"
    return f"{fmt_time(start)} – {fmt_time(end)}"


def fmt_address(addr: dict) -> str:
    parts = [addr.get("street", "")]
    city_state = ", ".join(filter(None, [addr.get("city"), addr.get("state")]))
    if city_state:
        parts.append(city_state)
    if addr.get("zip"):
        parts[-1] = parts[-1] + " " + addr["zip"]
    return ", ".join(p for p in parts if p)


def fmt_date(date_str: str) -> str:
    """'2026-04-18' → 'Friday, April 18'"""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%A, %B %-d")
    except ValueError:
        return date_str


def fmt_tray(tray_type: str, tray_count: int) -> str:
    label = f"{tray_count} {tray_type} tray{'s' if tray_count != 1 else ''}"
    return label


def fmt_distance(km: float | None) -> str:
    if km is None:
        return ""
    if km < 1.0:
        return f"{km * 1000:.0f} m"
    return f"{km:.1f} km"


def fmt_name(driver: dict) -> str:
    return f"{driver.get('first_name', '')} {driver.get('last_name', '')}".strip()
