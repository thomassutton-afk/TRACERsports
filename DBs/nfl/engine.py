"""
NFL Elo engine.

Faithful reimplementation of the NFL "Continelo" workbook's Elo system
(the math previously lived directly in nfl_elo.py's compute_elo(); this
restructures it into the shared EloEngine/TeamState shape NBA/WNBA use,
without changing any of the actual formulas).

WEEKLY BATCHING - the one real structural difference from NBA/WNBA:
Games are NOT processed strictly one at a time in date order. Every
game within the same NFL week snapshots every playing team's rating
BEFORE any of that week's results are applied, and ratings only update
once, after the whole week's math is computed - see process_week().
This is deliberate: it's what lets a Thursday night game and the
following Monday night game (different calendar dates, same NFL week)
share the same starting ratings, matching how the source workbook can
only look back to an earlier WEEK, not an earlier date. Call
process_week() once per week, in chronological week order - never
process_game() on an individual game in isolation for a real result.

REST-DAY CONVENTION - also genuinely different from NBA/WNBA:
days_off here is the RAW calendar gap between a team's games (no -1),
and a team's first game of a season gets NO rest adjustment at all
(rest_adj is 0, not computed against a season-opener date). Both
match the original workbook's convention exactly - don't "fix" these
to look like NBA/WNBA's rest handling.

preview_matchup() (a single unplayed game) is unaffected by weekly
batching - it just wants each team's most recently recorded rating,
same idea as NBA/WNBA's preview.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


BASELINE_PARAMS = dict(
    alpha=0.3,             # season-to-season carry-over weight
    base=1500.0,           # league-average / expansion-team rating
    hfa=72.0,               # home field advantage, in Elo points
    kmax=46.0,
    k_floor=36.2,           # floor K decays to by the last game of the regular season
    rest_minor=6.0,         # applied for a 1-4 day rest differential (short week)
    rest_major=24.0,        # applied for a 6+ day rest differential (bye week+)
    div_game_mult=1.1,
    conf_game_mult=1.02,
    playoff_round_mult={"WC": 1.1, "DV": 1.2, "CC": 1.35, "SB": 1.5},  # default 1.0
)
# The ORIGINAL nfl_elo.py's exact locked values. Never mutate this dict
# in place - use default_params() for a mutable copy.
DEFAULT_PARAMS = BASELINE_PARAMS


def default_params() -> dict:
    """A safe, independent mutable copy of the original baseline
    parameters (including a fresh copy of the nested playoff_round_mult
    dict), to build tuned parameter sets from."""
    return {**BASELINE_PARAMS, "playoff_round_mult": dict(BASELINE_PARAMS["playoff_round_mult"])}


def week_from_date(d: date, season_start: date) -> int:
    """Bucket a game date into an NFL week number. Weeks run Tuesday ->
    Monday (the day after Monday Night Football starts a new week),
    which correctly groups a Thursday night game with the following
    Sunday/Monday slate - including the Thanksgiving game - into the
    same week. Anchored to `season_start` (that season's first game),
    not to any fixed calendar date, since the season opener's weekday
    varies year to year."""
    from datetime import timedelta
    anchor = season_start - timedelta(days=(season_start.weekday() - 1) % 7)
    return (d - anchor).days // 7 + 1


def season_length(season: int) -> int:
    """Regular-season game count. The league expanded 16 -> 17 games in
    2021; K-decay needs this because it's a fraction-of-season
    denominator, not a fixed per-game slope, so it stays correct across
    the rule change without needing separate pre/post-2021 logic
    anywhere else."""
    return 17 if season >= 2021 else 16


def _decayed_k(games_played_this_season: int, season: int, params: dict) -> float:
    """K = Kmax - (Kmax - Kfloor) * fraction of season played so far.
    games_played is 1-indexed (this game IS that count) and continues
    into the playoffs; clamped at 1.0 so K never decays past the floor
    once the regular season ends."""
    length = season_length(season)
    frac = min(games_played_this_season, length) / length
    return params["kmax"] - (params["kmax"] - params["k_floor"]) * frac


def _rest_adj(days_off: Optional[int], opp_days_off: Optional[int], params: dict) -> float:
    """Tiered rest adjustment. 0 for equal rest; +/-rest_minor for a
    1-4 day differential (short week); +/-rest_major for 6+ days (bye
    week or bigger). No 5-day case exists in real NFL scheduling, so it
    falls into the minor tier by not meeting the >=6 threshold. A
    team's first game of a season (no prior game, days_off is None) ->
    no adjustment."""
    if days_off is None or opp_days_off is None:
        return 0.0
    diff = days_off - opp_days_off
    if diff == 0:
        return 0.0
    magnitude = params["rest_major"] if abs(diff) >= 6 else params["rest_minor"]
    return magnitude if diff > 0 else -magnitude


def _po_mult(game_type: str, round_: Optional[str], params: dict) -> float:
    if game_type != "P":
        return 1.0
    return params["playoff_round_mult"].get(round_, 1.0)


# ----------------------------------------------------------------------
# Conference / division reference table, keyed on whatever code was
# actually used in the source file for that game (its home_code/
# away_code, NOT its permanent team_id) - a franchise that relocates
# gets a NEW entry here under its new code (e.g. Oakland's OAK entry
# AND Las Vegas's LV entry both exist, side by side, mapping to the
# same conference/division), rather than the old code's entry being
# edited or removed. This branches on the 2002 realignment only,
# still nothing about team_id/era history - games carry their
# home_code/away_code alongside the permanent home_team/away_team
# synthetic IDs specifically so this lookup can stay pure/DB-free here
# - see db.py's `games.home_code` / `away_code` columns. Whenever
# franchise.py relocate registers a new code via --alias, the new code
# needs a matching entry added here too - see
# engine.check_conf_div_coverage(), which rebuild.py runs before every
# rebuild specifically to catch a missing one before it reaches
# process_week() as a bare KeyError.
# ----------------------------------------------------------------------
TEAM_CONF_DIV_PRE2002 = {
    "ARI": ("NFC", "East"), "ATL": ("NFC", "West"), "BAL": ("AFC", "Central"),
    "BUF": ("AFC", "East"), "CAR": ("NFC", "West"), "CHI": ("NFC", "Central"),
    "CIN": ("AFC", "Central"), "CLE": ("AFC", "Central"), "DAL": ("NFC", "East"),
    "DEN": ("AFC", "West"), "DET": ("NFC", "Central"), "GB": ("NFC", "Central"),
    "IND": ("AFC", "East"), "JAX": ("AFC", "Central"), "KC": ("AFC", "West"),
    "MIA": ("AFC", "East"), "MIN": ("NFC", "Central"), "NE": ("AFC", "East"),
    "NO": ("NFC", "West"), "NYG": ("NFC", "East"), "NYJ": ("AFC", "East"),
    "OAK": ("AFC", "West"), "PHI": ("NFC", "East"), "PIT": ("AFC", "Central"),
    "SD": ("AFC", "West"), "SEA": ("AFC", "West"), "SF": ("NFC", "West"),
    "STL": ("NFC", "West"), "TB": ("NFC", "Central"), "TEN": ("AFC", "Central"),
    "WAS": ("NFC", "East"), "HOO": ("AFC", "Central")
}

TEAM_CONF_DIV_2002_PLUS = {
    "ARI": ("NFC", "West"), "ATL": ("NFC", "South"), "BAL": ("AFC", "North"),
    "BUF": ("AFC", "East"), "CAR": ("NFC", "South"), "CHI": ("NFC", "North"),
    "CIN": ("AFC", "North"), "CLE": ("AFC", "North"), "DAL": ("NFC", "East"),
    "DEN": ("AFC", "West"), "DET": ("NFC", "North"), "GB": ("NFC", "North"),
    "HOU": ("AFC", "South"), "IND": ("AFC", "South"), "JAX": ("AFC", "South"),
    "KC": ("AFC", "West"), "MIA": ("AFC", "East"), "MIN": ("NFC", "North"),
    "NE": ("AFC", "East"), "NO": ("NFC", "South"), "NYG": ("NFC", "East"),
    "NYJ": ("AFC", "East"), "OAK": ("AFC", "West"), "PHI": ("NFC", "East"),
    "PIT": ("AFC", "North"), "SD": ("AFC", "West"), "SEA": ("NFC", "West"),
    "SF": ("NFC", "West"), "STL": ("NFC", "West"), "TB": ("NFC", "South"),
    "TEN": ("AFC", "South"), "WAS": ("NFC", "East"),"LAR": ("NFC", "West"),
    "LAC": ("AFC", "West"), "LV": ("AFC", "West"),"WFT": ("NFC", "East")
}


def conf_div(code: str, season: int) -> tuple[str, str]:
    table = TEAM_CONF_DIV_PRE2002 if season <= 2001 else TEAM_CONF_DIV_2002_PLUS
    return table[code]


def check_conf_div_coverage(games: list[dict]) -> list[str]:
    """Return one description per (season, code) combination among these
    games' home_code/away_code that conf_div() cannot resolve - empty
    list if every code/season pair is covered.

    Call this BEFORE replaying games through process_week(), so a
    missing entry (a new team code, or a relocation whose new code
    hasn't been added to TEAM_CONF_DIV_PRE2002/TEAM_CONF_DIV_2002_PLUS
    yet) surfaces as one complete, actionable list up front - instead
    of a bare KeyError deep inside process_week() that aborts the whole
    rebuild on the FIRST missing code it happens to hit, leaving every
    other missing code (if there's more than one) undiscovered until
    the next run."""
    missing = set()
    for g in games:
        for code in (g["home_code"], g["away_code"]):
            try:
                conf_div(code, g["season"])
            except KeyError:
                missing.add((g["season"], code))
    return [
        f"season {season}: no conf_div entry for code '{code}' "
        f"(add it to TEAM_CONF_DIV_PRE2002 or TEAM_CONF_DIV_2002_PLUS in engine.py)"
        for season, code in sorted(missing)
    ]


@dataclass
class TeamState:
    rating: float
    last_game_date: Optional[date] = None
    last_season: Optional[int] = None
    games_played_in_season: int = 0


class EloEngine:
    """
    Stateful engine that replays NFL games WEEK BY WEEK (see module
    docstring) and produces one output row per team-per-game.
    """

    def __init__(self, params: Optional[dict] = None, resets: Optional[set] = None):
        self.params = params or DEFAULT_PARAMS
        self.teams: dict[str, TeamState] = {}
        # set of (team_id, season) pairs: force this team to start this
        # season at the base rating, ignoring its actual history. No
        # NFL franchise has ever needed this historically, but it's
        # kept for parity with NBA/WNBA in case one ever folds/revives.
        self.resets = resets or set()

    def _get_or_init_team(self, team_id: str) -> TeamState:
        if team_id not in self.teams:
            self.teams[team_id] = TeamState(rating=self.params["base"])
        return self.teams[team_id]

    def _enter_season(self, state: TeamState, season: int, team_id: str) -> None:
        """Apply season-to-season regression to the mean the first time
        we see a team in a new season - or a hard reset to base rating
        if this (team_id, season) is a registered revival.

        This must only run ONCE per team per season - it's called at
        the top of every process_week(), so without this guard a
        (team_id, season) reset would fire before every single week
        that season, wiping out the team's rating each time instead of
        just at the season opener.
        """
        if state.last_season == season:
            # Already entered this season - nothing to do. This guard
            # has to come first, before the reset check below, or the
            # reset would re-apply on every week of the season.
            return

        if (team_id, season) in self.resets:
            state.rating = self.params["base"]
            state.last_season = season
            state.games_played_in_season = 0
            state.last_game_date = None
            return
        if state.last_season is None:
            # Brand new team - starts flat at base (equivalent to the
            # alpha blend collapsing to `base` when prior rating == base).
            state.last_season = season
            state.games_played_in_season = 0
            return
        alpha, base = self.params["alpha"], self.params["base"]
        state.rating = alpha * state.rating + (1 - alpha) * base
        state.last_season = season
        state.games_played_in_season = 0
        # Rest days are scoped to a single season: a team's first game
        # of a new season has no prior-game date to compare against,
        # matching the "no rest adjustment on a season opener" rule.
        state.last_game_date = None

    def _days_off(self, state: TeamState, game_date: date) -> Optional[int]:
        """Raw calendar-day gap since the team's last game this season
        (NOT gap-minus-one like NBA/WNBA). None if this is the team's
        first game of the season - _rest_adj() treats None as "no
        adjustment", matching the original workbook exactly."""
        if state.last_game_date is None:
            return None
        return (game_date - state.last_game_date).days

    def process_week(self, week_games: list[dict]) -> list[list[dict]]:
        """
        Process every game in one NFL week as a single atomic batch:
        snapshot every playing team's pre-game rating BEFORE applying
        ANY of this week's results, then only apply every result once
        the whole week's math has been computed off that shared
        snapshot. See the module docstring for why this matters.

        week_games must all share the same `season`; each needs keys:
        date, season, type ('R'/'P'), round (None for regular season,
        else 'WC'/'DV'/'CC'/'SB'), home_team, away_team (permanent
        team_ids), home_code, away_code (stable NFL abbreviations, for
        the conf/div lookup), home_pts, away_pts, ot (0/1), neutral (0/1,
        default 0 if omitted - suppresses home-field advantage for the
        designated "home" team of a game at a neutral site, e.g. the
        Super Bowl; the original nfl_elo.py stored this flag but never
        actually used it, which was a real gap - fixed here).

        Returns one [row_home, row_away] list per game, in the same
        order as week_games.
        """
        if not week_games:
            return []
        season = week_games[0]["season"]

        # --- Snapshot phase: enter-season + pre-game rating/rest/games
        # played for every team playing this week, all off the SAME
        # starting state - none of this week's results are visible yet.
        pre = {}
        for g in week_games:
            for team_id in (g["home_team"], g["away_team"]):
                if team_id in pre:
                    continue
                state = self._get_or_init_team(team_id)
                self._enter_season(state, season, team_id)
                pre[team_id] = dict(
                    rating=state.rating,
                    days_off=self._days_off(state, g["date"]),
                    games_played=state.games_played_in_season,
                )

        # --- Compute phase: every game's math uses ONLY the snapshot
        # above, never another game's result from this same week.
        results = []
        deferred = []  # (team_id, new_rating, game_date, new_games_played)

        for g in week_games:
            params = self.params
            home_id, away_id = g["home_team"], g["away_team"]
            pre_home, pre_away = pre[home_id]["rating"], pre[away_id]["rating"]
            days_off_home, days_off_away = pre[home_id]["days_off"], pre[away_id]["days_off"]

            home_conf, home_div = conf_div(g["home_code"], season)
            away_conf, away_div = conf_div(g["away_code"], season)
            conf_g = int(home_conf == away_conf)
            div_g = int(conf_g and home_div == away_div)

            team_rest_adj = _rest_adj(days_off_home, days_off_away, params)
            hfa = 0.0 if g.get("neutral") else params["hfa"]

            adj_home = pre_home + hfa + team_rest_adj
            adj_away = pre_away
            exp_home = 1 / (1 + 10 ** ((adj_away - adj_home) / 400))
            exp_away = 1 - exp_home

            mov = g["home_pts"] - g["away_pts"]
            result_home = 1.0 if mov > 0 else (0.5 if mov == 0 else 0.0)
            result_away = 1.0 - result_home

            ot_mult = 0.7 if g.get("ot") else 1.0
            mov_mult = ((abs(mov) + 3) ** 0.8) / (7.5 + 0.006 * abs(pre_home - pre_away)) * ot_mult

            po_mult = _po_mult(g["type"], g.get("round"), params)
            games_played_home = pre[home_id]["games_played"] + 1
            games_played_away = pre[away_id]["games_played"] + 1
            k_home = _decayed_k(games_played_home, season, params)
            k_away = _decayed_k(games_played_away, season, params)

            group_mult = (params["div_game_mult"] if div_g else 1) * \
                         (params["conf_game_mult"] if conf_g else 1) * po_mult
            keff_home = k_home * group_mult
            keff_away = k_away * group_mult

            change_home = keff_home * mov_mult * (result_home - exp_home)
            change_away = keff_away * mov_mult * (result_away - exp_away)
            post_home = pre_home + change_home
            post_away = pre_away + change_away

            def row(team_id, opp_id, is_home, pre_r, opp_pre, exp, pts_for, pts_against,
                    games_played, days_off, opp_days_off, k, keff, change, post):
                result = result_home if is_home else result_away
                accuracy = 1 if ((exp >= 0.5 and result == 1) or (exp < 0.5 and result == 0)) else 0
                test = -(result * _safe_log(exp) + (1 - result) * _safe_log(1 - exp))
                brier = (exp - result) ** 2
                win = 1 if (g["type"] == "R" and result > 0.5) else 0
                loss = 1 if (g["type"] == "R" and result < 0.5) else 0
                tie = 1 if (g["type"] == "R" and result == 0.5) else 0
                # Playoff win/loss by round, in the same r1/r2/r3/f slots
                # NBA/WNBA use - NFL's own round labels map onto them as
                # WC->r1, DV->r2, CC->r3, SB->f (the Super Bowl is the
                # "final" slot, same idea as NBA's Finals).
                rnd = g.get("round")
                slot = {"WC": "r1", "DV": "r2", "CC": "r3", "SB": "f"}.get(rnd) if g["type"] == "P" else None
                po_w = {s: (1 if (slot == s and result > 0.5) else 0) for s in ("r1", "r2", "r3", "f")}
                po_l = {s: (1 if (slot == s and result < 0.5) else 0) for s in ("r1", "r2", "r3", "f")}
                return dict(
                    date=g["date"], season=g["season"], type=g["type"], round=g.get("round"),
                    team=team_id, opponent=opp_id, home_away="H" if is_home else "A",
                    conf_game=conf_g, div_game=div_g,
                    games_played=games_played, days_off=days_off, opp_days_off=opp_days_off,
                    rest_adj=(team_rest_adj if is_home else -team_rest_adj),
                    pre_rate=pre_r, opp_pre_rate=opp_pre,
                    expected_win=exp, points_for=pts_for, points_against=pts_against,
                    ot=g.get("ot", 0), mov=(pts_for - pts_against), result=result,
                    accuracy=accuracy, test=test, brier=brier, mov_mult=mov_mult,
                    po_mult=po_mult, k=k, keff=keff, rating_change=change, post_rate=post,
                    w=win, l=loss, t=tie,
                    r1w=po_w["r1"], r1l=po_l["r1"], r2w=po_w["r2"], r2l=po_l["r2"],
                    r3w=po_w["r3"], r3l=po_l["r3"], fw=po_w["f"], fl=po_l["f"],
                )

            row_home = row(home_id, away_id, True, pre_home, pre_away, exp_home,
                            g["home_pts"], g["away_pts"], games_played_home,
                            days_off_home, days_off_away, k_home, keff_home,
                            change_home, post_home)
            row_away = row(away_id, home_id, False, pre_away, pre_home, exp_away,
                            g["away_pts"], g["home_pts"], games_played_away,
                            days_off_away, days_off_home, k_away, keff_away,
                            change_away, post_away)
            results.append([row_home, row_away])

            deferred.append((home_id, post_home, g["date"], games_played_home))
            deferred.append((away_id, post_away, g["date"], games_played_away))

        # --- Apply phase: commit every update only now, after the
        # whole week's math has been computed off the shared snapshot.
        for team_id, new_rating, game_date, games_played in deferred:
            state = self.teams[team_id]
            state.rating = new_rating
            state.last_game_date = game_date
            state.games_played_in_season = games_played

        return results

    def current_ratings(self) -> dict[str, float]:
        return {t: s.rating for t, s in self.teams.items()}

    def _preview_season_entry(self, state: TeamState, season: int, team_id: str):
        """Read-only version of _enter_season: returns what a team's
        rating/last_game_date/games_played WOULD be entering `season`,
        without mutating anything. Used for previewing a game that
        hasn't been played yet."""
        if state.last_season == season:
            return state.rating, state.last_game_date, state.games_played_in_season

        if (team_id, season) in self.resets:
            return self.params["base"], None, 0
        if state.last_season is None:
            return state.rating, state.last_game_date, state.games_played_in_season
        alpha, base = self.params["alpha"], self.params["base"]
        return alpha * state.rating + (1 - alpha) * base, None, 0

    def preview_preseason_rating(self, team_id: str, season: int) -> float:
        """Public single-team wrapper around _preview_season_entry - no
        opponent/matchup needed. What a team's rating WOULD be entering
        `season`, with the same regression-to-mean _preview_season_entry
        already applies for preview_matchup's predictions - just exposed
        standalone, for publishing preseason ratings before a season's
        first game exists (see export_to_supabase.py's
        build_future_preseason_ratings). Read-only, same as
        preview_matchup - does not mutate engine state."""
        state = self.teams.get(team_id) or TeamState(rating=self.params["base"])
        rating, _, _ = self._preview_season_entry(state, season, team_id)
        return rating

    def preview_matchup(self, home_team: str, away_team: str, game_date: date, season: int,
                         type_: str = "R", round_: Optional[str] = None,
                         home_code: Optional[str] = None, away_code: Optional[str] = None,
                         neutral: bool = False) -> dict:
        """Predict the outcome of a game that HASN'T been played yet,
        using each team's current rating as-is - does not mutate any
        engine state, and does not require (or use) a score. Unaffected
        by weekly batching: previewing doesn't need to know what week
        it is, just each team's most recently recorded state."""
        params = self.params
        home = self.teams.get(home_team) or TeamState(rating=params["base"])
        away = self.teams.get(away_team) or TeamState(rating=params["base"])

        home_rating, home_last_date, home_gp = self._preview_season_entry(home, season, home_team)
        away_rating, away_last_date, away_gp = self._preview_season_entry(away, season, away_team)

        days_off_home = (game_date - home_last_date).days if home_last_date else None
        days_off_away = (game_date - away_last_date).days if away_last_date else None
        rest_adj_home = _rest_adj(days_off_home, days_off_away, params)

        adj_home = home_rating + (0.0 if neutral else params["hfa"]) + rest_adj_home
        adj_away = away_rating
        exp_home = 1 / (1 + 10 ** ((adj_away - adj_home) / 400))

        return dict(
            home_team=home_team, away_team=away_team, date=game_date, season=season,
            type=type_, round=round_,
            home_rating=home_rating, away_rating=away_rating,
            days_off_home=days_off_home, days_off_away=days_off_away,
            rest_adj_home=rest_adj_home, rest_adj_away=-rest_adj_home,
            expected_win_home=exp_home, expected_win_away=1 - exp_home,
        )


def _safe_log(x: float) -> float:
    import math
    x = min(max(x, 1e-12), 1 - 1e-12)
    return math.log(x)
