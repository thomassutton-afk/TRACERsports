"""Recompute the full ratings history from the games table."""
from __future__ import annotations
import sqlite3
import engine
import db

# Every rating variant this pipeline computes. Echo is the original
# continuous-carryover model (formerly branded "Continelo"); Pulse
# resets every team to base rating at the start of each season. Add
# new variant names here (and to variant_params() below) if a third
# ever gets built - nothing else in this file hardcodes the pair.
VARIANTS = ("echo", "pulse")


def variant_params(conn: sqlite3.Connection, variant: str) -> dict:
    """Echo uses whatever's currently active (a tuned active_params.json,
    or the engine's original baseline if none exists). Pulse is always
    derived from Echo's CURRENT params with `alpha` forced to 0 - a
    full reset to base rating every season - since season-reset is the
    only difference between the two variants. This means any future
    tuning to Echo's other parameters (K-factor, home-court, etc.)
    carries over to Pulse automatically, without needing a second
    tuning file to keep in sync by hand."""
    echo_params = db.load_active_params(conn) or engine.default_params()
    if variant == "echo":
        return echo_params
    if variant == "pulse":
        pulse_params = {**echo_params, "playoff_mult": dict(echo_params["playoff_mult"])}
        pulse_params["alpha"] = 0.0
        return pulse_params
    raise ValueError(f"Unknown variant {variant!r} - expected one of {VARIANTS}")


def rebuild_ratings(conn: sqlite3.Connection, variant: str, params: dict | None = None) -> None:
    """Recompute and store ratings for ONE variant. Only that variant's
    rows in `ratings` are touched (db.clear_ratings scopes the DELETE
    to `variant`) - a different variant's ratings for the same games
    are left exactly as they were. Call once per entry in VARIANTS to
    keep every variant current."""
    if params is None:
        params = variant_params(conn, variant)
    games = db.load_games(conn)
    resets = db.load_resets(conn)
    db.clear_ratings(conn, variant)
    eng = engine.EloEngine(params, resets=resets)
    for g in games:
        rows = eng.process_game(g)
        db.save_ratings(conn, variant, rows, [g["game_id"], g["game_id"]])
    conn.commit()


def standings(conn: sqlite3.Connection, season: int, variant: str = "echo"):
    """Regular-season W/L + final rating as of end of that season's games
    seen so far, for ONE variant. Team name reflects whatever the
    franchise was actually called THAT season, via db.display_name -
    not just its current name."""
    cur = conn.execute(
        """
        SELECT r.team,
               SUM(r.w) AS wins, SUM(r.l) AS losses,
               (SELECT post_rate FROM ratings r2
                WHERE r2.team = r.team AND r2.season = r.season AND r2.variant = r.variant
                ORDER BY r2.date DESC, r2.game_id DESC LIMIT 1) AS final_rating
        FROM ratings r
        WHERE r.season = ? AND r.type = 'R' AND r.variant = ?
        GROUP BY r.team
        ORDER BY final_rating DESC
        """,
        (season, variant),
    )
    rows = cur.fetchall()
    return [
        (team, db.display_name(conn, team, season), wins, losses, rating)
        for team, wins, losses, rating in rows
    ]


def sanity_checks(conn: sqlite3.Connection, seasons, variant: str = "echo") -> list[str]:
    """Basic health checks for a set of seasons, for ONE variant: no NaN
    ratings, no team missing win/loss totals, no team that played games
    but has no standings row for this variant."""
    warnings = []
    for season in seasons:
        rows = standings(conn, season, variant)
        for team, name, w, l, rating in rows:
            if rating is None or rating != rating:  # NaN check
                warnings.append(f"[{variant}] Season {season}: {name} has an invalid (NaN) rating.")
            if w is None or l is None:
                warnings.append(f"[{variant}] Season {season}: {name} is missing win/loss totals.")
        game_teams = conn.execute(
            "SELECT DISTINCT home_team FROM games WHERE season=? "
            "UNION SELECT DISTINCT away_team FROM games WHERE season=?",
            (season, season),
        ).fetchall()
        standings_teams = {r[0] for r in rows}
        for (tid,) in game_teams:
            if tid not in standings_teams:
                warnings.append(f"[{variant}] Season {season}: {tid} played games but has no standings row.")
    return warnings


if __name__ == "__main__":
    conn = db.connect("wnba_elo.db")
    for variant in VARIANTS:
        rebuild_ratings(conn, variant)
        print(f"--- {variant} ---")
        for row in standings(conn, 1997, variant):
            print(row)
