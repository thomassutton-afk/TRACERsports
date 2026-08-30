/**
 * gamesData.js — shared game-pairing/fetch helpers.
 *
 * Extracted out of app/[league]/GamesPanel.jsx (unchanged logic, just moved)
 * so the homepage's "Today's Games" strip can reuse the exact same
 * pairing/query code instead of a second hand-copied version that could
 * silently drift from GamesPanel's behavior over time.
 */

import { supabase } from "@/lib/supabase";
import { LEAGUES } from "@/lib/sports/registry";

// Fetches every row of a paginated Supabase query, requesting pages in
// PARALLEL instead of one at a time. Supabase/PostgREST caps a single
// request to PAGE_SIZE rows, so any full-history query (e.g. All-Time's
// 150k+ rows across 30 NBA seasons) needs many pages — the original
// pattern used throughout this file awaited each page sequentially, so
// the total wait was the SUM of every page's round-trip (150+ round-trips
// for All-Time, one at a time). This fetches page 1 with an exact row
// count, then fires every remaining page at once, so the wait is roughly
// the slowest SINGLE page, not the sum of all of them.
//
// `pageQuery(from, to, withCount)` must return an already-built Supabase
// query for that row range — `withCount` is only ever true on the first
// call, so callers should only request `{ count: "exact" }` then (asking
// Postgres to also count the full table on every page would add needless
// overhead to pages 2+, which don't need the count).
async function fetchAllPages(pageQuery, pageSize = 1000) {
  const first = await pageQuery(0, pageSize - 1, true);
  if (first.error) return { rows: [], error: first.error };
  const rows = first.data ?? [];
  const total = first.count ?? rows.length;

  if (rows.length < pageSize || total <= rows.length) {
    return { rows, error: null };
  }

  const remainingPages = Math.ceil(total / pageSize) - 1;
  const pagePromises = [];
  for (let i = 1; i <= remainingPages; i++) {
    const from = i * pageSize;
    pagePromises.push(pageQuery(from, from + pageSize - 1, false));
  }
  const pageResults = await Promise.all(pagePromises);
  for (const page of pageResults) {
    if (page.error) return { rows: [], error: page.error };
    rows.push(...(page.data ?? []));
  }
  return { rows, error: null };
}

// A completed game's real final score, below which a row is almost
// certainly bad/placeholder data rather than a real result (e.g. an
// export artifact) — NOT the same across sports, so this has to come
// from each league's config rather than being one constant. Basketball
// scores are always comfortably above 50; football scores routinely
// fall well under that (a real, final "24-17" is completely normal),
// so reusing basketball's threshold for football would silently drop
// nearly every real completed game — exactly what happened before this
// was made per-league. `!row.points_for` above already independently
// excludes null/undefined (unplayed games), so this only needs to
// guard against a bad-but-truthy value, hence the low default.
function minValidScore(league) {
  return LEAGUES[league]?.minValidGameScore ?? 1;
}

// A round value's numeric "depth" for comparison purposes (champion
// detection, All-Time depth filters, WNBA's era-shift math, etc).
// Prefers leagueConfig.engine?.playoffRoundOrder (an explicit, ordered list of
// that league's real elimination-bracket round codes) when present —
// 1-based rank matching array position, so 'WC' -> 1, 'DV' -> 2, etc.
// for NFL, and '1' -> 1, '2' -> 2, etc. for NBA/WNBA (identical result
// to the old Number(round) parsing those two already relied on, so
// this is a pure generalization, not a behavior change for them).
// Falls back to Number(round) for any league that doesn't define
// playoffRoundOrder. Returns NaN for anything not found/parseable
// (RS, NBA's Play-In/In-Season-Tournament codes, etc.) — same "not
// part of the bracket depth" signal the old NaN-check callers already
// handle correctly.
function roundRank(round, leagueConfig) {
  const order = leagueConfig?.engine?.playoffRoundOrder;
  if (order) {
    const idx = order.indexOf(String(round));
    return idx === -1 ? NaN : idx + 1;
  }
  return Number(round);
}

export function formatDate(dateStr) {
  const [y, m, d] = dateStr.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

// type/round -> display label ("WNBA Finals", "Reg. Season", etc). The
// optional seasonDelta shifts round upward before lookup - needed because
// WNBA's playoff STRUCTURE has changed over time (not just series
// length): 1997 only had 2 real rounds, so that year's championship game
// is stored under round=2, the same raw number today's Semifinals uses.
// Passing the season's delta (from getSeasonRoundDelta, computed against
// getSeasonMaxRounds) re-maps round=2 to the "WNBA Finals" label for that
// season instead of "Semifinals". Callers with tallyPlayoffResults output
// in hand should prefer that object's own .roundLabel (already resolved,
// see tallyPlayoffResults) - this function is for callers working off raw
// game rows one at a time (Game Log tables), where there's no tally object.
export function roundLabel(round, type, leagueConfig, seasonDelta = 0) {
  if (type !== "P") return "Reg. Season";
  const roundLabelsCfg = leagueConfig.engine?.roundLabels ?? {};
  const rndNum = roundRank(round, leagueConfig);
  if (seasonDelta && !Number.isNaN(rndNum) && rndNum >= 1) {
    const order = leagueConfig.engine?.playoffRoundOrder;
    const shiftedKey = order ? order[rndNum + seasonDelta - 1] : String(rndNum + seasonDelta);
    const shifted = shiftedKey != null ? roundLabelsCfg[shiftedKey] : null;
    if (shifted != null) return shifted;
  }
  return roundLabelsCfg[String(round)] ?? round ?? "Playoffs";
}

export function pairGameRows(rows, league) {
  const seen = new Set();
  const games = [];
  const minScore = minValidScore(league);
  for (const row of rows) {
    if (row.home_away !== "H" || !row.points_for || row.points_for < minScore) continue;
    const key = `${row.date}_${row.team_id}_${row.opponent_id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const away = rows.find(
      (g) => g.date === row.date && g.team_id === row.opponent_id && g.home_away === "A"
    );
    games.push({
      date: row.date,
      home: row.team_id,
      away: row.opponent_id,
      homeScore: row.points_for,
      awayScore: row.points_against,
      homeRating: row.post_gm_rate,
      awayRating: away?.post_gm_rate ?? null,
      homeChange: row.rating_change,
      awayChange: away?.rating_change ?? null,
      winProb: row.expected_win_pct,
      round: row.round,
      type: row.type,
      ot: row.ot || false,
      upcoming: false,
    });
  }
  return games;
}

export function pairScheduleRows(rows, nextGameByTeam) {
  const seen = new Set();
  const games = [];
  for (const row of rows) {
    if (row.home_away !== "H") continue;
    const key = `${row.date}_${row.team_id}_${row.opponent_id}`;
    if (seen.has(key)) continue;
    seen.add(key);
    const isNextForHome = nextGameByTeam[row.team_id] === row.date;
    const isNextForAway = nextGameByTeam[row.opponent_id] === row.date;
    games.push({
      date: row.date,
      home: row.team_id,
      away: row.opponent_id,
      winProb: row.expected_win_pct,
      round: row.round,
      type: row.type,
      upcoming: true,
      showPick: isNextForHome && isNextForAway,
    });
  }
  return games;
}

export async function getGamesForDate(league, dateStr, season, variant) {
  const { data } = await supabase
    .from("games")
    .select(
      "team_id,post_gm_rate,rating_change,date,type,round,opponent_id,home_away,points_for,points_against,expected_win_pct,ot"
    )
    .eq("league", league)
    .eq("season", season)
    .eq("variant", variant)
    .eq("date", dateStr);
  return pairGameRows(data || [], league);
}

export async function getNextGameDateByTeam(league, season, variant) {
  const { data } = await supabase
    .from("schedule")
    .select("team_id, date")
    .eq("league", league)
    .eq("season", season)
    .eq("variant", variant);
  const earliest = {};
  for (const row of data || []) {
    if (!earliest[row.team_id] || row.date < earliest[row.team_id]) {
      earliest[row.team_id] = row.date;
    }
  }
  return earliest;
}

export async function getScheduledGamesForDate(league, dateStr, season, variant) {
  const [{ data }, nextGameByTeam] = await Promise.all([
    supabase
      .from("schedule")
      .select("team_id,opponent_id,home_away,date,type,round,expected_win_pct")
      .eq("league", league)
      .eq("season", season)
      .eq("variant", variant)
      .eq("date", dateStr),
    getNextGameDateByTeam(league, season, variant),
  ]);
  return pairScheduleRows(data || [], nextGameByTeam);
}

export async function getLatestGameDate(league, season, variant) {
  const { data } = await supabase
    .from("games")
    .select("date")
    .eq("league", league)
    .eq("season", season)
    .eq("variant", variant)
    .eq("home_away", "H")
    .not("points_for", "is", null)
    .order("date", { ascending: false })
    .limit(1);
  return data?.[0]?.date ?? null;
}

// Games (played OR scheduled) for a specific calendar date - used by the
// homepage, which (unlike GamesPanel) wants "today" specifically, not
// "whatever the latest available date is." Returns [] if there's nothing
// on that date either way, which is the homepage's cue to skip that
// league's section entirely rather than showing something stale.
export async function getGamesOrScheduleForDate(league, dateStr, season, variant) {
  const played = await getGamesForDate(league, dateStr, season, variant);
  if (played.length > 0) return played;
  return getScheduledGamesForDate(league, dateStr, season, variant);
}

// ---------------------------------------------------------------------------
// Season-level helpers — shared by the live Dashboard (app/[league]/page.js)
// and the historical Season Page (app/[league]/season/page.js). Both need
// "aggregate this league's games for season X, variant Y" - same shape,
// just a different X - so this is one function, not two copies.
// ---------------------------------------------------------------------------

// Every season that actually has data for a league, newest first. Reads
// preseason_ratings rather than games directly - it's one row per team per
// season (not one row per team per game), so pulling the full table to
// dedupe season values client-side stays cheap even after 30+ seasons of
// history, where doing the same thing against `games` would not.
export async function getAvailableSeasons(league) {
  // Season ranges don't differ between Echo/Pulse - both variants are
  // written for every game a season has - so this intentionally always
  // reads the 'echo' variant rather than depending on whichever variant
  // the page happens to be showing right now.
  const { data, error } = await supabase
    .from("preseason_ratings")
    .select("season")
    .eq("league", league)
    .eq("variant", "echo");

  if (error || !data) return { seasons: [], error };

  const seasons = [...new Set(data.map((r) => r.season))].sort((a, b) => b - a);
  return { seasons, error: null };
}

// The most recent season with real data for a league. Deliberately NOT a
// hardcoded constant anywhere in the app - a hardcoded "current season"
// silently goes stale the moment a new season starts and nobody remembers
// to bump it. This just asks the data what the latest season actually is.
export async function getCurrentSeason(league) {
  const { seasons, error } = await getAvailableSeasons(league);
  if (error || seasons.length === 0) return { season: null, error };
  return { season: seasons[0], error: null };
}

// Every game row (both types) for a team across a season, used by Season
// Page to derive regular-season-only record/rating, the true season-end
// rating (which includes playoff games, when a team made the playoffs),
// AND the season's model-accuracy summary — all from one query, rather
// than fetching the same season's rows three separate times.
export async function fetchSeasonTeamGames(league, season, variant) {
  return fetchAllPages((from, to, withCount) =>
    supabase
      .from("games")
      .select(
        "team_id, date, type, post_gm_rate, rating_change, w, l, home_away, accuracy, brier",
        withCount ? { count: "exact" } : undefined
      )
      .eq("league", league)
      .eq("season", season)
      .eq("variant", variant)
      .order("date", { ascending: true })
      .range(from, to)
  );
}

// Each team's preseason rating for a season/variant. Small table (one row
// per team), so a single unpaged query is fine. Pulse resets every team to
// the same baseline each season, so this is only meaningful for Echo —
// callers should skip rendering it for Pulse rather than show a column of
// identical numbers.
export async function fetchPreseasonRatings(league, season, variant) {
  const { data, error } = await supabase
    .from("preseason_ratings")
    .select("team_id, preseason_elo")
    .eq("league", league)
    .eq("season", season)
    .eq("variant", variant);

  if (error) return { byTeam: {}, error };
  const byTeam = {};
  for (const row of data ?? []) byTeam[row.team_id] = row.preseason_elo;
  return { byTeam, error: null };
}

// League-wide model accuracy across EVERY season on record (no season
// filter) - the About page's live counterpart to buildSeasonAccuracy
// below, which is season-scoped. Minimal columns (just what
// buildSeasonAccuracy actually reads) since this can span 20+ seasons of
// games. Same scope caveat as buildSeasonAccuracy: every game type
// (regular season, playoff, play-in, in-season tournament) is blended
// into one number, not broken out.
export async function fetchLeagueAccuracy(league, variant) {
  return fetchAllPages((from, to, withCount) =>
    supabase
      .from("games")
      .select("home_away, accuracy, brier", withCount ? { count: "exact" } : undefined)
      .eq("league", league)
      .eq("variant", variant)
      .range(from, to)
  );
}

// League-wide model accuracy for a season, straight off games.accuracy/
// .brier (populated per game row by the rating engine) - no separate
// season_accuracy table needed, that ContinElo-era table was never carried
// into the new schema. Counts each real-world game once (home_away='H'
// rows only), same de-dup convention as pairGameRows above.
export function buildSeasonAccuracy(rows) {
  const homeRows = rows.filter((r) => r.home_away === "H" && r.accuracy != null);
  if (homeRows.length === 0) return null;
  const avgAccuracy = homeRows.reduce((sum, r) => sum + r.accuracy, 0) / homeRows.length;
  const brierRows = homeRows.filter((r) => r.brier != null);
  const avgBrier = brierRows.length
    ? brierRows.reduce((sum, r) => sum + r.brier, 0) / brierRows.length
    : null;
  return {
    n: homeRows.length,
    pct: (avgAccuracy * 100).toFixed(1),
    brier: avgBrier != null ? avgBrier.toFixed(3) : null,
  };
}

// Full-detail game log for an entire season, across every team — the
// league-wide counterpart to fetchTeamGameLog (which is scoped to one
// team). Powers the Season Page's Game Log tab. Paired down to one row
// per real-world game via pairGameRows, the same de-dup/pairing logic
// every other game-log-shaped view in this file already uses.
export async function fetchSeasonGameLog(league, season, variant, { type } = {}) {
  const { rows: allRows, error } = await fetchAllPages((from, to, withCount) => {
    let q = supabase
      .from("games")
      .select(
        "game_id, date, team_id, opponent_id, home_away, points_for, points_against, " +
          "type, round, expected_win_pct, rating_change, result, ot",
        withCount ? { count: "exact" } : undefined
      )
      .eq("league", league)
      .eq("season", season)
      .eq("variant", variant)
      .order("date", { ascending: false });
    if (type) q = q.eq("type", type);
    return q.range(from, to);
  });

  if (error) return { games: [], error };

  return { games: pairGameRows(allRows, league), error: null };
}

// Snaps game-by-game post-game ratings to weekly Sunday checkpoints, one
// series per team — shared reducer behind the Season Page's Rating Chart
// (Heatmap + Head-to-Head modes both consume this same shape). Ported
// unchanged from reference/old-site/SeasonPage.jsx's buildWeeklySnapshots.
//
// Input: byTeam = { team_id: [{date: ms, rating}, ...] }, each array
// already sorted ascending by date.
// Output: { team_id: [{date: ms, rating}, ...] } — one point per Sunday
// (plus opening night), forward-filled for teams with no game that week.
export function buildWeeklySnapshots(byTeam) {
  const allDates = Object.values(byTeam).flat().map((p) => p.date).sort((a, b) => a - b);
  if (!allDates.length) return {};

  const openingNight = allDates[0];
  const lastDate = Math.max(...Object.values(byTeam).map((pts) => pts.at(-1)?.date ?? 0));

  const sundays = [];
  const d = new Date(openingNight);
  while (d.getDay() !== 0) d.setDate(d.getDate() + 1);
  while (d.getTime() <= lastDate) {
    sundays.push(d.getTime());
    d.setDate(d.getDate() + 7);
  }

  const result = {};
  for (const [teamId, points] of Object.entries(byTeam)) {
    const snaps = [];
    const firstGame = points[0];
    if (!firstGame) {
      result[teamId] = snaps;
      continue;
    }
    snaps.push({ date: openingNight, rating: firstGame.rating });

    for (const sun of sundays) {
      let best = firstGame;
      for (const p of points) {
        if (p.date <= sun) best = p;
        else break;
      }
      snaps.push({ date: sun, rating: best.rating });
    }
    result[teamId] = snaps;
  }
  return result;
}

// Rating heatmap color scale — red (low) through green (high), interpolated
// across a fixed set of stops. Ported unchanged from the old site.
const RATING_STOPS = [
  [0, "#C8102E"],
  [0.2, "#E05A28"],
  [0.42, "#F5A623"],
  [0.62, "#7AB648"],
  [0.82, "#2D9B5A"],
  [1.0, "#154733"],
];

export function ratingColor(val, globalMin, globalMax) {
  const t = Math.max(0, Math.min(1, (val - globalMin) / (globalMax - globalMin || 1)));
  for (let i = 1; i < RATING_STOPS.length; i++) {
    const [p0, c0] = RATING_STOPS[i - 1];
    const [p1, c1] = RATING_STOPS[i];
    if (t <= p1) {
      const f = (t - p0) / (p1 - p0);
      const h = (hex) => [parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16)];
      const [r0, g0, b0] = h(c0);
      const [r1, g1, b1] = h(c1);
      return `rgb(${Math.round(r0 + f * (r1 - r0))},${Math.round(g0 + f * (g1 - g0))},${Math.round(b0 + f * (b1 - b0))})`;
    }
  }
  return RATING_STOPS.at(-1)[1];
}

// Reduces fetchSeasonTeamGames' raw rows into one row per team: RS-only
// record + RS-end rating, plus the true final rating for the season (the
// last game either way — so it reflects playoff games too, for teams that
// made it that far).
export function buildSeasonStandingsRows(rows) {
  const byTeam = {};
  for (const row of rows) {
    const t = (byTeam[row.team_id] ??= {
      team_id: row.team_id,
      rsW: 0,
      rsL: 0,
      rsRating: null,
      finalRating: null,
      finalChange: null,
    });
    if (row.type === "R") {
      t.rsW += row.w ?? 0;
      t.rsL += row.l ?? 0;
      t.rsRating = row.post_gm_rate; // rows are date-ascending — last 'R' row seen is RS-end rating
    }
    t.finalRating = row.post_gm_rate; // last row overall, regardless of type
    t.finalChange = row.rating_change;
  }
  return Object.values(byTeam);
}

// Raw playoff game rows (type='P', excluding round=0.1 in-season-tournament
// games) for an arbitrary season - same query BracketTab's data needs for
// the current season, just not locked to it.
export async function fetchSeasonPlayoffGames(league, season, variant) {
  return fetchAllPages((from, to, withCount) =>
    supabase
      .from("games")
      .select(
        "team_id, season, round, result, opponent_id, home_away, date",
        withCount ? { count: "exact" } : undefined
      )
      .eq("league", league)
      .eq("season", season)
      .eq("variant", variant)
      .eq("type", "P")
      .neq("round", "0.1")
      .order("date", { ascending: true })
      .range(from, to)
  ).then(({ rows, error }) => (error ? { poGames: [], error } : { poGames: rows, error: null }));
}

// Determines, for every season present in a batch of playoff-only game
// rows, the highest round actually PLAYED that season (capped at the
// league's configured max as a sanity ceiling). This is the single source
// of truth for "which round was really that season's Finals" - used by
// tallyPlayoffResults (champion flag + round label) and by any raw-row
// caller (Game Log tables) via getSeasonRoundDelta below, so the champion
// flag, the round label text, and the All-Time depth filters can never
// disagree with each other about a given season's real bracket structure.
export function getSeasonMaxRounds(poGames, leagueConfig) {
  const configuredMax = leagueConfig.engine?.playoffRoundOrder?.length ?? null;

  const seasonMaxRound = {};
  for (const row of poGames) {
    const season = row.season;
    const rndNum = roundRank(row.round, leagueConfig);
    if (season == null || Number.isNaN(rndNum) || rndNum < 1) continue;
    const capped = configuredMax != null ? Math.min(rndNum, configuredMax) : rndNum;
    if (seasonMaxRound[season] == null || capped > seasonMaxRound[season]) {
      seasonMaxRound[season] = capped;
    }
  }
  return { seasonMaxRound, configuredMax };
}

// How many round-numbers to shift a raw round value UP by so it lines up
// with the league's current-day round labels/thresholds, for a season
// whose real bracket had fewer rounds than today's format. 0 (no shift)
// for seasons already at the configured max, or when there's nothing to
// compare against (e.g. this season has no playoff data loaded yet).
export function getSeasonRoundDelta(season, seasonMaxRound, configuredMax) {
  if (configuredMax == null || season == null) return 0;
  const seasonMax = seasonMaxRound[season];
  if (seasonMax == null) return 0;
  return configuredMax - seasonMax;
}

// Resolves how many wins a team needed to be crowned champion for a given
// season, consulting playoffFormat.winsNeededByEra when the league defines
// it (WNBA's Finals format has changed several times across history: 1997
// single game, 1998-2004 best-of-3, 2005-2024 best-of-5, 2025+ best-of-7 —
// sourced Aug 2026, see wnba/config.js). Deliberately NOT keyed by round
// number - "the finals" is resolved per-season by tallyPlayoffResults (see
// its comment for why: WNBA's round STRUCTURE has changed too, not just
// series length, so round 2 means different things in different eras).
// Falls back to the league's current-day Finals winsNeeded (or 4, i.e.
// best-of-7) for leagues/seasons that don't have era data, which covers
// the NBA (every round has always been best-of-7, so there's nothing
// era-dependent to model there).
function resolveWinsNeeded(leagueConfig, season) {
  const eras = leagueConfig.playoffFormat?.winsNeededByEra;
  if (eras?.length && season != null) {
    const era = eras.find((e) => season >= e.fromSeason && (e.toSeason == null || season <= e.toSeason));
    if (era?.winsNeeded != null) return era.winsNeeded;
  }
  const configuredMax = leagueConfig.engine?.playoffRoundOrder?.length ?? null;
  return leagueConfig.playoffFormat?.winsNeeded?.[configuredMax] ?? 4;
}

// Rolls up raw playoff game rows into a per-team { round: {w, l} } tally,
// plus which round (if any) each team was CROWNED in - i.e. actually won
// the series in, not just appeared in. "Won the series" is read off
// resolveWinsNeeded above (era-aware, not a single static value applied
// to all of history — see that function's comment for why this matters).
//
// IMPORTANT: "the finals round" is resolved PER SEASON from the data
// itself (getSeasonMaxRounds - the highest round number actually played
// that season), not from leagueConfig's static roundLabels max. WNBA's
// playoff STRUCTURE has changed over time, not just series length - 1997
// only had 2 real rounds (no "First Round" existed yet), so that year's
// actual championship game is stored under round=2, the same number
// today's 3-round Semifinals is. A team that legitimately won the 1997
// title would never trip a fixed "highestRound === 3" check, no matter
// how many games they won, because their season's bracket never went
// past round 2. Comparing each team's highestRound against ITS OWN
// season's observed max (capped at the league's configured max as a
// sanity ceiling) fixes this without needing to hardcode which years had
// which round structure - it just reads it off the actual games played.
//
// Each team's tally also gets .roundLabel (the correctly era-shifted
// display name, e.g. "WNBA Finals" not "Semifinals" for a 1997 team that
// reached their season's actual championship round) and
// .effectiveHighestRound (the delta-shifted round number, for any
// consumer doing threshold comparisons - see All-Time page's depth
// filter, which needs "did this team's SEASON-RELATIVE run reach at
// least round N" rather than a raw round-number comparison that breaks
// the same way the champion flag used to).
//
// keyFn defaults to grouping by team_id (Season Page's use — one season's
// worth of playoff rows at a time, so team_id alone is a unique key). The
// All-Time/Team pages pass rows spanning every season at once, so they key
// by `${team_id}-${season}` instead — same tally logic either way. Every
// row is expected to carry a `season` field now (both fetchSeasonPlayoffGames
// and fetchAllTimePlayoffGames select it) so both the era lookup and the
// per-season round ceiling always have what they need regardless of which
// page is calling this.
export function tallyPlayoffResults(poGames, leagueConfig, keyFn = (row) => row.team_id) {
  const roundLabelsCfg = leagueConfig.engine?.roundLabels ?? {};
  const order = leagueConfig.engine?.playoffRoundOrder;
  const { seasonMaxRound, configuredMax } = getSeasonMaxRounds(poGames, leagueConfig);

  const byKey = {};
  for (const row of poGames) {
    const key = keyFn(row);
    const t = (byKey[key] ??= { rounds: {}, champion: false, highestRound: null, season: row.season ?? null });
    const rnd = row.round;
    const r = (t.rounds[rnd] ??= { w: 0, l: 0 });
    if (row.result === 1) r.w += 1;
    else r.l += 1;

    const rndNum = roundRank(rnd, leagueConfig);
    if (!Number.isNaN(rndNum) && (t.highestRound === null || rndNum > t.highestRound)) {
      t.highestRound = rndNum;
    }
  }

  for (const t of Object.values(byKey)) {
    if (t.highestRound == null) {
      t.effectiveHighestRound = null;
      t.roundLabel = null;
      continue;
    }

    const seasonMax = t.season != null ? seasonMaxRound[t.season] : null;
    const delta = seasonMax != null && configuredMax != null ? configuredMax - seasonMax : 0;
    t.effectiveHighestRound = t.highestRound + delta;
    // Rank -> round CODE (order[rank-1]) -> label, rather than looking
    // the rank number up directly — needed for leagues whose round
    // values aren't the rank itself (NFL: rank 1 is round 'WC', not
    // round '1'). Falls back to the raw rank-as-string key for leagues
    // without playoffRoundOrder, matching the original lookup exactly.
    const effectiveKey = order ? order[t.highestRound + delta - 1] : String(t.highestRound + delta);
    const rawKey = order ? order[t.highestRound - 1] : String(t.highestRound);
    t.roundLabel = roundLabelsCfg[effectiveKey] ?? roundLabelsCfg[rawKey] ?? `Round ${t.highestRound}`;

    const seasonFinalsRound = seasonMax ?? configuredMax;
    if (seasonFinalsRound != null && t.highestRound === seasonFinalsRound) {
      const needed = resolveWinsNeeded(leagueConfig, t.season);
      const finalsCode = order ? order[seasonFinalsRound - 1] : String(seasonFinalsRound);
      const w = t.rounds[finalsCode]?.w ?? 0;
      if (w >= needed) t.champion = true;
    }
  }

  return byKey;
}

// ---------------------------------------------------------------------------
// All-time helpers — season-optional versions of the season-level helpers
// above (season=omitted fetches every season a league has), used by the
// All-Time Rankings and Team pages. Season Page keeps using the originals
// above unchanged; these are separate functions rather than an
// `season = null` branch on the existing ones, since the row shape differs
// (grouped by team+season, not just team) and callers need both at once
// in some cases (Team page shows one team's all-time row AND uses the
// same season-scoped fetch for its own dashboard-style current view).
// ---------------------------------------------------------------------------

// Every RS+PO game row for every team across every season a league has.
// Same pagination pattern as the season-scoped fetches, just without the
// `.eq("season", ...)` filter — this is the single most expensive query
// on the site (150k+ rows for a league with 30 seasons of NBA history),
// so All-Time/Team pages should call this once and derive everything else
// client-side rather than re-querying per team or per season.
export async function fetchAllTimeTeamGames(league, variant) {
  return fetchAllPages((from, to, withCount) =>
    supabase
      .from("games")
      .select(
        "team_id, season, date, type, post_gm_rate, rating_change, w, l",
        withCount ? { count: "exact" } : undefined
      )
      .eq("league", league)
      .eq("variant", variant)
      .order("season", { ascending: true })
      .order("date", { ascending: true })
      .range(from, to)
  );
}

// Preseason rating for every team, every season. Pulse resets to base
// every year (so this is Echo-only, same caveat as fetchPreseasonRatings)
// but still one row per team per season, so still paginated.
export async function fetchAllTimePreseasonRatings(league, variant) {
  const { rows: allRows, error } = await fetchAllPages((from, to, withCount) =>
    supabase
      .from("preseason_ratings")
      .select("team_id, season, preseason_elo", withCount ? { count: "exact" } : undefined)
      .eq("league", league)
      .eq("variant", variant)
      .range(from, to)
  );

  if (error) return { byTeamSeason: {}, error };

  const byTeamSeason = {};
  for (const row of allRows) byTeamSeason[`${row.team_id}-${row.season}`] = row.preseason_elo;
  return { byTeamSeason, error: null };
}

// Every playoff game row (type='P', excluding in-season-tournament) for
// every team across every season.
export async function fetchAllTimePlayoffGames(league, variant) {
  return fetchAllPages((from, to, withCount) =>
    supabase
      .from("games")
      .select(
        "team_id, season, round, result, opponent_id, home_away, date",
        withCount ? { count: "exact" } : undefined
      )
      .eq("league", league)
      .eq("variant", variant)
      .eq("type", "P")
      .neq("round", "0.1")
      .order("season", { ascending: true })
      .order("date", { ascending: true })
      .range(from, to)
  ).then(({ rows, error }) => (error ? { poGames: [], error } : { poGames: rows, error: null }));
}

// ---------------------------------------------------------------------------
// Team page helpers — everything scoped to ONE team across all seasons.
// Smaller result sets than the all-time versions above (one franchise's
// history, not the whole league's), but still paginated — a 30-season NBA
// team can clear 2,500+ career games, well past Supabase's 1000-row cap
// per request (the same gotcha noted elsewhere: PostgREST silently caps
// there, it doesn't error).
// ---------------------------------------------------------------------------

async function fetchAllRowsForTeam(selectCols, filters) {
  return fetchAllPages((from, to, withCount) => {
    let q = supabase.from("games").select(selectCols, withCount ? { count: "exact" } : undefined);
    for (const [col, val] of Object.entries(filters)) {
      if (Array.isArray(val)) q = q[val[0]](col, val[1]);
      else q = q.eq(col, val);
    }
    return q.order("date", { ascending: true }).range(from, to);
  });
}

// Lightweight — just enough to draw the all-time rating line.
export async function fetchTeamChartPoints(league, teamId, variant) {
  const { rows, error } = await fetchAllRowsForTeam("date, season, post_gm_rate", {
    league,
    team_id: teamId,
    variant,
  });
  if (error) return { points: [], error };
  const points = rows.map((r) => ({
    date: new Date(r.date + "T12:00:00").getTime(),
    season: r.season,
    rating: r.post_gm_rate,
  }));
  return { points, error: null };
}

// Same shape as fetchAllTimeTeamGames, just pre-filtered to one team —
// feeds the same buildAllTimeRows() reducer, so the season-by-season table
// logic isn't duplicated between All-Time Rankings and the Team page.
export async function fetchTeamAllSeasonsGames(league, teamId, variant) {
  return fetchAllRowsForTeam("team_id, season, date, type, post_gm_rate, w, l", {
    league,
    team_id: teamId,
    variant,
  });
}

export async function fetchTeamAllSeasonsPreseasonRatings(league, teamId, variant) {
  const { data, error } = await supabase
    .from("preseason_ratings")
    .select("season, preseason_elo")
    .eq("league", league)
    .eq("team_id", teamId)
    .eq("variant", variant);
  if (error) return { byTeamSeason: {}, error };
  const byTeamSeason = {};
  for (const row of data ?? []) byTeamSeason[`${teamId}-${row.season}`] = row.preseason_elo;
  return { byTeamSeason, error: null };
}

export async function fetchTeamAllSeasonsPlayoffGames(league, teamId, variant) {
  const { rows, error } = await fetchAllRowsForTeam("team_id, season, round, result, date", {
    league,
    team_id: teamId,
    variant,
    type: "P",
    round: ["neq", "0.1"],
  });
  return { poGames: rows, error };
}

// Full-detail game log — every column the Game Log tab renders. Separate
// from fetchTeamAllSeasonsGames (which only pulls the handful of columns
// the season table needs) since this one gets re-fetched on every
// season/type filter change, and there's no reason to drag home_away,
// points, win-prob, etc. through the season-table path where none of it
// is used.
export async function fetchTeamGameLog(league, teamId, variant, { type, season } = {}) {
  const filters = { league, team_id: teamId, variant };
  if (type) filters.type = type;
  if (season) filters.season = season;
  const { rows, error } = await fetchAllRowsForTeam(
    "game_id, date, season, type, round, opponent_id, home_away, points_for, points_against, " +
      "pre_gm_rate, post_gm_rate, expected_win_pct, rating_change, result, ot",
    filters
  );
  return { games: rows.reverse(), error }; // newest-first for display, fetched oldest-first for pagination consistency
}

// Reduces fetchAllTimeTeamGames' raw rows into one row per team-SEASON
// (not one row per team, like buildSeasonStandingsRows) — the All-Time
// page's grain is "how did this team do in this specific season."
export function buildAllTimeRows(rows) {
  const byTeamSeason = {};
  for (const row of rows) {
    const key = `${row.team_id}-${row.season}`;
    const t = (byTeamSeason[key] ??= {
      team_id: row.team_id,
      season: row.season,
      rsW: 0,
      rsL: 0,
      rsRating: null,
      finalRating: null,
    });
    if (row.type === "R") {
      t.rsW += row.w ?? 0;
      t.rsL += row.l ?? 0;
      t.rsRating = row.post_gm_rate;
    }
    t.finalRating = row.post_gm_rate;
  }
  return Object.values(byTeamSeason);
}
