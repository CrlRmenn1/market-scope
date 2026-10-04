"""Which business types fit the user's profile, and short highlights for a scanned spot.

Profile fit is three yes/no checks against TREND_BUSINESS_REQUIREMENTS:
  - Capital: the user's startup capital reaches the typical minimum
  - Setup:   the business's usual setup matches the user's preferred setup
  - Payback: the typical payback period is within the user's target
fit_score = checks passed / 3 * 100. It only decides WHICH business types get
scanned and shown; it never changes a spot's viability score.
"""
from constants.msme import SME_DATABASE, SME_PROFILE_BY_NAME


TREND_BUSINESS_REQUIREMENTS = {
    "coffee": {"capital_min": 120000, "capital_max": 450000, "risk": "medium", "setup": "storefront", "payback_months": 18},
    "print": {"capital_min": 90000, "capital_max": 280000, "risk": "low", "setup": "storefront", "payback_months": 20},
    "laundry": {"capital_min": 180000, "capital_max": 520000, "risk": "medium", "setup": "storefront", "payback_months": 22},
    "carwash": {"capital_min": 220000, "capital_max": 700000, "risk": "high", "setup": "roadside", "payback_months": 24},
    "kiosk": {"capital_min": 50000, "capital_max": 220000, "risk": "medium", "setup": "kiosk", "payback_months": 12},
    "water": {"capital_min": 120000, "capital_max": 360000, "risk": "low", "setup": "storefront", "payback_months": 18},
    "bakery": {"capital_min": 130000, "capital_max": 420000, "risk": "medium", "setup": "storefront", "payback_months": 18},
    "pharmacy": {"capital_min": 250000, "capital_max": 900000, "risk": "medium", "setup": "storefront", "payback_months": 26},
    "barber": {"capital_min": 70000, "capital_max": 260000, "risk": "low", "setup": "storefront", "payback_months": 14},
    "moto": {"capital_min": 100000, "capital_max": 350000, "risk": "medium", "setup": "roadside", "payback_months": 16},
    "internet": {"capital_min": 160000, "capital_max": 480000, "risk": "high", "setup": "storefront", "payback_months": 24},
    "meat": {"capital_min": 110000, "capital_max": 320000, "risk": "medium", "setup": "market-stall", "payback_months": 15},
    "hardware": {"capital_min": 300000, "capital_max": 1200000, "risk": "medium", "setup": "warehouse", "payback_months": 28},
}

# Other business types are suggested only when they pass at least 2 of the 3 checks.
MIN_FIT_SCORE_FOR_SUGGESTION = 67


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _peso(amount: int) -> str:
    return f"PHP {amount:,}"


def resolve_primary_business_key(user_profile):
    """primary_business is a key from the preferences dropdown ("coffee"); older
    profiles may hold the display name ("Coffee Shops") instead."""
    raw = str(user_profile.get("primary_business") or "").strip().lower()
    if raw in SME_DATABASE:
        return raw
    return SME_PROFILE_BY_NAME.get(raw)


def evaluate_business_fit(business_key: str, user_profile):
    requirement = TREND_BUSINESS_REQUIREMENTS.get(business_key, {})
    capital_min = int(requirement.get("capital_min") or 0)
    capital_max = int(requirement.get("capital_max") or 0)
    setup = str(requirement.get("setup") or "storefront")
    payback_months = int(requirement.get("payback_months") or 0)

    startup_capital = _as_int(user_profile.get("startup_capital"))
    preferred_setup = str(user_profile.get("preferred_setup") or "").strip().lower()
    target_payback = _as_int(user_profile.get("target_payback_months"))

    capital_passed = startup_capital is not None and startup_capital >= capital_min
    if startup_capital is None:
        capital_detail = f"Typical start-up cost is {_peso(capital_min)} to {_peso(capital_max)}."
    elif capital_passed:
        capital_detail = f"Your {_peso(startup_capital)} covers the typical minimum of {_peso(capital_min)}."
    else:
        capital_detail = f"Your {_peso(startup_capital)} is below the typical minimum of {_peso(capital_min)}."

    setup_passed = preferred_setup == setup
    setup_detail = (
        f"Usually a {setup} business, which matches your preference."
        if setup_passed
        else f"Usually a {setup} business; you prefer {preferred_setup or 'no specific setup'}."
    )

    payback_passed = target_payback is not None and payback_months <= target_payback
    payback_detail = (
        f"Typical payback is about {payback_months} months"
        + (f", within your {target_payback}-month target." if payback_passed else f", longer than your {target_payback or '?'}-month target.")
    )

    checks = [
        {"label": "Capital", "passed": capital_passed, "detail": capital_detail},
        {"label": "Setup", "passed": setup_passed, "detail": setup_detail},
        {"label": "Payback", "passed": payback_passed, "detail": payback_detail},
    ]
    passed_count = sum(1 for check in checks if check["passed"])

    return {
        "fit_score": round(passed_count / len(checks) * 100),
        "checks_passed": passed_count,
        "checks": checks,
        "requirements": {
            "capital_min": capital_min,
            "capital_max": capital_max,
            "setup": setup,
            "payback_months": payback_months,
            "risk": requirement.get("risk"),
        },
    }


def pick_trend_business_types(user_profile, extra: int = 2):
    """The business types to scan and show for this user.

    1. The user's primary business, always first.
    2. Up to `extra` other types that pass at least 2 of 3 fit checks, ordered by
       fit score, then by shorter payback, then by key (so the order never shifts).
    """
    primary_key = resolve_primary_business_key(user_profile)
    picks = []
    if primary_key:
        picks.append({"business_key": primary_key, "role": "primary"})

    others = []
    for business_key in SME_DATABASE:
        if business_key == primary_key:
            continue
        fit = evaluate_business_fit(business_key, user_profile)
        if fit["fit_score"] < MIN_FIT_SCORE_FOR_SUGGESTION:
            continue
        others.append((-fit["fit_score"], fit["requirements"]["payback_months"], business_key))

    others.sort()
    for _, _, business_key in others[:max(0, extra)]:
        picks.append({"business_key": business_key, "role": "fit"})

    return picks


def summarize_spot(report):
    """Short highlights taken straight from the /analyze breakdown of a spot."""
    breakdown = report.get("breakdown") or {}
    highlights = []

    zoning_status = (breakdown.get("zoning") or {}).get("status")
    if zoning_status:
        highlights.append(f"Zoning: {zoning_status}")

    hazard_status = (breakdown.get("hazard") or {}).get("status")
    if hazard_status:
        highlights.append(f"Flood hazard: {hazard_status}")

    competitors_found = report.get("competitors_found")
    radius = report.get("radius_meters")
    if competitors_found is not None and radius:
        highlights.append(f"{competitors_found} competitor{'s' if competitors_found != 1 else ''} within {radius} m")

    road_status = (breakdown.get("road_access") or {}).get("status")
    if road_status:
        highlights.append(f"Road access: {road_status}")

    return highlights
