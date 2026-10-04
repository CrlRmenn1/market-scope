#!/usr/bin/env python3
"""Debug script to check database configuration on Render"""
import os
import sys

print("=" * 60)
print("DATABASE CONFIGURATION CHECK")
print("=" * 60)

# Check if DATABASE_URL is set
db_url = os.environ.get("DATABASE_URL")
print(f"\n[1] DATABASE_URL env var: {'SET' if db_url else 'NOT SET'}")
if db_url:
    print(f"    Value (truncated): {db_url[:80]}...")
else:
    print("    ⚠️  WARNING: DATABASE_URL is not set!")
    print("    This will cause the app to use localhost defaults")

# Check individual fallback vars
print(f"\n[2] Fallback environment variables:")
print(f"    MARKETSCOPE_DB_HOST: {os.environ.get('MARKETSCOPE_DB_HOST', 'NOT SET')}")
print(f"    MARKETSCOPE_DB_USER: {os.environ.get('MARKETSCOPE_DB_USER', 'NOT SET')}")
print(f"    MARKETSCOPE_DB_PORT: {os.environ.get('MARKETSCOPE_DB_PORT', 'NOT SET')}")
print(f"    MARKETSCOPE_DB_NAME: {os.environ.get('MARKETSCOPE_DB_NAME', 'NOT SET')}")

# Import and show parsed config
try:
    from settings import get_database_config
    config = get_database_config()
    print(f"\n[3] Parsed database config:")
    for key, val in config.items():
        if key == "password":
            print(f"    {key}: {'*' * len(val) if val else '(empty)'}")
        else:
            print(f"    {key}: {val}")
except Exception as e:
    print(f"\n[3] ERROR loading config: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
