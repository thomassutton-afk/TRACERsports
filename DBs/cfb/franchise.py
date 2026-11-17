"""
Manage CFB program renames, conference realignment, and the rare
fold/revival reset.

Forked from NFL_Elo's franchise.py, but trimmed and reshaped for what
actually happens in college football: programs essentially never
physically relocate the way NFL/NBA franchises occasionally do, so
`relocate` (NFL_Elo's main command) is DROPPED entirely. Conference
realignment - a program switching conferences, which happens most
years and is genuinely common - gets a NEW `realign` command instead,
operating on `team_conference_history` (a table with no NFL_Elo
equivalent - see db.py's module docstring).

Every command below takes --current-code, not a team_id - team_id is a
permanent internal database key you should never need to know or type
(see franchise.py status if you ever want to look one up). You always
identify a program by whatever code it's CURRENTLY known by.

RENAME (a program's display name changes, code stays the same):

    python3 franchise.py rename --current-code southern-california --name "USC"

    Does NOT start a new team_history era - it just corrects the name
    on the currently-open one (e.g. fixing a placeholder name right
    after a program was registered, or a cosmetic full-name change).

REALIGNMENT (a program switches conferences - code/name usually don't
change; rating carries over unaffected, since conference membership
never feeds the rating math itself, only conf_game/div_game display
flags):

    python3 franchise.py realign --current-code oklahoma --conference SEC --season 2024

    Closes the program's currently-open team_conference_history era at
    --season minus one and opens a new one at --season under the new
    --conference (and optional --division, for conferences that still
    use them). This is a DISPLAY/classification change only - it does
    not touch `ratings` or trigger a rebuild, since conf_game/div_game
    flags are computed live from team_conference_history at rebuild
    time (see rebuild.py's `_annotate_conferences`), not stored
    statically. Run rebuild.py afterward if you want existing rating
    rows' conf_game/div_game flags to reflect the change immediately;
    otherwise it'll simply apply automatically the next time ratings
    get rebuilt for any other reason (e.g. the next add_season.py run).

FOLD + REVIVAL (a program discontinues football and later revives it
under the same code/brand - rating must NOT carry over; genuinely rare
in CFB, kept mainly for schema parity with NFL/NBA/WNBA):

    python3 franchise.py revive --current-code some-program --season 2010 --name "Some Program"

    Forces that team_id's rating to reset to the base rating (1500) at
    the start of the given season, ignoring whatever it ended on before
    it stopped playing. Starts a new team_history era at that season.

IMPORTANT: a program has to already be REGISTERED before you can run
any of these against it - i.e. it needs to have appeared in at least
one season file loaded via add_season.py already (which is what
actually creates its team_id in the first place).

After `rename` or `realign`, no rebuild is needed (neither affects the
rating math). After `revive`, ratings ARE rebuilt automatically, since
it forces a reset.
"""
import argparse
import os
import sys
import db
from rebuild import rebuild_ratings, VARIANTS

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cfb_elo.db")


def _resolve_or_die(conn, current_code: str) -> str:
    team_id = db.resolve_team_id(conn, current_code)
    row = conn.execute("SELECT 1 FROM teams WHERE team_id = ?", (team_id,)).fetchone()
    if not row:
        print(f"No team found for code '{current_code}'. It needs to have appeared in at "
              f"least one season file loaded via add_season.py first - franchise.py can't "
              f"operate on a program that doesn't exist yet. Run 'franchise.py status' to see "
              f"every code/team_id currently known.")
        sys.exit(1)
    return team_id


def realign(conn, current_code: str, conference: str, season: int, division: str | None = None):
    """Move a program to a new conference starting `season`. See this
    module's docstring - this is a classification/display change only,
    computed live from team_conference_history at rebuild time, so it
    never touches `ratings` and needs no rebuild afterward. Uses
    db.set_conference_era(), which is safe to call even if this ends up
    being run out of chronological order relative to other seasons
    already on file for this team (see that function's docstring in
    db.py) - a plain close-then-insert would collide with or corrupt
    existing rows in that case."""
    team_id = _resolve_or_die(conn, current_code)
    result = db.set_conference_era(conn, team_id, conference, season, division=division)
    conn.commit()
    if result == "unchanged":
        print(f"'{current_code}' (team_id '{team_id}') already shows {conference}"
              + (f" ({division} division)" if division else "") + f" for {season} - no change made.")
        return
    print(f"'{current_code}' (team_id '{team_id}') moves to {conference}"
          + (f" ({division} division)" if division else "") + f" starting {season}.")
    print(f"team_conference_history: {result} the era starting {season}. No rebuild needed - "
          f"conf_game/div_game are computed live from this table the next time ratings are "
          f"rebuilt for any reason.")


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
    for variant in VARIANTS:
        rebuild_ratings(conn, variant)
    print(f"'{current_code}' (team_id '{team_id}') will start {season} at the base rating "
          f"(1500), ignoring its pre-fold history.")
    if name:
        print(f"Renamed to '{name}'.")
    print(f"Ratings rebuilt ({', '.join(VARIANTS)}).")


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
    print("\nConference history (team_id: conference/division valid seasons):")
    rows = conn.execute(
        "SELECT team_id, conference, division, start_season, end_season "
        "FROM team_conference_history ORDER BY team_id, start_season"
    ).fetchall()
    if not rows:
        print("  (none)")
    for tid, conf, div, start, end in rows:
        end_label = end if end is not None else "present"
        label = f"{conf} ({div})" if div else conf
        print(f"  {tid:10s} {label:24s} {start}-{end_label}")
    print("\nForced resets (team_id, season -> base rating):")
    rows = conn.execute("SELECT team_id, season, note FROM franchise_resets ORDER BY season").fetchall()
    if not rows:
        print("  (none)")
    for tid, season, note in rows:
        print(f"  {tid:10s} {season}  {note or ''}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    rg = sub.add_parser("realign")
    rg.add_argument("--current-code", required=True, help="the code this program is CURRENTLY known by")
    rg.add_argument("--conference", required=True, help="new conference, e.g. 'SEC', 'Big Ten'")
    rg.add_argument("--division", help="new division within that conference, if it uses one "
                     "(most conferences dropped divisions in the 2020s realignment wave - "
                     "omit for those)")
    rg.add_argument("--season", type=int, required=True,
                     help="season the move takes effect (closes the old conference era at "
                          "season-1 and opens a new one at season)")

    rn = sub.add_parser("rename")
    rn.add_argument("--current-code", required=True, help="the code this program is CURRENTLY known by")
    rn.add_argument("--name", required=True)

    rv = sub.add_parser("revive")
    rv.add_argument("--current-code", required=True, help="the code this program is CURRENTLY known by")
    rv.add_argument("--season", type=int, required=True)
    rv.add_argument("--name", help="new display name")

    sub.add_parser("status")

    args = p.parse_args()
    conn = db.connect(DB_PATH)

    if args.cmd == "realign":
        realign(conn, args.current_code, args.conference, args.season, division=args.division)
    elif args.cmd == "rename":
        rename(conn, args.current_code, args.name)
    elif args.cmd == "revive":
        revive(conn, args.current_code, args.season, args.name)
    elif args.cmd == "status":
        list_status(conn)


if __name__ == "__main__":
    main()
