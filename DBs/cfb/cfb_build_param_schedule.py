"""
cfb_build_param_schedule.py

Builds CFB_Elo's param_schedule.json using warm-up + rolling 10-year
walk-forward tuning, driven through CFB's REAL engine and season-entry
logic (rebuild.apply_season_entry).

METHODOLOGY - CORRECTED from this script's first draft. The original
version tuned every rolling window from a FRESH, empty engine (matching
NFL_Elo's nfl_tune_engine.py precedent) - meaning the window used to
decide, say, 2010's parameters (2000-2009) started every team flat at
base rating in 2000, throwing away 4+ years of already-known, correct
1996-1999 history for no real reason. That's not circular to fix: the
parameters for every season before the one currently being decided are
ALREADY finalized by the time we get to it (seasons are processed
strictly in chronological order), so there's nothing paradoxical about
seeding a window from real prior state - it's simply reusing an
already-completed computation.

This version instead maintains ONE CONTINUOUS engine (`master_eng`)
that advances forward exactly one season at a time, always using that
season's own ALREADY-DECIDED final parameters - genuinely equivalent to
what production's continuous replay will do. After every season,
master_eng's full state is snapshotted (a cheap deepcopy - team ratings
only, nothing exotic, see engine.py's EloEngine/TeamState - trivial
memory cost across ~30 seasons).

To tune the window for deciding season y (y-10..y-1), the search
branches off a snapshot of master_eng's REAL state as of the end of
season (y-11) - not an artificial flat start - then replays candidate
params ONLY across the window being scored (y-10..y-1). Each candidate
gets its own independent branch (deepcopy of the same seed), same
"fresh branch per candidate" search convention as before - what
changed is WHAT that branch is seeded from, not that it's branched at
all. Once the best candidate is found for season y, master_eng itself
advances by exactly that one season using the winning params, and gets
snapshotted for the next window's seeding.

`is_first_season` (engine.py/rebuild.py's flag that skips conference-
average blending entirely) is passed based on whether a season is the
TRUE first season in the whole dataset (1996) - not "the first season
of whatever window happens to be running." This matters for one real
edge case: the window used to decide 2006 (1996-2005) is IDENTICAL to
the warm-up window, and its first season (1996) genuinely IS the
dataset's true first season - so a flat start there is correct, not a
shortcut. Every rolling window after that seeds from real prior
history, so is_first_season is False throughout.

fcs_rating is NOT tuned here - see cfb_tune_fcs_rating.py and the
project decision to tune it separately (too thin a sample for the same
rolling cadence as alpha/kmax/hfa). This script slots in the already-
tuned era-block values found there (1100 for 1996-2005, 1075 for
2006-2015, 925 for 2016-2025), matched to whichever season is actually
being scheduled, while alpha/kmax/hfa are searched for that season's
window.

kmax's search range is 20-100 (vs NFL_Elo's 20-70) - CFB's known
"2006 parameters" (kmax=96) sit outside NFL's original range.

WARNING: still a heavy compute job - 30 seasons, each a coordinate-
ascent search (3 rounds x ~59 candidate values per round), each
candidate requiring a real multi-season engine replay. The seeding fix
here doesn't change that cost - it fixes CORRECTNESS of what each
window builds on, not how much work scoring it takes. Expect a long
run; this is a "kick off and let it churn" script.

Usage:
    python3 cfb_build_param_schedule.py cfb_elo.db
"""
import copy
import json
import os
import sys

import db
import engine
import rebuild

WARMUP_START = 1996
WARMUP_END = 2005
WINDOW_LEN = 10

# Already-tuned era-block fcs_rating values from cfb_tune_fcs_rating.py's
# 3-way era stability check - see this module's docstring.
FCS_RATING_ERAS = [
    (1996, 2005, 1100),
    (2006, 2015, 1075),
    (2016, 9999, 925),
]


def fcs_rating_for_season(season: int) -> float:
    for lo, hi, val in FCS_RATING_ERAS:
        if lo <= season <= hi:
            return val
    return FCS_RATING_ERAS[-1][2]


def weeks_for_range(games: list[dict], lo: int, hi: int) -> dict:
    subset = [g for g in games if lo <= g["season"] <= hi]
    return rebuild._week_buckets(subset)


def make_params(alpha: float, kmax: float, hfa: float, fcs_rating: float) -> dict:
    p = engine.default_params()
    p["alpha"] = alpha
    p["kmax"] = kmax
    p["hfa"] = hfa
    p["fcs_rating"] = fcs_rating
    return p


def replay_window(conn, seed_eng: "engine.EloEngine", weeks: dict, params: dict,
                   season_rosters: dict, first_season: int) -> tuple["engine.EloEngine", list[dict]]:
    """Branches off a DEEPCOPY of seed_eng (never mutates it) and
    replays every week in `weeks` under one fixed params dict. Used
    BOTH for scoring a candidate during search AND for advancing
    master_eng by its next real season - same operation either way,
    just called with a single-season `weeks` dict for the latter."""
    eng = copy.deepcopy(seed_eng)
    eng.params = params
    current_season = None
    all_rows = []
    for key in sorted(weeks):
        season = key[0]
        if season != current_season:
            rebuild.apply_season_entry(
                conn, eng, season, season_rosters.get(season, set()),
                is_first_season=(season == first_season),
            )
            current_season = season
        week_games = sorted(weeks[key], key=lambda g: g["date"])
        for game_rows in eng.process_week(week_games):
            all_rows.extend(game_rows)
    return eng, all_rows


def log_loss_of(rows: list[dict]) -> float:
    home_rows = [r for r in rows if r["home_away"] == "H"]
    return sum(r["test"] for r in home_rows) / len(home_rows)


def coordinate_ascent(conn, seed_eng: "engine.EloEngine", weeks: dict, fcs_rating: float,
                       season_rosters: dict, first_season: int, rounds: int = 3,
                       start=(0.4, 44.0, 52.0)) -> dict:
    alpha, kmax, hfa = start
    alpha_range = [round(0.01 * i, 2) for i in range(1, 100)]
    kmax_range = [round(0.5 * i, 1) for i in range(10, 400)]   # 5.0 to 199.5, step 0.5
    hfa_range = [round(0.5 * i, 1) for i in range(0, 300)]     # 0.0 to 149.5, step 0.5
    def score(a, k, h):
        params = make_params(a, k, h, fcs_rating)
        _, rows = replay_window(conn, seed_eng, weeks, params, season_rosters, first_season)
        return log_loss_of(rows)

    best_ll = score(alpha, kmax, hfa)

    for _ in range(rounds):
        improved = False

        best_a, best_a_ll = alpha, best_ll
        for a in alpha_range:
            ll = score(a, kmax, hfa)
            if ll < best_a_ll:
                best_a, best_a_ll = a, ll
        if best_a != alpha:
            alpha, best_ll, improved = best_a, best_a_ll, True

        best_k, best_k_ll = kmax, best_ll
        for k in kmax_range:
            ll = score(alpha, k, hfa)
            if ll < best_k_ll:
                best_k, best_k_ll = k, ll
        if best_k != kmax:
            kmax, best_ll, improved = best_k, best_k_ll, True

        best_h, best_h_ll = hfa, best_ll
        for h in hfa_range:
            ll = score(alpha, kmax, h)
            if ll < best_h_ll:
                best_h, best_h_ll = h, ll
        if best_h != hfa:
            hfa, best_ll, improved = best_h, best_h_ll, True

        if not improved:
            break

    return {"alpha": alpha, "kmax": kmax, "hfa": hfa, "train_log_loss": best_ll}


def build_schedule(conn, games: list[dict], resets: set, season_rosters: dict,
                    rounds: int = 3) -> dict:
    first_season = games[0]["season"]
    schedule = {}
    snapshots = {}

    master_eng = engine.EloEngine(engine.default_params(), resets=resets)
    snapshots[first_season - 1] = copy.deepcopy(master_eng)  # true pre-history: empty

    print(f"=== Warm-up tune ({WARMUP_START}-{WARMUP_END}, in-sample, "
          f"seeded from true pre-history) ===")
    warmup_weeks = weeks_for_range(games, WARMUP_START, WARMUP_END)
    warmup_fcs = fcs_rating_for_season(WARMUP_START)
    warmup_result = coordinate_ascent(
        conn, snapshots[first_season - 1], warmup_weeks, warmup_fcs,
        season_rosters, first_season, rounds=rounds,
    )
    print(f"  alpha={warmup_result['alpha']} kmax={warmup_result['kmax']} "
          f"hfa={warmup_result['hfa']} fcs_rating={warmup_fcs} "
          f"train_log_loss={warmup_result['train_log_loss']:.4f}")

    for y in range(WARMUP_START, WARMUP_END + 1):
        y_fcs = fcs_rating_for_season(y)
        params = make_params(warmup_result["alpha"], warmup_result["kmax"], warmup_result["hfa"], y_fcs)
        weeks_y = weeks_for_range(games, y, y)
        master_eng, _ = replay_window(conn, master_eng, weeks_y, params, season_rosters, first_season)
        snapshots[y] = copy.deepcopy(master_eng)
        schedule[y] = {"alpha": warmup_result["alpha"], "kmax": warmup_result["kmax"],
                        "hfa": warmup_result["hfa"], "fcs_rating": y_fcs}

    print(f"\n=== Rolling {WINDOW_LEN}-year walk-forward ({WARMUP_END + 1} onward), "
          f"seeded from real prior state ===")
    seasons = sorted({g["season"] for g in games})
    for y in [s for s in seasons if s > WARMUP_END]:
        lo, hi = y - WINDOW_LEN, y - 1
        seed = snapshots[lo - 1]
        weeks = weeks_for_range(games, lo, hi)
        y_fcs = fcs_rating_for_season(y)

        result = coordinate_ascent(conn, seed, weeks, y_fcs, season_rosters, first_season, rounds=rounds)

        final_params = make_params(result["alpha"], result["kmax"], result["hfa"], y_fcs)
        weeks_y = weeks_for_range(games, y, y)
        master_eng, _ = replay_window(conn, master_eng, weeks_y, final_params, season_rosters, first_season)
        snapshots[y] = copy.deepcopy(master_eng)

        schedule[y] = {"alpha": result["alpha"], "kmax": result["kmax"],
                        "hfa": result["hfa"], "fcs_rating": y_fcs}
        print(f"  season {y} (tuned on {lo}-{hi}, seeded from real end-of-{lo - 1} state): "
              f"alpha={result['alpha']} kmax={result['kmax']} hfa={result['hfa']} "
              f"fcs_rating={y_fcs} train_log_loss={result['train_log_loss']:.4f}")

    return schedule


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "cfb_elo.db")
    out_path = sys.argv[2] if len(sys.argv) > 2 else "param_schedule.json"
    conn = db.connect(db_path)

    games = db.load_games(conn)
    if not games:
        print(f"No games found in {db_path}.")
        sys.exit(1)
    rebuild._annotate_conferences(conn, games)
    resets = db.load_resets(conn)
    season_rosters = rebuild._season_fbs_teams(games)

    print(f"Loaded {len(games):,} games ({games[0]['season']}-{games[-1]['season']}).\n")

    schedule = build_schedule(conn, games, resets, season_rosters)

    out = {
        str(y): {k: schedule[y][k] for k in ("alpha", "kmax", "hfa", "fcs_rating")}
        for y in sorted(schedule)
    }
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\nWrote {len(out)} season(s) -> {out_path}")


if __name__ == "__main__":
    main()
