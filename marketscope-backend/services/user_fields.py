"""Rules for the name, address, age, photo and consent fields saved on a user."""
import re
from datetime import date

from fastapi import HTTPException


PANABO_CITY = "Panabo City"
PANABO_REGION = "Davao del Norte"
NAME_MAX_LENGTH = 120
MIN_PASSWORD_LENGTH = 6

# A 2MB image is about 2.8 million characters once base64-encoded. SVG is left out
# on purpose: it can carry scripts. Remote links are out so nothing loads from
# someone else's server when the admin list opens.
MAX_IMAGE_DATA_URL_LENGTH = 2_800_000
_IMAGE_DATA_URL = re.compile(r"data:image/(png|jpeg|jpg|webp|gif);base64,[A-Za-z0-9+/]+={0,2}")
_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")

# Column limits, checked here so an oversized value gets a clear message.
_TEXT_LIMITS = {
    "email": ("Email", 254),
    "street": ("Street", 200),
    "barangay": ("Barangay", 120),
    "address": ("Address", 500),
    "cellphone_number": ("Cellphone number", 32),
    "primary_business": ("Primary business", 120),
    "preferred_setup": ("Preferred setup", 50),
}

# Bump together with PRIVACY_POLICY_VERSION in
# marketscope-frontend/src/content/privacyPolicy.jsx when the policy text changes.
PRIVACY_POLICY_VERSION = "1.0"


def _clean(value):
    if not isinstance(value, str):
        return None
    return value.strip() or None


def build_name_fields(first_name, last_name):
    """Validated first and last name, plus the full_name other pages read."""
    first = _clean(first_name)
    last = _clean(last_name)
    if not first or not last:
        raise HTTPException(status_code=400, detail="Enter both your first name and last name.")
    if len(first) > NAME_MAX_LENGTH or len(last) > NAME_MAX_LENGTH:
        raise HTTPException(status_code=400, detail=f"Names can be at most {NAME_MAX_LENGTH} characters.")
    return {"first_name": first, "last_name": last, "full_name": f"{first} {last}"}


def build_address_fields(street, barangay):
    """Split address columns plus the combined address other pages read.

    City and region are only saved alongside a street or barangay, so a blank
    address never turns into a bare "Panabo City, Davao del Norte".
    """
    clean_street = _clean(street)
    clean_barangay = _clean(barangay)
    if not clean_street and not clean_barangay:
        return {"street": None, "barangay": None, "city": None, "region": None, "address": None}

    parts = [clean_street, clean_barangay, PANABO_CITY, PANABO_REGION]
    return {
        "street": clean_street,
        "barangay": clean_barangay,
        "city": PANABO_CITY,
        "region": PANABO_REGION,
        "address": ", ".join(part for part in parts if part),
    }


def compute_age(birthday, today=None):
    today = today or date.today()
    had_birthday_this_year = (today.month, today.day) >= (birthday.month, birthday.day)
    age = today.year - birthday.year - (0 if had_birthday_this_year else 1)
    return max(0, age)


def resolve_age(birthday, age):
    """The birthday decides the age; an age alone only survives on older accounts."""
    return compute_age(birthday) if birthday else age


def is_valid_image_data_url(value):
    return (
        isinstance(value, str)
        and len(value) <= MAX_IMAGE_DATA_URL_LENGTH
        and _IMAGE_DATA_URL.fullmatch(value) is not None
    )


def validate_avatar(avatar_url):
    if avatar_url and not is_valid_image_data_url(avatar_url):
        raise HTTPException(status_code=400, detail="Profile picture must be a JPG, PNG, WebP or GIF image of 2MB or smaller.")


def validate_email(email):
    if not isinstance(email, str) or _EMAIL.fullmatch(email.strip()) is None:
        raise HTTPException(status_code=400, detail="Enter a valid email address.")


def validate_text_lengths(payload):
    for field, (label, limit) in _TEXT_LIMITS.items():
        value = getattr(payload, field, None)
        if isinstance(value, str) and len(value) > limit:
            raise HTTPException(status_code=400, detail=f"{label} can be at most {limit} characters.")


def validate_new_password(password):
    if len(password.strip()) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=400, detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")


def require_privacy_consent(privacy_consent, privacy_policy_version):
    if privacy_consent is not True:
        raise HTTPException(status_code=400, detail="Agree to the Data Privacy Policy to create an account.")
    if privacy_policy_version != PRIVACY_POLICY_VERSION:
        raise HTTPException(status_code=400, detail="The Data Privacy Policy was updated. Reload the page and review it.")
