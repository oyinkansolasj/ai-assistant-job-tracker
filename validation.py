# validation.py - Rules that check user input before it is saved.
# Each function returns the cleaned value if it is valid,
# or raises a ValueError with a friendly message if it is not.

from datetime import date

# The only statuses an application is allowed to have
VALID_STATUSES = ["applied", "interviewing", "offer", "rejected", "withdrawn"]


def validate_company_name(company_name):
    """Company name must not be empty or just spaces."""
    if company_name is None or company_name.strip() == "":
        raise ValueError("Company name cannot be empty.")
    return company_name.strip()


def validate_status(status):
    """Status must be one of VALID_STATUSES (not case-sensitive)."""
    cleaned = (status or "").strip().lower()
    if cleaned not in VALID_STATUSES:
        raise ValueError(
            f"'{status}' is not a valid status. "
            f"Choose one of: {', '.join(VALID_STATUSES)}."
        )
    return cleaned


def validate_deadline(deadline):
    """Deadline must be a real date in YYYY-MM-DD format, and not in the past."""
    try:
        deadline_date = date.fromisoformat(str(deadline).strip())
    except ValueError:
        raise ValueError(f"'{deadline}' is not a valid date. Use YYYY-MM-DD, e.g. 2026-12-31.")

    if deadline_date < date.today():
        raise ValueError(f"Deadline {deadline_date} is in the past. Pick today or a future date.")
    return deadline_date.isoformat()


def validate_date_applied(date_applied):
    """Date applied must be in YYYY-MM-DD format, and not in the future."""
    try:
        applied = date.fromisoformat(str(date_applied).strip())
    except ValueError:
        raise ValueError(f"'{date_applied}' is not a valid date. Use YYYY-MM-DD, e.g. 2026-11-16.")

    if applied > date.today():
        raise ValueError(f"Date applied {applied} is in the future.")
    return applied.isoformat()


def validate_goal(goal):
    """An application goal must be a whole number, 0 or more."""
    try:
        number = int(str(goal).strip())
    except ValueError:
        raise ValueError(f"'{goal}' is not a whole number.")

    if number < 0:
        raise ValueError("Goal cannot be negative.")
    return number
