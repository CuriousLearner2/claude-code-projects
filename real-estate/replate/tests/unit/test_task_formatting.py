import pytest

from client.display import fmt_address, fmt_date, fmt_distance, fmt_time_range, fmt_tray


def test_time_range_standard():
    assert fmt_time_range("14:00", "15:30") == "2:00 PM – 3:30 PM"


def test_time_range_morning():
    assert fmt_time_range("09:00", "10:00") == "9:00 AM – 10:00 AM"


def test_time_range_no_start():
    assert fmt_time_range(None, "15:00") == "Time TBD"


def test_time_range_empty_start():
    assert fmt_time_range("", "15:00") == "Time TBD"


def test_address_full():
    addr = {"street": "1600 Amphitheatre Pkwy", "city": "Mountain View", "state": "CA", "zip": "94043"}
    assert fmt_address(addr) == "1600 Amphitheatre Pkwy, Mountain View, CA 94043"


def test_address_no_zip():
    addr = {"street": "222 2nd St", "city": "San Francisco", "state": "CA", "zip": ""}
    result = fmt_address(addr)
    assert "94" not in result
    assert "San Francisco" in result


def test_address_minimal():
    assert fmt_address({"street": "123 Main St"}) == "123 Main St"


def test_date_formatting():
    assert fmt_date("2026-04-18") == "Saturday, April 18"


def test_date_invalid():
    assert fmt_date("not-a-date") == "not-a-date"


def test_tray_plural():
    assert fmt_tray("full", 8) == "8 full trays"


def test_tray_singular():
    assert fmt_tray("half", 1) == "1 half tray"


# ── Distance formatting ────────────────────────────────────────────────────────

def test_distance_none_returns_empty():
    assert fmt_distance(None) == ""


def test_distance_sub_km_shown_in_metres():
    assert fmt_distance(0.3) == "300 m"


def test_distance_exactly_1km():
    assert fmt_distance(1.0) == "1.0 km"


def test_distance_multi_km():
    assert fmt_distance(1.5) == "1.5 km"


def test_distance_large():
    assert fmt_distance(48.3) == "48.3 km"


def test_distance_zero():
    assert fmt_distance(0.0) == "0 m"


def test_distance_just_under_1km():
    assert fmt_distance(0.999) == "999 m"
