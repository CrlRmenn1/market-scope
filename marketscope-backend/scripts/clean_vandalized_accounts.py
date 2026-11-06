"""Clear vandalized names and photos from user accounts.

Changes nothing unless you pass --apply. Run it from the marketscope-backend folder,
with DATABASE_URL set to the database you mean to clean:

    python scripts/clean_vandalized_accounts.py --name-contains scubacat
    python scripts/clean_vandalized_accounts.py --name-contains scubacat --apply

An account counts as affected if its photo is one that --min-shared or more accounts
share, or if its name contains any --name-contains text. Affected accounts lose that
photo, and their name becomes a placeholder that Profile asks the owner to replace.
Those accounts are also logged out. Everything happens in one transaction, so a
failure leaves the database untouched.

Check the dry run first. It prints user ids and counts only, so it's safe to paste.
"""
import argparse
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import psycopg2
from psycopg2.extras import RealDictCursor

from core.database import DB_CONFIG
from db.schema import get_users_primary_key_column

# Keep in sync with PLACEHOLDER_NAME in marketscope-frontend/src/pages/Profile.jsx.
PLACEHOLDER_NAME = "MarketScope User"


def find_affected(cursor, pk, min_shared, name_terms):
    """Returns {user_id: [reasons]} and the shared photos, each as (digest, length, count)."""
    cursor.execute(
        """
        SELECT avatar_url, COUNT(*) AS total
        FROM users
        WHERE avatar_url IS NOT NULL AND avatar_url <> ''
        GROUP BY avatar_url
        HAVING COUNT(*) >= %s
        ORDER BY total DESC
        """,
        (min_shared,),
    )
    shared = cursor.fetchall()
    shared_summary = [
        (hashlib.sha256(row["avatar_url"].encode("utf-8")).hexdigest()[:12], len(row["avatar_url"]), row["total"])
        for row in shared
    ]

    affected = {}
    for row in shared:
        cursor.execute(f"SELECT {pk} AS user_id FROM users WHERE avatar_url = %s", (row["avatar_url"],))
        for user in cursor.fetchall():
            affected.setdefault(user["user_id"], []).append("shared photo")

    for term in name_terms:
        cursor.execute(
            f"SELECT {pk} AS user_id FROM users WHERE full_name ILIKE %s OR first_name ILIKE %s OR last_name ILIKE %s",
            (f"%{term}%", f"%{term}%", f"%{term}%"),
        )
        for user in cursor.fetchall():
            affected.setdefault(user["user_id"], []).append(f"name contains {term!r}")

    return affected, shared_summary


def clean(cursor, pk, user_ids, name_terms):
    """Clears the photo of every affected account, and the name where the name was hit."""
    cursor.execute(
        f"""
        UPDATE users
        SET avatar_url = NULL,
            full_name = CASE WHEN full_name ILIKE ANY(%s) OR first_name ILIKE ANY(%s) OR last_name ILIKE ANY(%s)
                             THEN %s ELSE full_name END,
            first_name = CASE WHEN full_name ILIKE ANY(%s) OR first_name ILIKE ANY(%s) OR last_name ILIKE ANY(%s)
                              THEN NULL ELSE first_name END,
            last_name = CASE WHEN full_name ILIKE ANY(%s) OR first_name ILIKE ANY(%s) OR last_name ILIKE ANY(%s)
                             THEN NULL ELSE last_name END
        WHERE {pk} = ANY(%s)
        """,
        (*([[f"%{term}%" for term in name_terms]] * 3), PLACEHOLDER_NAME,
         *([[f"%{term}%" for term in name_terms]] * 6), user_ids),
    )
    updated = cursor.rowcount
    cursor.execute("DELETE FROM user_sessions WHERE user_id = ANY(%s)", (user_ids,))
    return updated


def main(argv=None):
    parser = argparse.ArgumentParser(description="Clear vandalized names and photos. Dry run unless --apply is given.")
    parser.add_argument("--name-contains", action="append", default=[], metavar="TEXT", help="Affected if the name contains TEXT. Repeatable.")
    parser.add_argument("--min-shared", type=int, default=3, help="Affected if this many accounts share the same photo (default 3).")
    parser.add_argument("--apply", action="store_true", help="Actually make the changes.")
    args = parser.parse_args(argv)

    conn = psycopg2.connect(**DB_CONFIG)
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        pk = get_users_primary_key_column(cursor)

        cursor.execute("SELECT COUNT(*) AS total FROM users")
        total = cursor.fetchone()["total"]
        affected, shared = find_affected(cursor, pk, args.min_shared, args.name_contains)

        print(f"Database host: {DB_CONFIG['host']}")
        print(f"Accounts: {total}, affected: {len(affected)}")
        for digest, length, count in shared:
            print(f"  Photo {digest} ({length} characters) is shared by {count} accounts")
        print(f"Affected user ids: {sorted(affected)}")

        # Names many accounts share are likely the vandal's. Use them with --name-contains.
        cursor.execute(
            "SELECT full_name, COUNT(*) AS total FROM users GROUP BY full_name HAVING COUNT(*) >= %s ORDER BY total DESC",
            (args.min_shared,),
        )
        for row in cursor.fetchall():
            print(f"  Name {row['full_name']!r} is shared by {row['total']} accounts")

        # An attacker with admin or database access could have added themselves here.
        cursor.execute("SELECT email, created_at FROM admin_users ORDER BY created_at")
        print("Admin accounts. Remove any you don't recognize:")
        for admin in cursor.fetchall():
            print(f"  {admin['email']} (created {admin['created_at']})")

        if not args.apply:
            print("\nDry run: nothing was changed. Add --apply to clean these accounts.")
            return 0
        if not affected:
            print("\nNothing to clean.")
            return 0

        updated = clean(cursor, pk, sorted(affected), args.name_contains)
        conn.commit()
        print(f"\nCleaned {updated} accounts and logged them out.")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
