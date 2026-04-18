import pytest

from client.validation import (
    validate_email,
    validate_name,
    validate_password,
    validate_phone,
    validate_weight,
)


# ── Email ──────────────────────────────────────────────────────────────────────

def test_valid_email():
    assert validate_email("alice@example.com") == "alice@example.com"


def test_email_normalised_to_lowercase():
    assert validate_email("Alice@Example.COM") == "alice@example.com"


def test_email_invalid_format():
    with pytest.raises(ValueError, match="Invalid email"):
        validate_email("not-an-email")


def test_email_empty():
    with pytest.raises(ValueError, match="required"):
        validate_email("")


def test_email_too_long():
    with pytest.raises(ValueError, match="254"):
        validate_email("a" * 250 + "@x.com")


# ── Password ───────────────────────────────────────────────────────────────────

def test_valid_password():
    assert validate_password("Password1") == "Password1"


def test_password_too_short():
    with pytest.raises(ValueError, match="8 characters"):
        validate_password("Short1")


def test_password_no_uppercase():
    with pytest.raises(ValueError, match="uppercase"):
        validate_password("alllowercase1")


def test_password_empty():
    with pytest.raises(ValueError, match="required"):
        validate_password("")


def test_password_too_long():
    with pytest.raises(ValueError, match="128"):
        validate_password("A" + "a" * 128)


def test_password_custom_label():
    with pytest.raises(ValueError, match="New password"):
        validate_password("short", label="New password")


# ── Phone ──────────────────────────────────────────────────────────────────────

def test_valid_phone_10_digits():
    assert validate_phone("4155550001") == "4155550001"


def test_valid_phone_strips_formatting():
    assert validate_phone("(415) 555-0001") == "4155550001"


def test_phone_too_short():
    with pytest.raises(ValueError, match="10 digits"):
        validate_phone("415555000")


def test_phone_too_long():
    with pytest.raises(ValueError, match="15 digits"):
        validate_phone("4155550001234567")


def test_phone_empty():
    with pytest.raises(ValueError, match="required"):
        validate_phone("")


# ── Name ───────────────────────────────────────────────────────────────────────

def test_valid_name():
    assert validate_name("Alice") == "Alice"


def test_name_strips_whitespace():
    assert validate_name("  Alice  ") == "Alice"


def test_name_empty():
    with pytest.raises(ValueError, match="required"):
        validate_name("")


def test_name_too_long():
    with pytest.raises(ValueError, match="50"):
        validate_name("A" * 51)


def test_name_custom_field_label():
    with pytest.raises(ValueError, match="First name"):
        validate_name("", field="First name")


# ── Weight ─────────────────────────────────────────────────────────────────────

def test_valid_weight():
    assert validate_weight("42.5") == 42.5


def test_weight_integer_string():
    assert validate_weight("50") == 50.0


def test_weight_non_numeric():
    with pytest.raises(ValueError, match="number"):
        validate_weight("forty")


def test_weight_negative():
    with pytest.raises(ValueError, match="greater than 0"):
        validate_weight("-1")


def test_weight_zero():
    with pytest.raises(ValueError, match="greater than 0"):
        validate_weight("0")
