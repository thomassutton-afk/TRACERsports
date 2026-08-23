/**
 * Real-rule tiebreaker ranking, mirroring each league's actual documented
 * procedures — see DBs/tiebreakers.py for the source-of-truth writeup and
 * the identical algorithm run at export time (kept in sync manually).
 *
 *   NBA  (NBA_Tiebreaker_Procedures.pdf, ak-static-int.nba.com) — 2-team
 *        order differs from 3+-team order.
 *   WNBA (wnba.com/webview/standings, "Tiebreak Procedure") — one order
 *        regardless of group size; no divisions, no conference-record
 *        step, but adds a ".500 teams" step and a head-to-head-only
 *        point-diff step the NBA doesn't have.
 *   NFL  (nfl.com/standings/tie-breaking-procedures, confirmed Aug 2026)
 *        — one unified order for both within-division and wild-card ties
 *        (see DBs/tiebreakers.py's _criteria_for docstring for why that
 *        simplification is safe). Adds common games, strength of victory/
 *        schedule, and combined points-scored/allowed ranking steps none
 *        of the other leagues have.
 *
 * Previously this whole file lived duplicated inside StandingsTab.jsx,
 * with no NFL branch at all — criteriaFor() silently fell through to
 * NBA's rule list for any league that wasn't explicitly "wnba", which
 * meant NFL ties on the Standings page were being resolved with NBA's
 * criteria (no common games, no strength of victory/schedule, no
 * combined ranking). Extracted here specifically so NflBracketTab.jsx
 * can share the exact same real ranking instead of maintaining its own
 * third implementation, and so the NBA-fallback bug can't recur for
 * whatever league is added after NFL.
 *
 * A tie that survives every real criterion falls back to
 * lib/sports/tiebreakerOverrides.json (written by DBs/tiebreakers.py's
 * interactive cmd.exe prompt when TJ resolves one). If a tie has NO
 * override on file, the two teams keep their incidental order and get
 * flagged with a warning badge in the table — this should be rare, since
 * the export-time check is meant to catch it first.
 */

export function winPct(t) {
  const ties = t.t ?? 0;
  const gp = t.w + t.l + ties;
  return gp === 0 ? 0 : (t.w + ties * 0.5) / gp;
}

function recordVs(teamId, opponentSet, gamesByTeam) {
  const rows = (gamesByTeam[teamId] || []).filter((g) => opponentSet.has(g.opponent_id));
  if (rows.length === 0) return null;
  const wins = rows.filter((g) => (g.points_for ?? 0) > (g.points_against ?? 0)).length;
  return wins / rows.length;
}

function scoreGroupRecord(teamId, group, ctx) {
  const others = new Set(group.filter((id) => id !== teamId));
  return recordVs(teamId, others, ctx.gamesByTeam);
}
function scoreDivisionLeader(teamId, group, ctx) {
  if (!ctx.hasDivisions) return null;
  return ctx.divisionLeaders.has(teamId) ? 1 : 0;
}
function scoreDivisionRecord(teamId, group, ctx) {
  if (!ctx.hasDivisions) return null;
  const divisions = new Set(group.map((id) => ctx.records[id]?.division));
  if (divisions.size !== 1 || divisions.has(null) || divisions.has(undefined)) return null;
  const div = ctx.records[teamId]?.division;
  const opponents = new Set(Object.keys(ctx.records).filter((id) => ctx.records[id].division === div));
  return recordVs(teamId, opponents, ctx.gamesByTeam);
}
function scoreConferenceRecord(teamId, group, ctx) {
  if (!ctx.hasConferences) return null;
  const conf = ctx.records[teamId]?.conference;
  if (conf == null) return null;
  const opponents = new Set(Object.keys(ctx.records).filter((id) => ctx.records[id].conference === conf));
  return recordVs(teamId, opponents, ctx.gamesByTeam);
}
function scorePointDiff(teamId, group, ctx) {
  return ctx.records[teamId]?.pointDiff ?? 0;
}
function scoreVs500Teams(teamId, group, ctx) {
  // WNBA step 2: win pct vs. every team that finished the season .500+.
  const opponents = new Set(
    Object.keys(ctx.records).filter((id) => (ctx.records[id]?.winPct ?? 0) >= 0.5)
  );
  opponents.delete(teamId);
  return recordVs(teamId, opponents, ctx.gamesByTeam);
}
function scoreH2HPointDiff(teamId, group, ctx) {
  // WNBA step 3: point differential in games against the other tied
  // team(s) only — distinct from the season-wide total in step 4.
  const others = new Set(group.filter((id) => id !== teamId));
  const rows = (ctx.gamesByTeam[teamId] || []).filter((g) => others.has(g.opponent_id));
  if (rows.length === 0) return null;
  return rows.reduce((sum, g) => sum + ((g.points_for ?? 0) - (g.points_against ?? 0)), 0);
}

// NFL-only steps below. Each mirrors DBs/tiebreakers.py's Python version
// criterion-for-criterion — see that file's docstrings for the fuller
// reasoning; kept brief here to avoid maintaining the explanation twice.

function commonOpponents(group, ctx) {
  const perTeam = group.map((id) => new Set((ctx.gamesByTeam[id] || []).map((g) => g.opponent_id)));
  if (perTeam.length === 0) return new Set();
  return [...perTeam[0]].filter((id) => perTeam.every((s) => s.has(id))).reduce((s, id) => s.add(id), new Set());
}
function scoreCommonGames(teamId, group, ctx) {
  const common = commonOpponents(group, ctx);
  if (common.size === 0) return null;
  const rows = (ctx.gamesByTeam[teamId] || []).filter((g) => common.has(g.opponent_id));
  if (rows.length < 4) return null; // real rule's minimum sample size
  return recordVs(teamId, common, ctx.gamesByTeam);
}
function scoreCommonGamesNetPoints(teamId, group, ctx) {
  const common = commonOpponents(group, ctx);
  if (common.size === 0) return null;
  const rows = (ctx.gamesByTeam[teamId] || []).filter((g) => common.has(g.opponent_id));
  if (rows.length === 0) return null;
  return rows.reduce((sum, g) => sum + ((g.points_for ?? 0) - (g.points_against ?? 0)), 0);
}
function pooledRecord(teamId, ctx, winsOnly) {
  let rows = ctx.gamesByTeam[teamId] || [];
  if (winsOnly) rows = rows.filter((g) => (g.points_for ?? 0) > (g.points_against ?? 0));
  if (rows.length === 0) return null;
  let w = 0, l = 0;
  for (const g of rows) {
    const opp = ctx.records[g.opponent_id];
    if (!opp) continue;
    w += opp.wins;
    l += opp.losses;
  }
  const gp = w + l;
  return gp === 0 ? null : w / gp;
}
function scoreStrengthOfVictory(teamId, group, ctx) {
  return pooledRecord(teamId, ctx, true);
}
function scoreStrengthOfSchedule(teamId, group, ctx) {
  return pooledRecord(teamId, ctx, false);
}
function rankMap(values) {
  const sortedVals = [...new Set(Object.values(values))].sort((a, b) => b - a);
  const rankByValue = new Map(sortedVals.map((v, i) => [v, i + 1]));
  const out = {};
  for (const [id, v] of Object.entries(values)) out[id] = rankByValue.get(v);
  return out;
}
function scoreCombinedRanking(teamId, ctx, pool) {
  const validPool = pool.filter((id) => ctx.records[id]);
  if (!validPool.includes(teamId)) return null;
  const pf = {}, pa = {};
  for (const id of validPool) { pf[id] = ctx.records[id].pointsFor; pa[id] = -ctx.records[id].pointsAgainst; }
  const pfRanks = rankMap(pf), paRanks = rankMap(pa);
  return -(pfRanks[teamId] + paRanks[teamId]);
}
function scoreCombinedRankingConference(teamId, group, ctx) {
  if (!ctx.hasConferences) return null;
  const conf = ctx.records[teamId]?.conference;
  if (conf == null) return null;
  const pool = Object.keys(ctx.records).filter((id) => ctx.records[id].conference === conf);
  return scoreCombinedRanking(teamId, ctx, pool);
}
function scoreCombinedRankingAll(teamId, group, ctx) {
  return scoreCombinedRanking(teamId, ctx, Object.keys(ctx.records));
}

function criteriaFor(league, groupSize) {
  if (league === "wnba") {
    return [scoreGroupRecord, scoreVs500Teams, scoreH2HPointDiff, scorePointDiff];
  }
  if (league === "nfl") {
    return [scoreGroupRecord, scoreDivisionRecord, scoreCommonGames, scoreConferenceRecord,
            scoreStrengthOfVictory, scoreStrengthOfSchedule, scoreCombinedRankingConference,
            scoreCombinedRankingAll, scoreCommonGamesNetPoints, scorePointDiff];
  }
  return groupSize === 2
    ? [scoreGroupRecord, scoreDivisionLeader, scoreDivisionRecord, scoreConferenceRecord, scorePointDiff]
    : [scoreDivisionLeader, scoreGroupRecord, scoreDivisionRecord, scoreConferenceRecord, scorePointDiff];
}

// Peels a group of teams tied on overall win% down into ordered clusters,
// using the real criteria in the correct order for the group's current
// size, restarting the criteria list on any subgroup still tied after a
// criterion — matching the NBA's official "restart with remaining teams"
// wording. A returned cluster of length 1 is a fully resolved rank; a
// cluster of length 2+ is genuinely unresolved by every real criterion.
export function peel(group, ctx) {
  if (group.length <= 1) return [group];

  const criteria = criteriaFor(ctx.league, group.length);

  for (const scoreFn of criteria) {
    const scores = {};
    for (const id of group) scores[id] = scoreFn(id, group, ctx);
    if (Object.values(scores).some((v) => v === null || v === undefined)) continue;
    const uniqueScores = new Set(Object.values(scores));
    if (uniqueScores.size === 1) continue;

    const orderedScores = [...uniqueScores].sort((a, b) => b - a);
    const result = [];
    for (const s of orderedScores) {
      const subgroup = group.filter((id) => scores[id] === s);
      if (subgroup.length === 1) result.push(subgroup);
      else result.push(...peel(subgroup, ctx));
    }
    return result;
  }
  return [group]; // every criterion exhausted, still fully tied
}

function pairKey(a, b) {
  return [a, b].sort().join("|");
}

function findOverride(overrides, a, b) {
  for (const o of overrides) {
    if (o.above === a && o.below === b) return 1;
    if (o.above === b && o.below === a) return -1;
  }
  return 0;
}

function resolveWithOverrides(cluster, ctx) {
  if (cluster.length === 2) {
    const [a, b] = cluster;
    const dir = findOverride(ctx.overrides, a, b);
    if (dir === 1) return [a, b];
    if (dir === -1) return [b, a];
    ctx.unresolved.add(pairKey(a, b));
    ctx.flaggedIds.add(a);
    ctx.flaggedIds.add(b);
    return cluster; // no override yet — incidental order, flagged in the UI
  }
  const sorted = [...cluster].sort((x, y) => {
    const dir = findOverride(ctx.overrides, x, y);
    return dir === 1 ? -1 : dir === -1 ? 1 : 0;
  });
  for (let i = 0; i < sorted.length; i++) {
    for (let j = i + 1; j < sorted.length; j++) {
      if (findOverride(ctx.overrides, sorted[i], sorted[j]) === 0) {
        ctx.unresolved.add(pairKey(sorted[i], sorted[j]));
        ctx.flaggedIds.add(sorted[i]);
        ctx.flaggedIds.add(sorted[j]);
      }
    }
  }
  return sorted;
}

// Ranks a list of team_ids (any subset — full league, one conference, one
// division) using real tiebreaker criteria instead of a plain win% sort.
export function rankTeams(ids, ctx) {
  const byPct = new Map();
  for (const id of ids) {
    const pct = (ctx.records[id]?.winPct ?? 0).toFixed(10);
    if (!byPct.has(pct)) byPct.set(pct, []);
    byPct.get(pct).push(id);
  }
  const buckets = [...byPct.entries()].sort((a, b) => Number(b[0]) - Number(a[0]));
  const result = [];
  for (const [, group] of buckets) {
    for (const cluster of peel(group, ctx)) {
      result.push(...(cluster.length <= 1 ? cluster : resolveWithOverrides(cluster, ctx)));
    }
  }
  return result;
}

// Seeds one conference's playoff order. Most leagues (NBA since 2015-16,
// WNBA always) just rank by win%/real tiebreakers straight through — a
// division winner gets no automatic seeding boost, only a tiebreaker
// preference within an already-tied group (scoreDivisionLeader above
// already covers that). NFL is genuinely different: the 4 division
// winners are GUARANTEED seeds 1-4 regardless of overall record, and
// only the remaining 3 seeds (5-7) go to the best non-winners. Gated by
// leagueConfig.playoffFormat.divisionWinnersAutoSeed so this can't
// accidentally apply to a league that doesn't actually use this rule.
export function seedConference(teamIds, ctx, leagueConfig) {
  if (!leagueConfig.playoffFormat?.divisionWinnersAutoSeed || !ctx.hasDivisions) {
    return rankTeams(teamIds, ctx);
  }
  const byDiv = {};
  for (const id of teamIds) {
    const div = ctx.records[id]?.division;
    if (div == null) continue;
    (byDiv[div] ??= []).push(id);
  }
  const winners = Object.values(byDiv)
    .map((ids) => rankTeams(ids, ctx)[0])
    .filter(Boolean);
  const winnerSet = new Set(winners);
  const orderedWinners = rankTeams(winners, ctx);
  const wildcards = rankTeams(teamIds.filter((id) => !winnerSet.has(id)), ctx);
  return [...orderedWinners, ...wildcards];
}

export function buildContext(standings, games, leagueConfig, season, variant, tiebreakerOverrides) {
  const gamesByTeam = {};
  for (const g of games) {
    (gamesByTeam[g.team_id] ??= []).push(g);
  }
  const records = {};
  for (const t of standings) {
    const team = leagueConfig.teams[t.team_id];
    const teamGames = gamesByTeam[t.team_id] || [];
    const pointDiff = teamGames.reduce((sum, g) => sum + ((g.points_for ?? 0) - (g.points_against ?? 0)), 0);
    records[t.team_id] = {
      winPct: winPct(t),
      wins: t.w ?? 0,
      losses: t.l ?? 0,
      pointsFor: teamGames.reduce((sum, g) => sum + (g.points_for ?? 0), 0),
      pointsAgainst: teamGames.reduce((sum, g) => sum + (g.points_against ?? 0), 0),
      pointDiff,
      conference: team?.conf ?? null,
      division: team?.div ?? null,
    };
  }
  const hasDivisions = !!leagueConfig.hasDivisions;
  const divisionLeaders = new Set();
  if (hasDivisions) {
    const byDiv = {};
    for (const [tid, r] of Object.entries(records)) {
      if (r.division == null) continue;
      (byDiv[r.division] ??= []).push(tid);
    }
    for (const teamIds of Object.values(byDiv)) {
      let best = teamIds[0];
      for (const tid of teamIds) {
        const cur = records[tid];
        const bestRec = records[best];
        if (cur.winPct > bestRec.winPct || (cur.winPct === bestRec.winPct && cur.pointDiff > bestRec.pointDiff)) {
          best = tid;
        }
      }
      divisionLeaders.add(best);
    }
  }
  const overrides = (tiebreakerOverrides || []).filter(
    (o) => o.league === leagueConfig.id && o.season === season && o.variant === variant
  );
  return {
    gamesByTeam,
    records,
    hasDivisions,
    hasConferences: !!leagueConfig.hasConferences,
    divisionLeaders,
    overrides,
    league: leagueConfig.id,
    unresolved: new Set(),
    flaggedIds: new Set(),
  };
}
