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
    RESET_CODE_DEV_MODE,
    RESET_CODE_TTL_MINUTES,
    create_app_tables,
    ensure_admin_space_submissions_table,
    ensure_admin_users_table,
    ensure_custom_msme_table,
    ensure_user_space_submissions_table,
    generate_reset_code,
    get_analysis_history_pk_column,
    get_analysis_history_pk_column_async,
    get_users_primary_key_column,
    get_users_primary_key_column_async,
    send_password_reset_email,
)
from auth_service import (
    forgot_password as auth_forgot_password,
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
    update_user_profile as user_update_profile,
)
from settings import get_allowed_origins, get_database_config

try:
    import geopandas as gpd
except Exception:
    gpd = None

try:
    from shapely.geometry import Point, box
    from shapely.ops import unary_union
except Exception:
    Point = None
    box = None
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        create_app_tables(DB_CONFIG)
    except Exception as e:
        print(f"[DB Schema] Error creating tables: {e}", flush=True)
        # Continue startup even if table creation fails
    
    # Create asyncpg pool with retry logic
    app.state.db_pool = await connect_with_retry()
    preload_hazard_layer_cache()
    preload_pbf_competitor_cache()
    warm_citywide_scan_snapshot_async(radius=340)
    stop_event = Event()
    auto_refresh_thread = Thread(
        target=_trend_snapshot_auto_refresh_loop,
        args=(stop_event, 340),
        daemon=True,
    )
    auto_refresh_thread.start()
    yield
    stop_event.set()
    await app.state.db_pool.close()


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
    risk_tolerance: str | None = None
    preferred_setup: str | None = None
    time_commitment: str | None = None
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
    risk_tolerance: str | None = None
    preferred_setup: str | None = None
    time_commitment: str | None = None
    target_payback_months: int | None = None

class AnalysisRequest(BaseModel):
    lat: float
    lon: float
    business_type: str
    radius: int = 340 
    user_id: int | None = None


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
    risk_tolerance: str | None = None
    preferred_setup: str | None = None
    time_commitment: str | None = None
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
        return await auth_login_user(app.state.db_pool, user)
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
        citywide_businesses = citywide_snapshot.get("businesses") or {}

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
                "risk_tolerance": user_profile.get("risk_tolerance") or "Not set",
                "preferred_setup": user_profile.get("preferred_setup") or "Not set",
                "time_commitment": user_profile.get("time_commitment") or "Not set",
                "target_payback_months": user_profile.get("target_payback_months"),
                "total_options_evaluated": len(recommendations),
                "preference_business_matches": sorted(list(preference_business_keys)),
                "trend_recommendation_keys": trend_recommendation_keys,
                "scan_engine": "citywide-standalone",
                "citywide_scan_generated_at": citywide_snapshot.get("generated_at"),
                "citywide_scan_points": citywide_snapshot.get("candidate_count"),
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

ZONING_LAYERS = {
    "commercial_proper": (7.3000, 7.3150, 125.6700, 125.6900),
    "industrial_anflo": (7.2800, 7.2950, 125.6500, 125.6700)
}

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


def _parse_utc_iso_z(value: str):
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


def _is_snapshot_stale(payload: dict, threshold_seconds: int) -> bool:
    generated_at = _parse_utc_iso_z((payload or {}).get("generated_at"))
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

    keywords = PBF_NAME_KEYWORD_FALLBACK.get(normalize_osm_value(business_type), [])
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
    competitors_list.append({
        "lat": p_lat,
        "lon": p_lon,
        "name": normalized_name or default_name
    })


def fetch_custom_msmes(business_key):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT name, latitude, longitude FROM custom_msme WHERE business_type = %s", (business_key,))
        results = cursor.fetchall()
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
            risk_tolerance,
            preferred_setup,
            time_commitment,
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
            risk_tolerance,
            preferred_setup,
            time_commitment,
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
            created_at,
            reviewed_at,
            'user'::text AS source_type
        FROM user_space_submissions
        WHERE status = 'approved'
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
            "property_type": row.get("property_type"),
            "business_type": row.get("business_type"),
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
            "address_text": row.get("address_text"),
            "price_min": row.get("price_min"),
            "price_max": row.get("price_max"),
            "contact_info": row.get("contact_info"),
            "notes": row.get("notes"),
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
        "distance_meters": int(round(best_distance)),
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
        return db_payload

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
    business_bucket = (snapshot.get("businesses") or {}).get(business_key) or {}
    report = business_bucket.get("best_report")
    if not report:
        return None

    hydrated = dict(report)
    hydrated["trend_generated_for_user"] = user_id
    return hydrated


def verify_admin_token(x_admin_token: str | None):
    if not x_admin_token or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized admin access")


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
                status
            )
            VALUES (%s, %s, %s, 'guaranteed', %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending')
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
                verified_at,
                expires_at,
                is_active,
                created_by_admin_email
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            risk_tolerance,
            preferred_setup,
            time_commitment,
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
                risk_tolerance,
                preferred_setup,
                time_commitment,
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
                risk_tolerance = %s,
                preferred_setup = %s,
                time_commitment = %s,
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
                risk_tolerance,
                preferred_setup,
                time_commitment,
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
                payload.risk_tolerance or None,
                payload.preferred_setup or None,
                payload.time_commitment or None,
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

@app.post("/analyze")
def perform_analysis(data: AnalysisRequest):
    sme_profile = SME_DATABASE.get(data.business_type, {"key": "shop", "val": "convenience", "fear": 5, "need": 5, "name": "MSME"})
    search_val = sme_profile["val"]
    osm_tags = sme_profile.get("osm_tags") or [(sme_profile.get("key", "shop"), search_val)]
    print(f"[DEBUG] perform_analysis: business_type={data.business_type}, lat={data.lat}, lon={data.lon}, radius={data.radius}, osm_tags={osm_tags}")
    
    # FACTOR 1: ZONING - Normalized to 0-25 scale
    zoning_score = 0
    zoning_status = "Outside Commercial Zone"
    if check_inside_bounds(data.lat, data.lon, ZONING_LAYERS["commercial_proper"]):
        zoning_score = 25
        zoning_status = "Compliant (Commercial Center)"
    elif check_inside_bounds(data.lat, data.lon, ZONING_LAYERS["industrial_anflo"]):
        if data.business_type in ["carwash", "laundry", "hardware", "moto"]:
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

    # FACTOR 3: LOCAL COMPETITOR SCAN (SATURATION) - Normalized to 0-25 scale
    competitors_list = []
    competitor_dedupe = set()

    try:
        cached_competitors = []
        for _, tag_value in osm_tags:
            competitors = get_cached_pbf_competitors(tag_value)
            print(f"[DEBUG] OSM competitors for tag_value={tag_value}: {len(competitors)} found")
            cached_competitors.extend(competitors)

        for competitor in cached_competitors:
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                competitor,
                data.lat,
                data.lon,
                data.radius,
                f"Local {sme_profile['name']}"
            )
    except Exception as e:
        print(f"Spatial Scan Error: {e}")

    # Scan PostgreSQL Database and include them as direct competitors.
    custom_shops = fetch_custom_msmes(data.business_type)
    print(f"[DEBUG] Custom MSMEs for {data.business_type}: {len(custom_shops)} found")
    for shop in custom_shops:
        _append_competitor_if_within_radius(
            competitors_list,
            competitor_dedupe,
            {"lat": shop.get('latitude'), "lon": shop.get('longitude'), "name": shop.get('name')},
            data.lat,
            data.lon,
            data.radius,
            f"Local {sme_profile['name']}"
        )

    # Local-only fallback: match Panabo OSM features by business name keywords.
    if not competitors_list:
        for competitor in get_name_keyword_pbf_competitors(data.business_type):
            _append_competitor_if_within_radius(
                competitors_list,
                competitor_dedupe,
                competitor,
                data.lat,
                data.lon,
                data.radius,
                f"Nearby {sme_profile['name']}"
            )

    # Strict competitors are the only ones used for saturation scoring.
    strict_competitors_found = len(competitors_list)
    print(f"[DEBUG] Total competitors found for {data.business_type} at ({data.lat},{data.lon}): {strict_competitors_found}")

    competitors_found = strict_competitors_found

    # Normalize saturation score to 0-25 scale
    # Lower competitors = higher score (less saturated = better)
    if competitors_found == 0:
        saturation_score = 25  # Perfect - no competition
    elif competitors_found == 1:
        saturation_score = 20  # Good - minimal competition
    elif competitors_found <= 3:
        saturation_score = 15  # Moderate - some competition
    elif competitors_found <= 5:
        saturation_score = 10  # Challenging - notable competition
    else:
        saturation_score = 5   # Very saturated - high competition

    # Determine saturation status based on score
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

    # FACTOR 4: PROPRIETARY DEMAND SCAN 
    raw_demand_power = 0
    anchors_found = []
    for anchor in PANABO_ANCHORS:
        distance = calculate_distance(data.lat, data.lon, anchor["lat"], anchor["lon"])
        if distance <= data.radius:
            raw_demand_power += anchor["power"]
            anchors_found.append(anchor["name"])

    target_power = sme_profile['need'] * 8
    demand_ratio = (raw_demand_power / target_power) * 25 if target_power > 0 else 25
    demand_score = min(25, int(demand_ratio))
    
    if demand_score >= 20:
        demand_status = "High Foot Traffic"
    elif demand_score >= 10:
        demand_status = "Moderate Foot Traffic"
    else:
        demand_status = "Low Visibility"
        
    demand_desc = f"Proximate to: {', '.join(anchors_found)}." if anchors_found else "No major Panabo infrastructure anchors detected."
    demand_details = (
        f"Demand score is computed by summing the power values of nearby Panabo anchors within {data.radius} meters, then normalizing that total against a target power benchmark ({target_power}). "
        + f"Raw anchor power is {raw_demand_power}, and the result is scaled to a 0-25 index with a maximum cap of 25."
    )

    saturation_details = (
        f"The algorithm scanned local Panabo OSM data from panabo.pbf plus local MSME entries for matching businesses within {data.radius} meters. "
        + f"It counted direct competitors and then mapped that count to a 0-25 score: 0 competitors => 25, 1 competitor => 20, 2-3 => 15, 4-5 => 10, 6+ => 5."
    )

    zoning_details = (
        "The zoning score is derived by checking whether the target coordinates fall inside Panabo commercial or industrial polygon bounds. "
        + "If the site is inside the commercial polygon, it receives 25. If it is in the industrial support polygon and the business fits that category, it also receives 25; otherwise it is penalized."
    )

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

    breakdown_payload = {
        "zoning": {
            "score": zoning_score,
            "status": zoning_status,
            "description": "Alignment with Panabo City Land Use Plan.",
            "details": zoning_details
        },
        "hazard": {
            "score": hazard_score,
            "status": hazard_status,
            "description": hazard_description,
            "details": hazard_details
        },
        "saturation": {
            "score": saturation_score,
            "status": "Oversaturated" if competitors_found >= 1 else "Market Gap Available",
            "description": f"Penalty multiplier based on {sme_profile['name']} industry sensitivity.",
            "details": saturation_details
        },
        "demand": {
            "score": demand_score,
            "status": demand_status,
            "description": demand_desc,
            "details": demand_details
        }
    }

    total_score = zoning_score + hazard_score + saturation_score + demand_score

    # STATIC REPORTING MODULE (Combinational Matrix)
    if zoning_score <= 5:
        generated_insight = f"Critical Warning: This location is in a {zoning_status.lower()}. Even if market conditions are favorable, securing BPLO permits will be highly unlikely. Reconsider this site."
    elif hazard_score == 0 and demand_score >= 15:
        generated_insight = f"High Risk, High Reward (Score: {int(total_score)}). While this location benefits from strong foot traffic, it sits in a high-risk flood zone. You must factor in significant property insurance and structural mitigation costs."
    elif demand_score >= 20 and saturation_score <= 10:
        generated_insight = f"Competitive Hotspot (Score: {int(total_score)}). Excellent infrastructure demand is present, but the market is heavily oversaturated with {competitors_found} competitors. Success requires aggressive marketing and strong differentiation."
    elif demand_score >= 20 and saturation_score >= 20:
        generated_insight = f"Prime Market Gap (Score: {int(total_score)}). Highly recommended. This location enjoys fantastic foot traffic from nearby anchors with virtually zero direct competition. This is an optimal investment opportunity."
    elif demand_score < 10 and saturation_score >= 20:
        generated_insight = f"Low Visibility (Score: {int(total_score)}). There are zero competitors here, but also minimal infrastructure drivers. This site will require heavy destination-marketing to draw customers, as organic foot traffic is very low."
    elif total_score >= 70:
        generated_insight = f"Favorable Location (Score: {int(total_score)}). Strong overall metrics with manageable risks. The balance of foot traffic and market saturation provides a stable environment for this {sme_profile['name']}."
    elif total_score >= 45:
        generated_insight = f"Moderate Viability (Score: {int(total_score)}). This site has mixed indicators. Review the breakdown below—you will need to strategically compensate for environmental risks or lower market visibility."
    else:
        generated_insight = f"Not Recommended (Score: {int(total_score)}). Poor overall suitability. A combination of low demand, environmental hazards, or zoning issues makes this a highly unfavorable location."

    if data.user_id is not None:
        try:
            sanitized_competitors_list = competitors_list if competitors_found > 0 else []

            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO analysis_history (
                    user_id, business_type, viability_score,
                    target_lat, target_lon, radius_used, insight,
                    competitors_found, competitor_locations, breakdown
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    data.user_id,
                    sme_profile["name"],
                    int(total_score),
                    data.lat,
                    data.lon,
                    data.radius,
                    generated_insight,
                    competitors_found,
                    Json(sanitized_competitors_list),
                    Json(breakdown_payload)
                )
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"History Save Error: {e}")

    # FINAL PAYLOAD
    print(f"[DEBUG] Final score for {data.business_type} at ({data.lat},{data.lon}): {int(total_score)}\n---")
    return {
        "viability_score": int(total_score),
        "business_type": sme_profile["name"], 
        "competitors_found": competitors_found,
        "competitor_locations": competitors_list if competitors_found > 0 else [],
        "target_coords": {"lat": data.lat, "lng": data.lon}, 
        "radius_meters": data.radius,
        "insight": generated_insight, 
        "breakdown": breakdown_payload
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