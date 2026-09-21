"""One-time migration: add the two columns that were missing from
db.py's schema (see db.py/rebuild.py/add_season.py diffs alongside
this file) - `ratings.neutral` and `schedule_predictions.predicted_spread`.

Just adds the columns with safe defaults - it does NOT backfill correct
per-game `neutral` values, and leaves `predicted_spread` NULL until the
next real run. Run add_season.py once afterward with the patched
files in place: rebuild_ratings() deletes and rewrites every `ratings`
row from `games` (which already has correct `neutral` values), and
write_schedule_predictions() rewrites every `schedule_predictions` row
including the new `predicted_spread` - so the real backfill happens
naturally on the next normal run.

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

    sp_cols = [r[1] for r in conn.execute("PRAGMA table_info(schedule_predictions)")]
    if "predicted_spread" in sp_cols:
        print(f"{path}: schedule_predictions.predicted_spread already present, skipping.")
    else:
        conn.execute("ALTER TABLE schedule_predictions ADD COLUMN predicted_spread REAL")
        conn.commit()
        print(f"{path}: added schedule_predictions.predicted_spread (NULL until rerun).")
    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 migrate_add_neutral_to_ratings.py db1.db [db2.db ...]")
        sys.exit(1)
    for p in sys.argv[1:]:
        migrate(p)
