"""Citywide pre-scan of every MSME category, cached in memory and in the DB."""
import json
from datetime import datetime, timezone
from threading import Event, Lock, Thread

import psycopg2
from psycopg2.extras import RealDictCursor

from constants.geo import PANABO_ANCHORS, PANABO_BOUNDS
from constants.msme import SME_DATABASE
from core.config import (
    TREND_SCAN_AUTO_REFRESH_INTERVAL_SECONDS,
    TREND_SCAN_CACHE_MAX_STALE_SECONDS,
    TREND_SCAN_CACHE_TTL_SECONDS,
)
from core.database import DB_CONFIG
from models.requests import AnalysisRequest
from services.analysis import perform_analysis
from services.spaces import (
    fetch_active_space_markers_for_analysis,
    resolve_space_context_for_coords,
)
from utils.dates import _parse_utc_iso_z, utc_now_iso_z, utc_now_naive
from utils.values import to_finite_number


def trigger_trend_warmup_after_login(radius: int = 340):
    """Start trend warmup in the background after auth succeeds."""
    Thread(
        target=warm_citywide_scan_snapshot_async,
        kwargs={"radius": radius},
        daemon=True,
    ).start()


TREND_SCAN_CACHE = {}


TREND_SCAN_CACHE_LOCK = Lock()


TREND_SCAN_REFRESH_IN_FLIGHT = set()


def _is_snapshot_stale(payload: dict | list | None, threshold_seconds: int) -> bool:
    generated_raw = (payload or {}).get("generated_at") if isinstance(payload, dict) else None
    generated_at = _parse_utc_iso_z(generated_raw if isinstance(generated_raw, str) else None)
    if generated_at is None:
        return True

    age_seconds = (datetime.now(timezone.utc) - generated_at).total_seconds()
    return age_seconds > max(0, int(threshold_seconds))


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
