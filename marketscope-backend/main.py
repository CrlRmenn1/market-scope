from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import geopandas as gpd
import math
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import bcrypt

# ==========================================
# 1. CORE APP & DB CONFIGURATION
# ==========================================
app = FastAPI()

# Database environment variable for Render
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    try:
        if DATABASE_URL:
            # Production: Uses your Render Cloud Database URL
            return psycopg2.connect(DATABASE_URL)
        else:
            # Local: Uses your laptop's settings
            return psycopg2.connect(
                dbname="marketscope_db",
                user="postgres", 
                password="1234", # Change this to your local password if testing offline
                host="localhost",
                port="5432"
            )
    except Exception as e:
        print(f"Database Connection Error: {e}")
        raise e

# BULLETPROOF CORS: Allows your Vercel site to communicate with this server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allowing all origins for Alpha Testing to avoid blocked requests
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 2. DATA MODELS (PYDANTIC)
# ==========================================
class RegisterUser(BaseModel):
    full_name: str
    email: str
    password: str

class LoginUser(BaseModel):
    email: str
    password: str

class AnalysisRequest(BaseModel):
    lat: float
    lon: float
    business_type: str
    radius: int = 340 

# ==========================================
# 3. AUTHENTICATION ROUTES
# ==========================================
@app.post("/register")
def register(user: RegisterUser):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if email exists
        cursor.execute("SELECT id FROM users WHERE email = %s", (user.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")

        # Hash password
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), salt).decode('utf-8')

        # Save user
        cursor.execute(
            "INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s) RETURNING id, full_name",
            (user.full_name, user.email, hashed_password)
        )
        new_user = cursor.fetchone()
        conn.commit()
        cursor.close()

        return {"status": "success", "user": {"id": new_user[0], "name": new_user[1], "email": user.email}}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn: conn.close()

@app.post("/login")
def login(user: LoginUser):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT id, full_name, email, password_hash FROM users WHERE email = %s", (user.email,))
        db_user = cursor.fetchone()
        cursor.close()

        # Verify password
        if not db_user or not bcrypt.checkpw(user.password.encode('utf-8'), db_user['password_hash'].encode('utf-8')):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        return {"status": "success", "user": {"id": db_user['id'], "name": db_user['full_name'], "email": db_user['email']}}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn: conn.close()

# ==========================================
# 4. GEOSPATIAL ANALYSIS ENGINE
# ==========================================
PBF_PATH = "panabo.pbf"

ZONING_LAYERS = {
    "commercial_proper": (7.3000, 7.3150, 125.6700, 125.6900),
    "industrial_anflo": (7.2800, 7.2950, 125.6500, 125.6700)
}

HAZARD_LAYERS = {
    "heavy_flood": (7.3080, 7.3120, 125.6750, 125.6800),
    "moderate_flood": (7.3050, 7.3140, 125.6720, 125.6850)
}

PANABO_ANCHORS = [
    {"name": "Integrated Bus/Jeepney Terminal", "lat": 7.298318, "lon": 125.680099, "power": 25},
    {"name": "Panabo District Hospital", "lat": 7.298534, "lon": 125.681971, "power": 5},
    {"name": "LandBank Panabo", "lat": 7.302614, "lon": 125.681888, "power": 15},
    {"name": "Panabo Public Market", "lat": 7.306480, "lon": 125.683457, "power": 15},
    {"name": "Davao del Norte State College", "lat": 7.313671, "lon": 125.670372, "power": 20},
    {"name": "Central Market", "lat": 7.300987, "lon": 125.682584, "power": 25},
    {"name": "University of Mindanao Panabo", "lat": 7.304490, "lon": 125.679607, "power": 25}
]

SME_DATABASE = {
    "coffee": {"key": "amenity", "val": "cafe", "fear": 6, "need": 9, "name": "Coffee Shops"},
    "print": {"key": "shop", "val": "copyshop", "fear": 7, "need": 6, "name": "Print Centers"},
    "laundry": {"key": "shop", "val": "laundry", "fear": 9, "need": 7, "name": "Laundry Shops"},
    "carwash": {"key": "amenity", "val": "car_wash", "fear": 8, "need": 9, "name": "Car Washes"},
    "bakery": {"key": "shop", "val": "bakery", "fear": 8, "need": 9, "name": "Bakeries"},
    "pharmacy": {"key": "amenity", "val": "pharmacy", "fear": 7, "need": 9, "name": "Pharmacies"},
    "barber": {"key": "shop", "val": "hairdresser", "fear": 7, "need": 9, "name": "Barbershops"},
    "meat": {"key": "shop", "val": "butcher", "fear": 9, "need": 9, "name": "Meat Shops"}
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

@app.post("/analyze")
def perform_analysis(data: AnalysisRequest):
    sme_profile = SME_DATABASE.get(data.business_type, {"val": "shop", "fear": 5, "need": 5, "name": "MSME"})
    
    # 1. ZONING
    zoning_score = 10
    zoning_status = "Outside Commercial Zone"
    if check_inside_bounds(data.lat, data.lon, ZONING_LAYERS["commercial_proper"]):
        zoning_score = 25
        zoning_status = "Compliant (Commercial Center)"

    # 2. HAZARD
    hazard_score = 25
    hazard_status = "Low Risk / Safe"
    if check_inside_bounds(data.lat, data.lon, HAZARD_LAYERS["heavy_flood"]):
        hazard_score = 0
        hazard_status = "High Risk (Flood Zone)"

    # 3. COMPETITION SCAN (PBF + Custom DB)
    competitors_found = 0
    # Add your PBF scanning logic here if panabo.pbf is present on Render

    # 4. DEMAND SCORE
    raw_demand_power = 0
    for anchor in PANABO_ANCHORS:
        if calculate_distance(data.lat, data.lon, anchor["lat"], anchor["lon"]) <= data.radius:
            raw_demand_power += anchor["power"]
    
    demand_score = min(25, int((raw_demand_power / (sme_profile['need'] * 8)) * 25))
    total_score = zoning_score + hazard_score + demand_score + 25 # +25 for placeholder saturation

    return {
        "viability_score": int(total_score),
        "business_type": sme_profile["name"], 
        "insight": f"Analysis complete for {sme_profile['name']} in Panabo.",
        "breakdown": {
            "zoning": {"score": zoning_score, "status": zoning_status},
            "hazard": {"score": hazard_score, "status": hazard_status},
            "demand": {"score": demand_score, "status": "Calculated Foot Traffic"}
        }
    }

# START COMMAND
if __name__ == "__main__":
    import uvicorn
    # Use the PORT environment variable provided by Render
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)