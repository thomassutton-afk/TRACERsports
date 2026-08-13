/**
 * TRACER — Sport/League Registry
 *
 * This is the single source of truth for which leagues are LIVE on the site.
 * Pages, nav, and routing all read from here — adding a league later means
 * adding one entry here + a config file, not touching every page.
 *
 * Do NOT add future leagues (NFL/CFB/CBB/etc.) here until they're ready to
 * ship — this list drives what actually renders in nav/routing.
 */

import { nbaConfig } from './nba/config';
import { wnbaConfig } from './wnba/config';

export const SPORTS = {
  basketball: {
    id: 'basketball',
    label: 'Basketball',
    leagues: ['nba', 'wnba'],
  },
  // football, baseball, hockey, soccer added here when their first league ships
};

export const LEAGUES = {
  nba: nbaConfig,
  wnba: wnbaConfig,
};

export function getLeagueConfig(leagueId) {
  const config = LEAGUES[leagueId];
  if (!config) {
    throw new Error(`Unknown league "${leagueId}". Active leagues: ${Object.keys(LEAGUES).join(', ')}`);
  }
  return config;
}

export function getAllLeagueIds() {
  return Object.keys(LEAGUES);
}

export function getLeaguesForSport(sportId) {
  return SPORTS[sportId]?.leagues.map(id => LEAGUES[id]) ?? [];
}
