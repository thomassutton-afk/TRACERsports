"""
College Football (CFB) Elo engine.

Forked from NFL_Elo's engine.py. Same weekly-batch replay structure,
same rest-day/K-decay/margin-of-victory formulas as a starting point -
see WEEKLY BATCHING and REST-DAY CONVENTION below, both carried over
unchanged. The one REAL structural difference from the NFL version is
how conference/division games get identified - see CONFERENCE/DIVISION
LOOKUP below. Everything else in BASELINE_PARAMS is an untuned starting
point copied from NFL_Elo, not validated for CFB - see this module's
BASELINE_PARAMS comment.

WEEKLY BATCHING - carried over from NFL_Elo unchanged: games are NOT
processed strictly one at a time in date order. Every game within the
same CFB week snapshots every playing team's rating BEFORE any of that
week's results are applied, and ratings only update once, after the
whole week's math is computed - see process_week(). Call process_week()
once per week, in chronological week order - never process_game() on
an individual game in isolation for a real result.

REST-DAY CONVENTION - also carried over unchanged: days_off here is the
RAW calendar gap between a team's games (no -1), and a team's first
game of a season gets NO rest adjustment at all.

CONFERENCE/DIVISION LOOKUP - genuinely different from NFL_Elo. NFL's
conference/division assignment is a small, fixed, code-keyed table with
exactly one realignment event (2002) to branch on. CFB has 130+
programs, realignment happens most years, and a program's CODE doesn't
change when it switches conferences - a static in-engine table would
need constant hand-maintenance and would silently go stale. Instead,
each game dict passed to process_week()/preview_matchup() is expected
to already carry `home_conf`/`away_conf` (and optional `home_div`/
`away_div`), resolved by the CALLER via db.conference_for_season()
before reaching this module - see rebuild.py's `_annotate_conferences`.
This keeps the actual Elo math here just as DB-free as NFL_Elo's, while
letting conference membership live in `team_conference_history` (a
real table, editable via franchise.py's `realign` command) instead of
a hardcoded dict. A team with no conference on file for that season
(independent, or an FCS opponent with no row yet) resolves to
home_conf/away_conf of None, which this module treats as "not a
conference or division game" - never an error.

SEASON-ENTRY - genuinely new, no NFL_Elo equivalent (NFL_Elo blends
every team toward the SAME flat `base` constant between seasons). CFB
programs sit at wildly different competitive tiers that roughly track
their conference, so this engine blends toward a CONFERENCE (or
power/midmajor tier, for independents) average instead of one shared
number. This engine stays completely DB-free, same as everywhere else
in this module - the caller (rebuild.py) does every database lookup
and hands this engine two already-resolved things per season, via
regress_returning_team()/induct_new_team() below, called ONCE per
season boundary before that season's first process_week():
  - For a team already tracked (played FBS before): regress toward
    the average rating of every team that shared ITS conference LAST
    season (not this season - see rebuild.py's `_compute_season_targets`
    for why realignment year handling falls out of this naturally). An
    independent draws from the power or midmajor tier pool instead
    (Notre Dame -> power; every other independent -> midmajor).
  - For a team never tracked before (a true FBS debut, OR a former
    FCS opponent - fixed-rating, never persisted - becoming FBS for
    the first time): no prior rating exists to blend from, so it
    starts at a 50/50 blend of the fixed fcs_rating constant and its
    NEW conference's average (computed from that conference's
    already-resolved RETURNING members only, to avoid circularity
    between multiple teams debuting into the same conference the same
    season).
`base` (1500) is now only a fallback: the very first loaded season has
no prior-season data to compute any average from, and a conference
with zero already-resolved members to reference at all (its every
member is debuting the same season) falls back to the overall FBS
average.

POSTSEASON - PHASE 2 (see normalize_sr_games.py's docstring for the
full era-by-era classification rationale). Round now takes values
"CCG", "NC", "CFP-R1", "CFP-QF", "CFP-SF", and "BOWL", in addition to
None (regular season). Two separate multiplier mechanisms apply them,
both firing regardless of `type` - every CFB game, postseason
included, is still type='R' by design (see normalize_sr_games.py's
docstring on why postseason isn't reclassified as type='P'), which
means NFL_Elo's inherited playoff_round_mult mechanism (_po_mult
below) is permanently INERT for CFB - it only ever fires for type='P'
games, which never happens here. It's kept only for structural parity
with NFL_Elo; CFB's real postseason-round bump lives in the separate
postseason_round_mult dict/_postseason_mult() function instead:
  - _ccg_mult / conf_championship_mult: unchanged from Phase 1, for
    Round=="CCG".
  - _postseason_mult / postseason_round_mult: a CCG-style (type-
    agnostic) parallel to playoff_round_mult, keyed by "NC"/"CFP-R1"/
    "CFP-QF"/"CFP-SF".
  - _bowl_mult / bowl_mult + bowl_rank_*: for Round=="BOWL" only.
    Deliberately NOT a hardcoded "major bowl" name list (which would
    need the same era-branching the rest of this effort was trying to
    avoid) - instead scores bowl importance directly off the two
    teams' own AP ranks (home_ap_rank/away_ap_rank, now actually READ
    here for the first time - db.py's module docstring previously
    described these as display-only/never read by the engine; that's
    now only true outside the "BOWL" round). Both
    teams ranked -> bonus decays EXPONENTIALLY off the best possible
    combined rank (home_ap_rank + away_ap_rank, 3..49); exactly one
    team ranked -> a much smaller bump on a compressed exponential
    scale (deliberately small: a lone ranked team in a bowl is rare
    and rarely a highly-ranked one); neither ranked -> flat bowl_mult
    only.
All of postseason_round_mult, bowl_rank_bonus_max, and
bowl_one_ranked_bonus_max default to 0.0/empty (no-op) in
BASELINE_PARAMS, same "untuned placeholder" convention as
conf_championship_mult - real values need cfb_tune_engine.py against
loaded postseason data.

FCS HANDLING - genuinely new, no NFL_Elo equivalent (the NFL has no
lower-division opponents at all). CFB has 130+ programs and regularly
schedules FCS/lower-division opponents as early-season "buy games."
Since this dataset only ever
covers FBS schedules, an FCS opponent NEVER has an FCS-vs-FCS game in
it - only the occasional lopsided game against an FBS team. Tracking
an FCS opponent's OWN rating off that thin, biased sample would be
close to pure noise, and a rename mid-transition (a real case: Texas
A&M-Commerce became "East Texas A&M" while remaining FCS the whole
time) can silently split one program across two team_ids with no way
to tell they're the same school - a real problem if either side were
being tracked continuously. Instead, ANY team not recorded as FBS for
a given season (via `fbs_membership` - see db.py) is treated as a
fixed-strength opponent: process_week() substitutes a single tunable
`fcs_rating` constant for that side's rating, uses it only to compute
the FBS side's expected outcome and rating change, and never creates,
updates, or persists a TeamState or a ratings row for it. The FBS
opponent's own win/loss and rating update are entirely unaffected -
beating an FCS team still counts as a normal win, using this fixed
number as the opponent strength input. `fcs_rating` is a single global
constant, not a per-team rating - see BASELINE_PARAMS below; use
cfb_tune_engine.py to find a reasonable value once real games are
loaded.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


BASELINE_PARAMS = dict(
    alpha=0.3,             # season-to-season carry-over weight (blended against a
                            # conference/tier average now, not a flat constant - see
                            # SEASON-ENTRY above)
    base=1500.0,           # fallback only: used for the very first loaded season (no
                            # prior-season data exists yet to compute any average from)
    hfa=72.0,               # home field advantage, in Elo points
    kmax=46.0,
    k_floor=36.2,           # floor K decays to by the last game of the regular season
    rest_minor=6.0,         # applied for a 1-4 day rest differential (short week)
    rest_major=24.0,        # applied for a 6+ day rest differential (bye week+)
    conf_game_mult=1.1,     # any conference game, division or not - see SEASON-ENTRY
                            # docstring section on why div_game_mult was dropped
    conf_championship_mult=1.0,  # postseason bump for Round=="CCG" - untuned,
                                  # 1.0 is a no-op placeholder until this is tuned for real
    playoff_round_mult={},  # inherited from NFL_Elo, permanently inert for CFB - see
                             # POSTSEASON above; postseason_round_mult is CFB's real equivalent
    postseason_round_mult={},  # bump for Round in ("NC","CFP-R1","CFP-QF","CFP-SF") - see
                                # POSTSEASON above. Empty/no-op until tuned.
    bowl_mult=1.0,          # base bump for any Round=="BOWL" game - untuned no-op placeholder
    bowl_rank_bonus_max=0.0,   # extra multiplier at the best possible combined AP rank (3) for
                                # a two-ranked-team bowl, decaying to ~0 by the worst (49) - see
                                # POSTSEASON above. 0.0 is a no-op until tuned for real.
    bowl_rank_decay=0.08,      # exponential decay rate for the two-ranked-team falloff (shape
                                # placeholder - irrelevant while bowl_rank_bonus_max is 0.0)
    bowl_one_ranked_bonus_max=0.0,  # much smaller, compressed-scale bump when exactly one team
                                      # is ranked - see POSTSEASON above. Also a no-op until tuned.
    bowl_one_ranked_decay=0.05,      # decay rate for the one-ranked-team falloff (shape
                                       # placeholder, same as bowl_rank_decay above)
    fcs_rating=1200.0,      # fixed opponent strength for any non-FBS team - see FCS HANDLING above
)
# UNTUNED STARTING POINT - these are NFL_Elo's exact validated values,
# copied over as a starting point ONLY (fcs_rating and
# conf_championship_mult have no NFL_Elo equivalent at all - rough
# guesses, not validated numbers; conf_game_mult reuses NFL_Elo's old
# div_game_mult value as its starting point - see SEASON-ENTRY above).
# CFB has much higher score variance (60-3 games are common) and total
# roster turnover on a 4-5 year cycle with no draft-based parity
# mechanism, so alpha/kmax/hfa/fcs_rating/conf_game_mult should all be
# expected to need real tuning against CFB data via cfb_tune_engine.py
# before these numbers mean anything for CFB.
# Never mutate this dict in place - use default_params() for a mutable
# copy.
DEFAULT_PARAMS = BASELINE_PARAMS


def default_params() -> dict:
    """A safe, independent mutable copy of the original baseline
    parameters (including fresh copies of the nested playoff_round_mult
    and postseason_round_mult dicts), to build tuned parameter sets
    from."""
    return {
        **BASELINE_PARAMS,
        "playoff_round_mult": dict(BASELINE_PARAMS["playoff_round_mult"]),
        "postseason_round_mult": dict(BASELINE_PARAMS["postseason_round_mult"]),
    }


def week_from_date(d: date, season_start: date) -> int:
    """Bucket a game date into a CFB week number. Carried over unchanged
    from NFL_Elo: weeks run Tuesday -> Monday, which correctly groups a
    Thursday/Friday "MACtion" game with the following Saturday slate
    into the same week. Anchored to `season_start` (that season's first
    game), not to any fixed calendar date, since the season opener's
    weekday varies year to year."""
    from datetime import timedelta
    anchor = season_start - timedelta(days=(season_start.weekday() - 1) % 7)
    return (d - anchor).days // 7 + 1


# UNTUNED PLACEHOLDER: FBS teams have played a 12-game regular season
# in most years since 2006 (with occasional 13th-game exceptions for
# some programs), unlike the NFL's clean, uniform, league-wide game
# count. K-decay needs SOME fraction-of-season denominator, so this is
# a reasonable placeholder rather than a validated constant - revisit
# once postseason/conference-championship classification (deferred -
# see add_season.py's normalizer) makes it possible to compute an
# actual per-team-season game count instead of assuming one.
SEASON_LENGTH_PLACEHOLDER = 12


def season_length(season: int) -> int:
    """Regular-season game count used as the K-decay denominator. See
    SEASON_LENGTH_PLACEHOLDER above - this is a flat placeholder, not
    per-season-accurate the way NFL_Elo's was."""
    return SEASON_LENGTH_PLACEHOLDER


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


def _ccg_mult(round_: Optional[str], params: dict) -> float:
    """Conference championship bump (see this module's POSTSEASON
    docstring section). Unlike NFL_Elo's playoff_round_mult, this
    fires regardless of `type` - CCGs are still type='R' in this
    dataset (see normalize_sr_games.py's docstring on why postseason
    games aren't reclassified as type='P')."""
    if round_ == "CCG":
        return params["conf_championship_mult"]
    return 1.0


def _postseason_mult(round_: Optional[str], params: dict) -> float:
    """National championship / CFP-bracket bump (see this module's
    POSTSEASON docstring section) - a CCG-style, type-agnostic
    parallel to NFL_Elo's playoff_round_mult, needed because that
    mechanism (_po_mult above) only ever fires for type='P' games and
    every CFB game stays type='R' by design."""
    return params["postseason_round_mult"].get(round_, 1.0)


def _bowl_mult(round_: Optional[str], home_ap_rank: Optional[int],
               away_ap_rank: Optional[int], params: dict) -> float:
    """Rank-based bowl-importance bump for Round=="BOWL" games only
    (see this module's POSTSEASON docstring section for the full
    rationale - deliberately rank-driven rather than a hardcoded
    per-era "major bowl" name list).

    Combined rank (home_ap_rank + away_ap_rank) ranges from 3 (the two
    best possible teams, #1 and #2) to 49 (the two worst possible
    ranked teams, #24 and #25) when both teams are ranked - the bonus
    decays exponentially off the best-possible end of that range, so a
    top-5-vs-top-5 bowl is disproportionately more major than a linear
    falloff would give it. Exactly one team ranked gets a much
    smaller, compressed-scale bump (this tier is rare and rarely
    involves a highly-ranked team anyway). Neither team ranked -> the
    flat bowl_mult base only."""
    if round_ != "BOWL":
        return 1.0
    base = params["bowl_mult"]
    home_ranked = home_ap_rank is not None
    away_ranked = away_ap_rank is not None
    if home_ranked and away_ranked:
        combined = home_ap_rank + away_ap_rank  # 3 (best) .. 49 (worst)
        bonus = params["bowl_rank_bonus_max"] * math.exp(-params["bowl_rank_decay"] * (combined - 3))
        return base + bonus
    if home_ranked or away_ranked:
        rank = home_ap_rank if home_ranked else away_ap_rank
        bonus = params["bowl_one_ranked_bonus_max"] * math.exp(-params["bowl_one_ranked_decay"] * (rank - 1))
        return base + bonus
    return base


# ----------------------------------------------------------------------
# Conference/division game classification. Unlike NFL_Elo, there is NO
# static table here - see this module's docstring (CONFERENCE/DIVISION
# LOOKUP). Each game dict is expected to already carry home_conf/
# away_conf (and optionally home_div/away_div), resolved by the caller
# from `team_conference_history` before reaching process_week() or
# preview_matchup(). Missing/None on either side just means "not a
# conference game" - never an error, since plenty of real games
# (FCS opponents, historical independents) have no conference on file.
# ----------------------------------------------------------------------

def _conf_div_game(home_conf, away_conf, home_div, away_div) -> tuple[int, int]:
    """Returns (conf_game, div_game) as 0/1 ints, from whatever
    conference/division fields the caller already attached to the game
    dict. A None on either side (no conference on file for that team
    that season) always resolves to (0, 0)."""
    conf_g = int(bool(home_conf) and bool(away_conf) and home_conf == away_conf)
    div_g = int(conf_g and bool(home_div) and bool(away_div) and home_div == away_div)
    return conf_g, div_g


@dataclass
class TeamState:
    rating: float
    last_game_date: Optional[date] = None
    last_season: Optional[int] = None
    games_played_in_season: int = 0


class EloEngine:
    """
    Stateful engine that replays CFB games WEEK BY WEEK (see module
    docstring) and produces one output row per team-per-game.
    """

    def __init__(self, params: Optional[dict] = None, resets: Optional[set] = None):
        self.params = params or DEFAULT_PARAMS
        self.teams: dict[str, TeamState] = {}
        # set of (team_id, season) pairs: force this team to start this
        # season at the base rating, ignoring its actual history. Rare
        # in CFB (a program dropping football and reviving it under the
        # same brand), but kept for parity with NFL/NBA/WNBA.
        self.resets = resets or set()

    def regress_returning_team(self, team_id: str, season: int, target: float) -> None:
        """Apply season-to-season regression toward `target` for a team
        that's ALREADY tracked (has an existing TeamState) - see
        SEASON-ENTRY in the module docstring for how the caller
        (rebuild.py) computes `target` (last season's conference/tier
        average, never a flat shared constant). Idempotent per season -
        a second call for the same (team_id, season) is a no-op, same
        guard NFL_Elo's _enter_season used. Must be called for every
        already-tracked team BEFORE process_week() runs for that
        season's games - process_week() itself no longer does this
        lazily (see its docstring)."""
        state = self.teams[team_id]
        if state.last_season == season:
            return
        if (team_id, season) in self.resets:
            state.rating = self.params["base"]
            state.last_season = season
            state.games_played_in_season = 0
            state.last_game_date = None
            return
        alpha = self.params["alpha"]
        state.rating = alpha * state.rating + (1 - alpha) * target
        state.last_season = season
        state.games_played_in_season = 0
        # Rest days are scoped to a single season: a team's first game
        # of a new season has no prior-game date to compare against,
        # matching the "no rest adjustment on a season opener" rule.
        state.last_game_date = None

    def induct_new_team(self, team_id: str, season: int, rating: float) -> None:
        """Create a fresh TeamState for a team never tracked before -
        a true FBS debut, or a former fixed-rating FCS opponent
        becoming FBS for the first time (see SEASON-ENTRY in the
        module docstring). No alpha-blending here: `rating` (the
        caller's 50/50 fcs_rating/conference-average blend) IS the
        starting point outright, since there's no real prior rating to
        blend against. Must be called before process_week() runs for
        that season's games, same as regress_returning_team()."""
        self.teams[team_id] = TeamState(rating=rating, last_season=season, games_played_in_season=0)

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
        Process every game in one CFB week as a single atomic batch:
        snapshot every playing team's pre-game rating BEFORE applying
        ANY of this week's results, then only apply every result once
        the whole week's math has been computed off that shared
        snapshot. See the module docstring for why this matters.

        week_games must all share the same `season`; each needs keys:
        date, season, type ('R'/'P'), round (currently always None -
        see add_season.py's normalizer docstring on deferred postseason
        classification), home_team, away_team (permanent team_ids),
        home_code, away_code (slugified team codes), home_pts, away_pts,
        ot (0/1), neutral (0/1, default 0 if omitted - suppresses
        home-field advantage for the designated "home" team of a game
        at a neutral site). Optional home_conf/away_conf/home_div/
        away_div (resolved by the caller via db.conference_for_season -
        see this module's docstring) drive conference/division game
        classification; omitted or None on either side just means "not
        a conference/division game." Optional home_is_fbs/away_is_fbs
        (resolved by the caller via db.is_fbs() - see rebuild.py's
        `_annotate_conferences`) drive FCS HANDLING above; omitted on
        either side defaults to True (treated as FBS), so existing
        callers that don't set these keep tracking every team normally.

        Returns one row list per game, in the same order as week_games -
        [row_home, row_away] when both sides are FBS, a single-element
        list when only one side is, or [] if neither side is (no
        rating row is ever produced for a non-FBS side - see FCS
        HANDLING above).
        """
        if not week_games:
            return []
        season = week_games[0]["season"]

        # --- Snapshot phase: pre-game rating/rest/games played for
        # every team playing this week, all off the SAME starting
        # state - none of this week's results are visible yet. A
        # non-FBS team gets NO TeamState at all - its "pre" rating is
        # just the fixed fcs_rating constant, with no rest/games-played
        # tracking, since we never persist anything for it. Every FBS
        # team MUST already have a TeamState by this point - season
        # entry (regress_returning_team()/induct_new_team()) is the
        # caller's (rebuild.py's) job, done ONCE for the whole season
        # before its first week ever reaches this method - see
        # SEASON-ENTRY in the module docstring for why this can no
        # longer happen lazily, team-by-team, the way NFL_Elo's did.
        pre = {}
        for g in week_games:
            for team_id, is_fbs in (
                (g["home_team"], g.get("home_is_fbs", True)),
                (g["away_team"], g.get("away_is_fbs", True)),
            ):
                if team_id in pre:
                    continue
                if not is_fbs:
                    pre[team_id] = dict(
                        rating=self.params["fcs_rating"], days_off=None,
                        games_played=0, is_fbs=False,
                    )
                    continue
                if team_id not in self.teams:
                    raise KeyError(
                        f"{team_id!r} has no TeamState entering season {season} - "
                        f"the caller must call regress_returning_team()/induct_new_team() "
                        f"for every FBS team before process_week() runs for that season."
                    )
                state = self.teams[team_id]
                pre[team_id] = dict(
                    rating=state.rating,
                    days_off=self._days_off(state, g["date"]),
                    games_played=state.games_played_in_season,
                    is_fbs=True,
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

            conf_g, div_g = _conf_div_game(
                g.get("home_conf"), g.get("away_conf"), g.get("home_div"), g.get("away_div")
            )

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

            po_mult = _po_mult(g["type"], g.get("round"), params)  # always 1.0 for CFB - see POSTSEASON docstring
            ccg_mult = _ccg_mult(g.get("round"), params)
            postseason_mult = _postseason_mult(g.get("round"), params)
            bowl_mult = _bowl_mult(g.get("round"), g.get("home_ap_rank"), g.get("away_ap_rank"), params)
            games_played_home = pre[home_id]["games_played"] + 1
            games_played_away = pre[away_id]["games_played"] + 1
            k_home = _decayed_k(games_played_home, season, params)
            k_away = _decayed_k(games_played_away, season, params)

            # NOTE: div_g is still computed and stored on every row (see
            # `row()` below) for potential future display purposes, but
            # no longer moves the K-multiplier - CFB's remaining
            # divisions are largely vestigial post-realignment, and a
            # conference game is a conference game regardless of which
            # (if any) division either side is in. See engine.py's
            # module docstring on this collapse from NFL_Elo's separate
            # div_game_mult/conf_game_mult pair.
            group_mult = (params["conf_game_mult"] if conf_g else 1) * po_mult * ccg_mult * postseason_mult * bowl_mult
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

            # A non-FBS side gets NO row and NO persisted rating update
            # (see FCS HANDLING in the module docstring) - its "pre"
            # rating was already the fixed fcs_rating constant, used
            # only to compute the FBS side's expected outcome/change
            # above; nothing about it is ever tracked or saved.
            game_rows = []
            if pre[home_id]["is_fbs"]:
                game_rows.append(row_home)
                deferred.append((home_id, post_home, g["date"], games_played_home))
            if pre[away_id]["is_fbs"]:
                game_rows.append(row_away)
                deferred.append((away_id, post_away, g["date"], games_played_away))
            results.append(game_rows)

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
        """Read-only preview of what a team's rating/last_game_date/
        games_played WOULD be entering `season`, without mutating
        anything - used for previewing a game that hasn't been played
        yet.

        KNOWN SIMPLIFICATION: unlike the real regress_returning_team()/
        induct_new_team() (see SEASON-ENTRY in the module docstring),
        this still blends toward the flat `base` constant, not a
        conference/tier average - correctly reproducing that average
        here would need database access this method intentionally
        doesn't have. In practice this only matters when previewing a
        season's very first games before ANY of its real results have
        been loaded/rebuilt yet (once even one real game of a season
        has been processed, every team's state.last_season already
        reflects the real regress_returning_team()/induct_new_team()
        call rebuild.py made for that season, and this method's
        state.last_season == season branch below just returns that
        real value untouched)."""
        if state.last_season == season:
            return state.rating, state.last_game_date, state.games_played_in_season

        if (team_id, season) in self.resets:
            return self.params["base"], None, 0
        if state.last_season is None:
            return state.rating, state.last_game_date, state.games_played_in_season
        alpha, base = self.params["alpha"], self.params["base"]
        return alpha * state.rating + (1 - alpha) * base, None, 0

    def preview_matchup(self, home_team: str, away_team: str, game_date: date, season: int,
                         type_: str = "R", round_: Optional[str] = None,
                         home_code: Optional[str] = None, away_code: Optional[str] = None,
                         neutral: bool = False, home_is_fbs: bool = True,
                         away_is_fbs: bool = True) -> dict:
        """Predict the outcome of a game that HASN'T been played yet,
        using each team's current rating as-is - does not mutate any
        engine state, and does not require (or use) a score. Unaffected
        by weekly batching: previewing doesn't need to know what week
        it is, just each team's most recently recorded state.

        home_is_fbs/away_is_fbs default to True for backward
        compatibility with callers that don't look this up - pass
        False (via db.is_fbs()) for a side known to be a non-FBS
        opponent, so its preview rating is the fixed fcs_rating
        constant (see FCS HANDLING in the module docstring) rather
        than incorrectly falling back to `base` the way an untracked
        team normally would."""
        params = self.params
        if home_is_fbs:
            home = self.teams.get(home_team) or TeamState(rating=params["base"])
        else:
            home = TeamState(rating=params["fcs_rating"])
        if away_is_fbs:
            away = self.teams.get(away_team) or TeamState(rating=params["base"])
        else:
            away = TeamState(rating=params["fcs_rating"])

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
