"""
Elo differential -> point spread conversion for the WNBA model.

Unlike nfl/spread.py, this is calibrated ONLY against actual final
margins (elo_diff_to_margin() there) - no WNBA odds/betting-line
history was available to fit against Vegas closing lines the way the
NFL model does. Treat this as a placeholder-but-real calibration:
it's fit on real data (your own `ratings` history), just against a
noisier target (final score, not the market's own price on that
game).

    elo_diff = home_pre - away_pre + hca_applied + rest_adj_home

(the same home-adjusted quantity that feeds engine.py's logistic win
prob - HCA and rest already folded in, matching nfl/spread.py's
convention exactly).

SIGN CONVENTION: matches nfl/spread.py - POSITIVE means the HOME team
is favored by that many points.

Fit performed 2026-09-21 against wnba_elo.db's full `ratings` history
(echo variant, home rows only), n=6982, R^2=0.1434, RMSE=12.05.
That R^2 is essentially identical to NFL's own margin-fit R^2 (0.14
per nfl/spread.py's docstring) - final scores are just as noisy to
predict in this sport as in that one, so this isn't an underpowered
fit, it's the realistic ceiling for "final margin" as a target.

Recalibrate any time the ratings history changes meaningfully:

    python3 spread.py --calibrate --db wnba_elo.db

If/when you get a WNBA odds history CSV, add a Vegas-calibrated
elo_diff_to_spread() here mirroring nfl/spread.py's structure exactly
(load_elo_vs_vegas / calibrate / VEGAS_CALIBRATION) and swap
write_schedule_predictions() over to call that instead of this
margin-only version - see add_season.py.
"""
from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass

import numpy as np
import pandas as pd

DB_PATH = "wnba_elo.db"
HCA = 84.0  # must match engine.BASELINE_PARAMS["hca"] - keep in sync by hand

# Fit against wnba_elo.db's own `ratings` history (echo variant), see
# module docstring for date/n/R^2. spread = intercept + slope * elo_diff
MARGIN_CALIBRATION = dict(intercept=-0.6135, slope=0.03895)


def elo_diff_to_margin(elo_diff: float, cal: dict = MARGIN_CALIBRATION) -> float:
    """Elo differential (home-adjusted, HCA + rest already folded in) ->
    predicted point margin, positive = home favored. This IS the
    spread conversion for now - see module docstring for why there's
    no separate Vegas-calibrated version yet."""
    return cal["intercept"] + cal["slope"] * elo_diff


# Alias so calling code (write_schedule_predictions in add_season.py)
# can use the same function name as nfl/spread.py's
# elo_diff_to_spread(), without pretending this is market-calibrated.
elo_diff_to_spread = elo_diff_to_margin


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


def load_elo_vs_margin(conn: sqlite3.Connection, variant: str = "echo",
                        seasons: tuple[int, int] | None = None) -> pd.DataFrame:
    """One row per game: the model's home-adjusted Elo differential
    (elo_diff) and actual margin (mov, home perspective), straight from
    `ratings` - no external file needed, unlike nfl/spread.py's Vegas
    join. Pass `seasons=(lo, hi)` (inclusive) to restrict, e.g. for a
    walk-forward check later."""
    q = """
        SELECT r.pre_rate AS home_pre, r.opp_pre_rate AS away_pre,
               r.rest_adj AS home_rest_adj, r.neutral, r.mov, r.season
        FROM ratings r
        WHERE r.home_away = 'H' AND r.variant = ?
    """
    params: list = [variant]
    if seasons:
        q += " AND r.season BETWEEN ? AND ?"
        params += list(seasons)
    df = pd.read_sql(q, conn, params=params)
    if df.empty:
        return df
    hca_applied = np.where(df["neutral"] == 1, 0.0, HCA)
    df["elo_diff"] = df["home_pre"] - df["away_pre"] + hca_applied + df["home_rest_adj"]
    return df


def calibrate(conn: sqlite3.Connection, variant: str = "echo",
              seasons: tuple[int, int] | None = None) -> CalibrationResult:
    """Refit the margin calibration against the given season range
    (default: everything available). Returns the fit - paste
    intercept/slope into MARGIN_CALIBRATION above to lock it in."""
    df = load_elo_vs_margin(conn, variant, seasons=seasons)
    return _fit(df["elo_diff"].values, df["mov"].values)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DB_PATH)
    ap.add_argument("--variant", default="echo", choices=["echo", "pulse"])
    ap.add_argument("--calibrate", action="store_true",
                     help="Refit against full history and print the result.")
    args = ap.parse_args()

    conn = sqlite3.connect(args.db)
    fit = calibrate(conn, args.variant)
    print(f"Elo diff -> actual margin ({args.variant}):  {fit}")
    print("\nUpdate MARGIN_CALIBRATION at the top of this file with these "
          "numbers if you want to lock in the refit.")


if __name__ == "__main__":
    main()
