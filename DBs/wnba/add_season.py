"""
Add a new season's games to the database, from a single command.

Usage:
    python3 add_season.py /path/to/results_file.xlsx
    python3 add_season.py /path/to/results_file.csv

Works with either shape of file you've been using:
  - "raw results" style:   Date, Season, Type, Round, Team, Opp, HomeAway, PF, PA, OT
  - "Echo Ratings" style:  ...RawData sheet with Team, Opponent, PointsFor, PointsAgainst...

A row with a real score goes into `games` (and affects ratings). A row
with everything else but NO score yet (e.g. a future game on the
schedule) goes into `schedule` instead - it is never treated as a 0-0
result, and never touches the rating engine. This means you can pull
a season's FULL schedule the moment it's released, load it once, and
then just re-run this same command daily as scores come in - rows
that now have a score get inserted into `games` as normal, and their
matching `schedule` placeholder is automatically cleared out.

It will:
  1. Auto-detect any team codes not already in the database and
     register them as brand new franchises - each gets a permanent
     synthetic team_id (e.g. "wnba_0013") and an era-scoped history
     entry starting at the earliest season the code appears in this
     file (see "Naming a new team" below).
  2. Insert every completed game (deduped automatically - re-running on
     the same file is always safe).
  3. Route unplayed games to `schedule` (see above).
  4. Rebuild the full ratings history so everything stays consistent.
  5. Recompute Elo's predicted winner for every still-upcoming game in
     `schedule`, using the freshly-rebuilt ratings (see
     write_schedule_predictions() below) - so picks always reflect
     today's results, not yesterday's.
  6. Run a handful of sanity checks and print a standings summary.

Naming a new team:
    New teams get registered with team_name == team_id's original code
    (e.g. "IND") as a placeholder, so nothing blocks the load. Fix the
    display name afterward with:

        python3 -c "import db; c=db.connect('wnba_elo.db'); \\
            db.rename_current_history(c, 'wnba_0013', 'Indiana Fever'); \\
            db.upsert_team(c,'wnba_0013','Indiana Fever'); c.commit()"

    (Use franchise.py status to look up a code's team_id.)
"""
import sys
from pathlib import Path
import pandas as pd
import db
import predict
import simulate_season
from rebuild import rebuild_ratings, standings, sanity_checks, VARIANTS

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # DBs/ - for social_card.py
import social_card

DB_PATH = "wnba_elo.db"

# Accept either naming convention seen so far.
COLUMN_ALIASES = {
    "opponent": ["Opponent", "Opp"],
    "points_for": ["PointsFor", "PF"],
    "points_against": ["PointsAgainst", "PA"],
}


def _resolve_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["Date"] = df["Date"]
    out["Season"] = df["Season"]
    out["Type"] = df["Type"]
    out["Round"] = df["Round"]
    out["Team"] = df["Team"]
    out["HomeAway"] = df["HomeAway"]
    out["OT"] = df["OT"] if "OT" in df.columns else 0

    for a in COLUMN_ALIASES["opponent"]:
        if a in df.columns:
            out["opponent"] = df[a]
            break
    else:
        raise ValueError(f"Couldn't find any of {COLUMN_ALIASES['opponent']} in the "
                          f"file's columns: {list(df.columns)}")

    # Scores are optional: a pure schedule export (upcoming games, no
    # results yet) may not have PF/PA columns at all. Missing scores
    # are what route a row to `schedule` instead of `games` - see
    # load_file() below.
    for target in ("points_for", "points_against"):
        for a in COLUMN_ALIASES[target]:
            if a in df.columns:
                out[target] = df[a]
                break
        else:
            out[target] = pd.NA
    return out


def _read_any(path: str) -> pd.DataFrame:
    if path.lower().endswith(".csv"):
        df = pd.read_csv(path, parse_dates=["Date"])
    else:
        # Try a RawData sheet first (Echo Ratings style), else the first sheet.
        xl = pd.ExcelFile(path)
        sheet = "RawData" if "RawData" in xl.sheet_names else xl.sheet_names[0]
        df = pd.read_excel(path, sheet_name=sheet)
    return df


def _register_new_teams(conn, homes: pd.DataFrame, upcoming: pd.DataFrame) -> set[str]:
    """Find any team codes in this file that don't already resolve to
    a known team_id, register each as a brand new franchise (permanent
    synthetic team_id + an era-scoped team_history entry starting at
    the earliest season that code appears in this file), and remap
    `homes`/`upcoming` in place from the raw code to the new team_id.
    Returns the set of raw codes that were newly registered."""
    existing_teams = {row[0] for row in conn.execute("SELECT team_id FROM teams").fetchall()}
    for df in (homes, upcoming):
        df["Team"] = df["Team"].apply(lambda c: db.resolve_team_id(conn, c))
        df["opponent"] = df["opponent"].apply(lambda c: db.resolve_team_id(conn, c))

    new_codes = ((set(homes["Team"]) | set(homes["opponent"])
                  | set(upcoming["Team"]) | set(upcoming["opponent"])) - existing_teams)
    if new_codes:
        combined = pd.concat(
            [homes[["Team", "opponent", "Season"]], upcoming[["Team", "opponent", "Season"]]],
            ignore_index=True,
        )
        code_to_new_id = {}
        for code in sorted(new_codes):
            first_season = int(combined.loc[
                (combined["Team"] == code) | (combined["opponent"] == code), "Season"
            ].min())
            code_to_new_id[code] = db.register_new_team(conn, code, code, first_season)
        # Re-resolve now that aliases exist for the newly registered codes.
        for df in (homes, upcoming):
            df["Team"] = df["Team"].replace(code_to_new_id)
            df["opponent"] = df["opponent"].replace(code_to_new_id)
    return new_codes


def load_file(conn, path: str) -> tuple[dict, set[int], set[str]]:
    df = _read_any(path)
    df = _resolve_columns(df)

    # Regular home/away games: keep the "H" row as canonical.
    # Neutral-site games (e.g. the 2020 COVID "bubble" season, played
    # entirely at IMG Academy) have no true home team - both rows say
    # "N". Pick one deterministically (alphabetically first team code)
    # so each game is stored exactly once, and flag it as neutral so
    # the engine skips home-court advantage for it.
    is_home_away = df["HomeAway"] == "H"
    is_neutral_canonical = (df["HomeAway"] == "N") & (df["Team"] < df["opponent"])
    homes = df[is_home_away | is_neutral_canonical].copy()
    homes["neutral"] = (homes["HomeAway"] == "N").astype(int)

    # A row missing Date/Season/Type/Team/Opponent is genuinely
    # malformed (usually a stray blank row Excel included in the
    # sheet's used range) - drop it and say so.
    required = ["Date", "Season", "Type", "Team", "opponent"]
    bad_mask = homes[required].isna().any(axis=1)
    if bad_mask.any():
        print(f"WARNING: skipping {bad_mask.sum()} row(s) with missing/blank data "
              f"(often a stray blank row at the end of the sheet):")
        for idx, row in homes[bad_mask].iterrows():  # +2 ~= visible Excel row number
            print(f"  ~row {idx + 2}: {row[required].to_dict()}")
        homes = homes[~bad_mask].copy()

    # A row with everything EXCEPT a score is an upcoming/unplayed
    # game - it goes to `schedule`, never to `games`. This is the
    # deliberate fix for the old spreadsheet's "unplayed game = 0-0
    # tie" bug: a missing score here can only ever become a schedule
    # entry, structurally, not a fake result.
    has_score = homes[["points_for", "points_against"]].notna().all(axis=1)
    upcoming = homes[~has_score].copy()
    homes = homes[has_score].copy()

    new_teams = _register_new_teams(conn, homes, upcoming)

    inserted = 0
    attempted = 0
    seasons = set()
    for _, r in homes.iterrows():
        attempted += 1
        round_ = None if r["Round"] == "RS" else float(r["Round"])
        seasons.add(int(r["Season"]))
        was_new = db.add_game(
            conn,
            d=pd.Timestamp(r["Date"]).date(),
            season=int(r["Season"]),
            type_=r["Type"],
            round_=round_,
            home_team=r["Team"],
            away_team=r["opponent"],
            home_pts=int(r["points_for"]),
            away_pts=int(r["points_against"]),
            ot=int(r["OT"]),
            neutral=int(r["neutral"]),
        )
        if was_new:
            inserted += 1

    scheduled = 0
    for _, r in upcoming.iterrows():
        round_ = None if r["Round"] == "RS" else float(r["Round"])
        seasons.add(int(r["Season"]))
        was_new = db.add_scheduled_game(
            conn,
            d=pd.Timestamp(r["Date"]).date(),
            season=int(r["Season"]),
            type_=r["Type"],
            round_=round_,
            home_team=r["Team"],
            away_team=r["opponent"],
            neutral=int(r["neutral"]),
        )
        if was_new:
            scheduled += 1

    # If this file's now-scored rows match rows already sitting in
    # `schedule` from an earlier "schedule-only" load, clear those
    # placeholders out - they've been played now.
    pruned = db.prune_played_schedule_rows(conn)

    conn.commit()
    return (dict(attempted=attempted, inserted=inserted, scheduled=scheduled, pruned=pruned),
            seasons, new_teams)


def write_schedule_predictions(conn, variant: str) -> int:
    """Recompute Elo's pick for every still-upcoming game in `schedule`
    and write it into schedule_predictions FOR THIS VARIANT, using
    whatever ratings are current as of the games `rebuild_ratings()`
    just processed for this same variant.

    Deliberately called AFTER rebuild_ratings(variant) in main(), never
    before - a prediction made against stale ratings would be
    actively wrong, not just outdated. Purely additive/read-only
    against `games` and the rating engine: only ever writes to
    schedule_predictions via db.save_schedule_prediction(), so a bug
    here cannot corrupt real results or ratings, at worst it shows a
    wrong pick on the site.

    Reuses predict.py's build_current_engine() (replay real games to
    get each team's live state) rather than re-implementing it - see
    predict.py's own docstring for why that function is safe to reuse
    here: it's already read-only.

    Returns the number of upcoming games a prediction was written for.
    """
    eng = predict.build_current_engine(conn, variant)
    upcoming = db.upcoming_games(conn)
    for g in upcoming:
        p = eng.preview_matchup(
            home_team=g["home_team"], away_team=g["away_team"], game_date=g["date"],
            season=g["season"], type_=g["type"], round_=g["round"], neutral=bool(g["neutral"]),
        )
        db.save_schedule_prediction(
            conn, g["schedule_id"], variant,
            expected_win_home=p["expected_win_home"],
            expected_win_away=p["expected_win_away"],
            home_days_off=p["days_off_home"],
            away_days_off=p["days_off_away"],
            # Engine's clamp is symmetric (±16 both sides), so
            # rest_adj_away is always exactly -rest_adj_home - only
            # the home value needs to be stored. See schema note in
            # db.py's SCHEMA docstring for schedule_predictions.
            rest_adj=p["rest_adj_home"],
        )
    conn.commit()
    return len(upcoming)


def write_season_projection(conn, seasons, variant: str) -> dict:
    """Recompute the Monte Carlo season projection (simulate_season.py)
    FOR THIS VARIANT, for every season touched by this file's run that
    still has remaining (unplayed) regular-season games, and persist
    it to `season_projections` for the export script to pick up next.

    Called AFTER rebuild_ratings(variant), same reasoning as
    write_schedule_predictions() above - a projection built from stale
    ratings would be actively wrong. Read-only against `games`/ratings;
    only ever writes to `season_projections`, so a bug here can't
    corrupt real results, ratings, or the schedule/prediction data.

    Reuses simulate_season.py's own run_simulation()/summarize() rather
    than reimplementing them - same reasoning as reusing predict.py's
    build_current_engine() for schedule predictions. Note this is
    noticeably heavier than schedule predictions (1000 trials, each
    deep-copying the full rating engine and replaying every remaining
    game) - and this now runs once per variant, so expect roughly
    double the runtime of a single-variant projection pass.

    Returns {season: team_count} for seasons a projection was written
    for. A season with no remaining games (simulate_season returns
    None) has any stale projection for this variant cleared instead,
    so an old snapshot doesn't linger and look current once a season's
    actually over.
    """
    updated = {}
    for season in seasons:
        sim = simulate_season.run_simulation(conn, season, variant, trials=1000)
        if sim is None:
            db.clear_season_projection(conn, season, variant)
            continue
        summary_rows = simulate_season.summarize(sim, season)
        db.save_season_projection(
            conn, season, variant, summary_rows, trials=1000, remaining_games=len(sim["remaining"])
        )
        updated[season] = len(summary_rows)
    return updated


def main():
    if len(sys.argv) != 2:
        print("Usage: python3 add_season.py /path/to/file.xlsx")
        sys.exit(1)
    path = sys.argv[1]
    if not Path(path).exists():
        print(f"File not found: {path}")
        sys.exit(1)

    conn = db.connect(DB_PATH)
    counts, seasons, new_teams = load_file(conn, path)

    print(f"Read {counts['attempted'] + counts['scheduled']} rows from {path}.")
    print(f"Inserted {counts['inserted']} new completed game(s) "
          f"({counts['attempted'] - counts['inserted']} were already in the database).")
    if counts["scheduled"]:
        print(f"Added {counts['scheduled']} upcoming (unplayed) game(s) to the schedule "
              f"- these are NOT included in ratings until they have a real score.")
    if counts["pruned"]:
        print(f"Removed {counts['pruned']} schedule placeholder(s) that now have a real result.")
    if new_teams:
        print(f"Registered new team code(s): {sorted(new_teams)} "
              f"(placeholder names set - rename them, see this script's docstring)")

    # Raw results are parsed and inserted into `games` exactly once,
    # above - both variants share that same table, since results don't
    # differ between them. Everything from here down (ratings,
    # predictions, projections) is variant-specific and runs once per
    # entry in VARIANTS, so one command/one file keeps every variant
    # current together.
    for variant in VARIANTS:
        print(f"=== {variant} ===")
        rebuild_ratings(conn, variant)
        print(f"Ratings rebuilt for the full history ({variant}).")

        n_predicted = write_schedule_predictions(conn, variant)
        if n_predicted:
            print(f"Updated Elo predictions for {n_predicted} upcoming game(s) ({variant}).")

        projection_updates = write_season_projection(conn, seasons, variant)
        for season, n_teams in projection_updates.items():
            print(f"Updated season projection for {season} ({variant}): {n_teams} team(s).")

        warnings = sanity_checks(conn, seasons, variant)
        if warnings:
            print(f"WARNINGS ({variant}):")
            for w in warnings:
                print(f"  - {w}")
        else:
            print(f"Sanity checks passed ({variant}): no NaNs, no missing teams, standings look complete.")

        for season in sorted(seasons):
            print(f"--- {season} standings ({variant}) ---")
            for team, name, w, l, rating in standings(conn, season, variant):
                print(f"{name:24s} {w:.0f}-{l:.0f}   Elo {rating:.2f}")
        print()

    # Instagram card for the next upcoming slate, always off Echo (the
    # site's default variant) regardless of which variant just ran above -
    # see social_card.py's own docstring for why that's safe. None means
    # there's genuinely nothing upcoming to post (e.g. offseason), not
    # an error.
    card_path = social_card.generate_next_slate_card(conn, "wnba")
    if card_path:
        print(f"Saved Instagram card for the next slate: {card_path}")


if __name__ == "__main__":
    main()
