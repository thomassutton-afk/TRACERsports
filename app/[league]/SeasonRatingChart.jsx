"use client";

/**
 * SeasonRatingChart.jsx — Rating Chart tab for the Season Page.
 *
 * Ported from reference/old-site/SeasonPage.jsx's RatingHeatmap + H2HChart,
 * combined into one component with the same Heatmap/Head-to-Head mode
 * toggle the old site had. Restyled onto the app's CSS variable tokens
 * (var(--acc), var(--text3), var(--font-mono), etc.) instead of the old
 * site's hardcoded C palette, and made league-agnostic:
 *   - Team list comes from leagueConfig.teams, not a hardcoded NBA dict.
 *   - Conference filter buttons are driven by leagueConfig.conferences,
 *     so this works for any conference layout, not just East/West.
 *   - Era-correct abbr/name/color comes from lib/historicalIdentity.js's
 *     getDisplayIdentity (real team_history data), replacing the old
 *     site's hand-maintained DISPLAY_IDENTITIES map.
 *   - "Playoff Teams" filter reads off the poByTeam tally the Season Page
 *     already computes via tallyPlayoffResults, rather than re-deriving it
 *     from raw round columns.
 *
 * Data: takes the season's raw per-game rows (team_id, date, post_gm_rate)
 * that the Season Page already fetches for standings — no separate query,
 * since fetchSeasonTeamGames already pulls exactly what this chart needs.
 */

import { useState, useMemo } from "react";
import { buildWeeklySnapshots, ratingColor, RATING_COLOR_STOPS } from "@/lib/gamesData";
import { getDisplayIdentity } from "@/lib/historicalIdentity";
import { getFillColor } from "@/lib/teamColors";

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

const selectStyle = {
  fontFamily: "var(--font-mono)",
  fontSize: 12,
  padding: "5px 10px",
  border: "1px solid var(--border2)",
  borderRadius: 8,
  background: "var(--surface)",
  color: "var(--text)",
  cursor: "pointer",
};

export default function SeasonRatingChart({ rawRows, standingsRows, poByTeam, season, leagueConfig, historyByTeam, league }) {
  const [mode, setMode] = useState("heatmap"); // heatmap | h2h
  const [filter, setFilter] = useState("all"); // playoffs | <conference> | all
  const [h2hTeam1, setH2hTeam1] = useState(null);
  const [h2hTeam2, setH2hTeam2] = useState(null);

  const allTeamIds = useMemo(() => Object.keys(leagueConfig.teams).sort(), [leagueConfig]);

  // Group raw rows into per-team point series, sorted ascending by date.
  const byTeam = useMemo(() => {
    const grouped = {};
    for (const row of rawRows) {
      if (row.post_gm_rate == null) continue;
      (grouped[row.team_id] ??= []).push({
        date: new Date(row.date + "T12:00:00").getTime(),
        rating: row.post_gm_rate,
      });
    }
    for (const arr of Object.values(grouped)) arr.sort((a, b) => a.date - b.date);
    return grouped;
  }, [rawRows]);

  const rsRatingByTeam = useMemo(() => {
    const m = {};
    for (const r of standingsRows) m[r.team_id] = r.rsRating ?? 0;
    return m;
  }, [standingsRows]);

  const t1 = h2hTeam1 ?? allTeamIds[0];
  const t2 = h2hTeam2 ?? allTeamIds[1];

  const teamsToShow = useMemo(() => {
    if (mode === "h2h") return [t1, t2].filter(Boolean);
    if (filter === "playoffs") {
      return allTeamIds
        .filter((id) => poByTeam[id]?.highestRound != null)
        .sort((a, b) => (rsRatingByTeam[b] ?? 0) - (rsRatingByTeam[a] ?? 0));
    }
    if (leagueConfig.hasConferences && leagueConfig.conferences.includes(filter)) {
      return allTeamIds
        .filter((id) => leagueConfig.teams[id]?.conf === filter)
        .sort((a, b) => (rsRatingByTeam[b] ?? 0) - (rsRatingByTeam[a] ?? 0));
    }
    // "all"
    return [...allTeamIds].sort((a, b) => (rsRatingByTeam[b] ?? 0) - (rsRatingByTeam[a] ?? 0));
  }, [mode, filter, t1, t2, allTeamIds, poByTeam, rsRatingByTeam, leagueConfig]);

  const seriesData = teamsToShow.filter((id) => byTeam[id]?.length).map((id) => ({ team: id, points: byTeam[id] }));

  return (
    <>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16, flexWrap: "wrap" }}>
        <div style={{ display: "flex", background: "var(--border)", borderRadius: 8, overflow: "hidden", border: "1px solid var(--border2)" }}>
          {[
            ["heatmap", "Heatmap"],
            ["h2h", "Head-to-Head"],
          ].map(([m, l]) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 11,
                padding: "5px 14px",
                cursor: "pointer",
                border: "none",
                background: mode === m ? "var(--acc)" : "transparent",
                color: mode === m ? "#fff" : "var(--text2)",
              }}
            >
              {l}
            </button>
          ))}
        </div>

        {mode === "heatmap" && (
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            <button style={filterBtnStyle(filter === "playoffs")} onClick={() => setFilter("playoffs")}>
              Playoff Teams
            </button>
            {leagueConfig.hasConferences &&
              leagueConfig.conferences.map((c) => (
                <button key={c} style={filterBtnStyle(filter === c)} onClick={() => setFilter(c)}>
                  {c}
                </button>
              ))}
            <button style={filterBtnStyle(filter === "all")} onClick={() => setFilter("all")}>
              All {allTeamIds.length}
            </button>
          </div>
        )}

        {mode === "h2h" && (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <select value={t1} onChange={(e) => setH2hTeam1(e.target.value)} style={selectStyle}>
              {allTeamIds.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
            <span style={{ color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 12 }}>vs</span>
            <select value={t2} onChange={(e) => setH2hTeam2(e.target.value)} style={selectStyle}>
              {allTeamIds.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      <div style={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 12, padding: "20px 24px" }}>
        {mode === "h2h" ? (
          <H2HChart seriesData={seriesData} season={season} leagueConfig={leagueConfig} historyByTeam={historyByTeam} width={860} height={300} />
        ) : (
          <RatingHeatmap seriesData={seriesData} season={season} leagueConfig={leagueConfig} historyByTeam={historyByTeam} />
        )}
      </div>
    </>
  );
}

// ---------------------------------------------------------------------------
// RatingHeatmap — one row per team, weekly snapshots colored by rating.
// ---------------------------------------------------------------------------
function RatingHeatmap({ seriesData, season, leagueConfig, historyByTeam }) {
  const [tooltip, setTooltip] = useState(null);

  if (!seriesData?.length) {
    return <div style={{ padding: "40px 0", textAlign: "center", color: "var(--text3)", fontSize: 13, fontFamily: "var(--font-mono)" }}>No data for this filter.</div>;
  }

  const byTeam = {};
  for (const s of seriesData) byTeam[s.team] = s.points;
  const snapshots = buildWeeklySnapshots(byTeam);

  const allVals = Object.values(snapshots).flat().map((p) => p.rating);
  const globalMin = Math.min(...allVals);
  const globalMax = Math.max(...allVals);

  const firstTeam = seriesData[0].team;
  const weeks = snapshots[firstTeam] || [];
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const monthLabels = weeks.map((w, i) => {
    if (i === 0) return "Open";
    const dt = new Date(w.date);
    const prev = new Date(weeks[i - 1].date);
    return dt.getMonth() !== prev.getMonth() ? MONTHS[dt.getMonth()] : "";
  });

  const CELL_H = 26;
  const LABEL_W = 44;
  const DELTA_W = 44;

  return (
    <div>
      <div style={{ display: "flex", marginBottom: 2, paddingLeft: LABEL_W, paddingRight: DELTA_W + 8 }}>
        {monthLabels.map((lbl, i) => (
          <div
            key={i}
            style={{
              flex: 1,
              textAlign: "center",
              fontFamily: "var(--font-mono)",
              fontSize: 9,
              color: "var(--text3)",
              fontWeight: lbl && lbl !== "Open" ? 600 : 400,
              minWidth: 0,
            }}
          >
            {lbl}
          </div>
        ))}
      </div>

      {seriesData.map(({ team }) => {
        const snaps = snapshots[team] || [];
        const identity = getDisplayIdentity(team, season, historyByTeam, leagueConfig);
        const teamColor = getFillColor(identity);
        const openingRating = snaps[0]?.rating;
        const closingRating = snaps.at(-1)?.rating;
        const seasonChange = closingRating != null && openingRating != null ? Math.round(closingRating - openingRating) : null;

        return (
          <div key={team} style={{ display: "flex", alignItems: "stretch", marginBottom: 1 }}>
            <div
              style={{
                width: LABEL_W,
                flexShrink: 0,
                fontFamily: "var(--font-mono)",
                fontSize: 10,
                fontWeight: 600,
                color: teamColor,
                paddingRight: 6,
                textAlign: "right",
                lineHeight: `${CELL_H}px`,
              }}
            >
              {identity.code}
            </div>
            {snaps.map((snap, i) => {
              const bg = ratingColor(snap.rating, globalMin, globalMax);
              const isHovered = tooltip?.team === team && tooltip?.weekIdx === i;
              return (
                <div
                  key={i}
                  style={{
                    flex: 1,
                    height: CELL_H,
                    minWidth: 0,
                    background: bg,
                    opacity: isHovered ? 1 : 0.85,
                    outline: isHovered ? "2px solid var(--text)" : "none",
                    outlineOffset: -1,
                    cursor: "default",
                  }}
                  onMouseEnter={(e) => {
                    const prev = i > 0 ? snaps[i - 1].rating : null;
                    setTooltip({
                      x: e.clientX,
                      y: e.clientY,
                      team,
                      identity,
                      weekIdx: i,
                      date: new Date(snap.date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
                      rating: snap.rating,
                      change: prev != null ? Math.round(snap.rating - prev) : null,
                    });
                  }}
                  onMouseMove={(e) => setTooltip((t) => (t ? { ...t, x: e.clientX, y: e.clientY } : t))}
                  onMouseLeave={() => setTooltip(null)}
                />
              );
            })}
            <div
              style={{
                width: DELTA_W,
                flexShrink: 0,
                paddingLeft: 8,
                fontFamily: "var(--font-mono)",
                fontSize: 10,
                fontWeight: 600,
                lineHeight: `${CELL_H}px`,
                color: seasonChange == null ? "var(--text3)" : seasonChange > 0 ? "#1a7a34" : seasonChange < 0 ? "#b91c1c" : "var(--text3)",
              }}
            >
              {seasonChange == null ? "" : seasonChange > 0 ? `+${seasonChange}` : seasonChange}
            </div>
          </div>
        );
      })}

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 14, paddingLeft: LABEL_W, borderTop: "1px solid var(--border)", paddingTop: 12 }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text3)" }}>Lower</span>
        <div style={{ display: "flex", height: 8, width: 160, borderRadius: 2, overflow: "hidden" }}>
          {RATING_COLOR_STOPS.slice(0, -1).map(([, c], i) => (
            <div key={i} style={{ flex: 1, background: c }} />
          ))}
        </div>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text3)" }}>Higher</span>
        <span style={{ marginLeft: 16, fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--text3)" }}>
          Opening night + every Sunday · rightmost badge = season Δ
        </span>
      </div>

      {tooltip && (
        <div
          style={{
            position: "fixed",
            left: tooltip.x + 14,
            top: tooltip.y - 44,
            background: "var(--surface)",
            border: "1px solid var(--border2)",
            borderRadius: 8,
            padding: "7px 11px",
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            lineHeight: 1.7,
            pointerEvents: "none",
            zIndex: 999,
            boxShadow: "0 2px 10px rgba(0,0,0,0.15)",
          }}
        >
          <div style={{ fontWeight: 700, color: tooltip.identity.primary }}>{tooltip.identity.code}</div>
          <div style={{ color: "var(--text2)" }}>{tooltip.date}</div>
          <div style={{ color: "var(--text)" }}>
            Rating: <strong>{tooltip.rating?.toFixed(1)}</strong>
          </div>
          {tooltip.change != null && (
            <div style={{ color: tooltip.change > 0 ? "#1a7a34" : tooltip.change < 0 ? "#b91c1c" : "var(--text3)" }}>
              Wk Δ: {tooltip.change > 0 ? "+" : ""}
              {tooltip.change}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// H2HChart — two-team SVG line chart.
// ---------------------------------------------------------------------------
function H2HChart({ seriesData, season, leagueConfig, historyByTeam, width = 820, height = 300 }) {
  const [hovered, setHovered] = useState(null);

  if (!seriesData?.length) {
    return (
      <div style={{ height, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text3)", fontSize: 13, fontFamily: "var(--font-mono)" }}>
        Select two teams above
      </div>
    );
  }

  const byTeam = {};
  for (const s of seriesData) byTeam[s.team] = s.points;
  const snapshots = buildWeeklySnapshots(byTeam);

  const allPoints = Object.values(snapshots).flat();
  if (!allPoints.length) return null;

  const allRatings = allPoints.map((p) => p.rating);
  const allDates = allPoints.map((p) => p.date);
  const minR = Math.min(...allRatings) - 20;
  const maxR = Math.max(...allRatings) + 20;
  const minD = Math.min(...allDates);
  const maxD = Math.max(...allDates);
  const pad = { top: 16, right: 56, bottom: 28, left: 54 };
  const W = width - pad.left - pad.right;
  const H = height - pad.top - pad.bottom;

  const xS = (d) => ((d - minD) / (maxD - minD || 1)) * W;
  const yS = (r) => H - ((r - minR) / (maxR - minR || 1)) * H;

  const rawStep = (maxR - minR) / 5;
  const step = Math.ceil(rawStep / 10) * 10 || 10;
  const yTicks = [];
  for (let v = Math.ceil(minR / step) * step; v <= maxR; v += step) yTicks.push(v);

  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const xTicks = [];
  const seenMo = new Set();
  [...allDates]
    .sort((a, b) => a - b)
    .forEach((d) => {
      const dt = new Date(d);
      const key = `${dt.getFullYear()}-${dt.getMonth()}`;
      if (!seenMo.has(key)) {
        seenMo.add(key);
        xTicks.push({ d, label: MONTHS[dt.getMonth()] });
      }
    });

  return (
    <div>
      <svg width="100%" viewBox={`0 0 ${width} ${height}`} style={{ overflow: "visible" }} onMouseLeave={() => setHovered(null)}>
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={pad.left} y1={pad.top + yS(v)} x2={pad.left + W} y2={pad.top + yS(v)} stroke="var(--border)" strokeWidth={1} />
            <text x={pad.left - 6} y={pad.top + yS(v) + 4} textAnchor="end" fontSize={9} fill="var(--text3)" fontFamily="var(--font-mono)">
              {v.toFixed(0)}
            </text>
          </g>
        ))}
        {xTicks.map(({ d, label }) => (
          <text key={d} x={pad.left + xS(d)} y={pad.top + H + 18} textAnchor="middle" fontSize={9} fill="var(--text3)" fontFamily="var(--font-mono)">
            {label}
          </text>
        ))}
        {seriesData.map(({ team }) => {
          const snaps = snapshots[team] || [];
          const identity = getDisplayIdentity(team, season, historyByTeam, leagueConfig);
          const color = getFillColor(identity);
          const isHov = hovered === team;
          const dimmed = hovered && !isHov;
          const pts = snaps.map((p) => `${pad.left + xS(p.date)},${pad.top + yS(p.rating)}`).join(" ");
          const last = snaps.at(-1);
          return (
            <g key={team} onMouseEnter={() => setHovered(team)} style={{ cursor: "pointer" }}>
              <polyline
                points={pts}
                fill="none"
                stroke={color}
                strokeWidth={isHov ? 3 : 2}
                strokeLinejoin="round"
                strokeLinecap="round"
                opacity={dimmed ? 0.15 : 1}
                style={{ transition: "opacity 0.15s, stroke-width 0.15s" }}
              />
              {last && (
                <text
                  x={pad.left + xS(last.date) + 6}
                  y={pad.top + yS(last.rating) + 4}
                  fontSize={10}
                  fill={color}
                  opacity={dimmed ? 0.15 : 1}
                  fontFamily="var(--font-mono)"
                  fontWeight="700"
                  style={{ transition: "opacity 0.15s" }}
                >
                  {identity.code}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      <div style={{ display: "flex", gap: 20, marginTop: 14, borderTop: "1px solid var(--border)", paddingTop: 12, flexWrap: "wrap" }}>
        {seriesData.map(({ team }) => {
          const identity = getDisplayIdentity(team, season, historyByTeam, leagueConfig);
          const color = getFillColor(identity);
          const snaps = snapshots[team] || [];
          const change = snaps.length > 1 ? Math.round((snaps.at(-1)?.rating ?? 0) - (snaps[0]?.rating ?? 0)) : null;
          const isHov = hovered === team;
          return (
            <div
              key={team}
              style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", opacity: hovered && !isHov ? 0.3 : 1, transition: "opacity 0.15s" }}
              onMouseEnter={() => setHovered(team)}
              onMouseLeave={() => setHovered(null)}
            >
              <div style={{ width: 24, height: isHov ? 4 : 3, background: color, borderRadius: 2 }} />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: isHov ? 700 : 500, color: isHov ? color : "var(--text2)" }}>
                {identity.code}
                {identity.name ? ` · ${identity.name}` : ""}
              </span>
              {change != null && (
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: change > 0 ? "#1a7a34" : change < 0 ? "#b91c1c" : "var(--text3)" }}>
                  ({change > 0 ? "+" : ""}
                  {change})
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
