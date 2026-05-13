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


def score_business_opportunity(profile_key, profile_data, user_profile, global_trend, user_trend, local_competitor_count=0):
    business_name = str(profile_data.get("name") or profile_key).strip()
    business_name_key = business_name.lower()

    market_scan_count = int(global_trend.get("scan_count") or 0)
    market_avg_score = float(global_trend.get("avg_score") or 0.0)
    user_scan_count = int(user_trend.get("scan_count") or 0)
    user_avg_score = float(user_trend.get("avg_score") or 0.0)

    demand_points = min(22, int((profile_data.get("need", 5) / 10) * 22))
    market_gap_points = max(0, 22 - min(22, int(local_competitor_count) * 2))
    trend_points = min(18, int((market_avg_score / 100) * 18))
    momentum_points = min(10, market_scan_count * 2)
    user_experience_points = min(12, int((user_avg_score / 100) * 12)) if user_scan_count > 0 else 0

    requirement = TREND_BUSINESS_REQUIREMENTS.get(profile_key, {})
    capital_min = int(requirement.get("capital_min") or 0)
    capital_max = int(requirement.get("capital_max") or 0)
    business_risk = str(requirement.get("risk") or "medium").strip().lower()
    business_setup = str(requirement.get("setup") or "storefront").strip().lower()
    target_payback = int(requirement.get("payback_months") or 0)

    startup_capital = user_profile.get("startup_capital")
    risk_tolerance = str(user_profile.get("risk_tolerance") or "").strip().lower()
    preferred_setup = str(user_profile.get("preferred_setup") or "").strip().lower()
    target_payback_months = user_profile.get("target_payback_months")

    capital_fit_points = 6
    if isinstance(startup_capital, int):
        if capital_min <= startup_capital <= max(capital_max, capital_min):
            capital_fit_points = 14
        elif startup_capital >= capital_min:
            capital_fit_points = 10
        else:
            capital_fit_points = 2

    risk_rank = {"low": 1, "medium": 2, "high": 3}
    risk_fit_points = 5
    if risk_tolerance in risk_rank:
        if risk_rank[risk_tolerance] >= risk_rank.get(business_risk, 2):
            risk_fit_points = 10
        else:
            risk_fit_points = 3

    setup_fit_points = 4
    if preferred_setup:
        setup_fit_points = 9 if preferred_setup == business_setup else 3

    payback_fit_points = 3
    if isinstance(target_payback_months, int) and target_payback_months > 0 and target_payback > 0:
        payback_fit_points = 9 if target_payback <= target_payback_months else 2

    primary_interest = str(user_profile.get("primary_business") or "").strip().lower()
    interest_hit = bool(
        primary_interest
        and (
            profile_key in primary_interest
            or business_name_key in primary_interest
            or any(token in primary_interest for token in ["food"] if profile_key in {"kiosk", "bakery", "coffee", "meat"})
        )
    )
    interest_points = 16 if interest_hit else 4

    total_score = min(
        100,
        demand_points
        + market_gap_points
        + trend_points
        + momentum_points
        + user_experience_points
        + interest_points
        + capital_fit_points
        + risk_fit_points
        + setup_fit_points
        + payback_fit_points,
    )

    scoring = {
        "demand_points": demand_points,
        "market_gap_points": market_gap_points,
        "trend_points": trend_points,
        "momentum_points": momentum_points,
        "user_experience_points": user_experience_points,
        "interest_points": interest_points,
        "capital_fit_points": capital_fit_points,
        "risk_fit_points": risk_fit_points,
        "setup_fit_points": setup_fit_points,
        "payback_fit_points": payback_fit_points,
    }

    reasons = [
        f"Market trend average score is {market_avg_score:.1f} across {market_scan_count} recent scans.",
        f"Local competitor estimate is {int(local_competitor_count)} around this business type.",
        f"User profile signals a {risk_tolerance or 'default'} risk preference and {preferred_setup or 'unset'} setup preference.",
    ]

    return {
        "business_key": profile_key,
        "business_name": business_name,
        "opportunity_score": int(total_score),
        "scoring": scoring,
        "reasons": reasons,
        "local_competitor_estimate": int(local_competitor_count),
        "market_scan_count": market_scan_count,
        "market_average_viability": round(market_avg_score, 1),
        "user_scan_count": user_scan_count,
        "user_average_viability": round(user_avg_score, 1),
        "profile_match": {
            "capital_range": {"min": capital_min, "max": capital_max},
            "business_risk": business_risk,
            "business_setup": business_setup,
            "estimated_payback_months": target_payback,
        },
    }


def build_trend_upside_downside(recommendation, pre_scanned_report):
    scoring = recommendation.get("scoring") or {}
    upsides = []
    downsides = []

    if recommendation.get("opportunity_score", 0) >= 75:
        upsides.append("Strong overall opportunity score based on local demand, saturation, and profile fit.")

    if recommendation.get("local_competitor_estimate", 0) <= 2:
        upsides.append("Low local competitor pressure leaves room to capture unmet demand.")
    else:
        downsides.append("Local competition is already present, so differentiation is required.")

    if scoring.get("capital_fit_points", 0) >= 10:
        upsides.append("Startup capital fit is favorable for this category.")
    elif scoring.get("capital_fit_points", 0) <= 3:
        downsides.append("Your startup capital may be below the typical range for this business type.")

    if scoring.get("risk_fit_points", 0) >= 8:
        upsides.append("Risk profile aligns with the operating risk of this business.")
    elif scoring.get("risk_fit_points", 0) <= 3:
        downsides.append("Risk mismatch detected between your profile and this business category.")

    if pre_scanned_report:
        pre_scan_score = int(pre_scanned_report.get("viability_score") or 0)
        if pre_scan_score >= 70:
            upsides.append("The pre-scanned Panabo location shows strong viability for this business.")
        elif pre_scan_score <= 45:
            downsides.append("The pre-scanned Panabo location has mixed or weak viability indicators.")

        breakdown = pre_scanned_report.get("breakdown") or {}
        hazard_score = int((breakdown.get("hazard") or {}).get("score") or 0)
        if hazard_score <= 12:
            downsides.append("Flood hazard exposure may increase operating and mitigation costs in the selected area.")

        if pre_scanned_report.get("space_context"):
            upsides.append("A nearby active For Rent/For Sale listing matches the pre-scanned location.")

    if not upsides:
        upsides.append("Baseline demand and location-fit indicators are present, but require validation through full report review.")
    if not downsides:
        downsides.append("No major downside triggered in scoring, but permit checks and site validation are still required.")

    return upsides[:4], downsides[:4]


def recommend_trends(user_profile, global_trends):
    """
    Recommend business trends based on user profile and global trends.

    Args:
        user_profile (dict): The user's profile containing preferences and constraints.
        global_trends (dict): Global trends data for various businesses.

    Returns:
        list: A list of recommended business trends sorted by suitability.
    """
    recommendations = []

    startup_capital = user_profile.get("startup_capital") or 0
    risk_tolerance = str(user_profile.get("risk_tolerance") or "medium").strip().lower()
    preferred_setup = str(user_profile.get("preferred_setup") or "").strip().lower()
    target_payback_months = user_profile.get("target_payback_months") or 0

    for business, requirements in TREND_BUSINESS_REQUIREMENTS.items():
        capital_min = requirements["capital_min"]
        capital_max = requirements["capital_max"]
        risk = requirements["risk"]
        setup = requirements["setup"]
        payback_months = requirements["payback_months"]

        # Check if the business matches the user's profile
        if startup_capital < capital_min or startup_capital > capital_max:
            continue
        if risk_tolerance != risk and risk_tolerance != "high":
            continue
        if preferred_setup and preferred_setup != setup:
            continue
        if target_payback_months and target_payback_months < payback_months:
            continue

        # Add the business to recommendations with a score
        trend_data = global_trends.get(business, {})
        scan_count = trend_data.get("scan_count", 0)
        avg_score = trend_data.get("avg_score", 0)

        score = avg_score + scan_count  # Example scoring logic
        recommendations.append((business, score))

    # Sort recommendations by score in descending order
    recommendations.sort(key=lambda x: x[1], reverse=True)

    return [business for business, _ in recommendations]