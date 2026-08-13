"""
Project final season standings by simulating the remaining schedule
many times (Monte Carlo), starting from each team's CURRENT rating.

Usage:
    python3 simulate_season.py --season 2025
    python3 simulate_season.py --season 2025 --trials 5000

For each remaining game (in order), a winner is drawn using the
model's own expected-win probability at that point in the simulated
season, and a plausible margin of victory is sampled from real
historical games so the K-factor/margin-of-victory math updates
ratings the same way it would for a real result. Ratings update game
by game WITHIN each simulated season, exactly like the real engine
does - so a simulated early winning streak actually raises that team's
rating for its later simulated games, the same as it would in reality.

This is a projection tool, not a certainty - treat the output as "if
the model's current ratings are right and nothing unusual happens,
here's the range of plausible outcomes," not a guarantee.

Writes reports/season_projection_<season>.txt and
reports/season_projection_<season>.csv (per-team distribution of
simulated final wins and rank).
"""
import argparse
import copy
import csv
import os
import random
import db
import engine
from rebuild import standings as real_standings, variant_params

DB_PATH = "nba_elo.db"
OUT_DIR = "reports"


def historical_mov_pool(conn) -> list[int]:
    """Absolute margins of victory from every REAL game on record, used
    to sample a plausible margin for a simulated result."""
    rows = conn.execute("SELECT home_pts, away_pts FROM games").fetchall()
    pool = [abs(hp - ap) for hp, ap in rows if hp != ap]
    return pool or [10]  # fallback if the database is ever empty


def build_current_engine(conn, variant: str = "echo"):
    games = db.load_games(conn)
    resets = db.load_resets(conn)
    params = variant_params(conn, variant)
    eng = engine.EloEngine(params, resets=resets)
    for g in games:
        eng.process_game(g)
    return eng


def simulate_one_season(base_engine, remaining_games, mov_pool, rng) -> dict:
    """Returns final Elo rating and simulated W/L for every team that
    plays at least one of the remaining games, for ONE trial."""
    eng = copy.deepcopy(base_engine)
    wl = {}

    for g in remaining_games:
        preview = eng.preview_matchup(
            home_team=g["home_team"], away_team=g["away_team"], game_date=g["date"],
            season=g["season"], type_=g["type"], round_=g["round"], neutral=bool(g["neutral"]),
        )
        home_wins = rng.random() < preview["expected_win_home"]
        margin = rng.choice(mov_pool)
        if home_wins:
            home_pts, away_pts = 100 + margin, 100
        else:
            home_pts, away_pts = 100, 100 + margin

        synthetic_game = dict(
            date=g["date"], season=g["season"], type=g["type"], round=g["round"],
            home_team=g["home_team"], away_team=g["away_team"],
            home_pts=home_pts, away_pts=away_pts, ot=0, neutral=g["neutral"],
        )
        eng.process_game(synthetic_game)

        for team in (g["home_team"], g["away_team"]):
            wl.setdefault(team, {"w": 0, "l": 0})
        if home_wins:
            wl[g["home_team"]]["w"] += 1
            wl[g["away_team"]]["l"] += 1
        else:
            wl[g["away_team"]]["w"] += 1
            wl[g["home_team"]]["l"] += 1

    final_ratings = eng.current_ratings()
    return dict(wl=wl, ratings=final_ratings)


def run_simulation(conn, season: int, variant: str, trials: int, seed=None):
    rng = random.Random(seed)
    base_engine = build_current_engine(conn, variant)
    mov_pool = historical_mov_pool(conn)

    remaining = [g for g in db.upcoming_games(conn, season=season) if g["type"] == "R"]
    if not remaining:
        return None

    # Current real record so far this season, to add the simulated
    # remainder on top of. Wins/losses are the same across variants
    # (they're just real results), but final_rating comes from THIS
    # variant's standings, since a team's simulated starting point
    # should be Pulse's rating when projecting Pulse, not Echo's.
    current = {t: (w, l) for t, _, w, l, _ in real_standings(conn, season, variant)}
    all_team_ids = {row[0] for row in conn.execute("SELECT team_id FROM teams").fetchall()}
    team_names = {t: db.display_name(conn, t, season) for t in all_team_ids}

    results = []  # one dict per trial: team -> (final_wins, final_rating)
    for _ in range(trials):
        trial = simulate_one_season(base_engine, remaining, mov_pool, rng)
        trial_final = {}
        all_teams = set(current) | set(trial["wl"])
        for team in all_teams:
            base_w, base_l = current.get(team, (0, 0))
            add_w = trial["wl"].get(team, {}).get("w", 0)
            trial_final[team] = (base_w + add_w, trial["ratings"].get(team, base_engine.current_ratings().get(team)))
        results.append(trial_final)

    return dict(remaining=remaining, current=current, results=results, team_names=team_names)


def summarize(sim, season: int):
    all_teams = sorted({t for r in sim["results"] for t in r})
    trials = len(sim["results"])

    summary_rows = []
    for team in all_teams:
        wins = sorted(r[team][0] for r in sim["results"] if team in r)
        ratings = [r[team][1] for r in sim["results"] if team in r]
        n = len(wins)
        avg_wins = sum(wins) / n
        avg_rating = sum(ratings) / n
        p10 = wins[int(0.10 * n)]
        p50 = wins[int(0.50 * n)]
        p90 = wins[min(n - 1, int(0.90 * n))]
        summary_rows.append(dict(
            team=team, name=sim["team_names"].get(team, team),
            avg_wins=avg_wins, p10=p10, p50=p50, p90=p90, avg_rating=avg_rating,
        ))

    # Rank probability: for each trial, rank teams by final wins (ties
    # broken by final rating), then tally how often each team finishes
    # in each rank position.
    rank_counts = {t: [0] * len(all_teams) for t in all_teams}
    for r in sim["results"]:
        ranked = sorted(r.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))
        for i, (team, _) in enumerate(ranked):
            rank_counts[team][i] += 1

    summary_rows.sort(key=lambda row: -row["avg_wins"])
    for row in summary_rows:
        counts = rank_counts[row["team"]]
        row["p_first"] = counts[0] / trials if trials else 0.0

    return summary_rows


def write_outputs(summary_rows, season, trials, remaining_count, variant="echo"):
    label = "Echo" if variant == "echo" else "Pulse"
    lines = [
        f"NBA {label} - Season Projection ({season})",
        "=" * 50,
        f"{trials} trials, {remaining_count} remaining game(s) simulated per trial.",
        "",
        f"{'Team':<24}{'Proj. W':>9}{'10th pct':>10}{'Median':>9}{'90th pct':>10}{'P(finish 1st)':>15}",
        "-" * 77,
    ]
    for row in summary_rows:
        lines.append(
            f"{row['name']:<24}{row['avg_wins']:>9.1f}{row['p10']:>10}{row['p50']:>9}"
            f"{row['p90']:>10}{row['p_first']:>14.1%}"
        )
    lines.append("")
    lines.append("Note: this is a projection based on current ratings and simulated")
    lines.append("remaining games, not a guarantee. Treat the 10th-90th percentile range")
    lines.append("as the plausible range of outcomes, not a hard floor/ceiling.")

    os.makedirs(OUT_DIR, exist_ok=True)
    suffix = "" if variant == "echo" else f"_{variant}"
    txt_path = os.path.join(OUT_DIR, f"season_projection_{season}{suffix}.txt")
    with open(txt_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    csv_path = os.path.join(OUT_DIR, f"season_projection_{season}{suffix}.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["team", "name", "projected_wins", "p10_wins", "median_wins",
                    "p90_wins", "avg_final_rating", "prob_finish_first"])
        for row in summary_rows:
            w.writerow([row["team"], row["name"], round(row["avg_wins"], 2), row["p10"],
                        row["p50"], row["p90"], round(row["avg_rating"], 1),
                        round(row["p_first"], 4)])

    return txt_path, csv_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--variant", default="echo", choices=["echo", "pulse"])
    parser.add_argument("--trials", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=None, help="for reproducible results")
    args = parser.parse_args()

    conn = db.connect(DB_PATH)
    sim = run_simulation(conn, args.season, args.variant, args.trials, seed=args.seed)
    if sim is None:
        print(f"No remaining (unplayed) games found for season {args.season} - nothing to simulate.")
        return

    summary_rows = summarize(sim, args.season)
    txt_path, csv_path = write_outputs(summary_rows, args.season, args.trials,
                                        len(sim["remaining"]), args.variant)

    print(f"Simulated {args.trials} trials over {len(sim['remaining'])} remaining game(s).\n")
    for row in summary_rows:
        print(f"  {row['name']:<24} proj {row['avg_wins']:.1f} W  "
              f"(10th-90th: {row['p10']}-{row['p90']})  P(1st) {row['p_first']:.1%}")
    print(f"\nWrote {txt_path}")
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
