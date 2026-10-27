"""
rebuild_ratings_only.py

Rebuilds ratings for both variants (echo, pulse) WITHOUT touching
`games`/`schedule` at all - no re-normalizing, no reloading, no
dedup pass. Use this whenever something that affects the RATING MATH
itself changes (a param_schedule.json update, an engine.py/db.py fix
like the fcs_rating merge-key bug) but the underlying game data hasn't
changed - reingest_phase2.py does far more work than that (re-runs
normalize_sr_games.py against every raw file, deletes and reloads
every season) and is the wrong tool when only the math changed, not
the data.

Usage:
    python3 rebuild_ratings_only.py cfb_elo.db
"""
import os
import sys

import db
import rebuild
from rebuild import VARIANTS


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "cfb_elo.db")
    conn = db.connect(db_path)

    total_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    print(f"{total_games} games in {db_path} (unchanged by this script).\n")

    print("Rebuilding ratings for all variants...")
    for variant in VARIANTS:
        rebuild.rebuild_ratings(conn, variant)
        print(f"  {variant}: done")

    seasons = sorted(
        row[0] for row in conn.execute("SELECT DISTINCT season FROM games").fetchall()
    )
    warnings = rebuild.sanity_checks(conn, seasons, "echo")
    print(f"\nSanity check warnings: {len(warnings)}")
    for w in warnings:
        print(" ", w)

    print("\nDone.")


if __name__ == "__main__":
    main()
