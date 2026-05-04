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
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import bcrypt

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
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL:
    parsed_database_url = urlparse(DATABASE_URL)
    DB_CONFIG = {
        "dbname": parsed_database_url.path.lstrip("/") or "marketscope_db",
        "user": parsed_database_url.username or "postgres",
        "password": parsed_database_url.password or "",
        "host": parsed_database_url.hostname or "localhost",
        "port": str(parsed_database_url.port or 5432),
        "connect_timeout": int(os.environ.get("MARKETSCOPE_DB_CONNECT_TIMEOUT", "8")),
        "options": os.environ.get("MARKETSCOPE_DB_OPTIONS", "-c statement_timeout=10000"),
    }
else:
    DB_CONFIG = {
        "dbname": os.environ.get("MARKETSCOPE_DB_NAME", "marketscope_db"),
        "user": os.environ.get("MARKETSCOPE_DB_USER", "postgres"),
        "password": os.environ.get("MARKETSCOPE_DB_PASSWORD", "1234"),
        "host": os.environ.get("MARKETSCOPE_DB_HOST", "localhost"),
        "port": os.environ.get("MARKETSCOPE_DB_PORT", "5432"),
        "connect_timeout": int(os.environ.get("MARKETSCOPE_DB_CONNECT_TIMEOUT", "8")),
        "options": os.environ.get("MARKETSCOPE_DB_OPTIONS", "-c statement_timeout=10000"),
    }


def get_startup_db_config():
    startup_config = dict(DB_CONFIG)
    startup_options = os.environ.get("MARKETSCOPE_DB_STARTUP_OPTIONS", "-c statement_timeout=0")

    if startup_options:
        startup_config["options"] = startup_options
    else:
        startup_config.pop("options", None)

    return startup_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_app_tables()
    # Create asyncpg pool and attach to app state
    app.state.db_pool = await asyncpg.create_pool(
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["dbname"],
        host=DB_CONFIG["host"],
        port=int(DB_CONFIG["port"]),
        min_size=2,
        max_size=10,
        timeout=DB_CONFIG.get("connect_timeout", 8),
    )
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

allowed_origins = [
    origin.strip()
    for origin in os.environ.get(
        "MARKETSCOPE_ALLOWED_ORIGINS",
        "http://localhost:5173,http://localhost:4173,http://localhost:3000,https://market-scope.onrender.com"
    ).split(",")
    if origin.strip()
]

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


def create_app_tables():
    conn = psycopg2.connect(**get_startup_db_config())
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

    # Keep existing deployments compatible by ensuring optional columns exist.
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
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS risk_tolerance VARCHAR(20)")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS preferred_setup VARCHAR(40)")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS time_commitment VARCHAR(20)")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS target_payback_months INTEGER")


def ensure_custom_msme_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS custom_msme (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            business_type VARCHAR(64) NOT NULL,
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Backfill for older local DBs where custom_msme existed before created_at was introduced.
    cursor.execute("ALTER TABLE custom_msme ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    cursor.execute("UPDATE custom_msme SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL")


def ensure_user_space_submissions_table(cursor, user_pk_column):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_space_submissions (
            id SERIAL PRIMARY KEY,
            submitted_by_user_id INTEGER NOT NULL REFERENCES users(%s) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            listing_mode VARCHAR(12) NOT NULL,
            guarantee_level VARCHAR(20) NOT NULL DEFAULT 'guaranteed',
            property_type VARCHAR(80),
            business_type VARCHAR(64),
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            address_text TEXT,
            price_min INTEGER,
            price_max INTEGER,
            contact_info TEXT,
            notes TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            review_note TEXT,
            reviewed_by_admin_email VARCHAR(255),
            reviewed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """ % user_pk_column
    )
    cursor.execute("ALTER TABLE user_space_submissions ADD COLUMN IF NOT EXISTS business_type VARCHAR(64)")
    cursor.execute("ALTER TABLE user_space_submissions ADD COLUMN IF NOT EXISTS guarantee_level VARCHAR(20) DEFAULT 'guaranteed'")
    cursor.execute("ALTER TABLE user_space_submissions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")


def ensure_admin_space_submissions_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_space_submissions (
            id SERIAL PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            listing_mode VARCHAR(12) NOT NULL,
            guarantee_level VARCHAR(20) NOT NULL DEFAULT 'potential',
            confidence_score INTEGER,
            property_type VARCHAR(80),
            business_type VARCHAR(64),
            latitude DOUBLE PRECISION NOT NULL,
            longitude DOUBLE PRECISION NOT NULL,
            address_text TEXT,
            price_min INTEGER,
            price_max INTEGER,
            source_note TEXT,
            contact_info TEXT,
            notes TEXT,
            verified_at DATE,
            expires_at DATE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_by_admin_email VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute("ALTER TABLE admin_space_submissions ADD COLUMN IF NOT EXISTS confidence_score INTEGER")
    cursor.execute("ALTER TABLE admin_space_submissions ADD COLUMN IF NOT EXISTS business_type VARCHAR(64)")
    cursor.execute("ALTER TABLE admin_space_submissions ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")


def ensure_admin_users_table(cursor):
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
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
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_password_reset_codes_user_created
        ON password_reset_codes(user_id, created_at DESC)
        """
    )


def ensure_trend_scan_snapshots_table(cursor):
    """Create trend_scan_snapshots table for persistent trend caching."""
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


def generate_reset_code():
    return ''.join(random.choice('0123456789') for _ in range(6))


def is_smtp_configured():
    return bool(SMTP_HOST and SMTP_FROM_EMAIL)


def send_password_reset_email(target_email: str, reset_code: str):
    if not is_smtp_configured():
        raise HTTPException(
            status_code=503,
            detail="Password reset email is not configured on the server"
        )

    msg = EmailMessage()
    msg["Subject"] = "Your MarketScope Password Reset Code"
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    msg["To"] = target_email
    msg.set_content(
        "\n".join([
            "Hello,",
            "",
            "Use this code to reset your MarketScope password:",
            f"{reset_code}",
            "",
            f"This code will expire in {RESET_CODE_TTL_MINUTES} minutes.",
            "If you did not request this, you can ignore this email.",
        ])
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


def saturation_score_from_competitors(competitor_count):
    if competitor_count <= 0:
        return 25
    if competitor_count == 1:
        return 20
    if competitor_count <= 3:
        return 15
    if competitor_count <= 5:
        return 10
    return 5


def build_legacy_breakdown(row):
    competitors_found = row.get("competitors_found") or 0
    total_score = row.get("viability_score") or 0
    saturation_score = saturation_score_from_competitors(competitors_found)

    remainder = max(0, total_score - saturation_score)
    base_split = int(remainder / 3)
    extra = remainder - (base_split * 3)
    zoning_score = min(25, base_split + (1 if extra > 0 else 0))
    hazard_score = min(25, base_split + (1 if extra > 1 else 0))
    demand_score = min(25, base_split)

    legacy_note = "Estimated for legacy record. Run a fresh analysis to store exact factor-level values."
    return {
        "zoning": {
            "score": zoning_score,
            "status": "Legacy Estimate",
            "description": legacy_note,
            "details": legacy_note,
            "estimated": True
        },
        "hazard": {
            "score": hazard_score,
            "status": "Legacy Estimate",
            "description": legacy_note,
            "details": legacy_note,
            "estimated": True
        },
        "saturation": {
            "score": saturation_score,
            "status": "Derived from competitors",
            "description": f"{competitors_found} nearby competitor(s) detected in saved record.",
            "details": "Saturation score is mapped from saved competitor count.",
            "estimated": True
        },
        "demand": {
            "score": demand_score,
            "status": "Legacy Estimate",
            "description": legacy_note,
            "details": legacy_note,
            "estimated": True
        }
    }


def normalize_history_row(row):
    if row.get("competitors_found") is None:
        competitor_locations = row.get("competitor_locations")
        if isinstance(competitor_locations, list):
            row["competitors_found"] = len(competitor_locations)
        else:
            row["competitors_found"] = 0

    if row.get("radius_meters") is None:
        row["radius_meters"] = 340

    # Backward-compatibility guard: older records may contain context markers
    # in competitor_locations even when competitors_found is 0.
    competitors_found = int(row.get("competitors_found") or 0)
    if competitors_found <= 0:
        row["competitor_locations"] = []

    breakdown = row.get("breakdown")
    if not isinstance(breakdown, dict) or not breakdown:
        row["breakdown"] = build_legacy_breakdown(row)

    return row


# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

@app.post("/register")
async def register(user: RegisterUser):
    try:
        pool = app.state.db_pool
        async with pool.acquire() as conn:
            user_pk_column = await get_users_primary_key_column_async(conn)
            # Check if email already exists
            row = await conn.fetchrow(f"SELECT {user_pk_column} FROM users WHERE email = $1", user.email)
            if row:
                raise HTTPException(status_code=400, detail="Email already registered")

            # Hash the password
            salt = bcrypt.gensalt()
            hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), salt).decode('utf-8')

            # Save to database
            insert_query = f"""
                INSERT INTO users (
                    full_name, email, password_hash,
                    address, cellphone_number, avatar_url,
                    age, birthday, primary_business,
                    startup_capital, risk_tolerance, preferred_setup,
                    time_commitment, target_payback_months
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                RETURNING
                    {user_pk_column}, full_name, email, created_at,
                    address, cellphone_number, avatar_url,
                    age, birthday, primary_business,
                    startup_capital, risk_tolerance, preferred_setup,
                    time_commitment, target_payback_months
            """
            values = (
                user.full_name,
                user.email,
                hashed_password,
                user.address or None,
                user.cellphone_number or None,
                user.avatar_url or None,
                user.age,
                user.birthday,
                user.primary_business or None,
                user.startup_capital,
                user.risk_tolerance or None,
                user.preferred_setup or None,
                user.time_commitment or None,
                user.target_payback_months,
            )
            new_user = await conn.fetchrow(insert_query, *values)

        return {
            "status": "success",
            "user": {
                "id": new_user[0],
                "user_id": new_user[0],
                "name": new_user[1],
                "email": new_user[2],
                "created_at": new_user[3],
                "address": new_user[4],
                "cellphone_number": new_user[5],
                "avatar_url": new_user[6],
                "age": new_user[7],
                "birthday": new_user[8],
                "primary_business": new_user[9],
                "startup_capital": new_user[10],
                "risk_tolerance": new_user[11],
                "preferred_setup": new_user[12],
                "time_commitment": new_user[13],
                "target_payback_months": new_user[14],
            }
        }
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/login")
async def login(user: LoginUser):
    try:
        pool = app.state.db_pool
        async with pool.acquire() as conn:
            user_pk_column = await get_users_primary_key_column_async(conn)
            row = await conn.fetchrow(
                f"""
                SELECT
                    {user_pk_column} AS user_id,
                    full_name, email, password_hash, created_at,
                    address, cellphone_number, avatar_url,
                    age, birthday, primary_business,
                    startup_capital, risk_tolerance, preferred_setup,
                    time_commitment, target_payback_months
                FROM users
                WHERE email = $1
                """,
                user.email
            )

        db_user = dict(row) if row else None

        # Verify password
        if not db_user or not bcrypt.checkpw(user.password.encode('utf-8'), db_user['password_hash'].encode('utf-8')):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        return {
            "status": "success",
            "user": {
                "id": db_user['user_id'],
                "user_id": db_user['user_id'],
                "name": db_user['full_name'],
                "email": db_user['email'],
                "created_at": db_user['created_at'],
                "address": db_user.get('address'),
                "cellphone_number": db_user.get('cellphone_number'),
                "avatar_url": db_user.get('avatar_url'),
                "age": db_user.get('age'),
                "birthday": db_user.get('birthday'),
                "primary_business": db_user.get('primary_business'),
                "startup_capital": db_user.get('startup_capital'),
                "risk_tolerance": db_user.get('risk_tolerance'),
                "preferred_setup": db_user.get('preferred_setup'),
                "time_commitment": db_user.get('time_commitment'),
                "target_payback_months": db_user.get('target_payback_months'),
            }
        }
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/forgot-password")
def forgot_password(payload: ForgotPasswordRequest):
    conn = None
    cursor = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        user_pk_column = get_users_primary_key_column(cursor)

        cursor.execute(
            f"SELECT {user_pk_column} AS user_id, email FROM users WHERE email = %s",
            (payload.email,)
        )
        db_user = cursor.fetchone()

        # Always return a generic success message to avoid account enumeration.
        if not db_user:
            return {
                "status": "success",
                "detail": "If your account exists, a reset code has been sent to your email."
            }

        user_id = db_user['user_id']
        reset_code = generate_reset_code()
        reset_code_hash = bcrypt.hashpw(reset_code.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        expires_at = utc_now_naive() + timedelta(minutes=RESET_CODE_TTL_MINUTES)

        cursor.execute(
            """
            UPDATE password_reset_codes
            SET used_at = CURRENT_TIMESTAMP
            WHERE user_id = %s AND used_at IS NULL
            """,
            (user_id,)
        )
        cursor.execute(
            """
            INSERT INTO password_reset_codes (user_id, code_hash, expires_at)
            VALUES (%s, %s, %s)
            """,
            (user_id, reset_code_hash, expires_at)
        )

        send_password_reset_email(payload.email, reset_code)

        conn.commit()

        response = {
            "status": "success",
            "detail": "If your account exists, a reset code has been sent to your email."
        }
        if RESET_CODE_DEV_MODE:
            response["reset_code"] = reset_code

        return response
    except Exception as e:
        if conn:
            conn.rollback()
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


@app.post("/reset-password")
def reset_password(payload: ResetPasswordRequest):
    try:
        if len(payload.new_password.strip()) < 6:
            raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        user_pk_column = get_users_primary_key_column(cursor)

        cursor.execute(
            f"SELECT {user_pk_column} AS user_id FROM users WHERE email = %s",
            (payload.email,)
        )
        db_user = cursor.fetchone()
        if not db_user:
            raise HTTPException(status_code=400, detail="Invalid reset request")

        cursor.execute(
            """
            SELECT id, code_hash, expires_at
            FROM password_reset_codes
            WHERE user_id = %s AND used_at IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (db_user['user_id'],)
        )
        reset_row = cursor.fetchone()
        if not reset_row:
            raise HTTPException(status_code=400, detail="No active reset code found")

        expires_at = reset_row['expires_at']
        if isinstance(expires_at, datetime) and expires_at < utc_now_naive():
            raise HTTPException(status_code=400, detail="Reset code expired. Request a new one.")

        is_valid_code = bcrypt.checkpw(payload.code.encode('utf-8'), reset_row['code_hash'].encode('utf-8'))
        if not is_valid_code:
            raise HTTPException(status_code=400, detail="Invalid reset code")

        new_hash = bcrypt.hashpw(payload.new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cursor.execute(
            f"UPDATE users SET password_hash = %s WHERE {user_pk_column} = %s",
            (new_hash, db_user['user_id'])
        )
        cursor.execute(
            "UPDATE password_reset_codes SET used_at = CURRENT_TIMESTAMP WHERE id = %s",
            (reset_row['id'],)
        )

        conn.commit()
        cursor.close()
        conn.close()

        return {"status": "success", "detail": "Password reset successful. You can now log in."}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/reset-password-direct")
def reset_password_direct(payload: DirectResetPasswordRequest):
    try:
        if len(payload.new_password.strip()) < 6:
            raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        user_pk_column = get_users_primary_key_column(cursor)

        cursor.execute(
            f"SELECT {user_pk_column} AS user_id FROM users WHERE email = %s",
            (payload.email,)
        )
        db_user = cursor.fetchone()
        if not db_user:
            raise HTTPException(status_code=404, detail="Email not found")

        new_hash = bcrypt.hashpw(payload.new_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        cursor.execute(
            f"UPDATE users SET password_hash = %s WHERE {user_pk_column} = %s",
            (new_hash, db_user['user_id'])
        )

        conn.commit()
        cursor.close()
        conn.close()

        return {"status": "success", "detail": "Password reset successful. You can now log in."}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}")
async def get_user_profile(user_id: int):
    try:
        pool = app.state.db_pool
        async with pool.acquire() as conn:
            user_pk_column = await get_users_primary_key_column_async(conn)
            profile = await conn.fetchrow(
            f"""
            SELECT
                {user_pk_column} AS user_id,
                full_name, email, created_at,
                address, cellphone_number, avatar_url,
                age, birthday, primary_business,
                startup_capital, risk_tolerance, preferred_setup,
                time_commitment, target_payback_months
            FROM users
            WHERE {user_pk_column} = $1
            """,
            user_id,
        )

        if not profile:
            raise HTTPException(status_code=404, detail="User not found")

        return {"status": "success", "user": dict(profile)}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/users/{user_id}")
async def update_user_profile(user_id: int, payload: UpdateUserProfile):
    try:
        pool = app.state.db_pool
        async with pool.acquire() as conn:
            user_pk_column = await get_users_primary_key_column_async(conn)
            existing_user = await conn.fetchrow(
                f"SELECT {user_pk_column} AS user_id FROM users WHERE {user_pk_column} = $1",
                user_id,
            )
        if not existing_user:
            raise HTTPException(status_code=404, detail="User not found")

        async with pool.acquire() as conn:
            duplicate_email = await conn.fetchrow(
                f"""
                SELECT {user_pk_column} AS user_id
                FROM users
                WHERE email = $1 AND {user_pk_column} <> $2
                """,
                payload.email,
                user_id,
            )
        if duplicate_email:
            raise HTTPException(status_code=400, detail="Email already registered")

        async with pool.acquire() as conn:
            updated_user = await conn.fetchrow(
                f"""
                UPDATE users
                SET
                    full_name = $1,
                    email = $2,
                    address = $3,
                    cellphone_number = $4,
                    avatar_url = $5,
                    age = $6,
                    birthday = $7,
                    primary_business = $8,
                    startup_capital = $9,
                    risk_tolerance = $10,
                    preferred_setup = $11,
                    time_commitment = $12,
                    target_payback_months = $13
                WHERE {user_pk_column} = $14
                RETURNING
                    {user_pk_column} AS user_id,
                    full_name, email, created_at,
                    address, cellphone_number, avatar_url,
                    age, birthday, primary_business,
                    startup_capital, risk_tolerance, preferred_setup,
                    time_commitment, target_payback_months
                """,
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
                user_id,
            )

        return {"status": "success", "user": dict(updated_user) if updated_user else None}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}/history")
async def get_user_history(user_id: int):
    try:
        pool = app.state.db_pool
        async with pool.acquire() as conn:
            history_pk_column = await get_analysis_history_pk_column_async(conn)
            rows = await conn.fetch(
            f"""
            SELECT
                {history_pk_column} AS history_id,
                business_type,
                viability_score,
                target_lat,
                target_lon AS target_lng,
                radius_used AS radius_meters,
                insight,
                COALESCE(
                    competitors_found,
                    CASE
                        WHEN competitor_locations IS NOT NULL THEN jsonb_array_length(competitor_locations)
                        ELSE 0
                    END,
                    0
                ) AS competitors_found,
                competitor_locations,
                scan_date AS created_at,
                breakdown
            FROM analysis_history
            WHERE user_id = $1
            ORDER BY scan_date DESC, {history_pk_column} DESC
            """,
            user_id,
        )

        history = [dict(row) for row in rows]

        for row in history:
            normalize_history_row(row)

        return {"status": "success", "history": history}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}/history/{history_id}")
async def get_user_history_item(user_id: int, history_id: int):
    try:
        pool = app.state.db_pool
        async with pool.acquire() as conn:
            history_pk_column = await get_analysis_history_pk_column_async(conn)
            history_item = await conn.fetchrow(
            f"""
            SELECT
                {history_pk_column} AS history_id,
                business_type,
                viability_score,
                target_lat,
                target_lon AS target_lng,
                radius_used AS radius_meters,
                insight,
                COALESCE(
                    competitors_found,
                    CASE
                        WHEN competitor_locations IS NOT NULL THEN jsonb_array_length(competitor_locations)
                        ELSE 0
                    END,
                    0
                ) AS competitors_found,
                competitor_locations,
                scan_date AS created_at,
                breakdown
            FROM analysis_history
            WHERE user_id = $1 AND {history_pk_column} = $2
            LIMIT 1
            """,
            user_id,
            history_id,
        )

        if not history_item:
            raise HTTPException(status_code=404, detail="History item not found")

        history_payload = dict(history_item)
        normalize_history_row(history_payload)
        return {"status": "success", "history": history_payload}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/users/{user_id}/history/{history_id}")
async def delete_user_history_item(user_id: int, history_id: int):
    try:
        pool = app.state.db_pool
        async with pool.acquire() as conn:
            history_pk_column = await get_analysis_history_pk_column_async(conn)
            deleted_row = await conn.fetchrow(
                f"DELETE FROM analysis_history WHERE user_id = $1 AND {history_pk_column} = $2 RETURNING {history_pk_column}",
                user_id,
                history_id,
            )

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

TREND_BUSINESS_REQUIREMENTS = {
    "coffee": {"capital_min": 120000, "capital_max": 450000, "risk": "medium", "setup": "storefront", "payback_months": 18},
    "print": {"capital_min": 90000, "capital_max": 280000, "risk": "low", "setup": "storefront", "payback_months": 20},
    "laundry": {"capital_min": 180000, "capital_max": 520000, "risk": "medium", "setup": "storefront", "payback_months": 22},
    "carwash": {"capital_min": 220000, "capital_max": 700000, "risk": "high", "setup": "roadside", "payback_months": 24},
    "kiosk": {"capital_min": 50000, "capital_max": 220000, "risk": "medium", "setup": "kiosk", "payback_months": 12},
    "water": {"capital_min": 120000, "capital_max": 360000, "risk": "low", "setup": "storefront", "payback_months": 18},
    "bakery": {"capital_min": 130000, "capital_max": 420000, "risk": "medium", "setup": "storefront", "payback_months": 18},
    "pharmacy": {"capital_min": 250000, "capital_max": 900000, "risk": "medium", "setup": "storefront", "payback_months": 26},
    "barber": {"capital_min": 70000, "capital_max": 260000, "risk": "low", "setup": "storefront", "payback_months": 14},
    "moto": {"capital_min": 100000, "capital_max": 350000, "risk": "medium", "setup": "roadside", "payback_months": 16},
    "internet": {"capital_min": 160000, "capital_max": 480000, "risk": "high", "setup": "storefront", "payback_months": 24},
    "meat": {"capital_min": 110000, "capital_max": 320000, "risk": "medium", "setup": "market-stall", "payback_months": 15},
    "hardware": {"capital_min": 300000, "capital_max": 1200000, "risk": "medium", "setup": "warehouse", "payback_months": 28},
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
    dphi = math.radians(lat2 - lat1)
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


def score_business_opportunity(profile_key, profile_data, user_profile, global_trend, user_trend, local_competitor_count=None):
    business_name = str(profile_data.get("name") or profile_key).strip()
    business_name_key = business_name.lower()

    market_scan_count = int(global_trend.get("scan_count") or 0)
    market_avg_score = float(global_trend.get("avg_score") or 0.0)
    user_scan_count = int(user_trend.get("scan_count") or 0)
    user_avg_score = float(user_trend.get("avg_score") or 0.0)

    # Proxy demand potential using existing business need model.
    demand_points = min(22, int((profile_data.get("need", 5) / 10) * 22))

    # Proxy competition using locally cached OSM + custom MSME competitors.
    local_competitors = local_competitor_count
    if local_competitors is None:
        local_competitors = len(get_cached_pbf_competitors(profile_data.get("val"))) + len(fetch_custom_msmes(profile_key))
    market_gap_points = max(0, 22 - min(22, local_competitors * 2))

    trend_points = min(18, int((market_avg_score / 100) * 18))
    momentum_points = min(10, market_scan_count * 2)
    user_experience_points = min(12, int((user_avg_score / 100) * 12)) if user_scan_count > 0 else 0

    requirement = TREND_BUSINESS_REQUIREMENTS.get(profile_key, {})
    capital_min = int(requirement.get("capital_min") or 0)
    capital_max = int(requirement.get("capital_max") or 0)
    business_risk = str(requirement.get("risk") or "medium").strip().lower()
    business_setup = str(requirement.get("setup") or "storefront").strip().lower()
    target_payback = int(requirement.get("payback_months") or 0)

    startup_capital = user_profile.get("startup_capital")
    risk_tolerance = str(user_profile.get("risk_tolerance") or "").strip().lower()
    preferred_setup = str(user_profile.get("preferred_setup") or "").strip().lower()
    target_payback_months = user_profile.get("target_payback_months")

    capital_fit_points = 6
    if isinstance(startup_capital, int):
        if capital_min <= startup_capital <= max(capital_max, capital_min):
            capital_fit_points = 14
        elif startup_capital >= capital_min:
            capital_fit_points = 10
        else:
            capital_fit_points = 2

    risk_rank = {"low": 1, "medium": 2, "high": 3}
    risk_fit_points = 5
    if risk_tolerance in risk_rank:
        if risk_rank[risk_tolerance] >= risk_rank.get(business_risk, 2):
            risk_fit_points = 10
        else:
            risk_fit_points = 3

    setup_fit_points = 4
    if preferred_setup:
        setup_fit_points = 9 if preferred_setup == business_setup else 3

    payback_fit_points = 3
    if isinstance(target_payback_months, int) and target_payback_months > 0 and target_payback > 0:
        payback_fit_points = 9 if target_payback <= target_payback_months else 2

    primary_interest = str(user_profile.get("primary_business") or "").strip().lower()
    interest_hit = bool(
        primary_interest
        and (
            profile_key in primary_interest
            or business_name_key in primary_interest
            or any(token in primary_interest for token in ["food"] if profile_key in {"kiosk", "bakery", "coffee", "meat"})
        )
    )
    interest_points = 16 if interest_hit else 4

    total_score = min(
        100,
        demand_points
        + market_gap_points
        + trend_points
        + momentum_points
        + user_experience_points
        + interest_points
        + capital_fit_points
        + risk_fit_points
        + setup_fit_points
        + payback_fit_points
    )

    reasons = [
        f"Demand potential is {'high' if demand_points >= 15 else 'moderate'} based on local infrastructure fit.",
        (
            "Direct competition is currently low in local Panabo map data."
            if market_gap_points >= 14
            else "Competition exists, but opportunities remain with differentiation."
        ),
        (
            f"Recent market scans show strong viability trends (avg {market_avg_score:.1f}/100)."
            if market_scan_count > 0
            else "Limited recent scan history, so recommendation relies more on baseline demand and saturation."
        ),
    ]

    if capital_min > 0 and capital_max > 0:
        reasons.append(f"Typical startup capital range is around PHP {capital_min:,} to PHP {capital_max:,}.")
    if isinstance(startup_capital, int):
        if capital_fit_points >= 12:
            reasons.append("Your declared startup capital fits this business range.")
        elif capital_fit_points <= 3:
            reasons.append("Your current startup capital may be below the usual requirement for this category.")

    if risk_tolerance:
        reasons.append(f"Risk alignment: your profile is {risk_tolerance} tolerance vs {business_risk} category risk.")

    if preferred_setup:
        reasons.append(
            "Preferred setup matches this model."
            if setup_fit_points >= 8
            else f"This category is usually a {business_setup} setup, which differs from your preferred setup."
        )

    if isinstance(target_payback_months, int) and target_payback_months > 0 and target_payback > 0:
        reasons.append(
            f"Estimated payback around {target_payback} months; your target is {target_payback_months} months."
        )

    if interest_hit:
        reasons.append("Matches your declared primary business interest.")
    elif primary_interest:
        reasons.append("Expands beyond your current primary interest for diversification.")

    if user_scan_count > 0:
        reasons.append(f"You already evaluated this category {user_scan_count} time(s), which improves decision confidence.")

    return {
        "business_key": profile_key,
        "business_name": business_name,
        "opportunity_score": int(total_score),
        "market_scan_count": market_scan_count,
        "market_average_viability": round(market_avg_score, 1),
        "user_scan_count": user_scan_count,
        "local_competitor_estimate": int(local_competitors),
        "reasons": reasons,
        "scoring": {
            "demand_points": demand_points,
            "market_gap_points": market_gap_points,
            "trend_points": trend_points,
            "momentum_points": momentum_points,
            "user_experience_points": user_experience_points,
            "interest_points": interest_points,
            "capital_fit_points": capital_fit_points,
            "risk_fit_points": risk_fit_points,
            "setup_fit_points": setup_fit_points,
            "payback_fit_points": payback_fit_points,
        },
        "profile_match": {
            "capital_range": {"min": capital_min, "max": capital_max},
            "business_risk": business_risk,
            "business_setup": business_setup,
            "estimated_payback_months": target_payback,
        },
    }


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


def build_trend_upside_downside(recommendation, pre_scanned_report):
    scoring = recommendation.get("scoring") or {}
    upsides = []
    downsides = []

    if recommendation.get("opportunity_score", 0) >= 75:
        upsides.append("Strong overall opportunity score based on local demand, saturation, and profile fit.")

    if recommendation.get("local_competitor_estimate", 0) <= 2:
        upsides.append("Low local competitor pressure leaves room to capture unmet demand.")
    else:
        downsides.append("Local competition is already present, so differentiation is required.")

    if scoring.get("capital_fit_points", 0) >= 10:
        upsides.append("Startup capital fit is favorable for this category.")
    elif scoring.get("capital_fit_points", 0) <= 3:
        downsides.append("Your startup capital may be below the typical range for this business type.")

    if scoring.get("risk_fit_points", 0) >= 8:
        upsides.append("Risk profile aligns with the operating risk of this business.")
    elif scoring.get("risk_fit_points", 0) <= 3:
        downsides.append("Risk mismatch detected between your profile and this business category.")

    if pre_scanned_report:
        pre_scan_score = int(pre_scanned_report.get("viability_score") or 0)
        if pre_scan_score >= 70:
            upsides.append("The pre-scanned Panabo location shows strong viability for this business.")
        elif pre_scan_score <= 45:
            downsides.append("The pre-scanned Panabo location has mixed or weak viability indicators.")

        breakdown = pre_scanned_report.get("breakdown") or {}
        hazard_score = int((breakdown.get("hazard") or {}).get("score") or 0)
        if hazard_score <= 12:
            downsides.append("Flood hazard exposure may increase operating and mitigation costs in the selected area.")

        if pre_scanned_report.get("space_context"):
            upsides.append("A nearby active For Rent/For Sale listing matches the pre-scanned location.")

    if not upsides:
        upsides.append("Baseline demand and location-fit indicators are present, but require validation through full report review.")
    if not downsides:
        downsides.append("No major downside triggered in scoring, but permit checks and site validation are still required.")

    return upsides[:4], downsides[:4]


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