"""
Regression tests for engine.py. Each test documents one specific,
real risk found while building this engine - not generic scaffolding.
Run with: python3 test_engine.py

Uses real NFL codes (ARI, ATL, BAL) throughout, since conf_div() looks
codes up in a fixed real-team table and doesn't accept placeholders.
"""
from datetime import date
from engine import EloEngine, week_from_date, DEFAULT_PARAMS


def test_week_batch_isolation():
    """The core weekly-batching invariant (see engine.py's module
    docstring): two games in the SAME week must NOT let one see the
    other's result. If this broke, a Thursday game's result would
    leak into the following Sunday game's pre-game rating within the
    same week, which the real workbook never does."""
    eng = EloEngine()
    week = [
        dict(date=date(2019, 9, 5), season=2019, type="R", round=None,
             home_team="ARI", away_team="ATL", home_code="ARI", away_code="ATL",
             home_pts=30, away_pts=10, ot=0),  # ARI blows out ATL on Thursday
        dict(date=date(2019, 9, 8), season=2019, type="R", round=None,
             home_team="ARI", away_team="BAL", home_code="ARI", away_code="BAL",
             home_pts=20, away_pts=17, ot=0),  # ARI plays again Sunday, same week
    ]
    results = eng.process_week(week)
    # ARI's pre-game rating in game 2 (index [1][0]) must be the
    # ORIGINAL base rating, not already boosted by game 1's blowout win.
    pre_in_game2 = results[1][0]["pre_rate"]
    assert pre_in_game2 == DEFAULT_PARAMS["base"], (
        f"BUG: ARI's pre-game rating in the second game of the week was "
        f"{pre_in_game2}, expected {DEFAULT_PARAMS['base']} (unaffected by "
        f"the first game of the same week)."
    )
    print("test_week_batch_isolation: PASS")


def test_season_entry_guard_fires_once():
    """A revived team's reset-to-base must apply exactly once, at
    season entry - not before every game/week of that season. This
    exact bug (reset re-firing every game) was found and fixed in
    NBA's engine; ported the fix here from the start, but locking in
    the correct behavior so it can't regress."""
    eng = EloEngine(resets={("ARI", 2020)})
    weeks = [
        [dict(date=date(2020, 9, 1 + 7 * i), season=2020, type="R", round=None,
              home_team="ARI", away_team="ATL", home_code="ARI", away_code="ATL",
              home_pts=100 + i, away_pts=90, ot=0)]
        for i in range(3)
    ]
    ratings_after_each_week = []
    for wk in weeks:
        eng.process_week(wk)
        ratings_after_each_week.append(eng.current_ratings()["ARI"])
    assert ratings_after_each_week == sorted(ratings_after_each_week), (
        f"BUG: ARI's rating didn't rise monotonically across the season - "
        f"got {ratings_after_each_week}, meaning the reset re-fired mid-season "
        f"instead of applying only once at season entry."
    )
    print("test_season_entry_guard_fires_once: PASS")


def test_rest_days_reset_at_season_boundary():
    """A team's first game of a NEW season must get NO rest adjustment
    (None, not computed against the prior season's last game date) -
    matches the original workbook's convention exactly (confirmed
    against build_nfl_db.py's days_off computation, which groups by
    (Season, Team) so prev_date is NaN at a season boundary)."""
    eng = EloEngine()
    week1_2019 = [dict(date=date(2019, 12, 29), season=2019, type="R", round=None,
                        home_team="ARI", away_team="ATL", home_code="ARI", away_code="ATL",
                        home_pts=20, away_pts=17, ot=0)]
    eng.process_week(week1_2019)

    # ARI's next game is week 1 of the NEXT season, just 8 days later -
    # despite the short real gap, this must NOT count as a rest
    # differential, because it's a new season.
    week1_2020 = [dict(date=date(2020, 1, 6), season=2020, type="R", round=None,
                        home_team="ARI", away_team="BAL", home_code="ARI", away_code="BAL",
                        home_pts=24, away_pts=20, ot=0)]
    results = eng.process_week(week1_2020)
    home_row = results[0][0]
    assert home_row["days_off"] is None, (
        f"BUG: ARI's days_off on its first game of a new season was "
        f"{home_row['days_off']}, expected None (no carryover from the prior season)."
    )
    assert home_row["rest_adj"] == 0.0, (
        f"BUG: ARI got a nonzero rest_adj ({home_row['rest_adj']}) on its first game "
        f"of a new season."
    )
    print("test_rest_days_reset_at_season_boundary: PASS")


def test_days_off_is_raw_gap_not_minus_one():
    """days_off must be the RAW calendar gap between games (e.g. a
    week apart = 7), NOT gap-minus-one like NBA/WNBA's convention.
    Confirmed against build_nfl_db.py: days_off = (Date - prev_date).days,
    no -1."""
    eng = EloEngine()
    week1 = [dict(date=date(2019, 9, 8), season=2019, type="R", round=None,
                  home_team="ARI", away_team="ATL", home_code="ARI", away_code="ATL",
                  home_pts=20, away_pts=17, ot=0)]
    eng.process_week(week1)
    week2 = [dict(date=date(2019, 9, 15), season=2019, type="R", round=None,
                  home_team="ARI", away_team="BAL", home_code="ARI", away_code="BAL",
                  home_pts=24, away_pts=20, ot=0)]
    results = eng.process_week(week2)
    assert results[0][0]["days_off"] == 7, (
        f"BUG: expected a raw 7-day gap, got {results[0][0]['days_off']} - "
        f"looks like a -1 (NBA/WNBA-style) adjustment crept in."
    )
    print("test_days_off_is_raw_gap_not_minus_one: PASS")


def test_preview_matchup_does_not_mutate_state():
    """preview_matchup() must be read-only - it's used for every
    unplayed game in predict.py/simulate_season.py, and must never
    affect the real engine state those tools build once and reuse."""
    eng = EloEngine()
    week = [dict(date=date(2019, 9, 8), season=2019, type="R", round=None,
                 home_team="ARI", away_team="ATL", home_code="ARI", away_code="ATL",
                 home_pts=24, away_pts=17, ot=0)]
    eng.process_week(week)
    before = dict(eng.current_ratings())

    eng.preview_matchup("ARI", "BAL", date(2019, 9, 15), 2019, home_code="ARI", away_code="BAL")

    after = dict(eng.current_ratings())
    assert before == after, "BUG: preview_matchup mutated engine state."
    print("test_preview_matchup_does_not_mutate_state: PASS")


def test_week_from_date_groups_thursday_with_following_sunday():
    """The whole point of week_from_date(): a Thursday night game and
    the following Sunday/Monday games must land in the SAME week
    number, since that's what lets them share pre-game ratings."""
    season_start = date(2019, 9, 5)  # a Thursday (Week 1 opener)
    thu = week_from_date(date(2019, 9, 5), season_start)
    sun = week_from_date(date(2019, 9, 8), season_start)
    mon = week_from_date(date(2019, 9, 9), season_start)
    next_thu = week_from_date(date(2019, 9, 12), season_start)
    assert thu == sun == mon, f"BUG: Thu/Sun/Mon of the same week got different week numbers: {thu}, {sun}, {mon}"
    assert next_thu == thu + 1, f"BUG: the following week's Thursday should be week+1, got {next_thu} vs {thu}"
    print("test_week_from_date_groups_thursday_with_following_sunday: PASS")


def test_neutral_site_suppresses_home_field_advantage():
    """A neutral-site game (the Super Bowl every year - both source
    rows say HomeAway='N', neither team is actually at home) must NOT
    get home-field advantage applied to the arbitrarily-chosen 'home'
    team. This was a real bug found in production: the original
    nfl_elo.py stored a `neutral` flag but never actually used it, and
    a rewrite of add_season.py briefly dropped neutral-site games
    entirely (since neither row matched HomeAway=='H'). Both are fixed
    now - this locks in the fix."""
    eng = EloEngine()
    week = [dict(date=date(2026, 2, 8), season=2025, type="P", round="SB",
                  home_team="ARI", away_team="ATL", home_code="ARI", away_code="ATL",
                  home_pts=24, away_pts=20, ot=0, neutral=True)]
    results = eng.process_week(week)
    home_row = results[0][0]
    # Both teams start at the same base rating, so with HFA correctly
    # suppressed, expected_win should be exactly 0.5 - not shifted in
    # ARI's favor the way it would be for a real home game.
    assert abs(home_row["expected_win"] - 0.5) < 1e-9, (
        f"BUG: neutral-site game gave the 'home' team a {home_row['expected_win']:.3f} "
        f"expected win instead of 0.5 - home-field advantage wasn't suppressed."
    )

    # Also confirm preview_matchup (used by predict.py/simulate_season.py)
    # suppresses it too.
    eng2 = EloEngine()
    preview = eng2.preview_matchup("ARI", "ATL", date(2026, 2, 8), 2025,
                                     type_="P", round_="SB", neutral=True)
    assert abs(preview["expected_win_home"] - 0.5) < 1e-9, (
        "BUG: preview_matchup didn't suppress home-field advantage for a neutral-site game."
    )
    print("test_neutral_site_suppresses_home_field_advantage: PASS")


if __name__ == "__main__":
    test_week_batch_isolation()
    test_season_entry_guard_fires_once()
    test_rest_days_reset_at_season_boundary()
    test_days_off_is_raw_gap_not_minus_one()
    test_preview_matchup_does_not_mutate_state()
    test_week_from_date_groups_thursday_with_following_sunday()
    test_neutral_site_suppresses_home_field_advantage()
    print("\nAll engine sanity checks passed.")
