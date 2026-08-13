"use client";

/**
 * SeasonGameLog.jsx — Game Log tab for the Season Page.
 *
 * Ported from reference/old-site/SeasonPage.jsx's game-log table. Unlike
 * the Team page's Game Log (one team, so only "Opponent" needs a column),
 * this is league-wide for the season — both Away and Home teams shown per
 * row, same as the old site. Restyled onto the app's CSS variable tokens
 * and era-correct identity (lib/historicalIdentity.js) instead of the old
 * site's hardcoded palette/identity map. Pairing/fetching itself lives in
 * lib/gamesData.js's fetchSeasonGameLog, reusing the same pairGameRows
 * logic every other game-log view in the app already uses.
 */

import { useState, useEffect, useMemo } from "react";
import { fetchSeasonGameLog, formatDate, roundLabel } from "@/lib/gamesData";
import { getDisplayIdentity, resolveHistoricalLogoPath } from "@/lib/historicalIdentity";
import HistoricalTeamMark from "./HistoricalTeamMark";

const GAMES_PER_PAGE = 25;

const filterBtnStyle = (active) => ({
  fontFamily: "var(--font-mono)",
  fontSize: 11,
  padding: "4px 12px",
  borderRadius: 6,
  border: `1px solid ${active ? "var(--acc)" : "var(--border2)"}`,
  background: active ? "var(--acc-dim)" : "none",
  color: active ? "var(--acc)" : "var(--text3)",
  cursor: "pointer",
});

const thStyle = (align) => ({
  fontFamily: "var(--font-mono)",
  fontSize: 9,
  fontWeight: 500,
  color: "var(--text3)",
  textTransform: "uppercase",
  letterSpacing: 1.2,
  padding: "10px 12px",
  textAlign: align,
  whiteSpace: "nowrap",
  background: "var(--surface)",
  borderBottom: "2px solid var(--border)",
});

function fmt1(v) {
  return v != null ? Number(v).toFixed(1) : "—";
}
function chgColor(n) {
  return n > 0 ? "#1a7a34" : n < 0 ? "#b91c1c" : "var(--text3)";
}
function chgStr(n) {
  return n == null ? "—" : (n > 0 ? "+" : "") + Number(n).toFixed(1);
}

export default function SeasonGameLog({ league, season, variant, leagueConfig, historyByTeam, logoIndex, roundDelta = 0 }) {
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState("all"); // all | R | P
  const [page, setPage] = useState(1);

  useEffect(() => {
    if (!leagueConfig || season == null) return;
    setLoading(true);
    setPage(1);
    fetchSeasonGameLog(league, season, variant, { type: typeFilter === "all" ? undefined : typeFilter }).then(({ games }) => {
      setGames(games);
      setLoading(false);
    });
  }, [league, leagueConfig, season, variant, typeFilter]);

  const totalPages = Math.max(1, Math.ceil(games.length / GAMES_PER_PAGE));
  const pagedGames = useMemo(() => games.slice((page - 1) * GAMES_PER_PAGE, page * GAMES_PER_PAGE), [games, page]);

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16, flexWrap: "wrap", gap: 10 }}>
        <span style={{ fontSize: 12, color: "var(--text3)", fontFamily: "var(--font-mono)" }}>{loading ? "Loading…" : `${games.length.toLocaleString()} games`}</span>
        <div style={{ display: "flex", gap: 8 }}>
          {[
            { id: "all", label: "All" },
            { id: "R", label: "Regular Season" },
            { id: "P", label: "Playoffs" },
          ].map(({ id, label }) => (
            <button key={id} style={filterBtnStyle(typeFilter === id)} onClick={() => setTypeFilter(id)}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div style={{ padding: "40px 0", textAlign: "center", color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 13 }}>Loading…</div>
      ) : games.length === 0 ? (
        <div style={{ padding: "40px 0", textAlign: "center", color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 13 }}>No games for this filter.</div>
      ) : (
        <>
          <div style={{ overflowX: "auto", borderRadius: 12, border: "1px solid var(--border)", background: "var(--surface)" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={thStyle("left")}>Date</th>
                  <th style={thStyle("left")}>Type</th>
                  <th style={thStyle("left")}>Away</th>
                  <th style={{ ...thStyle("center") }}>Score</th>
                  <th style={thStyle("left")}>Home</th>
                  <th style={thStyle("right")}>Win Prob</th>
                  <th style={thStyle("right")}>Home Δ</th>
                  <th style={thStyle("right")}>OT</th>
                </tr>
              </thead>
              <tbody>
                {pagedGames.map((g) => {
                  const homeWon = g.homeScore > g.awayScore;
                  const isPlayoff = g.type === "P";
                  const label = roundLabel(g.round, g.type, leagueConfig, roundDelta);
                  const homeId = getDisplayIdentity(g.home, season, historyByTeam, leagueConfig);
                  const awayId = getDisplayIdentity(g.away, season, historyByTeam, leagueConfig);
                  const homeLogo = resolveHistoricalLogoPath(g.home, season, historyByTeam, logoIndex, league);
                  const awayLogo = resolveHistoricalLogoPath(g.away, season, historyByTeam, logoIndex, league);

                  return (
                    <tr key={`${g.date}-${g.home}-${g.away}`} style={{ borderTop: "1px solid var(--border)" }}>
                      <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text3)" }}>{formatDate(g.date)}</td>
                      <td style={{ padding: "10px 12px" }}>
                        <span
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: 10,
                            padding: "2px 7px",
                            borderRadius: 4,
                            fontWeight: 500,
                            background: isPlayoff ? "var(--acc-dim)" : "rgba(255,255,255,0.06)",
                            color: isPlayoff ? "var(--acc)" : "var(--text2)",
                          }}
                        >
                          {isPlayoff ? label : "RS"}
                        </span>
                      </td>
                      <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: homeWon ? 400 : 700, color: homeWon ? "var(--text3)" : "var(--text)" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <HistoricalTeamMark logoPath={awayLogo} currentLogoTeamId={g.away} league={league} abbr={awayId.code} color={awayId.primary} size={18} />
                          {awayId.code}
                        </div>
                      </td>
                      <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", textAlign: "center", fontWeight: 600 }}>
                        <span style={{ color: homeWon ? "var(--text3)" : "var(--text)" }}>{g.awayScore}</span>
                        <span style={{ color: "var(--border2)", margin: "0 4px" }}>–</span>
                        <span style={{ color: homeWon ? "var(--text)" : "var(--text3)" }}>{g.homeScore}</span>
                      </td>
                      <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: homeWon ? 700 : 400, color: homeWon ? "var(--text)" : "var(--text3)" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                          <HistoricalTeamMark logoPath={homeLogo} currentLogoTeamId={g.home} league={league} abbr={homeId.code} color={homeId.primary} size={18} />
                          {homeId.code}
                        </div>
                      </td>
                      <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", textAlign: "right", fontSize: 12, color: "var(--text3)" }}>
                        {g.winProb != null ? `${Math.round(g.winProb * 100)}% / ${Math.round((1 - g.winProb) * 100)}%` : "—"}
                      </td>
                      <td style={{ padding: "10px 12px", textAlign: "right" }}>
                        <span
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: 12,
                            fontWeight: 700,
                            padding: "2px 8px",
                            borderRadius: 4,
                            display: "inline-block",
                            color: chgColor(g.homeChange),
                            background: g.homeChange > 0 ? "rgba(26,122,52,0.12)" : g.homeChange < 0 ? "rgba(185,28,28,0.10)" : "transparent",
                          }}
                        >
                          {chgStr(g.homeChange)}
                        </span>
                      </td>
                      <td style={{ padding: "10px 12px", fontFamily: "var(--font-mono)", textAlign: "right", fontSize: 11, color: "var(--text3)" }}>{g.ot ? "OT" : ""}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 12, marginTop: 20 }}>
              <button style={pageBtnStyle(page === 1)} disabled={page === 1} onClick={() => setPage(1)}>
                «« First
              </button>
              <button style={pageBtnStyle(page === 1)} disabled={page === 1} onClick={() => setPage((p) => p - 1)}>
                ← Prev
              </button>
              <span style={{ fontSize: 12, color: "var(--text3)", fontFamily: "var(--font-mono)" }}>
                Page {page} of {totalPages} · {games.length} games
              </span>
              <button style={pageBtnStyle(page === totalPages)} disabled={page === totalPages} onClick={() => setPage((p) => p + 1)}>
                Next →
              </button>
              <button style={pageBtnStyle(page === totalPages)} disabled={page === totalPages} onClick={() => setPage(totalPages)}>
                Last »»
              </button>
            </div>
          )}
        </>
      )}
    </>
  );
}

function pageBtnStyle(disabled) {
  return {
    fontFamily: "var(--font-mono)",
    fontSize: 12,
    padding: "6px 14px",
    border: "1px solid var(--border2)",
    borderRadius: 6,
    background: "var(--surface)",
    color: "var(--acc)",
    cursor: disabled ? "default" : "pointer",
    opacity: disabled ? 0.4 : 1,
  };
}
