"""
Pull all available historical NFL betting lines from the nflverse games.csv
(spread/total back to 1999, moneylines/odds back to 2006) and load them
into a SQLite table.

Usage:
    python pull_betting_lines.py [--db path/to/nfl_elo.db] [--table betting_lines] [--csv-out games_betting.csv]

If no --db is given, it just writes a CSV.
"""

import argparse
import sqlite3
import sys
import urllib.request

import pandas as pd

NFLVERSE_GAMES_URL = "https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv"

# Columns we care about for a betting-lines table. Keep game_id/season/week/teams
# as join keys back to your existing schedule/Elo tables.
KEEP_COLS = [
    "game_id", "season", "game_type", "week", "gameday", "weekday", "gametime",
    "away_team", "home_team", "away_score", "home_score", "result", "overtime",
    "away_moneyline", "home_moneyline",
    "spread_line", "away_spread_odds", "home_spread_odds",
    "total_line", "under_odds", "over_odds",
    "div_game", "roof", "surface", "temp", "wind",
]


def fetch_games_csv(url: str = NFLVERSE_GAMES_URL) -> pd.DataFrame:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp:
        df = pd.read_csv(resp)
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=None, help="Path to a SQLite db to write into (e.g. nfl_elo.db)")
    ap.add_argument("--table", default="betting_lines", help="Table name to create/replace in the db")
    ap.add_argument("--csv-out", default="games_betting.csv", help="Path to also write a CSV copy")
    args = ap.parse_args()

    print(f"Fetching {NFLVERSE_GAMES_URL} ...")
    df = fetch_games_csv()
    print(f"Pulled {len(df)} games, seasons {df['season'].min()}-{df['season'].max()}")

    missing = [c for c in KEEP_COLS if c not in df.columns]
    if missing:
        print(f"Warning: expected columns not found in source, skipping: {missing}", file=sys.stderr)

    cols = [c for c in KEEP_COLS if c in df.columns]
    out = df[cols].copy()

    out.to_csv(args.csv_out, index=False)
    print(f"Wrote CSV: {args.csv_out} ({len(out)} rows)")

    if args.db:
        con = sqlite3.connect(args.db)
        out.to_sql(args.table, con, if_exists="replace", index=False)
        con.execute(f"CREATE INDEX IF NOT EXISTS idx_{args.table}_game_id ON {args.table}(game_id)")
        con.execute(f"CREATE INDEX IF NOT EXISTS idx_{args.table}_season_week ON {args.table}(season, week)")
        con.commit()
        con.close()
        print(f"Loaded into {args.db} -> table '{args.table}' with indexes on game_id and (season, week)")


if __name__ == "__main__":
    main()
