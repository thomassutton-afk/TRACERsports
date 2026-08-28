import os
"""
Manage franchise relocations and fold/revival resets.

Every command below takes --current-code, not a team_id - team_id is a
permanent internal database key you should never need to know or type
(see franchise.py status if you ever want to look one up). You always
identify a team by whatever code it's CURRENTLY known by.

RELOCATION (same franchise, new city - rating carries over):

    python3 franchise.py relocate --current-code SD --name "Los Angeles Chargers" --season 2017

    Most real relocations do NOT change the code used in source files
    (the Chargers' move to LA stayed coded "SD" throughout - that's
    this dataset's own convention, matching how Continelo tags every
    era of a franchise under one constant code). This closes the old
    team_history era at --season minus one and opens a new one at
    --season, under the SAME code, with the new display name - so old
    seasons still show "San Diego Chargers" and new ones show "Los
    Angeles Chargers", even though nothing in the source files or the
    alias table changes.

    Pass --alias only on the rarer occasion a relocation genuinely
    changes the code itself:

    python3 franchise.py relocate --current-code OLD --alias NEW --name "New City Team" --season 2030

    This additionally registers NEW as an alias for the same team_id,
    so future files using the new code merge into this franchise's
    existing history instead of registering a brand new team.

    You do NOT need this if a franchise's code stays the same but its
    name/city changes cosmetically - for that just rename it:

    python3 franchise.py rename --current-code WAS --name "Washington Football Team"

    A plain rename does NOT start a new team_history era - it just
    corrects the name on the currently-open one (e.g. fixing a
    placeholder name right after a team was registered).

FOLD + REVIVAL (a team folds, and the same code/brand is reused later
for what is functionally a new franchise - rating must NOT carry over):

    python3 franchise.py revive --current-code CLE --season 1999 --name "Cleveland Browns"

    This forces that team_id's rating to reset to the base rating
    (1500) at the start of the 1999 season, ignoring whatever it ended
    on before it folded (the actual Cleveland Browns case: the NFL
    ruled the Browns' history/records stayed in Cleveland when the
    original franchise moved to Baltimore in 1996, so the 1999 "CLE"
    team is treated as a fresh expansion franchise reusing the name -
    not a continuation of the team that moved). Starts a new
    team_history era at that season. Only needed if the SAME code is
    reused - a genuinely new team_id (e.g. an expansion team with a
    fresh abbreviation, like Houston in 2002) already starts at 1500
    automatically and needs no action here.

FOLDING itself needs no action - a team just stops appearing in future
season files. Nothing in the database needs to change when a team
folds; you only need `revive` if/when it comes back under the same code.

IMPORTANT: a team has to already be REGISTERED before you can run any
of these against it - i.e. it needs to have appeared in at least one
season file loaded via add_season.py already (which is what actually
creates its team_id in the first place), UNLESS it was pre-seeded via
seed_franchise_history.py - see TEMPLATE.md section 8. NFL's full
relocation history (1996-present) is already known, so it should be
pre-seeded rather than relocated live between season loads - reach for
this script mainly for something genuinely new going forward (a future
relocation/expansion not yet in that seed data).

After any of these, ratings are rebuilt automatically (relocate/rename
don't affect the math, only display - but revive does, since it forces
a reset).
"""
import argparse
import sys
import db
from rebuild import rebuild_ratings

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "nfl_elo.db"
)


def _resolve_or_die(conn, current_code: str) -> str:
    team_id = db.resolve_team_id(conn, current_code)
    row = conn.execute("SELECT 1 FROM teams WHERE team_id = ?", (team_id,)).fetchone()
    if not row:
        print(f"No team found for code '{current_code}'. It needs to have appeared in at "
              f"least one season file loaded via add_season.py first, or been pre-seeded via "
              f"seed_franchise_history.py - franchise.py can't relocate a team that doesn't "
              f"exist yet. Run 'franchise.py status' to see every code/team_id currently known.")
        sys.exit(1)
    return team_id


def relocate(conn, current_code: str, name: str | None, season: int | None, alias: str | None = None):
    team_id = _resolve_or_die(conn, current_code)
    new_code = alias or current_code
    if alias:
        db.add_alias(conn, alias, team_id, note=f"relocation alias for {team_id}")
    display_name = name
    if not display_name:
        row = conn.execute("SELECT team_name FROM teams WHERE team_id = ?", (team_id,)).fetchone()
        display_name = row[0] if row else team_id
    if name:
        db.upsert_team(conn, team_id, name)
    if season is not None:
        db.close_team_history(conn, team_id, season - 1)
        db.add_team_history(conn, team_id, new_code, display_name, season)
    conn.commit()
    if alias:
        print(f"Registered alias '{alias}' -> team_id '{team_id}' (previously '{current_code}')"
              + (f", renamed to '{name}'." if name else "."))
        print("Future files using this alias will be merged into this franchise's history.")
    else:
        print(f"'{current_code}' (team_id '{team_id}')"
              + (f" renamed to '{name}'." if name else " starting a new era with no name change."))
    if season is not None:
        print(f"team_history: closed prior era at {season - 1}, opened '{new_code}' / "
              f"'{display_name}' starting {season}.")
    else:
        print("No --season given, so team_history was NOT updated - old seasons will still "
              "display this franchise's most recent era. Re-run with --season to fix that.")


def rename(conn, current_code: str, name: str):
    team_id = _resolve_or_die(conn, current_code)
    db.upsert_team(conn, team_id, name)
    updated = db.rename_current_history(conn, team_id, name)
    conn.commit()
    print(f"Renamed '{current_code}' (team_id '{team_id}') to '{name}'.")
    if not updated:
        print("Note: no currently-open team_history entry existed for this team_id "
              "(it predates franchise-history tracking) - only teams.team_name was updated.")


def revive(conn, current_code: str, season: int, name: str | None):
    team_id = _resolve_or_die(conn, current_code)
    db.add_reset(conn, team_id, season, note=f"revived for {season} season, prior history reset")
    display_name = name
    if not display_name:
        row = conn.execute("SELECT team_name FROM teams WHERE team_id = ?", (team_id,)).fetchone()
        display_name = row[0] if row else team_id
    if name:
        db.upsert_team(conn, team_id, name)
    db.close_team_history(conn, team_id, season - 1)
    row = conn.execute(
        "SELECT code FROM team_history WHERE team_id = ? ORDER BY start_season DESC LIMIT 1",
        (team_id,),
    ).fetchone()
    code = row[0] if row else current_code
    db.add_team_history(conn, team_id, code, display_name, season)
    conn.commit()
    rebuild_ratings(conn)
    print(f"'{current_code}' (team_id '{team_id}') will start {season} at the base rating "
          f"(1500), ignoring its pre-fold history.")
    if name:
        print(f"Renamed to '{name}'.")
    print("Ratings rebuilt.")


def list_status(conn):
    print("Teams:")
    for tid, name in conn.execute("SELECT team_id, team_name FROM teams ORDER BY team_id"):
        print(f"  {tid:10s} {name}")
    print("\nAliases (source-file code -> canonical team_id):")
    rows = conn.execute("SELECT alias, team_id, note FROM team_aliases").fetchall()
    if not rows:
        print("  (none)")
    for alias, tid, note in rows:
        print(f"  {alias:6s} -> {tid:10s} {note or ''}")
    print("\nEra history (team_id: code/name valid seasons):")
    rows = conn.execute(
        "SELECT team_id, code, name, start_season, end_season FROM team_history "
        "ORDER BY team_id, start_season"
    ).fetchall()
    if not rows:
        print("  (none)")
    for tid, code, name, start, end in rows:
        end_label = end if end is not None else "present"
        print(f"  {tid:10s} {code:6s} {name:24s} {start}-{end_label}")
    print("\nForced resets (team_id, season -> base rating):")
    rows = conn.execute("SELECT team_id, season, note FROM franchise_resets ORDER BY season").fetchall()
    if not rows:
        print("  (none)")
    for tid, season, note in rows:
        print(f"  {tid:10s} {season}  {note or ''}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("relocate")
    r.add_argument("--current-code", required=True, help="the code this team is CURRENTLY known by")
    r.add_argument("--alias", help="new team code, ONLY if the relocation actually changes the "
                    "code used in source files - most real relocations don't (e.g. the Chargers' "
                    "move stayed coded 'SD' throughout); omit this and the new era just keeps "
                    "using --current-code")
    r.add_argument("--name", help="new display name")
    r.add_argument("--season", type=int,
                    help="season the relocation takes effect (closes the old team_history era "
                         "at season-1 and opens a new one at season; omit to skip history tracking)")

    rn = sub.add_parser("rename")
    rn.add_argument("--current-code", required=True, help="the code this team is CURRENTLY known by")
    rn.add_argument("--name", required=True)

    rv = sub.add_parser("revive")
    rv.add_argument("--current-code", required=True, help="the code this team is CURRENTLY known by")
    rv.add_argument("--season", type=int, required=True)
    rv.add_argument("--name", help="new display name")

    sub.add_parser("status")

    args = p.parse_args()
    conn = db.connect(DB_PATH)

    if args.cmd == "relocate":
        relocate(conn, args.current_code, args.name, args.season, alias=args.alias)
    elif args.cmd == "rename":
        rename(conn, args.current_code, args.name)
    elif args.cmd == "revive":
        revive(conn, args.current_code, args.season, args.name)
    elif args.cmd == "status":
        list_status(conn)


if __name__ == "__main__":
    main()
