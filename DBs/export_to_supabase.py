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
4. preseason_ratings   — two sources, per variant:
                         (a) PLAYED seasons: each team's `pre_rate` from its
                             first chronological game of the season
                             (build_preseason_ratings()).
                         (b) SCHEDULED-BUT-UNPLAYED seasons: a season whose
                             schedule is loaded but has zero games yet has no
                             game rows to read (a) from, so
                             build_future_preseason_ratings() carries each
                             team's rating is asked of the league's own
                             engine (rebuild.build_current_engine +
                             preview_preseason_rating), falling back to
                             carrying the final rating forward with the
                             carryover inferred from recent seasons. Works
                             for any league/variant with no per-league
                             config. If neither is possible it says so
                             loudly instead of writing guesses - see
                             check_preseason_coverage(). The Dashboard's
                             0-0 preseason view depends on these rows.

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
import importlib
import os
import sqlite3
import sys
from collections import defaultdict
from statistics import median

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

ACTIVE_CODES["cfb"] = set()  # filled from fbs_membership in main()

# Leagues with no single-table standings, so no tiebreaker check (CFB: 138 teams, ~12 conferences).
NO_TIEBREAKER_LEAGUES = {"cfb"}

SPORT_FOR_LEAGUE = {
    "nba": "basketball",
    "wnba": "basketball",
    "nfl": "football",
    "cfb": "football",
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
    "home_away", "neutral", "points_for", "points_against", "ot", "days_off",
    "opp_days_off", "rest_diff", "rest_adj", "pre_gm_rate", "opp_pre_gm_rate",
    "expected_win_pct", "mov", "result", "accuracy", "brier", "mov_mult",
    "games_played", "k", "po_mult", "k_eff", "rating_change", "post_gm_rate",
    "w", "l", "t", "r1w", "r1l", "r2w", "r2l", "r3w", "r3l", "fw", "fl",
]


def _has_column(conn, table, column):
    """True if `table` in this SQLite db has `column` (used to tolerate leagues
    whose local schema hasn't had a column added yet, e.g. CFB's `neutral`)."""
    return any(c[1] == column for c in conn.execute(f"PRAGMA table_info({table})"))

# CFB's pipeline stores bowls, the CFP and conference title games as type 'R' with a round code,
# but the site reads type 'R' as "counts toward the regular-season record" and type 'P' as
# postseason. So for CFB: bowls and CFP games export as 'P' (round kept); a conference title game
# counts toward the regular-season record, so it exports as plain 'R' with no round.
CFB_POSTSEASON_ROUNDS = {"BOWL", "CFP-R1", "CFP-QF", "CFP-SF", "NC"}


def site_type_round(league, type_, round_):
    if league != "cfb" or round_ is None:
        return type_, round_
    if round_ in CFB_POSTSEASON_ROUNDS:
        return "P", round_
    return type_, None


def build_games(conn, league, id_to_code, variant):
    cur = conn.cursor()
    # A ratings table without a `neutral` column exports every game as
    # neutral = 0 instead of crashing.
    neutral_sql = "neutral" if _has_column(conn, "ratings", "neutral") else "0 AS neutral"
    cur.execute(
        f"SELECT game_id, team, opponent, home_away, {neutral_sql}, date, season, type, "
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
        g_type, g_round = site_type_round(league, r["type"], r["round"])
        rows.append(
            {
                "game_id": str(r["game_id"]),
                "league": league,
                "variant": variant,
                "team_id": team_code,
                "date": r["date"],
                "season": r["season"],
                "type": g_type,
                "round": format_round(g_round),
                "opponent_id": opp_code,
                "home_away": r["home_away"],
                "neutral": r["neutral"],
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
    "predicted_spread",
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
    has_spread = any(c[1] == "predicted_spread"
                     for c in cur.execute("PRAGMA table_info(schedule_predictions)"))
    spread_sql = "p.predicted_spread" if has_spread else "NULL AS predicted_spread"
    cur.execute(
        "SELECT s.schedule_id, s.date, s.season, s.type, s.round, s.home_team, "
        "s.away_team, s.neutral, p.expected_win_home, p.expected_win_away, "
        f"p.home_days_off, p.away_days_off, p.rest_adj, {spread_sql} "
        "FROM schedule s LEFT JOIN schedule_predictions p "
        "ON p.schedule_id = s.schedule_id AND p.variant = ?", (variant,)
    )
    cols = [d[0] for d in cur.description]
    rows = []
    for raw in cur.fetchall():
        r = dict(zip(cols, raw))
        home_code = id_to_code.get(r["home_team"], (r["home_team"], None))[0]
        away_code = id_to_code.get(r["away_team"], (r["away_team"], None))[0]
        s_type, s_round = site_type_round(league, r["type"], r["round"])
        round_ = format_round(s_round)

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
            type=s_type, round=round_, neutral=r["neutral"],
        )
        predicted_spread_home = r["predicted_spread"]
        predicted_spread_away = None if predicted_spread_home is None else -predicted_spread_home

        rows.append({
            **base,
            "team_id": home_code, "opponent_id": away_code, "home_away": "H",
            "expected_win_pct": r["expected_win_home"],
            "days_off": home_days_off, "opp_days_off": away_days_off,
            "rest_diff": rest_diff_home, "rest_adj": rest_adj_home,
            "predicted_spread": predicted_spread_home,
        })
        rows.append({
            **base,
            "team_id": away_code, "opponent_id": home_code, "home_away": "A",
            "expected_win_pct": r["expected_win_away"],
            "days_off": away_days_off, "opp_days_off": home_days_off,
            "rest_diff": None if rest_diff_home is None else -rest_diff_home,
            "rest_adj": rest_adj_away,
            "predicted_spread": predicted_spread_away,
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


# Rating every team starts from before any carryover (config.js engine.base).
ELO_BASE = 1500.0
# How many most-recent season transitions must agree on the carryover
# before it's trusted for the next one, and how closely they must agree.
CARRY_MIN_TRANSITIONS = 3
CARRY_TOLERANCE = 1e-6
# A team whose final rating is this close to base tells us nothing about
# the carryover coefficient (division by ~0), so it's left out of the fit.
CARRY_MIN_DEVIATION = 25.0


def _fit_carry(first_pre, last_post, played, league, variant, base):
    """
    Infers the carryover coefficient `a` in
        preseason = base + a * (previous_final - base)
    from the most recent season transitions already in the data
    (echo: a = alpha, e.g. 0.6 for NBA; pulse: a = 0, i.e. reset to base).
    Returns (a, None) on success or (None, reason) if the data doesn't
    support a confident answer - e.g. a league whose carryover changes
    season to season (NFL's param_schedule.json), where guessing would
    write wrong numbers.
    """
    seasons = sorted(played)
    transitions = []  # (new_season, median ratio) for transitions that fit cleanly
    for prev, new in zip(seasons, seasons[1:]):
        if new != prev + 1:
            continue
        ratios = []
        for (lg, vr, season, team), (_, pre) in first_pre.items():
            if (lg, vr, season) != (league, variant, new):
                continue
            last = last_post.get((league, variant, prev, team))
            if last is None or abs(last[1] - base) < CARRY_MIN_DEVIATION:
                continue
            ratios.append((pre - base) / (last[1] - base))
        # pulse-style variants (a == 0) have |pre - base| ~ 0 for everyone,
        # which is a perfectly consistent ratio of 0, so no special case.
        if len(ratios) < 5:
            continue
        m = median(ratios)
        agree = sum(1 for r in ratios if abs(r - m) <= CARRY_TOLERANCE) / len(ratios)
        if agree >= 0.9:
            transitions.append((new, m))
    recent = transitions[-CARRY_MIN_TRANSITIONS:]
    if len(recent) < CARRY_MIN_TRANSITIONS:
        return None, f"only {len(recent)} clean season transition(s) to learn the carryover from (need {CARRY_MIN_TRANSITIONS})"
    vals = [m for _, m in recent]
    if max(vals) - min(vals) > CARRY_TOLERANCE:
        return None, ("carryover differs between recent seasons "
                      f"({', '.join(f'{n}: {m:.6f}' for n, m in recent)}) - can't tell which applies next")
    return recent[-1][1], None


def infer_future_preseason_ratings(games_rows, schedule_rows, base=ELO_BASE):
    """
    FALLBACK for engine_future_preseason_ratings(): used only when a league's
    rebuild.py can't provide the engine's own preview.

    Preseason ratings for a season that is SCHEDULED but has no games played
    yet. build_preseason_ratings() can't cover this case - it reads each
    team's first game of the season, and there is none - so without this a
    schedule-only season has no preseason_ratings rows and the Dashboard
    (which starts from preseason_ratings, see app/[league]/page.js) shows
    "No data yet" instead of a 0-0 projected power ranking.

    Generic by construction: league-agnostic, driven only by what's in
    games_rows/schedule_rows, so a new league or season needs no code or
    config change. For each (league, variant) it finds the scheduled
    season with no played games, carries every scheduled team's FINAL
    rating from the last played season forward with the carryover the
    engine itself used (inferred, see _fit_carry()), and returns rows in
    the same shape as build_preseason_ratings().

    Skips (and reports) rather than guesses when it can't be confident:
    no prior season, an unreadable carryover, a scheduled team with no prior
    rating (expansion team) when the carryover isn't a pure reset, or a
    second future season stacked behind the first.

    Returns (rows, warnings).
    """
    played = defaultdict(set)   # (league, variant) -> seasons with games
    first_pre = {}              # (league, variant, season, team) -> (date, pre_gm_rate)
    last_post = {}              # (league, variant, season, team) -> ((date, games_played), post_gm_rate)
    for g in games_rows:
        grp = (g["league"], g["variant"])
        key = grp + (g["season"], g["team_id"])
        played[grp].add(g["season"])
        if key not in first_pre or g["date"] < first_pre[key][0]:
            first_pre[key] = (g["date"], g["pre_gm_rate"])
        order = (g["date"], g.get("games_played") or 0)
        if key not in last_post or order > last_post[key][0]:
            last_post[key] = (order, g["post_gm_rate"])

    scheduled = defaultdict(lambda: defaultdict(set))  # grp -> season -> {team}
    for r in schedule_rows:
        scheduled[(r["league"], r["variant"])][r["season"]].add(r["team_id"])

    rows, warnings = [], []
    for grp, by_season in scheduled.items():
        league, variant = grp
        future = sorted(s for s in by_season if s not in played[grp])
        if not future:
            continue
        season, extra = future[0], future[1:]
        for s in extra:
            warnings.append(f"{league}/{variant}: season {s} is also scheduled but sits behind unplayed "
                            f"season {season}; its preseason ratings can't be derived until {season} is played")
        prior = [s for s in played[grp] if s < season]
        if not prior:
            warnings.append(f"{league}/{variant}: season {season} is scheduled but no earlier season has "
                            "any games to carry ratings forward from")
            continue
        prev = max(prior)
        carry, why = _fit_carry(first_pre, last_post, played[grp], league, variant, base)
        if carry is None:
            warnings.append(f"{league}/{variant}: season {season} preseason ratings NOT written - {why}")
            continue
        missing = []
        for team in sorted(by_season[season]):
            last = last_post.get(grp + (prev, team))
            if last is not None:
                elo = base + carry * (last[1] - base)
            elif carry == 0:
                elo = base  # pure reset: a team with no history starts at base like everyone else
            else:
                missing.append(team)
                continue
            rows.append({"league": league, "season": season, "variant": variant,
                         "team_id": team, "preseason_elo": elo})
        if missing:
            warnings.append(f"{league}/{variant}: season {season} has no prior-season rating for "
                            f"{', '.join(missing)} (new franchise?) - seed them manually")
    return rows, warnings


def engine_future_preseason_ratings(conn, league, id_to_code, variant, seasons):
    """
    PRIMARY source for scheduled-but-unplayed seasons (restored from
    e690c5d, where it was first added; commit 29969f1 deleted it by
    accident while adding the `neutral` column).

    build_preseason_ratings() can only produce a row once a season's first
    REAL game has been played (it reads that game's pre_gm_rate). That
    leaves a gap right before kickoff - schedule loaded, zero games played.

    This covers it: replay every real game up to now via that league's own
    rebuild.build_current_engine (identical to what predict.py already does
    for schedule predictions), then ask the engine's
    preview_preseason_rating() - the same regression-to-mean predict.py's
    win probabilities already use - for each team's rating entering the
    season. Exact for any league, including ones whose carryover changes
    from season to season. Raises if the league's rebuild.py doesn't offer
    these hooks; the caller then falls back to infer_future_preseason_ratings().
    """
    league_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), league)
    sys.path.insert(0, league_dir)
    try:
        sys.modules.pop("rebuild", None)  # don't reuse another league's cached rebuild module
        rebuild_mod = importlib.import_module("rebuild")
        eng = rebuild_mod.build_current_engine(conn, variant)
    finally:
        sys.path.remove(league_dir)
        sys.modules.pop("rebuild", None)

    rows = []
    for season in seasons:
        for internal_id, (code, _name) in id_to_code.items():
            elo = eng.preview_preseason_rating(internal_id, season)
            if elo is None:
                continue
            rows.append({"league": league, "season": season, "variant": variant,
                         "team_id": code, "preseason_elo": float(elo)})
    return rows


def build_future_preseason_ratings(conn, league, id_to_code, games_rows, schedule_rows):
    """
    Preseason ratings for every SCHEDULED season that has no played games yet,
    for any league/variant - no per-league code or config. Once a season's
    first real game exists, build_preseason_ratings() takes over for it
    automatically and this stops producing rows for it.

    Order of preference: the league's own engine (exact), then inference from
    game history (see infer_future_preseason_ratings). Only teams actually on
    that season's schedule are kept, so defunct/historical franchises in
    id_to_code never leak into the Dashboard's preseason list.

    Returns (rows, warnings).
    """
    played = defaultdict(set)
    for g in games_rows:
        played[g["variant"]].add(g["season"])
    scheduled = defaultdict(lambda: defaultdict(set))  # variant -> season -> {team codes}
    for r in schedule_rows:
        scheduled[r["variant"]][r["season"]].add(r["team_id"])

    rows, warnings, fallback_variants = [], [], []
    for variant, by_season in scheduled.items():
        future = sorted(s for s in by_season if s not in played[variant])
        if not future:
            continue
        try:
            raw = engine_future_preseason_ratings(conn, league, id_to_code, variant, future)
        except Exception as e:  # missing rebuild.py / hook / replay failure
            warnings.append(f"{league}/{variant}: engine preview unavailable ({type(e).__name__}: {e}) "
                            "- inferring from game history instead")
            fallback_variants.append(variant)
            continue
        rows += [r for r in raw if r["team_id"] in by_season[r["season"]]]

    if fallback_variants:
        fb_rows, fb_warnings = infer_future_preseason_ratings(
            games_rows, [r for r in schedule_rows if r["variant"] in fallback_variants])
        rows += fb_rows
        warnings += fb_warnings
    return rows, warnings


def check_preseason_coverage(schedule_rows, preseason_rows):
    """
    Guard against the silent failure this file once had: a season whose
    schedule is exported but whose preseason_ratings aren't, which makes
    the Dashboard show "No data yet". Returns a list of problem strings
    (empty = every scheduled season has a preseason rating for every
    scheduled team, so nothing to worry about).
    """
    have = defaultdict(set)
    for p in preseason_rows:
        have[(p["league"], p["variant"], p["season"])].add(p["team_id"])
    need = defaultdict(set)
    for r in schedule_rows:
        need[(r["league"], r["variant"], r["season"])].add(r["team_id"])
    problems = []
    for (league, variant, season), teams in sorted(need.items()):
        gap = sorted(teams - have[(league, variant, season)])
        if gap:
            problems.append(f"{league}/{variant}/{season}: no preseason rating for "
                            f"{len(gap)} of {len(teams)} scheduled team(s)"
                            + (f" ({', '.join(gap[:6])}{'...' if len(gap) > 6 else ''})"))
    return problems


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--league", required=True, choices=list(SPORT_FOR_LEAGUE))
    parser.add_argument("--db", required=True, help="Path to the SQLite .db file")
    parser.add_argument("--dry-run", action="store_true", help="Don't touch Supabase, just report")
    parser.add_argument("--strict-preseason", action="store_true",
                        help="Abort before writing if any scheduled season lacks preseason ratings")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    if args.league == "cfb":
        ACTIVE_CODES["cfb"] = {r[0] for r in conn.execute("SELECT h.code FROM team_history h JOIN fbs_membership f ON f.team_id=h.team_id AND f.season=(SELECT MAX(season) FROM fbs_membership) WHERE h.end_season IS NULL")}
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
        if args.league not in NO_TIEBREAKER_LEAGUES:
            check_tiebreakers(variant_games, args.league, variant, name_by_code, interactive=True)
        games_rows += variant_games
        schedule_rows += build_schedule(conn, args.league, id_to_code, variant)
        projection_rows += build_season_projection(conn, args.league, id_to_code, variant)
    preseason_rows = build_preseason_ratings(games_rows)
    future_rows, future_warnings = build_future_preseason_ratings(
        conn, args.league, id_to_code, games_rows, schedule_rows)
    preseason_rows += future_rows
    coverage_problems = check_preseason_coverage(schedule_rows, preseason_rows)
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
    print(f"  preseason_ratings: {len(preseason_rows)} rows "
          f"({len(future_rows)} for scheduled-but-unplayed season(s))")
    for w in future_warnings:
        print(f"  [preseason] {w}")
    if coverage_problems:
        print()
        print("  !!! SCHEDULED SEASON(S) WITHOUT PRESEASON RATINGS - the Dashboard will show")
        print("  !!! \"No data yet\" for these until fixed:")
        for c in coverage_problems:
            print(f"  !!!   {c}")
        if args.strict_preseason:
            sys.exit("Aborting (--strict-preseason): fix the above before exporting.")
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
