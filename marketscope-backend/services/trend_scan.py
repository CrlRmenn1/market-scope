"""Background trend scan: runs the main /analyze engine over many spots, saves every result.

How it works
  1. Someone asks for scans (login, profile save, opening Trends, "Rescan now")
     via request_trend_scans(["coffee", ...]).
  2. Cache check: a business type that already has a finished run younger than
     TREND_SCAN_FRESH_HOURS is skipped. That run's saved results are reused.
  3. Otherwise the business type goes on a queue. One worker thread takes it,
     builds the candidate spots (services/trend_candidates.py) and calls
     perform_analysis() on each one: the same function behind POST /analyze.
  4. Each result is saved as a row in trend_scan_results, and the run's progress
     is updated in trend_scan_runs. When it finishes, older runs are deleted.

Results depend only on (spot, business type), never on the user, so every user
interested in the same business type shares one scan.

Logs use the "[trend-scan]" prefix.
"""
import time
from queue import Empty, Queue
from threading import Event, Lock, Thread

from constants.msme import SME_DATABASE
from core.config import TREND_SCAN_FRESH_HOURS, TREND_SCAN_RADIUS
from db.trend_queries import (
    create_run,
    delete_older_runs,
    finish_run,
    get_latest_done_run,
    get_latest_run,
    insert_result,
    mark_interrupted_runs,
    open_trend_cursor,
    set_run_candidate_count,
    update_run_progress,
)
from models.requests import AnalysisRequest
from services.analysis import perform_analysis
from services.hazard import preload_hazard_layer_cache
from services.osm_data import preload_pbf_competitor_cache, preload_pbf_spatial_context_cache
from services.spaces import (
    fetch_active_space_markers_for_analysis,
    resolve_space_context_for_coords,
)
from services.trend_candidates import build_scan_candidates
from services.trend_scoring import pick_trend_business_types


PROGRESS_UPDATE_EVERY = 5

_SCAN_QUEUE = Queue()
_IN_FLIGHT = set()  # business types that are queued or being scanned right now
_IN_FLIGHT_LOCK = Lock()
_STOP_EVENT = Event()
_WORKER = None
_WORKER_LOCK = Lock()


def _log(message: str):
    print(f"[trend-scan] {message}", flush=True)


def is_run_fresh(run) -> bool:
    return bool(run) and int(run.get("age_seconds") or 0) <= TREND_SCAN_FRESH_HOURS * 3600


# ---- worker lifecycle -------------------------------------------------------

def start_trend_scan_worker():
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is not None and _WORKER.is_alive():
            return
        _STOP_EVENT.clear()
        _WORKER = Thread(target=_worker_loop, name="trend-scan-worker", daemon=True)
        _WORKER.start()


def stop_trend_scan_worker():
    _STOP_EVENT.set()


def mark_interrupted_trend_runs():
    """Called at startup: runs a previous server process left half-done."""
    try:
        with open_trend_cursor() as cursor:
            count = mark_interrupted_runs(cursor)
        if count:
            _log(f"marked {count} unfinished run(s) from the last server process as interrupted")
    except Exception as exc:
        _log(f"could not mark interrupted runs: {exc}")


def _worker_loop():
    while not _STOP_EVENT.is_set():
        try:
            business_key, trigger_source = _SCAN_QUEUE.get(timeout=1)
        except Empty:
            continue
        try:
            _run_business_scan(business_key, trigger_source)
        finally:
            with _IN_FLIGHT_LOCK:
                _IN_FLIGHT.discard(business_key)
            _SCAN_QUEUE.task_done()


# ---- asking for scans -------------------------------------------------------

def request_trend_scans(business_keys, trigger_source: str, force: bool = False):
    """Queue a scan for each business type that has no fresh saved results.

    force=True skips the freshness check ("Rescan now"). Returns the queued keys.
    """
    start_trend_scan_worker()
    queued = []

    for business_key in business_keys:
        if business_key not in SME_DATABASE:
            continue

        with _IN_FLIGHT_LOCK:
            if business_key in _IN_FLIGHT:
                continue

        if not force:
            try:
                with open_trend_cursor() as cursor:
                    done_run = get_latest_done_run(cursor, business_key, TREND_SCAN_RADIUS)
            except Exception as exc:
                _log(f"{business_key}: freshness check failed, not queuing ({exc})")
                continue
            if is_run_fresh(done_run):
                _log(f"{business_key}: skipped, saved results are fresh (run #{done_run['id']}, trigger={trigger_source})")
                continue

        with _IN_FLIGHT_LOCK:
            if business_key in _IN_FLIGHT:
                continue
            _IN_FLIGHT.add(business_key)
        _SCAN_QUEUE.put((business_key, trigger_source))
        queued.append(business_key)
        _log(f"{business_key}: queued (trigger={trigger_source}{', forced' if force else ''})")

    return queued


def queue_scans_for_user(user_profile, trigger_source: str, force: bool = False):
    """Queue scans for the business types picked for this user. Never raises,
    so it is safe to call from login and profile-save routes."""
    try:
        business_keys = [pick["business_key"] for pick in pick_trend_business_types(user_profile)]
        return request_trend_scans(business_keys, trigger_source, force=force)
    except Exception as exc:
        _log(f"could not queue scans ({trigger_source}): {exc}")
        return []


# ---- the scan itself --------------------------------------------------------

def scan_candidate(business_key: str, candidate: dict, space_markers):
    """One spot = one regular /analyze run (user_id=None, so no history row is saved)."""
    report = perform_analysis(
        AnalysisRequest(
            lat=float(candidate["lat"]),
            lon=float(candidate["lon"]),
            business_type=business_key,
            radius=TREND_SCAN_RADIUS,
            user_id=None,
        )
    )
    report["space_context"] = resolve_space_context_for_coords(
        candidate["lat"], candidate["lon"], space_markers=space_markers
    )
    report["trend_candidate"] = {"label": candidate.get("label"), "source": candidate.get("source")}
    return report


def _ensure_geo_data_loaded():
    """Without these caches perform_analysis falls back to neutral road/building
    scores, so a scan right after startup would save different scores than a
    manual scan. Each loader returns at once when already loaded, and waits
    when the startup preload thread is still loading it."""
    preload_hazard_layer_cache()
    preload_pbf_competitor_cache()
    preload_pbf_spatial_context_cache()


def _run_business_scan(business_key: str, trigger_source: str):
    started = time.monotonic()
    run_id = None
    try:
        _ensure_geo_data_loaded()
        with open_trend_cursor() as cursor:
            run_id = create_run(cursor, business_key, trigger_source, TREND_SCAN_RADIUS)
            space_markers = fetch_active_space_markers_for_analysis()
            candidates = build_scan_candidates(business_key, space_markers)
            set_run_candidate_count(cursor, run_id, len(candidates))
            _log(f"{business_key}: run #{run_id} started, {len(candidates)} spots ({len(space_markers)} listed spaces)")

            failed_spots = 0
            for index, candidate in enumerate(candidates, start=1):
                if _STOP_EVENT.is_set():
                    finish_run(cursor, run_id, "interrupted", "Server shutting down")
                    _log(f"{business_key}: run #{run_id} interrupted at {index - 1}/{len(candidates)}")
                    return

                try:
                    report = scan_candidate(business_key, candidate, space_markers)
                    insert_result(cursor, run_id, business_key, candidate, report)
                except Exception as exc:
                    failed_spots += 1
                    _log(f"{business_key}: spot '{candidate.get('label')}' failed: {exc}")

                if index % PROGRESS_UPDATE_EVERY == 0 or index == len(candidates):
                    update_run_progress(cursor, run_id, index)

            if failed_spots == len(candidates) and candidates:
                raise RuntimeError("every spot failed to scan")

            finish_run(cursor, run_id, "done")
            delete_older_runs(cursor, business_key, keep_run_id=run_id)

        _log(
            f"{business_key}: run #{run_id} done in {time.monotonic() - started:.1f}s "
            f"({len(candidates) - failed_spots} saved, {failed_spots} failed)"
        )
    except Exception as exc:
        _log(f"{business_key}: run #{run_id} failed: {exc}")
        if run_id is not None:
            try:
                with open_trend_cursor() as cursor:
                    finish_run(cursor, run_id, "failed", str(exc))
            except Exception:
                pass


# ---- reading the state ------------------------------------------------------

def get_business_scan_state(cursor, business_key: str):
    """Where a business type stands right now.

    state: "scanning" | "queued" | "ready" | "stale" | "failed" | "missing"
    done_run is the newest finished run (its results are shown even while a
    rescan is going on).
    """
    latest_run = get_latest_run(cursor, business_key)
    done_run = get_latest_done_run(cursor, business_key, TREND_SCAN_RADIUS)
    with _IN_FLIGHT_LOCK:
        in_flight = business_key in _IN_FLIGHT

    if in_flight and latest_run and latest_run["status"] == "running":
        state = "scanning"
    elif in_flight:
        state = "queued"
    elif done_run:
        state = "ready" if is_run_fresh(done_run) else "stale"
    elif latest_run and latest_run["status"] in ("failed", "interrupted"):
        state = "failed"
    else:
        state = "missing"

    progress = None
    if state == "scanning":
        progress = {
            "done": int(latest_run.get("scanned_count") or 0),
            "total": int(latest_run.get("candidate_count") or 0),
        }

    return {
        "state": state,
        "progress": progress,
        "done_run": done_run,
        "error": latest_run.get("error") if latest_run and state == "failed" else None,
    }


def get_in_flight_business_types():
    with _IN_FLIGHT_LOCK:
        return sorted(_IN_FLIGHT)
