"""
Check how well the college football Elo model's predictions actually
perform: accuracy, Brier score, and log loss - overall, and broken down
by round, season, month, and calibration bucket. Also flags the biggest
upsets and the model's most confident misses.

Usage:
    python3 accuracy_report.py
    python3 accuracy_report.py --variant pulse
    python3 accuracy_report.py --seasons 2023
    python3 accuracy_report.py --seasons 2021,2022,2023
    python3 accuracy_report.py --seasons 2015-2019
    python3 accuracy_report.py --seasons 2015-2019,2023
    python3 accuracy_report.py --include-fcs
    python3 accuracy_report.py --db ../cfb_elo_pre_otlist.db

Produces (in reports/, with the variant - and the database name, if you
pass --db - in the file name):
    accuracy_by_game_<variant>.csv    - one row per game, with the prediction
                                        and how it scored
    accuracy_summary_<variant>.txt    - overall + every breakdown below

--db lets you score a different copy of the database (for example a backup
taken before a change) so two runs can be compared side by side.

Definitions (all computed once per game, not per team-perspective -
these are symmetric between the two team-rows of a game, so every
breakdown below looks at one row per game to avoid double counting):
    - accuracy:  1 if the favored team (higher expected win %) won,
                 0 otherwise. A coin-flip game (expected win % = 50%)
                 counts as a miss either way, by convention.
    - brier:     (expected_win - actual_result)^2. Lower is better;
                 0 is a perfect prediction, 0.25 is what you'd get by
                 always guessing 50/50.
    - log loss:  -[result*log(expected_win) + (1-result)*log(1-expected_win)].
                 Lower is better; penalizes confident wrong predictions
                 much more heavily than Brier does. (Stored in the
                 `test` column of the ratings table.)

College football specifics:
    - The ratings table holds one set of rows per rating variant (echo,
      pulse); --variant picks which one (default: echo).
    - By default only games between two FBS teams are scored. A game against
      an FCS opponent has a single ratings row (the FCS team is held at a
      fixed rating and has none of its own), and predicting those mostly
      measures how big the gap to a fixed rating is. --include-fcs adds them.
    - `type` is 'R' for every game in this database; the round column
      separates conference championships (CCG), bowls (BOWL), the playoff
      (CFP-R1/QF/SF) and the title game (NC) from regular-season games
      (round is empty). "Regular season" below includes CCG, matching how
      the site counts them; the By round block splits them out.
    - "Always pick home team" is computed on non-neutral games only.

Note: this deliberately does NOT break results out "by venue"
(home-row vs away-row) - accuracy/brier/log-loss are identical on
both rows of the same game, so that split would just print the same
numbers twice under different labels.
"""
import argparse
import csv
import os
import db

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "cfb_elo.db"
)
OUT_DIR = "reports"
POSTSEASON_ROUNDS = ("BOWL", "CFP-R1", "CFP-QF", "CFP-SF", "NC")
ROUND_ORDER = ("CCG",) + POSTSEASON_ROUNDS


def pct(x):
    return f"{100 * x:.1f}%"


def parse_seasons(spec: str):
    """Parse a seasons spec like '2023' / '2021,2022' / '2015-2019' / '2015-2019,2023'
    into a sorted list of individual season ints."""
    seasons = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            lo, hi = chunk.split("-", 1)
            lo, hi = int(lo.strip()), int(hi.strip())
            if lo > hi:
                lo, hi = hi, lo
            seasons.update(range(lo, hi + 1))
        else:
            seasons.add(int(chunk))
    return sorted(seasons)


def fetch_games(conn, variant, seasons=None, include_fcs=False):
    """One row per actual game (one team's perspective only, since
    accuracy/brier/log-loss are identical for both perspectives).

    A game between two FBS teams has two ratings rows; we keep the home
    row (or, for a neutral game flagged 'N', the alphabetically first
    team). A game against an FCS opponent has one row and is kept only
    with include_fcs."""
    keep = ("(c.n_rows = 2 AND (r.home_away = 'H' "
            "OR (r.home_away = 'N' AND r.team < r.opponent)))")
    if include_fcs:
        keep = f"({keep} OR c.n_rows = 1)"
    query = f"""
        SELECT r.date, r.season, r.type, r.round, r.team AS home_team,
               r.opponent AS away_team, r.points_for, r.points_against,
               r.home_away, COALESCE(g.neutral, 0), r.ot,
               r.expected_win, r.result, r.accuracy, r.brier, r.test
        FROM ratings r
        JOIN (SELECT game_id, COUNT(*) AS n_rows
              FROM ratings WHERE variant = ? GROUP BY game_id) c
          ON c.game_id = r.game_id
        LEFT JOIN games g ON g.game_id = r.game_id
        WHERE r.variant = ? AND {keep}
    """
    params = [variant, variant]
    if seasons:
        placeholders = ",".join("?" for _ in seasons)
        query += f" AND r.season IN ({placeholders})"
        params += list(seasons)
    query += " ORDER BY r.date, r.game_id"
    rows = conn.execute(query, params).fetchall()
    cols = ["date", "season", "type", "round", "home_team", "away_team",
            "home_pts", "away_pts", "home_away", "neutral", "ot",
            "expected_win", "result", "accuracy", "brier", "log_loss"]
    return [dict(zip(cols, r)) for r in rows]


def is_regular(g):
    """Regular season as the site counts it: everything that is not a bowl,
    CFP game or the title game (so conference championships stay in)."""
    return g["round"] not in POSTSEASON_ROUNDS


def summarize(games, label):
    n = len(games)
    if n == 0:
        return f"{label}: no games"
    acc = sum(g["accuracy"] for g in games) / n
    brier = sum(g["brier"] for g in games) / n
    logloss = sum(g["log_loss"] for g in games) / n
    return f"{label:20s}  n={n:5d}   accuracy={acc:.3f}   brier={brier:.4f}   log_loss={logloss:.4f}"


def home_win_rate(games):
    """Accuracy of blindly picking the home team every time, as a baseline.
    Only genuine home games count (not neutral sites, not the single-row
    FCS games where the FBS team may be the visitor)."""
    decided = [g for g in games
               if g["result"] in (0.0, 1.0) and not g["neutral"] and g["home_away"] == "H"]
    if not decided:
        return float("nan")
    return sum(1 for g in decided if g["result"] == 1.0) / len(decided)


def calibration_buckets(games):
    """Does a '70% favorite' actually win ~70% of the time?"""
    buckets = [(0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)]
    lines = []
    for lo, hi in buckets:
        in_bucket = [g for g in games if lo <= g["expected_win"] < hi]
        if not in_bucket:
            continue
        n = len(in_bucket)
        pred = sum(g["expected_win"] for g in in_bucket) / n
        actual = sum(g["result"] for g in in_bucket) / n
        lines.append(f"  {lo:.0%}-{hi:.0%}     {n:>7} {pct(pred):>15} {pct(actual):>17}")
    return lines


def write_csv(games, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "season", "type", "round", "home_team", "away_team",
                    "home_pts", "away_pts", "neutral", "ot", "expected_win", "result",
                    "accuracy", "brier", "log_loss"])
        for g in games:
            w.writerow([g["date"], g["season"], g["type"], g["round"] or "", g["home_team"],
                        g["away_team"], g["home_pts"], g["away_pts"], g["neutral"], g["ot"],
                        round(g["expected_win"], 4), g["result"], g["accuracy"],
                        round(g["brier"], 4), round(g["log_loss"], 4)])


def write_summary(games, path, seasons_label, variant, include_fcs):
    seasons = sorted({g["season"] for g in games})
    lines = ["College Football Elo Model Accuracy Report", "=" * 45,
             f"Scope: {seasons_label}",
             f"Variant: {variant}",
             "FBS vs FCS games: " + ("included" if include_fcs else "excluded"), ""]

    lines.append(summarize(games, "All games"))
    lines.append(summarize([g for g in games if is_regular(g)], "Regular season"))
    lines.append(summarize([g for g in games if not is_regular(g)], "Postseason"))
    lines.append(summarize([g for g in games if g["ot"]], "Overtime games"))
    lines.append("")

    lines.append("By round:")
    lines.append("  " + summarize([g for g in games if not g["round"]], "Regular season*"))
    for r in ROUND_ORDER:
        sub = [g for g in games if g["round"] == r]
        if sub:
            lines.append("  " + summarize(sub, r))
    lines.append("  (*without conference championships)")
    lines.append("")

    lines.append("Baselines for context:")
    lines.append("  Coin flip (always 50%):   Brier = 0.2500")
    lines.append(f"  Always pick home team:    {pct(home_win_rate(games))} accuracy "
                 "(non-neutral games)")
    lines.append("")

    lines.append("By season:")
    for s in seasons:
        lines.append("  " + summarize([g for g in games if g["season"] == s], str(s)))
    lines.append("")

    lines.append("By month:")
    months = sorted({str(g["date"])[:7] for g in games})
    for m in months:
        lines.append("  " + summarize([g for g in games if str(g["date"]).startswith(m)], m))
    lines.append("")

    lines.append("Calibration (expected win% bucket vs actual win rate):")
    lines.append(f"  {'Bucket':<12} {'Games':>7} {'Predicted avg':>15} {'Actual win rate':>17}")
    lines.extend(calibration_buckets(games))
    lines.append("")

    lines.append("10 biggest upsets (lowest pre-game win probability for the winner):")
    upsets = sorted((g for g in games if g["result"] == 1.0), key=lambda g: g["expected_win"])[:10]
    for g in upsets:
        lines.append(
            f"  {g['date']}  {g['home_team']} beat {g['away_team']}  "
            f"({g['home_pts']}-{g['away_pts']}, given only {g['expected_win']:.1%} to win)"
        )
    lines.append("")

    lines.append("Worst 10 predictions (highest log loss - biggest confident misses):")
    worst = sorted(games, key=lambda g: g["log_loss"], reverse=True)[:10]
    for g in worst:
        fav = g["home_team"] if g["expected_win"] >= 0.5 else g["away_team"]
        winner = g["home_team"] if g["result"] == 1 else (g["away_team"] if g["result"] == 0 else "tie")
        lines.append(
            f"  {g['date']}  {g['home_team']} {g['home_pts']}-{g['away_pts']} {g['away_team']}  "
            f"(favored: {fav} @ {g['expected_win']:.1%}, winner: {winner}, log_loss={g['log_loss']:.3f})"
        )

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--seasons", type=str, default=None,
        help="Season(s) to include, e.g. '2023', '2021,2022', '2015-2019', "
             "or '2015-2019,2023'. Default: all seasons in the database.",
    )
    parser.add_argument(
        "--variant", type=str, default="echo",
        help="Rating variant to score: echo (default) or pulse.",
    )
    parser.add_argument(
        "--include-fcs", action="store_true",
        help="Also score games against FCS opponents (one ratings row each).",
    )
    parser.add_argument(
        "--db", type=str, default=None,
        help="Path to a different cfb_elo database copy (default: ../cfb_elo.db).",
    )
    args = parser.parse_args()

    os.makedirs(OUT_DIR, exist_ok=True)
    conn = db.connect(os.path.abspath(args.db) if args.db else DB_PATH)
    tag = args.variant + (
        "_" + os.path.splitext(os.path.basename(args.db))[0] if args.db else "")

    seasons = parse_seasons(args.seasons) if args.seasons else None
    fetched = fetch_games(conn, args.variant, seasons=seasons,
                          include_fcs=args.include_fcs)

    # A game missing any of its prediction columns can't be scored; say so
    # rather than dropping it silently.
    need = ("expected_win", "result", "accuracy", "brier", "log_loss")
    games = [g for g in fetched if all(g[k] is not None for k in need)]
    if len(games) != len(fetched):
        print(f"Skipped {len(fetched) - len(games)} game(s) with a missing prediction column.")

    if not games:
        print("No games found" + (f" for the requested season(s) {seasons}." if seasons else "."))
        return

    seasons_label = (
        f"season {seasons[0]}" if seasons and len(seasons) == 1
        else f"seasons {seasons[0]}-{seasons[-1]}" if seasons and seasons == list(range(seasons[0], seasons[-1] + 1))
        else f"seasons {seasons}" if seasons
        else "all seasons"
    )

    csv_path = os.path.join(OUT_DIR, f"accuracy_by_game_{tag}.csv")
    summary_path = os.path.join(OUT_DIR, f"accuracy_summary_{tag}.txt")
    write_csv(games, csv_path)
    write_summary(games, summary_path, seasons_label, args.variant, args.include_fcs)

    with open(summary_path) as f:
        print(f.read())
    print(f"Wrote {csv_path}")
    print(f"Wrote {summary_path}")


if __name__ == "__main__":
    main()