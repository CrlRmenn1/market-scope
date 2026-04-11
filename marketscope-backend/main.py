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
# DATABASE CONFIGURATION
# ==========================================
DB_CONFIG = {
    "dbname": "marketscope_db",
    "user": "postgres", 
    "password": "1234", # <-- PUT YOUR PASSWORD HERE
    "host": "localhost",
    "port": "5432"
}

app = FastAPI()

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

class LoginUser(BaseModel):
    email: str
    password: str

class AnalysisRequest(BaseModel):
    lat: float
    lon: float
    business_type: str
    radius: int = 340 

# ==========================================
# AUTHENTICATION ROUTES
# ==========================================
@app.post("/register")
def register(user: RegisterUser):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # Check if email already exists
        cursor.execute("SELECT id FROM users WHERE email = %s", (user.email,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Email already registered")

        # Hash the password
        salt = bcrypt.gensalt()
        hashed_password = bcrypt.hashpw(user.password.encode('utf-8'), salt).decode('utf-8')

        # Save to database
        cursor.execute(
            "INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s) RETURNING id, full_name",
            (user.full_name, user.email, hashed_password)
        )
        new_user = cursor.fetchone()
        conn.commit()
        cursor.close()
        conn.close()

        return {"status": "success", "user": {"id": new_user[0], "name": new_user[1], "email": user.email}}
    except Exception as e:
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/login")
def login(user: LoginUser):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        cursor.execute("SELECT id, full_name, email, password_hash FROM users WHERE email = %s", (user.email,))
        db_user = cursor.fetchone()
        cursor.close()
        conn.close()

        # Verify password
        if not db_user or not bcrypt.checkpw(user.password.encode('utf-8'), db_user['password_hash'].encode('utf-8')):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        return {"status": "success", "user": {"id": db_user['id'], "name": db_user['full_name'], "email": db_user['email']}}
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

    # FINAL PAYLOAD
    return {
        "viability_score": int(total_score),
        "business_type": sme_profile["name"], 
        "competitors_found": competitors_found,
        "competitor_locations": competitors_list, 
        "target_coords": {"lat": data.lat, "lng": data.lon}, 
        "radius_meters": data.radius,
        "insight": generated_insight, 
        "breakdown": {
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
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)