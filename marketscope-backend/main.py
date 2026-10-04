"""MarketScope API entry point.

Creates the FastAPI app, runs startup work (DB tables, pool, cache preloads),
and registers the routers. The actual endpoints live in routers/, and the
logic behind them lives in services/.

Run locally with `python main.py` (or `uvicorn main:app`).
"""
import os
import socket
from contextlib import asynccontextmanager
from threading import Thread

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import get_allowed_origins
from core.database import DB_CONFIG, connect_with_retry
from db.schema import create_app_tables
from routers import (
    admin_auth,
    admin_users,
    analysis,
    auth,
    health,
    msmes,
    reports,
    spaces,
    trends,
    users,
    verified_features,
)
from services.ahp_weights import _load_ahp_weights_cache
from services.hazard import preload_hazard_layer_cache
from services.osm_data import preload_pbf_competitor_cache, preload_pbf_spatial_context_cache
from services.trend_scan import (
    mark_interrupted_trend_runs,
    start_trend_scan_worker,
    stop_trend_scan_worker,
)


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

    # Background trend scan worker (services/trend_scan.py). Scans are queued on
    # demand (login, profile save, Trends page), not on a timer.
    mark_interrupted_trend_runs()
    start_trend_scan_worker()
    yield
    stop_trend_scan_worker()
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

# Registration order matches the original single-file route order.
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(spaces.router)
app.include_router(admin_auth.router)
app.include_router(reports.router)
app.include_router(admin_users.router)
app.include_router(msmes.router)
app.include_router(verified_features.router)
app.include_router(analysis.router)
app.include_router(trends.router)


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