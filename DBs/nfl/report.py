"""
Dump the database into plain, readable files - no SQLite browser needed.

Usage:
    python3 report.py

Produces, in a `reports/` folder next to the database:
    standings.csv     - one row per team per season (W/L/T, final Elo, rank)
    game_log.csv       - every game with both teams' ratings before/after
    summary.txt        - a plain-text standings report you can just open

Run this any time you want a fresh look at the data - it always
reflects whatever is currently in nfl_elo.db.
"""
import csv
import os
import db
from rebuild import standings

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "nfl_elo.db"
)
OUT_DIR = "reports"


def write_standings_csv(conn, path):
    seasons = [r[0] for r in conn.execute("SELECT DISTINCT season FROM games ORDER BY season")]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["season", "rank", "team_id", "team_name", "wins", "losses", "ties", "final_elo"])
        for season in seasons:
            rows = standings(conn, season)  # already ranked by final_elo desc
            for rank, (team_id, name, wins, losses, ties, rating) in enumerate(rows, start=1):
                w.writerow([season, rank, team_id, name, int(wins), int(losses), int(ties),
                            round(rating, 2)])


def write_game_log_csv(conn, path):
    cols = ["date", "season", "type", "round", "team", "opponent", "home_away",
            "conf_game", "div_game", "points_for", "points_against", "ot", "pre_rate",
            "post_rate", "rating_change", "expected_win", "result"]
    rows = conn.execute(
        f"SELECT {','.join(cols)} FROM ratings ORDER BY date, game_id, home_away DESC"
    ).fetchall()
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow(r)


def write_summary_txt(conn, path):
    seasons = [r[0] for r in conn.execute("SELECT DISTINCT season FROM games ORDER BY season")]
    lines = []
    lines.append("NFL Elo Ratings - Standings Summary")
    lines.append("=" * 40)
    for season in seasons:
        rows = standings(conn, season)
        lines.append(f"\n{season} ({len(rows)} teams)")
        lines.append("-" * 40)
        for rank, (team_id, name, wins, losses, ties, rating) in enumerate(rows, start=1):
            record = f"{int(wins)}-{int(losses)}" + (f"-{int(ties)}" if ties else "")
            lines.append(f"{rank:2d}. {name:24s} {record:>8s}   Elo {rating:8.2f}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    conn = db.connect(DB_PATH)

    standings_path = os.path.join(OUT_DIR, "standings.csv")
    log_path = os.path.join(OUT_DIR, "game_log.csv")
    summary_path = os.path.join(OUT_DIR, "summary.txt")

    write_standings_csv(conn, standings_path)
    write_game_log_csv(conn, log_path)
    write_summary_txt(conn, summary_path)

    print(f"Wrote {standings_path}")
    print(f"Wrote {log_path}")
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()
