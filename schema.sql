-- ============================================================================
-- TRACER — Fresh Multi-Sport Schema
-- sport = 'basketball' | 'football' | ...   league = 'nba' | 'wnba' | 'nfl' | ...
-- Every team-referencing table is keyed by (league, team_id), since team_id
-- values are NOT globally unique (e.g. "NY" exists in both NBA and WNBA).
-- ============================================================================

CREATE TABLE IF NOT EXISTS teams (
    league       TEXT NOT NULL,
    team_id      TEXT NOT NULL,
    sport        TEXT NOT NULL,
    full_name    TEXT NOT NULL,
    city         TEXT,              -- nullable: display metadata lives in lib/sports/{league}/config.js, not here
    nickname     TEXT,              -- nullable: same reason — especially true for historical/inactive teams
    conference   TEXT,              -- nullable: some sports/leagues don't use conferences
    division     TEXT,              -- nullable: e.g. WNBA has none
    active       BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (league, team_id)
);

-- Franchise identity history — e.g. Seattle SuperSonics (1996-2008) -> OKC
-- Thunder (2009-present), Utah Starzz -> San Antonio -> Las Vegas Aces.
-- team_id is always the CURRENT code (same one every other table uses);
-- `code`/`name`/`start_season`/`end_season` describe one era of that
-- franchise's identity. end_season IS NULL means "current" (still that
-- name today) — note a folded/dissolved franchise (e.g. WNBA's Houston
-- Comets) also has end_season NULL here since it never became something
-- else; `active` on the `teams` row above is what actually distinguishes
-- "still playing" from "folded", not this table.
-- Powers season-aware historical names/abbreviations/logos on the
-- All-Time and Team pages. Static reference data — effectively never
-- changes except when a real relocation/rename happens.
CREATE TABLE IF NOT EXISTS team_history (
    league          TEXT NOT NULL,
    team_id         TEXT NOT NULL,
    code            TEXT NOT NULL,
    name            TEXT NOT NULL,
    start_season    INTEGER NOT NULL,
    end_season      INTEGER,
    -- Frequently NULL — most eras don't have colors backfilled yet (see
    -- DBs/seed_historical_colors.py). Callers fall back to the current
    -- team's colors from config.js in that case, same fallback shape as
    -- name/code falling back to the current identity.
    primary_color   TEXT,
    secondary_color TEXT,
    tertiary_color  TEXT,
    PRIMARY KEY (league, team_id, code, start_season),
    FOREIGN KEY (league, team_id) REFERENCES teams(league, team_id)
);

CREATE TABLE IF NOT EXISTS preseason_ratings (
    league         TEXT NOT NULL,
    season         INTEGER NOT NULL,
    variant        TEXT NOT NULL,
    team_id        TEXT NOT NULL,
    preseason_elo  FLOAT NOT NULL,
    PRIMARY KEY (league, season, variant, team_id),
    FOREIGN KEY (league, team_id) REFERENCES teams(league, team_id)
);

CREATE TABLE IF NOT EXISTS games (
    game_id             TEXT    NOT NULL,
    league              TEXT    NOT NULL,
    variant             TEXT    NOT NULL,
    team_id             TEXT    NOT NULL,
    date                DATE    NOT NULL,
    season              INTEGER NOT NULL,
    type                TEXT    NOT NULL,
    round               TEXT,              -- nullable: NULL for every regular-season game (type='R'); only playoff games (type='P') have a round. The live table already allows this (confirmed by successful exports); this fixes the file to match, so a from-scratch rebuild wouldn't reintroduce the bug schedule.round just hit.
    opponent_id         TEXT    NOT NULL,
    home_away           TEXT    NOT NULL,
    points_for          INTEGER NOT NULL,
    points_against      INTEGER NOT NULL,
    ot                  INTEGER NOT NULL DEFAULT 0,
    days_off            INTEGER,
    opp_days_off        INTEGER,
    rest_diff           INTEGER,
    rest_adj            FLOAT,
    pre_gm_rate         FLOAT,
    opp_pre_gm_rate     FLOAT,
    expected_win_pct    FLOAT,
    mov                 INTEGER,
    result              FLOAT,
    accuracy            INTEGER,
    brier               FLOAT,
    mov_mult            FLOAT,
    games_played        INTEGER,
    k                   FLOAT,
    po_mult             FLOAT,
    k_eff               FLOAT,
    rating_change       FLOAT,
    post_gm_rate        FLOAT,
    w                   INTEGER DEFAULT 0,
    l                   INTEGER DEFAULT 0,
    t                   INTEGER DEFAULT 0, -- ties (NFL only in practice - basketball leagues never populate this, always 0)
    r1w INTEGER DEFAULT 0, r1l INTEGER DEFAULT 0,
    r2w INTEGER DEFAULT 0, r2l INTEGER DEFAULT 0,
    r3w INTEGER DEFAULT 0, r3l INTEGER DEFAULT 0,
    fw  INTEGER DEFAULT 0, fl  INTEGER DEFAULT 0,
    PRIMARY KEY (game_id, league, variant, team_id),
    FOREIGN KEY (league, team_id)     REFERENCES teams(league, team_id),
    FOREIGN KEY (league, opponent_id) REFERENCES teams(league, team_id)
);

-- Stable dedup key for exports. game_id comes from SQLite's AUTOINCREMENT
-- in the local pipeline databases and gets reassigned if the local `games`
-- table is ever rebuilt from scratch, so it can't be trusted as a durable
-- identity for a real-world game. This natural key can. COALESCE(round, '')
-- is required because Postgres treats every NULL as distinct from every
-- other NULL in a unique index, which would otherwise defeat dedup entirely
-- for every regular-season game (round is always NULL for type='R').
CREATE UNIQUE INDEX IF NOT EXISTS idx_games_natural_key
    ON games (league, season, variant, team_id, date, opponent_id, home_away, type, (COALESCE(round, '')));

-- Upcoming (unplayed) games with Elo's predicted winner. Mirrors games'
-- one-row-per-team-per-game shape (rather than SQLite's one-row-per-game
-- shape) deliberately, so GamesPanel.jsx can query/render both tables
-- with the same per-team logic it already has. expected_win_pct here is
-- ALWAYS this row's team_id's own predicted win probability (i.e. the
-- home row's expected_win_pct + the away row's expected_win_pct sum to
-- 1.0), same convention as games.expected_win_pct. No points_for/against/
-- result/rating_change columns at all — those genuinely don't exist yet
-- for an unplayed game, unlike games where they're always populated.
CREATE TABLE IF NOT EXISTS schedule (
    league              TEXT    NOT NULL,
    variant             TEXT    NOT NULL,
    team_id             TEXT    NOT NULL,
    date                DATE    NOT NULL,
    season              INTEGER NOT NULL,
    type                TEXT    NOT NULL,
    round               TEXT,              -- nullable: NULL for every regular-season game (type='R'); only playoff games (type='P') have a round
    opponent_id         TEXT    NOT NULL,
    home_away           TEXT    NOT NULL,
    neutral             INTEGER NOT NULL DEFAULT 0,
    expected_win_pct    FLOAT,
    days_off            INTEGER,
    opp_days_off        INTEGER,
    rest_diff           INTEGER,
    rest_adj            FLOAT,
    FOREIGN KEY (league, team_id)     REFERENCES teams(league, team_id),
    FOREIGN KEY (league, opponent_id) REFERENCES teams(league, team_id)
);

-- Postgres PRIMARY KEY/UNIQUE table constraints only accept plain column
-- names, not expressions - so the natural key (which needs COALESCE(round,
-- '') to make every regular-season NULL round compare equal, same reason
-- as idx_games_natural_key above) has to be a separate unique index, not
-- inlined into a PRIMARY KEY clause.
CREATE UNIQUE INDEX IF NOT EXISTS idx_schedule_natural_key
    ON schedule (league, variant, team_id, date, opponent_id, type, (COALESCE(round, '')));

ALTER TABLE schedule ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read access" ON schedule FOR SELECT USING (true);

-- Monte Carlo season projection (simulate_season.py), one row per team
-- per season. Fully replaced on every export (delete-then-insert per
-- league/variant, not upserted) - same reasoning as `schedule`: this is
-- always a fresh snapshot from current ratings, and once a season ends
-- the local season_projections table for that season is cleared
-- entirely (see db.py's clear_season_projection), so a stale row here
-- needs to actually disappear, not just stop being updated.
CREATE TABLE IF NOT EXISTS season_projections (
    league              TEXT    NOT NULL,
    season              INTEGER NOT NULL,
    variant             TEXT    NOT NULL,
    team_id             TEXT    NOT NULL,
    avg_wins            FLOAT,
    p10_wins            INTEGER,
    median_wins         INTEGER,
    p90_wins            INTEGER,
    avg_rating          FLOAT,
    prob_finish_first   FLOAT,
    trials              INTEGER,
    remaining_games     INTEGER,
    computed_at         TIMESTAMPTZ,
    PRIMARY KEY (league, season, variant, team_id),
    FOREIGN KEY (league, team_id) REFERENCES teams(league, team_id)
);

ALTER TABLE season_projections ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read access" ON season_projections FOR SELECT USING (true);

CREATE INDEX IF NOT EXISTS idx_games_league_season_variant     ON games (league, season, variant);
CREATE INDEX IF NOT EXISTS idx_schedule_league_season_variant  ON schedule (league, season, variant);
CREATE INDEX IF NOT EXISTS idx_projections_league_season_variant ON season_projections (league, season, variant);
CREATE INDEX IF NOT EXISTS idx_preseason_league_season_variant ON preseason_ratings (league, season, variant);
CREATE INDEX IF NOT EXISTS idx_teams_sport                     ON teams (sport);
CREATE INDEX IF NOT EXISTS idx_team_history_league_team         ON team_history (league, team_id);
