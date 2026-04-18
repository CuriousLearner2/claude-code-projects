import re

_EMAIL_RE = re.compile(
    r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
)


def validate_email(email: str) -> str:
    email = (email or "").strip()
    if not email:
        raise ValueError("Email is required")
    if len(email) > 254:
        raise ValueError("Email must be 254 characters or fewer")
    if not _EMAIL_RE.match(email):
        raise ValueError("Invalid email format")
    return email.lower()


def validate_password(password: str, label: str = "Password") -> str:
    password = password or ""
    if not password:
        raise ValueError(f"{label} is required")
    if len(password) < 8:
        raise ValueError(f"{label} must be at least 8 characters")
    if len(password) > 128:
        raise ValueError(f"{label} must be 128 characters or fewer")
    if not any(c.isupper() for c in password):
        raise ValueError(f"{label} must contain at least one uppercase letter")
    return password


def validate_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        raise ValueError("Phone number is required")
    if len(digits) < 10:
        raise ValueError("Phone number must be at least 10 digits")
    if len(digits) > 15:
        raise ValueError("Phone number must be 15 digits or fewer")
    return digits


def validate_name(name: str, field: str = "Name") -> str:
    name = (name or "").strip()
    if not name:
        raise ValueError(f"{field} is required")
    if len(name) > 50:
        raise ValueError(f"{field} must be 50 characters or fewer")
    return name


def validate_weight(weight_str: str) -> float:
    try:
        value = float(weight_str)
    except (ValueError, TypeError):
        raise ValueError("Weight must be a number")
    if value <= 0:
        raise ValueError("Weight must be greater than 0")
    return value
