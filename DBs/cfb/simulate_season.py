"""
Project final season standings by simulating the remaining schedule
many times (Monte Carlo), starting from each team's CURRENT rating.

Ported from NFL_Elo's simulate_season.py (see TRACERsports/DBs/nfl/
simulate_season.py). CFB-specific difference from the NFL original:
remaining games need home_conf/away_conf/home_div/away_div/
home_is_fbs/away_is_fbs annotated before they can be fed to
engine.process_week() or engine.preview_matchup() - see engine.py's
process_week docstring and FCS HANDLING section. The NFL version
doesn't need this (no conferences/FCS-equivalent opponents in that
engine), so this port adds a rebuild._annotate_conferences() call
that the NFL original doesn't have, and threads those fields through
both preview_matchup() and the synthetic week-game dicts. Without
this, every simulated remaining game would silently lose its
conference-game K-factor bonus and FCS-opponent handling, which
would skew projected win totals for any team with FCS or conference
games left on its schedule - i.e. almost every team, almost every
season.

Also filters the final projection to FBS teams only (via
db.is_fbs()): the per-trial win/loss bookkeeping below tracks BOTH
sides of every remaining game, including a same-season FCS
"buy game" opponent - but an FCS team doesn't have a real
`ratings`-based season entry (see FCS HANDLING), so it isn't in
`current`, and projecting a fragment-of-a-season win total for it
from only its FBS games would be meaningless. The NFL original
doesn't need this filter (no FCS-equivalent opponents exist there).

Usage:
    python3 simulate_season.py --season 2026
    python3 simulate_season.py --season 2026 --trials 5000

For each remaining game, a winner is drawn using the model's own
expected-win probability at that point in the simulated season, and a
plausible margin of victory is sampled from real historical games so
the K-factor/margin-of-victory math updates ratings the same way it
would for a real result. Remaining games are simulated WEEK BY WEEK,
in the same weekly batches the real engine uses (see engine.py) - two
games in the same simulated week never see each other's simulated
result, matching how the real engine works.

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
from rebuild import build_current_engine, standings as real_standings, _annotate_conferences

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cfb_elo.db")
OUT_DIR = "reports"


def historical_mov_pool(conn) -> list[int]:
    """Absolute margins of victory from every REAL game on record, used
    to sample a plausible margin for a simulated result."""
    rows = conn.execute("SELECT home_pts, away_pts FROM games").fetchall()
    pool = [abs(hp - ap) for hp, ap in rows if hp != ap]
    return pool or [7]  # fallback if the database is ever empty


def _week_buckets(games: list[dict]) -> dict[int, list[dict]]:
    """Same bucketing engine.week_from_date() needs, but for the
    remaining/upcoming games of ONE season only (so no season_start
    dict is needed, just this season's own opener)."""
    if not games:
        return {}
    season = games[0]["season"]
    season_start = min(g["date"] for g in games)
    weeks: dict[int, list[dict]] = {}
    for g in games:
        wk = engine.week_from_date(g["date"], season_start)
        weeks.setdefault(wk, []).append(g)
    return weeks


def simulate_one_season(base_engine, remaining_games, mov_pool, rng) -> dict:
    """Returns final Elo rating and simulated W/L for every team that
    plays at least one of the remaining games, for ONE trial. Processes
    week by week, same as the real engine - a simulated Thursday game
    and simulated Saturday game in the same week still share the same
    starting ratings for that week.

    remaining_games must already be annotated with home_conf/away_conf/
    home_div/away_div/home_is_fbs/away_is_fbs (see
    rebuild._annotate_conferences) - this function just threads those
    fields through, it doesn't look them up itself."""
    eng = copy.deepcopy(base_engine)
    wl = {}
    weeks = _week_buckets(remaining_games)

    for wk in sorted(weeks):
        week_games = sorted(weeks[wk], key=lambda g: g["date"])
        synthetic_week = []
        outcomes = []  # (home_team, away_team, home_wins) per game, for W/L bookkeeping
        for g in week_games:
            preview = eng.preview_matchup(
                home_team=g["home_team"], away_team=g["away_team"], game_date=g["date"],
                season=g["season"], type_=g["type"], round_=g["round"],
                home_code=g["home_code"], away_code=g["away_code"], neutral=bool(g["neutral"]),
                home_is_fbs=g.get("home_is_fbs", True), away_is_fbs=g.get("away_is_fbs", True),
            )
            home_wins = rng.random() < preview["expected_win_home"]
            margin = rng.choice(mov_pool)
            if home_wins:
                home_pts, away_pts = 20 + margin, 20
            else:
                home_pts, away_pts = 20, 20 + margin
            synthetic_week.append(dict(
                date=g["date"], season=g["season"], type=g["type"], round=g["round"],
                home_team=g["home_team"], away_team=g["away_team"],
                home_code=g["home_code"], away_code=g["away_code"],
                home_pts=home_pts, away_pts=away_pts, ot=0, neutral=g["neutral"],
                home_conf=g.get("home_conf"), away_conf=g.get("away_conf"),
                home_div=g.get("home_div"), away_div=g.get("away_div"),
                home_is_fbs=g.get("home_is_fbs", True), away_is_fbs=g.get("away_is_fbs", True),
            ))
            outcomes.append((g["home_team"], g["away_team"], home_wins))

        eng.process_week(synthetic_week)

        for home_team, away_team, home_wins in outcomes:
            for team in (home_team, away_team):
                wl.setdefault(team, {"w": 0, "l": 0})
            if home_wins:
                wl[home_team]["w"] += 1
                wl[away_team]["l"] += 1
            else:
                wl[away_team]["w"] += 1
                wl[home_team]["l"] += 1

    return dict(wl=wl, ratings=eng.current_ratings())


def run_simulation(conn, season: int, variant: str, trials: int, seed=None):
    rng = random.Random(seed)
    base_engine = build_current_engine(conn, variant)
    mov_pool = historical_mov_pool(conn)

    remaining = db.upcoming_games(conn, season=season)
    if not remaining:
        return None
    _annotate_conferences(conn, remaining)

    # Current real record so far this season, to add the simulated
    # remainder on top of. Wins/losses are the same across variants
    # (they're just real results), but final_rating comes from THIS
    # variant's standings, since a team's simulated starting point
    # should be Pulse's rating when projecting Pulse, not Echo's.
    # real_standings() only has rows for FBS teams (see FCS HANDLING -
    # a non-FBS team never gets a `ratings` row), so this also serves
    # as the FBS-only team list for the projection.
    current = {t: (w, l) for t, _, w, l, _t, _r in real_standings(conn, season, variant)}
    team_names = {t: db.display_name(conn, t, season) for t in current}

    results = []
    for _ in range(trials):
        trial = simulate_one_season(base_engine, remaining, mov_pool, rng)
        trial_final = {}
        # Only project FBS teams (i.e. teams with a real season entry
        # in `current`) - trial["wl"] also contains any FCS "buy game"
        # opponent still on the remaining schedule, but projecting a
        # fragment-of-a-season win total for a team we don't otherwise
        # track would be meaningless.
        for team in current:
            base_w, base_l = current[team]
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
        f"CFB {label} - Season Projection ({season})",
        "=" * 50,
        f"{trials} trials, {remaining_count} remaining game(s) simulated per trial.",
        "",
        f"{'Team':<28}{'Proj. W':>9}{'10th pct':>10}{'Median':>9}{'90th pct':>10}{'P(finish 1st)':>15}",
        "-" * 81,
    ]
    for row in summary_rows:
        lines.append(
            f"{row['name']:<28}{row['avg_wins']:>9.1f}{row['p10']:>10}{row['p50']:>9}"
            f"{row['p90']:>10}{row['p_first']:>14.1%}"
        )
    lines.append("")
    lines.append("Note: this is a projection based on current ratings and simulated")
    lines.append("remaining REGULAR-SEASON games only (no bowl/CCG/CFP projection),")
    lines.append("not a guarantee. Treat the 10th-90th percentile range as the")
    lines.append("plausible range of outcomes, not a hard floor/ceiling. 'P(finish")
    lines.append("1st)' ranks by wins only (no conference tiebreakers/strength-of-")
    lines.append("schedule modeling), so treat close percentages as effectively tied,")
    lines.append("especially across different conferences.")

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
        print(f"  {row['name']:<28} proj {row['avg_wins']:.1f} W  "
              f"(10th-90th: {row['p10']}-{row['p90']})  P(1st) {row['p_first']:.1%}")
    print(f"\nWrote {txt_path}")
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
