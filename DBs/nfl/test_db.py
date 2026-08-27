"""
Regression tests for db.py. Each test documents one specific, real
risk found while building this project - not generic scaffolding.
Run with: python3 test_db.py
"""
import os
import tempfile
from datetime import date
import db

_temp_files = []
_open_conns = []


def fresh_conn():
    """A fresh, empty database for one test - a unique filename per
    call (not reusing/recreating the same path) so an unclosed
    connection from an earlier test can never interfere with this one."""
    fd, path = tempfile.mkstemp(suffix=".db", dir=".")
    os.close(fd)
    os.remove(path)  # sqlite wants to create it itself
    _temp_files.append(path)
    conn = db.connect(path)
    _open_conns.append(conn)
    return conn


def _cleanup():
    # Windows keeps a file lock open for as long as a sqlite3 connection
    # to it is open - unlike Linux/Mac, where a still-open file can be
    # unlinked without error. Every connection fresh_conn() handed out
    # must be closed BEFORE the os.remove() pass below, or cleanup
    # fails with a PermissionError on Windows even though every test
    # already passed.
    for conn in _open_conns:
        conn.close()
    for path in _temp_files:
        if os.path.exists(path):
            os.remove(path)
    if os.path.exists("active_params.json"):
        os.remove("active_params.json")


def test_dedup_on_null_round():
    """A plain SQL UNIQUE constraint treats every NULL as distinct from
    every other NULL - so two regular-season games (round IS NULL) on
    the same date/matchup would never dedupe against each other without
    the IFNULL(round, 'RS') index. This is the same bug class NBA/WNBA's
    add_game() dedup relies on avoiding."""
    conn = fresh_conn()
    ari = db.register_new_team(conn, "ARI", "ARI", 2019)
    atl = db.register_new_team(conn, "ATL", "ATL", 2019)
    d = date(2019, 9, 8)
    first = db.add_game(conn, d, 2019, "R", None, ari, atl, "ARI", "ATL", 20, 17, ot=0)
    second = db.add_game(conn, d, 2019, "R", None, ari, atl, "ARI", "ATL", 20, 17, ot=0)
    assert first is True, "First insert should report as new."
    assert second is False, "BUG: re-adding the same regular-season game (round=NULL) " \
                             "created a duplicate instead of being deduped."
    count = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    assert count == 1, f"BUG: expected exactly 1 game row, found {count}."
    print("test_dedup_on_null_round: PASS")


def test_dedup_on_playoff_round():
    """Same dedup check, but for a playoff game with a real round label
    - makes sure the fix for regular-season NULLs didn't accidentally
    break deduping of playoff rounds that legitimately differ (e.g. two
    different playoff games between the same two teams in the same
    season should NOT be deduped against each other)."""
    conn = fresh_conn()
    ari = db.register_new_team(conn, "ARI", "ARI", 2019)
    atl = db.register_new_team(conn, "ATL", "ATL", 2019)
    d = date(2020, 1, 5)
    db.add_game(conn, d, 2019, "P", "WC", ari, atl, "ARI", "ATL", 24, 20, ot=0)
    dup = db.add_game(conn, d, 2019, "P", "WC", ari, atl, "ARI", "ATL", 24, 20, ot=0)
    assert dup is False, "BUG: re-adding the same playoff game created a duplicate."
    different_round = db.add_game(conn, date(2020, 1, 12), 2019, "P", "DV",
                                   ari, atl, "ARI", "ATL", 30, 27, ot=0)
    assert different_round is True, "BUG: a genuinely different playoff round (WC vs DV) " \
                                     "on the same matchup got incorrectly deduped."
    print("test_dedup_on_playoff_round: PASS")


def test_unplayed_game_never_reaches_games_table():
    """The whole point of the `schedule` table: an unplayed game must
    be structurally impossible to insert into `games` - there's no
    score to default to 0 for. This only checks that add_scheduled_game
    writes to `schedule`, not `games` - add_season.py is what actually
    decides an unplayed row belongs in schedule in the first place."""
    conn = fresh_conn()
    d = date(2026, 9, 13)
    db.register_new_team(conn, "ARI", "ARI", 2026)
    db.register_new_team(conn, "ATL", "ATL", 2026)
    db.add_scheduled_game(conn, d, 2026, "R", None, "nfl_0001", "nfl_0002", "ARI", "ATL")
    n_games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
    n_schedule = conn.execute("SELECT COUNT(*) FROM schedule").fetchone()[0]
    assert n_games == 0, f"BUG: an unplayed game ended up in `games` ({n_games} row(s))."
    assert n_schedule == 1, f"BUG: expected 1 schedule row, found {n_schedule}."
    print("test_unplayed_game_never_reaches_games_table: PASS")


def test_prune_removes_only_played_schedule_rows():
    """Once a game that was scheduled gets a real result, its
    `schedule` placeholder should be removed - but only THAT row, not
    other still-unplayed games."""
    conn = fresh_conn()
    db.register_new_team(conn, "ARI", "ARI", 2026)
    db.register_new_team(conn, "ATL", "ATL", 2026)
    db.register_new_team(conn, "BAL", "BAL", 2026)
    d1, d2 = date(2026, 9, 13), date(2026, 9, 20)
    db.add_scheduled_game(conn, d1, 2026, "R", None, "nfl_0001", "nfl_0002", "ARI", "ATL")
    db.add_scheduled_game(conn, d2, 2026, "R", None, "nfl_0001", "nfl_0003", "ARI", "BAL")
    # The first game now has a real result.
    db.add_game(conn, d1, 2026, "R", None, "nfl_0001", "nfl_0002", "ARI", "ATL", 24, 20, ot=0)
    removed = db.prune_played_schedule_rows(conn)
    remaining = conn.execute("SELECT COUNT(*) FROM schedule").fetchone()[0]
    assert removed == 1, f"BUG: expected to prune exactly 1 played placeholder, pruned {removed}."
    assert remaining == 1, f"BUG: expected 1 still-unplayed schedule row left, found {remaining}."
    print("test_prune_removes_only_played_schedule_rows: PASS")


def test_era_scoped_display_name():
    """The whole point of team_history: the same team_id must display
    under whatever code/name it actually used THAT season, even after
    a later relocation/rename changes its current name. Confirms the
    real NFL case (same code, name-only change) works, not just NBA's
    code-changes-too case."""
    conn = fresh_conn()
    team_id = db.register_new_team(conn, "SD", "San Diego Chargers", 1996)
    db.close_team_history(conn, team_id, 2016)
    db.add_team_history(conn, team_id, "SD", "Los Angeles Chargers", 2017)
    assert db.display_name(conn, team_id, 2010) == "San Diego Chargers", \
        "BUG: a pre-relocation season didn't show the historical name."
    assert db.display_name(conn, team_id, 2020) == "Los Angeles Chargers", \
        "BUG: a post-relocation season didn't show the current name."
    print("test_era_scoped_display_name: PASS")


if __name__ == "__main__":
    test_dedup_on_null_round()
    test_dedup_on_playoff_round()
    test_unplayed_game_never_reaches_games_table()
    test_prune_removes_only_played_schedule_rows()
    test_era_scoped_display_name()
    _cleanup()
    print("\nAll db sanity checks passed.")
