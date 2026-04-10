import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "dbname": "marketscope_db",
    "user": "postgres", 
    "password": "1234", # <-- Change this
    "host": "localhost",
    "port": "5432"
}

print("1. Attempting to connect to PostgreSQL...")

try:
    conn = psycopg2.connect(**DB_CONFIG)
    print("2. Connection Successful! Querying for 'pharmacy'...")
    
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    # We are forcing the search for 'pharmacy' just to see if Rose Pharmacy exists
    cursor.execute("SELECT name, latitude, longitude FROM custom_msme WHERE business_type = 'pharmacy'")
    results = cursor.fetchall()
    
    print("\n--- RESULTS ---")
    if len(results) == 0:
        print("FAIL: The query worked, but 0 shops were found. (Check if the table is empty or if business_type doesn't match exactly).")
    else:
        print(f"SUCCESS: Found {len(results)} shop(s)!")
        for shop in results:
            print(f"- {shop['name']} at [Lat: {shop['latitude']}, Lon: {shop['longitude']}]")
            
    cursor.close()
    conn.close()

except Exception as e:
    print(f"\nCRITICAL DATABASE ERROR: {e}")