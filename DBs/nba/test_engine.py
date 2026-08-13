"""
Sanity checks for the Elo engine. Run after any change to engine.py.

This specifically guards against the bug found while validating 1998:
rest days must reset at season boundaries (measured from that season's
opening day), not carry over from a team's last game of the prior
season.
"""
from datetime import date
from engine import EloEngine, DEFAULT_PARAMS


def test_rest_days_reset_at_season_boundary():
    engine = EloEngine(DEFAULT_PARAMS)

    # Season 1: team A plays late (Aug 30). Season 2 opens Jun 11 the
    # following year - almost a year of "rest" if not reset.
    engine.process_game(dict(
        date=date(1997, 8, 30), season=1997, type="R", round=None,
        home_team="A", away_team="B", home_pts=70, away_pts=60, ot=0,
    ))

    rows = engine.process_game(dict(
        date=date(1998, 6, 11), season=1998, type="R", round=None,
        home_team="A", away_team="C", home_pts=70, away_pts=60, ot=0,
    ))
    row_a = next(r for r in rows if r["team"] == "A")
    assert row_a["days_off"] == 0, f"expected 0 days off at season open, got {row_a['days_off']}"
    assert row_a["rest_adj"] == 0, f"expected no rest adjustment, got {row_a['rest_adj']}"

    # A team entering a couple days after the season opener should show
    # days-off relative to the season's open date, not 0 and not a huge
    # carryover number.
    rows2 = engine.process_game(dict(
        date=date(1998, 6, 13), season=1998, type="R", round=None,
        home_team="D", away_team="E", home_pts=70, away_pts=60, ot=0,
    ))
    row_d = next(r for r in rows2 if r["team"] == "D")
    assert row_d["days_off"] == 2, f"expected 2 days off (since season open), got {row_d['days_off']}"


def test_season_regression_to_mean_still_applies():
    """Rating carryover across seasons should still use the alpha blend,
    even though rest days no longer carry over."""
    engine = EloEngine(DEFAULT_PARAMS)
    engine.process_game(dict(
        date=date(1997, 6, 21), season=1997, type="R", round=None,
        home_team="A", away_team="B", home_pts=80, away_pts=50, ot=0,
    ))
    end_1997 = engine.current_ratings()["A"]

    rows = engine.process_game(dict(
        date=date(1998, 6, 11), season=1998, type="R", round=None,
        home_team="A", away_team="C", home_pts=70, away_pts=69, ot=0,
    ))
    row_a = next(r for r in rows if r["team"] == "A")
    alpha, base = DEFAULT_PARAMS["alpha"], DEFAULT_PARAMS["base"]
    expected_pre = alpha * end_1997 + (1 - alpha) * base
    assert abs(row_a["pre_rate"] - expected_pre) < 1e-9


def test_neutral_site_games_skip_home_court_advantage():
    engine = EloEngine(DEFAULT_PARAMS)
    rows = engine.process_game(dict(
        date=date(2020, 7, 25), season=2020, type="R", round=None,
        home_team="A", away_team="B", home_pts=70, away_pts=65, ot=0,
        neutral=1,
    ))
    row_a = next(r for r in rows if r["team"] == "A")
    manual_exp = 1 / (1 + 10 ** ((1500.0 - 1500.0) / 400))  # equal ratings, no HCA -> 0.5
    assert abs(row_a["expected_win"] - manual_exp) < 1e-9
    assert row_a["expected_win"] == 0.5, (
        f"expected exactly 0.5 with equal ratings and no HCA, got {row_a['expected_win']}"
    )


def test_engine_sanity():
    test_rest_days_reset_at_season_boundary()
    test_season_regression_to_mean_still_applies()
    test_neutral_site_games_skip_home_court_advantage()


if __name__ == "__main__":
    test_rest_days_reset_at_season_boundary()
    test_season_regression_to_mean_still_applies()
    test_neutral_site_games_skip_home_court_advantage()
    print("All engine sanity checks passed.")
