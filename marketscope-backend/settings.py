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