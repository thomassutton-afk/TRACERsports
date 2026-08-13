/**
 * historicalIdentity.js — season-aware franchise identity + historical logos.
 *
 * Generalizes the old site's hand-maintained, NBA-only DISPLAY_IDENTITIES/
 * FRANCHISE_ABBRS maps (reference/old-site/AllTimeRankings.jsx et al.) into
 * something driven by the real `team_history` table (exported from each
 * league's local team_history table — see export_to_supabase.py's
 * build_team_history()) instead of a hardcoded list someone has to
 * remember to update. Works for any league that has relocation/rename
 * history, not just NBA (e.g. WNBA's Utah Starzz -> San Antonio -> Las
 * Vegas Aces).
 *
 * Used by the All-Time Rankings and Team pages — anywhere a specific
 * season's row needs to show the identity that was actually true THEN
 * (name, abbreviation, logo), not today's.
 */

import { supabase } from "@/lib/supabase";

// One row per team, sorted oldest-first: [{ code, name, start_season,
// end_season, primary, secondary, tertiary }, ...]. end_season === null
// means "current" (still that identity today). primary/secondary/tertiary
// are frequently null — most eras don't have colors backfilled yet (see
// DBs/seed_historical_colors.py) — callers fall back to the current
// team's colors from config.js in that case, same as the name/code
// fallback in getDisplayIdentity below.
export async function fetchTeamHistory(league) {
  const { data, error } = await supabase
    .from("team_history")
    .select("team_id, code, name, start_season, end_season, primary_color, secondary_color, tertiary_color")
    .eq("league", league)
    .order("start_season", { ascending: true });

  if (error) return { byTeam: {}, error };

  const byTeam = {};
  for (const row of data ?? []) {
    (byTeam[row.team_id] ??= []).push({
      code: row.code,
      name: row.name,
      start_season: row.start_season,
      end_season: row.end_season,
      primary: row.primary_color,
      secondary: row.secondary_color,
      tertiary: row.tertiary_color,
    });
  }
  return { byTeam, error: null };
}

// { code, name, primary, secondary, tertiary } that was true for team_id
// during `season`. Falls back to the league config's current name/code/
// colors when there's no history data for that team (expected for most
// teams — this table only has rows for franchises that actually
// relocated/renamed) or the season predates whatever history rows exist,
// OR when a matched era simply has no colors backfilled yet (primary/
// secondary/tertiary null on that row) — colors fall back independently
// of name/code, since one can be known while the other isn't.
export function getDisplayIdentity(teamId, season, historyByTeam, leagueConfig) {
  const eras = historyByTeam[teamId];
  const currentTeam = leagueConfig.teams[teamId];
  const fallback = {
    code: teamId,
    name: currentTeam?.name ?? teamId,
    primary: currentTeam?.primary,
    secondary: currentTeam?.secondary,
    tertiary: currentTeam?.tertiary,
  };

  if (!eras || eras.length === 0) return fallback;

  for (const era of eras) {
    if (season <= (era.end_season ?? Infinity)) {
      return {
        code: era.code,
        name: era.name,
        primary: era.primary ?? fallback.primary,
        secondary: era.secondary ?? fallback.secondary,
        tertiary: era.tertiary ?? fallback.tertiary,
      };
    }
  }
  return fallback;
}

// ---------------------------------------------------------------------------
// Historical logo index — scans public/logos/historical/{CODE}_{year}.png
// via /api/logo-index. Same file-driven approach as the old site (no
// manual manifest to maintain — drop a file in, it shows up), just backed
// by real team_history segments instead of a hardcoded per-team list.
// ---------------------------------------------------------------------------

const _logoIndexCache = {};
const _logoIndexPromises = {};

// Cached per league. Files live under a per-league subfolder
// (public/logos/historical/{league}/) specifically to avoid abbreviation
// collisions between leagues (DAL/DET/ORL/UTA and others exist in both
// NBA and WNBA) — see app/api/logo-index/route.js.
export function fetchLogoIndex(league) {
  if (_logoIndexCache[league]) return Promise.resolve(_logoIndexCache[league]);
  if (_logoIndexPromises[league]) return _logoIndexPromises[league];
  _logoIndexPromises[league] = fetch(`/api/logo-index?league=${league}`)
    .then((r) => r.json())
    .then((data) => {
      _logoIndexCache[league] = data;
      return data;
    })
    .catch(() => ({})); // no index route / no historical folder yet — degrade gracefully
  return _logoIndexPromises[league];
}

// Historical logo files (public/logos/historical/{league}/{code}_{year}.png)
// are named after the REAL code for that era/team - the same code that
// shows up in team_history and leagueConfig.teams (e.g. NJN_1996.png,
// NOH_2003.png, CHH_2015.png) - so no code translation is needed here.
// (This used to alias a handful of codes to the old site's shorter
// filename convention - GS/NO/NJ/SA/CHA - but those files were renamed to
// match the real codes directly; the alias map just wasn't removed after,
// which meant every one of those lookups was quietly redirected to a
// bucket that no longer existed. Deleted rather than left empty, since an
// alias map with nothing in it invites the same drift again later.)

// Picks the best-matching historical logo file for team_id + season, given
// team_history's real era segments and the /api/logo-index manifest.
// Mirrors the old site's resolveHistoricalLogoPath exactly, just fed real
// segments instead of the hand-typed FRANCHISE_ABBRS table. Returns null
// (not a guess) when nothing matches — caller falls back to the current
// logo / abbreviation badge, same as every other missing-asset case.
//
// Takes `league` because the actual files live under a per-league
// subfolder (public/logos/historical/{league}/{code}_{year}.png) — that
// split happened after this function was first written (to keep NBA/WNBA
// abbreviation collisions like DAL/DET/ORL/UTA from resolving to the
// wrong league's logo), so the URL has to include it too, not just the
// index lookup in fetchLogoIndex above.
export function resolveHistoricalLogoPath(teamId, season, historyByTeam, logoIndex, league) {
  const eras = historyByTeam[teamId];
  // No history rows for this team at all -> it's never had a different
  // identity, so its "historical" logo IS just its current one, filed
  // under its own code with no year cap.
  const segments = eras && eras.length > 0
    ? eras.map((e) => ({ code: e.code, maxYear: e.end_season ?? Infinity }))
    : [{ code: teamId, maxYear: Infinity }];

  let bestFile = null;
  let bestYear = -1;

  for (const { code, maxYear } of segments) {
    const cap = Math.min(season, maxYear);
    const years = logoIndex?.[code] ?? [];
    for (const year of years) {
      if (year <= cap && year > bestYear) {
        bestYear = year;
        bestFile = `/logos/historical/${league}/${code}_${year}.png`;
      }
    }
  }

  return bestFile;
}
