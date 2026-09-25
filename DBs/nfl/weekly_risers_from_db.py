"""
weekly_risers_from_db.py — pulls "this week's winners, ranked by rating
gain" straight out of nfl_elo.db and renders the same card as
weekly_risers_card.py. Nothing to paste in by hand:

    cd DBs
    python3 -c "
    from weekly_risers_from_db import generate_weekly_risers_card_from_db
    print(generate_weekly_risers_card_from_db(season=2026, week=1))
    "

Run it any time after a week's Monday Night game has been loaded via
add_season.py - it reads whatever's already in `ratings` for that
week, so there's no separate step to "compute" the risers first.

WHY THIS NEEDS rebuild.py's week bucketing:
`games` and `ratings` don't store a week number - `round` is just
'RS' for every regular-season game (or a playoff code). The week each
game belongs to only exists as something rebuild.py computes on the
fly (rebuild._week_buckets, anchored to that season's own opener via
engine.week_from_date) while replaying games into ratings - it's never
written back to a column. So this file calls that exact same
bucketing function rather than re-guessing date ranges itself; if
engine.week_from_date's logic ever changes, this stays correct
automatically instead of quietly drifting out of sync with what
"week 1" meant when the ratings were actually computed.

WHY rating_change ALONE, filtered to w=1:
`ratings` has one row per team per game, and rating_change is exactly
"how much this team's rating moved" for that game - already computed,
already stored. Filtering to w=1 mirrors what you did by hand: only
that week's winners get ranked. (A blowout loss can still gain more
raw rating than a narrow win with these mov-multiplier engines, but
"biggest risers" as a post concept has always meant winners here, so
this keeps that meaning rather than silently becoming "biggest rating
movers regardless of result.")
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import db
from rebuild import _week_buckets

# This file lives in DBs/nfl/, same as db.py/rebuild.py/engine.py (each
# sport has its own copy of those three). export_to_supabase.py and
# weekly_risers_card.py are shared one level up, in DBs/ itself -
# same reason add_season.py adds this same path before importing
# social_card.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # DBs/
from export_to_supabase import resolve_current_codes
from weekly_risers_card import render_risers_card

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "nfl_elo.db")


def get_week_risers(conn, season: int, week: int, variant: str = "echo") -> list[tuple[str, float]]:
    """Returns [(team_code, rating_change), ...] for that week's
    winners, highest gain first. Raises ValueError with the season's
    available week numbers if `week` doesn't exist yet (e.g. it hasn't
    been loaded via add_season.py, or there's a typo) rather than
    silently returning an empty card."""
    games = db.load_games(conn)
    weeks = _week_buckets(games)
    key = (season, week)
    if key not in weeks:
        available = sorted(wk for (s, wk) in weeks if s == season)
        raise ValueError(
            f"No games found for season {season}, week {week}. "
            f"Weeks on file for {season}: {available or 'none'}."
        )

    game_ids = [g["game_id"] for g in weeks[key]]
    placeholders = ",".join("?" for _ in game_ids)
    cur = conn.execute(
        f"SELECT team, rating_change FROM ratings "
        f"WHERE variant = ? AND w = 1 AND game_id IN ({placeholders}) "
        f"ORDER BY rating_change DESC",
        [variant] + game_ids,
    )
    id_to_code = resolve_current_codes(conn)
    return [(id_to_code.get(team_id, (team_id, team_id))[0], rating_change)
            for team_id, rating_change in cur.fetchall()]


def generate_weekly_risers_card_from_db(
    season: int,
    week: int,
    league: str = "nfl",
    variant: str = "echo",
    db_path: str | None = None,
):
    """End-to-end: connect, pull that week's winners + rating_change,
    render, save. Returns the saved PNG path - same output location
    and look as weekly_risers_card.generate_weekly_risers_card."""
    conn = db.connect(db_path or DB_PATH)
    rows = get_week_risers(conn, season, week, variant=variant)
    if not rows:
        raise ValueError(
            f"No winners with a recorded rating_change for season {season}, week {week} "
            f"(variant={variant!r}). Has that week been loaded with add_season.py yet?"
        )
    return render_risers_card(rows, league=league, week=week)
