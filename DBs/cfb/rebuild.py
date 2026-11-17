"""
Replay every game in `games` into `ratings`, from scratch.

Forked from NFL_Elo's rebuild.py - same weekly-batch replay shape (see
engine.py's module docstring for why CFB, like NFL, processes games in
WEEKLY BATCHES rather than strictly one at a time). rebuild_ratings()
here groups every game by (season, week) - using the same
week_from_date() bucketing add_season.py uses when loading new games -
and calls engine.process_week() once per week, in chronological
(season, week) order.

ECHO / PULSE VARIANTS - same pair NFL/NBA/WNBA compute, same underlying
principle: Echo is the continuous-carryover model (a team's rating
regresses toward the mean between seasons, never resets); Pulse resets
every team to base rating at the start of each season (alpha forced to
0). variant_params() below composes with db.params_for_season() (a
per-season alpha/kmax/hfa override mechanism, for future in-season
tuning) the same way NFL_Elo's does: Echo gets whatever
params_for_season already resolves for that season; Pulse is the SAME
per-season params with alpha forced to 0.0.

CONFERENCE ANNOTATION - genuinely new vs. NFL_Elo. Because CFB's
conference/division classification comes from `team_conference_history`
rather than a static in-engine table (see engine.py's module
docstring), every game dict needs home_conf/away_conf/home_div/away_div
attached BEFORE it reaches engine.process_week() or preview_matchup().
`_annotate_conferences()` below does that lookup once per game, right
after loading from the database - engine.py itself stays completely
DB-free. Until `team_conference_history` is actually populated (a
separate, not-yet-built loading process), every lookup resolves to
None and every game is scored as "not a conference/division game" -
that's an expected, harmless starting state, not a bug.

FBS ANNOTATION - `_annotate_conferences()` also attaches home_is_fbs/
away_is_fbs via db.is_fbs(), for engine.py's FCS HANDLING (see its
module docstring). Until load_conference_membership.py has been run
for a season, every team in it looks non-FBS - unlike the conference
annotation above, this is NOT a harmless default: it means every team
that season gets treated as a fixed-rating FCS opponent (no persisted
rating at all) until that catches up. load_conference_membership.py
now triggers its own rebuild specifically because of this.
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


def _annotate_conferences(conn, games: list[dict]) -> None:
    """Attach home_conf/away_conf/home_div/away_div AND home_is_fbs/
    away_is_fbs to every game dict, IN PLACE, via
    db.conference_for_season()/db.is_fbs() - see this module's
    docstring and engine.py's FCS HANDLING section. Cached per
    (team_id, season) within this call so a program's conference/FBS
    status isn't re-queried for every game it plays that season."""
    conf_cache: dict[tuple[str, int], dict | None] = {}
    fbs_cache: dict[tuple[str, int], bool] = {}

    def lookup_conf(team_id: str, season: int) -> dict | None:
        key = (team_id, season)
        if key not in conf_cache:
            conf_cache[key] = db.conference_for_season(conn, team_id, season)
        return conf_cache[key]

    def lookup_fbs(team_id: str, season: int) -> bool:
        key = (team_id, season)
        if key not in fbs_cache:
            fbs_cache[key] = db.is_fbs(conn, team_id, season)
        return fbs_cache[key]

    for g in games:
        home_era = lookup_conf(g["home_team"], g["season"])
        away_era = lookup_conf(g["away_team"], g["season"])
        g["home_conf"] = home_era["conference"] if home_era else None
        g["home_div"] = home_era["division"] if home_era else None
        g["away_conf"] = away_era["conference"] if away_era else None
        g["away_div"] = away_era["division"] if away_era else None
        g["home_is_fbs"] = lookup_fbs(g["home_team"], g["season"])
        g["away_is_fbs"] = lookup_fbs(g["away_team"], g["season"])


def _season_fbs_teams(games: list[dict]) -> dict[int, set[str]]:
    """Every FBS team_id (per each game's home_is_fbs/away_is_fbs
    annotation) known to play each season - the roster
    apply_season_entry() needs to know who requires a SEASON-ENTRY
    target. Built once from the full, already-annotated `games` list
    rather than re-querying per season boundary."""
    by_season: dict[int, set[str]] = {}
    for g in games:
        s = by_season.setdefault(g["season"], set())
        if g["home_is_fbs"]:
            s.add(g["home_team"])
        if g["away_is_fbs"]:
            s.add(g["away_team"])
    return by_season


def apply_season_entry(conn, eng: "engine.EloEngine", season: int,
                        season_team_ids: set[str], is_first_season: bool = False) -> None:
    """Apply the SEASON-ENTRY algorithm (see engine.py's module
    docstring) for every team in `season_team_ids`, mutating `eng` in
    place. Must be called ONCE per (eng, season) pair, before that
    season's first process_week() call - Step C below computes off a
    snapshot of the just-regressed returning teams, so calling this
    twice for the same season would compute it from an already-shifted
    state the second time.

    Implements the four-step process from engine.py's SEASON-ENTRY
    docstring:
      A) group every RETURNING team's current (pre-regression) rating
         by its LAST season's conference (or power/midmajor tier, for
         a returning independent).
      B) average each group, then regress every returning team toward
         its own group's average.
      C) recompute conference averages using THIS season's membership,
         but ONLY from the now-regressed returning teams (never from
         a team also debuting this same season, to avoid circularity
         between multiple teams debuting into the same conference the
         same year).
      D) for every team never tracked before (a true debut, or a
         former fixed-rating FCS opponent), assign 0.5*fcs_rating +
         0.5*(its new conference's Step C average, or the overall FBS
         average if that conference has no returning members yet).

    `is_first_season=True` (the very first season this engine instance
    has ever processed ANY game for) skips the Step D blend entirely -
    every team is "new" simultaneously at that point, so there's no
    genuine "graduated from FCS" signal to blend against; they all
    just start flat at `base`, same as NFL_Elo's original behavior for
    a from-scratch database."""
    last_season = season - 1

    returning = [tid for tid in season_team_ids if tid in eng.teams]
    debuting = [tid for tid in season_team_ids if tid not in eng.teams]

    def _avg(values: list[float], fallback: float) -> float:
        return sum(values) / len(values) if values else fallback

    if is_first_season:
        for tid in debuting:
            eng.induct_new_team(tid, season, eng.params["base"])
        return

    # --- Step A: group returning teams' CURRENT (pre-regression)
    # ratings by last season's conference, or power/midmajor tier for
    # a returning independent. A team with a TeamState that WASN'T
    # actually FBS last season (a gap/demotion year) has a stale
    # rating with no honest "last conference" to regress from - treat
    # it as a fresh debut (Step D) instead of Step A/B.
    last_conf_groups: dict[str, list[float]] = {}
    last_tier_groups: dict[str, list[float]] = {"power": [], "midmajor": []}
    last_conf_of: dict[str, "str | None"] = {}
    stale_gap = []
    for tid in returning:
        if not db.is_fbs(conn, tid, last_season):
            stale_gap.append(tid)
            continue
        era = db.conference_for_season(conn, tid, last_season)
        last_conf_of[tid] = era["conference"] if era else None
        if era:
            last_conf_groups.setdefault(era["conference"], []).append(eng.teams[tid].rating)
        else:
            last_tier_groups[db.independent_tier(tid)].append(eng.teams[tid].rating)
    returning = [tid for tid in returning if tid not in stale_gap]
    debuting = debuting + stale_gap

    overall_fbs_avg = _avg(
        [r for group in last_conf_groups.values() for r in group]
        + last_tier_groups["power"] + last_tier_groups["midmajor"],
        eng.params["base"],
    )
    last_conf_avg = {c: _avg(v, overall_fbs_avg) for c, v in last_conf_groups.items()}
    last_tier_avg = {t: _avg(v, overall_fbs_avg) for t, v in last_tier_groups.items()}

    # --- Step B: regress every returning team toward ITS group's average.
    for tid in returning:
        conf = last_conf_of.get(tid)
        target = last_conf_avg[conf] if conf else last_tier_avg[db.independent_tier(tid)]
        eng.regress_returning_team(tid, season, target)

    # --- Step C: recompute conference/tier averages using THIS
    # season's membership, from the now-regressed returning teams only
    # (a team debuting THIS season never contributes to its own
    # conference's Step C average - see docstring above on avoiding
    # circularity).
    new_conf_groups: dict[str, list[float]] = {}
    new_tier_groups: dict[str, list[float]] = {"power": [], "midmajor": []}
    for tid in returning:
        era = db.conference_for_season(conn, tid, season)
        if era:
            new_conf_groups.setdefault(era["conference"], []).append(eng.teams[tid].rating)
        elif db.is_fbs(conn, tid, season):
            new_tier_groups[db.independent_tier(tid)].append(eng.teams[tid].rating)

    overall_fbs_avg_now = _avg(
        [r for group in new_conf_groups.values() for r in group]
        + new_tier_groups["power"] + new_tier_groups["midmajor"],
        overall_fbs_avg,
    )
    new_conf_avg = {c: _avg(v, overall_fbs_avg_now) for c, v in new_conf_groups.items()}
    new_tier_avg = {t: _avg(v, overall_fbs_avg_now) for t, v in new_tier_groups.items()}

    # --- Step D: induct every never-tracked team at a 50/50 blend of
    # fcs_rating and its NEW conference's (or tier's) Step C average.
    for tid in debuting:
        era = db.conference_for_season(conn, tid, season)
        if era:
            conf_target = new_conf_avg.get(era["conference"], overall_fbs_avg_now)
        elif db.is_fbs(conn, tid, season):
            conf_target = new_tier_avg.get(db.independent_tier(tid), overall_fbs_avg_now)
        else:
            conf_target = overall_fbs_avg_now
        blended = 0.5 * eng.params["fcs_rating"] + 0.5 * conf_target
        eng.induct_new_team(tid, season, blended)


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
    the time this runs), but it's a real path here the first time CFB
    data gets loaded."""
    games = db.load_games(conn)
    _annotate_conferences(conn, games)
    resets = resets if resets is not None else db.load_resets(conn)
    use_schedule = params is None
    season_rosters = _season_fbs_teams(games)

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
    first_season = current_season
    if current_season is not None:
        apply_season_entry(conn, eng, current_season, season_rosters.get(current_season, set()),
                            is_first_season=(current_season == first_season))
    for key in sorted(weeks):
        season = key[0]
        if season != current_season:
            if use_schedule:
                eng.params = variant_params(conn, variant, season)
            apply_season_entry(conn, eng, season, season_rosters.get(season, set()),
                                is_first_season=(season == first_season))
            current_season = season
        week_games = sorted(weeks[key], key=lambda g: g["date"])
        game_dicts = [
            dict(date=g["date"], season=g["season"], type=g["type"], round=g["round"],
                 home_team=g["home_team"], away_team=g["away_team"],
                 home_code=g["home_code"], away_code=g["away_code"],
                 home_pts=g["home_pts"], away_pts=g["away_pts"], ot=g["ot"], neutral=g["neutral"],
                 home_conf=g["home_conf"], away_conf=g["away_conf"],
                 home_div=g["home_div"], away_div=g["away_div"],
                 home_is_fbs=g["home_is_fbs"], away_is_fbs=g["away_is_fbs"],
                 home_ap_rank=g.get("home_ap_rank"), away_ap_rank=g.get("away_ap_rank"))
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
    _annotate_conferences(conn, games)
    season_rosters = _season_fbs_teams(games)

    resets = db.load_resets(conn)
    use_schedule = params is None
    eng = engine.EloEngine(
        params if not use_schedule else variant_params(conn, variant, games[0]["season"]),
        resets=resets,
    )

    weeks = _week_buckets(games)

    db.clear_ratings(conn, variant)
    current_season = games[0]["season"]
    first_season = current_season
    apply_season_entry(conn, eng, current_season, season_rosters.get(current_season, set()),
                        is_first_season=True)
    for key in sorted(weeks):
        season = key[0]
        if season != current_season:
            if use_schedule:
                eng.params = variant_params(conn, variant, season)
            apply_season_entry(conn, eng, season, season_rosters.get(season, set()),
                                is_first_season=(season == first_season))
            current_season = season
        week_games = sorted(weeks[key], key=lambda g: g["date"])
        game_dicts = [
            dict(date=g["date"], season=g["season"], type=g["type"], round=g["round"],
                 home_team=g["home_team"], away_team=g["away_team"],
                 home_code=g["home_code"], away_code=g["away_code"],
                 home_pts=g["home_pts"], away_pts=g["away_pts"], ot=g["ot"], neutral=g["neutral"],
                 home_conf=g["home_conf"], away_conf=g["away_conf"],
                 home_div=g["home_div"], away_div=g["away_div"],
                 home_is_fbs=g["home_is_fbs"], away_is_fbs=g["away_is_fbs"],
                 home_ap_rank=g.get("home_ap_rank"), away_ap_rank=g.get("away_ap_rank"))
            for g in week_games
        ]
        results = eng.process_week(game_dicts)
        # Each game now produces 0, 1, or 2 rows (see engine.py's
        # process_week docstring - a non-FBS side never gets a row),
        # so game_ids has to track actual row count per game rather
        # than assuming 2 the way NFL_Elo's version could.
        rows = []
        game_ids = []
        for g, row_list in zip(week_games, results):
            rows.extend(row_list)
            game_ids.extend([g["game_id"]] * len(row_list))
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
    NaN ratings, no team missing win/loss/tie totals, no FBS team that
    played games but has no standings row. A non-FBS opponent
    (db.is_fbs() False for that season) is EXPECTED to have no
    standings row at all - see engine.py's FCS HANDLING - so it's
    excluded from that last check rather than flagged as a bug."""
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
            if tid not in standings_teams and db.is_fbs(conn, tid, season):
                warnings.append(f"Season {season}: {tid} played games but has no standings row.")
    return warnings
