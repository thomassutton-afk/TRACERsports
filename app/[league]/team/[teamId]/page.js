"use client";

/**
 * app/[league]/team/[teamId]/page.js — Team Page.
 *
 * Ported from reference/old-site/TeamPage.jsx, restructured league-agnostic
 * the same way All-Time Rankings was: no hardcoded TEAM_NAMES/TEAM_COLORS,
 * historical identity/logos come from lib/historicalIdentity.js (real
 * team_history data, not a hand-typed IDENTITIES map), and the
 * season-by-season table reuses lib/gamesData.js's buildAllTimeRows/
 * tallyPlayoffResults — the exact same reducers All-Time Rankings uses,
 * just fed one team's rows instead of the whole league's.
 *
 * Three tabs, same as the old site: Rating History (the SVG line chart),
 * Season-by-Season (one row per year), Game Log (every game, filterable).
 */

import { useState, useEffect, useMemo } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { getLeagueConfig } from "@/lib/sports/registry";
import { getFillColor } from "@/lib/teamColors";
import {
  fetchTeamChartPoints,
  fetchTeamAllSeasonsGames,
  fetchTeamAllSeasonsPreseasonRatings,
  fetchTeamAllSeasonsPlayoffGames,
  fetchTeamGameLog,
  buildAllTimeRows,
  tallyPlayoffResults,
  getSeasonMaxRounds,
  getSeasonRoundDelta,
  formatDate,
  roundLabel,
} from "@/lib/gamesData";
import {
  fetchTeamHistory,
  getDisplayIdentity,
  fetchLogoIndex,
  resolveHistoricalLogoPath,
} from "@/lib/historicalIdentity";
import HistoricalTeamMark from "../../HistoricalTeamMark";
import Footer from "@/components/Footer";
import AllTimeChart from "../../AllTimeChart";

const VARIANT_LABELS = {
  echo: "Echo carry-forward variant",
  pulse: "Pulse season-reset variant",
};

const GAMES_PER_PAGE = 30;

function fmt1(v) {
  return v != null ? v.toFixed(1) : "—";
}
function fmtRec(w, l) {
  return w != null ? `${w}–${l}` : "—";
}
function fmtPct(v) {
  return v != null ? `${(v * 100).toFixed(0)}%` : "—";
}

export default function TeamPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const league = params.league;
  const teamId = (params.teamId || "").toUpperCase();
  const variant = searchParams.get("variant") || "echo";

  const [activeTab, setActiveTab] = useState("history");

  const [chartPoints, setChartPoints] = useState([]);
  const [chartLoading, setChartLoading] = useState(true);

  const [seasonRawRows, setSeasonRawRows] = useState([]);
  const [preseasonByTeamSeason, setPreseasonByTeamSeason] = useState({});
  const [poBySeason, setPoBySeason] = useState({});
  const [seasonsLoading, setSeasonsLoading] = useState(true);

  const [historyByTeam, setHistoryByTeam] = useState({});
  const [logoIndex, setLogoIndex] = useState({});

  const [games, setGames] = useState([]);
  const [gamesLoading, setGamesLoading] = useState(true);
  const [gameFilter, setGameFilter] = useState("all"); // all | R | P
  const [gameSeason, setGameSeason] = useState("all");
  const [gamePage, setGamePage] = useState(1);

  let leagueConfig;
  let configError = null;
  try {
    leagueConfig = getLeagueConfig(league);
  } catch (e) {
    configError = e.message;
  }

  const team = leagueConfig?.teams?.[teamId];

  // Team history + logo index — independent of variant, fetched once per league.
  useEffect(() => {
    if (!leagueConfig) return;
    fetchTeamHistory(league).then(({ byTeam }) => setHistoryByTeam(byTeam));
    fetchLogoIndex(league).then(setLogoIndex);
  }, [league, leagueConfig]);

  // Rating history chart
  useEffect(() => {
    if (!leagueConfig || !team) return;
    setChartLoading(true);
    fetchTeamChartPoints(league, teamId, variant).then(({ points }) => {
      setChartPoints(points);
      setChartLoading(false);
    });
  }, [league, leagueConfig, teamId, team, variant]);

  // Season-by-season table
  useEffect(() => {
    if (!leagueConfig || !team) return;
    setSeasonsLoading(true);
    Promise.all([
      fetchTeamAllSeasonsGames(league, teamId, variant),
      fetchTeamAllSeasonsPreseasonRatings(league, teamId, variant),
      fetchTeamAllSeasonsPlayoffGames(league, teamId, variant),
    ]).then(([gamesResult, preseasonResult, poResult]) => {
      setSeasonRawRows(buildAllTimeRows(gamesResult.rows));
      setPreseasonByTeamSeason(preseasonResult.byTeamSeason);
      setPoBySeason(tallyPlayoffResults(poResult.poGames, leagueConfig, (row) => row.season));
      setSeasonsLoading(false);
    });
  }, [league, leagueConfig, teamId, team, variant]);

  // Game log — refetches on filter change (season/type), not just team/variant
  useEffect(() => {
    if (!leagueConfig || !team) return;
    setGamesLoading(true);
    setGamePage(1);
    fetchTeamGameLog(league, teamId, variant, {
      type: gameFilter === "all" ? undefined : gameFilter,
      season: gameSeason === "all" ? undefined : Number(gameSeason),
    }).then(({ games }) => {
      setGames(games);
      setGamesLoading(false);
    });
  }, [league, leagueConfig, teamId, team, variant, gameFilter, gameSeason]);

  if (configError) {
    return (
      <div style={{ padding: 40, fontFamily: "var(--font-mono)" }}>
        <p>Unknown league: &quot;{league}&quot;</p>
      </div>
    );
  }
  if (!team) {
    return (
      <div style={{ padding: 40, fontFamily: "var(--font-mono)" }}>
        <p>Unknown team: &quot;{teamId}&quot; in {leagueConfig.label}.</p>
      </div>
    );
  }

  const showPreseason = variant === "echo";
  // Game Log spans every season this team has played - unlike the Season
  // Page (single season, one delta) or All-Time page (delta baked into
  // each row's own tallyPlayoffResults output), here each row can be a
  // DIFFERENT season, so this needs a per-season delta map instead of one
  // number. Derived from this team's own already-loaded games (filtering
  // to its playoff rows) - no extra fetch needed.
  const { seasonMaxRound: teamSeasonMaxRound, configuredMax: teamConfiguredMax } = useMemo(
    () => getSeasonMaxRounds(games.filter((g) => g.type === "P"), leagueConfig),
    [games, leagueConfig]
  );
  const fillColor = getFillColor(team);

  // Enrich season rows with identity/logo/playoff summary, sorted newest-first
  const seasonRows = useMemo(() => {
    return [...seasonRawRows]
      .sort((a, b) => b.season - a.season)
      .map((row) => {
        const identity = getDisplayIdentity(teamId, row.season, historyByTeam, leagueConfig);
        const logoPath = resolveHistoricalLogoPath(teamId, row.season, historyByTeam, logoIndex, league);
        const preseasonElo = preseasonByTeamSeason[`${teamId}-${row.season}`] ?? null;
        const po = poBySeason[row.season];
        return { ...row, identity, logoPath, preseasonElo, po };
      });
  }, [seasonRawRows, historyByTeam, logoIndex, preseasonByTeamSeason, poBySeason, teamId, league, leagueConfig]);

  const currentSeason = seasonRows.length ? Math.max(...seasonRows.map((r) => r.season)) : null;
  const currentRow = seasonRows.find((r) => r.season === currentSeason);
  const totalWins = seasonRows.reduce((s, r) => s + (r.rsW || 0), 0);
  const totalLosses = seasonRows.reduce((s, r) => s + (r.rsL || 0), 0);
  const championships = seasonRows.filter((r) => r.po?.champion).length;

  const chartRatings = chartPoints.map((p) => p.rating);
  const chartPeak = chartRatings.length ? Math.max(...chartRatings) : null;
  const chartTrough = chartRatings.length ? Math.min(...chartRatings) : null;
  const chartCurrent = chartPoints.length ? chartPoints[chartPoints.length - 1]?.rating : null;
  const peakPoint = chartPoints.find((p) => p.rating === chartPeak);
  const troughPoint = chartPoints.find((p) => p.rating === chartTrough);

  const pagedGames = games.slice((gamePage - 1) * GAMES_PER_PAGE, gamePage * GAMES_PER_PAGE);
  const totalGamePages = Math.max(1, Math.ceil(games.length / GAMES_PER_PAGE));

  // Franchise identity legend — only rendered if this team actually has history rows
  const identityEras = historyByTeam[teamId];

  function playoffBadge(po) {
    if (!po || po.highestRound === null) return null;
    const rec = po.rounds[String(po.highestRound)];
    return { label: po.roundLabel, w: rec?.w ?? 0, l: rec?.l ?? 0, champion: po.champion };
  }

  return (
    <div>
      <div className="hero">
        <div>
          <div className="hero-label" style={{ color: fillColor }}>
            Franchise History
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 8 }}>
            <HistoricalTeamMark
              logoPath={null}
              currentLogoTeamId={teamId}
              league={league}
              abbr={teamId}
              color={fillColor}
              size={56}
            />
            <div className="hero-heading" style={{ marginBottom: 0 }}>
              {team.name}
            </div>
          </div>
          <div className="hero-sub">
            {VARIANT_LABELS[variant]}
            <select
              value={teamId}
              onChange={(e) => router.push(`/${league}/team/${e.target.value}?variant=${variant}`)}
              style={{ ...selectStyle, marginLeft: 14 }}
            >
              {Object.keys(leagueConfig.teams)
                .sort()
                .map((tid) => (
                  <option key={tid} value={tid}>
                    {tid} — {leagueConfig.teams[tid].name}
                  </option>
                ))}
            </select>
          </div>
        </div>

        <div style={{ display: "flex", gap: 0 }}>
          <StatCard label="Current Rating" value={fmt1(currentRow?.finalRating)} color={fillColor} />
          <Divider />
          <StatCard label="This Season" value={fmtRec(currentRow?.rsW, currentRow?.rsL)} />
          <Divider />
          <StatCard label="Championships" value={championships > 0 ? `×${championships}` : "0"} color={championships > 0 ? "var(--ut)" : undefined} />
          <Divider />
          <StatCard label="All-Time Peak" value={chartPeak ? chartPeak.toFixed(0) : "—"} color={fillColor} />
          <Divider />
          <StatCard label="All-Time Record" value={`${totalWins.toLocaleString()}–${totalLosses.toLocaleString()}`} />
        </div>
      </div>

      {/* TAB BAR */}
      <div style={{ borderBottom: "1px solid var(--border)", background: "var(--surface)" }}>
        <div style={{ maxWidth: 1280, margin: "0 auto", display: "flex", gap: 4, padding: "0 2rem" }}>
          {[
            { id: "history", label: "Rating History" },
            { id: "seasons", label: "Season-by-Season" },
            { id: "gamelog", label: "Game Log" },
          ].map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 12,
                padding: "12px 16px",
                background: "none",
                border: "none",
                borderBottom: `2px solid ${activeTab === id ? fillColor : "transparent"}`,
                color: activeTab === id ? "var(--text)" : "var(--text3)",
                fontWeight: activeTab === id ? 600 : 400,
                cursor: "pointer",
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "1.5rem 2rem 2rem" }}>
        {/* ===== RATING HISTORY ===== */}
        {activeTab === "history" && (
          <>
            {!chartLoading && chartPoints.length > 0 && (
              <div style={summaryRowStyle}>
                <SummaryCard label="All-Time Peak" value={fmt1(chartPeak)} color={fillColor} desc={peakPoint ? leagueConfig.seasonLabel(peakPoint.season) : ""} />
                <SummaryCard label="All-Time Low" value={fmt1(chartTrough)} color="var(--text3)" desc={troughPoint ? leagueConfig.seasonLabel(troughPoint.season) : ""} />
                <SummaryCard label="Current" value={fmt1(chartCurrent)} color={fillColor} desc={currentSeason ? leagueConfig.seasonLabel(currentSeason) : ""} />
                <SummaryCard label="Games in Dataset" value={chartPoints.length.toLocaleString()} desc={`Across ${new Set(chartPoints.map((p) => p.season)).size} seasons`} />
              </div>
            )}

            <div style={{ borderRadius: 10, border: "1px solid var(--border)", background: "var(--surface)", padding: "20px 16px 8px" }}>
              {chartLoading ? (
                <div style={loadingStyle}>Loading all-time rating data…</div>
              ) : (
                <AllTimeChart points={chartPoints} color={fillColor} seasonLabel={leagueConfig.seasonLabel} width={960} height={340} />
              )}
            </div>

            {identityEras && identityEras.length > 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap", padding: "14px 4px", marginTop: 4 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: 1, fontWeight: 600 }}>
                  Franchise Identities
                </span>
                {identityEras.map((era) => (
                  <span key={`${era.code}-${era.start_season}`} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={identityBadgeStyle(era.primary || fillColor)}>{era.code}</span>
                    <span style={{ fontSize: 12, color: "var(--text2)" }}>
                      {era.name} ({leagueConfig.seasonLabel(era.start_season)}
                      {" – "}
                      {era.end_season ? leagueConfig.seasonLabel(era.end_season) : "present"})
                    </span>
                  </span>
                ))}
              </div>
            )}
          </>
        )}

        {/* ===== SEASON-BY-SEASON ===== */}
        {activeTab === "seasons" && (
          <>
            {seasonsLoading ? (
              <div style={loadingStyle}>Loading season data…</div>
            ) : (
              <div style={{ overflowX: "auto", borderRadius: 10, border: "1px solid var(--border)", background: "var(--surface)" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr>
                      <th style={thStyle("left")}>Season</th>
                      <th style={thStyle("left")}>Identity</th>
                      {showPreseason && <th style={thStyle("right")}>Pre-Season</th>}
                      <th style={thStyle("right")}>RS Record</th>
                      <th style={thStyle("right")}>RS Rating</th>
                      <th style={{ ...thStyle("left"), width: 90 }}>Strength</th>
                      <th style={{ ...thStyle("left"), width: 170 }}>Playoff Result</th>
                      <th style={thStyle("right")}>Final Rating</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(() => {
                      const allFinals = seasonRows.map((r) => r.finalRating || 0);
                      const maxR = Math.max(...allFinals);
                      const minR = Math.min(...allFinals);
                      return seasonRows.map((row, i) => {
                        const isChamp = row.po?.champion;
                        const isCurrent = row.season === currentSeason;
                        const barPct = maxR > minR ? ((row.finalRating - minR) / (maxR - minR)) * 100 : 50;
                        const po = playoffBadge(row.po);

                        return (
                          <tr
                            key={row.season}
                            style={{
                              borderTop: "1px solid var(--border)",
                              background: isChamp ? "var(--acc-dim)" : isCurrent ? "rgba(255,255,255,0.02)" : "transparent",
                            }}
                          >
                            <td style={{ padding: "9px 12px" }}>
                              <span style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: isCurrent ? 700 : 500, color: isCurrent ? fillColor : "var(--text)" }}>
                                {leagueConfig.seasonLabel(row.season)}
                              </span>
                              {isCurrent && <span style={nowBadgeStyle(fillColor)}>Now</span>}
                            </td>
                            <td style={{ padding: "9px 8px" }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                <HistoricalTeamMark logoPath={row.logoPath} currentLogoTeamId={teamId} league={league} abbr={row.identity.code} color={row.identity.primary || fillColor} size={24} />
                                <span style={identityBadgeStyle(row.identity.primary || fillColor)}>{row.identity.code}</span>
                                <span style={{ fontSize: 11, color: "var(--text3)", fontStyle: "italic" }}>{row.identity.name}</span>
                              </div>
                            </td>
                            {showPreseason && (
                              <td style={{ textAlign: "right", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text3)" }}>{fmt1(row.preseasonElo)}</td>
                            )}
                            <td style={{ textAlign: "right", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)" }}>{fmtRec(row.rsW, row.rsL)}</td>
                            <td style={{ textAlign: "right", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 600, color: "var(--text)" }}>{fmt1(row.rsRating)}</td>
                            <td style={{ padding: "0 12px 0 16px" }}>
                              <div style={{ height: 4, background: "var(--border)", borderRadius: 2, width: "100%", minWidth: 60 }}>
                                <div style={{ height: 4, borderRadius: 2, width: `${barPct}%`, background: isChamp ? "var(--ut)" : fillColor }} />
                              </div>
                            </td>
                            <td style={{ padding: "0 12px" }}>
                              {po ? (
                                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: po.champion ? 700 : 500, color: po.champion ? "var(--ut)" : "var(--text2)" }}>
                                  {po.champion ? "Champion" : `${po.label} (${po.w}–${po.l})`}
                                </span>
                              ) : (
                                <span style={{ color: "var(--border2)", fontSize: 12 }}>—</span>
                              )}
                            </td>
                            <td style={{ textAlign: "right", padding: "0 16px" }}>
                              <span style={{ fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 700, color: isChamp ? "var(--ut)" : i === 0 ? fillColor : "var(--text)" }}>
                                {fmt1(row.finalRating)}
                              </span>
                            </td>
                          </tr>
                        );
                      });
                    })()}
                  </tbody>
                </table>
              </div>
            )}

            {!seasonsLoading && seasonRows.length > 0 && (
              <div style={{ padding: "14px 4px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text3)" }}>
                {seasonRows.length} seasons · All-time record: {totalWins.toLocaleString()}–{totalLosses.toLocaleString()} (
                {((totalWins / (totalWins + totalLosses || 1)) * 100).toFixed(1)}%) ·{" "}
                {championships > 0 ? `${championships} championship${championships > 1 ? "s" : ""}` : "No championships"}
              </div>
            )}
          </>
        )}

        {/* ===== GAME LOG ===== */}
        {activeTab === "gamelog" && (
          <>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14, flexWrap: "wrap", gap: 10 }}>
              <span style={{ fontSize: 12, color: "var(--text3)", fontFamily: "var(--font-mono)" }}>
                {gamesLoading ? "Loading…" : `${games.length.toLocaleString()} games`}
              </span>
              <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                <select value={gameSeason} onChange={(e) => setGameSeason(e.target.value)} style={selectStyle}>
                  <option value="all">All Seasons</option>
                  {[...seasonRawRows]
                    .map((r) => r.season)
                    .sort((a, b) => b - a)
                    .map((y) => (
                      <option key={y} value={String(y)}>
                        {leagueConfig.seasonLabel(y)}
                      </option>
                    ))}
                </select>
                {[
                  { id: "all", label: "All" },
                  { id: "R", label: "Regular Season" },
                  { id: "P", label: "Playoffs" },
                ].map(({ id, label }) => (
                  <button key={id} style={pillStyle(gameFilter === id, fillColor)} onClick={() => setGameFilter(id)}>
                    {label}
                  </button>
                ))}
              </div>
            </div>

            {gamesLoading ? (
              <div style={loadingStyle}>Loading game log…</div>
            ) : (
              <>
                <div style={{ overflowX: "auto", borderRadius: 10, border: "1px solid var(--border)", background: "var(--surface)" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr>
                        <th style={thStyle("left")}>Date</th>
                        <th style={thStyle("left")}>Season</th>
                        <th style={thStyle("left")}>Type</th>
                        <th style={thStyle("left")}>Opponent</th>
                        <th style={thStyle("center")}>H/A</th>
                        <th style={thStyle("center")}>Score</th>
                        <th style={thStyle("right")}>Pre-Game</th>
                        <th style={thStyle("right")}>Win Prob</th>
                        <th style={thStyle("right")}>Rating Δ</th>
                        <th style={thStyle("right")}>Post-Game</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pagedGames.map((g) => {
                        const won = g.result === 1;
                        const isPlayoff = g.type === "P";
                        const label = roundLabel(g.round, g.type, leagueConfig, getSeasonRoundDelta(g.season, teamSeasonMaxRound, teamConfiguredMax));
                        const oppColor = leagueConfig.teams[g.opponent_id]?.primary ?? "var(--text3)";

                        return (
                          <tr key={`${g.game_id}-${g.season}-${g.date}`} style={{ borderTop: "1px solid var(--border)" }}>
                            <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text3)" }}>{formatDate(g.date)}</td>
                            <td style={{ padding: "8px 12px", fontFamily: "var(--font-mono)", fontSize: 11, color: fillColor, fontWeight: 500 }}>{leagueConfig.seasonLabel(g.season)}</td>
                            <td style={{ padding: "8px 12px" }}>
                              <span
                                style={{
                                  fontFamily: "var(--font-mono)",
                                  fontSize: 9,
                                  padding: "2px 6px",
                                  borderRadius: 4,
                                  fontWeight: 500,
                                  background: isPlayoff ? "var(--acc-dim)" : "rgba(255,255,255,0.06)",
                                  color: isPlayoff ? "var(--acc)" : "var(--text2)",
                                }}
                              >
                                {isPlayoff ? label : "RS"}
                              </span>
                            </td>
                            <td style={{ padding: "8px 12px" }}>
                              <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600, color: oppColor }}>{g.opponent_id}</span>
                            </td>
                            <td style={{ textAlign: "center", padding: "8px 6px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text3)" }}>{g.home_away}</td>
                            <td style={{ textAlign: "center", padding: "8px 6px", fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: won ? 700 : 400, color: won ? "var(--ut)" : "var(--text2)" }}>
                              {g.points_for}–{g.points_against}
                              {g.ot ? " OT" : ""}
                            </td>
                            <td style={{ textAlign: "right", padding: "0 12px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text3)" }}>{fmt1(g.pre_gm_rate)}</td>
                            <td style={{ textAlign: "right", padding: "0 12px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text3)" }}>{fmtPct(g.expected_win_pct)}</td>
                            <td style={{ textAlign: "right", padding: "0 12px" }}>
                              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color: g.rating_change > 0 ? "#1a7a34" : "#b91c1c" }}>
                                {g.rating_change > 0 ? "+" : ""}
                                {fmt1(g.rating_change)}
                              </span>
                            </td>
                            <td style={{ textAlign: "right", padding: "0 12px", fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600, color: "var(--text)" }}>{fmt1(g.post_gm_rate)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {totalGamePages > 1 && (
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, marginTop: 16 }}>
                    <button style={pageBtnStyle(gamePage === 1)} disabled={gamePage === 1} onClick={() => setGamePage(1)}>
                      «« First
                    </button>
                    <button style={pageBtnStyle(gamePage === 1)} disabled={gamePage === 1} onClick={() => setGamePage((p) => p - 1)}>
                      ← Prev
                    </button>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text3)" }}>
                      Page {gamePage} of {totalGamePages}
                    </span>
                    <button style={pageBtnStyle(gamePage === totalGamePages)} disabled={gamePage === totalGamePages} onClick={() => setGamePage((p) => p + 1)}>
                      Next →
                    </button>
                    <button style={pageBtnStyle(gamePage === totalGamePages)} disabled={gamePage === totalGamePages} onClick={() => setGamePage(totalGamePages)}>
                      Last »»
                    </button>
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>

      <Footer />
    </div>
  );
}

function StatCard({ label, value, color }) {
  return (
    <div style={{ padding: "0 18px", textAlign: "center" }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 20, fontWeight: 700, color: color ?? "var(--text)" }}>{value}</div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text3)", textTransform: "uppercase", letterSpacing: 1, marginTop: 3 }}>{label}</div>
    </div>
  );
}

function Divider() {
  return <div style={{ width: 1, background: "var(--border)", margin: "4px 0" }} />;
}

function SummaryCard({ label, value, color, desc }) {
  return (
    <div style={{ flex: 1, borderRadius: 10, border: "1px solid var(--border)", background: "var(--surface)", padding: "14px 16px" }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)", textTransform: "uppercase", letterSpacing: 1 }}>{label}</div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 22, fontWeight: 700, color: color ?? "var(--text)", margin: "4px 0 2px" }}>{value}</div>
      <div style={{ fontSize: 11, color: "var(--text3)" }}>{desc}</div>
    </div>
  );
}

const summaryRowStyle = { display: "flex", gap: 12, marginBottom: 16 };

const loadingStyle = { padding: "80px 0", textAlign: "center", color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 13 };

function thStyle(align) {
  return {
    fontFamily: "var(--font-mono)",
    fontSize: 9,
    fontWeight: 500,
    color: "var(--text3)",
    textTransform: "uppercase",
    letterSpacing: 1.2,
    padding: "7px 12px",
    textAlign: align,
    whiteSpace: "nowrap",
    background: "var(--surface)",
    borderBottom: "2px solid var(--border)",
  };
}

function identityBadgeStyle(color) {
  return {
    fontFamily: "var(--font-mono)",
    fontSize: 10,
    fontWeight: 700,
    padding: "2px 6px",
    borderRadius: 4,
    border: `1.5px solid ${color}`,
    color,
    letterSpacing: 0.3,
    flexShrink: 0,
  };
}

function nowBadgeStyle(color) {
  return {
    marginLeft: 6,
    fontSize: 9,
    color,
    background: "var(--acc-dim)",
    padding: "1px 5px",
    borderRadius: 3,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: 1,
  };
}

const selectStyle = {
  fontFamily: "var(--font-mono)",
  fontSize: 12,
  padding: "5px 10px",
  border: "1px solid var(--border2)",
  borderRadius: 6,
  background: "var(--surface)",
  color: "var(--text)",
  outline: "none",
};

function pillStyle(active, accentColor) {
  return {
    fontFamily: "var(--font-mono)",
    fontSize: 11,
    padding: "4px 12px",
    borderRadius: 20,
    border: `1px solid ${active ? accentColor : "var(--border2)"}`,
    background: active ? "var(--acc-dim)" : "none",
    color: active ? accentColor : "var(--text2)",
    cursor: "pointer",
    whiteSpace: "nowrap",
    fontWeight: active ? 600 : 400,
  };
}

function pageBtnStyle(disabled) {
  return {
    fontFamily: "var(--font-mono)",
    fontSize: 11,
    padding: "5px 14px",
    border: "1px solid var(--border2)",
    borderRadius: 6,
    background: "transparent",
    color: "var(--acc)",
    cursor: disabled ? "default" : "pointer",
    opacity: disabled ? 0.35 : 1,
  };
}
