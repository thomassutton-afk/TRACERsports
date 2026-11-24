"""
load_conference_membership.py

Loads one season's conference-standings export from Sports-Reference
(the "School, Conf, W-L, ..." table - only School and Conf actually
matter here) into `team_conference_history` AND `fbs_membership`. This
is the missing piece flagged in engine.py/rebuild.py's docstrings:
until this has been run for a season, every game that season scores as
"not a conference/division game" for conf_game/div_game purposes, AND
- more importantly now - every team that season is treated as an FCS
opponent (fixed rating, no persisted rating row) by engine.py, since
fbs_membership simply has no rows for it yet. See FBS MEMBERSHIP below.

Usage:
    python3 load_conference_membership.py standings_2025.csv --season 2025

WHAT THIS DOES:
  - Reads School + Conf for every row.
  - Splits a combined "Sun Belt (East)" / "Sun Belt (West)"-style Conf
    value into conference="Sun Belt", division="East"/"West". A plain
    conference name with no parenthetical stays as conference=Conf,
    division=None.
  - Resolves each School name to a team_id by slugifying it the SAME
    way normalize_sr_games.py does, then looking it up through the
    existing team_aliases table. Sports-Reference's standings exports
    use shorter common names ("BYU", "USC", "Ole Miss", "UTEP", "LSU",
    "SMU", "Pitt", "UCF", "UAB", "UTSA") that DON'T match the fuller
    formal names its schedule/score exports use ("Brigham Young",
    "Southern California", "Mississippi", "Texas-El Paso", "Louisiana
    State", "Southern Methodist", "Pittsburgh", "Central Florida",
    "Alabama-Birmingham", "Texas-San Antonio") - KNOWN_ALIASES below
    seeds the mismatches identified so far. Anything that STILL
    doesn't resolve is written to
    reports/unresolved_conference_teams_{season}.csv instead of being
    silently treated as a new team - resolve_team_id() only ever
    follows an EXISTING alias (see db.py), it never registers one, so
    an unresolved name is caught here rather than accidentally
    forking one real program into two different database rows. Review
    that file each time it's non-empty and either add an entry to
    KNOWN_ALIASES or register a real alias via db.add_alias() before
    re-running. This check now applies to EVERY school in the file,
    independents included - an unresolved independent used to be
    silently skipped entirely before it ever reached the resolution
    check, which was a real gap.

FBS MEMBERSHIP - every school that resolves gets an fbs_membership row
for this season, INCLUDING independents (Conf="Ind"). This is
deliberately separate from the conference-era logic below: an
independent still needs to be recognized as FBS (so it isn't treated
as a fixed-rating FCS opponent), even though it correctly gets NO
team_conference_history row.

CONFERENCE ERA - "Ind" (independent) gets NO team_conference_history
row at all. This is deliberate: two independents playing each other
must NOT read as a conference game, which a literal
conference="Independent" placeholder string would cause (both teams
would share that string and false-positive as "same conference"). No
row at all is what makes db.conference_for_season() correctly return
None for them - see engine.py's module docstring on that convention.
For every other school: uses db.set_conference_era(), which is safe to
call in ANY order (not just chronological) - see its docstring in
db.py.

REBUILD - unlike before FCS handling existed, this NOW triggers a full
ratings rebuild (both variants) after loading, since fbs_membership
directly changes which side of a game gets a real persisted rating -
this is no longer a display-only table the way team_conference_history
alone was. Expect this script to take noticeably longer than it used
to.

ORDERING STILL MATTERS: run this AFTER add_season.py has loaded a
season's games, same as before. But now, until you run THIS script for
a given season, every team in it looks FCS (fixed rating, not
persisted) to the rating engine - not just "not a conference game."
Don't be alarmed if a freshly add_season.py-loaded season's standings
look strange before you've run this for it; that's expected and gets
corrected by the rebuild this script triggers.
"""
import argparse
import os
import re
import sys

import pandas as pd

import db
from rebuild import rebuild_ratings, VARIANTS

# Seeded from known Sports-Reference naming discrepancies between its
# standings/conference exports (shorter common names) and its
# schedule/score exports (fuller formal names - what
# normalize_sr_games.py actually slugifies into team codes). Extend
# this as new mismatches turn up in
# reports/unresolved_conference_teams_*.csv.
KNOWN_ALIASES = {
    "byu": "brigham-young",
    "usc": "southern-california",
    "ole-miss": "mississippi",
    "utep": "texas-el-paso",
    "lsu": "louisiana-state",
    "smu": "southern-methodist",
    "pitt": "pittsburgh",
    "ucf": "central-florida",
    "unlv": "nevada-las-vegas",
    "uconn": "connecticut",
    "umass": "massachusetts",
    "uab": "alabama-birmingham",
    "utsa": "texas-san-antonio",
}

CONF_DIV_RE = re.compile(r"^(.*?)\s*\(([^)]+)\)\s*$")


def slugify(name: str) -> str:
    """Same slugification as normalize_sr_games.py - must stay in sync
    with that script, since this is matching against codes it produced."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def split_conf_div(raw: str) -> tuple[str, "str | None"]:
    """'Sun Belt (East)' -> ('Sun Belt', 'East'); 'ACC' -> ('ACC', None)."""
    m = CONF_DIV_RE.match(raw.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return raw.strip(), None


def _find_header_row(path: str) -> int:
    """Sports-Reference's raw export has a citation-request preamble
    (and sometimes blank lines, and multi-row headers) before the real
    header row - scan for the actual 'Rk,School,Conf,...' line."""
    with open(path, encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if line.startswith("Rk,School,Conf"):
                return i
    return 0


def load(conn, path: str, season: int) -> tuple[int, int, list[tuple[str, str]]]:
    header_row = _find_header_row(path)
    df = pd.read_csv(path, skiprows=header_row)
    df = df[df["School"].notna() & df["Conf"].notna()].copy()
    df = df[df["School"] != "School"].copy()

    unresolved = []
    updated = 0
    unchanged = 0
    for _, r in df.iterrows():
        school = str(r["School"]).strip()
        conf_raw = str(r["Conf"]).strip()
        is_independent = conf_raw in ("Ind", "Independent", "", "nan")

        slug = slugify(school)
        slug = KNOWN_ALIASES.get(slug, slug)
        team_id = db.resolve_team_id(conn, slug)
        exists = conn.execute("SELECT 1 FROM teams WHERE team_id = ?", (team_id,)).fetchone()
        if not exists:
            unresolved.append((school, slug))
            continue

        # FBS membership is recorded for EVERY resolved school this
        # season, independents included - see FBS MEMBERSHIP above.
        db.set_fbs_membership(conn, team_id, season)

        if is_independent:
            continue  # no team_conference_history row - see CONFERENCE ERA above

        conference, division = split_conf_div(conf_raw)
        result = db.set_conference_era(conn, team_id, conference, season, division=division)
        if result == "unchanged":
            unchanged += 1
        else:
            updated += 1

    conn.commit()
    return updated, unchanged, unresolved


def main():
    p = argparse.ArgumentParser()
    p.add_argument("path", help="raw Sports-Reference standings/conference CSV export")
    p.add_argument("--season", type=int, required=True)
    p.add_argument("--db", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "cfb_elo.db"))
    args = p.parse_args()

    if not os.path.exists(args.path):
        print(f"File not found: {args.path}")
        sys.exit(1)

    conn = db.connect(args.db)
    updated, unchanged, unresolved = load(conn, args.path, args.season)

    print(f"Season {args.season}: {updated} team(s) got a new/changed conference era, "
          f"{unchanged} already matched their prior era and were left alone.")
    if unresolved:
        os.makedirs("reports", exist_ok=True)
        out_path = f"reports/unresolved_conference_teams_{args.season}.csv"
        pd.DataFrame(unresolved, columns=["School", "AttemptedSlug"]).to_csv(out_path, index=False)
        print(f"WARNING: {len(unresolved)} school(s) could not be matched to an existing team - "
              f"wrote {out_path}. Each of these needs to already exist (via an add_season.py "
              f"load of a season file that includes them) AND either slugify to a matching code "
              f"on its own or get an entry added to KNOWN_ALIASES in this script, before its "
              f"conference AND its FBS status can be recorded.")

    print("Rebuilding ratings so FBS/FCS classification takes effect...")
    for variant in VARIANTS:
        rebuild_ratings(conn, variant)
    print(f"Ratings rebuilt ({', '.join(VARIANTS)}).")


if __name__ == "__main__":
    main()

