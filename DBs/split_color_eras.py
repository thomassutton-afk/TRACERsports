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
    python3 split_color_eras.py --league wnba

WNBA support added for splits discovered team-by-team from TruColor
reference screenshots (not the doc this script started from) - see
WNBA_SPLITS below. Unlike every NBA split above, WNBA season numbers are
used as-written, no +1 needed (WNBA uses calendar-year seasons, not
NBA's season-ends-in-this-year convention - see wnba config.js).

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
    "DET": [1997, 2002, 2021],
    "GSW": [1998, 2011],
    "HOU": [2004, 2020, 2027],
    "IND": [2011, 2026],
    "LAC": [2001, 2016, 2025],
    "LAL": [2000],
    "MEM": [2005, 2019],
    "MIA": [2000],
    "MIL": [2007, 2016],
    "MIN": [1997, 2018, 2027],
    "ORL": [1999, 2026],
    "PHI": [1998, 2010, 2023],
    "PHX": [2001, 2014, 2018],
    "SAC": [2017, 2024],
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

# Additional mid-history splits for franchises that DID relocate/rename
# (so their team_history already has multiple rows from that move) but
# ALSO had a real color change before/after the move that never got its
# own boundary. split_era() is fully general now (it finds whichever row
# currently owns the target season, open or closed) so the same function
# handles this identically to NBA_SPLITS above - this is just a separate
# dict for documentation clarity, not a different code path.
NBA_RELOCATED_ADDITIONAL_SPLITS = {
    # Seattle SuperSonics: originally left as ONE row (1996-2008) with the
    # SPLIT CANDIDATE note deferring this exact split - now confirmed
    # wanted. Splits the Forest Green/Brick Red/Deep Yellow look (1996-
    # 2001) from the later Hunter Green look (2002-2008, pre-OKC).
    "SEA": [2002],
}

# WNBA splits. NOTE: WNBA uses seasonFormat 'single-year' (season number
# IS the calendar year - see wnba config.js), unlike NBA's season-ends-
# in-this-year convention. So unlike every NBA split above, these season
# numbers are used AS WRITTEN - no +1 needed.
WNBA_SPLITS = {
    # Connecticut Sun (wnba_0012): per TruColor, 2003-2015 was one
    # continuous Navy/Red/Yellow look (TruColor lists 2003-06, 2007-11,
    # and 2012-15 as separate rows but all three share identical hex -
    # not a real change, so treated as one era here). Orange was promoted
    # to primary for 2016-2020. 2021-present already matches config.js
    # (confirmed against the current WNBA config you pasted) and stays
    # NULL as usual.
    "CON": [2016, 2021],
    # Detroit Shock: previously left as ONE row (1998-2009, SPLIT
    # CANDIDATE flagged in seed_historical_colors.py) using the dominant
    # 2002-2009 palette for the whole span. Now confirmed via TruColor and
    # split for real.
    "DET": [2002],
    # Atlanta Dream: 3 real eras. 2020-present flagged separately below -
    # see NOTE in seed_historical_colors.py, config.js's current ATL entry
    # doesn't match this TruColor data.
    "ATL": [2016, 2020],
    # Las Vegas Aces: config.js's current (2024-present) entry already
    # matches TruColor exactly, only the 2018-2023 era needed splitting
    # out and coloring.
    "LVA": [2024],
    # LA Sparks: 2 real eras. Flag in seed_historical_colors.py -
    # config.js's current tertiary (black) doesn't match TruColor's white
    # for 2021-present.
    "LAS": [2021],
    # Minnesota Lynx: 3 real eras. Flag in seed_historical_colors.py -
    # config.js's current secondary (green) doesn't match TruColor's
    # Midnight Blue for 2018-present.
    "MIN": [2011, 2018],
    # NY Liberty: TruColor's 1997-2002 and 2003-2011 rows are the same 5
    # colors just reordered (plus one alternate uniform shade in the
    # later row) - treated as one continuous era through 2011, not a real
    # split, so only 2 splits needed here (2012, 2020) not 3.
    "NYL": [2012, 2020],
    # Phoenix Mercury: 4 real eras. 2026-present already matches
    # config.js exactly, no flag needed there.
    "PHX": [2011, 2015, 2026],
    # Seattle Storm: 3 real eras. Flag in seed_historical_colors.py -
    # config.js's current tertiary (blue) doesn't match TruColor's Bolt
    # Green for 2021-present.
    "SEA": [2016, 2021],
    # Washington Mystics: 2 real eras. 2011-present already matches
    # config.js exactly, no flag needed there.
    "WAS": [2011],
    # Charlotte Sting: folded franchise, 2 real eras. The later era
    # (2004-2006) is left NULL same as an active team's "current" era -
    # config.js's folded CHA entry already holds exactly those values
    # (its own header comment says folded-team entries represent "each
    # team's own final/most complete branding era"), so no separate
    # color entry is needed for that row.
    "CHA": [2004],
}


def load_db_module(league: str):
    path = os.path.join(os.path.dirname(__file__), league, "db.py")
    spec = importlib.util.spec_from_file_location(f"{league}_db", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def split_era(db, conn, code: str, new_start_season: int) -> bool:
    """Close whichever team_history row for `code` currently CONTAINS
    new_start_season at new_start_season - 1, and open a new one under
    the SAME code/name for new_start_season onward, inheriting whatever
    end_season the original row had (None/open, or a real season number
    if we're inserting a boundary into an already-closed historical
    row - e.g. adding a 2014 split inside an existing 2001-2017 row).
    General on purpose: this works identically whether the row being
    split is the team's current open era (a fresh split, same as before)
    or an already-closed historical era from a prior run (a correction
    discovered after the fact) - it always finds "the row that currently
    owns this season" and divides it, rather than assuming the open row
    is always the target. Returns False if this exact split already
    exists (idempotent - see NOTE below) or if no row currently spans
    new_start_season for this code at all."""
    team_id = db.resolve_team_id(conn, code)

    # Idempotency guard: if a row already starts exactly here, this split
    # was already applied - do nothing rather than re-splitting.
    already = conn.execute(
        "SELECT 1 FROM team_history WHERE team_id = ? AND start_season = ?",
        (team_id, new_start_season),
    ).fetchone()
    if already:
        return False

    # Find whichever row (open OR closed) currently spans this season -
    # NOT just the open one. This is what makes it safe to add a NEW
    # split point that lands inside a row an earlier run already closed.
    row = conn.execute(
        "SELECT start_season, end_season, name FROM team_history "
        "WHERE team_id = ? AND code = ? AND start_season < ? "
        "AND (end_season IS NULL OR end_season >= ?)",
        (team_id, code, new_start_season, new_start_season),
    ).fetchone()
    if not row:
        return False
    orig_start, orig_end, name = row

    conn.execute(
        "UPDATE team_history SET end_season = ? WHERE team_id = ? AND start_season = ?",
        (new_start_season - 1, team_id, orig_start),
    )
    conn.execute(
        "INSERT INTO team_history "
        "(team_id, code, name, start_season, end_season, "
        " primary_color, secondary_color, tertiary_color) "
        "VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL)",
        (team_id, code, name, new_start_season, orig_end),
    )
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--league", required=True, choices=["nba", "wnba"])
    args = p.parse_args()

    db = load_db_module(args.league)
    db_path = os.path.join(os.path.dirname(__file__), f"{args.league}_elo.db")
    if not os.path.exists(db_path):
        print(f"Expected top-level db at {db_path} - not found. Run this from DBs\\, "
              f"not from inside DBs\\{args.league}\\.")
        sys.exit(1)

    conn = db.connect(db_path)
    if args.league == "nba":
        splits = {**NBA_SPLITS, **NBA_RELOCATED_ADDITIONAL_SPLITS}
    else:
        splits = WNBA_SPLITS

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
