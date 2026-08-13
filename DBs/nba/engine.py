"""
NBA Elo engine.

Re-implements the exact formulas found in the RawData sheet of the
original workbook (home-court adjustment, rest adjustment, margin-of-
victory multiplier, dynamic K-factor, playoff multipliers, season-to-
season regression to the mean) so that ratings can be produced,
verified, and extended to new seasons entirely in Python + SQLite.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


BASELINE_PARAMS = dict(
    alpha=0.6,       # season-to-season carry-over weight
    base=1500.0,     # league-average / expansion-team rating
    hca=84.0,        # home court advantage, in Elo points
    kmin=6.0,
    kmax=58.0,
    playoff_mult={1: 1.1, 2: 1.2, 3: 1.35, 4: 1.5, 0.5: 1.05, 0.1: 1.02},  # default 1.0
)
# These are the ORIGINAL spreadsheet's exact values (1997-1999
# verified to floating-point precision). Never mutate this dict in
# place - use default_params() to get a mutable copy. Kept frozen and
# separate from whatever's currently "active" so verify_against_workbook.py
# can always check the engine against the Excel backups regardless of
# how the live/tuned parameters have been adjusted since.
DEFAULT_PARAMS = BASELINE_PARAMS  # backward-compatible alias


def default_params() -> dict:
    """A safe, independent mutable copy of the original baseline
    parameters (including a fresh copy of the nested playoff_mult
    dict), to build tuned parameter sets from."""
    return {**BASELINE_PARAMS, "playoff_mult": dict(BASELINE_PARAMS["playoff_mult"])}


def _po_mult(game_type: str, round_: Optional[float], params: dict) -> float:
    if game_type != "P":
        return 1.0
    return params["playoff_mult"].get(round_, 1.0)


def _k_factor(games_played_this_season: int, params: dict) -> float:
    return max(params["kmin"], params["kmax"] - 0.15 * min(games_played_this_season, 82))


@dataclass
class TeamState:
    rating: float
    last_game_date: Optional[date] = None
    last_season: Optional[int] = None
    games_played_in_season: int = 0


class EloEngine:
    """
    Stateful engine that replays a chronologically-sorted list of games
    and produces one output row per team-per-game (matching the shape
    of the original RawData sheet).
    """

    def __init__(self, params: Optional[dict] = None, resets: Optional[set] = None):
        self.params = params or DEFAULT_PARAMS
        self.teams: dict[str, TeamState] = {}
        self.season_open_date: dict[int, date] = {}
        # set of (team_id, season) pairs: force this team to start this
        # season at the base rating, ignoring its actual history. Used
        # when a folded franchise's code/brand is revived later as a
        # functionally new team.
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
        the top of every process_game(), so without this guard a
        (team_id, season) reset would fire before every single game
        that season, wiping out the team's rating each time instead
        of just at the season opener.
        """
        if state.last_season == season:
            # Already entered this season - nothing to do. This guard
            # has to come first, before the reset check below, or the
            # reset would re-apply on every game of the season.
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
        # Rest days are scoped to a single season: a team's first
        # game of a new season measures days since that season's
        # opener, not days since its last game of the prior season.
        state.last_game_date = None

    def _rest_days(self, state: TeamState, game_date: date, season: int) -> int:
        if state.last_game_date is None:
            return (game_date - self.season_open_date[season]).days
        return (game_date - state.last_game_date).days - 1

    def process_game(self, g: dict) -> list[dict]:
        """
        g needs keys: date (date), season (int), type ('R'/'P'),
        round (None for regular season, else 1/2/3/4/0.5),
        home_team, away_team, home_pts, away_pts, ot (0/1)
        Returns two output rows (home-perspective, away-perspective),
        mirroring the original RawData layout.
        """
        params = self.params
        season = g["season"]
        if season not in self.season_open_date:
            self.season_open_date[season] = g["date"]

        home = self._get_or_init_team(g["home_team"])
        away = self._get_or_init_team(g["away_team"])

        self._enter_season(home, season, g["home_team"])
        self._enter_season(away, season, g["away_team"])

        home.games_played_in_season += 1
        away.games_played_in_season += 1

        days_off_home = self._rest_days(home, g["date"], season)
        days_off_away = self._rest_days(away, g["date"], season)
        rest_diff_home = days_off_home - days_off_away
        rest_diff_away = -rest_diff_home
        rest_adj_home = max(-16, min(16, rest_diff_home * 8))
        rest_adj_away = max(-16, min(16, rest_diff_away * 8))

        pre_home, pre_away = home.rating, away.rating

        hca = 0.0 if g.get("neutral") else params["hca"]
        adj_home = pre_home + hca + rest_adj_home
        adj_away = pre_away + 0 + rest_adj_away
        exp_home = 1 / (1 + 10 ** ((adj_away - adj_home) / 400))
        exp_away = 1 - exp_home

        mov = g["home_pts"] - g["away_pts"]
        result_home = 1.0 if mov > 0 else (0.5 if mov == 0 else 0.0)
        result_away = 1.0 - result_home

        ot_mult = 0.9 if g.get("ot") else 1.0
        mov_mult = ((abs(mov) + 5) ** 0.6) / (12 + 0.01 * abs(pre_home - pre_away)) * ot_mult

        po_mult = _po_mult(g["type"], g.get("round"), params)
        k_home = _k_factor(home.games_played_in_season, params)
        k_away = _k_factor(away.games_played_in_season, params)
        keff_home = k_home * po_mult
        keff_away = k_away * po_mult

        change_home = keff_home * mov_mult * (result_home - exp_home)
        change_away = keff_away * mov_mult * (result_away - exp_away)

        post_home = pre_home + change_home
        post_away = pre_away + change_away

        # commit state
        home.rating, away.rating = post_home, post_away
        home.last_game_date, away.last_game_date = g["date"], g["date"]

        def row(team_id, opp_id, is_home, pre, opp_pre, exp, pts_for, pts_against,
                games_played, days_off, opp_days_off, rest_adj, k, keff, change, post):
            result = result_home if is_home else result_away
            accuracy = 1 if ((exp >= 0.5 and result == 1) or (exp < 0.5 and result == 0)) else 0
            test = -(result * _safe_log(exp) + (1 - result) * _safe_log(1 - exp))
            brier = (exp - result) ** 2
            w = 1 if (g["type"] == "R" and result > 0.5) else 0
            l = 1 if (g["type"] == "R" and result < 0.5) else 0
            rnd = g.get("round")
            po_w = {r: (1 if (g["type"] == "P" and rnd == r and result > 0.5) else 0) for r in (1, 2, 3, 4)}
            po_l = {r: (1 if (g["type"] == "P" and rnd == r and result < 0.5) else 0) for r in (1, 2, 3, 4)}
            return dict(
                date=g["date"], season=g["season"], type=g["type"], round=rnd,
                team=team_id, opponent=opp_id, home_away="H" if is_home else "A",
                games_played=games_played, days_off=days_off, opp_days_off=opp_days_off,
                rest_adj=rest_adj, pre_rate=pre, opp_pre_rate=opp_pre,
                expected_win=exp, points_for=pts_for, points_against=pts_against,
                ot=g.get("ot", 0), mov=(pts_for - pts_against), result=result,
                accuracy=accuracy, test=test, brier=brier, mov_mult=mov_mult,
                po_mult=po_mult, k=k, keff=keff, rating_change=change, post_rate=post,
                w=w, l=l,
                r1w=po_w[1], r1l=po_l[1], r2w=po_w[2], r2l=po_l[2],
                r3w=po_w[3], r3l=po_l[3], fw=po_w[4], fl=po_l[4],
            )

        row_home = row(g["home_team"], g["away_team"], True, pre_home, pre_away, exp_home,
                        g["home_pts"], g["away_pts"], home.games_played_in_season,
                        days_off_home, days_off_away, rest_adj_home, k_home, keff_home,
                        change_home, post_home)
        row_away = row(g["away_team"], g["home_team"], False, pre_away, pre_home, exp_away,
                        g["away_pts"], g["home_pts"], away.games_played_in_season,
                        days_off_away, days_off_home, rest_adj_away, k_away, keff_away,
                        change_away, post_away)
        return [row_home, row_away]

    def current_ratings(self) -> dict[str, float]:
        return {t: s.rating for t, s in self.teams.items()}

    def _preview_season_entry(self, state: TeamState, season: int, team_id: str):
        """Read-only version of _enter_season: returns what a team's
        rating/last_game_date/games_played WOULD be entering `season`,
        without mutating anything. Used for previewing a game that
        hasn't been played yet.

        Same guard as _enter_season: if the team has already entered
        this season, its live state is the answer - a reset entry for
        (team_id, season) must not override an already-in-progress
        season, or every mid-season preview for a revived/reset team
        would predict off a phantom base rating instead of its real
        current one.
        """
        if state.last_season == season:
            return state.rating, state.last_game_date, state.games_played_in_season

        if (team_id, season) in self.resets:
            return self.params["base"], None, 0
        if state.last_season is None:
            return state.rating, state.last_game_date, state.games_played_in_season
        alpha, base = self.params["alpha"], self.params["base"]
        return alpha * state.rating + (1 - alpha) * base, None, 0

    def preview_matchup(self, home_team: str, away_team: str, game_date: date, season: int,
                         type_: str = "R", round_: Optional[float] = None,
                         neutral: bool = False) -> dict:
        """Predict the outcome of a game that HASN'T been played yet,
        using each team's current rating as-is - does not mutate any
        engine state, and does not require (or use) a score."""
        params = self.params
        home = self.teams.get(home_team) or TeamState(rating=params["base"])
        away = self.teams.get(away_team) or TeamState(rating=params["base"])

        home_rating, home_last_date, home_gp = self._preview_season_entry(home, season, home_team)
        away_rating, away_last_date, away_gp = self._preview_season_entry(away, season, away_team)

        season_open = self.season_open_date.get(season, game_date)
        days_off_home = (game_date - home_last_date).days - 1 if home_last_date else (game_date - season_open).days
        days_off_away = (game_date - away_last_date).days - 1 if away_last_date else (game_date - season_open).days
        rest_diff_home = days_off_home - days_off_away
        rest_adj_home = max(-16, min(16, rest_diff_home * 8))
        rest_adj_away = max(-16, min(16, -rest_diff_home * 8))

        hca = 0.0 if neutral else params["hca"]
        adj_home = home_rating + hca + rest_adj_home
        adj_away = away_rating + rest_adj_away
        exp_home = 1 / (1 + 10 ** ((adj_away - adj_home) / 400))

        return dict(
            home_team=home_team, away_team=away_team, date=game_date, season=season,
            type=type_, round=round_, neutral=neutral,
            home_rating=home_rating, away_rating=away_rating,
            days_off_home=days_off_home, days_off_away=days_off_away,
            rest_adj_home=rest_adj_home, rest_adj_away=rest_adj_away,
            expected_win_home=exp_home, expected_win_away=1 - exp_home,
        )


def _safe_log(x: float) -> float:
    import math
    x = min(max(x, 1e-12), 1 - 1e-12)
    return math.log(x)


def run_engine(games: list[dict], params: Optional[dict] = None) -> list[dict]:
    """games must already be sorted chronologically (date, then a stable
    tiebreaker such as game_id) before calling this."""
    engine = EloEngine(params)
    out = []
    for g in games:
        out.extend(engine.process_game(g))
    return out
