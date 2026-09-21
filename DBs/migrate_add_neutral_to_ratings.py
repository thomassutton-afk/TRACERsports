"""One-time migration: add `ratings.neutral`, which was missing from
db.py's schema (see db.py/rebuild.py diffs alongside this file).

Just adds the column with a safe default - it does NOT backfill correct
per-game values. Run add_season.py (or rebuild.py) once afterward with
the patched db.py/rebuild.py in place; that does a full
`rebuild_ratings()` pass per variant, which deletes and rewrites every
`ratings` row from `games` (which already has the correct `neutral`
values), so the real backfill happens naturally on the next normal run.

Usage:
    python3 migrate_add_neutral_to_ratings.py nba_elo.db wnba_elo.db
"""
import sqlite3
import sys


def migrate(path: str) -> None:
    conn = sqlite3.connect(path)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(ratings)")]
    if "neutral" in cols:
        print(f"{path}: ratings.neutral already present, skipping.")
    else:
        conn.execute("ALTER TABLE ratings ADD COLUMN neutral INTEGER NOT NULL DEFAULT 0")
        conn.commit()
        print(f"{path}: added ratings.neutral (defaulted to 0 - rerun add_season.py to backfill real values).")
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 migrate_add_neutral_to_ratings.py db1.db [db2.db ...]")
        sys.exit(1)
    for p in sys.argv[1:]:
        migrate(p)
