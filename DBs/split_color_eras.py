"""
One-time split for team_history rows belonging to franchises that have
NEVER relocated or renamed (same code, same name, 1996-present) but HAVE
had real color-identity changes - Atlanta Hawks, Cleveland Cavaliers,
Dallas Mavericks, etc. Source: the "NBA - Current 30 Franchises" section
of nba_wnba_color_reference_rev2.md.

WHY THIS EXISTS
---------------
db.set_era_colors() / franchise.py set-colors only UPDATE an existing
team_history row matched on (team_id, start_season) - they never CREATE
one. For a relocated/renamed franchise (SEA->OKC, VAN->MEM, etc.)
team_history already has one row per era, because franchise.py relocate
already ran for the code/name change. But a team like the Atlanta Hawks
has had 4 real color eras and exactly ONE continuous team_history row
(1996-present, same code, same name) - there was never a relocate/rename
to split it. That's why seed_historical_colors.py could only ever cover
the relocated/renamed scope: for everyone else, there was no row to set
colors ON.

This script creates those missing rows by doing exactly what
franchise.py relocate does under the hood (close_team_history +
add_team_history) with the SAME code and SAME name - no actual
relocation/rename implied, just a new era boundary. Ratings math is
untouched by this (relocate/rename never affects ratings, only display -
see franchise.py's own docstring), so no rebuild is run.

THE +1 YEAR TRAP - READ BEFORE EDITING THIS LIST
--------------------------------------------------
team_history.start_season uses the "season ends in this calendar year"
convention (confirmed against config.js's seasonLabel AND against the
real, already-correct Hornets->Pelicans split: Charlotte's last season
was 2001-02, and the live db's New Orleans row starts at start_season=
2003, not 2002).

The reference doc's "Recommended" shorthand (e.g. "2007-15") instead uses
the season-STARTS-in-this-year convention. So every split season below is
the doc's shorthand start year of the NEW era, PLUS ONE. Example: doc
says Atlanta's navy era is "2007-15" (raw TruColor row confirms it starts
the 2007-08 season) -> team_history start_season = 2008.

Do not copy a shorthand year directly into this list without adding 1 -
that mistake is already present, uncorrected, in a couple of the
seed_historical_colors.py SPLIT CANDIDATE inline comments (SEA/CHB/WAS)
which this script deliberately does NOT try to reproduce.

USAGE - run from DBs\\ (same convention as seed_historical_colors.py):

    python3 split_color_eras.py --league nba

WNBA has no entries here - the reference doc's WNBA section only covers
the relocated/renamed franchises, which already have the rows they need.

After this runs, seed_historical_colors.py's NBA_COLORS list needs to be
extended to actually set colors on these new rows (separate follow-up -
this script only creates the rows, it does not set any colors).
"""
import argparse
import importlib.util
import os
import sys

# code -> [new_start_season, ...] in ascending order. Only teams with 2+
# recommended eras in the doc appear here - teams with exactly 1
# recommended era (Boston, Brooklyn, current Charlotte Hornets, Chicago,
# New Orleans Pelicans, New York Knicks, Oklahoma City Thunder, Portland,
# San Antonio) need no split; their existing single row already covers
# their whole one-color history.
NBA_SPLITS = {
    "ATL": [2008, 2016, 2021],
    "CLE": [2004, 2011, 2023],
    "DAL": [2002, 2018],
    "DEN": [2004, 2019],
    "DET": [2002, 2021],
    "GSW": [1998, 2011],
    "HOU": [2004, 2020, 2027],
    "IND": [2011, 2026],
    "LAC": [2001, 2016, 2025],
    "LAL": [2000],
    "MEM": [2005],
    "MIA": [2000],
    "MIL": [2007, 2016],
    "MIN": [1997, 2018, 2027],
    "ORL": [1999, 2026],
    "PHI": [1998, 2010, 2023],
    "PHX": [2001, 2018],
    "SAC": [2017],
    # FLAGGED FOR YOUR CALL: doc's era-1 header says "1995-2006" but its
    # own description says purple carried through 2008, and the raw row
    # for the Red/Black/Silver era starts 2008-09 either way - split at
    # 2009 (matching the description + raw row) is what's used here. If
    # you actually want the header's 2006 read literally, that would be
    # split season 2007 instead.
    "TOR": [2009, 2021],
    "UTA": [2005, 2011, 2023, 2026],
    "WAS": [2012],
}


def load_db_module(league: str):
    path = os.path.join(os.path.dirname(__file__), league, "db.py")
    spec = importlib.util.spec_from_file_location(f"{league}_db", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def split_era(db, conn, code: str, new_start_season: int) -> bool:
    """Close the currently-open (end_season IS NULL) team_history era for
    `code` at new_start_season - 1, and open a new one under the SAME
    code/name starting at new_start_season. Returns False (does nothing)
    if this exact split has already been applied on a prior run (a row
    already starts at new_start_season) or if there's no open row for
    this code to split in the first place."""
    team_id = db.resolve_team_id(conn, code)

    # Idempotency guard: if a row already starts exactly here, this split
    # was already applied - do nothing rather than closing whatever OTHER
    # era currently happens to be open (which on a second run would be a
    # later, already-correct era, not the one this call is meant to
    # touch) and corrupting it.
    already = conn.execute(
        "SELECT 1 FROM team_history WHERE team_id = ? AND start_season = ?",
        (team_id, new_start_season),
    ).fetchone()
    if already:
        return False

    row = conn.execute(
        "SELECT name FROM team_history WHERE team_id = ? AND code = ? "
        "AND end_season IS NULL",
        (team_id, code),
    ).fetchone()
    if not row:
        return False
    name = row[0]
    db.close_team_history(conn, team_id, new_start_season - 1)
    db.add_team_history(conn, team_id, code, name, new_start_season)
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--league", required=True, choices=["nba"])
    args = p.parse_args()

    db = load_db_module(args.league)
    db_path = os.path.join(os.path.dirname(__file__), f"{args.league}_elo.db")
    if not os.path.exists(db_path):
        print(f"Expected top-level db at {db_path} - not found. Run this from DBs\\, "
              f"not from inside DBs\\{args.league}\\.")
        sys.exit(1)

    conn = db.connect(db_path)
    splits = NBA_SPLITS

    applied, skipped = 0, 0
    for code, seasons in splits.items():
        for season in seasons:
            ok = split_era(db, conn, code, season)
            if ok:
                applied += 1
                print(f"  {code}: split at {season} (era ending "
                      f"{season - 1} closed, new era opened at {season}).")
            else:
                skipped += 1
                print(f"  SKIPPED: {code} has no currently-open era to split at {season} - "
                      f"already split on a prior run, or code not recognized. Check "
                      f"'franchise.py status' if unexpected.")
    conn.commit()
    print(f"{args.league}: applied {applied}, skipped {skipped} "
          f"(of {sum(len(v) for v in splits.values())} total).")


if __name__ == "__main__":
    main()
