"""Input validation used by every form in all three apps.

Each function returns the cleaned value or raises ValidationError with a
friendly message that the apps show to the user.
"""
import re
from datetime import date, datetime


class ValidationError(ValueError):
    """A user-friendly message explaining what is wrong with the input."""


def clean_text(value, label, min_len=1, max_len=50, required=True) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        if required:
            raise ValidationError(f"{label} is required.")
        return ""
    if len(text) < min_len:
        raise ValidationError(f"{label} must have at least {min_len} characters.")
    if len(text) > max_len:
        raise ValidationError(f"{label} must be at most {max_len} characters.")
    return text


def validate_full_name(value) -> str:
    name = clean_text(value, "Full name", 2, 50)
    if not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]*", name):
        raise ValidationError("Full name can contain letters, spaces, dots, apostrophes and hyphens only.")
    return name


def validate_username(value) -> str:
    name = str(value or "").strip().lower()
    if not re.fullmatch(r"[a-z0-9_]{3,20}", name):
        raise ValidationError("Username must be 3-20 characters: letters, numbers or underscore.")
    return name


CID_LENGTH = 11         # Bhutanese Citizenship ID: 11 digits


def validate_cid(value, required=True) -> str:
    """CID: exactly 11 digits (spaces and dashes are ignored)."""
    text = re.sub(r"[\s-]", "", str(value or ""))
    if not text:
        if required:
            raise ValidationError("CID is required.")
        return ""
    if not text.isdigit() or len(text) != CID_LENGTH:
        raise ValidationError(f"CID must be exactly {CID_LENGTH} digits, e.g. 10805001234.")
    return text


PASSWORD_MIN = 6        # proposal presentation: "Password - at least 6 characters"


def validate_password(value) -> str:
    pw = str(value or "")
    if len(pw) < PASSWORD_MIN:
        raise ValidationError(f"Password must be at least {PASSWORD_MIN} characters.")
    if len(pw) > 64:
        raise ValidationError("Password must be at most 64 characters.")
    return pw


def validate_phone(value, required=False) -> str:
    """Bhutan numbers: 8 digits starting 17 / 77 (mobile) or 2-digit landline; +975 optional."""
    text = str(value or "").strip()
    if not text:
        if required:
            raise ValidationError("Phone number is required.")
        return ""
    digits = re.sub(r"[ \-()]", "", text)
    if digits.startswith("+975"):
        digits = digits[4:]
    elif digits.startswith("975"):
        digits = digits[3:]
    if not re.fullmatch(r"\d{6,8}", digits):
        raise ValidationError("Enter a valid phone number, e.g. +975 17 123456 or 17123456.")
    return text


def validate_email(value, required=False) -> str:
    text = str(value or "").strip()
    if not text:
        if required:
            raise ValidationError("Email is required.")
        return ""
    if not EMAIL_RE.fullmatch(text) or ".." in text or len(text) > 80:
        raise ValidationError("Email should look like name@gmail.com.")
    return text


# name@domain.tld  (letters/numbers . _ % + - before @, a real domain and a 2+ letter ending after it)
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")


# ============================================================ live (as-you-type) checks
def live_check(field, value, password="", taken=None) -> str:
    """Short message for ONE sign-up / log-in field, shown while the user is typing.

    Returns "" when the value is fine.  The messages are short so they fit under a text box.
    field: "name", "username", "email", "phone", "dob", "password", "confirm", "login_username"
    password: the first password (needed to check "confirm")
    taken: optional function(username) -> bool, to say instantly that a username is taken
    """
    value = "" if value is None else str(value)
    text = value.strip()
    if field == "name":
        if not text:
            return "Full name is required"
        if len(" ".join(text.split())) < 2:
            return "Name is too short"
        if len(text) > 50:
            return "At most 50 characters"
        if not re.fullmatch(r"[A-Za-z][A-Za-z .'\-]*", text):
            return "Use letters, spaces, . ' - only"
        return ""
    if field == "login_username":
        if not text:
            return "Enter your username or CID"
        if re.sub(r"[\s-]", "", text).isdigit():
            return "" if len(re.sub(r"[\s-]", "", text)) == CID_LENGTH else f"CID needs {CID_LENGTH} digits"
    if field in ("username", "login_username"):
        if not text:
            return "Username is required"
        if len(text) < 3:
            return "At least 3 characters"
        if len(text) > 20:
            return "At most 20 characters"
        if not re.fullmatch(r"[A-Za-z0-9_]+", text):
            return "Only letters, numbers and _"
        if field == "username" and taken and taken(text):
            return "This username is already taken"
        return ""
    if field == "cid":
        digits = re.sub(r"[\s-]", "", text)
        if not digits:
            return "CID is required"
        if not digits.isdigit():
            return "CID has numbers only"
        if len(digits) != CID_LENGTH:
            return f"CID needs {CID_LENGTH} digits ({len(digits)}/{CID_LENGTH})"
        if taken and taken(digits):
            return "This CID is already registered"
        return ""
    if field == "email":
        if not text:
            return ""                                   # email is optional
        if "@" not in text:
            return "Missing @  (e.g. name@gmail.com)"
        try:
            validate_email(text)
        except ValidationError:
            return "Email should look like name@gmail.com"
        return ""
    if field == "phone":
        try:
            validate_phone(text)
        except ValidationError:
            return "e.g. 17123456 or +975 17123456"
        return ""
    if field == "dob":
        if not text:
            return ""                                   # date of birth is optional
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return "Use YYYY-MM-DD, e.g. 1999-11-23"
        try:
            validate_date(text, "Date", allow_future=False)
        except ValidationError as err:
            return "Date can't be in the future" if "future" in str(err) else "Not a real date"
        return ""
    if field == "password":
        if not value:
            return "Password is required"
        if len(value) < PASSWORD_MIN:
            return f"At least {PASSWORD_MIN} characters ({len(value)}/{PASSWORD_MIN})"
        if len(value) > 64:
            return "At most 64 characters"
        return ""
    if field == "confirm":
        if not value:
            return "Please type the password again"
        return "" if value == password else "Passwords do not match"
    return ""


def validate_date(value, label="Date", required=True, allow_future=True) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        d = value
    else:
        text = str(value or "").strip()
        if not text:
            if required:
                raise ValidationError(f"{label} is required.")
            return ""
        d = None
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
            try:
                d = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue
        if d is None:
            raise ValidationError(f"{label} must look like 2026-10-31 (YYYY-MM-DD).")
    if not allow_future and d > date.today():
        raise ValidationError(f"{label} cannot be in the future.")
    if d.year < 1900:
        raise ValidationError(f"{label} is not a valid date.")
    return d.isoformat()


def parse_time(text):
    """Try the three accepted formats in turn; return 'HH:MM' or None.
         %H:%M     e.g. 20:15 or 08:30
         %I:%M %p  e.g. 8:30 AM
         %I:%M%p   e.g. 8:30AM"""
    text = " ".join(str(text or "").strip().upper().split())
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p"):
        try:
            return datetime.strptime(text, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return None


def time_label(hhmm) -> str:
    """'08:30' -> '8:30 AM', '20:15' -> '8:15 PM' (how times are SHOWN; they are saved as HH:MM)."""
    parsed = parse_time(hhmm)
    if parsed is None:
        return str(hhmm or "")
    return datetime.strptime(parsed, "%H:%M").strftime("%I:%M %p").lstrip("0")


def time_choices(step=15, start_hour=0, end_hour=24) -> list:
    """AM/PM labels for time drop-downs, e.g. ['5:00 AM', '5:30 AM', ... '11:30 PM']."""
    return [time_label(f"{m // 60:02d}:{m % 60:02d}") for m in range(start_hour * 60, end_hour * 60, step)]


def validate_time(value, label="Time") -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    if not str(value or "").strip():
        raise ValidationError(f"{label} is required.")
    parsed = parse_time(value)
    if parsed is None:
        raise ValidationError(f"{label} must look like 08:30, 8:30 AM or 20:15.")
    return parsed


def validate_number(value, label, minimum, maximum, integer=True, required=True):
    if value is None or str(value).strip() == "":
        if required:
            raise ValidationError(f"{label} is required.")
        return None
    try:
        number = float(str(value).replace(",", ""))
    except ValueError:
        raise ValidationError(f"{label} must be a number.")
    if number < minimum or number > maximum:
        raise ValidationError(f"{label} must be between {minimum:g} and {maximum:g}.")
    return int(round(number)) if integer else round(number, 2)


def validate_choice(value, label, choices):
    if value not in choices:
        raise ValidationError(f"{label} must be one of: {', '.join(choices)}.")
    return value
