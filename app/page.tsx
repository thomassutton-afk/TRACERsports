import Link from "next/link";
import { SPORTS, LEAGUES } from "@/lib/sports/registry";
import { supabase } from "@/lib/supabase";
import { getGamesOrScheduleForDate, getCurrentSeason, roundLabel } from "@/lib/gamesData";
import TeamMark from "./[league]/TeamMark";

/**
 * Homepage.
 *
 * Two live, data-backed sections instead of bare navigation links:
 *  1. TODAY'S GAMES — real box scores / upcoming matchups for whichever
 *     leagues actually have something today, pulled via the same
 *     pairing/fetch logic GamesPanel.jsx uses (lib/gamesData.js), so this
 *     can't silently drift from what the per-league dashboards show.
 *     A league with nothing today just doesn't get a row - no empty
 *     placeholder, no stale "last game" leftover.
 *  2. League picker cards, each showing a live top-3 so there's something
 *     concrete to look at before clicking in.
 *
 * Both fetch server-side (async Server Component - no client "use client",
 * no loading spinners) using the same public anon-key client the rest of
 * the app already uses.
 */

// "Today" per US sports-day convention (America/New_York), NOT server UTC.
// Game `date` values in the DB follow the game's actual US calendar day.
// Computing "today" from the server's raw UTC clock would show the wrong
// slate for a few hours around midnight ET - e.g. a 10pm ET tip-off is
// already "tomorrow" in UTC. en-CA locale gives YYYY-MM-DD directly.
function todayET() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/New_York",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

async function fetchTopTeams(league: string, season: number, variant: string, count = 3) {
  const { data, error } = await supabase
    .from("games")
    .select("team_id, date, post_gm_rate")
    .eq("league", league)
    .eq("season", season)
    .eq("variant", variant)
    .order("date", { ascending: false })
    .limit(200);

  if (error || !data) return [];

  const latestByTeam: Record<string, number> = {};
  for (const row of data) {
    if (!(row.team_id in latestByTeam)) {
      latestByTeam[row.team_id] = row.post_gm_rate;
    }
  }

  return Object.entries(latestByTeam)
    .map(([team_id, rating]) => ({ team_id, rating }))
    .sort((a, b) => b.rating - a.rating)
    .slice(0, count);
}

function TodayGameCard({ leagueId, leagueConfig, game }: { leagueId: string; leagueConfig: any; game: any }) {
  const homeTeam = leagueConfig.teams[game.home];
  const awayTeam = leagueConfig.teams[game.away];
  const homeFav = game.winProb != null && game.winProb >= 0.5;
  const favPct = game.winProb != null ? Math.round(homeFav ? game.winProb * 100 : (1 - game.winProb) * 100) : null;

  return (
    <div style={{ minWidth: 250, flex: "0 0 auto", background: "var(--surface)", border: game.upcoming ? "1px dashed var(--border2)" : "1px solid var(--border)", borderRadius: 10, padding: "10px 12px" }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)" }}>
        <span style={{ fontWeight: 700, color: "var(--acc)" }}>{leagueConfig.label}</span>
        <span>{game.upcoming ? "Upcoming" : roundLabel(game.round, game.type, leagueConfig)}</span>
      </div>

      <div style={{ display: "flex", alignItems: "center", padding: "10px 0 6px", gap: 8 }}>
        <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 6 }}>
          {awayTeam && <TeamMark team={awayTeam} teamId={game.away} league={leagueId} size={24} />}
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text)", fontWeight: 600 }}>{game.away}</span>
        </div>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 900, color: "var(--text)" }}>
          {game.upcoming ? "—" : game.awayScore}
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text3)" }}>@</span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 15, fontWeight: 900, color: "var(--text)" }}>
          {game.upcoming ? "—" : game.homeScore}
        </span>
        <div style={{ flex: 1, display: "flex", alignItems: "center", gap: 6, justifyContent: "flex-end" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text)", fontWeight: 600 }}>{game.home}</span>
          {homeTeam && <TeamMark team={homeTeam} teamId={game.home} league={leagueId} size={24} />}
        </div>
      </div>

      {favPct != null && (!game.upcoming || game.showPick) && (
        <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 4, borderTop: "1px solid var(--border)", marginTop: 2, paddingTop: 6, fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--text2)" }}>
          {!homeFav && <span style={{ color: "var(--acc)" }}>◀</span>}
          <strong>{homeFav ? game.home : game.away} {favPct}%</strong>
          {homeFav && <span style={{ color: "var(--acc)" }}>▶</span>}
        </div>
      )}
    </div>
  );
}

export default async function Home() {
  const allLeagueIds = Object.values(SPORTS).flatMap((sport) => sport.leagues);
  const todayStr = todayET();

  // Each league resolves its own current season (e.g. NFL is still on its
  // 2025 season through the summer, while NBA/WNBA have already rolled to
  // 2026) — same helper app/[league]/page.js uses, so this can't drift out
  // of sync with what the per-league dashboards show.
  const currentSeasonEntries = await Promise.all(
    allLeagueIds.map(async (leagueId) => [leagueId, (await getCurrentSeason(leagueId)).season])
  );
  const currentSeasonByLeague: Record<string, number | null> = Object.fromEntries(currentSeasonEntries);

  const [topTeamsEntries, todaysGamesEntries] = await Promise.all([
    Promise.all(
      allLeagueIds.map(async (leagueId) => {
        const season = currentSeasonByLeague[leagueId];
        return [leagueId, season ? await fetchTopTeams(leagueId, season, "echo") : []];
      })
    ),
    Promise.all(
      allLeagueIds.map(async (leagueId) => {
        const season = currentSeasonByLeague[leagueId];
        return [
          leagueId,
          season ? await getGamesOrScheduleForDate(leagueId, todayStr, season, "echo") : [],
        ];
      })
    ),
  ]);
  const topTeamsByLeague: Record<string, any[]> = Object.fromEntries(topTeamsEntries);
  const todaysGamesByLeague: Record<string, any[]> = Object.fromEntries(todaysGamesEntries);
  const hasAnyGamesToday = Object.values(todaysGamesByLeague).some((games) => games.length > 0);

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto", padding: "3rem 2rem 4rem" }}>
      <div style={{ textAlign: "center", marginBottom: "2.5rem" }}>
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            fontWeight: 500,
            color: "var(--acc)",
            letterSpacing: 2,
            textTransform: "uppercase",
            marginBottom: 10,
          }}
        >
          Elo Power Ratings
        </div>
        <h1
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 44,
            fontWeight: 900,
            letterSpacing: -1.5,
            color: "var(--text)",
          }}
        >
          TRACER
        </h1>
      </div>

      {hasAnyGamesToday && (
        <div style={{ marginBottom: "2.5rem" }}>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              fontWeight: 700,
              color: "var(--text3)",
              textTransform: "uppercase",
              letterSpacing: 2,
              marginBottom: 14,
              paddingBottom: 8,
              borderBottom: "1px solid var(--border)",
            }}
          >
            Today's Games
          </div>
          <div style={{ display: "flex", gap: 12, overflowX: "auto", paddingBottom: 4 }}>
            {allLeagueIds.flatMap((leagueId) =>
              (todaysGamesByLeague[leagueId] || []).map((game, i) => (
                <TodayGameCard key={`${leagueId}-${i}`} leagueId={leagueId} leagueConfig={(LEAGUES as any)[leagueId]} game={game} />
              ))
            )}
          </div>
        </div>
      )}

      {Object.values(SPORTS).map((sport) => (
        <div key={sport.id} style={{ marginBottom: "2.5rem" }}>
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              fontWeight: 700,
              color: "var(--text3)",
              textTransform: "uppercase",
              letterSpacing: 2,
              marginBottom: 14,
              paddingBottom: 8,
              borderBottom: "1px solid var(--border)",
            }}
          >
            {sport.label}
          </div>
          <div style={{ display: "flex", gap: 20, flexWrap: "wrap" }}>
            {sport.leagues.map((leagueId) => {
              const config = (LEAGUES as any)[leagueId];
              const topTeams = topTeamsByLeague[leagueId] || [];
              return (
                <Link key={leagueId} href={`/${leagueId}?variant=echo`} className="league-card">
                  <div style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 900, color: "var(--text)", marginBottom: 4 }}>
                    {config.label}
                  </div>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text2)" }}>
                    {config.fullName}
                  </div>

                  {topTeams.length > 0 && (
                    <div style={{ marginTop: 14, display: "flex", flexDirection: "column", gap: 7 }}>
                      {topTeams.map((t, i) => {
                        const team = config.teams[t.team_id];
                        if (!team) return null;
                        return (
                          <div key={t.team_id} style={{ display: "flex", alignItems: "center", gap: 8, fontFamily: "var(--font-mono)", fontSize: 12 }}>
                            <span style={{ color: "var(--text3)", width: 14 }}>{i + 1}</span>
                            <TeamMark team={team} teamId={t.team_id} league={leagueId} size={18} />
                            <span style={{ flex: 1, color: "var(--text)", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                              {team.name}
                            </span>
                            <span style={{ color: "var(--text2)" }}>{t.rating?.toFixed(1)}</span>
                          </div>
                        );
                      })}
                    </div>
                  )}

                  <div
                    style={{
                      marginTop: 14,
                      fontFamily: "var(--font-mono)",
                      fontSize: 11,
                      fontWeight: 600,
                      color: "var(--acc)",
                    }}
                  >
                    View Full Rankings →
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
