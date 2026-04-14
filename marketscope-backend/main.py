from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import geopandas as gpd
import math
import os
import socket
from datetime import date
from contextlib import asynccontextmanager
from urllib.parse import parse_qs, urlparse
import psycopg2
from psycopg2.extras import RealDictCursor, Json
import bcrypt

# ==========================================
# DATABASE CONFIGURATION
# ==========================================
def build_db_config():
    database_url = (
        os.environ.get("DATABASE_URL")
        or os.environ.get("DATABASE_INTERNAL_URL")
        or os.environ.get("DATABASE_EXTERNAL_URL")
        or os.environ.get("INTERNAL_DATABASE_URL")
        or os.environ.get("EXTERNAL_DATABASE_URL")
    )
    if database_url:
        parsed_url = urlparse(database_url)
        query_params = parse_qs(parsed_url.query)
        config = {
            "dbname": parsed_url.path.lstrip("/"),
            "user": parsed_url.username,
            "password": parsed_url.password,
            "host": parsed_url.hostname,
            "port": parsed_url.port or 5432,
        }
        config["sslmode"] = (
            os.environ.get("DB_SSLMODE")
            or query_params.get("sslmode", [None])[0]
            or "require"
        )
        return config

    return {
        "dbname": os.environ.get("DB_NAME", "marketscope_db"),
        "user": os.environ.get("DB_USER", "postgres"),
        "password": os.environ.get("DB_PASSWORD", "1234"),
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": os.environ.get("DB_PORT", "5432"),
    }


DB_CONFIG = build_db_config()

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_app_tables()
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class LoginUser(BaseModel):
    email: str
    password: str


class UpdateUserProfile(BaseModel):
    full_name: str
    email: str
    address: str | None = None
    cellphone_number: str | None = None
    avatar_url: str | None = None
    age: int | None = None
    birthday: date | None = None
    primary_business: str | None = None

class AnalysisRequest(BaseModel):
    lat: float
    lon: float
    business_type: str
    radius: int = 340 
    user_id: int | None = None


def create_app_tables():
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
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

    conn.commit()
    cursor.close()
    conn.close()


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

    breakdown = row.get("breakdown")
    if not isinstance(breakdown, dict) or not breakdown:
        row["breakdown"] = build_legacy_breakdown(row)

    return row


# ==========================================
# AUTHENTICATION ROUTES
# ==========================================
@app.post("/register")
def register(user: RegisterUser):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        user_pk_column = get_users_primary_key_column(cursor)
        ensure_users_profile_columns(cursor)
        
        # Check if email already exists
        cursor.execute(f"SELECT {user_pk_column} FROM users WHERE email = %s", (user.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")

        # Hash the password
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), salt).decode('utf-8')

        # Save to database
        cursor.execute(
            f"""
            INSERT INTO users (
                full_name, email, password_hash,
                address, cellphone_number, avatar_url,
                age, birthday, primary_business
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING
                {user_pk_column}, full_name, email, created_at,
                address, cellphone_number, avatar_url,
                age, birthday, primary_business
            """,
            (
                user.full_name,
                user.email,
                hashed_password,
                user.address or None,
                user.cellphone_number or None,
                user.avatar_url or None,
                user.age,
                user.birthday,
                user.primary_business or None
            )
        )
        new_user = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

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
                "primary_business": new_user[9]
            }
        }
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/login")
def login(user: LoginUser):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        user_pk_column = get_users_primary_key_column(cursor)
        ensure_users_profile_columns(cursor)
        
        cursor.execute(
            f"""
            SELECT
                {user_pk_column} AS user_id,
                full_name, email, password_hash, created_at,
                address, cellphone_number, avatar_url,
                age, birthday, primary_business
            FROM users
            WHERE email = %s
            """,
            (user.email,)
        )
        db_user = cursor.fetchone()
        cursor.close()
        conn.close()

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
                "primary_business": db_user.get('primary_business')
            }
        }
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}")
def get_user_profile(user_id: int):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        user_pk_column = get_users_primary_key_column(cursor)
        ensure_users_profile_columns(cursor)
        cursor.execute(
            f"""
            SELECT
                {user_pk_column} AS user_id,
                full_name, email, created_at,
                address, cellphone_number, avatar_url,
                age, birthday, primary_business
            FROM users
            WHERE {user_pk_column} = %s
            """,
            (user_id,)
        )
        profile = cursor.fetchone()
        cursor.close()
        conn.close()

        if not profile:
            raise HTTPException(status_code=404, detail="User not found")

        return {"status": "success", "user": profile}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/users/{user_id}")
def update_user_profile(user_id: int, payload: UpdateUserProfile):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        user_pk_column = get_users_primary_key_column(cursor)
        ensure_users_profile_columns(cursor)

        cursor.execute(
            f"SELECT {user_pk_column} AS user_id FROM users WHERE {user_pk_column} = %s",
            (user_id,)
        )
        existing_user = cursor.fetchone()
        if not existing_user:
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
        duplicate_email = cursor.fetchone()
        if duplicate_email:
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
                primary_business = %s
            WHERE {user_pk_column} = %s
            RETURNING
                {user_pk_column} AS user_id,
                full_name, email, created_at,
                address, cellphone_number, avatar_url,
                age, birthday, primary_business
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
                user_id
            )
        )
        updated_user = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        return {"status": "success", "user": updated_user}
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}/history")
def get_user_history(user_id: int):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_history_table_columns(cursor)
        history_pk_column = get_analysis_history_pk_column(cursor)
        cursor.execute(
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
            WHERE user_id = %s
            ORDER BY scan_date DESC, {history_pk_column} DESC
            """,
            (user_id,)
        )
        history = cursor.fetchall()

        for row in history:
            normalize_history_row(row)

        cursor.close()
        conn.close()

        return {"status": "success", "history": history}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/users/{user_id}/history/{history_id}")
def get_user_history_item(user_id: int, history_id: int):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        ensure_history_table_columns(cursor)
        history_pk_column = get_analysis_history_pk_column(cursor)

        cursor.execute(
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
            WHERE user_id = %s AND {history_pk_column} = %s
            LIMIT 1
            """,
            (user_id, history_id)
        )

        history_item = cursor.fetchone()
        cursor.close()
        conn.close()

        if not history_item:
            raise HTTPException(status_code=404, detail="History item not found")

        normalize_history_row(history_item)
        return {"status": "success", "history": history_item}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/users/{user_id}/history/{history_id}")
def delete_user_history_item(user_id: int, history_id: int):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        history_pk_column = get_analysis_history_pk_column(cursor)
        cursor.execute(
            f"DELETE FROM analysis_history WHERE user_id = %s AND {history_pk_column} = %s RETURNING {history_pk_column}",
            (user_id, history_id)
        )
        deleted_row = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        if not deleted_row:
            return {"status": "success", "deleted_history_id": history_id, "already_missing": True}

        return {"status": "success", "deleted_history_id": deleted_row[0]}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# GEOSPATIAL ANALYSIS ROUTE
# ==========================================
PBF_PATH = "panabo.pbf"

ZONING_LAYERS = {
    "commercial_proper": (7.3000, 7.3150, 125.6700, 125.6900),
    "industrial_anflo": (7.2800, 7.2950, 125.6500, 125.6700)
}

# Temporary hazard proxy zones based on the attached Panabo DENR/MGB susceptibility map
# These are used until official GIS hazard polygons are available.
HAZARD_ZONES = {
    "flood": [
        {
            "name": "Very High Flood Susceptibility",
            "bounds": (7.3080, 7.3120, 125.6750, 125.6800),
            "score": 0
        },
        {
            "name": "High Flood Susceptibility",
            "bounds": (7.3050, 7.3140, 125.6720, 125.6850),
            "score": 10
        },
        {
            "name": "Moderate Flood Susceptibility",
            "bounds": (7.2990, 7.3150, 125.6700, 125.6860),
            "score": 18
        }
    ],
    "landslide": [
        {
            "name": "Very High Landslide Susceptibility",
            "bounds": (7.3050, 7.3130, 125.6670, 125.6750),
            "score": 0
        },
        {
            "name": "High Landslide Susceptibility",
            "bounds": (7.3030, 7.3150, 125.6680, 125.6800),
            "score": 10
        },
        {
            "name": "Moderate Landslide Susceptibility",
            "bounds": (7.3000, 7.3150, 125.6690, 125.6830),
            "score": 18
        }
    ]
}


def evaluate_hazard(lat, lon):
    hazard_score = 25
    hazard_status = "Low Risk / Safe"
    hazard_matches = []

    for hazard_type, zones in HAZARD_ZONES.items():
        for zone in zones:
            if check_inside_bounds(lat, lon, zone["bounds"]):
                hazard_matches.append(f"{zone['name']} ({hazard_type.title()})")
                if zone["score"] < hazard_score:
                    hazard_score = zone["score"]
                    hazard_status = f"{zone['name']} ({hazard_type.title()})"

    if hazard_matches and hazard_status not in hazard_matches:
        hazard_matches.insert(0, hazard_status)

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
    "coffee": {"key": "amenity", "val": "cafe", "fear": 6, "need": 9, "name": "Coffee Shops"},
    "print": {"key": "shop", "val": "copyshop", "fear": 7, "need": 6, "name": "Print/Copy Centers"},
    "laundry": {"key": "shop", "val": "laundry", "fear": 9, "need": 7, "name": "Laundry Shops"},
    "carwash": {"key": "amenity", "val": "car_wash", "fear": 8, "need": 9, "name": "Car Washes"},
    "kiosk": {"key": "amenity", "val": "fast_food", "fear": 6, "need": 9, "name": "Food Kiosks/Stalls"},
    "water": {"key": "shop", "val": "water", "fear": 4, "need": 7, "name": "Water Refilling Stations"},
    "bakery": {"key": "shop", "val": "bakery", "fear": 8, "need": 9, "name": "Bakeries"},
    "pharmacy": {"key": "amenity", "val": "pharmacy", "fear": 7, "need": 9, "name": "Small Pharmacies"},
    "barber": {"key": "shop", "val": "hairdresser", "fear": 7, "need": 9, "name": "Barbershops/Salons"},
    "moto": {"key": "shop", "val": "motorcycle_repair", "fear": 5, "need": 8, "name": "Motorcycle Repair Shops"},
    "internet": {"key": "amenity", "val": "internet_cafe", "fear": 6, "need": 6, "name": "Internet Cafes"},
    "meat": {"key": "shop", "val": "butcher", "fear": 9, "need": 9, "name": "Meat Shops"},
    "hardware": {"key": "shop", "val": "hardware", "fear": 7, "need": 8, "name": "Hardware/Construction Supplies"}
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

@app.post("/analyze")
def perform_analysis(data: AnalysisRequest):
    sme_profile = SME_DATABASE.get(data.business_type, {"key": "shop", "val": "convenience", "fear": 5, "need": 5, "name": "MSME"})
    search_val = sme_profile["val"]
    
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
    hazard_description = (
        "Temporary Panabo flood and landslide susceptibility mapping used as a proxy for hazard evaluation. "
        + ("Matched zones: " + ", ".join(hazard_matches) + "." if hazard_matches else "No mapped hazard zones matched.")
    )

    # FACTOR 3: LOCAL COMPETITOR SCAN (SATURATION) - Normalized to 0-25 scale
    competitors_list = []

    if os.path.exists(PBF_PATH):
        try:
            for layer in ["points", "multipolygons", "lines", "multilinestrings"]:
                try:
                    gdf = gpd.read_file(PBF_PATH, layer=layer, engine="pyogrio")
                except Exception:
                    continue

                for col in ["amenity", "shop", "healthcare", "building"]:
                    if col in gdf.columns:
                        matches = gdf[gdf[col] == search_val]
                        for _, row in matches.iterrows():
                            if row.geometry is None:
                                continue
                            p_lat = row.geometry.centroid.y
                            p_lon = row.geometry.centroid.x
                            dist = calculate_distance(data.lat, data.lon, p_lat, p_lon)

                            if dist <= data.radius:
                                competitors_list.append({
                                    "lat": p_lat,
                                    "lon": p_lon,
                                    "name": row.get('name', f"Local {sme_profile['name']}")
                                })
        except Exception as e:
            print(f"Spatial Scan Error: {e}")

    # Scan PostgreSQL Database
    custom_shops = fetch_custom_msmes(data.business_type)
    for shop in custom_shops:
        p_lat = shop['latitude']
        p_lon = shop['longitude']
        dist = calculate_distance(data.lat, data.lon, p_lat, p_lon)

        if dist <= data.radius:
            competitors_list.append({
                "lat": p_lat,
                "lon": p_lon,
                "name": shop['name']
            })

    competitors_found = len(competitors_list)

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
        f"The algorithm scanned Panabo PBF layers and local MSME records for matching businesses within {data.radius} meters. "
        + f"It counted competitors and then mapped that count to a 0-25 score: 0 competitors => 25, 1 competitor => 20, 2-3 => 15, 4-5 => 10, 6+ => 5."
    )

    zoning_details = (
        "The zoning score is derived by checking whether the target coordinates fall inside Panabo commercial or industrial polygon bounds. "
        + "If the site is inside the commercial polygon, it receives 25. If it is in the industrial support polygon and the business fits that category, it also receives 25; otherwise it is penalized."
    )

    hazard_details = (
        "The hazard score is based on temporary Panabo flood and landslide proxy zones. "
        + ("Matched zones: " + ", ".join(hazard_matches) + ". " if hazard_matches else "No mapped hazard zones matched. ")
        + "The lowest matched zone score is used as the factor result."
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
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            ensure_history_table_columns(cursor)
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
                    Json(competitors_list),
                    Json(breakdown_payload)
                )
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"History Save Error: {e}")

    # FINAL PAYLOAD
    return {
        "viability_score": int(total_score),
        "business_type": sme_profile["name"], 
        "competitors_found": competitors_found,
        "competitor_locations": competitors_list, 
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