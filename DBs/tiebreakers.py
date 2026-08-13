"""
Real-rule standings tiebreakers, run at export time (from cmd.exe, via
export_to_supabase.py) rather than silently in the browser.

Implements each league's actual documented tiebreaker procedure — see
_criteria_for() for the exact source-confirmed order used per league:

  NBA  (NBA_Tiebreaker_Procedures.pdf, ak-static-int.nba.com)
    2 teams tied:   head-to-head -> division leader -> division record
                    -> conference record -> point differential
    3+ teams tied:  division leader -> combined record among tied teams
                    -> division record -> conference record -> point diff

  WNBA (wnba.com/webview/standings, "Tiebreak Procedure")
    Same order regardless of group size (no divisions, no conference-
    record step):
      head-to-head/combined record among tied teams
      -> win% vs. all teams that finished the season .500 or better
      -> point differential in head-to-head games only
      -> point differential against all opponents

Both leagues restart the criteria list from the top on any subgroup
still tied after a criterion resolves some (but not all) of the group —
matching each league's official "restart" wording.

Deliberately NOT implemented (extremely rare in practice, and each adds
real complexity for almost no real-world payoff):
  - "Record vs. playoff-eligible teams" (NBA) — circular, depends on who's
    in the playoff picture, which is the thing being determined
  - Either league's random-drawing fallback (doesn't apply to a website)
Ties that survive every real criterion above fall through to the manual
override system below instead.

Overrides are stored in lib/sports/tiebreakerOverrides.json as a flat list
of {league, season, variant, above, below} entries. This module both reads
existing overrides (to silently resolve a tie that's already been handled)
and writes new ones (when TJ answers the interactive prompt below).
"""

import json
import os
from collections import defaultdict

from team_divisions import LEAGUE_HAS_DIVISIONS, LEAGUE_HAS_CONFERENCES, conf_div


def overrides_path():
    return os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "lib", "sports", "tiebreakerOverrides.json")
    )


def load_overrides():
    path = overrides_path()
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_override(league, season, variant, above, below):
    path = overrides_path()
    overrides = load_overrides()
    for o in overrides:
        if (
            o.get("league") == league
            and o.get("season") == season
            and o.get("variant") == variant
            and o.get("above") == above
            and o.get("below") == below
        ):
            return  # already saved, nothing to do
    overrides.append(
        {"league": league, "season": season, "variant": variant, "above": above, "below": below}
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2)
        f.write("\n")


def _find_override(overrides, league, season, variant, a, b):
    """Returns 1 if a should rank above b, -1 if b above a, 0 if no override exists."""
    for o in overrides:
        if o.get("league") == league and o.get("season") == season and o.get("variant") == variant:
            if o.get("above") == a and o.get("below") == b:
                return 1
            if o.get("above") == b and o.get("below") == a:
                return -1
    return 0


class _Ctx:
    def __init__(self, records, games_by_team, has_divisions, has_conferences, division_leaders, league):
        self.records = records
        self.games_by_team = games_by_team
        self.has_divisions = has_divisions
        self.has_conferences = has_conferences
        self.division_leaders = division_leaders
        self.league = league


def _record_vs(team_id, opponents, games_by_team):
    """Win pct of team_id against games whose opponent_id is in `opponents`."""
    rows = [g for g in games_by_team[team_id] if g["opponent_id"] in opponents]
    w = sum(g["w"] or 0 for g in rows)
    l = sum(g["l"] or 0 for g in rows)
    gp = w + l
    return None if gp == 0 else w / gp


def _score_group_record(team_id, group, ctx):
    """Head-to-head (2-team groups) or combined record among tied teams (3+)."""
    others = set(group) - {team_id}
    return _record_vs(team_id, others, ctx.games_by_team)


def _score_division_leader(team_id, group, ctx):
    if not ctx.has_divisions:
        return None
    return 1 if team_id in ctx.division_leaders else 0


def _score_division_record(team_id, group, ctx):
    if not ctx.has_divisions:
        return None
    divisions = {ctx.records[t]["division"] for t in group}
    if len(divisions) != 1 or None in divisions:
        return None  # only applies when every tied team shares one division
    div = ctx.records[team_id]["division"]
    opponents = {t for t, r in ctx.records.items() if r["division"] == div}
    return _record_vs(team_id, opponents, ctx.games_by_team)


def _score_conference_record(team_id, group, ctx):
    if not ctx.has_conferences:
        return None
    conf = ctx.records[team_id]["conference"]
    if conf is None:
        return None
    opponents = {t for t, r in ctx.records.items() if r["conference"] == conf}
    return _record_vs(team_id, opponents, ctx.games_by_team)


def _score_point_diff(team_id, group, ctx):
    return ctx.records[team_id]["point_diff"]


def _score_vs_500_teams(team_id, group, ctx):
    """WNBA step 2: win pct against every team that finished the season
    .500 or better. This is a fixed bar (not "playoff-eligible teams",
    which would be circular), so it's safe to compute directly."""
    opponents = {t for t, r in ctx.records.items() if r["win_pct"] >= 0.5} - {team_id}
    return _record_vs(team_id, opponents, ctx.games_by_team)


def _score_h2h_point_diff(team_id, group, ctx):
    """WNBA step 3: point differential in games against the other tied
    team(s) only — distinct from the season-wide point diff in step 4."""
    others = set(group) - {team_id}
    rows = [g for g in ctx.games_by_team[team_id] if g["opponent_id"] in others]
    if not rows:
        return None
    return sum((r["points_for"] or 0) - (r["points_against"] or 0) for r in rows)


def _criteria_for(league, group_size):
    """
    Real, source-confirmed rule sets:
      NBA  (ak-static-int.nba.com NBA_Tiebreaker_Procedures.pdf) — order
           differs between 2-team and 3+-team ties.
      WNBA (wnba.com/webview/standings, "Tiebreak Procedure") — one order
           regardless of group size; no divisions, no conference-record
           step, but adds a ".500 teams" step and a head-to-head-only
           point-diff step the NBA doesn't have.
    """
    if league == "wnba":
        return [_score_group_record, _score_vs_500_teams, _score_h2h_point_diff, _score_point_diff]
    if group_size == 2:
        return [_score_group_record, _score_division_leader, _score_division_record,
                _score_conference_record, _score_point_diff]
    return [_score_division_leader, _score_group_record, _score_division_record,
            _score_conference_record, _score_point_diff]


def _peel(group, ctx):
    """
    Resolves a group of teams tied on overall win%, using the real criteria
    in the correct order for the group's current size, and RESTARTING the
    criteria list (from the top, for the new smaller size) on any subgroup
    that's still tied after a criterion — matching the NBA's official
    "restart with remaining teams" procedure.

    Returns a list of clusters (each a list of team_ids). A cluster of size
    1 is a fully resolved rank; a cluster of size 2+ is genuinely
    unresolved by every real criterion and needs a manual override.
    """
    if len(group) <= 1:
        return [group]

    criteria = _criteria_for(ctx.league, len(group))

    for score_fn in criteria:
        scores = {tid: score_fn(tid, group, ctx) for tid in group}
        if any(v is None for v in scores.values()):
            continue  # criterion not applicable to this group at all — skip it
        if len(set(scores.values())) == 1:
            continue  # doesn't differentiate anyone — try the next criterion

        ordered_scores = sorted(set(scores.values()), reverse=True)
        result = []
        for s in ordered_scores:
            subgroup = [tid for tid in group if scores[tid] == s]
            if len(subgroup) == 1:
                result.append(subgroup)
            else:
                result.extend(_peel(subgroup, ctx))  # restart criteria for the remaining tie
        return result

    return [group]  # every criterion exhausted, still fully tied


def _compute_division_leaders(records, has_divisions):
    if not has_divisions:
        return set()
    by_division = defaultdict(list)
    for tid, r in records.items():
        if r["division"] is not None:
            by_division[r["division"]].append(tid)
    leaders = set()
    for teams in by_division.values():
        # Simplification: division-winner ties broken by point differential
        # rather than the NBA's full recursive division-winner procedure —
        # a division lead being itself tied on both win% AND point diff is
        # rare enough not to warrant the extra complexity here.
        best = max(teams, key=lambda t: (records[t]["win_pct"], records[t]["point_diff"]))
        leaders.add(best)
    return leaders


def _prompt_pair(a, b, name_by_code, league, season, variant, overrides):
    print(f"\n\u26a0 UNRESOLVED TIE \u2014 {league} {season} {variant}")
    print(f"  {name_by_code.get(a, a)} ({a}) vs {name_by_code.get(b, b)} ({b}) "
          f"\u2014 tied on every real tiebreaker criterion")
    while True:
        try:
            ans = input(f"Which team should rank higher? [{a}/{b}]: ").strip().upper()
        except EOFError:
            print(f"  No input available \u2014 add an override for {a}/{b} in "
                  f"lib/sports/tiebreakerOverrides.json before trusting this export.\n")
            return
        if ans in (a, b):
            other = b if ans == a else a
            save_override(league, season, variant, ans, other)
            overrides.append({"league": league, "season": season, "variant": variant,
                               "above": ans, "below": other})
            print(f"\u2713 Override saved: {ans} ranks above {other} ({league}, {season}, {variant})\n")
            return
        print(f"  Please enter {a} or {b}.")


def _prompt_group(codes, name_by_code, league, season, variant, overrides):
    print(f"\n\u26a0 UNRESOLVED TIE ({len(codes)}-way) \u2014 {league} {season} {variant}")
    names = ", ".join(f"{name_by_code.get(c, c)} ({c})" for c in codes)
    print(f"  {names} \u2014 all tied on every real tiebreaker criterion")
    while True:
        try:
            ans = input(f"Enter final order, highest to lowest, space-separated "
                        f"(e.g. {' '.join(codes)}): ").strip().upper()
        except EOFError:
            print(f"  No input available \u2014 add overrides for {', '.join(codes)} in "
                  f"lib/sports/tiebreakerOverrides.json before trusting this export.\n")
            return
        order = ans.split()
        if sorted(order) == sorted(codes):
            for i in range(len(order)):
                for j in range(i + 1, len(order)):
                    save_override(league, season, variant, order[i], order[j])
                    overrides.append({"league": league, "season": season, "variant": variant,
                                       "above": order[i], "below": order[j]})
            print(f"\u2713 Overrides saved for {len(codes)}-way tie ({league}, {season}, {variant})\n")
            return
        print(f"  Please enter exactly these codes, space-separated: {', '.join(codes)}")


def check_tiebreakers(games_rows, league, variant, name_by_code, interactive=True):
    """
    games_rows: the per-variant list built by build_games() in
                export_to_supabase.py (one row per team per game).
    name_by_code: {team_id: full_name}, for readable prompts/output.
    """
    reg = [g for g in games_rows if g["type"] == "R"]
    if not reg:
        return
    season = max(g["season"] for g in reg)
    reg = [g for g in reg if g["season"] == season]

    games_by_team = defaultdict(list)
    for g in reg:
        games_by_team[g["team_id"]].append(g)

    records = {}
    for team_id, rows in games_by_team.items():
        wins = sum(r["w"] or 0 for r in rows)
        losses = sum(r["l"] or 0 for r in rows)
        gp = wins + losses
        if gp == 0:
            continue  # hasn't played yet this season — nothing to tiebreak
        conf, div = conf_div(league, team_id)
        records[team_id] = {
            "wins": wins,
            "losses": losses,
            "win_pct": wins / gp,
            "point_diff": sum((r["points_for"] or 0) - (r["points_against"] or 0) for r in rows),
            "conference": conf,
            "division": div,
        }

    if len(records) < 2:
        return

    has_divisions = LEAGUE_HAS_DIVISIONS.get(league, False)
    has_conferences = LEAGUE_HAS_CONFERENCES.get(league, False)
    division_leaders = _compute_division_leaders(records, has_divisions)
    ctx = _Ctx(records, games_by_team, has_divisions, has_conferences, division_leaders, league)

    by_pct = defaultdict(list)
    for tid, r in records.items():
        by_pct[round(r["win_pct"], 10)].append(tid)

    overrides = load_overrides()

    for group in by_pct.values():
        if len(group) < 2:
            continue
        for cluster in _peel(group, ctx):
            if len(cluster) < 2:
                continue
            if len(cluster) == 2:
                a, b = cluster
                existing = _find_override(overrides, league, season, variant, a, b)
                if existing != 0:
                    winner, loser = (a, b) if existing == 1 else (b, a)
                    print(f"  (tie {a} vs {b} resolved via existing override: "
                          f"{winner} above {loser})")
                    continue
                _prompt_pair(a, b, name_by_code, league, season, variant, overrides) if interactive \
                    else print(f"\n\u26a0 UNRESOLVED TIE \u2014 {league} {season} {variant}: "
                               f"{a} vs {b} \u2014 add an override before trusting this export.\n")
            else:
                _prompt_group(cluster, name_by_code, league, season, variant, overrides) if interactive \
                    else print(f"\n\u26a0 UNRESOLVED TIE \u2014 {league} {season} {variant}: "
                               f"{', '.join(cluster)} \u2014 add overrides before trusting this export.\n")
