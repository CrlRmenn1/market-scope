"""Which business types to scan and show, based on the user's two trend preferences.

  - Primary business: always scanned and shown first.
  - Preferred setup:  every other business type usually run in that setup
                      (TYPICAL_SETUP in constants/msme.py) is scanned too; the
                      Trends page shows the ones whose best spot scored highest.

Preferences only decide WHICH business types are scanned. They never change a
spot's viability score.
"""
from constants.msme import SME_DATABASE, SME_PROFILE_BY_NAME, TYPICAL_SETUP


def _preferred_setup(user_profile) -> str:
    return str(user_profile.get("preferred_setup") or "").strip().lower()


def resolve_primary_business_key(user_profile):
    """primary_business is a key from the preferences dropdown ("coffee"); older
    profiles may hold the display name ("Coffee Shops") instead."""
    raw = str(user_profile.get("primary_business") or "").strip().lower()
    if raw in SME_DATABASE:
        return raw
    return SME_PROFILE_BY_NAME.get(raw)


def get_same_setup_business_keys(user_profile, exclude=None):
    """Other business types usually run in the user's preferred setup, in SME_DATABASE order."""
    setup = _preferred_setup(user_profile)
    if not setup:
        return []
    return [
        business_key
        for business_key in SME_DATABASE
        if business_key != exclude and TYPICAL_SETUP.get(business_key) == setup
    ]


def get_trend_scan_business_keys(user_profile):
    """Everything the background scan should cover for this user: primary first."""
    primary_key = resolve_primary_business_key(user_profile)
    keys = [primary_key] if primary_key else []
    keys.extend(get_same_setup_business_keys(user_profile, exclude=primary_key))
    return keys


def describe_setup_match(business_key: str, user_profile):
    typical_setup = TYPICAL_SETUP.get(business_key)
    preferred = _preferred_setup(user_profile)
    business_name = SME_DATABASE.get(business_key, {}).get("name", business_key)
    matches = bool(typical_setup) and typical_setup == preferred

    if matches:
        detail = f"{business_name} is usually a {typical_setup} business, which matches your preferred setup."
    else:
        detail = f"{business_name} is usually a {typical_setup or 'mixed-setup'} business; you prefer {preferred or 'no specific setup'}."

    return {"typical_setup": typical_setup, "matches": matches, "detail": detail}
