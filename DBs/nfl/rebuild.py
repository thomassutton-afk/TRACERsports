"""
Replay every game in `games` into `ratings`, from scratch.

Unlike NBA/WNBA (replay strictly one game at a time, in date order),
NFL's engine processes games in WEEKLY BATCHES - see engine.py's
module docstring for why. rebuild_ratings() here groups every game by
(season, week) - using the same week_from_date() bucketing add_season.py
uses when loading new games - and calls engine.process_week() once per
week, in chronological (season, week) order.

ECHO / PULSE VARIANTS - same pair NBA/WNBA compute, same underlying
principle: Echo is the original continuous-carryover model (a team's
rating regresses toward the mean between seasons, never resets); Pulse
resets every team to base rating at the start of each season (alpha
forced to 0). The one thing genuinely different here vs. NBA/WNBA:
NFL already has its own per-season params mechanism
(db.params_for_season / param_schedule.json, from in-season tuning -
see db.py's docstring). variant_params() below composes with that
directly rather than replacing it: Echo gets whatever params_for_season
already resolves for that season; Pulse is the SAME per-season params
with alpha forced to 0.0 - so any future retuning of Echo's other
knobs (kmax, hfa, etc.) for a given season carries over to Pulse
automatically, without a second schedule file to keep in sync by hand.
"""
import db
import engine

# Every rating variant this pipeline computes. Add new variant names
# here (and make sure variant_params() below handles them) if a third
# ever gets built - nothing else in this file hardcodes the pair.
VARIANTS = ("echo", "pulse")


def variant_params(conn, variant: str, season: int) -> dict:
    """Echo uses whatever db.params_for_season() resolves for `season`
    (the tuned per-season schedule if one exists, else active_params.json,
    else the engine baseline - see db.py's params_for_season docstring).
    Pulse is always that SAME season's params with `alpha` forced to 0 -
    a full reset to base rating every season - since season-reset is the
    only difference between the two variants."""
    echo_params = db.params_for_season(conn, season)
    if variant == "echo":
        return echo_params
    if variant == "pulse":
        pulse_params = {**echo_params, "playoff_round_mult": dict(echo_params["playoff_round_mult"])}
        pulse_params["alpha"] = 0.0
        return pulse_params
    raise ValueError(f"Unknown variant {variant!r} - expected one of {VARIANTS}")


def _week_buckets(games: list[dict]) -> dict[tuple[int, int], list[dict]]:
    """Group games into (season, week), anchored to that season's own
    opener - NOT a fixed calendar date, since the season opener's
    weekday varies year to year."""
    season_start = {}
    for g in games:
        season_start.setdefault(g["season"], g["date"])
        if g["date"] < season_start[g["season"]]:
            season_start[g["season"]] = g["date"]

    weeks: dict[tuple[int, int], list[dict]] = {}
    for g in games:
        wk = engine.week_from_date(g["date"], season_start[g["season"]])
        weeks.setdefault((g["season"], wk), []).append(g)
    return weeks


def build_current_engine(conn, variant: str = "echo", resets=None, params=None) -> engine.EloEngine:
    """Replay every REAL game in the database, week by week, to get
    each team's current state for ONE variant - without writing
    anything back to the database. Shared by rebuild_ratings() (which
    also saves the per-game rows) and by predict.py/simulate_season.py
    (which only need the resulting ratings, not another database write).

    If `params` is explicitly passed, it's used for the ENTIRE replay
    as-is (a caller forcing one fixed param set for a what-if run -
    this bypasses `variant` entirely, same as before). If `params` is
    left None (the normal case), this instead looks up
    variant_params(conn, variant, season) at each season boundary -
    Echo follows db.params_for_season()'s per-season schedule, Pulse is
    that same schedule with alpha forced to 0 (see this module's
    docstring). If no param_schedule.json exists yet, this still
    resolves correctly - variant_params falls back to
    active_params.json / the engine baseline via params_for_season,
    exactly like before variants existed.

    Handles zero completed games gracefully (e.g. right after a
    from-scratch schedule-only load, before any real results exist) -
    the season used to seed initial params comes from the earliest
    upcoming `schedule` row instead of games[0], and falls back further
    to today's year if `schedule` is also empty. This case never comes
    up for NBA/WNBA (their databases always already have history by
    the time this runs), but it's a real path here the first time NFL
    data gets loaded."""
    games = db.load_games(conn)
    missing = engine.check_conf_div_coverage(games)
    if missing:
        raise RuntimeError(
            "conf_div() coverage is incomplete - fix these before replaying games:\n  "
            + "\n  ".join(missing)
        )
    resets = resets if resets is not None else db.load_resets(conn)
    use_schedule = params is None

    if games:
        seed_season = games[0]["season"]
    else:
        upcoming = db.upcoming_games(conn)
        if upcoming:
            seed_season = min(g["season"] for g in upcoming)
        else:
            from datetime import date as _date
            seed_season = _date.today().year

    eng = engine.EloEngine(
        params if not use_schedule else variant_params(conn, variant, seed_season),
        resets=resets,
    )

    weeks = _week_buckets(games)
    current_season = games[0]["season"] if games else None
    for key in sorted(weeks):
        season = key[0]
        if use_schedule and season != current_season:
            eng.params = variant_params(conn, variant, season)
            current_season = season
        week_games = sorted(weeks[key], key=lambda g: g["date"])
        game_dicts = [
            dict(date=g["date"], season=g["season"], type=g["type"], round=g["round"],
                 home_team=g["home_team"], away_team=g["away_team"],
                 home_code=g["home_code"], away_code=g["away_code"],
                 home_pts=g["home_pts"], away_pts=g["away_pts"], ot=g["ot"], neutral=g["neutral"])
            for g in week_games
        ]
        eng.process_week(game_dicts)

    return eng


def rebuild_ratings(conn, variant: str, params: dict | None = None) -> None:
    """Recompute and store ratings for ONE variant. Only that variant's
    rows in `ratings` are touched (db.clear_ratings scopes the DELETE
    to `variant`) - a different variant's ratings for the same games
    are left exactly as they were. Call once per entry in VARIANTS to
    keep every variant current."""
    games = db.load_games(conn)
    if not games:
        db.clear_ratings(conn, variant)
        conn.commit()
        return

    missing = engine.check_conf_div_coverage(games)
    if missing:
        raise RuntimeError(
            "conf_div() coverage is incomplete - fix these before rebuilding ratings:\n  "
            + "\n  ".join(missing)
        )

    resets = db.load_resets(conn)
    use_schedule = params is None
    eng = engine.EloEngine(
        params if not use_schedule else variant_params(conn, variant, games[0]["season"]),
        resets=resets,
    )

    weeks = _week_buckets(games)

    db.clear_ratings(conn, variant)
    current_season = games[0]["season"]
    for key in sorted(weeks):
        season = key[0]
        if use_schedule and season != current_season:
            eng.params = variant_params(conn, variant, season)
            current_season = season
        week_games = sorted(weeks[key], key=lambda g: g["date"])
        game_dicts = [
            dict(date=g["date"], season=g["season"], type=g["type"], round=g["round"],
                 home_team=g["home_team"], away_team=g["away_team"],
                 home_code=g["home_code"], away_code=g["away_code"],
                 home_pts=g["home_pts"], away_pts=g["away_pts"], ot=g["ot"], neutral=g["neutral"])
            for g in week_games
        ]
        results = eng.process_week(game_dicts)
        game_ids = []
        for g in week_games:
            game_ids.extend([g["game_id"], g["game_id"]])
        rows = [row for pair in results for row in pair]
        db.save_ratings(conn, variant, rows, game_ids)

    conn.commit()


def standings(conn, season: int, variant: str = "echo"):
    """Regular-season W/L/T + final rating as of end of that season's
    games seen so far, for ONE variant. Team name reflects whatever the
    franchise was actually called THAT season, via db.display_name -
    not just its current name."""
    cur = conn.execute(
        """
        SELECT r.team,
               SUM(r.w) AS wins, SUM(r.l) AS losses, SUM(r.t) AS ties,
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
        (team, db.display_name(conn, team, season), wins, losses, ties, rating)
        for team, wins, losses, ties, rating in rows
    ]


def sanity_checks(conn, seasons, variant: str = "echo") -> list[str]:
    """Basic health checks for a set of seasons, for ONE variant: no
    NaN ratings, no team missing win/loss/tie totals, no team that
    played games but has no standings row."""
    warnings = []
    for season in seasons:
        rows = standings(conn, season, variant)
        for team, name, w, l, t, rating in rows:
            if rating is None or rating != rating:  # NaN check
                warnings.append(f"Season {season}: {name} has an invalid (NaN) rating.")
            if w is None or l is None:
                warnings.append(f"Season {season}: {name} is missing win/loss totals.")
        game_teams = conn.execute(
            "SELECT DISTINCT home_team FROM games WHERE season=? "
            "UNION SELECT DISTINCT away_team FROM games WHERE season=?",
            (season, season),
        ).fetchall()
        standings_teams = {r[0] for r in rows}
        for (tid,) in game_teams:
            if tid not in standings_teams:
                warnings.append(f"Season {season}: {tid} played games but has no standings row.")
    return warnings
