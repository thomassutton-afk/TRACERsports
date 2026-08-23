"use client";

/**
 * StandingsTab — league-agnostic standings.
 *
 * Groups teams into playoff tiers (Auto / Play-In / rest) using each
 * league's own playoffFormat.autoSeeds and playInSeeds — no hardcoded
 * NBA-specific 6/4 split.
 *
 * View toggle depends on the league's actual playoff shape, not a fixed
 * pair of options:
 *   - hasDivisions leagues (NBA): "Conference" (default) / "By Division" —
 *     seeding is still computed per-conference either way.
 *   - Conference-having leagues WITHOUT divisions whose real playoff format
 *     is league-wide, not per-conference (WNBA — top 8 overall, confirmed
 *     in wnba/config.js): "League" (default) / "Conference". "League" seeds
 *     Auto/Play-In/Rest across the FULL standings, matching the real format;
 *     "Conference" is kept as a secondary/browsing view (was previously the
 *     only view, which is what made WNBA's Auto/Play-In tiers wrong — top-8
 *     was being computed per-conference instead of league-wide).
 */

import { useState } from "react";
import TeamMark from "./TeamMark";
import tiebreakerOverrides from "@/lib/sports/tiebreakerOverrides.json";

function winPct(t) {
  const gp = t.w + t.l;
  return gp === 0 ? 0 : t.w / gp;
}

/**
 * Real-rule tiebreaker ranking, mirroring each league's actual documented
 * procedures (see DBs/tiebreakers.py for the source-of-truth writeup and
 * the identical algorithm run at export time — kept in sync manually).
 *
 *   NBA:  2-team order differs from 3+-team order (see criteriaFor below).
 *   WNBA: single order regardless of group size; no divisions, no
 *         conference-record step, but adds a ".500 teams" step and a
 *         head-to-head-only point-diff step the NBA doesn't have.
 *
 * A tie that survives every real criterion falls back to
 * lib/sports/tiebreakerOverrides.json (written by DBs/tiebreakers.py's
 * interactive cmd.exe prompt when TJ resolves one). If a tie has NO
 * override on file, the two teams keep their incidental order and get
 * flagged with a warning badge in the table — this should be rare, since
 * the export-time check is meant to catch it first.
 */
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
  // A fixed bar (not "playoff-eligible teams"), so safe to compute directly.
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

// Real, source-confirmed rule sets per league:
//   NBA  (NBA_Tiebreaker_Procedures.pdf, ak-static-int.nba.com) — order
//        differs between 2-team and 3+-team ties.
//   WNBA (wnba.com/webview/standings, "Tiebreak Procedure") — one order
//        regardless of group size; no divisions, no conference-record
//        step, but adds a ".500 teams" step and a head-to-head-only
//        point-diff step the NBA doesn't have.
function criteriaFor(league, groupSize) {
  if (league === "wnba") {
    return [scoreGroupRecord, scoreVs500Teams, scoreH2HPointDiff, scorePointDiff];
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
function peel(group, ctx) {
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
  // 3+ unresolved cluster: order what pairwise overrides we have, flag any pair still missing one
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
// division) using real tiebreaker criteria instead of the old "wins" tiebreak.
function rankTeams(ids, ctx) {
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

function buildContext(standings, games, leagueConfig, season, variant) {
  const gamesByTeam = {};
  for (const g of games) {
    (gamesByTeam[g.team_id] ??= []).push(g);
  }
  const records = {};
  for (const t of standings) {
    const team = leagueConfig.teams[t.team_id];
    const pointDiff = (gamesByTeam[t.team_id] || []).reduce(
      (sum, g) => sum + ((g.points_for ?? 0) - (g.points_against ?? 0)),
      0
    );
    records[t.team_id] = {
      winPct: winPct(t),
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
  const overrides = tiebreakerOverrides.filter(
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

export default function StandingsTab({ leagueConfig, standings, games = [], season, variant }) {
  const ctx = buildContext(standings, games, leagueConfig, season, variant);
  const hasDivisions = !!leagueConfig.hasDivisions;
  const showLeagueToggle = !hasDivisions && !!leagueConfig.hasConferences;
  const [view, setView] = useState(showLeagueToggle ? "league" : "conference");

  const teamMap = {};
  for (const t of standings) teamMap[t.team_id] = t;

  const allRatings = standings.map((t) => t.rating ?? 0);
  const maxR = Math.max(...allRatings);
  const minR = Math.min(...allRatings);

  const autoSeeds = leagueConfig.playoffFormat?.autoSeeds ?? standings.length;
  const playInSeeds = leagueConfig.playoffFormat?.playInSeeds ?? 0;

  function TeamRow({ t, seed }) {
    const team = leagueConfig.teams[t.team_id];
    const barPct = maxR > minR ? ((t.rating - minR) / (maxR - minR)) * 100 : 50;
    return (
      <tr style={{ borderBottom: "1px solid var(--border)", borderLeft: `4px solid ${team.primary}` }}>
        <td style={{ padding: "0 8px 0 6px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)", width: 26, textAlign: "right", fontWeight: 600 }}>
          {seed ?? "—"}
        </td>
        <td style={{ padding: "9px 8px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <TeamMark team={team} teamId={t.team_id} league={leagueConfig.id} size={24} />
            <span style={{ fontSize: 12, fontWeight: 600, color: "var(--text)" }}>{team.name}</span>
            {ctx.flaggedIds.has(t.team_id) && (
              <span
                title="Tied on every real tiebreaker criterion — needs a manual override in lib/sports/tiebreakerOverrides.json"
                style={{ fontSize: 11, color: "#b45309", cursor: "help" }}
              >
                ⚠
              </span>
            )}
          </div>
        </td>
        <td style={{ padding: "0 8px", fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600, textAlign: "right" }}>{t.w}</td>
        <td style={{ padding: "0 8px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)", textAlign: "right" }}>{t.l}</td>
        <td style={{ padding: "0 8px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text2)", textAlign: "right" }}>
          {(winPct(t) * 100).toFixed(1)}%
        </td>
        <td style={{ padding: "0 10px 0 6px", textAlign: "right" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, justifyContent: "flex-end" }}>
            <div style={{ width: 50, height: 3, background: "var(--border)", borderRadius: 2, flexShrink: 0 }}>
              <div style={{ width: `${barPct}%`, height: 3, borderRadius: 2, background: team.primary }} />
            </div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600, minWidth: 44, textAlign: "right" }}>
              {t.rating?.toFixed(1) ?? "—"}
            </span>
          </div>
        </td>
      </tr>
    );
  }

  function GroupSep({ label, color }) {
    return (
      <tr>
        <td colSpan={5} style={{ padding: 0 }}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "5px 10px",
              background: `${color}12`,
              borderTop: `2px solid ${color}40`,
              borderBottom: `1px solid ${color}20`,
            }}
          >
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: color, flexShrink: 0 }} />
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 8, fontWeight: 700, color, textTransform: "uppercase", letterSpacing: 1.5 }}>
              {label}
            </span>
          </div>
        </td>
      </tr>
    );
  }

  const tableHead = () => (
    <thead>
      <tr>
        {["#", "Team", "W", "L", "Pct", "Rating"].map((label, i) => (
          <th
            key={label}
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 9,
              fontWeight: 500,
              color: "var(--text3)",
              textTransform: "uppercase",
              letterSpacing: 1.2,
              padding: "7px 8px",
              textAlign: i === 1 ? "left" : "right",
              whiteSpace: "nowrap",
              borderBottom: "2px solid var(--border)",
            }}
          >
            {label}
          </th>
        ))}
      </tr>
    </thead>
  );

  function LeagueTable() {
    const allTeams = rankTeams(standings.map((t) => t.team_id), ctx).map((id) => teamMap[id]).filter(Boolean);
    const auto = allTeams.slice(0, autoSeeds);
    const playIn = playInSeeds > 0 ? allTeams.slice(autoSeeds, autoSeeds + playInSeeds) : [];
    const rest = allTeams.slice(autoSeeds + playInSeeds);

    return (
      <div style={{ maxWidth: 640, margin: "0 auto" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: "var(--acc)", textTransform: "uppercase", letterSpacing: 2 }}>
            {leagueConfig.label}
          </span>
          <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
        </div>
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            {tableHead()}
            <tbody>
              <GroupSep label={`Automatic Playoff Berths · Seeds 1–${autoSeeds}`} color="var(--uo)" />
              {auto.map((t, i) => (
                <TeamRow key={t.team_id} t={t} seed={i + 1} />
              ))}
              {playIn.length > 0 && (
                <>
                  <GroupSep label={`Play-In · Seeds ${autoSeeds + 1}–${autoSeeds + playInSeeds}`} color="var(--ut)" />
                  {playIn.map((t, i) => (
                    <TeamRow key={t.team_id} t={t} seed={autoSeeds + i + 1} />
                  ))}
                </>
              )}
              {rest.length > 0 && (
                <>
                  <GroupSep label={`Remaining · Seeds ${autoSeeds + playInSeeds + 1}–${allTeams.length}`} color="var(--acc)" />
                  {rest.map((t, i) => (
                    <TeamRow key={t.team_id} t={t} seed={autoSeeds + playInSeeds + i + 1} />
                  ))}
                </>
              )}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  function ConferenceTable({ confName, confColor }) {
    const cTeamIds = standings.filter((t) => leagueConfig.teams[t.team_id]?.conf === confName).map((t) => t.team_id);
    const cTeams = rankTeams(cTeamIds, ctx).map((id) => teamMap[id]).filter(Boolean);
    const auto = cTeams.slice(0, autoSeeds);
    const playIn = playInSeeds > 0 ? cTeams.slice(autoSeeds, autoSeeds + playInSeeds) : [];
    const rest = cTeams.slice(autoSeeds + playInSeeds);

    if (view === "conference" || !hasDivisions) {
      return (
        <div style={{ flex: "1 1 0", minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: confColor, textTransform: "uppercase", letterSpacing: 2 }}>
              {confName} Conference
            </span>
            <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
          </div>
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              {tableHead()}
              <tbody>
                <GroupSep label={`Automatic Playoff Berths · Seeds 1–${autoSeeds}`} color="var(--uo)" />
                {auto.map((t, i) => (
                  <TeamRow key={t.team_id} t={t} seed={i + 1} />
                ))}
                {playIn.length > 0 && (
                  <>
                    <GroupSep label={`Play-In · Seeds ${autoSeeds + 1}–${autoSeeds + playInSeeds}`} color="var(--ut)" />
                    {playIn.map((t, i) => (
                      <TeamRow key={t.team_id} t={t} seed={autoSeeds + i + 1} />
                    ))}
                  </>
                )}
                {rest.length > 0 && (
                  <>
                    <GroupSep label={`Remaining · Seeds ${autoSeeds + playInSeeds + 1}–${cTeams.length}`} color="var(--acc)" />
                    {rest.map((t, i) => (
                      <TeamRow key={t.team_id} t={t} seed={autoSeeds + playInSeeds + i + 1} />
                    ))}
                  </>
                )}
              </tbody>
            </table>
          </div>
        </div>
      );
    }

    // Division view (only reachable when hasDivisions is true)
    const confSeedMap = {};
    cTeams.forEach((t, i) => {
      confSeedMap[t.team_id] = i + 1;
    });
    const divisions = leagueConfig.divisions[confName] || {};

    return (
      <div style={{ flex: "1 1 0", minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: confColor, textTransform: "uppercase", letterSpacing: 2 }}>
            {confName} Conference
          </span>
          <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {Object.entries(divisions).map(([divName, teamIds]) => {
            const sorted = rankTeams(teamIds.filter((id) => teamMap[id]), ctx).map((id) => teamMap[id]).filter(Boolean);
            return (
              <div key={divName} style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
                <div style={{ padding: "5px 10px", background: "var(--bg)", borderBottom: "1px solid var(--border)" }}>
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 700, color: confColor, textTransform: "uppercase", letterSpacing: 1.5 }}>
                    {divName} Division
                  </span>
                </div>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  {tableHead()}
                  <tbody>
                    {sorted.map((t) => (
                      <TeamRow key={t.team_id} t={t} seed={confSeedMap[t.team_id] ?? null} />
                    ))}
                  </tbody>
                </table>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  if (!leagueConfig.hasConferences) {
    // Fallback for a future league with no conferences at all — one flat table.
    const sorted = rankTeams(standings.map((t) => t.team_id), ctx).map((id) => teamMap[id]).filter(Boolean);
    return (
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          {tableHead()}
          <tbody>
            {sorted.map((t, i) => (
              <TeamRow key={t.team_id} t={t} seed={i + 1} />
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 20 }}>
        {(hasDivisions || showLeagueToggle) && (
          <div style={{ display: "flex", background: "var(--border)", borderRadius: 8, overflow: "hidden", border: "1px solid var(--border2)" }}>
            {(hasDivisions
              ? [
                  ["conference", "Conference"],
                  ["division", "By Division"],
                ]
              : [
                  ["league", "League"],
                  ["conference", "Conference"],
                ]
            ).map(([v, l]) => (
              <button
                key={v}
                onClick={() => setView(v)}
                style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: 11,
                  padding: "5px 14px",
                  cursor: "pointer",
                  border: "none",
                  background: view === v ? "var(--acc)" : "transparent",
                  color: view === v ? "#fff" : "var(--text2)",
                }}
              >
                {l}
              </button>
            ))}
          </div>
        )}
        <span style={{ marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)" }}>
          Sorted by win% · NBA-style tiebreakers
        </span>
      </div>
      {view === "league" ? (
        <LeagueTable />
      ) : (
        <div style={{ display: "flex", gap: 24, alignItems: "flex-start" }}>
          {leagueConfig.conferences.map((confName, i) => (
            <ConferenceTable key={confName} confName={confName} confColor={i === 0 ? "var(--acc)" : "var(--ut)"} />
          ))}
        </div>
      )}
    </div>
  );
}
