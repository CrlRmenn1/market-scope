"""User profile, analysis history, and trend recommendation routes."""
from fastapi import APIRouter, HTTPException, Request

from constants.msme import SME_DATABASE
from db.queries import (
    fetch_custom_msme_counts_async,
    fetch_history_trend_snapshot_async,
    fetch_user_business_history_snapshot_async,
    fetch_user_profile_by_id_async,
)
from db.schema import get_users_primary_key_column_async
from models.requests import UpdateUserProfile
from services.auth_service import get_missing_trend_preferences
from services.osm_data import get_cached_pbf_competitors, preload_pbf_competitor_cache
from services.trend_scan import (
    get_citywide_scan_snapshot,
    match_preference_business_keys,
    run_pre_scanned_trend_report,
)
from services.trend_scoring import (
    build_trend_upside_downside,
    recommend_trends,
    score_business_opportunity,
)
from services.user_service import (
    delete_user_history_item as user_delete_history_item,
    get_user_history as user_get_history,
    get_user_history_item as user_get_history_item,
    get_user_profile as user_get_profile,
    mark_user_onboarding_seen as user_mark_onboarding_seen,
    update_user_profile as user_update_profile,
)
from utils.dates import utc_now_iso_z


router = APIRouter()


@router.get("/users/{user_id}")
async def get_user_profile(request: Request, user_id: int):
    try:
        profile = await user_get_profile(request.app.state.db_pool, user_id)

        if not profile:
            raise HTTPException(status_code=404, detail="User not found")

        return {"status": "success", "user": dict(profile)}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/users/{user_id}")
async def update_user_profile(request: Request, user_id: int, payload: UpdateUserProfile):
    try:
        updated_user = await user_update_profile(request.app.state.db_pool, user_id, payload)
        return {"status": "success", "user": dict(updated_user) if updated_user else None}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/users/{user_id}/onboarding-seen")
async def mark_onboarding_seen(request: Request, user_id: int):
    try:
        updated = await user_mark_onboarding_seen(request.app.state.db_pool, user_id)
        return {"status": "success", "onboarding_seen": bool(updated["onboarding_seen"])}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/history")
async def get_user_history(request: Request, user_id: int):
    try:
        history = await user_get_history(request.app.state.db_pool, user_id)
        return {"status": "success", "history": history}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/history/{history_id}")
async def get_user_history_item(request: Request, user_id: int, history_id: int):
    try:
        history_item = await user_get_history_item(request.app.state.db_pool, user_id, history_id)

        if not history_item:
            raise HTTPException(status_code=404, detail="History item not found")

        return {"status": "success", "history": history_item}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/users/{user_id}/history/{history_id}")
async def delete_user_history_item(request: Request, user_id: int, history_id: int):
    try:
        deleted_row = await user_delete_history_item(request.app.state.db_pool, user_id, history_id)

        if not deleted_row:
            return {"status": "success", "deleted_history_id": history_id, "already_missing": True}

        return {"status": "success", "deleted_history_id": deleted_row[0]}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/users/{user_id}/trend-recommendations")
async def get_user_trend_recommendations(request: Request, user_id: int, limit: int = 5):
    try:
        safe_limit = max(1, min(10, int(limit)))
        preload_pbf_competitor_cache()

        pool = request.app.state.db_pool
        async with pool.acquire() as conn:
            user_pk_column = await get_users_primary_key_column_async(conn)
            user_profile = await fetch_user_profile_by_id_async(conn, user_pk_column, user_id)

        if not user_profile:
            raise HTTPException(status_code=404, detail="User not found")

        missing_trend_preferences = get_missing_trend_preferences(user_profile)
        if missing_trend_preferences:
            raise HTTPException(
                status_code=400,
                detail={
                    "message": "Please complete your trend preferences first.",
                    "missing_fields": missing_trend_preferences,
                },
            )

        async with pool.acquire() as conn:
            global_trend_snapshot = await fetch_history_trend_snapshot_async(conn)
            user_trend_snapshot = await fetch_user_business_history_snapshot_async(conn, user_id)
            custom_msme_counts = await fetch_custom_msme_counts_async(conn)

        trend_inputs = {}
        for profile_key, profile_data in SME_DATABASE.items():
            business_name = str(profile_data.get("name") or profile_key).strip().lower()
            trend_inputs[profile_key] = global_trend_snapshot.get(business_name, {"scan_count": 0, "avg_score": 0.0})

        trend_recommendation_keys = recommend_trends(user_profile, trend_inputs)

        recommendations = []
        for profile_key, profile_data in SME_DATABASE.items():
            business_name = str(profile_data.get("name") or profile_key).strip().lower()
            global_trend = global_trend_snapshot.get(business_name, {"scan_count": 0, "avg_score": 0.0})
            user_trend = user_trend_snapshot.get(business_name, {"scan_count": 0, "avg_score": 0.0})
            local_competitor_count = len(get_cached_pbf_competitors(profile_data.get("val"))) + int(custom_msme_counts.get(profile_key, 0))

            recommendations.append(
                score_business_opportunity(
                    profile_key,
                    profile_data,
                    user_profile,
                    global_trend,
                    user_trend,
                    local_competitor_count=local_competitor_count,
                )
            )

        recommendations.sort(key=lambda item: item.get("opportunity_score", 0), reverse=True)

        citywide_snapshot = get_citywide_scan_snapshot(radius=340)
        citywide_snapshot_obj = citywide_snapshot if isinstance(citywide_snapshot, dict) else {}
        citywide_businesses = citywide_snapshot_obj.get("businesses") or {}

        for item in recommendations:
            business_key = item.get("business_key")
            city_bucket = citywide_businesses.get(business_key) or {}
            city_report = city_bucket.get("best_report") or {}
            city_score = int(city_report.get("viability_score") or 0)
            item["citywide_potential_score"] = city_score
            item["citywide_hotspots"] = city_bucket.get("hotspots") or []

        recommendations.sort(
            key=lambda item: (
                item.get("citywide_potential_score", 0),
                item.get("opportunity_score", 0)
            ),
            reverse=True,
        )

        preference_business_keys = match_preference_business_keys(user_profile.get("primary_business"))
        trend_priority = {
            business_key: index
            for index, business_key in enumerate(trend_recommendation_keys)
        }

        recommendations.sort(
            key=lambda item: (
                0 if item.get("business_key") in trend_priority else 1,
                trend_priority.get(item.get("business_key"), 999),
                -int(item.get("citywide_potential_score", 0)),
                -int(item.get("opportunity_score", 0)),
            )
        )

        recommendations_by_key = {
            item.get("business_key"): item
            for item in recommendations
            if item.get("business_key")
        }

        selected_recommendations = []
        selected_keys = set()

        for item in recommendations:
            business_key = item.get("business_key")
            if business_key in selected_keys:
                continue
            selected_recommendations.append(dict(item))
            selected_keys.add(business_key)
            if len(selected_recommendations) >= safe_limit:
                break

        for preferred_key in preference_business_keys:
            if preferred_key in selected_keys:
                continue
            preferred_item = recommendations_by_key.get(preferred_key)
            if preferred_item:
                selected_recommendations.append(dict(preferred_item))
                selected_keys.add(preferred_key)

        enriched_recommendations = []

        for item in selected_recommendations:
            business_key = item.get("business_key")
            pre_scanned_report = run_pre_scanned_trend_report(
                business_key,
                user_id=user_id,
                radius=340,
            ) if business_key else None

            upsides, downsides = build_trend_upside_downside(item, pre_scanned_report)

            pre_scanned_location = None
            if pre_scanned_report:
                target_coords = pre_scanned_report.get("target_coords") or {}
                pre_scanned_location = {
                    "lat": target_coords.get("lat"),
                    "lng": target_coords.get("lng"),
                    "source": pre_scanned_report.get("scan_source"),
                    "source_type": pre_scanned_report.get("scan_source_type"),
                    "viability_score": pre_scanned_report.get("viability_score"),
                    "space_context": pre_scanned_report.get("space_context"),
                }

            item["included_by_preference"] = item.get("business_key") in preference_business_keys
            item["upsides"] = upsides
            item["downsides"] = downsides
            item["pre_scanned_location"] = pre_scanned_location
            item["full_report"] = pre_scanned_report
            enriched_recommendations.append(item)

        return {
            "status": "success",
            "user_id": user_id,
            "generated_at": utc_now_iso_z(),
            "summary": {
                "profile_interest": user_profile.get("primary_business") or "Not set",
                "startup_capital": user_profile.get("startup_capital"),
                "preferred_setup": user_profile.get("preferred_setup") or "Not set",
                "target_payback_months": user_profile.get("target_payback_months"),
                "total_options_evaluated": len(recommendations),
                "preference_business_matches": sorted(list(preference_business_keys)),
                "trend_recommendation_keys": trend_recommendation_keys,
                "scan_engine": "citywide-standalone",
                "citywide_scan_generated_at": citywide_snapshot_obj.get("generated_at"),
                "citywide_scan_points": citywide_snapshot_obj.get("candidate_count"),
            },
            "recommendations": enriched_recommendations,
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))
