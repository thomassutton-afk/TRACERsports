"""SQLite storage for the WNBA Echo Ratings model.

TEAM IDENTITY MODEL
--------------------
`teams.team_id` is a permanent synthetic ID (e.g. "wnba_0001") assigned
once to a franchise and never changed, regardless of relocations or
rebrands. It carries no meaning of its own - it's just a stable peg for
`games` and `ratings` to reference.

Every human-readable code a franchise has ever played under - including
whatever it currently uses - lives in `team_aliases`, resolved to that
permanent ID via `resolve_team_id`. No single code is privileged as
"the real one."

`team_history` tracks which code/name a franchise used during which
seasons, so you can ask "what was this team called in 1998?" vs "what
is it called now?" even though both are the same team_id. `teams.team_name`
remains a simple current-name fallback for convenience/older callers.
"""
from __future__ import annotations
import sqlite3
from datetime import date, datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    team_id   TEXT PRIMARY KEY,
    team_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS games (
    game_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    date       TEXT NOT NULL,
    season     INTEGER NOT NULL,
    type       TEXT NOT NULL CHECK(type IN ('R','P')),
    round      REAL,
    home_team  TEXT NOT NULL REFERENCES teams(team_id),
    away_team  TEXT NOT NULL REFERENCES teams(team_id),
    home_pts   INTEGER NOT NULL,
    away_pts   INTEGER NOT NULL,
    ot         INTEGER NOT NULL DEFAULT 0,
    neutral    INTEGER NOT NULL DEFAULT 0
);

-- A plain UNIQUE constraint treats every NULL `round` as distinct from
-- every other NULL, so regular-season games (round IS NULL) would
-- never be deduplicated. IFNULL(round, -1) makes NULLs compare equal
-- to each other for uniqueness purposes.
CREATE UNIQUE INDEX IF NOT EXISTS idx_games_unique
    ON games(date, home_team, away_team, type, IFNULL(round, -1));

-- Unplayed games live here, NEVER in `games`. This is deliberate: the
-- rating engine (rebuild_ratings) only ever reads from `games`, and
-- has no code path that touches `schedule` at all. A game with no
-- score literally cannot reach the rating math - there's no "0-0
-- tie" failure mode possible, because there's no score column here
-- to default to 0.
--
-- expected_win_home/expected_win_away/*_days_off/rest_adj columns here
-- are LEGACY and no longer written to (kept only so an old .db file
-- doesn't break) - predictions are now per-variant and live in
-- schedule_predictions below, since Echo and Pulse genuinely predict
-- different winners once their ratings diverge.
CREATE TABLE IF NOT EXISTS schedule (
    schedule_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    date                TEXT NOT NULL,
    season              INTEGER NOT NULL,
    type                TEXT NOT NULL CHECK(type IN ('R','P')),
    round               REAL,
    home_team           TEXT NOT NULL REFERENCES teams(team_id),
    away_team           TEXT NOT NULL REFERENCES teams(team_id),
    neutral             INTEGER NOT NULL DEFAULT 0,
    expected_win_home   REAL,
    expected_win_away   REAL,
    home_days_off       INTEGER,
    away_days_off       INTEGER,
    rest_adj            REAL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_unique
    ON schedule(date, home_team, away_team, type, IFNULL(round, -1));

-- Per-variant prediction for an upcoming (unplayed) game in `schedule`.
-- Split out from `schedule` itself (rather than adding a variant column
-- there) because the fixture - date/teams/round - is shared across
-- variants, only the predicted winner differs. Display-only, same as
-- the legacy columns it replaces: nothing in the rating engine ever
-- reads this back.
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
    round         REAL,
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
    w REAL, l REAL, t REAL DEFAULT 0, r1w REAL, r1l REAL, r2w REAL, r2l REAL,
    r3w REAL, r3l REAL, fw REAL, fl REAL,
    PRIMARY KEY (game_id, team, variant)
);

CREATE TABLE IF NOT EXISTS params (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Monte Carlo season projection (simulate_season.py), one row per team
-- per season per VARIANT - Pulse's projected win totals genuinely
-- differ from Echo's once ratings diverge, same reasoning as ratings
-- above. Fully replaced each time it's recomputed (see
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

-- Franchise relocations: maps a team code as it appears in a new
-- season's source file (e.g. "SAS") to the canonical team_id already
-- used in the database for that same continuous franchise (e.g.
-- "UTA"). Rating history carries through unaffected.
CREATE TABLE IF NOT EXISTS team_aliases (
    alias      TEXT PRIMARY KEY,
    team_id    TEXT NOT NULL REFERENCES teams(team_id),
    note       TEXT
);

-- Era-scoped code/name for a franchise, so games display under the
-- name/code the team actually used at the time (e.g. Seattle
-- SuperSonics in 1996, Oklahoma City Thunder in 2010 - same team_id).
-- end_season IS NULL means "still current."
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
-- old final rating.
CREATE TABLE IF NOT EXISTS franchise_resets (
    team_id TEXT NOT NULL,
    season  INTEGER NOT NULL,
    note    TEXT,
    PRIMARY KEY (team_id, season)
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SCHEMA)
    _migrate(conn)
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Upgrade an older database file in place, for schema additions
    made after it was first created."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(games)")}
    if "neutral" not in cols:
        conn.execute("ALTER TABLE games ADD COLUMN neutral INTEGER NOT NULL DEFAULT 0")
        conn.commit()

    schedule_cols = {row[1] for row in conn.execute("PRAGMA table_info(schedule)")}
    new_schedule_cols = {
        "expected_win_home": "REAL",
        "expected_win_away": "REAL",
        "home_days_off": "INTEGER",
        "away_days_off": "INTEGER",
        "rest_adj": "REAL",
    }
    for col, coltype in new_schedule_cols.items():
        if col not in schedule_cols:
            conn.execute(f"ALTER TABLE schedule ADD COLUMN {col} {coltype}")
    conn.commit()

    # Pulse variant support: `ratings` and `season_projections` both
    # need a `variant` column folded into their primary key. Both
    # tables are 100% derived/disposable - always fully wiped and
    # recomputed from `games` (ratings) or recomputed from current
    # ratings (season_projections), never hand-edited or treated as a
    # source of truth - so on an old .db file that predates Pulse, the
    # safe fix is just to drop and recreate them with the new schema.
    # The very next add_season.py run repopulates both for every
    # variant, same as any other rebuild.
    ratings_cols = {row[1] for row in conn.execute("PRAGMA table_info(ratings)")}
    if ratings_cols and "variant" not in ratings_cols:
        conn.execute("DROP TABLE ratings")
        conn.executescript(SCHEMA)
        conn.commit()

    proj_cols = {row[1] for row in conn.execute("PRAGMA table_info(season_projections)")}
    if proj_cols and "variant" not in proj_cols:
        conn.execute("DROP TABLE season_projections")
        conn.executescript(SCHEMA)
        conn.commit()

    # Era-specific colors: nullable by design. A row with no colors set
    # just means nobody's populated that era's colors yet - callers fall
    # back to the current identity's colors (from config.js), not an
    # error. Kept on team_history itself (not a separate lookup keyed by
    # code) because code alone isn't a stable key - e.g. 'San Antonio
    # Silver Stars' (2003-2013) and 'San Antonio Stars' (2014-2017) are
    # two different team_history rows sharing the code 'SAS'; only
    # (team_id, start_season) uniquely identifies an era.
    history_cols = {row[1] for row in conn.execute("PRAGMA table_info(team_history)")}
    for col in ("primary_color", "secondary_color", "tertiary_color"):
        if col not in history_cols:
            conn.execute(f"ALTER TABLE team_history ADD COLUMN {col} TEXT")
    conn.commit()


def add_alias(conn: sqlite3.Connection, alias: str, team_id: str, note: str = "") -> None:
    """Register that `alias` (a team code as it appears in a source
    file) refers to the same franchise as the existing `team_id`."""
    conn.execute(
        "INSERT INTO team_aliases(alias, team_id, note) VALUES (?, ?, ?) "
        "ON CONFLICT(alias) DO UPDATE SET team_id=excluded.team_id, note=excluded.note",
        (alias, team_id, note),
    )


def resolve_team_id(conn: sqlite3.Connection, code: str) -> str:
    """Translate a raw team code from a source file into its canonical
    team_id, following any registered alias. Returns the code unchanged
    if no alias exists."""
    row = conn.execute("SELECT team_id FROM team_aliases WHERE alias = ?", (code,)).fetchone()
    return row[0] if row else code


def next_team_id(conn: sqlite3.Connection) -> str:
    """Generate the next sequential permanent franchise ID, e.g.
    'wnba_0001'. Once assigned, a team_id never changes - relocations
    and rebrands are handled entirely through aliases/team_history."""
    row = conn.execute(
        "SELECT team_id FROM teams WHERE team_id LIKE 'wnba\\_%' ESCAPE '\\' "
        "ORDER BY team_id DESC LIMIT 1"
    ).fetchone()
    n = int(row[0].split("_")[1]) + 1 if row else 1
    return f"wnba_{n:04d}"


def add_team_history(conn: sqlite3.Connection, team_id: str, code: str, name: str,
                      start_season: int, end_season: int | None = None) -> None:
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
    """The name a franchise went by during `season` - e.g. its 1998
    name vs. its current name, even for the same team_id. Falls back
    to teams.team_name if no era-specific history row covers that
    season yet."""
    row = conn.execute(
        "SELECT name FROM team_history WHERE team_id = ? AND start_season <= ? "
        "AND (end_season IS NULL OR end_season >= ?)",
        (team_id, season, season),
    ).fetchone()
    if row:
        return row[0]
    row = conn.execute("SELECT team_name FROM teams WHERE team_id = ?", (team_id,)).fetchone()
    return row[0] if row else team_id


def era_info(conn: sqlite3.Connection, team_id: str, season: int) -> dict | None:
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
# from the database, so deleting/resetting wnba_elo.db can never
# silently wipe out tuning. If you genuinely want to go back to the
# original values, use `python3 set_params.py reset` (or delete this
# file directly) rather than deleting the database.


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
    fall back to the original baseline)."""
    import json
    import os
    if not os.path.exists(PARAMS_FILE):
        return None
    with open(PARAMS_FILE) as f:
        params = json.load(f)
    # JSON turns dict keys into strings; playoff_mult round numbers
    # need to be restored to their numeric form (1, 2, 3, 4, 0.5).
    params["playoff_mult"] = {float(k) if "." in k else int(k): v
                               for k, v in params["playoff_mult"].items()}
    return params


def upsert_team(conn: sqlite3.Connection, team_id: str, team_name: str) -> None:
    conn.execute(
        "INSERT INTO teams(team_id, team_name) VALUES (?, ?) "
        "ON CONFLICT(team_id) DO UPDATE SET team_name=excluded.team_name",
        (team_id, team_name),
    )


def add_scheduled_game(conn: sqlite3.Connection, d: date, season: int, type_: str, round_,
                        home_team: str, away_team: str, neutral: int = 0) -> bool:
    """Returns True if a new schedule row was inserted, False if it was
    already there."""
    before = conn.total_changes
    conn.execute(
        "INSERT OR IGNORE INTO schedule(date, season, type, round, home_team, away_team, neutral) "
        "VALUES (?,?,?,?,?,?,?)",
        (d.isoformat(), season, type_, round_, home_team, away_team, neutral),
    )
    return conn.total_changes > before


def upcoming_games(conn: sqlite3.Connection, season: int | None = None) -> list[dict]:
    """Schedule entries that don't yet have a matching row in `games`
    (i.e. games that haven't been played/scored yet)."""
    query = """
        SELECT s.schedule_id, s.date, s.season, s.type, s.round,
               s.home_team, s.away_team, s.neutral
        FROM schedule s
        WHERE NOT EXISTS (
            SELECT 1 FROM games g
            WHERE g.date = s.date AND g.home_team = s.home_team AND g.away_team = s.away_team
              AND g.type = s.type AND IFNULL(g.round, -1) = IFNULL(s.round, -1)
        )
    """
    params = []
    if season is not None:
        query += " AND s.season = ?"
        params.append(season)
    query += " ORDER BY s.date, s.schedule_id"

    rows = conn.execute(query, params).fetchall()
    cols = ["schedule_id", "date", "season", "type", "round", "home_team", "away_team", "neutral"]
    out = []
    for r in rows:
        d = dict(zip(cols, r))
        d["date"] = datetime.fromisoformat(d["date"]).date()
        out.append(d)
    return out


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
        "s.away_team, s.neutral, p.expected_win_home, p.expected_win_away, "
        "p.home_days_off, p.away_days_off, p.rest_adj "
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
              AND IFNULL(g.round, -1) = IFNULL(schedule.round, -1)
        )
    """
    conn.execute(f"DELETE FROM schedule_predictions WHERE schedule_id IN ({to_prune})")
    conn.execute(f"DELETE FROM schedule WHERE schedule_id IN ({to_prune})")
    conn.commit()
    return conn.total_changes - before


def add_game(conn: sqlite3.Connection, d: date, season: int, type_: str, round_,
             home_team: str, away_team: str, home_pts: int, away_pts: int, ot: int = 0,
             neutral: int = 0) -> bool:
    """Returns True if a new row was inserted, False if it was a duplicate
    (matched on date, home_team, away_team, type, and round) and ignored."""
    before = conn.total_changes
    conn.execute(
        "INSERT OR IGNORE INTO games(date, season, type, round, home_team, away_team, "
        "home_pts, away_pts, ot, neutral) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (d.isoformat(), season, type_, round_, home_team, away_team, home_pts, away_pts, ot, neutral),
    )
    return conn.total_changes > before


def load_games(conn: sqlite3.Connection) -> list[dict]:
    cur = conn.execute(
        "SELECT game_id, date, season, type, round, home_team, away_team, "
        "home_pts, away_pts, ot, neutral FROM games ORDER BY date, game_id"
    )
    out = []
    for row in cur.fetchall():
        gid, d, season, type_, round_, home, away, hp, ap, ot, neutral = row
        out.append(dict(
            game_id=gid, date=datetime.fromisoformat(d).date(), season=season,
            type=type_, round=round_, home_team=home, away_team=away,
            home_pts=hp, away_pts=ap, ot=ot, neutral=neutral,
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
            "games_played", "days_off", "opp_days_off", "rest_adj", "pre_rate", "opp_pre_rate",
            "expected_win", "points_for", "points_against", "ot", "mov", "result", "accuracy",
            "test", "brier", "mov_mult", "po_mult", "k", "keff", "rating_change", "post_rate",
            "w", "l", "r1w", "r1l", "r2w", "r2l", "r3w", "r3l", "fw", "fl"]
    placeholders = ",".join("?" for _ in cols)
    sql = f"INSERT INTO ratings ({','.join(cols)}) VALUES ({placeholders})"
    for gid, r in zip(game_id_by_row, rows):
        r = dict(r)
        r["date"] = r["date"].isoformat()
        r["variant"] = variant
        conn.execute(sql, [gid] + [r[c] for c in cols[1:]])
