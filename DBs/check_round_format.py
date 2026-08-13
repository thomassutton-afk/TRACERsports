"""
check_round_format.py — checks whether the one-time round-format backfill
(round like "1.0" -> "1") has been run against Supabase yet.

Run from DBs\\, same place export_to_supabase.py runs from, so it picks up
the same .env / SUPABASE_DB_* env vars.

    cd C:\\Users\\tjsut\\tracersports-app\\DBs
    python check_round_format.py
"""

import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg2

db_host = os.environ.get("SUPABASE_DB_HOST")
db_port = os.environ.get("SUPABASE_DB_PORT", "5432")
db_name = os.environ.get("SUPABASE_DB_NAME", "postgres")
db_user = os.environ.get("SUPABASE_DB_USER")
db_pass = os.environ.get("SUPABASE_DB_PASS")

if not all([db_host, db_user, db_pass]):
    print("Missing SUPABASE_DB_HOST / SUPABASE_DB_USER / SUPABASE_DB_PASS "
          "in environment or .env — same vars export_to_supabase.py needs.")
    sys.exit(1)

conn = psycopg2.connect(
    host=db_host, port=db_port, dbname=db_name,
    user=db_user, password=db_pass,
)
cur = conn.cursor()

print("Checking for old-format round values (e.g. '1.0', '4.0') ...\n")

for table in ("games", "schedule"):
    cur.execute(
        f"SELECT COUNT(*) FROM {table} WHERE round ~ '^[0-9]+\\.0$'"
    )
    bad_count = cur.fetchone()[0]

    if bad_count == 0:
        print(f"  {table}: clean — no old-format round values found.")
    else:
        cur.execute(
            f"SELECT DISTINCT round FROM {table} WHERE round ~ '^[0-9]+\\.0$' "
            f"ORDER BY round LIMIT 10"
        )
        samples = [r[0] for r in cur.fetchall()]
        print(f"  {table}: {bad_count} row(s) still in old format. "
              f"Examples: {samples}")

print("\nIf either table shows rows still in old format, the backfill SQL "
      "hasn't been run (or didn't cover everything). Safe to run again:\n")
print("  UPDATE games SET round = regexp_replace(round, '\\.0$', '') "
      "WHERE round ~ '^[0-9]+\\.0$';")
print("  UPDATE schedule SET round = regexp_replace(round, '\\.0$', '') "
      "WHERE round ~ '^[0-9]+\\.0$';")

cur.close()
conn.close()
