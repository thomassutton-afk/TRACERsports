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
import { rankTeams, seedConference, buildContext, winPct } from "@/lib/tiebreakers";

export default function StandingsTab({ leagueConfig, standings, games = [], season, variant }) {
  const ctx = buildContext(standings, games, leagueConfig, season, variant, tiebreakerOverrides);
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
        {leagueConfig.hasTies && (
          <td style={{ padding: "0 8px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)", textAlign: "right" }}>{t.t ?? 0}</td>
        )}
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
        <td colSpan={colCount} style={{ padding: 0 }}>
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

  const columnLabels = leagueConfig.hasTies ? ["#", "Team", "W", "L", "T", "Pct", "Rating"] : ["#", "Team", "W", "L", "Pct", "Rating"];
  const colCount = columnLabels.length;

  const tableHead = () => (
    <thead>
      <tr>
        {columnLabels.map((label, i) => (
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
        <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, overflow: "auto" }}>
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
    const cTeams = seedConference(cTeamIds, ctx, leagueConfig).map((id) => teamMap[id]).filter(Boolean);
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
          <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, overflow: "auto" }}>
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
              <div key={divName} style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, overflow: "auto" }}>
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
      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, overflow: "auto" }}>
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
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 20, flexWrap: "wrap" }}>
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
        <div className="standings-conf-row">
          {leagueConfig.conferences.map((confName, i) => (
            <ConferenceTable key={confName} confName={confName} confColor={i === 0 ? "var(--acc)" : "var(--ut)"} />
          ))}
        </div>
      )}
    </div>
  );
}
