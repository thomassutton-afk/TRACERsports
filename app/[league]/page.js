"use client";

/**
 * app/[league]/page.js — Real Dashboard, league-agnostic, LIVE Supabase data.
 *
 * Matches the old single-league Dashboard.jsx layout: two-column grid
 * (ratings table left, Games panel right), Echo/Pulse variant read from the
 * ?variant= search param (toggle lives in Nav.jsx, shared across the site).
 *
 * Fetches every game row for the current season/variant, then reduces
 * client-side to: latest row per team (for current rating + last change)
 * and summed w/l across all rows (season record) — w/l in the games table
 * are per-game results (1/0), not running totals, so they must be summed,
 * not read off the latest row.
 *
 * Playoff Bracket tab: live for conference-bracket leagues (NBA) via
 * BracketTab.jsx. Overall-bracket leagues (WNBA: top-8, no conferences)
 * still show a placeholder — that format needs its own component, not a
 * variant of BracketTab, since the whole layout assumes two conferences
 * funneling into a Finals column.
 */

import { useState, useEffect } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { getLeagueConfig } from "@/lib/sports/registry";
import { getFillColor } from "@/lib/teamColors";
import { supabase } from "@/lib/supabase";
import { getCurrentSeason } from "@/lib/gamesData";
import TeamMark from "./TeamMark";
import StandingsTab from "./StandingsTab";
import GamesPanel from "./GamesPanel";
import BracketTab from "./BracketTab";
import OverallBracketTab from "./OverallBracketTab";
import Footer from "@/components/Footer";

const TABS = [
  { id: "rankings", label: "Power Rankings" },
  { id: "standings", label: "Standings" },
  { id: "bracket", label: "Playoff Bracket" },
];

const VARIANT_LABELS = {
  echo: "Echo ratings — carry-forward variant",
  pulse: "Pulse ratings — season-reset variant",
};

async function fetchStandings(league, season, variant) {
  const PAGE_SIZE = 1000; // matches Supabase/PostgREST's typical default Max Rows;
                           // safe even if the project's cap is raised later, since
                           // we stop as soon as a page comes back short.
  let allRows = [];
  let from = 0;

  while (true) {
    const { data, error } = await supabase
      .from("games")
      // opponent_id/home_away/points_for/points_against/type are pulled
      // alongside the original columns so StandingsTab can run the real
      // NBA-style tiebreaker criteria (head-to-head, division/conference
      // record, point differential) client-side, matching the same logic
      // DBs/tiebreakers.py already runs at export time.
      .select("team_id, date, post_gm_rate, rating_change, w, l, opponent_id, home_away, points_for, points_against, type")
      .eq("league", league)
      .eq("season", season)
      .eq("variant", variant)
      .order("date", { ascending: true })
      .range(from, from + PAGE_SIZE - 1);

    if (error) return { standings: [], games: [], error };

    allRows = allRows.concat(data ?? []);

    // A short page means we've hit the end of the result set.
    if (!data || data.length < PAGE_SIZE) break;

    from += PAGE_SIZE;
  }

  const byTeam = {};
  for (const row of allRows) {
    const t = (byTeam[row.team_id] ??= { team_id: row.team_id, w: 0, l: 0, rating: null, change: null });
    t.w += row.w ?? 0;
    t.l += row.l ?? 0;
    // rows are date-ascending, so the last one we see is the latest
    t.rating = row.post_gm_rate;
    t.change = row.rating_change;
  }

  const standings = Object.values(byTeam).sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0));
  // Regular-season-only rows, trimmed to just what the tiebreaker math needs.
  const games = allRows
    .filter((row) => row.type === "R")
    .map((row) => ({
      team_id: row.team_id,
      opponent_id: row.opponent_id,
      points_for: row.points_for,
      points_against: row.points_against,
    }));
  return { standings, games, error: null };
}

async function fetchPlayoffGames(league, season, variant) {
  const PAGE_SIZE = 1000;
  let allRows = [];
  let from = 0;

  while (true) {
    const { data, error } = await supabase
      .from("games")
      .select("team_id, round, result, post_gm_rate, opponent_id, home_away, points_for, points_against, date, game_id")
      .eq("league", league)
      .eq("season", season)
      .eq("variant", variant)
      .eq("type", "P")
      .neq("round", "0.1") // excludes in-season tournament games (round=0.1); games.round is TEXT in Postgres, so compare as a string, not a number
      .order("date", { ascending: true })
      .range(from, from + PAGE_SIZE - 1);

    if (error) return { poGames: [], error };

    allRows = allRows.concat(data ?? []);
    if (!data || data.length < PAGE_SIZE) break;
    from += PAGE_SIZE;
  }

  return { poGames: allRows, error: null };
}

async function fetchProjection(league, season, variant) {
  const { data, error } = await supabase
    .from("season_projections")
    .select("team_id, avg_wins, p10_wins, p90_wins, prob_finish_first, remaining_games")
    .eq("league", league)
    .eq("season", season)
    .eq("variant", variant);

  if (error) return { projByTeam: {}, error };

  const projByTeam = {};
  for (const row of data ?? []) {
    projByTeam[row.team_id] = row;
  }
  return { projByTeam, error: null };
}

// Header cell styling ported from the old site's TH helper (reference/old-site/Dashboard.jsx
// ~line 330) — mono, small, uppercase, muted. The "ratings-table"/".r" classNames below never
// had matching CSS defined, so headers were rendering as plain bold browser defaults; this
// replaces that with real styling instead of adding the missing CSS rules.
function Th({ children, align = "center", style }) {
  return (
    <th
      style={{
        fontFamily: "var(--font-mono)",
        fontSize: 9,
        fontWeight: 500,
        color: "var(--text3)",
        textTransform: "uppercase",
        letterSpacing: 1.2,
        padding: "7px 8px",
        textAlign: align,
        whiteSpace: "nowrap",
        background: "var(--surface)",
        borderBottom: "2px solid var(--border)",
        ...style,
      }}
    >
      {children}
    </th>
  );
}

export default function LeaguePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const league = params.league;
  const variant = searchParams.get("variant") || "echo";
  const [activeTab, setActiveTab] = useState("rankings");
  const [season, setSeason] = useState(null);
  const [standings, setStandings] = useState([]);
  const [standingsGames, setStandingsGames] = useState([]);
  const [projByTeam, setProjByTeam] = useState({});
  const [poGames, setPoGames] = useState([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(null);

  // No season_projections rows exist once a season's finished (simulate_season
  // has nothing left to project over remaining games) - this is empty for a
  // completed NBA season and populated for an in-progress WNBA season right
  // now, and flips back automatically once a new season's projections start
  // getting written, no manual toggle needed.
  const hasProjections = Object.keys(projByTeam).length > 0;

  let leagueConfig;
  let configError = null;
  try {
    leagueConfig = getLeagueConfig(league);
  } catch (e) {
    configError = e.message;
  }

  // Resolve "current season" from real data (latest season with games)
  // rather than a hardcoded year, so this self-corrects the moment a new
  // season starts writing rows - no manual bump needed each year.
  useEffect(() => {
    if (!leagueConfig) return;
    setSeason(null);
    getCurrentSeason(league).then(({ season: resolved }) => {
      setSeason(resolved);
    });
  }, [league, leagueConfig]);

  useEffect(() => {
    if (!leagueConfig || season === null) return;
    setLoading(true);
    Promise.all([
      fetchStandings(league, season, variant),
      fetchProjection(league, season, variant),
      // Only conference-bracket leagues (NBA) need actual playoff game rows
      // right now — OverallBracketTab (WNBA) projects off standings alone.
      leagueConfig.playoffFormat?.type === "conference-bracket"
        ? fetchPlayoffGames(league, season, variant)
        : Promise.resolve({ poGames: [], error: null }),
    ]).then(([standingsResult, projResult, poResult]) => {
      setStandings(standingsResult.standings);
      setStandingsGames(standingsResult.games);
      setFetchError(standingsResult.error);
      setProjByTeam(projResult.projByTeam); // projection errors are non-fatal - table still renders, projection columns just show "—"
      setPoGames(poResult.poGames); // playoff-fetch errors are non-fatal - bracket tab just renders empty/TBD
      setLoading(false);
    });
  }, [league, leagueConfig, variant, season]);

  if (configError) {
    return (
      <div style={{ padding: 40, fontFamily: "var(--font-mono)" }}>
        <p>Unknown league: &quot;{league}&quot;</p>
        <p>{configError}</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div style={{ padding: 40, fontFamily: "var(--font-mono)", color: "var(--text3)", fontSize: 13 }}>
        Loading…
      </div>
    );
  }

  if (fetchError) {
    return (
      <div style={{ padding: 40, fontFamily: "var(--font-mono)", color: "#b91c1c", fontSize: 13 }}>
        Couldn&apos;t load ratings: {fetchError.message}
      </div>
    );
  }

  if (standings.length === 0) {
    return (
      <div style={{ padding: 40, fontFamily: "var(--font-mono)", color: "var(--text3)", fontSize: 13 }}>
        No data yet for {leagueConfig.label} season {season}.
      </div>
    );
  }

  const minRating = Math.min(...standings.map((r) => r.rating ?? 0));
  const maxRating = Math.max(...standings.map((r) => r.rating ?? 0));

  return (
    <div>
      <div className="hero">
        <div>
          <div className="hero-label">
            {leagueConfig.seasonLabel(season)} Season
          </div>
          <div className="hero-heading">Dashboard</div>
          <div className="hero-sub">
            {VARIANT_LABELS[variant]} · Updated after every game
          </div>
        </div>
      </div>

      <div
        style={{
          borderBottom: "1px solid var(--border)",
          background: "var(--surface)",
          display: "flex",
          maxWidth: 1280,
          margin: "0 auto",
          padding: "0 2rem",
        }}
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              fontSize: 13,
              fontFamily: "var(--font-mono)",
              padding: "12px 20px",
              cursor: "pointer",
              background: "none",
              border: "none",
              marginBottom: -1,
              borderBottom:
                activeTab === tab.id
                  ? "2px solid var(--acc)"
                  : "2px solid transparent",
              color: activeTab === tab.id ? "var(--acc)" : "var(--text3)",
              fontWeight: activeTab === tab.id ? 600 : 400,
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "rankings" && (
        <div style={{ maxWidth: 1280, margin: "0 auto", padding: "1.5rem 2rem 4rem" }}>
        <div className="main-grid">
          <div className="left-col">
            <div className="section-label">Current Ratings</div>
            <table className="ratings-table">
              <thead>
                <tr>
                  <Th align="left">#</Th>
                  <Th align="left">Team</Th>
                  <Th>Rating</Th>
                  <Th align="right" style={{ width: 90 }}>Strength</Th>
                  <Th>Δ Last</Th>
                  <Th>Record</Th>
                  {hasProjections && (
                    <>
                      <Th>Proj. W</Th>
                      <Th>10th–90th</Th>
                      <Th>P(1st)</Th>
                    </>
                  )}
                </tr>
              </thead>
              <tbody>
                {standings.map((row, i) => {
                  const team = leagueConfig.teams[row.team_id];
                  if (!team) return null; // defensive: skip any team_id not in this league's config
                  const barPct = maxRating > minRating ? ((row.rating - minRating) / (maxRating - minRating)) * 100 : 50;
                  const chgPos = (row.change ?? 0) > 0;
                  // black/near-black primaries (Nets, Aces) fall back to tertiary so the bar/border isn't invisible —
                  // see lib/teamColors.js for why this uses luminance, not a string match
                  const fillColor = getFillColor(team);
                  const proj = projByTeam[row.team_id];
                  return (
                    <tr
                      key={row.team_id}
                      style={{
                        borderLeft: `4px solid ${fillColor}`,
                        background: `linear-gradient(to right, ${fillColor} 0%, ${fillColor} 180px, ${fillColor}55 260px, transparent 340px)`,
                      }}
                    >
                      <td style={{ textAlign: "right", padding: "0 10px 0 6px", fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, color: "#fff", width: 36 }}>
                        {i + 1}
                      </td>
                      <td style={{ padding: "10px 8px" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                          <TeamMark team={team} teamId={row.team_id} league={league} />
                          <span style={{ fontSize: 13, fontWeight: 700, color: team.secondary }}>{team.name}</span>
                        </div>
                      </td>
                      <td style={{ textAlign: "center", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 14, fontWeight: 700, color: "var(--text)" }}>
                        {row.rating?.toFixed(1) ?? "—"}
                      </td>
                      <td style={{ padding: "0 8px", width: 130 }}>
                        <div style={{ height: 4, background: "rgba(0,0,0,0.12)", borderRadius: 2 }}>
                          <div style={{ width: `${barPct}%`, height: 4, borderRadius: 2, background: fillColor }} />
                        </div>
                      </td>
                      <td style={{ textAlign: "center", padding: "0 12px" }}>
                        <span
                          style={{
                            fontFamily: "var(--font-mono)",
                            fontSize: 12,
                            fontWeight: 700,
                            padding: "2px 8px",
                            borderRadius: 4,
                            color: chgPos ? "#1a7a34" : "#b91c1c",
                            background: chgPos ? "rgba(26,122,52,0.12)" : "rgba(185,28,28,0.10)",
                          }}
                        >
                          {chgPos ? "+" : ""}
                          {row.change?.toFixed(1) ?? "—"}
                        </span>
                      </td>
                      <td style={{ textAlign: "center", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)" }}>
                        {row.w}–{row.l}
                      </td>
                      {hasProjections && (
                        <>
                          <td style={{ textAlign: "center", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text)" }}>
                            {proj?.avg_wins?.toFixed(1) ?? "—"}
                          </td>
                          <td style={{ textAlign: "center", padding: "0 16px", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text2)" }}>
                            {proj ? `${proj.p10_wins}–${proj.p90_wins}` : "—"}
                          </td>
                          <td
                            style={{
                              textAlign: "center",
                              padding: "0 16px",
                              fontFamily: "var(--font-mono)",
                              fontSize: 12,
                              fontWeight: proj?.prob_finish_first >= 0.05 ? 700 : 400,
                              color: proj?.prob_finish_first >= 0.05 ? "var(--text)" : "var(--text2)",
                            }}
                          >
                            {proj ? `${(proj.prob_finish_first * 100).toFixed(proj.prob_finish_first < 0.01 ? 1 : 0)}%` : "—"}
                          </td>
                        </>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <GamesPanel league={league} season={season} variant={variant} leagueConfig={leagueConfig} />
        </div>
        </div>
      )}

      {activeTab === "standings" && (
        <div style={{ maxWidth: 1280, margin: "0 auto", padding: "1.5rem 2rem 4rem" }}>
          <StandingsTab leagueConfig={leagueConfig} standings={standings} games={standingsGames} season={season} variant={variant} />
        </div>
      )}

      {activeTab === "bracket" && (
        <div style={{ maxWidth: 1280, margin: "0 auto", padding: "1.5rem 2rem 4rem" }}>
          {leagueConfig.playoffFormat?.type === "conference-bracket" ? (
            <div style={{ overflowX: "auto" }}>
              <BracketTab poGames={poGames} standings={standings} leagueConfig={leagueConfig} season={season} />
            </div>
          ) : leagueConfig.playoffFormat?.type === "overall-bracket" ? (
            <div style={{ overflowX: "auto" }}>
              <OverallBracketTab standings={standings} leagueConfig={leagueConfig} season={season} />
            </div>
          ) : (
            <div style={{ padding: "2.5rem 0", textAlign: "center", color: "var(--text3)", fontFamily: "var(--font-mono)", fontSize: 13 }}>
              Playoff Bracket — coming soon
            </div>
          )}
        </div>
      )}

      <Footer />
    </div>
  );
}
