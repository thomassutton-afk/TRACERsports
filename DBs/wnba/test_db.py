"""
Regression test for the duplicate-game bug found while building
add_season.py: a plain SQL UNIQUE constraint treats every NULL as
distinct from every other NULL, so regular-season games (which store
round=NULL) were never deduplicated by re-running a loader on the same
file twice. Fixed by indexing on IFNULL(round, -1) instead.

Run with: python3 test_db.py
"""
import os
from datetime import date
import db

TEST_DB = "test_dedup.db"


def test_regular_season_games_dedupe_on_reinsert():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    conn = db.connect(TEST_DB)
    db.upsert_team(conn, "A", "Team A")
    db.upsert_team(conn, "B", "Team B")

    inserted_1 = db.add_game(conn, date(2000, 5, 29), 2000, "R", None, "A", "B", 80, 70, 0)
    inserted_2 = db.add_game(conn, date(2000, 5, 29), 2000, "R", None, "A", "B", 80, 70, 0)
    conn.commit()

    assert inserted_1 is True, "first insert of a regular-season game should succeed"
    assert inserted_2 is False, "re-inserting the same regular-season game should be ignored"

    count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    assert count == 1, f"expected exactly 1 game row after inserting the same game twice, got {count}"

    conn.close()
    os.remove(TEST_DB)


def test_playoff_games_still_dedupe_by_round():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    conn = db.connect(TEST_DB)
    db.upsert_team(conn, "A", "Team A")
    db.upsert_team(conn, "B", "Team B")

    # Same two teams, same date is unrealistic, but different playoff
    # rounds must NOT be treated as duplicates of each other.
    db.add_game(conn, date(2000, 8, 1), 2000, "P", 1, "A", "B", 80, 70, 0)
    db.add_game(conn, date(2000, 8, 1), 2000, "P", 2, "A", "B", 75, 74, 0)
    conn.commit()

    count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    assert count == 2, f"expected 2 distinct playoff rounds to both be kept, got {count}"

    conn.close()
    os.remove(TEST_DB)


def test_unplayed_games_never_enter_games_table():
    """The exact bug class this whole feature exists to prevent: an
    unplayed game must never be able to reach `games` (and therefore
    the rating engine) as a fake 0-0 result. It can only ever exist in
    `schedule`, which the engine never reads from."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    conn = db.connect(TEST_DB)
    db.upsert_team(conn, "A", "Team A")
    db.upsert_team(conn, "B", "Team B")

    db.add_scheduled_game(conn, date(2025, 6, 1), 2025, "R", None, "A", "B")
    conn.commit()

    games_count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    schedule_count = conn.execute("SELECT COUNT(*) FROM schedule").fetchone()[0]
    assert games_count == 0, "an unplayed game must never land in `games`"
    assert schedule_count == 1

    # Rebuilding ratings must not error or fabricate a result for it.
    from rebuild import rebuild_ratings
    rebuild_ratings(conn)
    ratings_count = conn.execute("SELECT COUNT(*) FROM ratings").fetchone()[0]
    assert ratings_count == 0, "an unplayed game must never produce a ratings row"

    conn.close()
    os.remove(TEST_DB)


def test_schedule_placeholder_pruned_once_scored():
    """Once a real result comes in for a previously-scheduled game, the
    schedule placeholder should be removed automatically."""
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    conn = db.connect(TEST_DB)
    db.upsert_team(conn, "A", "Team A")
    db.upsert_team(conn, "B", "Team B")

    db.add_scheduled_game(conn, date(2025, 6, 1), 2025, "R", None, "A", "B")
    db.add_game(conn, date(2025, 6, 1), 2025, "R", None, "A", "B", 80, 70, 0)
    conn.commit()

    pruned = db.prune_played_schedule_rows(conn)
    assert pruned == 1

    schedule_count = conn.execute("SELECT COUNT(*) FROM schedule").fetchone()[0]
    assert schedule_count == 0

    conn.close()
    os.remove(TEST_DB)


if __name__ == "__main__":
    test_regular_season_games_dedupe_on_reinsert()
    test_playoff_games_still_dedupe_by_round()
    test_unplayed_games_never_enter_games_table()
    test_schedule_placeholder_pruned_once_scored()
    print("All db sanity checks passed.")
