"use client";

/**
 * GamesPanel — date-navigable box scores, ported from the old Dashboard's
 * "Games" sidebar. Pairs the two per-team rows for each game (home + away
 * perspective) into a single game object, same logic as the old site's
 * pairGameRows/getGamesForDate/getLatestGameDate.
 *
 * Pairing/fetch logic lives in lib/gamesData.js - shared with the
 * homepage's "Today's Games" strip so both stay in sync automatically.
 */

import { useState, useEffect } from "react";
import TeamMark from "./TeamMark";
import {
  formatDate,
  roundLabel,
  getGamesForDate,
  getScheduledGamesForDate,
  getLatestGameDate,
} from "@/lib/gamesData";

function shiftDate(dateStr, delta) {
  const [y, m, d] = dateStr.split("-").map(Number);
  const dt = new Date(y, m - 1, d);
  dt.setDate(dt.getDate() + delta);
  return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}-${String(dt.getDate()).padStart(2, "0")}`;
}

export default function GamesPanel({ league, season, variant, leagueConfig }) {
  const [latestDate, setLatestDate] = useState(null);
  const [selectedDate, setSelectedDate] = useState(null);
  const [games, setGames] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    getLatestGameDate(league, season, variant).then((date) => {
      if (cancelled) return;
      setLatestDate(date);
      setSelectedDate(date);
    });
    return () => {
      cancelled = true;
    };
  }, [league, season, variant]);

  useEffect(() => {
    if (!selectedDate) return;
    let cancelled = false;
    setLoading(true);
    getGamesForDate(league, selectedDate, season, variant).then((rows) => {
      if (cancelled) return;
      if (rows.length > 0) {
        setGames(rows);
        setLoading(false);
        return;
      }
      // No played games this date yet - see if any are on the schedule.
      getScheduledGamesForDate(league, selectedDate, season, variant).then((upcoming) => {
        if (cancelled) return;
        setGames(upcoming);
        setLoading(false);
      });
    });
    return () => {
      cancelled = true;
    };
  }, [league, selectedDate, season, variant]);

  return (
    <div className="right-col">
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10, gap: 8 }}>
        <div className="section-label" style={{ marginBottom: 0 }}>Games</div>
        {latestDate && selectedDate !== latestDate && (
          <button
            onClick={() => setSelectedDate(latestDate)}
            style={{
              fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--acc)",
              background: "none", border: "1px solid rgba(102,51,153,0.25)",
              borderRadius: 5, padding: "3px 8px", cursor: "pointer",
            }}
          >
            Jump to latest
          </button>
        )}
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 14 }}>
        <button
          onClick={() => selectedDate && setSelectedDate(shiftDate(selectedDate, -1))}
          style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--text2)", background: "#fff", border: "1px solid var(--border2)", borderRadius: 6, padding: "4px 9px", cursor: "pointer" }}
        >
          ‹
        </button>
        <input
          type="date"
          value={selectedDate || ""}
          onChange={(e) => setSelectedDate(e.target.value)}
          style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text)", background: "#fff", border: "1px solid var(--border2)", borderRadius: 6, padding: "4px 8px", flex: 1 }}
        />
        <button
          onClick={() => selectedDate && setSelectedDate(shiftDate(selectedDate, 1))}
          style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--text2)", background: "#fff", border: "1px solid var(--border2)", borderRadius: 6, padding: "4px 9px", cursor: "pointer" }}
        >
          ›
        </button>
      </div>

      {loading ? (
        <div style={{ color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 13, padding: "1.5rem 0", textAlign: "center" }}>
          Loading…
        </div>
      ) : games.length === 0 ? (
        <div style={{ color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 12, padding: "1.5rem 0", textAlign: "center", border: "1px dashed var(--border2)", borderRadius: 10 }}>
          No games on {selectedDate ? formatDate(selectedDate) : "this date"}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {games.map((g, i) => {
            if (g.upcoming) {
              const homeTeam = leagueConfig.teams[g.home];
              const awayTeam = leagueConfig.teams[g.away];
              const homeFav = g.winProb != null && g.winProb >= 0.5;
              const favPct = g.winProb != null ? Math.round(homeFav ? g.winProb * 100 : (1 - g.winProb) * 100) : null;
              return (
                <div key={i} style={{ background: "var(--surface)", border: "1px dashed var(--border2)", borderRadius: 10, padding: "10px 12px" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)" }}>
                    <span>{formatDate(g.date)}</span>
                    <span style={{ fontWeight: 700, letterSpacing: 0.5 }}>UPCOMING</span>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", padding: "12px 0 8px" }}>
                    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)" }}>{g.away}</span>
                    </div>

                    {awayTeam && <TeamMark team={awayTeam} teamId={g.away} league={league} size={34} />}

                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3, padding: "0 8px", flexShrink: 0, minWidth: 44 }}>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)" }}>@</span>
                    </div>

                    {homeTeam && <TeamMark team={homeTeam} teamId={g.home} league={league} size={34} />}

                    <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)" }}>{g.home}</span>
                    </div>
                  </div>

                  {g.showPick && favPct != null && (
                    <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 4, borderTop: "1px solid var(--border)", marginTop: 2, paddingTop: 8, fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text2)" }}>
                      <span>Elo&apos;s pick:</span>
                      {!homeFav && <span style={{ color: "var(--acc)", fontSize: 10 }}>◀</span>}
                      <strong>{homeFav ? g.home : g.away} {favPct}%</strong>
                      {homeFav && <span style={{ color: "var(--acc)", fontSize: 10 }}>▶</span>}
                    </div>
                  )}
                </div>
              );
            }

            const homeWon = g.homeScore > g.awayScore;
            const isPlayoff = g.type === "P";
            const homeTeam = leagueConfig.teams[g.home];
            const awayTeam = leagueConfig.teams[g.away];
            const homeFav = g.winProb != null && g.winProb >= 0.5;
            const favPct = g.winProb != null ? Math.round(homeFav ? g.winProb * 100 : (1 - g.winProb) * 100) : null;
            return (
              <div key={i} style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 10, padding: "10px 12px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)" }}>
                  <span>{formatDate(g.date)}</span>
                  <span style={{ color: isPlayoff ? "var(--ut)" : "var(--text3)", fontWeight: isPlayoff ? 700 : 400 }}>
                    {roundLabel(g.round, g.type, leagueConfig)}
                  </span>
                </div>

                <div style={{ display: "flex", alignItems: "center", padding: "12px 0 8px" }}>
                  <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)" }}>{g.away}</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 30, fontWeight: 900, lineHeight: 1, color: homeWon ? "var(--text)" : "#D4AF37" }}>
                      {g.awayScore}
                    </span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)" }}>{g.awayRating?.toFixed(1)}</span>
                  </div>

                  {awayTeam && <TeamMark team={awayTeam} teamId={g.away} league={league} size={34} />}

                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 3, padding: "0 8px", flexShrink: 0, minWidth: 44 }}>
                    {g.ot && (
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 700, padding: "2px 5px", borderRadius: 3, background: "rgba(191,87,0,0.15)", color: "var(--ut)", border: "1px solid rgba(191,87,0,0.25)" }}>
                        OT
                      </span>
                    )}
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)" }}>@</span>
                  </div>

                  {homeTeam && <TeamMark team={homeTeam} teamId={g.home} league={league} size={34} />}

                  <div style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 3 }}>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)" }}>{g.home}</span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 30, fontWeight: 900, lineHeight: 1, color: homeWon ? "#D4AF37" : "var(--text)" }}>
                      {g.homeScore}
                    </span>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)" }}>{g.homeRating?.toFixed(1)}</span>
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderTop: "1px solid var(--border)", marginTop: 2, paddingTop: 8, fontFamily: "var(--font-mono)", fontSize: 11 }}>
                  <span>
                    {g.away}{" "}
                    <strong style={{ color: g.awayChange > 0 ? "#1a7a34" : "#b91c1c" }}>
                      {g.awayChange > 0 ? "+" : ""}{g.awayChange?.toFixed(1)}
                    </strong>
                  </span>
                  {favPct != null && (
                    <span style={{ display: "flex", alignItems: "center", gap: 3, color: "var(--text2)" }}>
                      {!homeFav && <span style={{ color: "var(--acc)", fontSize: 10 }}>◀</span>}
                      <strong>{favPct}%</strong>
                      {homeFav && <span style={{ color: "var(--acc)", fontSize: 10 }}>▶</span>}
                    </span>
                  )}
                  <span>
                    {g.home}{" "}
                    <strong style={{ color: g.homeChange > 0 ? "#1a7a34" : "#b91c1c" }}>
                      {g.homeChange > 0 ? "+" : ""}{g.homeChange?.toFixed(1)}
                    </strong>
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
