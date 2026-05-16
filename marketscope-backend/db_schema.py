import os
import random
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import bcrypt
import psycopg2
from fastapi import HTTPException


ADMIN_EMAIL = os.environ.get("MARKETSCOPE_ADMIN_EMAIL", "admin@marketscope.local")
ADMIN_PASSWORD = os.environ.get("MARKETSCOPE_ADMIN_PASSWORD", "admin123")
ADMIN_TOKEN = os.environ.get("MARKETSCOPE_ADMIN_TOKEN", "marketscope-admin-local-token")
RESET_CODE_TTL_MINUTES = int(os.environ.get("MARKETSCOPE_RESET_CODE_TTL_MINUTES", "10"))
RESET_CODE_DEV_MODE = os.environ.get("MARKETSCOPE_RESET_CODE_DEV_MODE", "false").lower() == "true"

SMTP_HOST = os.environ.get("MARKETSCOPE_SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("MARKETSCOPE_SMTP_PORT", "587"))
SMTP_USERNAME = os.environ.get("MARKETSCOPE_SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.environ.get("MARKETSCOPE_SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.environ.get("MARKETSCOPE_SMTP_FROM_EMAIL", "").strip()
SMTP_FROM_NAME = os.environ.get("MARKETSCOPE_SMTP_FROM_NAME", "MarketScope")
SMTP_USE_TLS = os.environ.get("MARKETSCOPE_SMTP_USE_TLS", "true").lower() == "true"
SMTP_USE_SSL = os.environ.get("MARKETSCOPE_SMTP_USE_SSL", "false").lower() == "true"


def get_startup_db_config(base_config):
    startup_config = dict(base_config)
    startup_options = os.environ.get("MARKETSCOPE_DB_STARTUP_OPTIONS", "-c statement_timeout=0")

    if startup_options:
        startup_config["options"] = startup_options
    else:
        startup_config.pop("options", None)

    return startup_config


def create_app_tables(db_config):
    """Create app tables with retry logic for Render deployments."""
    import time
    max_retries = 3
    initial_delay = 1
    
    for attempt in range(max_retries):
        try:
            print(f"[DB Schema] Attempt {attempt + 1}/{max_retries} to create tables...", flush=True)
            conn = psycopg2.connect(**get_startup_db_config(db_config))
            cursor = conn.cursor()
            ensure_users_table(cursor)
            user_pk_column = get_users_primary_key_column(cursor)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_history (
                    history_id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL REFERENCES users(%s) ON DELETE CASCADE,
                    business_type VARCHAR(255) NOT NULL,
                    viability_score INTEGER NOT NULL,
                    target_lat DOUBLE PRECISION NOT NULL,
                    target_lon DOUBLE PRECISION NOT NULL,
                    radius_used INTEGER NOT NULL,
                    insight TEXT,
                    competitors_found INTEGER,
                    competitor_locations JSONB,
                    scan_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """ % user_pk_column
            )

            ensure_history_table_columns(cursor)
            ensure_users_profile_columns(cursor)
            ensure_custom_msme_table(cursor)
            ensure_admin_users_table(cursor)
            ensure_user_space_submissions_table(cursor, user_pk_column)
            ensure_admin_space_submissions_table(cursor)
            ensure_password_reset_codes_table(cursor, user_pk_column)
            ensure_trend_scan_snapshots_table(cursor)
            ensure_default_admin_user(cursor)

            conn.commit()
            cursor.close()
            conn.close()
            print("[DB Schema] ✓ Tables created successfully", flush=True)
            return  # Success
        except psycopg2.OperationalError as e:
            print(f"[DB Schema] ✗ Connection error on attempt {attempt + 1}: {e}", flush=True)
            if attempt < max_retries - 1:
                wait_time = initial_delay * (2 ** attempt)
                print(f"[DB Schema] Retrying in {wait_time}s...", flush=True)
                time.sleep(wait_time)
            else:
                print(f"[DB Schema] Failed to create tables after {max_retries} attempts", flush=True)
                raise
        except Exception as e:
            print(f"[DB Schema] ✗ Unexpected error on attempt {attempt + 1}: {e}", flush=True)
            raise


def ensure_users_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            user_id SERIAL PRIMARY KEY,
            full_name VARCHAR(255) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def ensure_history_table_columns(cursor):
    cursor.execute("ALTER TABLE analysis_history ADD COLUMN IF NOT EXISTS competitors_found INTEGER")
    cursor.execute("ALTER TABLE analysis_history ADD COLUMN IF NOT EXISTS competitor_locations JSONB")
    cursor.execute("ALTER TABLE analysis_history ADD COLUMN IF NOT EXISTS breakdown JSONB")


def ensure_users_profile_columns(cursor):
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS address TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS cellphone_number VARCHAR(32)")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS age INTEGER")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS birthday DATE")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS primary_business VARCHAR(120)")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS startup_capital INTEGER")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS risk_tolerance VARCHAR(50)")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_setup VARCHAR(50)")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS time_commitment VARCHAR(50)")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS target_payback_months INTEGER")


def ensure_custom_msme_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_msme (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            business_type VARCHAR(255) NOT NULL,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def ensure_user_space_submissions_table(cursor, user_pk_column):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_space_submissions (
            id SERIAL PRIMARY KEY,
            submitted_by_user_id INTEGER NOT NULL REFERENCES users(%s) ON DELETE CASCADE,
            title TEXT NOT NULL,
            listing_mode VARCHAR(20) NOT NULL,
            guarantee_level VARCHAR(20) NOT NULL DEFAULT 'potential',
            property_type VARCHAR(120),
            business_type VARCHAR(120),
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            address_text TEXT,
            price_min INTEGER,
            price_max INTEGER,
            contact_info TEXT,
            notes TEXT,
            photo_urls JSONB,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            review_note TEXT,
            reviewed_by_admin_email TEXT,
            reviewed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """ % user_pk_column
    )
    cursor.execute("ALTER TABLE user_space_submissions ADD COLUMN IF NOT EXISTS photo_urls JSONB")


def ensure_admin_space_submissions_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_space_submissions (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            listing_mode VARCHAR(20) NOT NULL,
            guarantee_level VARCHAR(20) NOT NULL DEFAULT 'potential',
            confidence_score INTEGER,
            property_type VARCHAR(120),
            business_type VARCHAR(120),
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            address_text TEXT,
            price_min INTEGER,
            price_max INTEGER,
            source_note TEXT,
            contact_info TEXT,
            notes TEXT,
            photo_urls JSONB,
            verified_at DATE,
            expires_at DATE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by_admin_email TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("ALTER TABLE admin_space_submissions ADD COLUMN IF NOT EXISTS photo_urls JSONB")


def ensure_admin_users_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def ensure_password_reset_codes_table(cursor, user_pk_column):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_codes (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(%s) ON DELETE CASCADE,
            code_hash TEXT NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """ % user_pk_column
    )


def ensure_trend_scan_snapshots_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS trend_scan_snapshots (
            id SERIAL PRIMARY KEY,
            radius INTEGER NOT NULL,
            snapshot_payload JSONB NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(radius)
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_trend_snapshots_radius_updated
        ON trend_scan_snapshots(radius, updated_at DESC)
        """
    )


def ensure_default_admin_user(cursor):
    cursor.execute("SELECT id FROM admin_users WHERE email = %s", (ADMIN_EMAIL,))
    existing = cursor.fetchone()
    if existing:
        return

    hashed_password = bcrypt.hashpw(ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    cursor.execute(
        """
        INSERT INTO admin_users (email, password_hash)
        VALUES (%s, %s)
        """,
        (ADMIN_EMAIL, hashed_password)
    )


def get_users_primary_key_column(cursor):
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND column_name IN ('user_id', 'id')
        ORDER BY CASE WHEN column_name = 'user_id' THEN 0 ELSE 1 END
        LIMIT 1
        """
    )
    result = cursor.fetchone()
    if not result:
        raise HTTPException(status_code=500, detail="Users table must include either user_id or id")
    if isinstance(result, dict):
        return result.get('column_name')
    return result[0]


def get_analysis_history_pk_column(cursor):
    cursor.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'analysis_history'
          AND column_name IN ('history_id', 'id')
        ORDER BY CASE WHEN column_name = 'history_id' THEN 0 ELSE 1 END
        LIMIT 1
        """
    )
    result = cursor.fetchone()
    if not result:
        raise HTTPException(status_code=500, detail="analysis_history table must include either history_id or id")
    if isinstance(result, dict):
        return result.get('column_name')
    return result[0]


async def get_users_primary_key_column_async(conn):
    result = await conn.fetchrow(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'users'
          AND column_name IN ('user_id', 'id')
        ORDER BY CASE WHEN column_name = 'user_id' THEN 0 ELSE 1 END
        LIMIT 1
        """
    )
    if not result:
        raise HTTPException(status_code=500, detail="Users table must include either user_id or id")
    return result["column_name"]


async def get_analysis_history_pk_column_async(conn):
    result = await conn.fetchrow(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'analysis_history'
          AND column_name IN ('history_id', 'id')
        ORDER BY CASE WHEN column_name = 'history_id' THEN 0 ELSE 1 END
        LIMIT 1
        """
    )
    if not result:
        raise HTTPException(status_code=500, detail="analysis_history table must include either history_id or id")
    return result["column_name"]


def generate_reset_code():
    return ''.join(random.choice('0123456789') for _ in range(6))


def is_smtp_configured():
    return bool(SMTP_HOST and SMTP_FROM_EMAIL)


def send_password_reset_email(target_email: str, reset_code: str):
    if not is_smtp_configured():
        print(f"Password reset code for {target_email}: {reset_code}")
        return

    msg = EmailMessage()
    msg["Subject"] = f"{SMTP_FROM_NAME} Password Reset Code"
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    msg["To"] = target_email
    msg.set_content(
        f"Your MarketScope password reset code is: {reset_code}\n\n"
        f"This code expires in {RESET_CODE_TTL_MINUTES} minutes."
    )

    if SMTP_USE_SSL:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            if SMTP_USERNAME:
                smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
            smtp.send_message(msg)
        return

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
        if SMTP_USE_TLS:
            smtp.starttls()
        if SMTP_USERNAME:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtp.send_message(msg)