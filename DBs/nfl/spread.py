"""
Elo differential -> point spread conversion for the NFL model.

Calibrated against Vegas closing lines (games_betting.csv, nflverse
data, 1999-2025) rather than borrowing a constant like 538's Elo/25.
Two calibrations are available:

  - elo_diff_to_spread()   fit against Vegas closing spread_line
                           (R^2 ~ 0.68 in-sample). Use this one for
                           anything you're comparing to a betting
                           line (display, ATS backtests) - it's
                           calibrated to what the market prices, not
                           to noisy final scores.
  - elo_diff_to_margin()   fit against actual game margin
                           (R^2 ~ 0.14 in-sample). Included for
                           completeness. Final margins just aren't
                           very predictable, even for Vegas - the
                           market's own closing line only correlates
                           ~0.42 with actual margin in this same
                           sample, so don't expect much more from us.

SIGN CONVENTION: matches nflverse's spread_line - POSITIVE means the
HOME team is favored by that many points, negative means the away
team is favored. (Confirmed empirically against games_betting.csv -
this is the opposite of the "-3 = favorite" convention you'll see
quoted for a single game's odds, so don't flip it by habit.)

Recalibrate whenever the ratings history changes meaningfully (new
seasons added, engine re-tuned):

    python3 spread.py --calibrate

This prints refit coefficients - paste them into VEGAS_CALIBRATION /
MARGIN_CALIBRATION below to lock them in. It's a deliberate snapshot,
not something recomputed on every import, so predict.py stays fast
and deterministic between recalibrations.

    python3 spread.py --backtest [--first-season 2010]

Runs a walk-forward ATS backtest: for each test season, calibration
is refit on ONLY the seasons before it, then applied out-of-sample to
that season. This is slower but is the number that actually means
something - the in-sample fit above will look better than any of
these because it's grading itself on data it was fit to.
"""
from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass

import numpy as np
import pandas as pd

DB_PATH = "nfl_elo.db"
BETTING_CSV = "games_betting.csv"
HFA = 72.0  # must match engine.BASELINE_PARAMS["hfa"] - keep in sync by hand

# Fit on 1999-2025 (games_betting.csv coverage), see calibrate() below.
# spread_or_margin = intercept + slope * elo_diff
VEGAS_CALIBRATION = dict(intercept=-0.9397, slope=0.04347)
MARGIN_CALIBRATION = dict(intercept=-1.1281, slope=0.04745)


def elo_diff_to_spread(elo_diff: float, cal: dict = VEGAS_CALIBRATION) -> float:
    """Elo differential (the same home-adjusted quantity that feeds
    engine.py's logistic win prob - HFA and rest already folded in) ->
    predicted point spread, Vegas sign convention (positive = home
    favored)."""
    return cal["intercept"] + cal["slope"] * elo_diff


def elo_diff_to_margin(elo_diff: float, cal: dict = MARGIN_CALIBRATION) -> float:
    """Same idea, calibrated against actual final margin instead of
    the market. Prefer elo_diff_to_spread() for anything getting
    compared to a betting line."""
    return cal["intercept"] + cal["slope"] * elo_diff


@dataclass
class CalibrationResult:
    intercept: float
    slope: float
    r2: float
    rmse: float
    mae: float
    n: int

    def __str__(self):
        per_pt = f"{1 / self.slope:.1f}" if self.slope else "inf"
        return (f"intercept={self.intercept:+.4f}  slope={self.slope:.5f}  "
                f"(1 pt / {per_pt} Elo)  R2={self.r2:.4f}  "
                f"RMSE={self.rmse:.2f}  MAE={self.mae:.2f}  n={self.n}")


def _fit(x: np.ndarray, y: np.ndarray) -> CalibrationResult:
    slope, intercept = np.polyfit(x, y, 1)
    pred = intercept + slope * x
    resid = y - pred
    ss_tot = np.sum((y - y.mean()) ** 2)
    r2 = 1 - np.sum(resid ** 2) / ss_tot if ss_tot else float("nan")
    return CalibrationResult(
        intercept=float(intercept), slope=float(slope), r2=float(r2),
        rmse=float(np.sqrt(np.mean(resid ** 2))),
        mae=float(np.mean(np.abs(resid))), n=len(x),
    )


def load_elo_vs_vegas(conn: sqlite3.Connection, betting_csv: str = BETTING_CSV,
                       seasons: tuple[int, int] | None = None) -> pd.DataFrame:
    """One row per game: the model's home-adjusted Elo differential
    (elo_diff), actual margin (mov, home perspective), and the Vegas
    closing spread_line - joined on date + home/away code. Pass
    `seasons=(lo, hi)` (inclusive) to restrict for walk-forward
    calibration/backtesting. Rows without a matching betting line
    (pre-1999, or a code mismatch) are dropped."""
    q = """
        SELECT r.game_id, g.date, g.season, g.type, g.round,
               g.home_code, g.away_code, g.neutral,
               r.pre_rate AS home_pre, r.opp_pre_rate AS away_pre,
               r.rest_adj AS home_rest_adj, r.expected_win, r.mov
        FROM ratings r
        JOIN games g ON g.game_id = r.game_id
        WHERE r.home_away = 'H'
    """
    params: list = []
    if seasons:
        q += " AND g.season BETWEEN ? AND ?"
        params = list(seasons)
    ratings = pd.read_sql(q, conn, params=params)
    if ratings.empty:
        return ratings

    hfa_applied = np.where(ratings["neutral"] == 1, 0.0, HFA)
    ratings["elo_diff"] = (ratings["home_pre"] - ratings["away_pre"]
                            + hfa_applied + ratings["home_rest_adj"])

    bet = pd.read_csv(betting_csv)
    bet["gameday"] = pd.to_datetime(bet["gameday"])
    ratings["date"] = pd.to_datetime(ratings["date"])

    merged = ratings.merge(
        bet[["gameday", "home_team", "away_team", "spread_line"]],
        left_on=["date", "home_code", "away_code"],
        right_on=["gameday", "home_team", "away_team"], how="inner",
    ).dropna(subset=["spread_line"])
    return merged


def calibrate(conn: sqlite3.Connection, betting_csv: str = BETTING_CSV,
              seasons: tuple[int, int] | None = None
              ) -> tuple[CalibrationResult, CalibrationResult]:
    """Refit both calibrations against the given season range (default:
    everything available). Returns (vegas_fit, margin_fit)."""
    df = load_elo_vs_vegas(conn, betting_csv, seasons=seasons)
    vegas_fit = _fit(df["elo_diff"].values, df["spread_line"].values)
    margin_fit = _fit(df["elo_diff"].values, df["mov"].values)
    return vegas_fit, margin_fit


def walk_forward_ats_backtest(conn: sqlite3.Connection, betting_csv: str = BETTING_CSV,
                               first_test_season: int = 2010,
                               thresholds: tuple[float, ...] = (0, 1, 2, 3, 4, 5),
                               vig: float = 110.0) -> pd.DataFrame:
    """For each season >= first_test_season, refit VEGAS_CALIBRATION on
    every prior season only, then bet the side Elo disagrees with
    Vegas on for that season, out-of-sample. Aggregates across all
    test seasons per disagreement threshold. Returns a summary
    DataFrame; also prints it.

    This is the number to trust over the in-sample fit's own residual
    stats - a calibration graded on the data it was fit to will always
    look better than it performs going forward.
    """
    full = load_elo_vs_vegas(conn, betting_csv)
    seasons = sorted(full["season"].unique())
    test_seasons = [s for s in seasons if s >= first_test_season]

    rows = []
    for s in test_seasons:
        train = full[full["season"] < s]
        test = full[full["season"] == s].copy()
        if len(train) < 200 or test.empty:
            continue  # not enough history yet to fit a meaningful line
        fit = _fit(train["elo_diff"].values, train["spread_line"].values)
        test["elo_pred_spread"] = fit.intercept + fit.slope * test["elo_diff"]
        test["disagreement"] = test["elo_pred_spread"] - test["spread_line"]
        test = test[test["mov"] != test["spread_line"]]  # drop pushes
        test["home_covered"] = (test["mov"] > test["spread_line"]).astype(int)
        rows.append(test)

    if not rows:
        raise ValueError("No test seasons had enough training history - "
                          "lower --first-season.")
    allrows = pd.concat(rows, ignore_index=True)

    summary = []
    for t in thresholds:
        bet_home = allrows[allrows["disagreement"] >= t]
        bet_away = allrows[allrows["disagreement"] <= -t]
        n = len(bet_home) + len(bet_away)
        wins = bet_home["home_covered"].sum() + (1 - bet_away["home_covered"]).sum()
        if n == 0:
            continue
        rate = wins / n
        roi = (wins * 100 - (n - wins) * vig) / (n * vig)
        summary.append(dict(threshold=t, n=n, ats_win_rate=rate, roi=roi))

    df = pd.DataFrame(summary)
    print(f"Walk-forward ATS backtest, test seasons {test_seasons[0]}-{test_seasons[-1]} "
          f"(each refit on only prior seasons):\n")
    for r in summary:
        print(f"  threshold >= {r['threshold']:.0f} pts: n={r['n']:5d}  "
              f"ATS win rate={r['ats_win_rate']:.3%}  ROI={r['roi']:+.2%}")
    breakeven = vig / (vig + 100)
    print(f"\nBreakeven at -{vig:.0f} vig: {breakeven:.3%}")
    return df


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--betting-csv", default=BETTING_CSV)
    ap.add_argument("--calibrate", action="store_true",
                     help="Refit both calibrations on full history and print them.")
    ap.add_argument("--backtest", action="store_true",
                     help="Run the walk-forward out-of-sample ATS backtest.")
    ap.add_argument("--first-season", type=int, default=2010,
                     help="First season to test in --backtest (needs prior seasons to train on).")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)

    if args.calibrate or not (args.calibrate or args.backtest):
        vegas_fit, margin_fit = calibrate(conn, args.betting_csv)
        print(f"Elo diff -> Vegas spread_line:  {vegas_fit}")
        print(f"Elo diff -> actual margin:      {margin_fit}")
        print("\nUpdate VEGAS_CALIBRATION / MARGIN_CALIBRATION at the top of "
              "this file with these numbers if you want to lock in the refit.")

    if args.backtest:
        walk_forward_ats_backtest(conn, args.betting_csv, first_test_season=args.first_season)


if __name__ == "__main__":
    main()
