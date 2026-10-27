"""SQLite storage for the College Football (CFB) Elo model.

Forked from NFL_Elo's db.py - same team-identity model, same core
schema shape. Differences from the NFL version are called out below;
everything not mentioned works exactly like NFL_Elo.

TEAM IDENTITY MODEL
--------------------
`teams.team_id` is a permanent synthetic ID (e.g. "cfb_0001") assigned
once to a program and never changed. It carries no meaning of its own -
it's just a stable peg for `games` and `ratings` to reference.

Every human-readable code a program has ever played under - including
whatever it currently uses - lives in `team_aliases`, resolved to that
permanent ID via `resolve_team_id`. No single code is privileged as
"the real one." Unlike NFL, CFB has no standard stable abbreviation
source, so `add_season.py`'s normalizer derives a code by slugifying
the team's full name as it appears in source data (e.g. "Southern
California" -> "southern-california", "Miami (FL)" -> "miami-fl").
A genuine name change (not a code change - see CFB-SPECIFIC ADDITIONS
below) still goes through `team_aliases`/`team_history` the same way
an NFL relocation does.

`team_history` tracks which code/name a program used during which
seasons, so you can ask "what was this program called in 1996?" vs
"in 2010?" even though both are the same team_id. `teams.team_name`
remains a simple current-name fallback for convenience/older callers.

CFB-SPECIFIC SCHEMA ADDITIONS
------------------------------
- `games`/`schedule` carry `home_code`/`away_code` (the slugified
  team code) alongside `home_team`/`away_team` (the permanent
  synthetic team_id), same reasoning as NFL_Elo: keeps engine.py able
  to work off game data without a database round-trip.
- `games`/`schedule` also carry nullable `home_ap_rank`/`away_ap_rank`
  (the AP poll rank at kickoff, parsed from source data like
  "(11) Penn State"). Display-only - the Elo engine never reads these.
- `ratings` carries `conf_game`/`div_game` (whether this was a
  conference/division matchup) and `t` (ties), on top of the same
  columns NBA/WNBA use - same as NFL_Elo. Note division games are far
  less common in CFB than NFL (most conferences dropped divisions in
  the 2020s realignment wave); `div_game` will legitimately be 0/NULL
  for most games and most conferences.
- NEW: `team_conference_history` tracks which conference a program
  belonged to during which seasons (e.g. Oklahoma: Big 12 through
  2023, SEC from 2024). This is DELIBERATELY separate from
  `team_history` - conference realignment is not a relocation or
  rebrand, a program's code/name usually don't change when it
  switches conferences, so this needed its own era-scoped table
  rather than overloading team_history's meaning.
- No `franchise.py` relocate/revive equivalent - CFB programs don't
  physically relocate or fold-and-revive the way NFL/NBA franchises
  occasionally do. See franchise.py's module docstring for what
  replaced those commands.
"""
from __future__ import annotations
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    team_id   TEXT PRIMARY KEY,
    team_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS games (
    game_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL,
    season        INTEGER NOT NULL,
    type          TEXT NOT NULL CHECK(type IN ('R','P')),
    round         TEXT,
    home_team     TEXT NOT NULL REFERENCES teams(team_id),
    away_team     TEXT NOT NULL REFERENCES teams(team_id),
    home_code     TEXT NOT NULL,
    away_code     TEXT NOT NULL,
    home_pts      INTEGER NOT NULL,
    away_pts      INTEGER NOT NULL,
    ot            INTEGER NOT NULL DEFAULT 0,
    neutral       INTEGER NOT NULL DEFAULT 0,
    home_ap_rank  INTEGER,
    away_ap_rank  INTEGER
);

-- A plain UNIQUE constraint treats every NULL `round` as distinct from
-- every other NULL, so regular-season games (round IS NULL) would
-- never be deduplicated. IFNULL(round, 'RS') makes NULLs compare equal
-- to each other for uniqueness purposes.
CREATE UNIQUE INDEX IF NOT EXISTS idx_games_unique
    ON games(date, home_team, away_team, type, IFNULL(round, 'RS'));

-- Unplayed games live here, NEVER in `games`. This is deliberate: the
-- rating engine (rebuild_ratings) only ever reads from `games`, and
-- has no code path that touches `schedule` at all. A game with no
-- score literally cannot reach the rating math - there's no "0-0
-- tie" failure mode possible, because there's no score column here
-- to default to 0.
CREATE TABLE IF NOT EXISTS schedule (
    schedule_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    date          TEXT NOT NULL,
    season        INTEGER NOT NULL,
    type          TEXT NOT NULL CHECK(type IN ('R','P')),
    round         TEXT,
    home_team     TEXT NOT NULL REFERENCES teams(team_id),
    away_team     TEXT NOT NULL REFERENCES teams(team_id),
    home_code     TEXT NOT NULL,
    away_code     TEXT NOT NULL,
    neutral       INTEGER NOT NULL DEFAULT 0,
    home_ap_rank  INTEGER,
    away_ap_rank  INTEGER
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_unique
    ON schedule(date, home_team, away_team, type, IFNULL(round, 'RS'));

-- Unplayed-game predictions, one row per schedule entry per VARIANT
-- (e.g. 'echo', 'pulse') - Pulse's predicted winner genuinely differs
-- from Echo's once ratings diverge, so variant is part of the
-- identity here, not just a label. Written by add_season.py's
-- write_schedule_predictions() after each rebuild_ratings(variant)
-- pass; display-only, never read by the rating engine itself.
CREATE TABLE IF NOT EXISTS schedule_predictions (
    schedule_id        INTEGER NOT NULL REFERENCES schedule(schedule_id),
    variant             TEXT NOT NULL,
    expected_win_home   REAL,
    expected_win_away   REAL,
    home_days_off       INTEGER,
    away_days_off       INTEGER,
    rest_adj            REAL,
    PRIMARY KEY (schedule_id, variant)
);

-- Monte Carlo season projection (simulate_season.py), one row per team
-- per season per VARIANT - Pulse's projected win totals genuinely
-- differ from Echo's once ratings diverge, same reasoning as ratings
-- below. Fully replaced each time it's recomputed (see
-- save_season_projection below) - this is always a fresh snapshot from
-- current ratings, never an incremental update, so there's no
-- reasonable way to "diff" an old projection against a new one, and no
-- reason to try. computed_at records when a given snapshot was made,
-- mainly so the site can show "as of" freshness if useful later.
CREATE TABLE IF NOT EXISTS season_projections (
    season             INTEGER NOT NULL,
    team_id            TEXT NOT NULL,
    variant            TEXT NOT NULL,
    avg_wins           REAL,
    p10_wins           INTEGER,
    median_wins        INTEGER,
    p90_wins           INTEGER,
    avg_rating         REAL,
    prob_finish_first  REAL,
    trials             INTEGER,
    remaining_games    INTEGER,
    computed_at        TEXT,
    PRIMARY KEY (season, team_id, variant)
);

-- One row per team per game per VARIANT (e.g. 'echo', 'pulse') - the
-- same game produces different ratings/rating_change/etc depending on
-- which variant computed it, so variant is part of the identity here,
-- not just a label. rebuild_ratings() clears and rewrites one variant
-- at a time (db.clear_ratings(conn, variant)), never touching another
-- variant's rows in the same call.
CREATE TABLE IF NOT EXISTS ratings (
    game_id       INTEGER NOT NULL REFERENCES games(game_id),
    team          TEXT NOT NULL,
    variant       TEXT NOT NULL,
    opponent      TEXT NOT NULL,
    home_away     TEXT NOT NULL,
    date          TEXT NOT NULL,
    season        INTEGER NOT NULL,
    type          TEXT NOT NULL,
    round         TEXT,
    conf_game     INTEGER,
    div_game      INTEGER,
    games_played  INTEGER,
    days_off      INTEGER,
    opp_days_off  INTEGER,
    rest_adj      REAL,
    pre_rate      REAL,
    opp_pre_rate  REAL,
    expected_win  REAL,
    points_for    INTEGER,
    points_against INTEGER,
    ot            INTEGER,
    mov           INTEGER,
    result        REAL,
    accuracy      INTEGER,
    test          REAL,
    brier         REAL,
    mov_mult      REAL,
    po_mult       REAL,
    k             REAL,
    keff          REAL,
    rating_change REAL,
    post_rate     REAL,
    w REAL, l REAL, t REAL, r1w REAL, r1l REAL, r2w REAL, r2l REAL,
    r3w REAL, r3l REAL, fw REAL, fl REAL,
    PRIMARY KEY (game_id, team, variant)
);

CREATE TABLE IF NOT EXISTS params (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Every code a franchise has ever used (current or historical, plus
-- alternate codes from other data sources) maps here to its permanent
-- team_id. Loaders resolve raw source-file codes through this table; a
-- code with no alias yet is treated as a brand new franchise (see
-- register_new_team).
CREATE TABLE IF NOT EXISTS team_aliases (
    alias      TEXT PRIMARY KEY,
    team_id    TEXT NOT NULL REFERENCES teams(team_id),
    note       TEXT
);

-- Era-scoped code/name for a franchise, so games display under the
-- name/code the team actually used at the time (e.g. Houston Oilers
-- in 1996, Tennessee Titans in 2010 - same team_id). end_season IS
-- NULL means "still current."
CREATE TABLE IF NOT EXISTS team_history (
    team_id      TEXT NOT NULL REFERENCES teams(team_id),
    code         TEXT NOT NULL,
    name         TEXT NOT NULL,
    start_season INTEGER NOT NULL,
    end_season   INTEGER,
    PRIMARY KEY (team_id, start_season)
);

-- Forced resets: a team_id that folded and was later revived (same
-- code/brand reused for what is functionally a new franchise) needs
-- its rating wiped back to the base rating at the start of the given
-- season, instead of the normal season-to-season regression from its
-- old final rating. Genuinely rare in CFB (a program dropping to FCS
-- or discontinuing football entirely and later reviving it under the
-- same brand) - kept for schema parity with NFL/NBA/WNBA in case one
-- ever needs it.
CREATE TABLE IF NOT EXISTS franchise_resets (
    team_id TEXT NOT NULL,
    season  INTEGER NOT NULL,
    note    TEXT,
    PRIMARY KEY (team_id, season)
);

-- CFB-SPECIFIC: era-scoped conference membership. Deliberately separate
-- from `team_history` - a program switching conferences (Oklahoma:
-- Big 12 -> SEC in 2024) is NOT a relocation or rebrand, its code/name
-- usually don't change, so this needed its own table rather than
-- overloading team_history's meaning. end_season IS NULL means "still
-- current." A program can have no row at all for a season it was an
-- independent (Notre Dame, historically; UMass at various points) -
-- engine.py treats "no conference on file for this team this season"
-- as neither a conference nor a division game, same as playing an
-- FCS opponent with no conference row.
CREATE TABLE IF NOT EXISTS team_conference_history (
    team_id      TEXT NOT NULL REFERENCES teams(team_id),
    conference   TEXT NOT NULL,
    division     TEXT,
    start_season INTEGER NOT NULL,
    end_season   INTEGER,
    PRIMARY KEY (team_id, start_season)
);

-- CFB-SPECIFIC: which programs are FBS in which season. Populated by
-- load_conference_membership.py for EVERY school row in that season's
-- Standings export - including independents (Conf='Ind'), which get
-- a row here even though they deliberately get NO row in
-- team_conference_history (see that table's comment above - an
-- "Independent" conference string would falsely match two
-- independents against each other as a conference game). This table
-- is what actually answers "is this team FBS this season" - a team
-- with no team_conference_history era could still be a real FBS
-- independent, so that table alone can't be used for this check.
-- A team_id with NO row here for a given season is treated as an FCS
-- (or lower-division) opponent by engine.py - see its module
-- docstring on FCS HANDLING. IMPORTANT: this only becomes accurate
-- for a season once load_conference_membership.py has actually been
-- run for it - a season loaded via add_season.py but not yet run
-- through the conference loader will have EVERY team look FCS until
-- that catches up, since this table simply has no rows for it yet.
CREATE TABLE IF NOT EXISTS fbs_membership (
    team_id TEXT NOT NULL REFERENCES teams(team_id),
    season  INTEGER NOT NULL,
    PRIMARY KEY (team_id, season)
);

-- CFB-SPECIFIC: which conferences count as "power" vs "midmajor" in a
-- given season - used ONLY for bucketing FBS INDEPENDENTS (who have
-- no literal conference of their own) into a peer-group average for
-- SEASON-ENTRY purposes (see engine.py's module docstring). Every
-- conference NOT covered by a row here defaults to "midmajor" - see
-- db.py's tier_for_conference(). end_season NULL means "still power
-- as of the present."
CREATE TABLE IF NOT EXISTS conference_tier (
    conference   TEXT NOT NULL,
    start_season INTEGER NOT NULL,
    end_season   INTEGER,
    tier         TEXT NOT NULL CHECK(tier IN ('power', 'midmajor')),
    PRIMARY KEY (conference, start_season)
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SCHEMA)
    _migrate(conn)
    # Auto-seed the power-conference eras exactly once - harmless to
    # check on every connect() (a single indexed lookup), and means no
    # one has to remember a separate one-time setup step before
    # SEASON-ENTRY math can work. seed_conference_tiers() itself is
    # idempotent (INSERT OR REPLACE), so this is safe even if it's
    # somehow already been seeded.
    if not conn.execute("SELECT 1 FROM conference_tier LIMIT 1").fetchone():
        seed_conference_tiers(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Upgrade an older database file in place, for schema additions
    made after it was first created. Same pattern NBA/WNBA's db.py
    already uses for this exact upgrade.

    Pulse variant support: `ratings` needs a `variant` column folded
    into its primary key. It's 100% derived/disposable - always fully
    wiped and recomputed from `games` by rebuild_ratings(), never
    hand-edited or treated as a source of truth - so on an old .db file
    that predates variants (i.e. any real nfl_elo.db from before this
    retrofit), the safe fix is just to drop and recreate it with the
    new schema. The very next add_season.py run repopulates it for
    every variant, same as any other rebuild.

    `schedule_predictions` and `season_projections` are brand new
    tables (didn't exist at all pre-retrofit), so CREATE TABLE IF NOT
    EXISTS in SCHEMA above already creates them correctly on an old
    file - no migration step needed for those two."""
    ratings_cols = {row[1] for row in conn.execute("PRAGMA table_info(ratings)")}
    if ratings_cols and "variant" not in ratings_cols:
        conn.execute("DROP TABLE ratings")
        conn.executescript(SCHEMA)
        conn.commit()

    # Era-specific colors: nullable by design, same as NBA/WNBA. A row
    # with no colors set just means nobody's populated that era's
    # colors yet - callers fall back to the current identity's colors
    # (lib/sports/nfl/config.js), not an error. Kept on team_history
    # itself (not a separate lookup keyed by code) because code alone
    # isn't a stable key across relocations. These columns exist
    # regardless of whether colors have actually been populated yet -
    # export_to_supabase.py's build_team_history() queries them
    # unconditionally for every league, so they need to exist even
    # while still NULL.
    history_cols = {row[1] for row in conn.execute("PRAGMA table_info(team_history)")}
    for col in ("primary_color", "secondary_color", "tertiary_color"):
        if col not in history_cols:
            conn.execute(f"ALTER TABLE team_history ADD COLUMN {col} TEXT")

    # CFB-SPECIFIC: AP rank columns, added after initial schema design.
    # Nullable/display-only (see module docstring) - an old db file just
    # gets NULLs for every existing row until re-loaded from a source
    # file that carries rank data.
    for table in ("games", "schedule"):
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for col in ("home_ap_rank", "away_ap_rank"):
            if col not in cols:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} INTEGER")
    conn.commit()


# --------------------------------------------------------------------
# Franchise identity: synthetic IDs, aliases, era-scoped history
# --------------------------------------------------------------------

def next_team_id(conn: sqlite3.Connection) -> str:
    """Generate the next sequential permanent program ID, e.g.
    'cfb_0001'. Once assigned, a team_id never changes - conference
    moves and name changes are handled entirely through
    aliases/team_history/team_conference_history."""
    row = conn.execute(
        "SELECT team_id FROM teams WHERE team_id LIKE 'cfb\\_%' ESCAPE '\\' "
        "ORDER BY team_id DESC LIMIT 1"
    ).fetchone()
    n = int(row[0].split("_")[1]) + 1 if row else 1
    return f"cfb_{n:04d}"


def add_alias(conn: sqlite3.Connection, alias: str, team_id: str, note: str = "") -> None:
    """Register that `alias` (a team code as it appears in a source
    file) refers to the same franchise as the existing `team_id`."""
    conn.execute(
        "INSERT INTO team_aliases(alias, team_id, note) VALUES (?, ?, ?) "
        "ON CONFLICT(alias) DO UPDATE SET team_id=excluded.team_id, note=excluded.note",
        (alias, team_id, note),
    )


def resolve_team_id(conn: sqlite3.Connection, code: str) -> str:
    """Translate a raw team code from a source file into its permanent
    team_id, following the registered alias. Returns the code unchanged
    if no alias exists yet (caller should register one first - see
    register_new_team)."""
    row = conn.execute("SELECT team_id FROM team_aliases WHERE alias = ?", (code,)).fetchone()
    return row[0] if row else code


def add_team_history(conn: sqlite3.Connection, team_id: str, code: str, name: str,
                      start_season: int, end_season: Optional[int] = None) -> None:
    conn.execute(
        "INSERT INTO team_history(team_id, code, name, start_season, end_season) "
        "VALUES (?, ?, ?, ?, ?)",
        (team_id, code, name, start_season, end_season),
    )


def close_team_history(conn: sqlite3.Connection, team_id: str, end_season: int) -> None:
    """Close out the currently-open (end_season IS NULL) history row for
    a franchise - call this right before its code/name changes, e.g. a
    relocation or rebrand taking effect."""
    conn.execute(
        "UPDATE team_history SET end_season = ? WHERE team_id = ? AND end_season IS NULL",
        (end_season, team_id),
    )


def register_new_team(conn: sqlite3.Connection, code: str, name: str, start_season: int) -> str:
    """Register a franchise never seen before: mint a permanent
    synthetic team_id, register `code` as its alias, set the current
    display name, and open a team_history row starting this season.
    Returns the new team_id."""
    team_id = next_team_id(conn)
    upsert_team(conn, team_id, name)
    add_alias(conn, code, team_id, note="initial code")
    add_team_history(conn, team_id, code, name, start_season)
    return team_id


def rename_current_history(conn: sqlite3.Connection, team_id: str, name: str) -> bool:
    """Update the name on team_id's currently-open (end_season IS NULL)
    team_history row, for a cosmetic rename that does NOT change its
    code (e.g. fixing a placeholder name after registration). Use
    close_team_history + add_team_history instead for an actual
    relocation/rebrand, which should start a new era.
    Returns True if a row was updated, False if there was no open row
    to update (team predates team_history and needs one opened first)."""
    before = conn.total_changes
    conn.execute(
        "UPDATE team_history SET name = ? WHERE team_id = ? AND end_season IS NULL",
        (name, team_id),
    )
    return conn.total_changes > before


def display_name(conn: sqlite3.Connection, team_id: str, season: int) -> str:
    """The name a franchise went by during `season` - e.g. 'Houston
    Oilers' for a given team_id in 1996, 'Tennessee Titans' for the
    same team_id in 2010. Falls back to teams.team_name if no
    era-specific history row covers that season yet."""
    row = conn.execute(
        "SELECT name FROM team_history WHERE team_id = ? AND start_season <= ? "
        "AND (end_season IS NULL OR end_season >= ?)",
        (team_id, season, season),
    ).fetchone()
    if row:
        return row[0]
    row = conn.execute("SELECT team_name FROM teams WHERE team_id = ?", (team_id,)).fetchone()
    return row[0] if row else team_id


def era_info(conn: sqlite3.Connection, team_id: str, season: int) -> Optional[dict]:
    """Everything about the era covering `season`: code, name, and
    (possibly None) colors. Returns None if no team_history row covers
    that season - caller should fall back to teams.team_name/config.js
    current colors in that case, same as display_name()'s fallback."""
    row = conn.execute(
        "SELECT code, name, primary_color, secondary_color, tertiary_color "
        "FROM team_history WHERE team_id = ? AND start_season <= ? "
        "AND (end_season IS NULL OR end_season >= ?)",
        (team_id, season, season),
    ).fetchone()
    if not row:
        return None
    return {
        "code": row[0], "name": row[1],
        "primary": row[2], "secondary": row[3], "tertiary": row[4],
    }


def set_era_colors(conn: sqlite3.Connection, team_id: str, start_season: int,
                    primary: str, secondary: str, tertiary: str) -> bool:
    """Set colors on the specific team_history era row identified by
    (team_id, start_season) - the primary key, so this always targets
    exactly one era even when multiple rows share the same code.
    Returns True if a row was updated, False if no era starts at that
    exact season (check franchise.py status for the real start_season)."""
    before = conn.total_changes
    conn.execute(
        "UPDATE team_history SET primary_color = ?, secondary_color = ?, tertiary_color = ? "
        "WHERE team_id = ? AND start_season = ?",
        (primary, secondary, tertiary, team_id, start_season),
    )
    return conn.total_changes > before


# --------------------------------------------------------------------
# CFB-SPECIFIC: conference realignment (era-scoped, separate from
# team_history - see team_conference_history's schema comment above)
# --------------------------------------------------------------------

def add_conference_era(conn: sqlite3.Connection, team_id: str, conference: str,
                        start_season: int, division: Optional[str] = None,
                        end_season: Optional[int] = None) -> None:
    """Open a new conference-membership era for team_id starting
    `start_season`. Call close_conference_era() on the prior era first
    if one is open (franchise.py's `realign` command does this for
    you).

    ORDER-SENSITIVE - only safe when seasons are being recorded in
    chronological order. Loading (or re-loading) an EARLIER season
    after a LATER one is already on file can collide with an existing
    row on the (team_id, start_season) primary key, or - worse - can
    have close_conference_era() incorrectly "close" a later era that
    only looked open because it hadn't been followed by anything yet.
    Prefer set_conference_era() below for anything that might run out
    of order (load_conference_membership.py and franchise.py's
    `realign` both use it for exactly this reason)."""
    conn.execute(
        "INSERT INTO team_conference_history(team_id, conference, division, "
        "start_season, end_season) VALUES (?, ?, ?, ?, ?)",
        (team_id, conference, division, start_season, end_season),
    )


def close_conference_era(conn: sqlite3.Connection, team_id: str, end_season: int) -> None:
    """Close out the currently-open (end_season IS NULL) conference era
    for a program - call this right before its conference changes.
    See add_conference_era's ORDER-SENSITIVE note - this blindly closes
    whatever has end_season IS NULL, with no check that it actually
    started before `end_season`. Prefer set_conference_era() below if
    seasons might be recorded out of chronological order."""
    conn.execute(
        "UPDATE team_conference_history SET end_season = ? "
        "WHERE team_id = ? AND end_season IS NULL",
        (end_season, team_id),
    )


def set_conference_era(conn: sqlite3.Connection, team_id: str, conference: str,
                        start_season: int, division: Optional[str] = None) -> str:
    """Order-INDEPENDENT way to record team_id's conference starting
    `start_season`. Loading season 2013 before 1996, then 1996
    afterward, produces the same end state as loading 1996 first -
    unlike add_conference_era/close_conference_era, which assume
    strictly chronological loading and will corrupt or collide on data
    when that assumption is violated (see their docstrings). Returns
    "updated" (an exact (team_id, start_season) row already existed and
    got its conference/division corrected in place - e.g. re-running
    after a KNOWN_ALIASES fix), "inserted" (a new era was added), or
    "unchanged" (an existing era already covering this season already
    has this exact conference/division - nothing to do).

    How it stays order-independent:
      1. If a row already exists for EXACTLY this (team_id,
         start_season), update it in place instead of inserting a
         second row - this is what a naive close-then-insert would
         collide on.
      2. Only closes a era that's genuinely PRIOR (start_season
         strictly less than this one) and open/overlapping - never
         blindly closes "whatever has end_season IS NULL", since that
         row might actually start AFTER this season if seasons were
         recorded out of order.
      3. Sets this era's own end_season based on the next
         chronologically LATER era already on file (if any) - so
         backfilling an earlier season after a later one already
         exists correctly bounds the new era instead of leaving it
         falsely open-ended.
    """
    exact = conn.execute(
        "SELECT conference, division FROM team_conference_history "
        "WHERE team_id = ? AND start_season = ?",
        (team_id, start_season),
    ).fetchone()
    if exact:
        if exact[0] == conference and exact[1] == division:
            return "unchanged"
        conn.execute(
            "UPDATE team_conference_history SET conference = ?, division = ? "
            "WHERE team_id = ? AND start_season = ?",
            (conference, division, team_id, start_season),
        )
        return "updated"

    current = conference_for_season(conn, team_id, start_season)
    if current and current["conference"] == conference and current["division"] == division:
        return "unchanged"

    # Close only a genuinely prior, overlapping era - start_season
    # strictly less than this one, never a "later" era that merely
    # looks open because nothing has followed it yet.
    conn.execute(
        "UPDATE team_conference_history SET end_season = ? "
        "WHERE team_id = ? AND start_season < ? AND (end_season IS NULL OR end_season >= ?)",
        (start_season - 1, team_id, start_season, start_season),
    )

    next_start_row = conn.execute(
        "SELECT MIN(start_season) FROM team_conference_history "
        "WHERE team_id = ? AND start_season > ?",
        (team_id, start_season),
    ).fetchone()
    next_start = next_start_row[0] if next_start_row else None
    new_end = (next_start - 1) if next_start is not None else None

    conn.execute(
        "INSERT INTO team_conference_history(team_id, conference, division, "
        "start_season, end_season) VALUES (?, ?, ?, ?, ?)",
        (team_id, conference, division, start_season, new_end),
    )
    return "inserted"


def conference_for_season(conn: sqlite3.Connection, team_id: str,
                           season: int) -> Optional[dict]:
    """The conference/division team_id belonged to during `season`, or
    None if no era covers that season (independent, FCS opponent with
    no conference on file, etc.) - engine.py treats None as "not a
    conference or division game" for this team, same as an unaffiliated
    program. NOTE: this is NOT the right check for "is this team FBS" -
    a real FBS independent also has no era here. Use is_fbs() for that."""
    row = conn.execute(
        "SELECT conference, division FROM team_conference_history "
        "WHERE team_id = ? AND start_season <= ? "
        "AND (end_season IS NULL OR end_season >= ?)",
        (team_id, season, season),
    ).fetchone()
    if not row:
        return None
    return {"conference": row[0], "division": row[1]}


def set_fbs_membership(conn: sqlite3.Connection, team_id: str, season: int) -> None:
    """Record that team_id was FBS during `season` - called for every
    resolved school row in a season's Standings export, independents
    included (see fbs_membership's schema comment)."""
    conn.execute(
        "INSERT OR IGNORE INTO fbs_membership(team_id, season) VALUES (?, ?)",
        (team_id, season),
    )


def is_fbs(conn: sqlite3.Connection, team_id: str, season: int) -> bool:
    """Whether team_id is known to be FBS for `season`. False means
    either a genuine FCS/lower-division opponent, OR that
    load_conference_membership.py simply hasn't been run for this
    season yet - see fbs_membership's schema comment. engine.py treats
    False as "use the fixed FCS rating, don't persist a rating row" -
    see its module docstring."""
    row = conn.execute(
        "SELECT 1 FROM fbs_membership WHERE team_id = ? AND season = ?",
        (team_id, season),
    ).fetchone()
    return row is not None


# CFB-SPECIFIC: FBS independents have no conference to draw a
# SEASON-ENTRY average from (see engine.py's module docstring), so
# each one is manually bucketed into the power or midmajor tier pool
# instead. Notre Dame is the one enduring power-independent; every
# other independent (historically UConn, UMass, Army before joining
# the AAC, etc.) defaults to midmajor. Extend this if a genuinely
# power-caliber program goes independent again in the future.
INDEPENDENT_TIER = {
    "notre-dame": "power",
}


def independent_tier(team_id: str) -> str:
    """Which tier pool an FBS independent draws its SEASON-ENTRY
    average from - see INDEPENDENT_TIER above. Defaults to midmajor
    for anything not explicitly listed."""
    return INDEPENDENT_TIER.get(team_id, "midmajor")


def set_conference_tier(conn: sqlite3.Connection, conference: str, tier: str,
                         start_season: int, end_season: Optional[int] = None) -> None:
    """Register a conference as power/midmajor for a range of seasons -
    see conference_tier's schema comment. Used by seed_conference_tiers()
    below and by anyone hand-correcting an era later."""
    conn.execute(
        "INSERT OR REPLACE INTO conference_tier(conference, start_season, end_season, tier) "
        "VALUES (?, ?, ?, ?)",
        (conference, start_season, end_season, tier),
    )


def tier_for_conference(conn: sqlite3.Connection, conference: str, season: int) -> str:
    """"power" or "midmajor" for `conference` during `season`. Defaults
    to "midmajor" if no row covers it - see conference_tier's schema
    comment. Conference NAME matching only (not team_id-based), since
    tier is a property of the conference brand/era, not any specific
    member."""
    row = conn.execute(
        "SELECT tier FROM conference_tier WHERE conference = ? AND start_season <= ? "
        "AND (end_season IS NULL OR end_season >= ?)",
        (conference, season, season),
    ).fetchone()
    return row[0] if row else "midmajor"


def seed_conference_tiers(conn: sqlite3.Connection) -> None:
    """One-time seed of the well-known power-conference eras across
    1996-present. Safe to re-run (INSERT OR REPLACE via
    set_conference_tier). This is a STARTING POINT, not an exhaustive
    or definitive history - conference names/tiers before 1996, or any
    edge case not listed here, default to "midmajor" via
    tier_for_conference()'s fallback. Extend/correct via
    set_conference_tier() directly as gaps turn up."""
    # Conferences that have been power-tier for this dataset's ENTIRE
    # 1996-present range and show no sign of stopping.
    for conf in ("SEC", "Big Ten", "ACC", "Big 12"):
        set_conference_tier(conn, conf, "power", 1996, end_season=None)
    # The Pac-12 was power-tier through its 2023 dissolution (most
    # members left for the Big Ten/Big 12/ACC in 2024).
    set_conference_tier(conn, "Pac-12", "power", 1996, end_season=2023)
    # The old football-playing Big East was power-tier through its
    # 2012 season, before splitting into the American (a midmajor
    # conference in this scheme) in 2013.
    set_conference_tier(conn, "Big East", "power", 1996, end_season=2012)
    conn.commit()


def add_reset(conn: sqlite3.Connection, team_id: str, season: int, note: str = "") -> None:
    """Force team_id's rating to reset to the base rating at the start
    of `season`, ignoring its actual prior-season history. Use this
    when a folded franchise's brand/code is reused for what is really
    a new team."""
    conn.execute(
        "INSERT INTO franchise_resets(team_id, season, note) VALUES (?, ?, ?) "
        "ON CONFLICT(team_id, season) DO UPDATE SET note=excluded.note",
        (team_id, season, note),
    )


def load_resets(conn: sqlite3.Connection) -> set[tuple[str, int]]:
    rows = conn.execute("SELECT team_id, season FROM franchise_resets").fetchall()
    return {(t, s) for t, s in rows}


PARAMS_FILE = "active_params.json"
# Active (tuned) parameters live in this file, deliberately SEPARATE
# from the database, so deleting/resetting nfl_elo.db can never
# silently wipe out tuning. There's no set_params.py for NFL yet (see
# TEMPLATE.md - it's only worth building while actively tuning); until
# then, retuning means hand-editing BASELINE_PARAMS in engine.py and
# running rebuild.py, or writing to this file directly.


def save_active_params(conn: sqlite3.Connection, params: dict) -> None:
    """Persist the currently-active (possibly tuned) parameter set to
    active_params.json, so it survives between script runs AND survives
    the database being deleted/recreated."""
    import json
    with open(PARAMS_FILE, "w") as f:
        json.dump(params, f, indent=2)


def load_active_params(conn: sqlite3.Connection) -> Optional[dict]:
    """Returns the persisted active parameter set from active_params.json,
    or None if that file doesn't exist (in which case callers should
    fall back to the original baseline). Unlike NBA/WNBA's playoff_mult
    (numeric round keys, which JSON round-trips as strings and need
    restoring), NFL's playoff_round_mult keys are already strings
    ('WC'/'DV'/'CC'/'SB'), so no reparse is needed here."""
    import json
    import os
    if not os.path.exists(PARAMS_FILE):
        return None
    with open(PARAMS_FILE) as f:
        return json.load(f)


SCHEDULE_FILE = "param_schedule.json"
# A per-season override of alpha/kmax/hfa (see nfl_tune_engine.py /
# nfl_reconstruct_engine.py). Deliberately a SEPARATE file from
# active_params.json rather than a new shape inside it, so a system that
# doesn't know about scheduling yet (or a person hand-editing
# active_params.json) can't accidentally desync the two. If this file
# exists, rebuild.py should prefer it over active_params.json and swap
# eng.params at each season boundary; if it doesn't exist, nothing about
# current behavior changes.


def save_param_schedule(conn: sqlite3.Connection, schedule: dict[int, dict]) -> None:
    """Persist a season -> {alpha, kmax, hfa} schedule. `schedule` keys
    are ints (seasons); JSON needs string keys, so this round-trips them
    through str() on save and int() on load."""
    import json
    with open(SCHEDULE_FILE, "w") as f:
        json.dump({str(season): params for season, params in schedule.items()}, f, indent=2)


def load_param_schedule(conn: sqlite3.Connection) -> Optional[dict[int, dict]]:
    """Returns the persisted season -> {alpha, kmax, hfa} schedule, or
    None if no schedule file exists yet (caller should fall back to
    load_active_params()/baseline - see PARAMS_FILE note above)."""
    import json
    import os
    if not os.path.exists(SCHEDULE_FILE):
        return None
    with open(SCHEDULE_FILE) as f:
        raw = json.load(f)
    return {int(season): params for season, params in raw.items()}


def params_for_season(conn: sqlite3.Connection, season: int) -> dict:
    """The single lookup rebuild.py needs at each season boundary: the
    schedule's entry for this season if one exists (merged onto the
    engine baseline, so only alpha/kmax/hfa/fcs_rating are overridden
    and everything else - k_floor, rest adjustments, div/conf/playoff
    multipliers - stays at the validated baseline); otherwise the most
    recently locked EARLIER season in the schedule (e.g. an unplayed
    season with a schedule uploaded via add_season.py but not yet
    retuned inherits last season's numbers, not the original stale
    baseline - a season with no games yet and no schedule entry is a
    far more common case than "the schedule file itself is missing",
    and defaulting all the way back to hfa=72/kmax=46 for it would be
    a much worse failure mode than defaulting to last season's already
    -corrected values); otherwise falls back to active_params.json;
    otherwise the engine's own baseline."""
    import engine
    schedule = load_param_schedule(conn)
    base = engine.default_params()
    SCHEDULE_KEYS = ("alpha", "kmax", "hfa", "fcs_rating")
    if schedule:
        if season in schedule:
            base.update({k: v for k, v in schedule[season].items() if k in SCHEDULE_KEYS})
            return base
        earlier = [s for s in schedule if s < season]
        if earlier:
            nearest = max(earlier)
            base.update({k: v for k, v in schedule[nearest].items() if k in SCHEDULE_KEYS})
            return base
    active = load_active_params(conn)
    if active:
        base.update({k: v for k, v in active.items() if k in base})
        return base
    return base


def upsert_team(conn: sqlite3.Connection, team_id: str, team_name: str) -> None:
    conn.execute(
        "INSERT INTO teams(team_id, team_name) VALUES (?, ?) "
        "ON CONFLICT(team_id) DO UPDATE SET team_name=excluded.team_name",
        (team_id, team_name),
    )


def add_scheduled_game(conn: sqlite3.Connection, d: date, season: int, type_: str, round_,
                        home_team: str, away_team: str, home_code: str, away_code: str,
                        neutral: int = 0, home_ap_rank: Optional[int] = None,
                        away_ap_rank: Optional[int] = None) -> bool:
    """Returns True if a new schedule row was inserted, False if it was
    already there."""
    before = conn.total_changes
    conn.execute(
        "INSERT OR IGNORE INTO schedule(date, season, type, round, home_team, away_team, "
        "home_code, away_code, neutral, home_ap_rank, away_ap_rank) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (d.isoformat(), season, type_, round_, home_team, away_team, home_code, away_code,
         neutral, home_ap_rank, away_ap_rank),
    )
    return conn.total_changes > before


def upcoming_games(conn: sqlite3.Connection, season: int | None = None) -> list[dict]:
    """Schedule entries that don't yet have a matching row in `games`
    (i.e. games that haven't been played/scored yet)."""
    query = """
        SELECT s.schedule_id, s.date, s.season, s.type, s.round,
               s.home_team, s.away_team, s.home_code, s.away_code, s.neutral,
               s.home_ap_rank, s.away_ap_rank
        FROM schedule s
        WHERE NOT EXISTS (
            SELECT 1 FROM games g
            WHERE g.date = s.date AND g.home_team = s.home_team AND g.away_team = s.away_team
              AND g.type = s.type AND IFNULL(g.round, 'RS') = IFNULL(s.round, 'RS')
        )
    """
    params = []
    if season is not None:
        query += " AND s.season = ?"
        params.append(season)
    query += " ORDER BY s.date, s.schedule_id"

    rows = conn.execute(query, params).fetchall()
    cols = ["schedule_id", "date", "season", "type", "round", "home_team", "away_team",
            "home_code", "away_code", "neutral", "home_ap_rank", "away_ap_rank"]
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        d["date"] = datetime.fromisoformat(d["date"]).date()
        out.append(d)
    return out


def prune_played_schedule_rows(conn: sqlite3.Connection) -> int:
    """Delete schedule rows that now have a matching completed game in
    `games` (i.e. the result has come in - the schedule placeholder is
    no longer needed). Returns the number removed.

    Deletes matching schedule_predictions rows FIRST - schedule_predictions
    has a foreign key on schedule_id, so with foreign_keys=ON (see
    connect()) deleting a `schedule` row that still has prediction rows
    pointing at it fails with an IntegrityError. A game can have
    predictions for multiple variants (echo, pulse, ...) by the time
    it's played, so this clears all of them for that schedule_id, not
    just one variant's."""
    before = conn.total_changes
    to_prune = """
        SELECT schedule_id FROM schedule
        WHERE EXISTS (
            SELECT 1 FROM games g
            WHERE g.date = schedule.date AND g.home_team = schedule.home_team
              AND g.away_team = schedule.away_team AND g.type = schedule.type
              AND IFNULL(g.round, 'RS') = IFNULL(schedule.round, 'RS')
        )
    """
    conn.execute(f"DELETE FROM schedule_predictions WHERE schedule_id IN ({to_prune})")
    conn.execute(f"DELETE FROM schedule WHERE schedule_id IN ({to_prune})")
    conn.commit()
    return conn.total_changes - before


def add_game(conn: sqlite3.Connection, d: date, season: int, type_: str, round_,
             home_team: str, away_team: str, home_code: str, away_code: str,
             home_pts: int, away_pts: int, ot: int = 0, neutral: int = 0,
             home_ap_rank: Optional[int] = None, away_ap_rank: Optional[int] = None) -> bool:
    """Returns True if a new row was inserted, False if it was a duplicate
    (matched on date, home_team, away_team, type, and round) and ignored.
    AP ranks are display-only (see db.py's module docstring) - never
    read by the rating engine."""
    before = conn.total_changes
    conn.execute(
        "INSERT OR IGNORE INTO games(date, season, type, round, home_team, away_team, "
        "home_code, away_code, home_pts, away_pts, ot, neutral, home_ap_rank, away_ap_rank) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (d.isoformat(), season, type_, round_, home_team, away_team, home_code, away_code,
         home_pts, away_pts, ot, neutral, home_ap_rank, away_ap_rank),
    )
    return conn.total_changes > before


def load_games(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.execute(
        "SELECT game_id, date, season, type, round, home_team, away_team, "
        "home_code, away_code, home_pts, away_pts, ot, neutral, home_ap_rank, away_ap_rank "
        "FROM games ORDER BY date, game_id"
    )
    out = []
    for row in cur.fetchall():
        (gid, d, season, type_, round_, home, away, home_code, away_code, hp, ap,
         ot, neutral, home_rank, away_rank) = row
        out.append(dict(
            game_id=gid, date=datetime.fromisoformat(d).date(), season=season,
            type=type_, round=round_, home_team=home, away_team=away,
            home_code=home_code, away_code=away_code,
            home_pts=hp, away_pts=ap, ot=ot, neutral=neutral,
            home_ap_rank=home_rank, away_ap_rank=away_rank,
        ))
    return out


def clear_ratings(conn: sqlite3.Connection, variant: str) -> None:
    """Wipe only this variant's rating rows - a different variant's
    rows for the same games are untouched, so rebuilding one variant
    never disturbs the other."""
    conn.execute("DELETE FROM ratings WHERE variant = ?", (variant,))


def save_ratings(conn: sqlite3.Connection, variant: str, rows: list[dict],
                  game_id_by_row: list[int]) -> None:
    cols = ["game_id", "team", "variant", "opponent", "home_away", "date", "season", "type", "round",
            "conf_game", "div_game", "games_played", "days_off", "opp_days_off", "rest_adj",
            "pre_rate", "opp_pre_rate", "expected_win", "points_for", "points_against", "ot",
            "mov", "result", "accuracy", "test", "brier", "mov_mult", "po_mult", "k", "keff",
            "rating_change", "post_rate", "w", "l", "t", "r1w", "r1l", "r2w", "r2l", "r3w", "r3l",
            "fw", "fl"]
    placeholders = ",".join("?" for _ in cols)
    sql = f"INSERT INTO ratings ({','.join(cols)}) VALUES ({placeholders})"
    for gid, r in zip(game_id_by_row, rows):
        r = dict(r)
        r["date"] = r["date"].isoformat()
        r["variant"] = variant
        conn.execute(sql, [gid] + [r[c] for c in cols[1:]])


def save_schedule_prediction(conn: sqlite3.Connection, schedule_id: int, variant: str,
                              expected_win_home: float, expected_win_away: float,
                              home_days_off: int | None, away_days_off: int | None,
                              rest_adj: float | None) -> None:
    """Write a preview_matchup() result for one variant into
    schedule_predictions. Called from write_schedule_predictions()
    (add_season.py) for every row returned by upcoming_games() after
    each rebuild_ratings() pass, once per variant. Display-only -
    never read by the rating engine itself."""
    conn.execute(
        "INSERT INTO schedule_predictions(schedule_id, variant, expected_win_home, "
        "expected_win_away, home_days_off, away_days_off, rest_adj) VALUES (?,?,?,?,?,?,?) "
        "ON CONFLICT(schedule_id, variant) DO UPDATE SET "
        "expected_win_home=excluded.expected_win_home, "
        "expected_win_away=excluded.expected_win_away, "
        "home_days_off=excluded.home_days_off, away_days_off=excluded.away_days_off, "
        "rest_adj=excluded.rest_adj",
        (schedule_id, variant, expected_win_home, expected_win_away,
         home_days_off, away_days_off, rest_adj),
    )


def schedule_with_predictions(conn: sqlite3.Connection, variant: str) -> list[dict]:
    """Every row in `schedule`, left-joined against that variant's
    prediction in schedule_predictions (NULL prediction fields if a
    prediction pass hasn't run yet for this variant/row). Used by
    export_to_supabase.py's build_schedule() instead of reading
    `schedule` directly, now that predictions are variant-scoped."""
    cur = conn.execute(
        "SELECT s.schedule_id, s.date, s.season, s.type, s.round, s.home_team, "
        "s.away_team, s.home_code, s.away_code, s.neutral, p.expected_win_home, "
        "p.expected_win_away, p.home_days_off, p.away_days_off, p.rest_adj "
        "FROM schedule s LEFT JOIN schedule_predictions p "
        "ON p.schedule_id = s.schedule_id AND p.variant = ?",
        (variant,),
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def save_season_projection(conn: sqlite3.Connection, season: int, variant: str,
                            rows: list[dict], trials: int, remaining_games: int) -> None:
    """Fully replace `season`'s projection FOR THIS VARIANT with a
    freshly computed set - a different variant's rows for the same
    season are untouched. Like schedule predictions, this is a
    snapshot recomputed from scratch on every call, not an incremental
    update - delete-then-insert is simpler and safer than trying to
    reconcile an old snapshot against a new one. Called from
    write_season_projection() (add_season.py) after every
    rebuild_ratings() pass, for every season/variant combo in this run
    that still has remaining games (see clear_season_projection for
    what happens when a season ends)."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("DELETE FROM season_projections WHERE season = ? AND variant = ?", (season, variant))
    for r in rows:
        conn.execute(
            "INSERT INTO season_projections(season, team_id, variant, avg_wins, p10_wins, "
            "median_wins, p90_wins, avg_rating, prob_finish_first, trials, "
            "remaining_games, computed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (season, r["team"], variant, r["avg_wins"], r["p10"], r["p50"], r["p90"],
             r["avg_rating"], r["p_first"], trials, remaining_games, now),
        )
    conn.commit()


def clear_season_projection(conn: sqlite3.Connection, season: int, variant: str) -> None:
    """Remove this variant's projection rows for `season` - called when
    a season has no remaining games left (simulate_season.run_simulation
    returns None in that case), so a stale "final" projection from
    before the season actually ended doesn't linger and look current.
    Only clears the given variant - a different variant's rows for the
    same season, if any, are untouched."""
    conn.execute("DELETE FROM season_projections WHERE season = ? AND variant = ?", (season, variant))
    conn.commit()


def load_season_projection(conn: sqlite3.Connection, season: int, variant: str = "echo") -> list[dict]:
    cur = conn.execute(
        "SELECT season, team_id, variant, avg_wins, p10_wins, median_wins, p90_wins, "
        "avg_rating, prob_finish_first, trials, remaining_games, computed_at "
        "FROM season_projections WHERE season = ? AND variant = ?", (season, variant)
    )
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
