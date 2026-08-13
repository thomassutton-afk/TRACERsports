"""
check_playoff_coverage.py — checks which WNBA (and NBA, for comparison)
seasons actually have playoff game rows (type='P') in Supabase.

This is a genuine data-gap check, separate from the champion win-threshold
fix from last session. If a season shows 0 playoff games here, no amount
of frontend logic can show a playoff result for it — the rows just aren't
in the games table for that season/league/variant.

Run from DBs\\, same place export_to_supabase.py runs from, so it picks up
the same .env / SUPABASE_DB_* env vars.

    cd C:\\Users\\tjsut\\tracersports-app\\DBs
    python check_playoff_coverage.py
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

for league in ("wnba", "nba"):
    print(f"\n=== {league.upper()} — regular-season vs playoff game rows per season (echo) ===")
    cur.execute(
        """
        SELECT season,
               COUNT(*) FILTER (WHERE type = 'R') AS rs_rows,
               COUNT(*) FILTER (WHERE type = 'P') AS po_rows
        FROM games
        WHERE league = %s AND variant = 'echo'
        GROUP BY season
        ORDER BY season
        """,
        (league,),
    )
    rows = cur.fetchall()

    if not rows:
        print("  No rows found at all for this league.")
        continue

    missing = [season for season, rs, po in rows if rs > 0 and po == 0]

    for season, rs, po in rows:
        flag = "  <-- NO PLAYOFF ROWS" if (rs > 0 and po == 0) else ""
        print(f"  {season}: {rs:>4} regular-season rows, {po:>4} playoff rows{flag}")

    if missing:
        print(f"\n  {league.upper()} seasons with regular-season data but ZERO playoff rows: {missing}")
    else:
        print(f"\n  Every {league.upper()} season with regular-season data also has playoff rows.")

cur.close()
conn.close()
