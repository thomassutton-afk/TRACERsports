"use client";

/**
 * app/[league]/all-time/page.js — All-Time Rankings.
 *
 * Ported from reference/old-site/AllTimeRankings.jsx, restructured to be
 * league-agnostic (reads leagueConfig instead of a hardcoded NBA-only
 * TEAM_NAMES/TEAM_COLORS dict, and derives playoff-depth filters from
 * leagueConfig.engine.roundLabels instead of hardcoded r1/r2/r3/finals)
 * and to query the tables that actually exist in the new schema — the old
 * page read season_standings/season_records views that were never carried
 * over; this instead aggregates from games/preseason_ratings the same way
 * Season Page does (lib/gamesData.js's all-time helpers), just across
 * every season at once instead of one.
 *
 * Season-aware historical identity (name/abbreviation/logo) comes from
 * lib/historicalIdentity.js, backed by the real team_history table rather
 * than a hand-maintained map — see that file's header comment.
 *
 * Team names link to the Team page (app/[league]/team/[teamId]/page.js).
 */

import { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { getLeagueConfig } from "@/lib/sports/registry";
import { getFillColor, getTextColor } from "@/lib/teamColors";
import {
  fetchAllTimeTeamGames,
  fetchAllTimePreseasonRatings,
  fetchAllTimePlayoffGames,
  buildAllTimeRows,
  tallyPlayoffResults,
} from "@/lib/gamesData";
import {
  fetchTeamHistory,
  getDisplayIdentity,
  fetchLogoIndex,
  resolveHistoricalLogoPath,
} from "@/lib/historicalIdentity";
import HistoricalTeamMark from "../HistoricalTeamMark";
import Footer from "@/components/Footer";

const DECADES = ["All Eras", "1990s", "2000s", "2010s", "2020s"];
const PER_PAGE = 50;

function inDecade(season, decade) {
  if (decade === "1990s") return season <= 2000;
  if (decade === "2000s") return season > 2000 && season <= 2010;
  if (decade === "2010s") return season > 2010 && season <= 2020;
  if (decade === "2020s") return season > 2020;
  return true;
}

// Playoff-depth filter pills, derived from this league's actual round
// structure instead of hardcoded NBA round numbers — a league with 3
// playoff rounds (WNBA) gets 3 depth tiers + champion, a league with 4
// (NBA) gets 4. Round 1 is skipped as its own tier since it's redundant
// with "Made Playoffs" (every playoff team has at least a Round 1 result).
function buildDepthFilters(leagueConfig) {
  const roundLabels = leagueConfig.engine?.roundLabels ?? {};
  const order = leagueConfig.engine?.playoffRoundOrder ?? [];

  const filters = [
    { id: "all", label: "All Seasons" },
    { id: "playoffs", label: "Made Playoffs" },
  ];
  for (let r = 2; r <= order.length; r++) {
    // Old-site wording: label describes the round just won (r-1), not the
    // round reached (r) — e.g. reaching Conf. Semis (round 2) is phrased
    // "Won Round 1", matching reference/old-site/AllTimeRankings.jsx.
    // order[r-2] is the round-code for rank (r-1) — rank is 1-based,
    // array is 0-based, so rank (r-1) sits at index (r-1)-1 = r-2.
    const priorRoundLabel = roundLabels[order[r - 2]] ?? `Round ${r - 1}`;
    filters.push({ id: `round${r}`, label: `Won ${priorRoundLabel}` });
  }
  filters.push({ id: "champion", label: "Champions Only" });
  return filters;
}

function fmt1(v) {
  return v != null ? v.toFixed(1) : "—";
}
function fmtRec(w, l) {
  return w != null ? `${w}–${l}` : "—";
}

export default function AllTimeRankingsPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const league = params.league;
  const variant = searchParams.get("variant") || "echo";

  const [depth, setDepth] = useState("all");
  const [decade, setDecade] = useState("All Eras");
  const [teamSearch, setTeamSearch] = useState("");
  const [sortCol, setSortCol] = useState("finalRating");
  const [sortDir, setSortDir] = useState("desc");
  const [page, setPage] = useState(1);

  const [rows, setRows] = useState([]);
  const [preseasonByTeamSeason, setPreseasonByTeamSeason] = useState({});
  const [poByTeamSeason, setPoByTeamSeason] = useState({});
  const [historyByTeam, setHistoryByTeam] = useState({});
  const [logoIndex, setLogoIndex] = useState({});
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);

  let leagueConfig;
  let configError = null;
  try {
    leagueConfig = getLeagueConfig(league);
  } catch (e) {
    configError = e.message;
  }

  // Team history + logo index — independent of variant, fetched once per league.
  useEffect(() => {
    if (!leagueConfig) return;
    fetchTeamHistory(league).then(({ byTeam }) => setHistoryByTeam(byTeam));
    fetchLogoIndex(league).then(setLogoIndex);
  }, [league, leagueConfig]);

  // The actual all-time data — every team-season this league has, for the
  // selected variant. This is the expensive query (150k+ game rows for a
  // 30-season league), so it runs once per variant switch, not per filter
  // change — filtering/sorting/paginating below is all client-side.
  useEffect(() => {
    if (!leagueConfig) return;
    setLoading(true);
    Promise.all([
      fetchAllTimeTeamGames(league, variant),
      fetchAllTimePreseasonRatings(league, variant),
      fetchAllTimePlayoffGames(league, variant),
    ]).then(([gamesResult, preseasonResult, poResult]) => {
      if (gamesResult.error) {
        setFetchError(gamesResult.error);
        setRows([]);
      } else {
        setFetchError(null);
        setRows(buildAllTimeRows(gamesResult.rows));
      }
      setPreseasonByTeamSeason(preseasonResult.byTeamSeason);
      setPoByTeamSeason(
        tallyPlayoffResults(poResult.poGames, leagueConfig, (row) => `${row.team_id}-${row.season}`)
      );
      setLoading(false);
    });
  }, [league, leagueConfig, variant]);

  if (configError) {
    return (
      <div style={{ padding: 40, fontFamily: "var(--font-mono)" }}>
        <p>Unknown league: &quot;{league}&quot;</p>
        <p>{configError}</p>
      </div>
    );
  }

  const showPreseason = variant === "echo";
  const depthFilters = buildDepthFilters(leagueConfig);

  // Enrich raw rows with derived fields once — playoff summary, delta,
  // historical identity, logo path — before filtering/sorting/paginating.
  const enriched = useMemo(() => {
    return rows.map((row) => {
      const key = `${row.team_id}-${row.season}`;
      const po = poByTeamSeason[key];
      const identity = getDisplayIdentity(row.team_id, row.season, historyByTeam, leagueConfig);
      const logoPath = resolveHistoricalLogoPath(row.team_id, row.season, historyByTeam, logoIndex, league);
      const preseasonElo = preseasonByTeamSeason[key] ?? null;
      const ratingDelta =
        row.finalRating != null && row.rsRating != null ? row.finalRating - row.rsRating : null;
      return { ...row, po, identity, logoPath, preseasonElo, ratingDelta };
    });
  }, [rows, poByTeamSeason, historyByTeam, logoIndex, preseasonByTeamSeason, leagueConfig]);

  const filtered = useMemo(() => {
    let out = enriched.filter((r) => leagueConfig.teams[r.team_id]); // skip rows for unknown team_ids

    if (depth === "playoffs") out = out.filter((r) => r.po && Object.keys(r.po.rounds).length > 0);
    else if (depth === "champion") out = out.filter((r) => r.po?.champion);
    else if (depth.startsWith("round")) {
      const need = Number(depth.replace("round", ""));
      out = out.filter((r) => r.po?.effectiveHighestRound != null && r.po.effectiveHighestRound >= need);
    }

    out = out.filter((r) => inDecade(r.season, decade));

    if (teamSearch.trim()) {
      const q = teamSearch.trim().toLowerCase();
      out = out.filter((r) => {
        const currentName = leagueConfig.teams[r.team_id]?.name ?? "";
        return (
          r.team_id.toLowerCase().includes(q) ||
          currentName.toLowerCase().includes(q) ||
          (r.identity.name || "").toLowerCase().includes(q)
        );
      });
    }

    out = [...out].sort((a, b) => {
      const dir = sortDir === "asc" ? 1 : -1;
      const av = a[sortCol] ?? (sortDir === "asc" ? Infinity : -Infinity);
      const bv = b[sortCol] ?? (sortDir === "asc" ? Infinity : -Infinity);
      if (typeof av === "string") return dir * av.localeCompare(bv);
      return dir * (av - bv);
    });

    return out;
  }, [enriched, depth, decade, teamSearch, sortCol, sortDir, leagueConfig]);

  const overallRankMap = useMemo(() => {
    const bySortField = [...filtered].sort((a, b) => (b.finalRating ?? 0) - (a.finalRating ?? 0));
    const map = {};
    bySortField.forEach((r, i) => {
      map[`${r.team_id}-${r.season}`] = i + 1;
    });
    return map;
  }, [filtered]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PER_PAGE));
  const pageRows = filtered.slice((page - 1) * PER_PAGE, page * PER_PAGE);

  function handleSort(col) {
    if (sortCol === col) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else {
      setSortCol(col);
      setSortDir(col === "team_id" || col === "season" ? "asc" : "desc");
    }
    setPage(1);
  }

  function playoffBadge(row) {
    const po = row.po;
    if (!po || po.highestRound === null) return null;
    const rec = po.rounds[String(po.highestRound)];
    return { label: po.roundLabel, w: rec?.w ?? 0, l: rec?.l ?? 0, champion: po.champion };
  }

  return (
    <div>
      <div className="hero">
        <div>
          <div className="hero-label">Historical Record</div>
          <div className="hero-heading">All-Time Rankings</div>
          <div className="hero-sub">Every team-season in {leagueConfig.label} history</div>
        </div>
      </div>

      {/* FILTER BAR */}
      <div style={{ borderBottom: "1px solid var(--border)", background: "var(--surface)", padding: "0 2rem" }}>
        <div className="at-filter-bar">
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={filterLabelStyle}>Playoff Depth</span>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {depthFilters.map((f) => (
                <button
                  key={f.id}
                  style={pillStyle(depth === f.id)}
                  onClick={() => {
                    setDepth(f.id);
                    setPage(1);
                  }}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
          <div className="at-filter-divider" />
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={filterLabelStyle}>Era</span>
            <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
              {DECADES.map((d) => (
                <button
                  key={d}
                  style={pillStyle(decade === d)}
                  onClick={() => {
                    setDecade(d);
                    setPage(1);
                  }}
                >
                  {d}
                </button>
              ))}
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={filterLabelStyle}>Team</span>
            <input
              type="text"
              placeholder="Search team…"
              value={teamSearch}
              onChange={(e) => {
                setTeamSearch(e.target.value);
                setPage(1);
              }}
              className="at-search-input"
            />
          </div>
          <div
            style={{
              marginLeft: "auto",
              fontSize: 11,
              color: "var(--text3)",
              fontFamily: "var(--font-mono)",
              alignSelf: "center",
              flexShrink: 0,
            }}
          >
            {loading ? "Loading…" : `${filtered.length.toLocaleString()} results`}
          </div>
        </div>
      </div>

      <div className="season-content" style={{ maxWidth: 1280, paddingBottom: "2rem" }}>
        {loading ? (
          <div style={{ padding: "80px 0", textAlign: "center", color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 13 }}>
            Loading historical data…
          </div>
        ) : fetchError ? (
          <div style={{ padding: "80px 0", textAlign: "center", color: "#b91c1c", fontFamily: "var(--font-mono)", fontSize: 13 }}>
            Couldn&apos;t load data: {fetchError.message}
          </div>
        ) : filtered.length === 0 ? (
          <div style={{ padding: "80px 0", textAlign: "center" }}>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--text3)", marginBottom: 16 }}>
              No results match your filters
            </div>
            <button
              style={{ ...pillStyle(false), background: "var(--acc)", color: "#fff", border: "none" }}
              onClick={() => {
                setDepth("all");
                setDecade("All Eras");
                setTeamSearch("");
              }}
            >
              Clear filters
            </button>
          </div>
        ) : (
          <>
            <div className="desktop-only" style={{ overflowX: "auto", borderRadius: 10, border: "1px solid var(--border)", background: "var(--surface)", marginBottom: 20 }}>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <th style={{ ...thStyle("center"), width: 52 }}>Rank</th>
                    <Th col="team_id" label="Team" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} align="left" />
                    {showPreseason && (
                      <Th col="preseasonElo" label="Pre-Season" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                    )}
                    <Th col="rsW" label="RS Record" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                    <Th col="rsRating" label="RS Rating" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                    <th style={{ ...thStyle("left"), width: 170 }}>Playoff Result</th>
                    <Th col="finalRating" label="Final Rating" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                    <Th col="ratingDelta" label="Δ Playoff" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((row) => {
                    const overallRank = overallRankMap[`${row.team_id}-${row.season}`];
                    const isChamp = row.po?.champion;
                    const fillColor = getFillColor(row.identity);
                    const po = playoffBadge(row);

                    return (
                      <tr
                        key={`${row.team_id}-${row.season}`}
                        style={{
                          borderTop: "1px solid var(--border)",
                          borderLeft: `4px solid ${fillColor}`,
                          background: `linear-gradient(to right, ${fillColor} 0%, ${fillColor} 180px, ${fillColor}55 260px, transparent 340px)`,
                        }}
                      >
                        <td style={{ textAlign: "center", padding: "9px 12px", fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, color: "#fff", width: 36 }}>
                          {overallRank}
                        </td>
                        <td style={{ padding: "9px 8px" }}>
                          <Link
                            href={`/${league}/team/${row.team_id}?variant=${variant}`}
                            style={{ display: "flex", alignItems: "center", gap: 10, textDecoration: "none" }}
                          >
                            <div style={{ width: 34, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                              <HistoricalTeamMark
                                logoPath={row.logoPath}
                                currentLogoTeamId={row.team_id}
                                league={league}
                                abbr={row.identity.code}
                                color={fillColor}
                                size={28}
                              />
                            </div>
                            <div>
                              <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600, color: getTextColor(row.identity), opacity: 0.75, letterSpacing: 0.3, marginBottom: 2 }}>
                                {leagueConfig.seasonLabel(row.season)}
                              </div>
                              <div style={{ fontSize: 13, fontWeight: 700, color: getTextColor(row.identity), lineHeight: 1.2 }}>
                                {row.identity.name}
                              </div>
                            </div>
                          </Link>
                        </td>
                        {showPreseason && (
                          <td style={{ textAlign: "right", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text3)" }}>
                            {fmt1(row.preseasonElo)}
                          </td>
                        )}
                        <td style={{ textAlign: "right", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)" }}>
                          {fmtRec(row.rsW, row.rsL)}
                        </td>
                        <td style={{ textAlign: "right", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 600, color: "var(--text)" }}>
                          {fmt1(row.rsRating)}
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
                          <div style={{ fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 700, color: isChamp ? "var(--ut)" : overallRank === 1 ? "var(--acc)" : "var(--text)" }}>
                            {fmt1(row.finalRating)}
                          </div>
                        </td>
                        <td style={{ textAlign: "right", padding: "0 14px" }}>
                          {row.ratingDelta ? (
                            <span
                              style={{
                                fontFamily: "var(--font-mono)",
                                fontSize: 12,
                                fontWeight: 700,
                                padding: "2px 8px",
                                borderRadius: 4,
                                display: "inline-block",
                                color: row.ratingDelta > 0 ? "#1a7a34" : "#b91c1c",
                                background: row.ratingDelta > 0 ? "rgba(26,122,52,0.12)" : "rgba(185,28,28,0.10)",
                              }}
                            >
                              {row.ratingDelta > 0 ? "+" : ""}
                              {row.ratingDelta.toFixed(1)}
                            </span>
                          ) : (
                            <span style={{ color: "var(--border2)", fontSize: 12 }}>—</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile replacement for the table above. Unlike Season/Dashboard,
                every row here is a different season for the same team, so the
                season label is essential context (not optional) — it's kept
                as its own line above the team name. Playoff Result is kept
                too since playoff depth is central to how this page is
                filtered/browsed; RS Rating, Pre-Season, and Δ Playoff are
                dropped as the least glanceable on a phone. */}
            <div className="ratings-cards mobile-only" style={{ marginBottom: 20 }}>
              {pageRows.map((row) => {
                const overallRank = overallRankMap[`${row.team_id}-${row.season}`];
                const fillColor = getFillColor(row.identity);
                const po = playoffBadge(row);
                return (
                  <Link
                    key={`${row.team_id}-${row.season}`}
                    href={`/${league}/team/${row.team_id}?variant=${variant}`}
                    className="rating-card"
                    style={{ borderLeft: `4px solid ${fillColor}`, textDecoration: "none" }}
                  >
                    <div className="rating-card-rank">{overallRank}</div>
                    <HistoricalTeamMark
                      logoPath={row.logoPath}
                      currentLogoTeamId={row.team_id}
                      league={league}
                      abbr={row.identity.code}
                      color={fillColor}
                      size={26}
                    />
                    <div className="rating-card-body">
                      <div className="rating-card-sub">{leagueConfig.seasonLabel(row.season)}</div>
                      <div className="rating-card-name">{row.identity.name}</div>
                      {po && (
                        <div className="rating-card-sub">
                          {po.champion ? "Champion" : `${po.label} (${po.w}–${po.l})`}
                        </div>
                      )}
                    </div>
                    <div className="rating-card-stats">
                      <div className="rating-card-rating">{fmt1(row.finalRating)}</div>
                      <div className="rating-card-record">{fmtRec(row.rsW, row.rsL)}</div>
                    </div>
                  </Link>
                );
              })}
            </div>

            {totalPages > 1 && (
              <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "center", gap: 12, marginTop: 8 }}>
                <button style={pageBtnStyle(page === 1)} disabled={page === 1} onClick={() => { setPage(1); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                  «« First
                </button>
                <button style={pageBtnStyle(page === 1)} disabled={page === 1} onClick={() => { setPage((p) => p - 1); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                  ← Prev
                </button>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text3)" }}>
                  Page {page} of {totalPages} · {((page - 1) * PER_PAGE + 1).toLocaleString()}–{Math.min(page * PER_PAGE, filtered.length).toLocaleString()} of {filtered.length.toLocaleString()}
                </span>
                <button style={pageBtnStyle(page === totalPages)} disabled={page === totalPages} onClick={() => { setPage((p) => p + 1); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                  Next →
                </button>
                <button style={pageBtnStyle(page === totalPages)} disabled={page === totalPages} onClick={() => { setPage(totalPages); window.scrollTo({ top: 0, behavior: "smooth" }); }}>
                  Last »»
                </button>
              </div>
            )}
          </>
        )}
      </div>

      <Footer />
    </div>
  );
}

function Th({ col, label, sortCol, sortDir, onSort, align = "right" }) {
  const active = sortCol === col;
  return (
    <th
      onClick={() => onSort(col)}
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: 9,
        fontWeight: 500,
        color: active ? "var(--acc)" : "var(--text3)",
        textTransform: "uppercase",
        letterSpacing: 1.2,
        padding: "7px 12px",
        textAlign: align,
        cursor: "pointer",
        userSelect: "none",
        whiteSpace: "nowrap",
        background: "var(--surface)",
        borderBottom: "2px solid var(--border)",
      }}
    >
      {label}
      <span style={{ marginLeft: 3, color: active ? "var(--acc)" : "var(--border2)" }}>
        {active ? (sortDir === "asc" ? "↑" : "↓") : "↕"}
      </span>
    </th>
  );
}

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

const filterLabelStyle = {
  fontFamily: "var(--font-mono)",
  fontSize: 10,
  fontWeight: 500,
  color: "var(--text3)",
  textTransform: "uppercase",
  letterSpacing: 1,
  flexShrink: 0,
};

function pillStyle(active) {
  return {
    fontFamily: "var(--font-mono)",
    fontSize: 11,
    padding: "4px 12px",
    borderRadius: 20,
    border: `1px solid ${active ? "var(--acc)" : "var(--border2)"}`,
    background: active ? "var(--acc-dim)" : "none",
    color: active ? "var(--acc)" : "var(--text2)",
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
