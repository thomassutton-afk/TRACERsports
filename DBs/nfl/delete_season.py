import os
"""
Delete one or more entire seasons from the database.

Usage:
    python3 delete_season.py --season 2012 --season 2013
    python3 delete_season.py --season 2012 --season 2013 --yes   (skip confirmation)

Deletes in the correct order (ratings before games, since ratings
references games via a foreign key), also clears any forced
fold/revival resets registered for those seasons, then rebuilds the
remaining history. Everything else - other seasons, team names,
relocation aliases - is untouched.
"""
import argparse
import db
from rebuild import rebuild_ratings, VARIANTS

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "nfl_elo.db"
)


def preview(conn, seasons):
    placeholders = ",".join("?" for _ in seasons)
    n_games = conn.execute(
        f"SELECT COUNT(*) FROM games WHERE season IN ({placeholders})", seasons
    ).fetchone()[0]
    n_resets = conn.execute(
        f"SELECT COUNT(*) FROM franchise_resets WHERE season IN ({placeholders})", seasons
    ).fetchone()[0]
    return n_games, n_resets


def delete_seasons(conn, seasons):
    placeholders = ",".join("?" for _ in seasons)
    conn.execute(f"DELETE FROM ratings WHERE season IN ({placeholders})", seasons)
    conn.execute(f"DELETE FROM games WHERE season IN ({placeholders})", seasons)
    conn.execute(f"DELETE FROM franchise_resets WHERE season IN ({placeholders})", seasons)
    conn.commit()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--season", type=int, action="append", required=True,
                    help="a season to delete; repeat --season for multiple")
    p.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = p.parse_args()
    seasons = args.season

    conn = db.connect(DB_PATH)
    n_games, n_resets = preview(conn, seasons)

    if n_games == 0 and n_resets == 0:
        print(f"No data found for season(s) {seasons} - nothing to delete.")
        return

    print(f"This will delete {n_games} game(s) and {n_resets} forced-reset record(s) "
          f"for season(s) {seasons}.")
    if not args.yes:
        confirm = input("Type 'yes' to proceed: ").strip().lower()
        if confirm != "yes":
            print("Cancelled - nothing was deleted.")
            return

    delete_seasons(conn, seasons)
    for variant in VARIANTS:
        rebuild_ratings(conn, variant)
    print(f"Deleted season(s) {seasons} and rebuilt the remaining history (both variants).")


if __name__ == "__main__":
    main()
