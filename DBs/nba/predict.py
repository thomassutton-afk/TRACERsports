"""
Predict upcoming (unplayed) games using each team's CURRENT rating.

Usage:
    python3 predict.py                    # all upcoming games in the schedule
    python3 predict.py --season 2025      # just one season's upcoming games

This never touches `games` or the rating engine's stored state - it's
purely read-only. Ratings used are whatever's currently in the
database as of the most recently PLAYED game; unplayed games in
`schedule` have no influence on this or on each other.

Writes reports/upcoming_predictions.csv and prints a summary to the
terminal.
"""
import argparse
import csv
import os
import db
import engine
from rebuild import variant_params

DB_PATH = "nba_elo.db"
OUT_DIR = "reports"


def build_current_engine(conn, variant: str = "echo") -> engine.EloEngine:
    """Replay all real games to get each team's current state for ONE
    variant, without writing anything back to the database."""
    games = db.load_games(conn)
    resets = db.load_resets(conn)
    params = variant_params(conn, variant)
    eng = engine.EloEngine(params, resets=resets)
    for g in games:
        eng.process_game(g)
    return eng


def predict_all(conn, season=None, variant: str = "echo"):
    eng = build_current_engine(conn, variant)
    upcoming = db.upcoming_games(conn, season=season)

    predictions = []
    for g in upcoming:
        p = eng.preview_matchup(
            home_team=g["home_team"], away_team=g["away_team"], game_date=g["date"],
            season=g["season"], type_=g["type"], round_=g["round"], neutral=bool(g["neutral"]),
        )
        p["home_name"] = db.display_name(conn, g["home_team"], g["season"])
        p["away_name"] = db.display_name(conn, g["away_team"], g["season"])
        predictions.append(p)
    return predictions


def write_csv(predictions, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "season", "type", "round", "home_team", "away_team", "neutral",
                    "home_rating", "away_rating", "expected_win_home", "expected_win_away",
                    "favored_team"])
        for p in predictions:
            favored = p["home_team"] if p["expected_win_home"] >= 0.5 else p["away_team"]
            w.writerow([p["date"], p["season"], p["type"], p["round"], p["home_team"],
                        p["away_team"], p["neutral"], round(p["home_rating"], 2),
                        round(p["away_rating"], 2), round(p["expected_win_home"], 4),
                        round(p["expected_win_away"], 4), favored])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, help="restrict to one season; omit for all upcoming games")
    parser.add_argument("--variant", default="echo", choices=["echo", "pulse"])
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    conn = db.connect(DB_PATH)
    predictions = predict_all(conn, season=args.season, variant=args.variant)

    if not predictions:
        print("No upcoming (unplayed) games found in the schedule"
              + (f" for season {args.season}." if args.season else "."))
        return

    csv_path = os.path.join(OUT_DIR, "upcoming_predictions.csv")
    write_csv(predictions, csv_path)

    print(f"{len(predictions)} upcoming game(s):\n")
    for p in predictions:
        venue = " (neutral site)" if p["neutral"] else ""
        print(f"  {p['date']}  {p['home_name']} vs {p['away_name']}{venue}")
        print(f"    Ratings: {p['home_name']} {p['home_rating']:.1f}  |  "
              f"{p['away_name']} {p['away_rating']:.1f}")
        print(f"    Win probability: {p['home_name']} {p['expected_win_home']:.1%}  |  "
              f"{p['away_name']} {p['expected_win_away']:.1%}\n")

    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
