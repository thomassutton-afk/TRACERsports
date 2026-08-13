/**
 * WNBA league config.
 *
 * VERIFY BEFORE SHIP:
 * - Team colors below are best-effort from general knowledge, NOT pulled from
 *   official brand guides. Toronto Tempo and Portland Fire are 2026 expansion
 *   teams I have low confidence on — treat their colors as placeholders.
 * - Engine tuning (kMax/kMin/kDecay/hca) is copied from NBA as a starting
 *   point. WNBA plays far fewer games per season (44 in 2026, 50 from 2027
 *   vs NBA's 82), so K-factor decay almost certainly needs separate
 *   backtesting against real WNBA results before this is trustworthy.
 * - Playoff format assumed: top 8 overall (no conference bracket, no
 *   play-in) — confirm this is still current before building BracketTab
 *   equivalent for this league.
 * - Team IDs use NYL (not NY), LAS (not LA), GSV (not GS), and LVA (not LV)
 *   deliberately, to match the 3-letter codes used in the Elo database
 *   source data — kept consistent even where a shorter code would also work.
 * - RESOLVED (Aug 2026): the 5 truly-folded WNBA franchises with no
 *   current-day successor (Charlotte Sting, Cleveland Rockers, Houston
 *   Comets, Sacramento Monarchs, Miami Sol) now have entries below,
 *   marked `folded: true` with `conf: null`. Utah Starzz is NOT one of
 *   these — it relocated and rebranded into the currently-listed Las
 *   Vegas Aces, so its old games need the season-aware display-name fix
 *   (still open, see HANDOFF) rather than a separate config entry here.
 */

export const wnbaConfig = {
  id: 'wnba',
  sport: 'basketball',
  label: 'WNBA',
  fullName: "Women's National Basketball Association",

  // Season plays entirely within one calendar year (May–Oct)
  seasonFormat: 'single-year',
  seasonLabel: (year) => `${year}`,

  hasConferences: true,
  hasDivisions: false,

  conferences: ['East', 'West'],
  divisions: null,

  // Top 8 overall make playoffs regardless of conference — single ladder,
  // not two conference brackets like the NBA. Confirm before building UI.
  playoffFormat: {
    type: 'overall-bracket',
    autoSeeds: 8,
    playInSeeds: 0,
    roundsPerConference: null, // not conference-split
    // Games needed to WIN each round (not the best-of-N length itself) -
    // confirmed by TJ. This is the CURRENT era (2025+) only: Round 1
    // best-of-3, Semis best-of-5, WNBA Finals best-of-7. Used as the
    // fallback for any season winsNeededByEra below doesn't cover.
    winsNeeded: { 1: 2, 2: 3, 3: 4 },
    // tallyPlayoffResults (lib/gamesData.js) uses this to correctly flag
    // champions across every era. Two related fixes went into this:
    //   1. winsNeeded is a plain number per era now, not keyed by round -
    //      "the finals round" is resolved PER SEASON from the actual data
    //      (highest round played that season), not from a fixed round
    //      number, since WNBA's playoff STRUCTURE has changed over time
    //      too, not just series length. 1997 only had 2 real rounds (no
    //      "First Round" existed yet), so that year's championship game
    //      is stored under round=2 - the same number today's Semifinals
    //      uses. A fixed "round 3 = Finals" check would never match 1997
    //      regardless of win count.
    //   2. Applying the CURRENT era's winsNeeded (4, best-of-7) to every
    //      season retroactively was silently marking every pre-2025
    //      champion as "not champion" — only the 2025 Aces, who actually
    //      won a 4-game Finals, passed the old static check.
    // Round 1/Semifinals win totals display as-is regardless of era; this
    // table only ever answers "how many wins to win THE FINALS this
    // season," whatever round number that happened to be that year.
    winsNeededByEra: [
      { fromSeason: 1997, toSeason: 1997, winsNeeded: 1 },
      { fromSeason: 1998, toSeason: 2004, winsNeeded: 2 },
      { fromSeason: 2005, toSeason: 2024, winsNeeded: 3 },
      { fromSeason: 2025, toSeason: null, winsNeeded: 4 },
    ],
  },

  teams: {
    ATL: { name: 'Atlanta Dream',           city: 'Atlanta',       nickname: 'Dream',      conf: 'East', div: null, primary: '#E31837', secondary: '#000000', tertiary: '#C3996B' },
    CHI: { name: 'Chicago Sky',             city: 'Chicago',       nickname: 'Sky',        conf: 'East', div: null, primary: '#418FDE', secondary: '#FFCD00', tertiary: '#00285E' },
    CON: { name: 'Connecticut Sun',         city: 'Uncasville',    nickname: 'Sun',        conf: 'East', div: null, primary: '#FC4C02', secondary: '#0C2340', tertiary: '#FFFFFF' }, // corrected Aug 2026 — 2021 rebrand dropped red; current is Orange/Navy/White (verified via TruColor + Wikipedia)
    IND: { name: 'Indiana Fever',           city: 'Indianapolis',  nickname: 'Fever',      conf: 'East', div: null, primary: '#E03A3E', secondary: '#002D62', tertiary: '#FFC633' },
    NYL: { name: 'New York Liberty',        city: 'New York',      nickname: 'Liberty',    conf: 'East', div: null, primary: '#6ECEB2', secondary: '#000000', tertiary: '#FFFFFF' },
    TOR: { name: 'Toronto Tempo',           city: 'Toronto',       nickname: 'Tempo',      conf: 'East', div: null, primary: '#612C51', secondary: '#B8CCEA', tertiary: '#010101' }, // corrected Aug 2026 — real colors are Bordeaux + Borealis Blue (not purple), confirmed via team's Dec 2025 uniform reveal + TruColor
    WAS: { name: 'Washington Mystics',      city: 'Washington',    nickname: 'Mystics',    conf: 'East', div: null, primary: '#C8102E', secondary: '#0C2340', tertiary: '#8D9093' }, // corrected Aug 2026 — third color is Silver, never gold, in the 2011-present scheme (verified via TruColor)

    DAL: { name: 'Dallas Wings',            city: 'Arlington',     nickname: 'Wings',      conf: 'West', div: null, primary: '#002F6C', secondary: '#C4D600', tertiary: '#B1B3B3' },
    GSV: { name: 'Golden State Valkyries',  city: 'San Francisco', nickname: 'Valkyries',  conf: 'West', div: null, primary: '#AD96DC', secondary: '#000000', tertiary: '#B9975B' }, // corrected Aug 2026 — real "Valkyrie Violet" is a lighter lavender than the dark purple previously here (verified via TruColor)
    LVA: { name: 'Las Vegas Aces',          city: 'Las Vegas',     nickname: 'Aces',       conf: 'West', div: null, primary: '#A7A8A9', secondary: '#010101', tertiary: '#FFFFFF' }, // Black/Silver/White (verified via TruColor); primary/secondary swapped from initial Aug 2026 entry to mirror the Spurs — plain black secondary text reads better than white did
    LAS: { name: 'Los Angeles Sparks',      city: 'Los Angeles',   nickname: 'Sparks',     conf: 'West', div: null, primary: '#702F8A', secondary: '#FFC72C', tertiary: '#000000' },
    MIN: { name: 'Minnesota Lynx',          city: 'Minneapolis',   nickname: 'Lynx',       conf: 'West', div: null, primary: '#236192', secondary: '#78BE21', tertiary: '#9EA2A2' },
    PHX: { name: 'Phoenix Mercury',         city: 'Phoenix',       nickname: 'Mercury',    conf: 'West', div: null, primary: '#582C83', secondary: '#FC4C02', tertiary: '#753BBD' }, // corrected Aug 2026 — team did a full rebrand for the 2026 season (Nov 2025); previous values were the old 2015-2025 scheme. Third color is the new "Psychic Purple" accent (verified via TruColor + ESPN/WNBA.com coverage)
    POR: { name: 'Portland Fire',           city: 'Portland',      nickname: 'Fire',       conf: 'West', div: null, primary: '#C8102E', secondary: '#010101', tertiary: '#E93CAC' }, // corrected Aug 2026 — Pink is the real primary identity color, was missing entirely; Red/Black are the supporting colors (verified via TruColor)
    SEA: { name: 'Seattle Storm',           city: 'Seattle',       nickname: 'Storm',      conf: 'West', div: null, primary: '#2C5234', secondary: '#FEE11A', tertiary: '#003087' },

    // FOLDED FRANCHISES — no current-day successor team_id (unlike the
    // Utah Starzz→Las Vegas Aces / Detroit Shock→Dallas Wings / Orlando
    // Miracle→Connecticut Sun lineages, which resolve to an
    // already-listed active team and need the season-aware
    // display-name fix instead — see HANDOFF for that plan).
    // `conf: null` deliberately, not 'East'/'West' — these teams should
    // never be eligible to match a conference filter (StandingsTab,
    // BracketTab both do exact 'East'/'West' string checks), even
    // defensively/in case a future season-browsing feature ever queries
    // across all seasons instead of just the current one.
    // Colors verified against TruColor's historical franchise records
    // (each team's own final/most complete branding era) — not a
    // placeholder guess.
    // NOTE: no historical logo assets exist for any of these codes.
    // /logos/historical/ is NBA-only right now, and reusing it naively
    // would be actively wrong here — CLE/HOU/SAC/MIA are already
    // claimed by (unrelated) NBA historical logo files under those same
    // codes. TeamMark will fall back to the abbreviation badge for
    // these until real WNBA historical logo assets exist.
    CHA: { name: 'Charlotte Sting',         city: 'Charlotte',     nickname: 'Sting',      conf: null, div: null, primary: '#F9423A', secondary: '#1B365D', tertiary: '#010101', folded: true }, // 1997-2006
    CLE: { name: 'Cleveland Rockers',       city: 'Cleveland',     nickname: 'Rockers',    conf: null, div: null, primary: '#010101', secondary: '#009FDF', tertiary: '#DC4405', folded: true }, // 1997-2003
    HOU: { name: 'Houston Comets',          city: 'Houston',       nickname: 'Comets',     conf: null, div: null, primary: '#BA0C2F', secondary: '#041E42', tertiary: '#8D9093', folded: true }, // 1997-2008
    MIA: { name: 'Miami Sol',               city: 'Miami',         nickname: 'Sol',        conf: null, div: null, primary: '#A6192E', secondary: '#010101', tertiary: '#FB9500', folded: true }, // 2000-2002
    SAC: { name: 'Sacramento Monarchs',     city: 'Sacramento',    nickname: 'Monarchs',   conf: null, div: null, primary: '#753BBD', secondary: '#010101', tertiary: '#BA0C2F', folded: true }, // 1997-2009
  },

  // Engine tuning — STARTING POINT ONLY, needs backtesting against real
  // WNBA results before treated as final (see file header note)
  engine: {
    base: 1500,
    alpha: 0.6,
    hca: 84,
    kMax: 58,
    kMin: 6,
    kDecay: 0.30,   // steeper than NBA's 0.15 since ~44-50 games, not 82 — UNVERIFIED, backtest this
    restScale: 8,
    restCap: 16,
    gamesPlayedCap: 44,
    poMult: { RS: 1.00, 1: 1.10, 2: 1.20, 3: 1.35 }, // no play-in/INS tiers — VERIFY round count
    roundLabels: { RS: 'Reg. Season', '1': 'First Round', '2': 'Semifinals', '3': 'WNBA Finals' },
  },
};
