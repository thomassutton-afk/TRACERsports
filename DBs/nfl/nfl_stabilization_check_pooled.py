"""
Multi-season pooled trust check: is the coverage/calibration picture
from a single season real, or was it just sampling noise?

NFL version - checkpoints at the end of every REAL week of the season
(see engine.py's week_from_date/process_week), pooled across seasons
by week NUMBER (week 1 = every season's week 1, etc. - NFL's week
numbering is already a natural alignment key, no anchoring trick
needed like NBA/WNBA). A single season only gives ~32 teams per
checkpoint; pooling N seasons gives ~32xN, which shrinks the noise on
the coverage percentage a lot.

Same three simulation methods:

  DYNAMIC - simulate_season.py's actual method (full-strength rating
            drift within each trial, batched by week).
  DAMPED  - same, but each simulated WEEK's rating change is scaled by
            --damping before being applied (default 0.5).
  FROZEN  - win probabilities fixed at the start, no mid-trial rating
            updates at all.

Usage:
    python3 stabilization_check.py --seasons 2016-2025
    python3 stabilization_check.py --seasons 2018,2020-2025 --damping 0.6 --trials 300

Writes reports/stabilization_pooled_<seasons>_<variant>.csv and .txt.
"""
import argparse
import copy
import csv
import os
import random
from datetime import date
from math import comb

import db
import engine
from rebuild import _week_buckets, variant_params
from simulate_season import historical_mov_pool, simulate_one_season

DB_PATH = "nfl_elo.db"
OUT_DIR = "reports"
LEAGUE_LABEL = "NFL"

_coinflip_cache = {}


def coinflip_band_width(n, p=0.5):
    if n <= 0:
        return 0
    if n in _coinflip_cache:
        return _coinflip_cache[n]
    pmf = [comb(n, k) * (p**k) * ((1 - p) ** (n - k)) for k in range(n + 1)]
    cum = 0.0
    p10 = p90 = n
    for k, mass in enumerate(pmf):
        cum += mass
        if cum >= 0.10 and p10 == n and k < n:
            p10 = k
        if cum >= 0.90:
            p90 = k
            break
    width = p90 - p10
    _coinflip_cache[n] = width
    return width


def parse_seasons(spec):
    seasons = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-")
            seasons.update(range(int(lo), int(hi) + 1))
        elif part:
            seasons.add(int(part))
    return sorted(seasons)


def season_weeks(conn, season):
    games = [g for g in db.load_games(conn) if g["season"] == season and g["type"] == "R"]
    if not games:
        return {}, []
    season_start = min(g["date"] for g in games)
    by_week = {}
    for g in games:
        wk = engine.week_from_date(g["date"], season_start)
        by_week.setdefault(wk, []).append(g)
    week_ends = {wk: max(g["date"] for g in gs) for wk, gs in by_week.items()}
    return week_ends, games


def record_as_of(games, cutoff=None):
    record = {}
    for g in games:
        if cutoff is not None and g["date"] > cutoff:
            continue
        home, away = g["home_team"], g["away_team"]
        record.setdefault(home, [0, 0])
        record.setdefault(away, [0, 0])
        if g["home_pts"] > g["away_pts"]:
            record[home][0] += 1
            record[away][1] += 1
        elif g["away_pts"] > g["home_pts"]:
            record[away][0] += 1
            record[home][1] += 1
    return {t: tuple(v) for t, v in record.items()}


def build_engine_as_of(conn, variant, cutoff):
    games = [g for g in db.load_games(conn) if g["date"] <= cutoff]
    resets = db.load_resets(conn)
    if games:
        seed_season = games[0]["season"]
    else:
        seed_season = date.today().year
    eng = engine.EloEngine(variant_params(conn, variant, seed_season), resets=resets)
    weeks = _week_buckets(games)
    current_season = games[0]["season"] if games else None
    for key in sorted(weeks):
        season = key[0]
        if season != current_season:
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


def bands_from_wins(per_team_wins):
    bands = {}
    for team, wins in per_team_wins.items():
        wins.sort()
        n = len(wins)
        bands[team] = dict(
            p10=wins[int(0.10 * n)],
            p50=wins[int(0.50 * n)],
            p90=wins[min(n - 1, int(0.90 * n))],
            avg=sum(wins) / n,
        )
    return bands


def simulate_one_season_damped(base_engine, remaining_games, mov_pool, rng, damping):
    eng = copy.deepcopy(base_engine)
    wl = {}
    weeks = _week_buckets(remaining_games)

    for wk in sorted(weeks):
        week_games = sorted(weeks[wk], key=lambda g: g["date"])
        synthetic_week = []
        outcomes = []
        teams_this_week = set()
        for g in week_games:
            preview = eng.preview_matchup(
                home_team=g["home_team"], away_team=g["away_team"], game_date=g["date"],
                season=g["season"], type_=g["type"], round_=g["round"],
                home_code=g["home_code"], away_code=g["away_code"], neutral=bool(g["neutral"]),
            )
            home_wins = rng.random() < preview["expected_win_home"]
            margin = rng.choice(mov_pool)
            if home_wins:
                home_pts, away_pts = 20 + margin, 20
            else:
                home_pts, away_pts = 20, 20 + margin
            synthetic_week.append(dict(
                date=g["date"], season=g["season"], type=g["type"], round=g["round"],
                home_team=g["home_team"], away_team=g["away_team"],
                home_code=g["home_code"], away_code=g["away_code"],
                home_pts=home_pts, away_pts=away_pts, ot=0, neutral=g["neutral"],
            ))
            outcomes.append((g["home_team"], g["away_team"], home_wins))
            teams_this_week.add(g["home_team"])
            teams_this_week.add(g["away_team"])

        pre_ratings = {
            t: (eng.teams[t].rating if t in eng.teams else eng.params["base"])
            for t in teams_this_week
        }
        eng.process_week(synthetic_week)
        for t in teams_this_week:
            post = eng.teams[t].rating
            eng.teams[t].rating = pre_ratings[t] + damping * (post - pre_ratings[t])

        for home_team, away_team, home_wins in outcomes:
            for team in (home_team, away_team):
                wl.setdefault(team, {"w": 0, "l": 0})
            if home_wins:
                wl[home_team]["w"] += 1
                wl[away_team]["l"] += 1
            else:
                wl[away_team]["w"] += 1
                wl[home_team]["l"] += 1

    return dict(wl=wl, ratings=eng.current_ratings())


def project_bands_dynamic(base_engine, season_teams, current, remaining, mov_pool, trials, rng):
    per_team_wins = {team: [] for team in season_teams}
    for _ in range(trials):
        trial = simulate_one_season(base_engine, remaining, mov_pool, rng)
        for team in season_teams:
            base_w, _base_l = current.get(team, (0, 0))
            add_w = trial["wl"].get(team, {}).get("w", 0)
            per_team_wins[team].append(base_w + add_w)
    return bands_from_wins(per_team_wins)


def project_bands_damped(base_engine, season_teams, current, remaining, mov_pool, trials, rng, damping):
    per_team_wins = {team: [] for team in season_teams}
    for _ in range(trials):
        trial = simulate_one_season_damped(base_engine, remaining, mov_pool, rng, damping)
        for team in season_teams:
            base_w, _base_l = current.get(team, (0, 0))
            add_w = trial["wl"].get(team, {}).get("w", 0)
            per_team_wins[team].append(base_w + add_w)
    return bands_from_wins(per_team_wins)


def project_bands_frozen(base_engine, season_teams, current, remaining, trials, rng):
    game_probs = []
    for g in remaining:
        preview = base_engine.preview_matchup(
            home_team=g["home_team"], away_team=g["away_team"], game_date=g["date"],
            season=g["season"], type_=g["type"], round_=g["round"], neutral=bool(g["neutral"]),
        )
        game_probs.append((g["home_team"], g["away_team"], preview["expected_win_home"]))
    per_team_wins = {team: [] for team in season_teams}
    for _ in range(trials):
        trial_wins = {}
        for home, away, p in game_probs:
            if rng.random() < p:
                trial_wins[home] = trial_wins.get(home, 0) + 1
            else:
                trial_wins[away] = trial_wins.get(away, 0) + 1
        for team in season_teams:
            base_w, _base_l = current.get(team, (0, 0))
            per_team_wins[team].append(base_w + trial_wins.get(team, 0))
    return bands_from_wins(per_team_wins)


def games_remaining_per_team(remaining):
    counts = {}
    for g in remaining:
        counts[g["home_team"]] = counts.get(g["home_team"], 0) + 1
        counts[g["away_team"]] = counts.get(g["away_team"], 0) + 1
    return counts


def raw_scores(bands, common, actual_final, remaining_counts):
    hits, widths, ratios, abs_errs = [], [], [], []
    for t in common:
        actual_wins = actual_final[t][0]
        b = bands[t]
        width = b["p90"] - b["p10"]
        widths.append(width)
        abs_errs.append(abs(b["avg"] - actual_wins))
        hits.append(1 if b["p10"] <= actual_wins <= b["p90"] else 0)
        n_i = remaining_counts.get(t, 0)
        baseline_width = coinflip_band_width(n_i)
        if baseline_width > 0:
            ratios.append(width / baseline_width)
    return dict(hits=hits, widths=widths, ratios=ratios, abs_errs=abs_errs)


def pooled_stats(raw_list):
    hits, widths, ratios, abs_errs = [], [], [], []
    for r in raw_list:
        hits += r["hits"]
        widths += r["widths"]
        ratios += r["ratios"]
        abs_errs += r["abs_errs"]
    n = len(hits)
    if n == 0:
        return dict(coverage=float("nan"), avg_band_width=float("nan"),
                    coinflip_ratio=float("nan"), mae=float("nan"), n_teams=0)
    return dict(
        coverage=sum(hits) / n,
        avg_band_width=sum(widths) / len(widths) if widths else 0.0,
        coinflip_ratio=sum(ratios) / len(ratios) if ratios else 0.0,
        mae=sum(abs_errs) / len(abs_errs) if abs_errs else 0.0,
        n_teams=n,
    )


def run_checkpoint(base_engine, season_teams, played_so_far, remaining, actual_final,
                    mov_pool, trials, rng, damping):
    current = record_as_of(played_so_far)
    common = sorted(t for t in season_teams if t in actual_final)

    if not remaining:
        empty = dict(hits=[1] * len(common), widths=[0] * len(common),
                     ratios=[], abs_errs=[0] * len(common))
        return dict(dyn=empty, frz=dict(empty), dmp=dict(empty))

    remaining_counts = games_remaining_per_team(remaining)
    dyn_bands = project_bands_dynamic(base_engine, season_teams, current, remaining, mov_pool, trials, rng)
    frz_bands = project_bands_frozen(base_engine, season_teams, current, remaining, trials, rng)
    dmp_bands = project_bands_damped(base_engine, season_teams, current, remaining, mov_pool, trials, rng, damping)

    return dict(
        dyn=raw_scores(dyn_bands, common, actual_final, remaining_counts),
        frz=raw_scores(frz_bands, common, actual_final, remaining_counts),
        dmp=raw_scores(dmp_bands, common, actual_final, remaining_counts),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--seasons", type=str, required=True,
                         help="e.g. '2016-2025' or '2016,2018,2020-2022'")
    parser.add_argument("--variant", default="echo", choices=["echo", "pulse"])
    parser.add_argument("--trials", type=int, default=300)
    parser.add_argument("--damping", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()

    seasons = parse_seasons(args.seasons)
    conn = db.connect(DB_PATH)
    mov_pool = historical_mov_pool(conn)
    rng = random.Random(args.seed)

    pooled = {}
    seasons_used = []

    for season in seasons:
        week_ends, all_games = season_weeks(conn, season)
        if not week_ends:
            print(f"  (skipping {season}: no regular-season games found)")
            continue
        season_teams = {g["home_team"] for g in all_games} | {g["away_team"] for g in all_games}
        actual_final = record_as_of(all_games)
        seasons_used.append(season)

        print(f"Season {season}: {len(week_ends)} weeks")
        for wk in sorted(week_ends):
            cp = week_ends[wk]
            played_so_far = [g for g in all_games if g["date"] <= cp]
            remaining = [g for g in all_games if g["date"] > cp]
            base_engine = build_engine_as_of(conn, args.variant, cp)

            result = run_checkpoint(base_engine, season_teams, played_so_far, remaining,
                                     actual_final, mov_pool, args.trials, rng, args.damping)

            pooled.setdefault(wk, {"dyn": [], "frz": [], "dmp": []})
            pooled[wk]["dyn"].append(result["dyn"])
            pooled[wk]["frz"].append(result["frz"])
            pooled[wk]["dmp"].append(result["dmp"])

    print(f"\nPooled across {len(seasons_used)} seasons: {seasons_used}\n")

    rows = []
    for wk in sorted(pooled):
        d = pooled_stats(pooled[wk]["dyn"])
        f = pooled_stats(pooled[wk]["frz"])
        m = pooled_stats(pooled[wk]["dmp"])
        n_seasons_here = len(pooled[wk]["dyn"])
        rows.append(dict(week=wk, n_seasons=n_seasons_here, n_teams=d["n_teams"],
                          dyn_coverage=d["coverage"], dyn_avg_band_width=d["avg_band_width"],
                          dyn_coinflip_ratio=d["coinflip_ratio"], dyn_mae=d["mae"],
                          frz_coverage=f["coverage"], frz_avg_band_width=f["avg_band_width"],
                          frz_coinflip_ratio=f["coinflip_ratio"], frz_mae=f["mae"],
                          dmp_coverage=m["coverage"], dmp_avg_band_width=m["avg_band_width"],
                          dmp_coinflip_ratio=m["coinflip_ratio"], dmp_mae=m["mae"]))
        print(f"  Week {wk:>2} (n={d['n_teams']:>4} team-seasons, {n_seasons_here} seasons)")
        print(f"           dynamic: band {d['avg_band_width']:>5.2f}  coinflip {d['coinflip_ratio']:>4.2f}x  coverage {d['coverage']:>5.1%}")
        print(f"           damped:  band {m['avg_band_width']:>5.2f}  coinflip {m['coinflip_ratio']:>4.2f}x  coverage {m['coverage']:>5.1%}")
        print(f"           frozen:  band {f['avg_band_width']:>5.2f}  coinflip {f['coinflip_ratio']:>4.2f}x  coverage {f['coverage']:>5.1%}")

    os.makedirs(OUT_DIR, exist_ok=True)
    season_tag = args.seasons.replace(",", "_").replace("-", "to")
    suffix = "" if args.variant == "echo" else f"_{args.variant}"
    fieldnames = ["week", "n_seasons", "n_teams",
                  "dyn_coverage", "dyn_avg_band_width", "dyn_coinflip_ratio", "dyn_mae",
                  "dmp_coverage", "dmp_avg_band_width", "dmp_coinflip_ratio", "dmp_mae",
                  "frz_coverage", "frz_avg_band_width", "frz_coinflip_ratio", "frz_mae"]
    csv_path = os.path.join(OUT_DIR, f"stabilization_pooled_{season_tag}{suffix}.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow(row)

    txt_path = os.path.join(OUT_DIR, f"stabilization_pooled_{season_tag}{suffix}.txt")
    with open(txt_path, "w") as f:
        label = "Echo" if args.variant == "echo" else "Pulse"
        f.write(f"{LEAGUE_LABEL} {label} - Pooled Multi-Season Trust Check\n")
        f.write(f"Seasons: {seasons_used}\n")
        f.write("=" * 100 + "\n")
        f.write(f"{args.trials} trials per checkpoint per season, pooled by week number across\n")
        f.write("every season (week 1 = every season's week 1, etc). COVERAGE target ~80%.\n")
        f.write("COINFLIP RATIO: 1.0 = no better than a coin flip.\n\n")
        f.write(f"{'Week':<6}{'nSea':>6}{'nTeam':>7}  "
                f"{'DynBand':>8}{'DynRat':>8}{'DynCov':>8}   "
                f"{'DmpBand':>8}{'DmpRat':>8}{'DmpCov':>8}   "
                f"{'FrzBand':>8}{'FrzRat':>8}{'FrzCov':>8}\n")
        f.write("-" * 100 + "\n")
        for row in rows:
            f.write(f"{row['week']:<6}{row['n_seasons']:>6}{row['n_teams']:>7}  "
                     f"{row['dyn_avg_band_width']:>8.2f}{row['dyn_coinflip_ratio']:>7.2f}x{row['dyn_coverage']:>8.1%}   "
                     f"{row['dmp_avg_band_width']:>8.2f}{row['dmp_coinflip_ratio']:>7.2f}x{row['dmp_coverage']:>8.1%}   "
                     f"{row['frz_avg_band_width']:>8.2f}{row['frz_coinflip_ratio']:>7.2f}x{row['frz_coverage']:>8.1%}\n")

    print(f"\nWrote {csv_path}")
    print(f"Wrote {txt_path}")


if __name__ == "__main__":
    main()
