"""Database connection settings and the asyncpg pool factory."""
import asyncio

import asyncpg

from core.config import get_database_config


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
