from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import math
import os
import random
import socket
import smtplib
import json
from pathlib import Path
from urllib.parse import urlparse
from datetime import date, datetime, timedelta, timezone
from contextlib import asynccontextmanager
from threading import Event, Lock, Thread
from email.message import EmailMessage
import asyncpg
import asyncio
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import bcrypt

from db_schema import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    ADMIN_TOKEN,
    AHP_GLOBAL_CATEGORY_SENTINEL,
    RESET_CODE_DEV_MODE,
    RESET_CODE_TTL_MINUTES,
    create_app_tables,
    ensure_admin_space_submissions_table,
    ensure_admin_users_table,
    ensure_custom_msme_table,
    ensure_verified_local_features_table,
    ensure_user_space_submissions_table,
    generate_reset_code,
    get_analysis_history_pk_column,
    get_analysis_history_pk_column_async,
    get_users_primary_key_column,
    get_users_primary_key_column_async,
    send_password_reset_email,
)
from ahp import (
    AHPValidationError,
    build_reciprocal_matrix,
    solve_ahp,
)
from auth_service import (
    forgot_password as auth_forgot_password,
    get_missing_trend_preferences,
    login_user as auth_login_user,
    register_user as auth_register_user,
    reset_password as auth_reset_password,
    reset_password_direct as auth_reset_password_direct,
)
from user_service import (
    delete_user_history_item as user_delete_history_item,
    get_user_history as user_get_history,
    get_user_history_item as user_get_history_item,
    get_user_profile as user_get_profile,
    mark_user_onboarding_seen as user_mark_onboarding_seen,
    update_user_profile as user_update_profile,
)
from reporting import (
    build_structured_report,
    render_report_html,
    try_render_pdf_bytes,
    generate_narrative_with_fallback,
)
from settings import get_allowed_origins, get_database_config

try:
    import geopandas as gpd
except Exception:
    gpd = None

try:
    from shapely.geometry import Point, box
    from shapely.ops import nearest_points, unary_union
except Exception:
    Point = None
    box = None
    nearest_points = None
    unary_union = None

# ==========================================
# UTC HELPERS (Replace Deprecated datetime.utcnow())
# ==========================================
def utc_now_naive():
    """Return current UTC time as naive datetime (no timezone info)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)

def utc_now_iso_z():
    """Return current UTC time as ISO 8601 string with Z suffix."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'

# ==========================================
# DATABASE CONFIGURATION
# ==========================================
DB_CONFIG = get_database_config()


def log_db_config_debug():
    """Log database config for debugging (without password)."""
    safe_config = {k: v for k, v in DB_CONFIG.items() if k != "password"}
    print(f"[DB Config] {safe_config}", flush=True)


async def connect_with_retry(max_retries=3, initial_delay=2):
    """Create asyncpg pool with retry logic for Render deployments."""
    import time
    
    log_db_config_debug()
    
    for attempt in range(max_retries):
        try:
            print(f"[DB Connect] Attempt {attempt + 1}/{max_retries}...", flush=True)
            pool = await asyncpg.create_pool(
                user=DB_CONFIG["user"],
                password=DB_CONFIG["password"],
                database=DB_CONFIG["dbname"],
                host=DB_CONFIG["host"],
                port=int(DB_CONFIG["port"]),
                min_size=2,
                max_size=10,
                timeout=DB_CONFIG.get("connect_timeout", 8),
            )
            print("[DB Connect] ✓ Pool created successfully", flush=True)
            return pool
        except Exception as e:
            print(f"[DB Connect] ✗ Attempt {attempt + 1} failed: {e}", flush=True)
            if attempt < max_retries - 1:
                await asyncio.sleep(initial_delay * (attempt + 1))
            else:
                raise


def trigger_trend_warmup_after_login(radius: int = 340):
    """Start trend warmup in the background after auth succeeds."""
    Thread(
        target=warm_citywide_scan_snapshot_async,
        kwargs={"radius": radius},
        daemon=True,
    ).start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        create_app_tables(DB_CONFIG)
    except Exception as e:
        print(f"[DB Schema] Error creating tables: {e}", flush=True)
        # Continue startup even if table creation fails
    
    # Create asyncpg pool with retry logic
    app.state.db_pool = await connect_with_retry()

    # The geopandas/PBF preloads below are the slow part of startup (parsing
    # panabo.pbf and the hazard shapefile can take well over a minute on a
    # low-CPU host). Running them synchronously here blocks the port from
    # opening at all, which reads as a hung/failed deploy on hosts like
    # Render. Run them in the background instead so the server starts
    # accepting connections immediately; each cache already has its own
    # lazy-load-on-first-use fallback (hazard, PBF competitors) or a
    # clearly-labeled neutral score for callers that land before it's ready
    # (road/building spatial context), so this is safe.
    def _preload_geo_caches():
        preload_hazard_layer_cache()
        preload_pbf_competitor_cache()
        preload_pbf_spatial_context_cache()

    Thread(target=_preload_geo_caches, daemon=True).start()

    _load_ahp_weights_cache()
    stop_event = Event()
    auto_refresh_thread = Thread(
        target=_trend_snapshot_auto_refresh_loop,
        args=(stop_event, 340),
        daemon=True,
    )
    auto_refresh_thread.start()
    yield
    stop_event.set()
    db_pool = getattr(app.state, "db_pool", None)
    if db_pool is not None:
        await db_pool.close()


app = FastAPI(lifespan=lifespan)

allowed_origins = get_allowed_origins()

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins if allowed_origins else ["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "status": "success",
        "service": "MarketScope API"
    }


@app.head("/")
def root_head():
    return

# ==========================================
# PYDANTIC MODELS
# ==========================================
class RegisterUser(BaseModel):
    full_name: str
    email: str
    password: str
    address: str | None = None
    cellphone_number: str | None = None
    avatar_url: str | None = None
    age: int | None = None
    birthday: date | None = None
    primary_business: str | None = None
    startup_capital: int | None = None
    preferred_setup: str | None = None
    target_payback_months: int | None = None

class LoginUser(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    email: str
    code: str
    new_password: str


class DirectResetPasswordRequest(BaseModel):
    email: str
    new_password: str


class UpdateUserProfile(BaseModel):
    full_name: str
    email: str
    address: str | None = None
    cellphone_number: str | None = None
    avatar_url: str | None = None
    age: int | None = None
    birthday: date | None = None
    primary_business: str | None = None
    startup_capital: int | None = None
    preferred_setup: str | None = None
    target_payback_months: int | None = None

class AnalysisRequest(BaseModel):
    lat: float
    lon: float
    business_type: str
    radius: int = 340
    user_id: int | None = None
    history_id: int | None = None


class CompetitorPreviewRequest(BaseModel):
    lat: float
    lon: float
    business_type: str
    radius: int = 340


class AdminLoginRequest(BaseModel):
    email: str
    password: str


class AdminCreateMsme(BaseModel):
    name: str
    business_type: str
    latitude: float
    longitude: float


class AdminUpdateMsme(AdminCreateMsme):
    pass


class AdminVerifiedLocalFeatureRequest(BaseModel):
    feature_kind: str
    name: str
    latitude: float
    longitude: float
    business_type: str | None = None
    feature_subtype: str | None = None
    road_class: str | None = None
    power: int | None = None
    building_type: str | None = None
    landuse: str | None = None
    area_m2: float | None = None
    confidence_score: int = 100
    source_note: str | None = None
    verified_at: date | None = None
    is_active: bool = True


class AhpPairwiseSubmitRequest(BaseModel):
    level: str                          # "criteria" | "saturation"
    category: str | None = None         # required if level == "saturation"
    criteria_labels: list[str]          # order defines matrix row/col order
    judgments: dict[str, float]         # upper-triangle only, "i,j" string keys -> Saaty value


class AdminUpdateUser(BaseModel):
    full_name: str
    email: str
    address: str | None = None
    cellphone_number: str | None = None
    avatar_url: str | None = None
    age: int | None = None
    birthday: date | None = None
    primary_business: str | None = None
    startup_capital: int | None = None
    preferred_setup: str | None = None
    target_payback_months: int | None = None


class UserSpaceSubmissionRequest(BaseModel):
    user_id: int
    title: str
    listing_mode: str
    property_type: str | None = None
    business_type: str | None = None
    latitude: float
    longitude: float
    address_text: str | None = None
    price_min: int | None = None
    price_max: int | None = None
    contact_info: str | None = None
    notes: str | None = None
    photo_urls: list[str] | None = None


class AdminSpaceSubmissionRequest(BaseModel):
    title: str
    listing_mode: str
    guarantee_level: str = "potential"
    confidence_score: int | None = None
    property_type: str | None = None
    business_type: str | None = None
    latitude: float
    longitude: float
    address_text: str | None = None
    price_min: int | None = None
    price_max: int | None = None
    source_note: str | None = None
    contact_info: str | None = None
    notes: str | None = None
    photo_urls: list[str] | None = None
    verified_at: date | None = None
    expires_at: date | None = None
    is_active: bool = True


class AdminToggleSpaceSubmissionActiveRequest(BaseModel):
    is_active: bool


class AdminReviewUserSpaceSubmissionRequest(BaseModel):
    status: str
    review_note: str | None = None


# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

@app.post("/register")
async def register(user: RegisterUser):
    try:
        return await auth_register_user(app.state.db_pool, user)
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/login")
async def login(user: LoginUser):
    try:
        response = await auth_login_user(app.state.db_pool, user)
        trigger_trend_warmup_after_login(radius=340)
        return response
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/forgot-password")
async def forgot_password(payload: ForgotPasswordRequest):
    try:
        response = await auth_forgot_password(app.state.db_pool, payload, RESET_CODE_TTL_MINUTES)
        if RESET_CODE_DEV_MODE and response.get("status") == "success" and payload.email:
            # dev-only hint is handled in the service flow; keep compatibility here if needed later
            pass
        return response
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest):
    try:
        return await auth_reset_password(app.state.db_pool, payload)
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset-password-direct")
async def reset_password_direct(payload: DirectResetPasswordRequest):
    try:
        return await auth_reset_password_direct(app.state.db_pool, payload)
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}")
async def get_user_profile(user_id: int):
    try:
        profile = await user_get_profile(app.state.db_pool, user_id)

        if not profile:
            raise HTTPException(status_code=404, detail="User not found")

        return {"status": "success", "user": dict(profile)}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/users/{user_id}")
async def update_user_profile(user_id: int, payload: UpdateUserProfile):
    try:
        updated_user = await user_update_profile(app.state.db_pool, user_id, payload)
        return {"status": "success", "user": dict(updated_user) if updated_user else None}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/users/{user_id}/onboarding-seen")
async def mark_onboarding_seen(user_id: int):
    try:
        updated = await user_mark_onboarding_seen(app.state.db_pool, user_id)
        return {"status": "success", "onboarding_seen": bool(updated["onboarding_seen"])}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}/history")
async def get_user_history(user_id: int):
    try:
        history = await user_get_history(app.state.db_pool, user_id)
        return {"status": "success", "history": history}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}/history/{history_id}")
async def get_user_history_item(user_id: int, history_id: int):
    try:
        history_item = await user_get_history_item(app.state.db_pool, user_id, history_id)

        if not history_item:
            raise HTTPException(status_code=404, detail="History item not found")

        return {"status": "success", "history": history_item}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/users/{user_id}/history/{history_id}")
async def delete_user_history_item(user_id: int, history_id: int):
    try:
        deleted_row = await user_delete_history_item(app.state.db_pool, user_id, history_id)

        if not deleted_row:
            return {"status": "success", "deleted_history_id": history_id, "already_missing": True}

        return {"status": "success", "deleted_history_id": deleted_row[0]}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}/trend-recommendations")
async def get_user_trend_recommendations(user_id: int, limit: int = 5):
    try:
        safe_limit = max(1, min(10, int(limit)))
        preload_pbf_competitor_cache()

        pool = app.state.db_pool
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

# ==========================================
# GEOSPATIAL ANALYSIS ROUTE
# ==========================================
BACKEND_DIR = Path(__file__).resolve().parent
PBF_PATH = BACKEND_DIR / "panabo.pbf"
PBF_COMPETITOR_CACHE = {}
PBF_ALL_COMPETITORS = []
PBF_CACHE_LOADED = False
PBF_CACHE_LOCK = Lock()
PBF_LAYERS = ["points", "multipolygons", "lines", "multilinestrings"]
PBF_SEARCH_COLUMNS = ["amenity", "shop", "healthcare"]
PBF_ROAD_CONTEXT_GDF = None
PBF_BUILDING_CONTEXT_GDF = None
PBF_SPATIAL_CONTEXT_LOADED = False
PBF_SPATIAL_CONTEXT_LOCK = Lock()

ZONING_LAYERS = {
    "commercial_proper": (7.3000, 7.3150, 125.6700, 125.6900),
    "industrial_anflo": (7.2800, 7.2950, 125.6500, 125.6700)
}

VERIFIED_LOCAL_FEATURE_KINDS = {"msme", "anchor", "road", "building"}

# ==========================================
# AHP WEIGHTS CACHE
# ==========================================
# In-memory cache of admin-configured AHP weight configs, keyed by
# (level, category). Avoids a DB round-trip per perform_analysis() call, since
# citywide scans call perform_analysis() hundreds of times per scan across all
# MSME categories. Populated at startup (lifespan) and refreshed after every
# admin write.
_AHP_WEIGHTS_CACHE = {}
_AHP_WEIGHTS_CACHE_LOCK = Lock()


def _load_ahp_weights_cache():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            """
            SELECT level, category, criteria_labels, pairwise_matrix, priority_vector,
                   lambda_max, consistency_index, random_index, consistency_ratio,
                   is_consistent, updated_by_admin_email, updated_at
            FROM ahp_weight_configs
            """
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[AHP] Failed to load weights cache: {e}", flush=True)
        return

    new_cache = {}
    for row in rows:
        key = (row["level"], row["category"])
        new_cache[key] = {
            "criteria_labels": row["criteria_labels"],
            "pairwise_matrix": row["pairwise_matrix"],
            "priority_vector": row["priority_vector"],
            "lambda_max": row["lambda_max"],
            "ci": row["consistency_index"],
            "ri": row["random_index"],
            "cr": row["consistency_ratio"],
            "is_consistent": row["is_consistent"],
            "updated_by_admin_email": row["updated_by_admin_email"],
            "updated_at": row["updated_at"],
        }

    with _AHP_WEIGHTS_CACHE_LOCK:
        _AHP_WEIGHTS_CACHE.clear()
        _AHP_WEIGHTS_CACHE.update(new_cache)


def get_ahp_weights(level: str, category: str | None = None):
    """Returns the cached AHP config dict for (level, category), or None if not
    yet configured -- callers should fall back to static defaults in that case."""
    cache_key = (level, category or AHP_GLOBAL_CATEGORY_SENTINEL)
    with _AHP_WEIGHTS_CACHE_LOCK:
        return _AHP_WEIGHTS_CACHE.get(cache_key)


def _source_confidence_multiplier(source_name, confidence_score=None):
    normalized_source = normalize_osm_value(source_name)
    if normalized_source in {"verified_local", "verified", "manual_verified"}:
        base = 1.55
    elif normalized_source in {"custom_msme", "manual", "admin"}:
        base = 1.30
    else:
        base = 1.0

    confidence_value = to_finite_number(confidence_score)
    if confidence_value is None:
        return base

    confidence_scale = 0.75 + (max(0.0, min(100.0, confidence_value)) / 100.0) * 0.5
    return base * confidence_scale


def fetch_verified_local_features(feature_kind=None, business_type=None, active_only=True, cursor=None):
    # When a cursor is supplied, the caller owns the connection (and is
    # responsible for having already ensured the table exists) - this lets
    # callers that need several of these in a row (e.g.
    # evaluate_layered_market_context) share one connection instead of each
    # call opening/closing its own. Callers that don't pass one get today's
    # exact behavior, unchanged.
    owns_connection = cursor is None
    conn = None
    try:
        if owns_connection:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            ensure_verified_local_features_table(cursor)

        query = [
            "SELECT id, feature_kind, name, business_type, feature_subtype, latitude, longitude, road_class, power, building_type, landuse, area_m2, confidence_score, source_note, is_active, verified_at, created_by_admin_email, created_at, updated_at",
            "FROM verified_local_features",
            "WHERE 1 = 1",
        ]
        params = []

        if feature_kind:
            normalized_kind = normalize_osm_value(feature_kind)
            if normalized_kind in VERIFIED_LOCAL_FEATURE_KINDS:
                query.append("AND feature_kind = %s")
                params.append(normalized_kind)

        if business_type:
            query.append("AND LOWER(TRIM(COALESCE(business_type, ''))) = %s")
            params.append(normalize_osm_value(business_type))

        if active_only:
            query.append("AND is_active = TRUE")

        query.append("ORDER BY updated_at DESC, created_at DESC, id DESC")
        cursor.execute("\n".join(query), params)
        rows = cursor.fetchall()
        if conn is not None:
            cursor.close()
            conn.close()
        return rows
    except Exception as e:
        print(f"Verified local feature fetch error: {e}")
        return []

# Davao del Norte 5-year flood return period hazard zones
# Extracted from official NOAH/DENR flood hazard shapefile (DavaoDelNorte_Flood_5year.shp)
# Intersection with Panabo City bounds (7.269-7.333 lat, 125.636-125.742 lon)
# Severity levels: Var 1=Very High, Var 2=High, Var 3=Moderate
HAZARD_ZONES = {
    "flood": [
        {
            "name": "Very High Flood Hazard (5-Year Return Period)",
            "bounds": (7.269, 7.333, 125.636, 125.742),
            "score": 5
        },
        {
            "name": "High Flood Hazard (5-Year Return Period)",
            "bounds": (7.269, 7.333, 125.636, 125.73958735603416),
            "score": 12
        },
        {
            "name": "Moderate Flood Hazard (5-Year Return Period)",
            "bounds": (7.269, 7.333, 125.636, 125.7389400572897),
            "score": 18
        }
    ]
}

PANABO_BOUNDS = (7.269, 7.333, 125.636, 125.742)
HAZARD_LAYER_CACHE = []
HAZARD_LAYER_CACHE_LOADED = False
HAZARD_LAYER_LOCK = Lock()
HAZARD_LAYER_SOURCE = None
TREND_SCAN_CACHE = {}
TREND_SCAN_CACHE_LOCK = Lock()
TREND_SCAN_CACHE_TTL_SECONDS = int(os.environ.get("MARKETSCOPE_TREND_SCAN_CACHE_TTL_SECONDS", "21600"))
TREND_SCAN_CACHE_MAX_STALE_SECONDS = int(os.environ.get("MARKETSCOPE_TREND_SCAN_CACHE_MAX_STALE_SECONDS", "86400"))
TREND_SCAN_AUTO_REFRESH_INTERVAL_SECONDS = int(os.environ.get("MARKETSCOPE_TREND_SCAN_AUTO_REFRESH_INTERVAL_SECONDS", "7200"))
TREND_SCAN_REFRESH_IN_FLIGHT = set()


def _parse_utc_iso_z(value: str | None):
    raw = str(value or "").strip()
    if not raw:
        return None

    try:
        if raw.endswith("Z"):
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _is_snapshot_stale(payload: dict | list | None, threshold_seconds: int) -> bool:
    generated_raw = (payload or {}).get("generated_at") if isinstance(payload, dict) else None
    generated_at = _parse_utc_iso_z(generated_raw if isinstance(generated_raw, str) else None)
    if generated_at is None:
        return True

    age_seconds = (datetime.now(timezone.utc) - generated_at).total_seconds()
    return age_seconds > max(0, int(threshold_seconds))

HAZARD_LAYER_LABELS = {
    1: {"name": "Very High Flood Hazard (5-Year Return Period)", "score": 5},
    2: {"name": "High Flood Hazard (5-Year Return Period)", "score": 12},
    3: {"name": "Moderate Flood Hazard (5-Year Return Period)", "score": 18},
}


def _resolve_hazard_var(row, column_name):
    if not column_name:
        return None

    try:
        raw = row[column_name]
        if raw is None:
            return None
        return int(float(raw))
    except Exception:
        return None


def preload_hazard_layer_cache():
    global HAZARD_LAYER_CACHE, HAZARD_LAYER_CACHE_LOADED, HAZARD_LAYER_SOURCE

    if HAZARD_LAYER_CACHE_LOADED:
        return

    if gpd is None or Point is None or box is None or unary_union is None:
        HAZARD_LAYER_CACHE = []
        HAZARD_LAYER_SOURCE = None
        HAZARD_LAYER_CACHE_LOADED = True
        print("Hazard layer cache skipped: geopandas/shapely is unavailable")
        return

    with HAZARD_LAYER_LOCK:
        if HAZARD_LAYER_CACHE_LOADED:
            return

        candidates = [
            Path(__file__).resolve().parent / "flood-data" / "panabo_hazard_5yr.geojson",
            Path(__file__).resolve().parent / "panabo_hazard_5yr.geojson",
            Path(__file__).resolve().parent.parent / "marketscope-frontend" / "public" / "panabo_hazard_5yr.geojson",
            Path(__file__).resolve().parent / "DavaoDelNorte" / "DavaoDelNorte_Flood_5year.shp",
            Path(__file__).resolve().parent / "Davao_del_Norte.geojson",
        ]

        cache = []
        panabo_clip = box(PANABO_BOUNDS[2], PANABO_BOUNDS[0], PANABO_BOUNDS[3], PANABO_BOUNDS[1])

        for hazard_path in candidates:
            if not hazard_path.exists():
                continue

            try:
                hazard_gdf = gpd.read_file(hazard_path)
                if hazard_gdf.empty:
                    continue

                var_column = next((col for col in hazard_gdf.columns if str(col).strip().lower() == "var"), None)
                if not var_column:
                    print(f"Hazard layer skipped (missing Var field): {hazard_path}")
                    continue

                clipped = hazard_gdf.copy()
                clipped["geometry"] = clipped.geometry.intersection(panabo_clip)
                clipped = clipped[~clipped.geometry.is_empty]

                raw_geometries_by_var = {}

                for _, row in clipped.iterrows():
                    geometry = row.geometry
                    if geometry is None or geometry.is_empty:
                        continue

                    hazard_var = _resolve_hazard_var(row, var_column)
                    if hazard_var is None:
                        continue

                    label = HAZARD_LAYER_LABELS.get(hazard_var)
                    if label is None:
                        continue

                    raw_geometries_by_var.setdefault(hazard_var, []).append(geometry)

                # Remove overlaps by hazard priority so each point belongs to at most one flood class.
                covered_geometry = None
                for hazard_var, label in sorted(HAZARD_LAYER_LABELS.items(), key=lambda item: item[1]["score"]):
                    var_geometries = raw_geometries_by_var.get(hazard_var, [])
                    if not var_geometries:
                        continue

                    try:
                        merged_geometry = unary_union(var_geometries)
                    except Exception:
                        continue

                    if merged_geometry is None or merged_geometry.is_empty:
                        continue

                    exclusive_geometry = merged_geometry
                    if covered_geometry is not None and not covered_geometry.is_empty:
                        exclusive_geometry = merged_geometry.difference(covered_geometry)

                    if exclusive_geometry is None or exclusive_geometry.is_empty:
                        continue

                    cache.append({
                        "var": hazard_var,
                        "name": label["name"],
                        "score": label["score"],
                        "geometry": exclusive_geometry,
                    })

                    covered_geometry = (
                        exclusive_geometry
                        if covered_geometry is None
                        else covered_geometry.union(exclusive_geometry)
                    )

                if cache:
                    HAZARD_LAYER_SOURCE = str(hazard_path)
                    break
            except Exception as e:
                print(f"Hazard layer load warning for {hazard_path}: {e}")

        cache.sort(key=lambda item: item["score"])
        HAZARD_LAYER_CACHE = cache
        HAZARD_LAYER_CACHE_LOADED = True
        if HAZARD_LAYER_CACHE:
            print(f"Hazard layer cache loaded: {len(HAZARD_LAYER_CACHE)} polygon features from {HAZARD_LAYER_SOURCE}")
        else:
            print("Hazard layer cache loaded with 0 polygon features")


def evaluate_hazard(lat, lon):
    global HAZARD_LAYER_CACHE_LOADED

    # Recover from stale empty caches (for example if startup happened before files existed).
    if HAZARD_LAYER_CACHE_LOADED and not HAZARD_LAYER_CACHE:
        with HAZARD_LAYER_LOCK:
            if HAZARD_LAYER_CACHE_LOADED and not HAZARD_LAYER_CACHE:
                HAZARD_LAYER_CACHE_LOADED = False

    preload_hazard_layer_cache()

    hazard_score = 25
    hazard_status = "Low Risk / Safe"
    hazard_matches = []

    if HAZARD_LAYER_CACHE and Point is not None:
        location_point = Point(lon, lat)

        for feature in HAZARD_LAYER_CACHE:
            try:
                if feature["geometry"].intersects(location_point):
                    match_name = f"{feature['name']} (Flood)"
                    hazard_matches.append(match_name)
                    hazard_score = feature["score"]
                    hazard_status = match_name
                    break
            except Exception:
                continue

        if hazard_matches and hazard_status not in hazard_matches:
            hazard_matches.insert(0, hazard_status)

        return hazard_score, hazard_status, hazard_matches

    # Do not fallback to temporary rectangular proxies; avoid false positives.
    return hazard_score, hazard_status, hazard_matches

PANABO_ANCHORS = [
    {"name": "Integrated Bus and Jeepney Terminal", "lat": 7.298318, "lon": 125.680099, "power": 25},
    {"name": "Panabo District Hospital", "lat": 7.298534, "lon": 125.681971, "power": 5},
    {"name": "LandBank", "lat": 7.302614, "lon": 125.681888, "power": 15},
    {"name": "Panabo Public Market", "lat": 7.306480, "lon": 125.683457, "power": 15},
    {"name": "Davao del Norte State College", "lat": 7.313671, "lon": 125.670372, "power": 20},
    {"name": "Central Market", "lat": 7.300987, "lon": 125.682584, "power": 25},
    {"name": "Panabo Park", "lat": 7.299585, "lon": 125.681187, "power": 15},
    {"name": "University of Mindanao Panabo", "lat": 7.304490, "lon": 125.679607, "power": 25}
]

SME_DATABASE = {
    "coffee": {"key": "amenity", "val": "cafe", "fear": 6, "need": 9, "name": "Coffee Shops", "osm_tags": [("amenity", "cafe"), ("shop", "coffee")]},
    "print": {"key": "shop", "val": "copyshop", "fear": 7, "need": 6, "name": "Print/Copy Centers", "osm_tags": [("shop", "copyshop"), ("shop", "stationery"), ("shop", "books")]},
    "laundry": {"key": "shop", "val": "laundry", "fear": 9, "need": 7, "name": "Laundry Shops", "osm_tags": [("shop", "laundry"), ("shop", "dry_cleaning")]},
    "carwash": {"key": "amenity", "val": "car_wash", "fear": 8, "need": 9, "name": "Car Washes", "osm_tags": [("amenity", "car_wash"), ("shop", "car_repair")]},
    "kiosk": {"key": "amenity", "val": "fast_food", "fear": 6, "need": 9, "name": "Food Kiosks/Stalls", "osm_tags": [("amenity", "fast_food"), ("amenity", "food_court"), ("shop", "kiosk")]},
    "water": {"key": "shop", "val": "water", "fear": 4, "need": 7, "name": "Water Refilling Stations", "osm_tags": [("shop", "water"), ("amenity", "drinking_water"), ("amenity", "water_point")]},
    "bakery": {"key": "shop", "val": "bakery", "fear": 8, "need": 9, "name": "Bakeries", "osm_tags": [("shop", "bakery"), ("shop", "pastry")]},
    "pharmacy": {"key": "amenity", "val": "pharmacy", "fear": 7, "need": 9, "name": "Small Pharmacies", "osm_tags": [("amenity", "pharmacy"), ("shop", "chemist")]},
    "barber": {"key": "shop", "val": "hairdresser", "fear": 7, "need": 9, "name": "Barbershops/Salons", "osm_tags": [("shop", "hairdresser"), ("shop", "beauty")]},
    "moto": {"key": "shop", "val": "motorcycle_repair", "fear": 5, "need": 8, "name": "Motorcycle Repair Shops", "osm_tags": [("shop", "motorcycle"), ("shop", "motorcycle_repair"), ("shop", "car_repair")]},
    "internet": {"key": "amenity", "val": "internet_cafe", "fear": 6, "need": 6, "name": "Internet Cafes", "osm_tags": [("amenity", "internet_cafe"), ("amenity", "cafe")]},
    "meat": {"key": "shop", "val": "butcher", "fear": 9, "need": 9, "name": "Meat Shops", "osm_tags": [("shop", "butcher"), ("shop", "deli")]},
    "hardware": {"key": "shop", "val": "hardware", "fear": 7, "need": 8, "name": "Hardware/Construction Supplies", "osm_tags": [("shop", "hardware"), ("shop", "doityourself"), ("shop", "trade")]}
}

MSME_CATEGORY_PROFILES = {
    "coffee": {
        "display_name": "Coffee Shops",
        "osm_tags": [("amenity", "cafe"), ("shop", "coffee")],
        "competition_sensitivity": 1.38,
        "competition_weight": 0.47,
        "road_weight": 0.20,
        "anchor_weight": 0.19,
        "building_weight": 0.14,
        "preferred_road_classes": ["secondary", "tertiary", "primary"],
        "required_road_classes": ["secondary", "tertiary", "primary"],
        "road_distance_soft_cap_m": 700.0,
        "anchor_scale_m": 300.0,
        "anchor_target_power": 40.0,
        "building_radius_scale_m": 360.0,
    },
    "print": {
        "display_name": "Print/Copy Centers",
        "osm_tags": [("shop", "copyshop"), ("shop", "stationery"), ("shop", "books")],
        "competition_sensitivity": 1.12,
        "competition_weight": 0.42,
        "road_weight": 0.23,
        "anchor_weight": 0.18,
        "building_weight": 0.17,
        "preferred_road_classes": ["tertiary", "secondary", "primary"],
        "required_road_classes": ["tertiary", "secondary", "primary"],
        "road_distance_soft_cap_m": 820.0,
        "anchor_scale_m": 340.0,
        "anchor_target_power": 34.0,
        "building_radius_scale_m": 420.0,
    },
    "laundry": {
        "display_name": "Laundry Shops",
        "osm_tags": [("shop", "laundry"), ("shop", "dry_cleaning")],
        "competition_sensitivity": 1.18,
        "competition_weight": 0.43,
        "road_weight": 0.20,
        "anchor_weight": 0.19,
        "building_weight": 0.18,
        "preferred_road_classes": ["secondary", "tertiary", "primary"],
        "required_road_classes": ["secondary", "tertiary", "primary"],
        "road_distance_soft_cap_m": 780.0,
        "anchor_scale_m": 320.0,
        "anchor_target_power": 36.0,
        "building_radius_scale_m": 420.0,
    },
    "carwash": {
        "display_name": "Car Washes",
        "osm_tags": [("amenity", "car_wash"), ("shop", "car_repair")],
        "competition_sensitivity": 1.10,
        "competition_weight": 0.39,
        "road_weight": 0.28,
        "anchor_weight": 0.16,
        "building_weight": 0.17,
        "preferred_road_classes": ["trunk", "primary", "secondary"],
        "required_road_classes": ["trunk", "primary", "secondary"],
        "road_distance_soft_cap_m": 920.0,
        "anchor_scale_m": 360.0,
        "anchor_target_power": 38.0,
        "building_radius_scale_m": 450.0,
    },
    "kiosk": {
        "display_name": "Food Kiosks/Stalls",
        "osm_tags": [("amenity", "fast_food"), ("amenity", "food_court"), ("shop", "kiosk")],
        "competition_sensitivity": 1.34,
        "competition_weight": 0.44,
        "road_weight": 0.18,
        "anchor_weight": 0.22,
        "building_weight": 0.16,
        "preferred_road_classes": ["primary", "secondary", "tertiary"],
        "required_road_classes": ["primary", "secondary", "tertiary"],
        "road_distance_soft_cap_m": 650.0,
        "anchor_scale_m": 280.0,
        "anchor_target_power": 42.0,
        "building_radius_scale_m": 340.0,
    },
    "water": {
        "display_name": "Water Refilling Stations",
        "osm_tags": [("shop", "water"), ("amenity", "drinking_water"), ("amenity", "water_point")],
        "competition_sensitivity": 0.98,
        "competition_weight": 0.36,
        "road_weight": 0.22,
        "anchor_weight": 0.18,
        "building_weight": 0.24,
        "preferred_road_classes": ["residential", "service", "tertiary", "secondary"],
        "required_road_classes": ["residential", "service", "tertiary", "secondary"],
        "road_distance_soft_cap_m": 860.0,
        "anchor_scale_m": 360.0,
        "anchor_target_power": 30.0,
        "building_radius_scale_m": 460.0,
    },
    "bakery": {
        "display_name": "Bakeries",
        "osm_tags": [("shop", "bakery"), ("shop", "pastry")],
        "competition_sensitivity": 1.28,
        "competition_weight": 0.44,
        "road_weight": 0.20,
        "anchor_weight": 0.19,
        "building_weight": 0.17,
        "preferred_road_classes": ["secondary", "tertiary", "primary"],
        "required_road_classes": ["secondary", "tertiary", "primary"],
        "road_distance_soft_cap_m": 760.0,
        "anchor_scale_m": 320.0,
        "anchor_target_power": 38.0,
        "building_radius_scale_m": 380.0,
    },
    "pharmacy": {
        "display_name": "Small Pharmacies",
        "osm_tags": [("amenity", "pharmacy"), ("shop", "chemist")],
        "competition_sensitivity": 1.22,
        "competition_weight": 0.43,
        "road_weight": 0.21,
        "anchor_weight": 0.22,
        "building_weight": 0.14,
        "preferred_road_classes": ["secondary", "tertiary", "primary"],
        "required_road_classes": ["secondary", "tertiary", "primary"],
        "road_distance_soft_cap_m": 720.0,
        "anchor_scale_m": 300.0,
        "anchor_target_power": 40.0,
        "building_radius_scale_m": 340.0,
    },
    "barber": {
        "display_name": "Barbershops/Salons",
        "osm_tags": [("shop", "hairdresser"), ("shop", "beauty")],
        "competition_sensitivity": 1.24,
        "competition_weight": 0.45,
        "road_weight": 0.19,
        "anchor_weight": 0.20,
        "building_weight": 0.16,
        "preferred_road_classes": ["secondary", "tertiary", "primary"],
        "required_road_classes": ["secondary", "tertiary", "primary"],
        "road_distance_soft_cap_m": 760.0,
        "anchor_scale_m": 320.0,
        "anchor_target_power": 39.0,
        "building_radius_scale_m": 360.0,
    },
    "moto": {
        "display_name": "Motorcycle Repair Shops",
        "osm_tags": [("shop", "motorcycle"), ("shop", "motorcycle_repair"), ("shop", "car_repair")],
        "competition_sensitivity": 1.06,
        "competition_weight": 0.40,
        "road_weight": 0.30,
        "anchor_weight": 0.14,
        "building_weight": 0.16,
        "preferred_road_classes": ["trunk", "primary", "secondary"],
        "required_road_classes": ["trunk", "primary", "secondary"],
        "road_distance_soft_cap_m": 980.0,
        "anchor_scale_m": 380.0,
        "anchor_target_power": 32.0,
        "building_radius_scale_m": 430.0,
    },
    "internet": {
        "display_name": "Internet Cafes",
        "osm_tags": [("amenity", "internet_cafe"), ("amenity", "cafe")],
        "competition_sensitivity": 1.15,
        "competition_weight": 0.41,
        "road_weight": 0.21,
        "anchor_weight": 0.20,
        "building_weight": 0.18,
        "preferred_road_classes": ["secondary", "tertiary", "primary"],
        "required_road_classes": ["secondary", "tertiary", "primary"],
        "road_distance_soft_cap_m": 760.0,
        "anchor_scale_m": 330.0,
        "anchor_target_power": 34.0,
        "building_radius_scale_m": 400.0,
    },
    "meat": {
        "display_name": "Meat Shops",
        "osm_tags": [("shop", "butcher"), ("shop", "deli")],
        "competition_sensitivity": 1.20,
        "competition_weight": 0.42,
        "road_weight": 0.20,
        "anchor_weight": 0.20,
        "building_weight": 0.18,
        "preferred_road_classes": ["secondary", "tertiary", "primary"],
        "required_road_classes": ["secondary", "tertiary", "primary"],
        "road_distance_soft_cap_m": 740.0,
        "anchor_scale_m": 300.0,
        "anchor_target_power": 35.0,
        "building_radius_scale_m": 360.0,
    },
    "hardware": {
        "display_name": "Hardware/Construction Supplies",
        "osm_tags": [("shop", "hardware"), ("shop", "doityourself"), ("shop", "trade")],
        "competition_sensitivity": 1.04,
        "competition_weight": 0.40,
        "road_weight": 0.30,
        "anchor_weight": 0.14,
        "building_weight": 0.16,
        "preferred_road_classes": ["trunk", "primary", "secondary"],
        "required_road_classes": ["trunk", "primary", "secondary"],
        "road_distance_soft_cap_m": 1000.0,
        "anchor_scale_m": 420.0,
        "anchor_target_power": 30.0,
        "building_radius_scale_m": 460.0,
    },
}

SME_PROFILE_BY_NAME = {
    str(profile.get("name") or "").strip().lower(): key
    for key, profile in SME_DATABASE.items()
    if str(profile.get("name") or "").strip()
}

PBF_NAME_KEYWORD_FALLBACK = {
    "coffee": ["coffee", "cafe"],
    "print": ["print", "copy", "xerox"],
    "laundry": ["laundry", "wash", "dry clean"],
    "carwash": ["car wash", "autowash", "auto spa"],
    "kiosk": ["kiosk", "snack", "food"],
    "water": ["water refilling", "water station", "purified water"],
    "bakery": ["bakery", "bakeshop", "bread"],
    "pharmacy": ["pharmacy", "drugstore", "mercury"],
    "barber": ["barber", "salon", "hair"],
    "moto": ["motor", "motorcycle", "moto", "repair"],
    "internet": ["internet", "computer", "cyber"],
    "meat": ["meat", "butcher"],
    "hardware": ["hardware", "construction", "tools"],
}

COMMERCIAL_AMENITY_VALUES = {
    "cafe", "restaurant", "fast_food", "food_court", "pharmacy", "bank", "fuel", "marketplace",
    "car_wash", "clinic", "hospital", "internet_cafe", "bar", "pub", "biergarten"
}

ROAD_CLASS_BASE_SCORES = {
    "motorway": 25,
    "trunk": 24,
    "primary": 23,
    "secondary": 21,
    "tertiary": 18,
    "unclassified": 15,
    "living_street": 13,
    "residential": 11,
    "service": 8,
    "track": 6,
    "path": 4,
    "footway": 3,
    "cycleway": 4,
    "pedestrian": 5,
}

DEFAULT_MSME_ANALYSIS_PROFILE = {
    "display_name": "MSME",
    "osm_tags": [("shop", "convenience")],
    "competition_sensitivity": 1.0,
    "competition_weight": 0.42,
    "road_weight": 0.23,
    "anchor_weight": 0.20,
    "building_weight": 0.15,
    "preferred_road_classes": ["primary", "secondary", "tertiary"],
    "required_road_classes": ["primary", "secondary", "tertiary"],
    "road_distance_soft_cap_m": 850.0,
    "anchor_scale_m": 320.0,
    "anchor_target_power": 36.0,
    "building_radius_scale_m": 420.0,
}

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lon2 - lon1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def check_inside_bounds(lat, lon, bounds):
    min_lat, max_lat, min_lon, max_lon = bounds
    return min_lat <= lat <= max_lat and min_lon <= lon <= max_lon


def normalize_osm_value(value):
    if value is None:
        return None
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
    except Exception:
        pass

    normalized = str(value).strip().lower()
    return normalized or None


def to_finite_number(value):
    try:
        parsed = float(value)
    except Exception:
        return None

    if math.isfinite(parsed):
        return parsed
    return None


def _clamp_score(value, minimum=0, maximum=25):
    try:
        numeric = float(value)
    except Exception:
        numeric = minimum
    return max(minimum, min(maximum, numeric))


def _normalize_road_class(value):
    normalized = normalize_osm_value(value)
    if normalized is None:
        return None

    normalized = normalized.replace("-", "_")
    normalized = normalized.replace(" ", "_")
    normalized = normalized.replace("__", "_")

    if normalized.endswith("_link"):
        normalized = normalized[:-5]

    if normalized in ROAD_CLASS_BASE_SCORES:
        return normalized

    if normalized in {"road", "street", "lane"}:
        return "unclassified"
    if normalized in {"main", "main_road", "major_road"}:
        return "primary"
    return None


def _approx_polygon_area_m2(geometry):
    if geometry is None or geometry.is_empty:
        return 0.0

    try:
        area_degrees = float(getattr(geometry, "area", 0.0) or 0.0)
        centroid_lat = float(geometry.centroid.y)
        meters_per_deg_lat = 111132.92
        meters_per_deg_lon = 111412.84 * math.cos(math.radians(centroid_lat))
        return abs(area_degrees) * abs(meters_per_deg_lat) * max(1.0, abs(meters_per_deg_lon))
    except Exception:
        return 0.0


def _feature_weight_from_building_row(row):
    building_value = normalize_osm_value(row.get("building"))
    landuse_value = normalize_osm_value(row.get("landuse"))
    amenity_value = normalize_osm_value(row.get("amenity"))
    shop_value = normalize_osm_value(row.get("shop"))
    office_value = normalize_osm_value(row.get("office"))

    weight = 1.0

    if building_value in {"commercial", "retail", "industrial", "public", "university", "hospital", "school", "office"}:
        weight *= 1.20
    elif building_value in {"house", "residential", "apartments", "roof"}:
        weight *= 0.86

    if landuse_value in {"commercial", "retail"}:
        weight *= 1.28
    elif landuse_value == "industrial":
        weight *= 1.14
    elif landuse_value == "residential":
        weight *= 0.88

    if amenity_value in {"marketplace", "hospital", "school", "college", "university", "fuel", "parking", "restaurant", "fast_food", "cafe"}:
        weight *= 1.12

    if shop_value:
        weight *= 1.10

    if office_value:
        weight *= 1.05

    return weight


def preload_pbf_spatial_context_cache():
    global PBF_ROAD_CONTEXT_GDF, PBF_BUILDING_CONTEXT_GDF, PBF_SPATIAL_CONTEXT_LOADED

    if PBF_SPATIAL_CONTEXT_LOADED:
        return

    if gpd is None:
        PBF_ROAD_CONTEXT_GDF = None
        PBF_BUILDING_CONTEXT_GDF = None
        PBF_SPATIAL_CONTEXT_LOADED = True
        print("PBF spatial context cache skipped: geopandas is unavailable")
        return

    with PBF_SPATIAL_CONTEXT_LOCK:
        if PBF_SPATIAL_CONTEXT_LOADED:
            return

        if not PBF_PATH.exists():
            PBF_ROAD_CONTEXT_GDF = None
            PBF_BUILDING_CONTEXT_GDF = None
            PBF_SPATIAL_CONTEXT_LOADED = True
            print(f"PBF spatial context cache skipped: file not found at {PBF_PATH}")
            return

        road_gdf = None
        building_gdf = None

        try:
            road_gdf = gpd.read_file(str(PBF_PATH), layer="lines", engine="pyogrio")
        except Exception as exc:
            print(f"PBF road context read skipped: {exc}")

        if road_gdf is not None and not road_gdf.empty and "geometry" in road_gdf.columns and "highway" in road_gdf.columns:
            road_gdf = road_gdf[road_gdf["geometry"].notna() & road_gdf["highway"].notna()].copy()
            road_gdf["road_class"] = road_gdf["highway"].apply(_normalize_road_class)
            road_gdf = road_gdf[road_gdf["road_class"].notna()].copy()
            road_gdf["road_base_score"] = road_gdf["road_class"].map(ROAD_CLASS_BASE_SCORES).fillna(10)
            PBF_ROAD_CONTEXT_GDF = road_gdf[["name", "highway", "road_class", "road_base_score", "geometry"]].copy()
        else:
            PBF_ROAD_CONTEXT_GDF = None

        try:
            building_gdf = gpd.read_file(str(PBF_PATH), layer="multipolygons", engine="pyogrio")
        except Exception as exc:
            print(f"PBF building context read skipped: {exc}")

        if building_gdf is not None and not building_gdf.empty and "geometry" in building_gdf.columns:
            context_columns = [col for col in ["name", "building", "landuse", "amenity", "shop", "office", "geometry"] if col in building_gdf.columns]
            building_gdf = building_gdf[context_columns].copy()
            context_mask = False
            for col in ["building", "landuse", "amenity", "shop", "office"]:
                if col in building_gdf.columns:
                    context_mask = context_mask | building_gdf[col].notna()
            building_gdf = building_gdf[context_mask & building_gdf["geometry"].notna()].copy()
            if not building_gdf.empty:
                building_gdf["feature_weight"] = building_gdf.apply(_feature_weight_from_building_row, axis=1)
                PBF_BUILDING_CONTEXT_GDF = building_gdf[["name", "building", "landuse", "amenity", "shop", "office", "feature_weight", "geometry"]].copy()
            else:
                PBF_BUILDING_CONTEXT_GDF = None
        else:
            PBF_BUILDING_CONTEXT_GDF = None

        PBF_SPATIAL_CONTEXT_LOADED = True
        print(
            "PBF spatial context loaded: "
            f"roads={0 if PBF_ROAD_CONTEXT_GDF is None else len(PBF_ROAD_CONTEXT_GDF)}, "
            f"buildings={0 if PBF_BUILDING_CONTEXT_GDF is None else len(PBF_BUILDING_CONTEXT_GDF)}"
        )


def _get_analysis_profile(business_type: str | None):
    profile_key = normalize_osm_value(business_type)
    if not profile_key:
        return DEFAULT_MSME_ANALYSIS_PROFILE
    return MSME_CATEGORY_PROFILES.get(profile_key, DEFAULT_MSME_ANALYSIS_PROFILE)


def _query_context_candidates(gdf, lat, lon, radius_meters, fallback_multiplier=1.35):
    if gdf is None or Point is None or box is None:
        return None

    search_radius = max(150.0, float(radius_meters) * float(fallback_multiplier))
    lon_delta = search_radius / max(1.0, 111320.0 * max(0.2, math.cos(math.radians(lat))))
    lat_delta = search_radius / 111132.0
    search_box = box(lon - lon_delta, lat - lat_delta, lon + lon_delta, lat + lat_delta)

    if getattr(gdf, "sindex", None) is not None:
        try:
            candidate_index = list(gdf.sindex.intersection(search_box.bounds))
            if candidate_index:
                return gdf.iloc[candidate_index]
        except Exception:
            pass

    return gdf


def _score_competitor_density(lat, lon, competitors, radius_meters, profile):
    weighted_pressure = 0.0
    nearby_competitors = []
    decay_scale = max(1.0, float(radius_meters) * 0.42)

    for competitor in competitors:
        competitor_lat = to_finite_number(competitor.get("lat"))
        competitor_lon = to_finite_number(competitor.get("lon"))
        if competitor_lat is None or competitor_lon is None:
            continue

        distance_m = calculate_distance(lat, lon, competitor_lat, competitor_lon)
        if distance_m > radius_meters:
            continue

        distance_decay = 1.0 / (1.0 + (distance_m / decay_scale))
        radial_band = 1.0 if distance_m <= radius_meters * 0.33 else 0.72 if distance_m <= radius_meters * 0.66 else 0.48
        source_name = str(competitor.get("name") or "").strip()
        source_weight = 1.15 if source_name else 1.0
        source_weight *= _source_confidence_multiplier(competitor.get("source"), competitor.get("confidence_score"))

        weighted_pressure += distance_decay * radial_band * source_weight
        nearby_competitors.append({
            "lat": competitor_lat,
            "lon": competitor_lon,
            "name": source_name or None,
            "distance_m": round(distance_m, 2),
            "source": competitor.get("source") or "osm",
        })

    competition_intensity = math.log1p(weighted_pressure * float(profile.get("competition_sensitivity") or 1.0))
    score = _clamp_score(25 - (competition_intensity * 7.0), 0, 25)

    if score >= 20:
        status = "Light Competition"
    elif score >= 15:
        status = "Manageable Competition"
    elif score >= 10:
        status = "Noticeable Competition"
    elif score >= 5:
        status = "Heavy Competition"
    else:
        status = "Highly Saturated"

    details = (
        f"Weighted competitor pressure within {radius_meters} meters is {weighted_pressure:.2f}. "
        f"The engine dampens distant points with radial decay and multi-band weighting before converting the pressure to a 0-25 inverse-density score."
    )

    return {
        "score": round(score),
        "status": status,
        "details": details,
        "weighted_pressure": round(weighted_pressure, 3),
        "competitor_count": len(nearby_competitors),
        "nearby_competitors": nearby_competitors,
    }


def _score_road_access(lat, lon, radius_meters, profile, verified_roads=None):
    verified_roads = verified_roads or []

    best_verified = None
    soft_cap = float(profile.get("road_distance_soft_cap_m") or 850.0)
    preferred_classes = set(profile.get("preferred_road_classes") or [])
    required_classes = set(profile.get("required_road_classes") or [])

    for road in verified_roads:
        road_lat = to_finite_number(road.get("latitude"))
        road_lon = to_finite_number(road.get("longitude"))
        if road_lat is None or road_lon is None:
            continue

        distance_m = calculate_distance(lat, lon, road_lat, road_lon)
        if distance_m > radius_meters:
            continue

        road_class = normalize_osm_value(road.get("road_class") or road.get("feature_subtype"))
        road_name = str(road.get("name") or "").strip() or None
        road_base_score = float(ROAD_CLASS_BASE_SCORES.get(road_class or "", 10))
        distance_factor = max(0.34, 1.0 - (distance_m / max(1.0, soft_cap)))
        score = road_base_score * distance_factor * _source_confidence_multiplier("verified_local", road.get("confidence_score"))

        if road_class in preferred_classes:
            score += 2.5
        elif road_class in required_classes:
            score += 1.0
        else:
            score -= 2.0

        if distance_m <= 120:
            score += 1.5
        elif distance_m <= 300:
            score += 0.75
        elif distance_m > soft_cap:
            score -= 1.5

        score = round(_clamp_score(score, 0, 25))

        if best_verified is None or score > best_verified["score"] or (score == best_verified["score"] and distance_m < best_verified["distance_m"]):
            best_verified = {
                "score": score,
                "road_class": road_class,
                "road_name": road_name,
                "distance_m": distance_m,
            }

    if best_verified is not None:
        if best_verified["score"] >= 20:
            status = "Excellent Road Access"
        elif best_verified["score"] >= 15:
            status = "Good Road Access"
        elif best_verified["score"] >= 10:
            status = "Moderate Road Access"
        elif best_verified["score"] >= 5:
            status = "Limited Road Access"
        else:
            status = "Poor Road Access"

        road_label = best_verified["road_class"] or "verified local road"
        details = (
            f"A manually verified road record was found approximately {best_verified['distance_m']:.1f} meters away. "
            f"Its class is {road_label}, and the score uses the verified local source hierarchy before falling back to OSM geometry."
        )

        return {
            "score": best_verified["score"],
            "status": status,
            "details": details,
            "road_class": best_verified["road_class"],
            "road_name": best_verified["road_name"],
            "distance_m": round(best_verified["distance_m"], 2),
        }

    if PBF_ROAD_CONTEXT_GDF is None or Point is None:
        return {
            "score": 12,
            "status": "Road Context Unavailable",
            "details": "Road geometry context could not be loaded, so the engine used a neutral accessibility fallback.",
            "road_class": None,
            "road_name": None,
            "distance_m": None,
        }

    candidates = _query_context_candidates(PBF_ROAD_CONTEXT_GDF, lat, lon, radius_meters, fallback_multiplier=1.8)
    if candidates is None or candidates.empty:
        return {
            "score": 12,
            "status": "Road Context Unavailable",
            "details": "No road candidates were found in the scan window, so the engine used a neutral accessibility fallback.",
            "road_class": None,
            "road_name": None,
            "distance_m": None,
        }

    origin = Point(lon, lat)
    best_candidate = None
    best_distance = None

    for _, row in candidates.iterrows():
        geometry = row.geometry
        if geometry is None or geometry.is_empty:
            continue

        try:
            nearest_point = nearest_points(origin, geometry)[1] if nearest_points is not None else geometry.representative_point()
            distance_m = calculate_distance(lat, lon, nearest_point.y, nearest_point.x)
        except Exception:
            continue

        if best_distance is None or distance_m < best_distance:
            best_distance = distance_m
            best_candidate = row

    if best_candidate is None or best_distance is None:
        return {
            "score": 12,
            "status": "Road Context Unavailable",
            "details": "The scan could not determine a stable nearest road geometry, so the engine used a neutral accessibility fallback.",
            "road_class": None,
            "road_name": None,
            "distance_m": None,
        }

    road_class = normalize_osm_value(best_candidate.get("road_class"))
    road_name = str(best_candidate.get("name") or "").strip() or None
    road_base_score_value = None
    try:
        road_base_score_value = best_candidate["road_base_score"]
    except Exception:
        road_base_score_value = None
    road_base_score = float(road_base_score_value or ROAD_CLASS_BASE_SCORES.get(road_class or "", 10))
    distance_factor = max(0.34, 1.0 - (best_distance / max(1.0, soft_cap)))

    score = road_base_score * distance_factor
    preferred_classes = set(profile.get("preferred_road_classes") or [])
    required_classes = set(profile.get("required_road_classes") or [])

    if road_class in preferred_classes:
        score += 2.5
    elif road_class in required_classes:
        score += 1.0
    else:
        score -= 2.5

    if best_distance <= 120:
        score += 1.5
    elif best_distance <= 300:
        score += 0.75
    elif best_distance > soft_cap:
        score -= 1.5

    score = round(_clamp_score(score, 0, 25))

    if score >= 20:
        status = "Excellent Road Access"
    elif score >= 15:
        status = "Good Road Access"
    elif score >= 10:
        status = "Moderate Road Access"
    elif score >= 5:
        status = "Limited Road Access"
    else:
        status = "Poor Road Access"

    road_label = road_class or "unknown"
    details = (
        f"The nearest road is {road_name or 'an unnamed road'} classified as {road_label}. "
        f"It is approximately {best_distance:.1f} meters away, and the accessibility score is dampened by distance plus category road preference rules."
    )

    return {
        "score": score,
        "status": status,
        "details": details,
        "road_class": road_class,
        "road_name": road_name,
        "distance_m": round(best_distance, 2),
    }


def _score_anchor_proximity(lat, lon, radius_meters, profile, verified_anchors=None):
    weighted_anchor_power = 0.0
    nearby_anchors = []
    scale = max(1.0, float(profile.get("anchor_scale_m") or 320.0))

    anchor_sources = list(verified_anchors or []) + list(PANABO_ANCHORS)

    for anchor in anchor_sources:
        anchor_lat = to_finite_number(anchor.get("lat"))
        anchor_lon = to_finite_number(anchor.get("lon"))
        if anchor_lat is None or anchor_lon is None:
            continue

        distance_m = calculate_distance(lat, lon, anchor_lat, anchor_lon)
        if distance_m > radius_meters:
            continue

        power = float(anchor.get("power") or 0.0)
        distance_decay = 1.0 / (1.0 + (distance_m / scale))
        weighted_anchor_power += power * distance_decay * _source_confidence_multiplier(anchor.get("source"), anchor.get("confidence_score"))
        nearby_anchors.append({
            "name": anchor.get("name"),
            "distance_m": round(distance_m, 2),
            "power": power,
            "source": anchor.get("source") or "osm",
        })

    target_power = float(profile.get("anchor_target_power") or 36.0)
    demand_ratio = (weighted_anchor_power / max(1.0, target_power)) * 25.0
    score = round(_clamp_score(demand_ratio, 0, 25))

    if score >= 20:
        status = "Strong Traffic Generators"
    elif score >= 15:
        status = "Moderate Traffic Generators"
    elif score >= 10:
        status = "Mixed Traffic Support"
    elif score >= 5:
        status = "Weak Traffic Support"
    else:
        status = "Low Visibility"

    details = (
        f"The engine sums nearby anchor power using inverse-distance decay and normalizes the result against a category target of {target_power:.1f}. "
        f"Weighted anchor power inside the radius is {weighted_anchor_power:.2f}."
    )

    return {
        "score": score,
        "status": status,
        "details": details,
        "weighted_anchor_power": round(weighted_anchor_power, 3),
        "anchors_found": [item.get("name") for item in nearby_anchors if item.get("name")],
        "nearby_anchors": nearby_anchors,
    }


def _score_building_density(lat, lon, radius_meters, profile, verified_buildings=None):
    weighted_intensity = 0.0
    matched_features = []
    scale = max(1.0, float(profile.get("building_radius_scale_m") or radius_meters or 420.0))

    for building in verified_buildings or []:
        building_lat = to_finite_number(building.get("latitude"))
        building_lon = to_finite_number(building.get("longitude"))
        if building_lat is None or building_lon is None:
            continue

        distance_m = calculate_distance(lat, lon, building_lat, building_lon)
        if distance_m > radius_meters:
            continue

        distance_decay = 1.0 / (1.0 + (distance_m / scale))
        feature_weight = float(building.get("feature_weight") or 1.0)
        area_m2 = to_finite_number(building.get("area_m2")) or 0.0
        area_bonus = 1.0 + min(2.0, area_m2 / 2500.0) * 0.2
        feature_weight *= _source_confidence_multiplier("verified_local", building.get("confidence_score"))

        weighted_intensity += feature_weight * distance_decay * area_bonus
        matched_features.append({
            "name": building.get("name"),
            "distance_m": round(distance_m, 2),
            "feature_weight": round(feature_weight, 2),
            "area_m2": round(area_m2, 2),
            "source": building.get("source") or "verified_local",
        })

    if PBF_BUILDING_CONTEXT_GDF is not None and Point is not None:
        candidates = _query_context_candidates(PBF_BUILDING_CONTEXT_GDF, lat, lon, radius_meters, fallback_multiplier=1.55)
    else:
        candidates = None

    if candidates is None or candidates.empty:
        if not matched_features:
            return {
                "score": 12,
                "status": "Building Context Unavailable",
                "details": "Building footprint context could not be loaded, so the engine used a neutral built-form fallback.",
                "weighted_intensity": 0.0,
                "matched_features": [],
            }
    else:
        for _, row in candidates.iterrows():
            geometry = row.geometry
            if geometry is None or geometry.is_empty:
                continue

            try:
                feature_point = geometry.representative_point() if hasattr(geometry, "representative_point") else geometry.centroid
                distance_m = calculate_distance(lat, lon, feature_point.y, feature_point.x)
            except Exception:
                continue

            if distance_m > radius_meters:
                continue

            distance_decay = 1.0 / (1.0 + (distance_m / scale))
            feature_weight = float(row.get("feature_weight") or 1.0)
            area_m2 = _approx_polygon_area_m2(geometry)
            area_bonus = 1.0 + min(2.0, area_m2 / 2500.0) * 0.18

            weighted_intensity += feature_weight * distance_decay * area_bonus
            matched_features.append({
                "name": row.get("name"),
                "distance_m": round(distance_m, 2),
                "feature_weight": round(feature_weight, 2),
                "area_m2": round(area_m2, 2),
                "source": "osm",
            })

    density_score = math.log1p(weighted_intensity * float(profile.get("building_weight") or 0.15)) * 8.5
    score = round(_clamp_score(density_score, 0, 25))

    if score >= 20:
        status = "Dense Built Environment"
    elif score >= 15:
        status = "Moderately Built-Up"
    elif score >= 10:
        status = "Balanced Built Form"
    elif score >= 5:
        status = "Sparse Built Form"
    else:
        status = "Very Sparse Built Form"

    details = (
        f"The engine measures built-form intensity from nearby building footprints, land-use polygons, and amenity clusters within {radius_meters} meters. "
        f"Weighted built intensity is {weighted_intensity:.2f}, then converted to a 0-25 density proxy.")

    return {
        "score": score,
        "status": status,
        "details": details,
        "weighted_intensity": round(weighted_intensity, 3),
        "matched_features": matched_features,
    }


def evaluate_layered_market_context(lat, lon, radius_meters, business_type):
    profile_key = normalize_osm_value(business_type)
    profile_key_safe = profile_key or ""
    profile = MSME_CATEGORY_PROFILES.get(profile_key_safe, DEFAULT_MSME_ANALYSIS_PROFILE)
    osm_tags = profile.get("osm_tags") or SME_DATABASE.get(profile_key_safe, {}).get("osm_tags") or [("shop", "convenience")]

    competitors_list = []
    competitor_dedupe = set()
    verified_competitors = []
    verified_roads = []
    verified_anchors = []
    verified_buildings = []

    # Share one DB connection across the several verified-feature/custom-MSME
    # lookups below instead of each one opening/closing its own (this used to
    # be up to 5 fresh connections - plus a 13-statement schema-ensure re-run
    # on every one of them - per /analyze call). If the shared connection
    # can't be opened, shared_cursor stays None and every call below falls
    # back to opening its own connection, exactly like before this change.
    shared_conn = None
    shared_cursor = None
    try:
        shared_conn = psycopg2.connect(**DB_CONFIG)
        shared_cursor = shared_conn.cursor(cursor_factory=RealDictCursor)
        ensure_verified_local_features_table(shared_cursor)
    except Exception as exc:
        print(f"Shared DB connection for market context failed, falling back to per-call connections: {exc}")
        shared_conn = None
        shared_cursor = None

    try:
        verified_competitors = fetch_verified_local_features("msme", business_type=business_type, cursor=shared_cursor)
        verified_roads = fetch_verified_local_features("road", cursor=shared_cursor)
        verified_anchors = fetch_verified_local_features("anchor", cursor=shared_cursor)
        verified_buildings = fetch_verified_local_features("building", cursor=shared_cursor)

        for shop in verified_competitors:
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                {
                    "lat": shop.get("latitude"),
                    "lon": shop.get("longitude"),
                    "name": shop.get("name"),
                    "source": "verified_local",
                    "confidence_score": shop.get("confidence_score"),
                },
                lat,
                lon,
                radius_meters,
                profile.get("display_name") or "MSME"
            )
    except Exception as exc:
        print(f"Verified local feature scan error: {exc}")

    try:
        cached_competitors = []
        for _, tag_value in osm_tags:
            competitors = get_cached_pbf_competitors(tag_value)
            cached_competitors.extend(competitors)

        for competitor in cached_competitors:
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                competitor,
                lat,
                lon,
                radius_meters,
                profile.get("display_name") or "MSME"
            )
    except Exception as exc:
        print(f"Spatial competitor scan error: {exc}")

    custom_competitors = []
    try:
        custom_competitors = fetch_custom_msmes(business_type, cursor=shared_cursor)
        for shop in custom_competitors:
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                {"lat": shop.get("latitude"), "lon": shop.get("longitude"), "name": shop.get("name"), "source": "custom_msme"},
                lat,
                lon,
                radius_meters,
                profile.get("display_name") or "MSME"
            )
    except Exception as exc:
        print(f"Custom MSME competitor scan error: {exc}")
    finally:
        if shared_cursor is not None:
            shared_cursor.close()
        if shared_conn is not None:
            shared_conn.close()

    if not competitors_list:
        for competitor in get_name_keyword_pbf_competitors(business_type):
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                competitor,
                lat,
                lon,
                radius_meters,
                profile.get("display_name") or "MSME"
            )

    competition_density = _score_competitor_density(lat, lon, competitors_list, radius_meters, profile)
    road_access = _score_road_access(lat, lon, radius_meters, profile, verified_roads=verified_roads)
    anchor_proximity = _score_anchor_proximity(lat, lon, radius_meters, profile, verified_anchors=verified_anchors)
    building_density = _score_building_density(lat, lon, radius_meters, profile, verified_buildings=verified_buildings)

    ahp_saturation = get_ahp_weights("saturation", profile_key_safe)
    if ahp_saturation:
        w_competition, w_road, w_anchor, w_building = ahp_saturation["priority_vector"]
        saturation_weight_source = "ahp"
    else:
        w_competition = float(profile.get("competition_weight") or 0.42)
        w_road = float(profile.get("road_weight") or 0.23)
        w_anchor = float(profile.get("anchor_weight") or 0.20)
        w_building = float(profile.get("building_weight") or 0.15)
        saturation_weight_source = "static_fallback"

    saturation_raw = (
        (competition_density["score"] * w_competition)
        + (road_access["score"] * w_road)
        + (anchor_proximity["score"] * w_anchor)
        + (building_density["score"] * w_building)
    )
    weight_total = w_competition + w_road + w_anchor + w_building
    saturation_score = round(_clamp_score(saturation_raw / max(0.01, weight_total), 0, 25))

    if saturation_score >= 20:
        saturation_status = "Market Gap Available"
    elif saturation_score >= 15:
        saturation_status = "Low Competition"
    elif saturation_score >= 10:
        saturation_status = "Moderate Competition"
    elif saturation_score >= 5:
        saturation_status = "High Competition"
    else:
        saturation_status = "Oversaturated"

    saturation_details = (
        f"The composite market saturation score blends competitor density, road access, traffic-generator proximity, and built-form intensity for {profile.get('display_name')}. "
        f"Weights used for this category ({saturation_weight_source}) are competition={w_competition:.2f}, road={w_road:.2f}, anchor={w_anchor:.2f}, building={w_building:.2f}. "
        f"Raw component scores are competition {competition_density['score']}, road {road_access['score']}, anchor {anchor_proximity['score']}, and building {building_density['score']}."
    )

    ahp_sub_criteria_methodology = {
        "source": saturation_weight_source,
        "criteria_labels": (ahp_saturation or {}).get("criteria_labels") or ["competition", "road", "anchor", "building"],
        "pairwise_matrix": (ahp_saturation or {}).get("pairwise_matrix"),
        "priority_vector": [w_competition, w_road, w_anchor, w_building],
        "lambda_max": (ahp_saturation or {}).get("lambda_max"),
        "consistency_index": (ahp_saturation or {}).get("ci"),
        "random_index": (ahp_saturation or {}).get("ri"),
        "consistency_ratio": (ahp_saturation or {}).get("cr"),
        "is_consistent": (ahp_saturation or {}).get("is_consistent", True),
    }

    return {
        "profile": profile,
        "competitors": competitors_list,
        "custom_competitors": custom_competitors,
        "competition_density": competition_density,
        "road_access": road_access,
        "anchor_proximity": anchor_proximity,
        "building_density": building_density,
        "ahp_sub_criteria_methodology": ahp_sub_criteria_methodology,
        "saturation": {
            "score": saturation_score,
            "status": saturation_status,
            "description": f"Composite market saturation for {profile.get('display_name')}",
            "details": saturation_details,
        },
        "component_scores": {
            "competition_density": competition_density["score"],
            "road_access": road_access["score"],
            "anchor_proximity": anchor_proximity["score"],
            "building_density": building_density["score"],
        },
    }


def collect_competitor_preview(lat, lon, radius_meters, business_type):
    profile_key = normalize_osm_value(business_type)
    profile_key_safe = profile_key or ""
    profile = MSME_CATEGORY_PROFILES.get(profile_key_safe, DEFAULT_MSME_ANALYSIS_PROFILE)
    osm_tags = profile.get("osm_tags") or SME_DATABASE.get(profile_key_safe, {}).get("osm_tags") or [("shop", "convenience")]

    competitors_list = []
    competitor_dedupe = set()

    try:
        verified_competitors = fetch_verified_local_features("msme", business_type=business_type)
        for shop in verified_competitors:
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                {
                    "lat": shop.get("latitude"),
                    "lon": shop.get("longitude"),
                    "name": shop.get("name"),
                    "source": "verified_local",
                    "confidence_score": shop.get("confidence_score"),
                },
                lat,
                lon,
                radius_meters,
                profile.get("display_name") or "MSME"
            )
    except Exception as exc:
        print(f"Verified local competitor preview error: {exc}")

    try:
        cached_competitors = []
        for _, tag_value in osm_tags:
            cached_competitors.extend(get_cached_pbf_competitors(tag_value))

        for competitor in cached_competitors:
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                competitor,
                lat,
                lon,
                radius_meters,
                profile.get("display_name") or "MSME"
            )
    except Exception as exc:
        print(f"Spatial competitor preview error: {exc}")

    try:
        custom_competitors = fetch_custom_msmes(business_type)
        for shop in custom_competitors:
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                {"lat": shop.get("latitude"), "lon": shop.get("longitude"), "name": shop.get("name"), "source": "custom_msme"},
                lat,
                lon,
                radius_meters,
                profile.get("display_name") or "MSME"
            )
    except Exception as exc:
        print(f"Custom MSME competitor preview error: {exc}")

    if not competitors_list:
        for competitor in get_name_keyword_pbf_competitors(business_type):
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                competitor,
                lat,
                lon,
                radius_meters,
                profile.get("display_name") or "MSME"
            )

    return {
        "business_type": profile_key_safe,
        "business_label": profile.get("display_name") or "MSME",
        "target_coords": {"lat": lat, "lng": lon},
        "radius_meters": radius_meters,
        "competitors_found": len(competitors_list),
        "competitor_locations": competitors_list,
    }


def preload_pbf_competitor_cache():
    global PBF_COMPETITOR_CACHE, PBF_ALL_COMPETITORS, PBF_CACHE_LOADED

    if PBF_CACHE_LOADED:
        return

    if gpd is None:
        PBF_COMPETITOR_CACHE = {}
        PBF_ALL_COMPETITORS = []
        PBF_CACHE_LOADED = True
        print("PBF cache skipped: geopandas is unavailable")
        return

    with PBF_CACHE_LOCK:
        if PBF_CACHE_LOADED:
            return

        cache = {}
        all_competitors = []

        if not PBF_PATH.exists():
            PBF_COMPETITOR_CACHE = cache
            PBF_ALL_COMPETITORS = all_competitors
            PBF_CACHE_LOADED = True
            print(f"PBF cache skipped: file not found at {PBF_PATH}")
            return

        for layer in PBF_LAYERS:
            try:
                gdf = gpd.read_file(str(PBF_PATH), layer=layer, engine="pyogrio")
            except Exception:
                continue

            available_columns = [col for col in PBF_SEARCH_COLUMNS if col in gdf.columns]
            if not available_columns or "geometry" not in gdf.columns:
                continue

            for col in available_columns:
                matches = gdf[gdf[col].notna()]
                for _, row in matches.iterrows():
                    geometry = row.geometry
                    if geometry is None:
                        continue

                    search_key = normalize_osm_value(row[col])
                    if not search_key:
                        continue

                    centroid = geometry.centroid
                    competitor_entry = {
                        "lat": centroid.y,
                        "lon": centroid.x,
                        "name": row.get("name"),
                        "tag_key": col,
                        "tag_value": search_key,
                    }

                    cache.setdefault(search_key, []).append(competitor_entry)
                    all_competitors.append(competitor_entry)

        PBF_COMPETITOR_CACHE = cache
        PBF_ALL_COMPETITORS = all_competitors
        PBF_CACHE_LOADED = True
        print(f"PBF cache loaded for {len(cache)} business values and {len(all_competitors)} features")


def get_cached_pbf_competitors(search_value):
    if not PBF_CACHE_LOADED:
        preload_pbf_competitor_cache()
    return PBF_COMPETITOR_CACHE.get(normalize_osm_value(search_value), [])


def get_name_keyword_pbf_competitors(business_type):
    if not PBF_CACHE_LOADED:
        preload_pbf_competitor_cache()

    business_key = normalize_osm_value(business_type) or ""
    keywords = PBF_NAME_KEYWORD_FALLBACK.get(business_key, [])
    if not keywords:
        return []

    matches = []
    for item in PBF_ALL_COMPETITORS:
        name = str(item.get("name") or "").strip().lower()
        if not name:
            continue
        if any(keyword in name for keyword in keywords):
            matches.append(item)

    return matches


def get_generic_nearby_pbf_competitors(lat, lon, radius_meters, limit=80):
    if not PBF_CACHE_LOADED:
        preload_pbf_competitor_cache()

    nearby = []
    for item in PBF_ALL_COMPETITORS:
        name = str(item.get("name") or "").strip()
        if not name:
            continue

        tag_key = normalize_osm_value(item.get("tag_key"))
        tag_value = normalize_osm_value(item.get("tag_value"))
        if tag_key == "shop":
            pass
        elif tag_key == "healthcare":
            pass
        elif tag_key == "amenity" and tag_value in COMMERCIAL_AMENITY_VALUES:
            pass
        else:
            continue

        item_lat = to_finite_number(item.get("lat"))
        item_lon = to_finite_number(item.get("lon"))
        if item_lat is None or item_lon is None:
            continue

        if calculate_distance(lat, lon, item_lat, item_lon) <= radius_meters:
            nearby.append(item)
            if len(nearby) >= limit:
                break

    return nearby


def _append_competitor_if_within_radius(competitors_list, dedupe_keys, source_item, origin_lat, origin_lon, radius_meters, default_name):
    p_lat = to_finite_number(source_item.get("lat")) if isinstance(source_item, dict) else None
    p_lon = to_finite_number(source_item.get("lon")) if isinstance(source_item, dict) else None

    if p_lat is None or p_lon is None:
        return

    distance_m = calculate_distance(origin_lat, origin_lon, p_lat, p_lon)
    if distance_m > radius_meters:
        return

    competitor_name = None
    if isinstance(source_item, dict):
        competitor_name = source_item.get("name")

    normalized_name = str(competitor_name or default_name or "").strip()
    dedupe_key = (round(p_lat, 6), round(p_lon, 6), normalized_name.lower())
    if dedupe_key in dedupe_keys:
        return

    dedupe_keys.add(dedupe_key)
    source_name = str(source_item.get("source") or "osm").strip().lower() if isinstance(source_item, dict) else "osm"
    competitors_list.append({
        "lat": p_lat,
        "lon": p_lon,
        "name": normalized_name or default_name,
        "source": source_name,
        "confidence_score": source_item.get("confidence_score") if isinstance(source_item, dict) else None
    })


def fetch_custom_msmes(business_key, cursor=None):
    conn = None
    try:
        if cursor is None:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT name, latitude, longitude FROM custom_msme WHERE business_type = %s", (business_key,))
        results = cursor.fetchall()
        if conn is not None:
            cursor.close()
            conn.close()
        return results
    except Exception as e:
        print(f"Database Error: {e}")
        return []


def fetch_custom_msme_counts(cursor):
    cursor.execute(
        """
        SELECT
            LOWER(TRIM(business_type)) AS business_key,
            COUNT(*) AS total
        FROM custom_msme
        GROUP BY LOWER(TRIM(business_type))
        """
    )

    rows = cursor.fetchall() or []
    counts = {}
    for row in rows:
        business_key = str(row.get("business_key") or "").strip()
        if not business_key:
            continue
        counts[business_key] = int(row.get("total") or 0)

    return counts


def fetch_user_profile_by_id(cursor, user_pk_column: str, user_id: int):
    cursor.execute(
        f"""
        SELECT
            {user_pk_column} AS user_id,
            full_name,
            email,
            address,
            cellphone_number,
            avatar_url,
            age,
            birthday,
            primary_business,
            startup_capital,
            preferred_setup,
            target_payback_months,
            created_at
        FROM users
        WHERE {user_pk_column} = %s
        LIMIT 1
        """,
        (user_id,)
    )
    return cursor.fetchone()


def fetch_history_trend_snapshot(cursor):
    cursor.execute(
        """
        SELECT
            LOWER(TRIM(business_type)) AS business_name,
            COUNT(*) AS scan_count,
            AVG(viability_score) AS avg_score
        FROM analysis_history
        WHERE scan_date >= (NOW() - INTERVAL '180 days')
        GROUP BY LOWER(TRIM(business_type))
        """
    )
    rows = cursor.fetchall() or []
    snapshot = {}
    for row in rows:
        business_name = (row.get("business_name") or "").strip()
        if not business_name:
            continue
        snapshot[business_name] = {
            "scan_count": int(row.get("scan_count") or 0),
            "avg_score": float(row.get("avg_score") or 0.0),
        }
    return snapshot


def fetch_user_business_history_snapshot(cursor, user_id: int):
    cursor.execute(
        """
        SELECT
            LOWER(TRIM(business_type)) AS business_name,
            COUNT(*) AS scan_count,
            AVG(viability_score) AS avg_score
        FROM analysis_history
        WHERE user_id = %s
        GROUP BY LOWER(TRIM(business_type))
        """,
        (user_id,)
    )
    rows = cursor.fetchall() or []
    snapshot = {}
    for row in rows:
        business_name = (row.get("business_name") or "").strip()
        if not business_name:
            continue
        snapshot[business_name] = {
            "scan_count": int(row.get("scan_count") or 0),
            "avg_score": float(row.get("avg_score") or 0.0),
        }
    return snapshot


async def fetch_custom_msme_counts_async(conn):
    rows = await conn.fetch(
        """
        SELECT
            LOWER(TRIM(business_type)) AS business_key,
            COUNT(*) AS total
        FROM custom_msme
        GROUP BY LOWER(TRIM(business_type))
        """
    )

    counts = {}
    for row in rows or []:
        business_key = str(row.get("business_key") or "").strip()
        if not business_key:
            continue
        counts[business_key] = int(row.get("total") or 0)

    return counts


async def fetch_user_profile_by_id_async(conn, user_pk_column: str, user_id: int):
    row = await conn.fetchrow(
        f"""
        SELECT
            {user_pk_column} AS user_id,
            full_name,
            email,
            address,
            cellphone_number,
            avatar_url,
            age,
            birthday,
            primary_business,
            startup_capital,
            preferred_setup,
            target_payback_months,
            created_at
        FROM users
        WHERE {user_pk_column} = $1
        LIMIT 1
        """,
        user_id,
    )
    return dict(row) if row else None


async def fetch_history_trend_snapshot_async(conn):
    rows = await conn.fetch(
        """
        SELECT
            LOWER(TRIM(business_type)) AS business_name,
            COUNT(*) AS scan_count,
            AVG(viability_score) AS avg_score
        FROM analysis_history
        WHERE scan_date >= (NOW() - INTERVAL '180 days')
        GROUP BY LOWER(TRIM(business_type))
        """
    )
    snapshot = {}
    for row in rows or []:
        business_name = (row.get("business_name") or "").strip()
        if not business_name:
            continue
        snapshot[business_name] = {
            "scan_count": int(row.get("scan_count") or 0),
            "avg_score": float(row.get("avg_score") or 0.0),
        }
    return snapshot


async def fetch_user_business_history_snapshot_async(conn, user_id: int):
    rows = await conn.fetch(
        """
        SELECT
            LOWER(TRIM(business_type)) AS business_name,
            COUNT(*) AS scan_count,
            AVG(viability_score) AS avg_score
        FROM analysis_history
        WHERE user_id = $1
        GROUP BY LOWER(TRIM(business_type))
        """,
        user_id,
    )
    snapshot = {}
    for row in rows or []:
        business_name = (row.get("business_name") or "").strip()
        if not business_name:
            continue
        snapshot[business_name] = {
            "scan_count": int(row.get("scan_count") or 0),
            "avg_score": float(row.get("avg_score") or 0.0),
        }
    return snapshot


from analysis_service import (
    score_business_opportunity,
    build_trend_upside_downside,
    recommend_trends,
)

def match_preference_business_keys(primary_interest: str | None):
    interest_text = str(primary_interest or "").strip().lower()
    if not interest_text:
        return set()

    matched = set()
    tokenized_interest = {
        token
        for token in interest_text.replace("/", " ").replace(",", " ").replace("-", " ").split()
        if token
    }

    for business_key, profile_data in SME_DATABASE.items():
        business_name = str(profile_data.get("name") or "").strip().lower()
        if not business_name:
            continue

        if business_key in interest_text or business_name in interest_text:
            matched.add(business_key)
            continue

        business_tokens = {
            token
            for token in business_name.replace("/", " ").replace("-", " ").split()
            if token
        }
        if tokenized_interest.intersection(business_tokens):
            matched.add(business_key)

    if "food" in interest_text:
        matched.update({"kiosk", "bakery", "coffee", "meat"})

    return matched


def fetch_active_space_markers_for_analysis():
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    user_pk_column = get_users_primary_key_column(cursor)
    ensure_user_space_submissions_table(cursor, user_pk_column)
    ensure_admin_space_submissions_table(cursor)

    cursor.execute(
        """
        SELECT
            id,
            title,
            listing_mode,
            guarantee_level,
            property_type,
            business_type,
            latitude,
            longitude,
            address_text,
            price_min,
            price_max,
            contact_info,
            notes,
            photo_urls,
            status,
            created_at,
            reviewed_at,
            'user'::text AS source_type
        FROM user_space_submissions
        WHERE status IN ('approved', 'pending')
        """
    )
    user_rows = cursor.fetchall() or []

    cursor.execute(
        """
        SELECT
            id,
            title,
            listing_mode,
            guarantee_level,
            property_type,
            business_type,
            latitude,
            longitude,
            address_text,
            price_min,
            price_max,
            contact_info,
            notes,
            confidence_score,
            photo_urls,
            created_at,
            verified_at,
            expires_at,
            'admin'::text AS source_type
        FROM admin_space_submissions
        WHERE is_active = TRUE
          AND (expires_at IS NULL OR expires_at >= CURRENT_DATE)
        """
    )
    admin_rows = cursor.fetchall() or []

    cursor.close()
    conn.close()

    markers = []

    for row in user_rows:
        markers.append({
            "id": f"user-{row.get('id')}",
            "source_type": "user",
            "title": row.get("title"),
            "listing_mode": row.get("listing_mode"),
            "guarantee_level": "guaranteed",
            "status": row.get("status"),
            "property_type": row.get("property_type"),
            "business_type": row.get("business_type"),
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
            "address_text": row.get("address_text"),
            "price_min": row.get("price_min"),
            "price_max": row.get("price_max"),
            "contact_info": row.get("contact_info"),
            "notes": row.get("notes"),
            "photo_urls": row.get("photo_urls") or [],
            "confidence_score": 100,
            "verified_at": row.get("reviewed_at") or row.get("created_at"),
            "expires_at": None,
        })

    for row in admin_rows:
        markers.append({
            "id": f"admin-{row.get('id')}",
            "source_type": "admin",
            "title": row.get("title"),
            "listing_mode": row.get("listing_mode"),
            "guarantee_level": row.get("guarantee_level") or "potential",
            "property_type": row.get("property_type"),
            "business_type": row.get("business_type"),
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
            "address_text": row.get("address_text"),
            "price_min": row.get("price_min"),
            "price_max": row.get("price_max"),
            "contact_info": row.get("contact_info"),
            "notes": row.get("notes"),
            "photo_urls": row.get("photo_urls") or [],
            "confidence_score": row.get("confidence_score"),
            "verified_at": row.get("verified_at") or row.get("created_at"),
            "expires_at": row.get("expires_at"),
        })

    return markers


def resolve_space_context_for_coords(lat: float, lon: float, space_markers=None, max_distance_meters: int = 85):
    markers = space_markers if isinstance(space_markers, list) else fetch_active_space_markers_for_analysis()
    best_match = None
    best_distance = None

    for marker in markers:
        marker_lat = to_finite_number(marker.get("latitude"))
        marker_lon = to_finite_number(marker.get("longitude"))
        if marker_lat is None or marker_lon is None:
            continue

        distance_m = calculate_distance(lat, lon, marker_lat, marker_lon)
        if distance_m > max_distance_meters:
            continue

        if best_distance is None or distance_m < best_distance:
            best_distance = distance_m
            best_match = marker

    if not best_match:
        return None

    return {
        "id": best_match.get("id"),
        "source_type": best_match.get("source_type"),
        "title": best_match.get("title"),
        "listing_mode": best_match.get("listing_mode"),
        "guarantee_level": best_match.get("guarantee_level"),
        "property_type": best_match.get("property_type"),
        "business_type": best_match.get("business_type"),
        "latitude": best_match.get("latitude"),
        "longitude": best_match.get("longitude"),
        "address_text": best_match.get("address_text"),
        "price_min": best_match.get("price_min"),
        "price_max": best_match.get("price_max"),
        "contact_info": best_match.get("contact_info"),
        "notes": best_match.get("notes"),
        "confidence_score": best_match.get("confidence_score"),
        "verified_at": best_match.get("verified_at"),
        "expires_at": best_match.get("expires_at"),
        "distance_meters": int(round(best_distance if best_distance is not None else 0.0)),
    }


def build_panabo_prescan_points(space_markers=None, max_space_points: int = 12):
    min_lat, max_lat, min_lon, max_lon = PANABO_BOUNDS
    lat_step = 0.006
    lon_step = 0.006

    points = []

    lat_value = min_lat
    while lat_value <= max_lat:
        lon_value = min_lon
        while lon_value <= max_lon:
            points.append({
                "lat": round(lat_value, 6),
                "lon": round(lon_value, 6),
                "label": "Panabo citywide scan point",
                "source": "city-grid",
            })
            lon_value += lon_step
        lat_value += lat_step

    # Keep one central point even if grid spacing changes.
    points.append({"lat": 7.3075, "lon": 125.6811, "label": "Panabo central corridor", "source": "city-grid"})

    for anchor in PANABO_ANCHORS:
        points.append({
            "lat": anchor["lat"],
            "lon": anchor["lon"],
            "label": anchor["name"],
            "source": "anchor",
        })

    if isinstance(space_markers, list):
        for marker in space_markers[:max_space_points]:
            lat = to_finite_number(marker.get("latitude"))
            lon = to_finite_number(marker.get("longitude"))
            if lat is None or lon is None:
                continue

            points.append({
                "lat": lat,
                "lon": lon,
                "label": marker.get("title") or "Approved space listing",
                "source": "space",
            })

    deduped = []
    seen = set()
    for point in points:
        dedupe_key = (round(point["lat"], 6), round(point["lon"], 6))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(point)

    return deduped


def run_citywide_business_scan(business_key: str, candidates, radius: int = 340, space_markers=None, top_hotspots: int = 3):
    best_report = None
    hotspots = []

    for candidate in candidates:
        report = perform_analysis(
            AnalysisRequest(
                lat=float(candidate["lat"]),
                lon=float(candidate["lon"]),
                business_type=business_key,
                radius=radius,
                user_id=None,
            )
        )

        score = int(report.get("viability_score") or 0)
        report["scan_source"] = candidate.get("label")
        report["scan_source_type"] = candidate.get("source")

        target_coords = report.get("target_coords") or {}
        target_lat = to_finite_number(target_coords.get("lat"))
        target_lng = to_finite_number(target_coords.get("lng"))
        if target_lat is not None and target_lng is not None:
            report["space_context"] = resolve_space_context_for_coords(
                target_lat,
                target_lng,
                space_markers=space_markers,
            )
        else:
            report["space_context"] = None

        hotspots.append({
            "score": score,
            "source": candidate.get("label"),
            "source_type": candidate.get("source"),
            "coords": target_coords,
            "space_context": report.get("space_context"),
        })

        if best_report is None or score > int(best_report.get("viability_score") or 0):
            best_report = report

    hotspots.sort(key=lambda item: item.get("score", 0), reverse=True)
    return {
        "best_report": best_report,
        "hotspots": hotspots[:top_hotspots],
    }


def save_citywide_scan_snapshot_to_db(radius: int, payload: dict):
    """Save trend snapshot to database."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO trend_scan_snapshots (radius, snapshot_payload, updated_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (radius) DO UPDATE SET
                snapshot_payload = EXCLUDED.snapshot_payload,
                updated_at = CURRENT_TIMESTAMP
            """,
            (radius, json.dumps(payload))
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as exc:
        print(f"Warning: Failed to save trend snapshot to DB: {exc}")

def load_citywide_scan_snapshot_from_db(radius: int):
    """Load trend snapshot from database."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(RealDictCursor)
        cursor.execute(
            "SELECT snapshot_payload FROM trend_scan_snapshots WHERE radius = %s",
            (radius,)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row and row["snapshot_payload"]:
            payload = row["snapshot_payload"]
            if isinstance(payload, (dict, list)):
                return payload
            if isinstance(payload, (bytes, bytearray, memoryview)):
                return json.loads(bytes(payload).decode("utf-8"))
            if isinstance(payload, str):
                return json.loads(payload)
            return payload
    except Exception as exc:
        print(f"Warning: Failed to load trend snapshot from DB: {exc}")
    return None


def build_citywide_scan_snapshot(radius: int = 340):
    space_markers = fetch_active_space_markers_for_analysis()
    candidates = build_panabo_prescan_points(space_markers=space_markers, max_space_points=24)
    print(f"[DEBUG] Citywide scan: {len(candidates)} grid points")
    businesses = {}
    for business_key in SME_DATABASE.keys():
        print(f"[DEBUG] Scanning business: {business_key}")
        scan_result = run_citywide_business_scan(
            business_key,
            candidates,
            radius=radius,
            space_markers=space_markers,
            top_hotspots=3,
        )
        best_report = scan_result.get("best_report")
        print(f"[DEBUG] Best report for {business_key}: score={best_report.get('viability_score') if best_report else None}, competitors={best_report.get('competitors_found') if best_report else None}")
        businesses[business_key] = {
            "best_report": best_report,
            "hotspots": scan_result.get("hotspots") or [],
        }

    return {
        "generated_at": utc_now_iso_z(),
        "radius": radius,
        "candidate_count": len(candidates),
        "businesses": businesses,
    }


def _refresh_citywide_scan_snapshot_worker(cache_key: str, radius: int):
    try:
        payload = build_citywide_scan_snapshot(radius=radius)
        # Save to database
        save_citywide_scan_snapshot_to_db(radius, payload)
        # Also update in-memory cache
        with TREND_SCAN_CACHE_LOCK:
            TREND_SCAN_CACHE[cache_key] = {
                "cached_at": utc_now_naive(),
                "payload": payload,
            }
    except Exception as exc:
        print(f"Citywide scan refresh warning ({cache_key}): {exc}")
    finally:
        with TREND_SCAN_CACHE_LOCK:
            TREND_SCAN_REFRESH_IN_FLIGHT.discard(cache_key)


def warm_citywide_scan_snapshot_async(radius: int = 340):
    cache_key = f"radius:{int(radius)}"

    db_payload = load_citywide_scan_snapshot_from_db(radius)
    if db_payload:
        with TREND_SCAN_CACHE_LOCK:
            TREND_SCAN_CACHE[cache_key] = {
                "cached_at": utc_now_naive(),
                "payload": db_payload,
            }

        if not _is_snapshot_stale(db_payload, TREND_SCAN_CACHE_TTL_SECONDS):
            return

    with TREND_SCAN_CACHE_LOCK:
        if cache_key in TREND_SCAN_REFRESH_IN_FLIGHT:
            return
        TREND_SCAN_REFRESH_IN_FLIGHT.add(cache_key)

    Thread(
        target=_refresh_citywide_scan_snapshot_worker,
        args=(cache_key, int(radius)),
        daemon=True,
    ).start()


def get_citywide_scan_snapshot(radius: int = 340):
    """Get trend snapshot with non-blocking first load and background refresh.
    
    Strategy:
    1. First call: Return empty snapshot immediately, trigger background scan
    2. Subsequent calls: Return latest from DB or cache, refresh in background if stale
    """
    cache_key = f"radius:{int(radius)}"
    now = utc_now_naive()

    # Check in-memory cache first
    with TREND_SCAN_CACHE_LOCK:
        cached = TREND_SCAN_CACHE.get(cache_key)
        if cached:
            cached_at = cached.get("cached_at")
            if isinstance(cached_at, datetime):
                age_seconds = (now - cached_at).total_seconds()
                payload = cached.get("payload") or {}

                if age_seconds <= TREND_SCAN_CACHE_TTL_SECONDS:
                    return payload

                if age_seconds <= TREND_SCAN_CACHE_MAX_STALE_SECONDS:
                    if cache_key not in TREND_SCAN_REFRESH_IN_FLIGHT:
                        TREND_SCAN_REFRESH_IN_FLIGHT.add(cache_key)
                        Thread(
                            target=_refresh_citywide_scan_snapshot_worker,
                            args=(cache_key, int(radius)),
                            daemon=True,
                        ).start()
                    return payload

    # Try to load from database
    db_payload = load_citywide_scan_snapshot_from_db(radius)
    if db_payload:
        # Cache it in memory
        with TREND_SCAN_CACHE_LOCK:
            TREND_SCAN_CACHE[cache_key] = {
                "cached_at": now,
                "payload": db_payload,
            }
        # Trigger background refresh only when snapshot is stale.
        if _is_snapshot_stale(db_payload, TREND_SCAN_CACHE_TTL_SECONDS):
            with TREND_SCAN_CACHE_LOCK:
                if cache_key not in TREND_SCAN_REFRESH_IN_FLIGHT:
                    TREND_SCAN_REFRESH_IN_FLIGHT.add(cache_key)
                    Thread(
                        target=_refresh_citywide_scan_snapshot_worker,
                        args=(cache_key, int(radius)),
                        daemon=True,
                    ).start()
        return db_payload if isinstance(db_payload, dict) else {}

    # No cache and no DB entry: trigger background scan
    if cache_key not in TREND_SCAN_REFRESH_IN_FLIGHT:
        TREND_SCAN_REFRESH_IN_FLIGHT.add(cache_key)
        Thread(
            target=_refresh_citywide_scan_snapshot_worker,
            args=(cache_key, int(radius)),
            daemon=True,
        ).start()
    # Return empty snapshot immediately (non-blocking)
    return {
        "generated_at": utc_now_iso_z(),
        "radius": radius,
        "candidate_count": 0,
        "businesses": {},
        "snapshot_ready": False,
    }


def _trend_snapshot_auto_refresh_loop(stop_event: Event, radius: int = 340):
    interval_seconds = max(300, TREND_SCAN_AUTO_REFRESH_INTERVAL_SECONDS)

    while not stop_event.is_set():
        if stop_event.wait(interval_seconds):
            break

        try:
            warm_citywide_scan_snapshot_async(radius=radius)
        except Exception as exc:
            print(f"Trend auto-refresh warning (radius:{radius}): {exc}")


def run_pre_scanned_trend_report(business_key: str, user_id: int | None = None, radius: int = 340, space_markers=None):
    snapshot = get_citywide_scan_snapshot(radius=radius)
    snapshot_obj = snapshot if isinstance(snapshot, dict) else {}
    business_bucket = (snapshot_obj.get("businesses") or {}).get(business_key) or {}
    report = business_bucket.get("best_report")
    if not report:
        return None

    hydrated = dict(report)
    hydrated["trend_generated_for_user"] = user_id
    return hydrated


def verify_admin_token(x_admin_token: str | None):
    if not x_admin_token or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized admin access")


AHP_LEVEL_EXPECTED_SIZE = {"criteria": 3, "saturation": 4}


def _ahp_judgments_to_upper_triangle(judgments: dict) -> dict:
    """Converts {"i,j": value} string-keyed JSON judgments into {(i, j): value}
    tuple-keyed judgments expected by ahp.build_reciprocal_matrix."""
    upper_triangle = {}
    for key, value in (judgments or {}).items():
        try:
            i_str, j_str = str(key).split(",")
            i, j = int(i_str), int(j_str)
        except (ValueError, AttributeError):
            raise HTTPException(status_code=400, detail=f"Malformed judgment key: {key!r}, expected 'i,j'")
        if i >= j:
            raise HTTPException(status_code=400, detail=f"Judgment key {key!r} must satisfy i < j (upper triangle only)")
        upper_triangle[(i, j)] = value
    return upper_triangle


def _ahp_config_row_to_dict(row: dict) -> dict:
    return {
        "level": row["level"],
        "category": row["category"],
        "criteria_labels": row["criteria_labels"],
        "pairwise_matrix": row["pairwise_matrix"],
        "priority_vector": row["priority_vector"],
        "lambda_max": row["lambda_max"],
        "consistency_index": row["consistency_index"],
        "random_index": row["random_index"],
        "consistency_ratio": row["consistency_ratio"],
        "is_consistent": row["is_consistent"],
        "updated_by_admin_email": row["updated_by_admin_email"],
        "updated_at": row["updated_at"],
    }


@app.post("/admin/ahp/matrix")
def admin_submit_ahp_matrix(payload: AhpPairwiseSubmitRequest, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        level = str(payload.level or "").strip().lower()
        if level not in AHP_LEVEL_EXPECTED_SIZE:
            raise HTTPException(status_code=400, detail="level must be either 'criteria' or 'saturation'")

        if level == "criteria":
            category = AHP_GLOBAL_CATEGORY_SENTINEL
        else:
            category = str(payload.category or "").strip().lower()
            if category not in MSME_CATEGORY_PROFILES:
                raise HTTPException(status_code=400, detail=f"Unknown business category: {payload.category!r}")

        expected_n = AHP_LEVEL_EXPECTED_SIZE[level]
        if len(payload.criteria_labels) != expected_n:
            raise HTTPException(
                status_code=400,
                detail=f"criteria_labels must have exactly {expected_n} entries for level={level!r}"
            )

        upper_triangle = _ahp_judgments_to_upper_triangle(payload.judgments)
        matrix = build_reciprocal_matrix(upper_triangle, expected_n)
        solved = solve_ahp(matrix)

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            """
            INSERT INTO ahp_weight_configs (
                level, category, criteria_labels, pairwise_matrix, priority_vector,
                lambda_max, consistency_index, random_index, consistency_ratio,
                is_consistent, updated_by_admin_email
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (level, category) DO UPDATE SET
                criteria_labels = EXCLUDED.criteria_labels,
                pairwise_matrix = EXCLUDED.pairwise_matrix,
                priority_vector = EXCLUDED.priority_vector,
                lambda_max = EXCLUDED.lambda_max,
                consistency_index = EXCLUDED.consistency_index,
                random_index = EXCLUDED.random_index,
                consistency_ratio = EXCLUDED.consistency_ratio,
                is_consistent = EXCLUDED.is_consistent,
                updated_by_admin_email = EXCLUDED.updated_by_admin_email,
                updated_at = CURRENT_TIMESTAMP
            RETURNING *
            """,
            (
                level,
                category,
                Json(payload.criteria_labels),
                Json(matrix),
                Json(solved["priority_vector"]),
                solved["lambda_max"],
                solved["ci"],
                solved["ri"],
                solved["cr"],
                solved["is_consistent"],
                ADMIN_EMAIL,
            )
        )
        saved = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        _load_ahp_weights_cache()

        return {"status": "success", "config": _ahp_config_row_to_dict(saved)}
    except AHPValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/ahp/matrix")
def admin_get_ahp_matrix(level: str, category: str | None = None, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        level = str(level or "").strip().lower()
        if level not in AHP_LEVEL_EXPECTED_SIZE:
            raise HTTPException(status_code=400, detail="level must be either 'criteria' or 'saturation'")
        lookup_category = AHP_GLOBAL_CATEGORY_SENTINEL if level == "criteria" else str(category or "").strip().lower()

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            "SELECT * FROM ahp_weight_configs WHERE level = %s AND category = %s",
            (level, lookup_category)
        )
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if not row:
            raise HTTPException(status_code=404, detail="No AHP matrix configured for this level/category yet")

        return {"status": "success", "config": _ahp_config_row_to_dict(row)}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/ahp/matrices")
def admin_list_ahp_matrices(x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM ahp_weight_configs ORDER BY level, category")
        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        configured_by_key = {(row["level"], row["category"]): row for row in rows}
        entries = []

        criteria_row = configured_by_key.get(("criteria", AHP_GLOBAL_CATEGORY_SENTINEL))
        entries.append({
            "level": "criteria",
            "category": AHP_GLOBAL_CATEGORY_SENTINEL,
            "is_configured": criteria_row is not None,
            "is_consistent": criteria_row["is_consistent"] if criteria_row else None,
            "consistency_ratio": criteria_row["consistency_ratio"] if criteria_row else None,
            "updated_by_admin_email": criteria_row["updated_by_admin_email"] if criteria_row else None,
            "updated_at": criteria_row["updated_at"] if criteria_row else None,
        })

        for category_key in MSME_CATEGORY_PROFILES:
            row = configured_by_key.get(("saturation", category_key))
            entries.append({
                "level": "saturation",
                "category": category_key,
                "is_configured": row is not None,
                "is_consistent": row["is_consistent"] if row else None,
                "consistency_ratio": row["consistency_ratio"] if row else None,
                "updated_by_admin_email": row["updated_by_admin_email"] if row else None,
                "updated_at": row["updated_at"] if row else None,
            })

        return {"status": "success", "configs": entries}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/admin/ahp/matrix")
def admin_delete_ahp_matrix(level: str, category: str | None = None, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        level = str(level or "").strip().lower()
        if level not in AHP_LEVEL_EXPECTED_SIZE:
            raise HTTPException(status_code=400, detail="level must be either 'criteria' or 'saturation'")
        lookup_category = AHP_GLOBAL_CATEGORY_SENTINEL if level == "criteria" else str(category or "").strip().lower()

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(
            "DELETE FROM ahp_weight_configs WHERE level = %s AND category = %s RETURNING id",
            (level, lookup_category)
        )
        deleted = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not deleted:
            raise HTTPException(status_code=404, detail="No AHP matrix configured for this level/category")

        _load_ahp_weights_cache()
        return {"status": "success", "reverted_to": "static_fallback"}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


def normalize_listing_mode(value: str) -> str:
    mode = str(value or "").strip().lower()
    if mode not in {"rent", "buy"}:
        raise HTTPException(status_code=400, detail="listing_mode must be either 'rent' or 'buy'")
    return mode


def normalize_guarantee_level(value: str) -> str:
    level = str(value or "").strip().lower()
    if level not in {"guaranteed", "potential"}:
        raise HTTPException(status_code=400, detail="guarantee_level must be either 'guaranteed' or 'potential'")
    return level


def normalize_space_submission_status(value: str) -> str:
    status = str(value or "").strip().lower()
    if status not in {"pending", "approved", "rejected", "archived"}:
        raise HTTPException(status_code=400, detail="status must be pending, approved, rejected, or archived")
    return status


@app.post("/spaces/user-submissions")
def create_user_space_submission(payload: UserSpaceSubmissionRequest):
    try:
        listing_mode = normalize_listing_mode(payload.listing_mode)

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        user_pk_column = get_users_primary_key_column(cursor)
        ensure_user_space_submissions_table(cursor, user_pk_column)

        cursor.execute(
            f"SELECT {user_pk_column} AS user_id FROM users WHERE {user_pk_column} = %s",
            (payload.user_id,)
        )
        existing_user = cursor.fetchone()
        if not existing_user:
            cursor.close()
            conn.close()
            raise HTTPException(status_code=404, detail="User not found")

        cursor.execute(
            """
            INSERT INTO user_space_submissions (
                submitted_by_user_id,
                title,
                listing_mode,
                guarantee_level,
                property_type,
                business_type,
                latitude,
                longitude,
                address_text,
                price_min,
                price_max,
                contact_info,
                notes,
                photo_urls,
                status
            )
            VALUES (%s, %s, %s, 'guaranteed', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
            RETURNING *
            """,
            (
                payload.user_id,
                payload.title,
                listing_mode,
                (payload.property_type or None),
                (payload.business_type or None),
                payload.latitude,
                payload.longitude,
                (payload.address_text or None),
                payload.price_min,
                payload.price_max,
                (payload.contact_info or None),
                (payload.notes or None),
                Json(payload.photo_urls or []),
            )
        )
        created = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "success", "submission": created}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/spaces/map-markers")
def list_space_map_markers():
    try:
        markers = fetch_active_space_markers_for_analysis()

        for marker in markers:
            marker["last_verified_at"] = marker.get("verified_at")

        return {"status": "success", "markers": markers}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/spaces/user-submissions")
def admin_list_user_space_submissions(status: str | None = None, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        normalized_status = normalize_space_submission_status(status) if status else None

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        user_pk_column = get_users_primary_key_column(cursor)
        ensure_user_space_submissions_table(cursor, user_pk_column)

        if normalized_status:
            cursor.execute(
                "SELECT * FROM user_space_submissions WHERE status = %s ORDER BY created_at DESC, id DESC",
                (normalized_status,)
            )
        else:
            cursor.execute("SELECT * FROM user_space_submissions ORDER BY created_at DESC, id DESC")

        rows = cursor.fetchall() or []
        cursor.close()
        conn.close()
        return {"status": "success", "submissions": rows}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/admin/spaces/user-submissions/{submission_id}/status")
def admin_update_user_space_submission_status(
    submission_id: int,
    payload: AdminReviewUserSpaceSubmissionRequest,
    x_admin_token: str | None = Header(default=None)
):
    verify_admin_token(x_admin_token)
    try:
        normalized_status = normalize_space_submission_status(payload.status)

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        user_pk_column = get_users_primary_key_column(cursor)
        ensure_user_space_submissions_table(cursor, user_pk_column)

        cursor.execute(
            """
            UPDATE user_space_submissions
            SET
                status = %s,
                review_note = %s,
                reviewed_by_admin_email = %s,
                reviewed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING *
            """,
            (normalized_status, (payload.review_note or None), ADMIN_EMAIL, submission_id)
        )
        updated = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not updated:
            raise HTTPException(status_code=404, detail="User space submission not found")

        return {"status": "success", "submission": updated}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/spaces/admin-submissions")
def admin_list_admin_space_submissions(x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_admin_space_submissions_table(cursor)
        cursor.execute("SELECT * FROM admin_space_submissions ORDER BY created_at DESC, id DESC")
        rows = cursor.fetchall() or []
        cursor.close()
        conn.close()
        return {"status": "success", "submissions": rows}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/spaces/admin-submissions")
def admin_create_admin_space_submission(
    payload: AdminSpaceSubmissionRequest,
    x_admin_token: str | None = Header(default=None)
):
    verify_admin_token(x_admin_token)
    try:
        listing_mode = normalize_listing_mode(payload.listing_mode)
        guarantee_level = normalize_guarantee_level(payload.guarantee_level)
        confidence_score = payload.confidence_score

        if confidence_score is not None and (confidence_score < 0 or confidence_score > 100):
            raise HTTPException(status_code=400, detail="confidence_score must be between 0 and 100")

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_admin_space_submissions_table(cursor)
        cursor.execute(
            """
            INSERT INTO admin_space_submissions (
                title,
                listing_mode,
                guarantee_level,
                confidence_score,
                property_type,
                business_type,
                latitude,
                longitude,
                address_text,
                price_min,
                price_max,
                source_note,
                contact_info,
                notes,
                photo_urls,
                verified_at,
                expires_at,
                is_active,
                created_by_admin_email
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING *
            """,
            (
                payload.title,
                listing_mode,
                guarantee_level,
                confidence_score,
                (payload.property_type or None),
                (payload.business_type or None),
                payload.latitude,
                payload.longitude,
                (payload.address_text or None),
                payload.price_min,
                payload.price_max,
                (payload.source_note or None),
                (payload.contact_info or None),
                (payload.notes or None),
                Json(payload.photo_urls or []),
                payload.verified_at,
                payload.expires_at,
                payload.is_active,
                ADMIN_EMAIL,
            )
        )
        created = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "success", "submission": created}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/admin/spaces/admin-submissions/{submission_id}/active")
def admin_update_admin_space_submission_active_state(
    submission_id: int,
    payload: AdminToggleSpaceSubmissionActiveRequest,
    x_admin_token: str | None = Header(default=None)
):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_admin_space_submissions_table(cursor)

        cursor.execute(
            """
            UPDATE admin_space_submissions
            SET
                is_active = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING *
            """,
            (payload.is_active, submission_id)
        )
        updated = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not updated:
            raise HTTPException(status_code=404, detail="Admin space submission not found")

        return {"status": "success", "submission": updated}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


def fetch_user_for_admin(cursor, user_pk_column: str, user_id: int):
    cursor.execute(
        f"""
        SELECT
            {user_pk_column} AS user_id,
            full_name,
            email,
            created_at,
            address,
            cellphone_number,
            avatar_url,
            age,
            birthday,
            primary_business,
            startup_capital,
            preferred_setup,
            target_payback_months
        FROM users
        WHERE {user_pk_column} = %s
        """,
        (user_id,)
    )
    return cursor.fetchone()


@app.post("/admin/login")
def admin_login(payload: AdminLoginRequest):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_admin_users_table(cursor)

        cursor.execute(
            """
            SELECT email, password_hash
            FROM admin_users
            WHERE email = %s
            LIMIT 1
            """,
            (payload.email,)
        )
        admin_row = cursor.fetchone()

        cursor.close()
        conn.close()

        if admin_row:
            stored_hash = str(admin_row.get("password_hash") or "")
            is_valid = False
            try:
                is_valid = bcrypt.checkpw(payload.password.encode("utf-8"), stored_hash.encode("utf-8"))
            except Exception:
                is_valid = payload.password == stored_hash

            if is_valid:
                return {
                    "status": "success",
                    "admin": {
                        "email": admin_row.get("email") or payload.email,
                        "token": ADMIN_TOKEN
                    }
                }

        # Backward-compatible fallback to env credentials.
        if payload.email == ADMIN_EMAIL and payload.password == ADMIN_PASSWORD:
            return {
                "status": "success",
                "admin": {
                    "email": ADMIN_EMAIL,
                    "token": ADMIN_TOKEN
                }
            }

        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


class ReportRequest(BaseModel):
    analysis: dict
    category: str | None = None
    export_pdf: bool = False
    business_type: str | None = None
    use_llm: bool = True
    gemini_model: str = "gemini-1.5-pro"


@app.post("/reports/generate")
def generate_report(payload: ReportRequest):
    try:
        profile = DEFAULT_MSME_ANALYSIS_PROFILE
        if payload.category:
            profile = MSME_CATEGORY_PROFILES.get(payload.category.lower(), DEFAULT_MSME_ANALYSIS_PROFILE)

        structured = build_structured_report(payload.analysis or {}, profile)
        narrative_result = generate_narrative_with_fallback(
            structured,
            business_type=(payload.business_type or payload.category or ''),
            use_llm=bool(payload.use_llm),
            gemini_model=(payload.gemini_model or "gemini-1.5-pro"),
        )
        structured["narrative"] = narrative_result.get("narrative")
        structured["quality_control"] = narrative_result.get("qc")
        structured["generation_meta"] = narrative_result.get("meta")
        html = render_report_html(structured)

        pdf_b64 = None
        if payload.export_pdf:
            pdf_bytes = try_render_pdf_bytes(html)
            if pdf_bytes:
                import base64
                pdf_b64 = base64.b64encode(pdf_bytes).decode('ascii')

        return {
            "status": "success",
            "report": structured,
            "html": html,
            "pdf_base64": pdf_b64,
            "qc": narrative_result.get("qc"),
            "generation_meta": narrative_result.get("meta"),
            "deterministic_backup": narrative_result.get("deterministic_backup"),
        }
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/users")
def admin_list_users(x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        user_pk_column = get_users_primary_key_column(cursor)
        cursor.execute(
            f"""
            SELECT
                {user_pk_column} AS user_id,
                full_name,
                email,
                created_at,
                address,
                cellphone_number,
                avatar_url,
                age,
                birthday,
                primary_business,
                startup_capital,
                preferred_setup,
                target_payback_months
            FROM users
            ORDER BY created_at DESC, {user_pk_column} DESC
            """
        )
        users = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"status": "success", "users": users}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/admin/users/{user_id}")
def admin_update_user(user_id: int, payload: AdminUpdateUser, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        user_pk_column = get_users_primary_key_column(cursor)
        if not user_pk_column:
            cursor.close()
            conn.close()
            raise HTTPException(status_code=500, detail="Unable to determine users primary key column")

        existing = fetch_user_for_admin(cursor, user_pk_column, user_id)
        if not existing:
            cursor.close()
            conn.close()
            raise HTTPException(status_code=404, detail="User not found")

        cursor.execute(
            f"""
            SELECT {user_pk_column} AS user_id
            FROM users
            WHERE email = %s AND {user_pk_column} <> %s
            """,
            (payload.email, user_id)
        )
        duplicate = cursor.fetchone()
        if duplicate:
            cursor.close()
            conn.close()
            raise HTTPException(status_code=400, detail="Email already registered")

        cursor.execute(
            f"""
            UPDATE users
            SET
                full_name = %s,
                email = %s,
                address = %s,
                cellphone_number = %s,
                avatar_url = %s,
                age = %s,
                birthday = %s,
                primary_business = %s,
                startup_capital = %s,
                preferred_setup = %s,
                target_payback_months = %s
            WHERE {user_pk_column} = %s
            RETURNING
                {user_pk_column} AS user_id,
                full_name,
                email,
                created_at,
                address,
                cellphone_number,
                avatar_url,
                age,
                birthday,
                primary_business,
                startup_capital,
                preferred_setup,
                target_payback_months
            """,
            (
                payload.full_name,
                payload.email,
                payload.address or None,
                payload.cellphone_number or None,
                payload.avatar_url or None,
                payload.age,
                payload.birthday,
                payload.primary_business or None,
                payload.startup_capital,
                payload.preferred_setup or None,
                payload.target_payback_months,
                user_id
            )
        )
        updated = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "success", "user": updated}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/admin/users/{user_id}")
def admin_delete_user(user_id: int, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        user_pk_column = get_users_primary_key_column(cursor)
        cursor.execute(
            f"DELETE FROM users WHERE {user_pk_column} = %s RETURNING {user_pk_column}",
            (user_id,)
        )
        deleted = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not deleted:
            raise HTTPException(status_code=404, detail="User not found")

        return {"status": "success", "deleted_user_id": deleted[0]}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/custom-msmes")
def admin_list_custom_msmes(x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_custom_msme_table(cursor)
        cursor.execute(
            """
            SELECT id, name, business_type, latitude, longitude, created_at
            FROM custom_msme
            ORDER BY created_at DESC, id DESC
            """
        )
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"status": "success", "custom_msmes": rows}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/custom-msmes")
def admin_create_custom_msme(payload: AdminCreateMsme, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_custom_msme_table(cursor)
        cursor.execute(
            """
            INSERT INTO custom_msme (name, business_type, latitude, longitude)
            VALUES (%s, %s, %s, %s)
            RETURNING id, name, business_type, latitude, longitude, created_at
            """,
            (payload.name, payload.business_type, payload.latitude, payload.longitude)
        )
        created = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "success", "custom_msme": created}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/admin/custom-msmes/{msme_id}")
def admin_update_custom_msme(msme_id: int, payload: AdminUpdateMsme, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_custom_msme_table(cursor)
        cursor.execute(
            """
            UPDATE custom_msme
            SET name = %s, business_type = %s, latitude = %s, longitude = %s
            WHERE id = %s
            RETURNING id, name, business_type, latitude, longitude, created_at
            """,
            (payload.name, payload.business_type, payload.latitude, payload.longitude, msme_id)
        )
        updated = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not updated:
            raise HTTPException(status_code=404, detail="Custom MSME not found")

        return {"status": "success", "custom_msme": updated}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/admin/custom-msmes/{msme_id}")
def admin_delete_custom_msme(msme_id: int, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        ensure_custom_msme_table(cursor)
        cursor.execute("DELETE FROM custom_msme WHERE id = %s RETURNING id", (msme_id,))
        deleted = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not deleted:
            raise HTTPException(status_code=404, detail="Custom MSME not found")

        return {"status": "success", "deleted_custom_msme_id": deleted[0]}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/admin/verified-local-features")
def admin_list_verified_local_features(
    feature_kind: str | None = None,
    business_type: str | None = None,
    include_inactive: bool = False,
    x_admin_token: str | None = Header(default=None)
):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_verified_local_features_table(cursor)

        query = [
            "SELECT id, feature_kind, name, business_type, feature_subtype, latitude, longitude, road_class, power, building_type, landuse, area_m2, confidence_score, source_note, is_active, verified_at, created_by_admin_email, created_at, updated_at",
            "FROM verified_local_features",
            "WHERE 1 = 1",
        ]
        params = []

        if feature_kind:
            normalized_kind = normalize_osm_value(feature_kind)
            if normalized_kind not in VERIFIED_LOCAL_FEATURE_KINDS:
                raise HTTPException(status_code=400, detail="Invalid verified feature kind")
            query.append("AND feature_kind = %s")
            params.append(normalized_kind)

        if business_type:
            query.append("AND LOWER(TRIM(COALESCE(business_type, ''))) = %s")
            params.append(normalize_osm_value(business_type))

        if not include_inactive:
            query.append("AND is_active = TRUE")

        query.append("ORDER BY updated_at DESC, created_at DESC, id DESC")
        cursor.execute("\n".join(query), params)
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return {"status": "success", "verified_local_features": rows}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/admin/verified-local-features")
def admin_create_verified_local_feature(payload: AdminVerifiedLocalFeatureRequest, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        feature_kind = normalize_osm_value(payload.feature_kind)
        if feature_kind not in VERIFIED_LOCAL_FEATURE_KINDS:
            raise HTTPException(status_code=400, detail="Invalid verified feature kind")

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_verified_local_features_table(cursor)
        cursor.execute(
            """
            INSERT INTO verified_local_features (
                feature_kind, name, business_type, feature_subtype, latitude, longitude,
                road_class, power, building_type, landuse, area_m2, confidence_score,
                source_note, is_active, verified_at, created_by_admin_email
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id, feature_kind, name, business_type, feature_subtype, latitude, longitude, road_class, power, building_type, landuse, area_m2, confidence_score, source_note, is_active, verified_at, created_by_admin_email, created_at, updated_at
            """,
            (
                feature_kind,
                payload.name,
                payload.business_type,
                payload.feature_subtype,
                payload.latitude,
                payload.longitude,
                payload.road_class,
                payload.power,
                payload.building_type,
                payload.landuse,
                payload.area_m2,
                int(payload.confidence_score or 0),
                payload.source_note,
                payload.is_active,
                payload.verified_at,
                None,
            )
        )
        created = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()
        return {"status": "success", "verified_local_feature": created}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/admin/verified-local-features/{feature_id}")
def admin_update_verified_local_feature(feature_id: int, payload: AdminVerifiedLocalFeatureRequest, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        feature_kind = normalize_osm_value(payload.feature_kind)
        if feature_kind not in VERIFIED_LOCAL_FEATURE_KINDS:
            raise HTTPException(status_code=400, detail="Invalid verified feature kind")

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_verified_local_features_table(cursor)
        cursor.execute(
            """
            UPDATE verified_local_features
            SET feature_kind = %s,
                name = %s,
                business_type = %s,
                feature_subtype = %s,
                latitude = %s,
                longitude = %s,
                road_class = %s,
                power = %s,
                building_type = %s,
                landuse = %s,
                area_m2 = %s,
                confidence_score = %s,
                source_note = %s,
                is_active = %s,
                verified_at = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id, feature_kind, name, business_type, feature_subtype, latitude, longitude, road_class, power, building_type, landuse, area_m2, confidence_score, source_note, is_active, verified_at, created_by_admin_email, created_at, updated_at
            """,
            (
                feature_kind,
                payload.name,
                payload.business_type,
                payload.feature_subtype,
                payload.latitude,
                payload.longitude,
                payload.road_class,
                payload.power,
                payload.building_type,
                payload.landuse,
                payload.area_m2,
                int(payload.confidence_score or 0),
                payload.source_note,
                payload.is_active,
                payload.verified_at,
                feature_id,
            )
        )
        updated = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not updated:
            raise HTTPException(status_code=404, detail="Verified local feature not found")

        return {"status": "success", "verified_local_feature": updated}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/admin/verified-local-features/{feature_id}")
def admin_delete_verified_local_feature(feature_id: int, x_admin_token: str | None = Header(default=None)):
    verify_admin_token(x_admin_token)
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        ensure_verified_local_features_table(cursor)
        cursor.execute("DELETE FROM verified_local_features WHERE id = %s RETURNING id", (feature_id,))
        deleted = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not deleted:
            raise HTTPException(status_code=404, detail="Verified local feature not found")

        return {"status": "success", "deleted_verified_local_feature_id": deleted[0]}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze")
def perform_analysis(data: AnalysisRequest):
    business_key = normalize_osm_value(data.business_type) or ''
    sme_profile = SME_DATABASE.get(business_key, {"key": business_key or "shop", "val": "convenience", "fear": 5, "need": 5, "name": "MSME"})
    analysis_profile = _get_analysis_profile(business_key)
    print(
        f"[DEBUG] perform_analysis: business_type={business_key}, lat={data.lat}, lon={data.lon}, radius={data.radius}, "
        f"profile={analysis_profile.get('display_name')}, competition_weight={analysis_profile.get('competition_weight')}"
    )

    preflight_context = evaluate_layered_market_context(data.lat, data.lon, data.radius, business_key)

    # FACTOR 1: ZONING - Normalized to 0-25 scale
    zoning_score = 0
    zoning_status = "Outside Commercial Zone"
    if check_inside_bounds(data.lat, data.lon, ZONING_LAYERS["commercial_proper"]):
        zoning_score = 25
        zoning_status = "Compliant (Commercial Center)"
    elif check_inside_bounds(data.lat, data.lon, ZONING_LAYERS["industrial_anflo"]):
        if business_key in ["carwash", "laundry", "hardware", "moto"]:
            zoning_score = 25
            zoning_status = "Compliant (Agri-Industrial Support)"
        else:
            zoning_score = 5
            zoning_status = "Non-Compliant (Heavy Industrial Zone)"

    # FACTOR 2: HAZARD
    hazard_score, hazard_status, hazard_matches = evaluate_hazard(data.lat, data.lon)
    if HAZARD_LAYER_CACHE:
        hazard_description = (
            "Hazard evaluation uses official Panabo-clipped flood polygons from the Davao del Norte 5-year return period layer. "
            + ("Matched zone: " + hazard_matches[0] + "." if hazard_matches else "No mapped hazard zone matched.")
        )
    else:
        hazard_description = "Hazard layer is unavailable, so no hazard class was applied to this scan."

    competition_density = preflight_context["competition_density"]
    road_access = preflight_context["road_access"]
    anchor_proximity = preflight_context["anchor_proximity"]
    building_density = preflight_context["building_density"]
    saturation_score = preflight_context["saturation"]["score"]
    saturation_status = preflight_context["saturation"]["status"]
    saturation_details = preflight_context["saturation"]["details"]
    competitors_list = preflight_context["competitors"]
    competitors_found = len(competitors_list)

    if HAZARD_LAYER_CACHE:
        source_label = HAZARD_LAYER_SOURCE or "unknown source"
        hazard_details = (
            "The hazard score is based on official Panabo-clipped flood polygons from the Davao del Norte 5-year return period dataset. "
            + f"Loaded source: {source_label}. "
            + ("Matched zone: " + hazard_matches[0] + ". " if hazard_matches else "No mapped flood zone matched. ")
            + "Hazard classes are made mutually exclusive by priority (Very High > High > Moderate), so each point can map to at most one zone."
        )
    else:
        hazard_details = (
            "No valid hazard polygon layer with a Var flood-class field was loaded, so the engine returned Low Risk / Safe "
            "instead of using temporary placeholder bounds."
        )

    zoning_details = (
        "The zoning score is derived by checking whether the target coordinates fall inside Panabo commercial or industrial polygon bounds. "
        + "If the site is inside the commercial polygon, it receives 25. If it is in the industrial support polygon and the business fits that category, it also receives 25; otherwise it is penalized."
    )

    ahp_criteria = get_ahp_weights("criteria", None)
    if ahp_criteria:
        w_zoning, w_hazard, w_saturation = ahp_criteria["priority_vector"]
        criteria_weight_source = "ahp"
    else:
        w_zoning, w_hazard, w_saturation = 0.30, 0.20, 0.50
        criteria_weight_source = "static_fallback"

    total_score = round(((zoning_score * w_zoning) + (hazard_score * w_hazard) + (saturation_score * w_saturation)) * 4)

    ahp_criteria_methodology = {
        "source": criteria_weight_source,
        "criteria_labels": (ahp_criteria or {}).get("criteria_labels") or ["zoning", "hazard", "saturation"],
        "pairwise_matrix": (ahp_criteria or {}).get("pairwise_matrix"),
        "priority_vector": [w_zoning, w_hazard, w_saturation],
        "lambda_max": (ahp_criteria or {}).get("lambda_max"),
        "consistency_index": (ahp_criteria or {}).get("ci"),
        "random_index": (ahp_criteria or {}).get("ri"),
        "consistency_ratio": (ahp_criteria or {}).get("cr"),
        "is_consistent": (ahp_criteria or {}).get("is_consistent", True),
    }
    ahp_methodology_payload = {
        "criteria": ahp_criteria_methodology,
        "saturation_sub_criteria": preflight_context.get("ahp_sub_criteria_methodology"),
    }

    # STATIC REPORTING MODULE (Combinational Matrix)
    if zoning_score <= 5:
        generated_insight = f"Critical Warning: This location is in a {zoning_status.lower()}. Even if market conditions are favorable, securing BPLO permits will be highly unlikely. Reconsider this site."
    elif hazard_score <= 5 and anchor_proximity["score"] >= 15:
        generated_insight = f"High Risk, High Reward (Score: {int(total_score)}). The location attracts strong traffic generators, but it is also exposed to severe flood risk. Any development plan must account for mitigation, insurance, and resilient design."
    elif saturation_score >= 20 and road_access["score"] >= 18 and anchor_proximity["score"] >= 18:
        generated_insight = f"Prime Market Gap (Score: {int(total_score)}). The site combines excellent road access, strong traffic generators, and a low competitive burden. This is the strongest placement profile in the current scan window."
    elif saturation_score <= 10 and competition_density["score"] <= 10:
        generated_insight = f"Competitive Hotspot (Score: {int(total_score)}). The corridor shows clustered competitors and the inverse-density score is weak, so this location will demand sharper differentiation and pricing discipline."
    elif anchor_proximity["score"] < 10 and road_access["score"] < 10:
        generated_insight = f"Low Visibility (Score: {int(total_score)}). The site lacks strong traffic generators and does not sit on a high-value road class, so footfall generation will depend heavily on destination marketing."
    elif total_score >= 70:
        generated_insight = f"Favorable Location (Score: {int(total_score)}). Strong overall metrics with manageable risks. The balance of foot traffic and market saturation provides a stable environment for this {sme_profile['name']}."
    elif total_score >= 45:
        generated_insight = f"Moderate Viability (Score: {int(total_score)}). This site has mixed indicators. Review the breakdown below—you will need to strategically compensate for environmental risks or lower market visibility."
    else:
        generated_insight = f"Not Recommended (Score: {int(total_score)}). Poor overall suitability. A combination of low demand, environmental hazards, or zoning issues makes this a highly unfavorable location."

    breakdown_payload = {
        "zoning": {
            "score": zoning_score,
            "status": zoning_status,
            "description": "Alignment with Panabo City Land Use Plan.",
            "details": zoning_details,
        },
        "hazard": {
            "score": hazard_score,
            "status": hazard_status,
            "description": hazard_description,
            "details": hazard_details,
        },
        "competition_density": {
            "score": competition_density["score"],
            "status": competition_density["status"],
            "description": f"Inverse-density competition pressure for {analysis_profile.get('display_name')}",
            "details": competition_density["details"],
        },
        "road_access": {
            "score": road_access["score"],
            "status": road_access["status"],
            "description": f"Nearest OSM road class and accessibility fit for {analysis_profile.get('display_name')}",
            "details": road_access["details"],
        },
        "anchor_proximity": {
            "score": anchor_proximity["score"],
            "status": anchor_proximity["status"],
            "description": f"Traffic-generator proximity using Panabo anchor points for {analysis_profile.get('display_name')}",
            "details": anchor_proximity["details"],
        },
        "building_density": {
            "score": building_density["score"],
            "status": building_density["status"],
            "description": f"Built-form intensity around the site for {analysis_profile.get('display_name')}",
            "details": building_density["details"],
        },
        "saturation": {
            "score": saturation_score,
            "status": saturation_status,
            "description": f"Composite market saturation score for {analysis_profile.get('display_name')}",
            "details": saturation_details,
        },
    }

    if data.user_id is not None:
        try:
            sanitized_competitors_list = competitors_list if competitors_found > 0 else []

            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()

            updated_existing = False
            if data.history_id is not None:
                # Re-scan of an already-saved report (e.g. opened from History) should
                # refresh that row in place instead of inserting a duplicate.
                history_pk_column = get_analysis_history_pk_column(cursor)
                cursor.execute(
                    f"""
                    UPDATE analysis_history
                    SET business_type = %s,
                        viability_score = %s,
                        target_lat = %s,
                        target_lon = %s,
                        radius_used = %s,
                        insight = %s,
                        competitors_found = %s,
                        competitor_locations = %s,
                        breakdown = %s,
                        ahp_methodology = %s
                    WHERE user_id = %s AND {history_pk_column} = %s
                    """,
                    (
                        business_key,
                        int(total_score),
                        data.lat,
                        data.lon,
                        data.radius,
                        generated_insight,
                        competitors_found,
                        Json(sanitized_competitors_list),
                        Json(breakdown_payload),
                        Json(ahp_methodology_payload),
                        data.user_id,
                        data.history_id,
                    )
                )
                updated_existing = cursor.rowcount > 0

            if not updated_existing:
                # Fresh scan (or the referenced saved record no longer exists) - insert a new row.
                cursor.execute(
                    """
                    INSERT INTO analysis_history (
                        user_id, business_type, viability_score,
                        target_lat, target_lon, radius_used, insight,
                        competitors_found, competitor_locations, breakdown, ahp_methodology
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        data.user_id,
                        business_key,
                        int(total_score),
                        data.lat,
                        data.lon,
                        data.radius,
                        generated_insight,
                        competitors_found,
                        Json(sanitized_competitors_list),
                        Json(breakdown_payload),
                        Json(ahp_methodology_payload)
                    )
                )

            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"History Save Error: {e}")

    # FINAL PAYLOAD
    print(f"[DEBUG] Final score for {business_key} at ({data.lat},{data.lon}): {int(total_score)}\n---")
    return {
        "viability_score": int(total_score),
        "business_type": business_key,
        "business_label": sme_profile["name"],
        "competitors_found": competitors_found,
        "competitor_locations": competitors_list if competitors_found > 0 else [],
        "target_coords": {"lat": data.lat, "lng": data.lon},
        "radius_meters": data.radius,
        "insight": generated_insight,
        "breakdown": breakdown_payload,
        "ahp_methodology": ahp_methodology_payload,
    }


@app.post("/competitors/preview")
def preview_competitors(data: CompetitorPreviewRequest):
    preview = collect_competitor_preview(data.lat, data.lon, data.radius, data.business_type)
    return {
        "status": "success",
        **preview,
    }

if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("MARKETSCOPE_HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", os.environ.get("MARKETSCOPE_PORT", "8000")))

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if sock.connect_ex(("127.0.0.1", port)) == 0:
            raise SystemExit(
                f"Port {port} is already in use. Stop the existing backend process or set MARKETSCOPE_PORT to a different port."
            )

    uvicorn.run(app, host=host, port=port)