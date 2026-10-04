"""Every environment variable the backend reads, in one place.

See .env.example in the backend folder for the full list with defaults.
"""
import os
from urllib.parse import urlparse


def get_database_config():
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        parsed_database_url = urlparse(database_url)
        return {
            "dbname": parsed_database_url.path.lstrip("/") or "marketscope_db",
            "user": parsed_database_url.username or "postgres",
            "password": parsed_database_url.password or "",
            "host": parsed_database_url.hostname or "localhost",
            "port": str(parsed_database_url.port or 5432),
            "connect_timeout": int(os.environ.get("MARKETSCOPE_DB_CONNECT_TIMEOUT", "8")),
            "options": os.environ.get("MARKETSCOPE_DB_OPTIONS", "-c statement_timeout=10000"),
        }

    return {
        "dbname": os.environ.get("MARKETSCOPE_DB_NAME", "marketscope_db"),
        "user": os.environ.get("MARKETSCOPE_DB_USER", "postgres"),
        "password": os.environ.get("MARKETSCOPE_DB_PASSWORD", "1234"),
        "host": os.environ.get("MARKETSCOPE_DB_HOST", "localhost"),
        "port": os.environ.get("MARKETSCOPE_DB_PORT", "5432"),
        "connect_timeout": int(os.environ.get("MARKETSCOPE_DB_CONNECT_TIMEOUT", "8")),
        "options": os.environ.get("MARKETSCOPE_DB_OPTIONS", "-c statement_timeout=10000"),
    }


def get_startup_database_config(base_config):
    startup_config = dict(base_config)
    startup_options = os.environ.get("MARKETSCOPE_DB_STARTUP_OPTIONS", "-c statement_timeout=0")

    if startup_options:
        startup_config["options"] = startup_options
    else:
        startup_config.pop("options", None)

    return startup_config


def get_allowed_origins():
    allowed_origins_env = os.environ.get("MARKETSCOPE_ALLOWED_ORIGINS", "").strip()
    return [
        origin.strip()
        for origin in allowed_origins_env.split(",")
        if origin.strip()
    ]


# Admin account and token
ADMIN_EMAIL = os.environ.get("MARKETSCOPE_ADMIN_EMAIL", "admin@marketscope.local")
ADMIN_PASSWORD = os.environ.get("MARKETSCOPE_ADMIN_PASSWORD", "admin123")
ADMIN_TOKEN = os.environ.get("MARKETSCOPE_ADMIN_TOKEN", "marketscope-admin-local-token")

# Password reset codes
RESET_CODE_TTL_MINUTES = int(os.environ.get("MARKETSCOPE_RESET_CODE_TTL_MINUTES", "10"))
RESET_CODE_DEV_MODE = os.environ.get("MARKETSCOPE_RESET_CODE_DEV_MODE", "false").lower() == "true"

# Outgoing email (password reset)
SMTP_HOST = os.environ.get("MARKETSCOPE_SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("MARKETSCOPE_SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("MARKETSCOPE_SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.environ.get("MARKETSCOPE_SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.environ.get("MARKETSCOPE_SMTP_FROM_EMAIL", "").strip()
SMTP_FROM_NAME = os.environ.get("MARKETSCOPE_SMTP_FROM_NAME", "MarketScope")
SMTP_USE_TLS = os.environ.get("MARKETSCOPE_SMTP_USE_TLS", "true").lower() == "true"
SMTP_USE_SSL = os.environ.get("MARKETSCOPE_SMTP_USE_SSL", "false").lower() == "true"

# Background trend scan (services/trend_scan.py)
# Radius passed to perform_analysis for every scanned spot (same default as /analyze).
TREND_SCAN_RADIUS = int(os.environ.get("MARKETSCOPE_TREND_SCAN_RADIUS", "340"))
# A finished scan younger than this is reused instead of scanning again.
TREND_SCAN_FRESH_HOURS = int(os.environ.get("MARKETSCOPE_TREND_SCAN_FRESH_HOURS", "24"))
# Spots scoring at least this are "high chance" (same cut-off as the "Favorable Location" insight).
TREND_HIGH_CHANCE_MIN_SCORE = int(os.environ.get("MARKETSCOPE_TREND_HIGH_CHANCE_MIN_SCORE", "70"))
