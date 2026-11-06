"""How the user's two trend preferences shape the Trends page.

  - Primary business: scanned first and given its own "best areas" section.
  - Preferred setup:  businesses usually run in that setup (TYPICAL_SETUP in
                      constants/msme.py) are scanned next and tagged on the page,
                      which can also filter to them.

Every business type is scanned in the end, because suggestions compare them within
an area. Preferences only decide the order and what is tagged. They never change a
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
    """The user's own business types: primary first, then the same-setup ones."""
    primary_key = resolve_primary_business_key(user_profile)
    keys = [primary_key] if primary_key else []
    keys.extend(get_same_setup_business_keys(user_profile, exclude=primary_key))
    return keys


def get_all_scan_business_keys(user_profile):
    """Every business type, because suggestions compare them all within an area.
    The user's own come first, so their results are ready soonest."""
    own_keys = get_trend_scan_business_keys(user_profile)
    return own_keys + [business_key for business_key in SME_DATABASE if business_key not in own_keys]


def fits_preferred_setup(business_key: str, user_profile) -> bool:
    preferred = _preferred_setup(user_profile)
    return bool(preferred) and TYPICAL_SETUP.get(business_key) == preferred


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
