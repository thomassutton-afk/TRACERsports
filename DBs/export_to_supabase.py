"""
export_to_supabase.py — moves finished ratings data from a per-sport SQLite
database (built by the NBA_Elo / WNBA_Elo / etc. toolchain) into the new
multi-sport Supabase schema (schema.sql).

USAGE
-----
Dry run first (no Supabase connection needed, just prints what WOULD be
written, plus sample rows, so you can sanity-check before touching the
real database):

    python export_to_supabase.py --league nba --db nba_elo.db --dry-run
    python export_to_supabase.py --league wnba --db wnba_elo.db --dry-run

Real run (writes to Supabase; needs a .env file — see bottom of this file
for what it should contain):

    python export_to_supabase.py --league nba --db nba_elo.db
    python export_to_supabase.py --league wnba --db wnba_elo.db

WHAT THIS DOES
--------------
1. teams              — resolves each opaque team_id (e.g. "nba_0003") to its
                         CURRENT 3-letter code and full name, using team_history
                         (the row with end_season IS NULL is "current"). Marks a
                         team `active` if that current code appears in this
                         league's live site config (lib/sports/{league}/config.js)
                         — i.e. it's a team the site actually displays today.
                         Variant-independent - written once, not per variant.
2. games               — one row per team per game, copied from the `ratings`
                         table, with team/opponent remapped from opaque IDs to
                         current codes. Written once per entry in VARIANTS
                         (currently 'echo' and 'pulse'), reading only that
                         variant's rows from `ratings`.
3. schedule            — one row per team per UPCOMING (unplayed) game, copied
                         from `schedule` joined against schedule_predictions
                         for the variant being exported (Elo's predicted win
                         probability differs by variant once ratings diverge).
                         Fully replaced on every run (delete-then-insert per
                         league/variant, not upserted) — see build_schedule()
                         docstring for why an upsert alone isn't enough here.
4. preseason_ratings   — APPROXIMATED as each team's `pre_rate` from its
                         first chronological game of a season, per variant.
                         This isn't necessarily identical to a true "preseason"
                         figure if the source system computes one separately —
                         flagged as an approximation, not verified against
                         source intent.

WHAT THIS DOES NOT DO YET
--------------------------
- No `standings` table population — deferred. The site's Standings tab
  already derives everything it needs from game-level data directly
  (same pattern as StandingsTab.jsx's mock data), so a separately
  maintained standings table isn't blocking anything yet. Revisit if a
  need for it becomes concrete (e.g. an All-Time champions page).
- `conference`/`division` columns in the new `teams` table are left NULL
  intentionally. Per the project's architecture, that display metadata
  comes from lib/sports/{league}/config.js at render time, not the
  database — this export only needs to satisfy the FK from games/standings.
"""
import argparse
import os
import sqlite3
import sys

from tiebreakers import check_tiebreakers

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — fine for --dry-run, needed for a real run

# Current, live-site team codes per league — used only to set `active` on
# historical teams. Source of truth is each league's config.js; keep this
# in sync manually if a team is added/removed from the live site.
ACTIVE_CODES = {
    "nba": {
        "ATL", "BOS", "BRK", "CHH", "CHI", "CLE", "DAL", "DEN", "DET", "GSW",
        "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NOP", "NYK",
        "OKC", "ORL", "PHI", "PHX", "POR", "SAS", "SAC", "TOR", "UTA", "WAS",
    },
    "wnba": {
        "ATL", "CHI", "CON", "IND", "NYL", "TOR", "WAS", "DAL", "GSV", "LVA",
        "LAS", "MIN", "PHX", "POR", "SEA",
    },
    # Each code here is a franchise's CURRENT code (matches id_to_code's
    # output, and lib/sports/nfl/config.js's team keys) - LV/LAC/LAR, not
    # the old OAK/SD/STL, since those relocations are tracked via
    # franchise.py's --alias mechanism and every exported row uses the
    # current code (see build_games()/build_teams()'s id_to_code lookup).
    "nfl": {
        "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE", "DAL", "DEN",
        "DET", "GB", "HOU", "IND", "JAX", "KC", "MIA", "MIN", "NE", "NO",
        "NYG", "NYJ", "LV", "PHI", "PIT", "LAC", "SEA", "SF", "LAR", "TB",
        "TEN", "WAS",
    },
}

SPORT_FOR_LEAGUE = {
    "nba": "basketball",
    "wnba": "basketball",
    "nfl": "football",
}

# Both rating variants this export moves over. 'echo' is the original
# continuous-carryover model (formerly branded "Continelo" - renamed
# here and throughout this file's comments/output, though the site's
# ?variant= query param and any already-written Supabase rows under
# the old name are a separate cleanup, not touched by this script).
# 'pulse' resets every team to base rating at the start of each season.
# Every table this script writes (`ratings`/`schedule_predictions`/
# `season_projections` locally, `games`/`schedule`/`season_projections`
# on Supabase) is already variant-scoped, so adding a third variant
# later is just adding its name here.
VARIANTS = ("echo", "pulse")


def format_round(round_val):
    """
    games.round and schedule.round are TEXT columns on Supabase, but the
    source SQLite columns are REAL for NBA/WNBA (e.g. 1.0, 2.0, 0.5,
    0.1) - stringifying a Python float directly produces trailing-.0
    strings ("1.0", "2.0") for whole-number rounds, which then fail to
    match the roundLabels config keys ('1', '2', '3', '4') and any
    app-side string comparisons that expect the plain integer form.
    Fractional rounds (0.5 = play-in, 0.1 = in-season tournament) are
    left as-is since they're not whole numbers and their config keys
    already include the decimal.

    NFL's round column is TEXT to begin with ('WC', 'DV', 'CC', 'SB') -
    not a stringified float at all, so float(round_val) would raise
    ValueError on it. Any round value that isn't parseable as a float
    is passed through unchanged rather than reformatted - this covers
    NFL today, and any other league that ever uses text round codes
    instead of numeric ones, without needing a per-league branch here.
    """
    if round_val is None:
        return None
    try:
        f = float(round_val)
    except (TypeError, ValueError):
        return str(round_val)
    return str(int(f)) if f == int(f) else str(f)


def resolve_current_codes(conn):
    """
    Returns {team_id: (current_code, full_name)} for every team_id in the
    SQLite database, using the team_history row with end_season IS NULL as
    the "current" identity. Falls back to the row with the highest
    start_season if none has a NULL end_season (shouldn't happen in
    practice, but better to fall back than crash).
    """
    cur = conn.cursor()
    cur.execute("SELECT team_id, team_name FROM teams")
    full_names = dict(cur.fetchall())

    cur.execute(
        "SELECT team_id, code, start_season, end_season FROM team_history "
        "ORDER BY team_id, start_season"
    )
    by_team = {}
    for team_id, code, start, end in cur.fetchall():
        by_team.setdefault(team_id, []).append((code, start, end))

    result = {}
    for team_id, rows in by_team.items():
        current = next((r for r in rows if r[2] is None), None)
        if current is None:
            current = max(rows, key=lambda r: r[1])  # highest start_season
        code = current[0]
        result[team_id] = (code, full_names.get(team_id, code))
    return result


def build_teams(conn, league, id_to_code):
    sport = SPORT_FOR_LEAGUE[league]
    active_set = ACTIVE_CODES[league]
    rows = []
    seen_codes = set()
    for team_id, (code, full_name) in id_to_code.items():
        if code in seen_codes:
            continue  # a code should map to exactly one team_id; guard anyway
        seen_codes.add(code)
        rows.append(
            {
                "league": league,
                "team_id": code,
                "sport": sport,
                "full_name": full_name,
                "city": None,          # comes from config.js at render time
                "nickname": None,      # comes from config.js at render time
                "conference": None,    # intentional — see module docstring
                "division": None,      # intentional — see module docstring
                "active": code in active_set,
            }
        )
    return rows


TEAM_HISTORY_COLUMNS = [
    "league", "team_id", "code", "name", "start_season", "end_season",
    "primary_color", "secondary_color", "tertiary_color",
]


def build_team_history(conn, league, id_to_code):
    """
    Franchise identity history (e.g. Seattle SuperSonics 1996-2008 -> OKC
    2009-present) — source of truth is the local team_history table, keyed
    to the CURRENT code (same team_id every other exported table uses) so
    the frontend can join on it directly. This is what powers season-aware
    historical names/abbreviations/logos on the All-Time and Team pages —
    deliberately not a hand-maintained JS map (the old site's
    DISPLAY_IDENTITIES/FRANCHISE_ABBRS), since this data already exists,
    is per-league (not NBA-only — WNBA has real relocations too, e.g.
    Utah Starzz -> San Antonio -> Las Vegas Aces), and won't drift from
    whatever's actually in the database.

    primary/secondary/tertiary colors are frequently NULL — most eras
    don't have colors backfilled yet (see DBs/seed_historical_colors.py
    and db.py's set_era_colors/franchise.py's set-colors command). Callers
    fall back to the current team's colors from config.js in that case,
    same fallback shape as name/code falling back to the current identity.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT team_id, code, name, start_season, end_season, "
        "primary_color, secondary_color, tertiary_color "
        "FROM team_history ORDER BY team_id, start_season"
    )
    rows = []
    for team_id, code, name, start, end, pri, sec, ter in cur.fetchall():
        current_code = id_to_code.get(team_id, (team_id, None))[0]
        rows.append({
            "league": league,
            "team_id": current_code,
            "code": code,
            "name": name,
            "start_season": start,
            "end_season": end,
            "primary_color": pri,
            "secondary_color": sec,
            "tertiary_color": ter,
        })
    return rows


GAMES_COLUMNS = [
    "game_id", "team_id", "date", "season", "type", "round", "opponent_id",
    "home_away", "points_for", "points_against", "ot", "days_off",
    "opp_days_off", "rest_diff", "rest_adj", "pre_gm_rate", "opp_pre_gm_rate",
    "expected_win_pct", "mov", "result", "accuracy", "brier", "mov_mult",
    "games_played", "k", "po_mult", "k_eff", "rating_change", "post_gm_rate",
    "w", "l", "t", "r1w", "r1l", "r2w", "r2l", "r3w", "r3l", "fw", "fl",
]


def build_games(conn, league, id_to_code, variant):
    cur = conn.cursor()
    cur.execute(
        "SELECT game_id, team, opponent, home_away, date, season, type, "
        "round, games_played, days_off, opp_days_off, rest_adj, pre_rate, "
        "opp_pre_rate, expected_win, points_for, points_against, ot, mov, "
        "result, accuracy, brier, mov_mult, po_mult, k, keff, "
        "rating_change, post_rate, w, l, t, r1w, r1l, r2w, r2l, r3w, r3l, fw, fl "
        "FROM ratings WHERE variant = ?", (variant,)
    )
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        r = dict(zip(cols, raw))
        team_code = id_to_code.get(r["team"], (r["team"], None))[0]
        opp_code = id_to_code.get(r["opponent"], (r["opponent"], None))[0]
        rows.append(
            {
                "game_id": str(r["game_id"]),
                "league": league,
                "variant": variant,
                "team_id": team_code,
                "date": r["date"],
                "season": r["season"],
                "type": r["type"],
                "round": format_round(r["round"]),
                "opponent_id": opp_code,
                "home_away": r["home_away"],
                "points_for": r["points_for"],
                "points_against": r["points_against"],
                "ot": r["ot"],
                "days_off": r["days_off"],
                "opp_days_off": r["opp_days_off"],
                "rest_diff": (
                    None
                    if r["days_off"] is None or r["opp_days_off"] is None
                    else r["days_off"] - r["opp_days_off"]
                ),
                "rest_adj": r["rest_adj"],
                "pre_gm_rate": r["pre_rate"],
                "opp_pre_gm_rate": r["opp_pre_rate"],
                "expected_win_pct": r["expected_win"],
                "mov": r["mov"],
                "result": r["result"],
                "accuracy": r["accuracy"],
                "brier": r["brier"],
                "mov_mult": r["mov_mult"],
                "games_played": r["games_played"],
                "k": r["k"],
                "po_mult": r["po_mult"],
                "k_eff": r["keff"],
                "rating_change": r["rating_change"],
                "post_gm_rate": r["post_rate"],
                "w": r["w"],
                "l": r["l"],
                "t": r["t"],
                "r1w": r["r1w"], "r1l": r["r1l"],
                "r2w": r["r2w"], "r2l": r["r2l"],
                "r3w": r["r3w"], "r3l": r["r3l"],
                "fw": r["fw"], "fl": r["fl"],
            }
        )
    return rows


SCHEDULE_COLUMNS = [
    "team_id", "date", "season", "type", "round", "opponent_id", "home_away",
    "neutral", "expected_win_pct", "days_off", "opp_days_off", "rest_diff", "rest_adj",
]


def build_schedule(conn, league, id_to_code, variant):
    """
    Mirrors build_games(), but reads from `schedule` LEFT JOINed against
    schedule_predictions for this variant (upcoming, unplayed games,
    with Elo's prediction already written by add_season.py's
    write_schedule_predictions()) instead of `ratings`. Two rows per
    game — home + away perspective — same convention as build_games(),
    so GamesPanel.jsx can render both with shared logic.

    Unlike games (which only ever grows, so an upsert is safe), a game
    can DISAPPEAR from the local `schedule` table entirely once it's
    played (add_season.py's prune_played_schedule_rows() deletes it).
    An upsert alone can't express "this row shouldn't exist anymore" —
    it only knows how to insert or update, never remove. So the caller
    (write_to_supabase()) deletes this league/variant's existing
    schedule rows before inserting this run's fresh set, rather than
    upserting. `schedule` is small (a handful of upcoming games at any
    time) and fully recomputed every run, so a full replace is cheap
    and simpler than trying to diff out exactly which rows to remove.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT s.schedule_id, s.date, s.season, s.type, s.round, s.home_team, "
        "s.away_team, s.neutral, p.expected_win_home, p.expected_win_away, "
        "p.home_days_off, p.away_days_off, p.rest_adj "
        "FROM schedule s LEFT JOIN schedule_predictions p "
        "ON p.schedule_id = s.schedule_id AND p.variant = ?", (variant,)
    )
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        r = dict(zip(cols, raw))
        home_code = id_to_code.get(r["home_team"], (r["home_team"], None))[0]
        away_code = id_to_code.get(r["away_team"], (r["away_team"], None))[0]
        round_ = format_round(r["round"])

        home_days_off = r["home_days_off"]
        away_days_off = r["away_days_off"]
        rest_diff_home = (
            None if home_days_off is None or away_days_off is None
            else home_days_off - away_days_off
        )
        # Convention: the stored `rest_adj` column is always the HOME
        # side's value. engine.py's clamp is symmetric (±16 both
        # directions), so the away side's is always exactly its
        # negation — see write_schedule_predictions() in add_season.py.
        rest_adj_home = r["rest_adj"]
        rest_adj_away = None if rest_adj_home is None else -rest_adj_home

        base = dict(
            league=league, variant=variant, date=r["date"], season=r["season"],
            type=r["type"], round=round_, neutral=r["neutral"],
        )
        rows.append({
            **base,
            "team_id": home_code, "opponent_id": away_code, "home_away": "H",
            "expected_win_pct": r["expected_win_home"],
            "days_off": home_days_off, "opp_days_off": away_days_off,
            "rest_diff": rest_diff_home, "rest_adj": rest_adj_home,
        })
        rows.append({
            **base,
            "team_id": away_code, "opponent_id": home_code, "home_away": "A",
            "expected_win_pct": r["expected_win_away"],
            "days_off": away_days_off, "opp_days_off": home_days_off,
            "rest_diff": None if rest_diff_home is None else -rest_diff_home,
            "rest_adj": rest_adj_away,
        })
    return rows


PROJECTION_COLUMNS = [
    "season", "team_id", "avg_wins", "p10_wins", "median_wins", "p90_wins",
    "avg_rating", "prob_finish_first", "trials", "remaining_games", "computed_at",
]


def build_season_projection(conn, league, id_to_code, variant):
    """
    Reads the local season_projections table for ONE variant (written
    by add_season.py's write_season_projection(), see that function's
    docstring) and remaps team_id from opaque local IDs to current
    codes, same as build_games() and build_schedule(). One row per
    team per season - already fully replaced locally each time it's
    recomputed, so this just mirrors whatever's currently there; a
    season with no remaining games has no rows here at all (cleared
    locally once the season ends).
    """
    cur = conn.cursor()
    cur.execute(
        f"SELECT {', '.join(PROJECTION_COLUMNS)} FROM season_projections WHERE variant = ?",
        (variant,)
    )
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        r = dict(zip(cols, raw))
        code = id_to_code.get(r["team_id"], (r["team_id"], None))[0]
        rows.append({
            **{c: r[c] for c in PROJECTION_COLUMNS if c != "team_id"},
            "team_id": code,
            "league": league,
            "variant": variant,
        })
    return rows


def build_preseason_ratings(games_rows):
    """
    APPROXIMATION: uses each team's earliest game of a season as a proxy
    for a "preseason" rating (its pre_gm_rate). Not verified against
    whatever the source engine considers a true preseason value — flagged
    for a look if that turns out to matter (e.g. if there's a real
    preseason projection distinct from "rating entering game 1").
    """
    earliest = {}
    for g in games_rows:
        key = (g["league"], g["season"], g["variant"], g["team_id"])
        if key not in earliest or g["date"] < earliest[key]["date"]:
            earliest[key] = g
    return [
        {
            "league": g["league"],
            "season": g["season"],
            "variant": g["variant"],
            "team_id": g["team_id"],
            "preseason_elo": g["pre_gm_rate"],
        }
        for g in earliest.values()
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", required=True, choices=list(SPORT_FOR_LEAGUE))
    parser.add_argument("--db", required=True, help="Path to the SQLite .db file")
    parser.add_argument("--dry-run", action="store_true", help="Don't touch Supabase, just report")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    id_to_code = resolve_current_codes(conn)
    teams_rows = build_teams(conn, args.league, id_to_code)  # variant-independent, built once
    team_history_rows = build_team_history(conn, args.league, id_to_code)  # also variant-independent
    name_by_code = {t["team_id"]: t["full_name"] for t in teams_rows}

    games_rows, schedule_rows, projection_rows = [], [], []
    for variant in VARIANTS:
        variant_games = build_games(conn, args.league, id_to_code, variant)
        # Real-rule standings tiebreaker check, before anything is written —
        # prompts right here in the terminal if two teams are still tied
        # after every real criterion (see tiebreakers.py for the full
        # procedure). Runs on every export, dry-run or not, since a tie is
        # a tie regardless of whether this run pushes to Supabase.
        check_tiebreakers(variant_games, args.league, variant, name_by_code, interactive=True)
        games_rows += variant_games
        schedule_rows += build_schedule(conn, args.league, id_to_code, variant)
        projection_rows += build_season_projection(conn, args.league, id_to_code, variant)
    preseason_rows = build_preseason_ratings(games_rows)
    conn.close()

    print(f"League: {args.league}  (variants: {', '.join(VARIANTS)})")
    print(f"  teams: {len(teams_rows)} rows "
          f"({sum(1 for t in teams_rows if t['active'])} active, "
          f"{sum(1 for t in teams_rows if not t['active'])} historical)")
    print(f"  team_history: {len(team_history_rows)} rows")
    print(f"  games: {len(games_rows)} rows")
    print(f"  schedule: {len(schedule_rows)} rows "
          f"({len(schedule_rows) // 2 // len(VARIANTS)} upcoming game(s) per variant)")
    print(f"  season_projections: {len(projection_rows)} rows")
    print(f"  preseason_ratings: {len(preseason_rows)} rows")
    print()

    print("Sample team rows:")
    for t in teams_rows[:5]:
        print("  ", t)
    print()

    print("Sample game rows:")
    for g in games_rows[:2]:
        print("  ", g)
    print()

    if schedule_rows:
        print("Sample schedule rows:")
        for s in schedule_rows[:2]:
            print("  ", s)

    if projection_rows:
        print("Sample season projection rows:")
        for p in projection_rows[:2]:
            print("  ", p)

    if args.dry_run:
        print("\n[dry run] No Supabase connection made, nothing written.")
        return

    write_to_supabase(teams_rows, team_history_rows, games_rows, schedule_rows,
                       projection_rows, preseason_rows, args.league)


def write_to_supabase(teams_rows, team_history_rows, games_rows, schedule_rows,
                       projection_rows, preseason_rows, league):
    import psycopg2
    from psycopg2.extras import execute_values

    db_host = os.environ.get("SUPABASE_DB_HOST")
    db_port = os.environ.get("SUPABASE_DB_PORT", "5432")
    db_name = os.environ.get("SUPABASE_DB_NAME", "postgres")
    db_user = os.environ.get("SUPABASE_DB_USER")
    db_pass = os.environ.get("SUPABASE_DB_PASS")

    if not all([db_host, db_user, db_pass]):
        print(
            "Missing SUPABASE_DB_HOST / SUPABASE_DB_USER / SUPABASE_DB_PASS "
            "environment variables. Set them in a .env file (see bottom of "
            "this script) and make sure something loads it (e.g. "
            "python-dotenv), or export them in your shell before running."
        )
        sys.exit(1)

    conn = psycopg2.connect(
        host=db_host, port=db_port, dbname=db_name, user=db_user, password=db_pass
    )
    cur = conn.cursor()

    execute_values(
        cur,
        """
        INSERT INTO teams (league, team_id, sport, full_name, city, nickname,
                            conference, division, active)
        VALUES %s
        ON CONFLICT (league, team_id) DO UPDATE SET
            full_name = EXCLUDED.full_name,
            active = EXCLUDED.active
        """,
        [
            (
                t["league"], t["team_id"], t["sport"], t["full_name"],
                t["city"], t["nickname"], t["conference"], t["division"],
                t["active"],
            )
            for t in teams_rows
        ],
    )
    print(f"Wrote {len(teams_rows)} team rows.")

    if team_history_rows:
        execute_values(
            cur,
            f"""
            INSERT INTO team_history ({', '.join(TEAM_HISTORY_COLUMNS)})
            VALUES %s
            ON CONFLICT (league, team_id, code, start_season) DO UPDATE SET
                name = EXCLUDED.name,
                end_season = EXCLUDED.end_season,
                primary_color = EXCLUDED.primary_color,
                secondary_color = EXCLUDED.secondary_color,
                tertiary_color = EXCLUDED.tertiary_color
            """,
            [tuple(h[c] for c in TEAM_HISTORY_COLUMNS) for h in team_history_rows],
        )
    print(f"Wrote {len(team_history_rows)} team_history rows.")

    execute_values(
        cur,
        f"""
        INSERT INTO games ({', '.join(GAMES_COLUMNS)}, league, variant)
        VALUES %s
        -- Unqualified ON CONFLICT DO NOTHING (no target columns) so this
        -- swallows a conflict against EITHER of the two unique constraints
        -- games can hit: the natural key (idx_games_natural_key - guards
        -- against re-exporting the same game twice under a different
        -- game_id after a local rebuild, see d2b92ec) AND the primary key
        -- (game_id, league, variant, team_id). Targeting only the natural
        -- key here caused a crash: when format_round() changed how `round`
        -- is stringified (see format_round() above), an already-exported
        -- row's natural key no longer matched (different round string),
        -- so Postgres attempted a real insert instead of skipping it - and
        -- that insert then hit the *primary* key, which a natural-key-only
        -- ON CONFLICT target doesn't cover, raising an unhandled
        -- UniqueViolation instead of silently no-op'ing like intended.
        -- Trade-off: a genuine field correction on an existing row (e.g. a
        -- fixed score, or this round-format change) won't overwrite what's
        -- already in Supabase - it'll just be skipped. That's the same
        -- "replace never happens on conflict" behavior this already had,
        -- just now safe instead of crashing. A one-time backfill UPDATE is
        -- the right tool if old `round` strings ever need correcting in
        -- place - see the note in HANDOFF.
        ON CONFLICT DO NOTHING
        """,
        [
            tuple(g[c] for c in GAMES_COLUMNS) + (g["league"], g["variant"])
            for g in games_rows
        ],
    )
    print(f"Wrote {len(games_rows)} game rows.")

    # schedule is fully replaced, not upserted — see build_schedule()'s
    # docstring for why an upsert alone can't handle a game leaving the
    # schedule once it's been played. Deletes once per variant, since
    # games_rows/schedule_rows now carry multiple variants combined -
    # a single DELETE with one variant would leave the other variant's
    # old rows behind uncleared.
    for variant in VARIANTS:
        cur.execute(
            "DELETE FROM schedule WHERE league = %s AND variant = %s",
            (league, variant),
        )
    if schedule_rows:
        execute_values(
            cur,
            f"INSERT INTO schedule ({', '.join(SCHEDULE_COLUMNS)}, league, variant) VALUES %s",
            [
                tuple(s[c] for c in SCHEDULE_COLUMNS) + (s["league"], s["variant"])
                for s in schedule_rows
            ],
        )
    print(f"Wrote {len(schedule_rows)} schedule rows "
          f"(replaced this league's prior schedule rows for every variant).")

    # season_projections is fully replaced too, same reasoning as
    # schedule - a season that's ended locally has zero rows here, and
    # that absence needs to actually delete the stale Supabase rows,
    # not just leave last week's "final" projection sitting there
    # looking current. Same per-variant loop as schedule above.
    for variant in VARIANTS:
        cur.execute(
            "DELETE FROM season_projections WHERE league = %s AND variant = %s",
            (league, variant),
        )
    if projection_rows:
        execute_values(
            cur,
            f"INSERT INTO season_projections ({', '.join(PROJECTION_COLUMNS)}, league, variant) VALUES %s",
            [
                tuple(p[c] for c in PROJECTION_COLUMNS) + (p["league"], p["variant"])
                for p in projection_rows
            ],
        )
    print(f"Wrote {len(projection_rows)} season projection rows "
          f"(replaced this league's prior projection rows for every variant).")

    execute_values(
        cur,
        """
        INSERT INTO preseason_ratings (league, season, variant, team_id, preseason_elo)
        VALUES %s
        ON CONFLICT (league, season, variant, team_id) DO UPDATE SET
            preseason_elo = EXCLUDED.preseason_elo
        """,
        [
            (p["league"], p["season"], p["variant"], p["team_id"], p["preseason_elo"])
            for p in preseason_rows
        ],
    )
    print(f"Wrote {len(preseason_rows)} preseason rating rows.")

    conn.commit()
    cur.close()
    conn.close()
    print("Done.")


if __name__ == "__main__":
    main()

# .env file this script expects for a real (non-dry-run) run:
#
# SUPABASE_DB_HOST=db.xxxxxxxxxxxx.supabase.co
# SUPABASE_DB_PORT=5432
# SUPABASE_DB_NAME=postgres
# SUPABASE_DB_USER=postgres
# SUPABASE_DB_PASS=your_new_rotated_password
#
# These come from the Supabase project's connection info — NOT your
# Supabase account login. Load it with `pip install python-dotenv` and
# `from dotenv import load_dotenv; load_dotenv()` at the top of this file
# if you want it read automatically, or just export the variables in your
# shell before running.
