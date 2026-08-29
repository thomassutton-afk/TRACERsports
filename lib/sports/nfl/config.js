/**
 * NFL league config.
 *
 * Team IDs here are each franchise's CURRENT code (LV, LAC, LAR — not
 * the old OAK, SD, STL). As of the NFL rebuild, relocations that
 * genuinely changed the code used in source files (OAK->LV in 2020,
 * SD->LAC in 2017, STL->LAR in 2016, WAS->WFT->WAS in 2020-2021) are
 * tracked via franchise.py's --alias mechanism, and export_to_supabase.py
 * always exports every game/team_history row under the franchise's
 * CURRENT code (see build_games()'s id_to_code lookup) — so the old
 * codes (OAK, SD, STL, WFT) never appear as a team_id in Supabase at
 * all; they only appear in team_history.code for era-correct historical
 * display (see lib/historicalIdentity.js). Matches
 * export_to_supabase.py's ACTIVE_CODES for "nfl" and the actual codes
 * registered in nfl_elo.db.
 *
 * Conferences/divisions reflect the CURRENT (2002-realignment-onward)
 * structure only — same as NBA/WNBA's config, era-correct historical
 * conf/div (e.g. Arizona was NFC East pre-2002, Baltimore/Cincinnati/
 * Cleveland/Pittsburgh were "Central" not "North") is a `team_history`
 * / display_name() concern, not something this static config tracks.
 */

export const nflConfig = {
  id: 'nfl',
  sport: 'football',
  label: 'NFL',
  fullName: 'National Football League',

  // NFL seasons are labeled by the year they START (e.g. the
  // 2025 season runs Sept 2025 - Feb 2026), unlike NBA's split-year
  // label — matches the literal `Season` value used throughout the
  // pipeline's source data and database.
  seasonFormat: 'single-year',
  seasonLabel: (year) => `${year}`,

  hasConferences: true,
  hasDivisions: true,

  // NFL games can end in a genuine tie (rare, but real — happens under
  // current OT rules). StandingsTab.jsx only renders a Ties column and
  // uses the tie-aware win% formula when this is true; basketball
  // leagues leave it unset since a tie is structurally impossible there.
  hasTies: true,

  // A completed game's points_for below this is treated as bad/
  // placeholder data, not a real result — see lib/gamesData.js's
  // pairGameRows(). Real NFL final scores are routinely well under
  // basketball's threshold (a normal "24-17" final would get silently
  // dropped as "bad data" under NBA/WNBA's value of 50) — points_for
  // being null/undefined already independently excludes unplayed
  // games, so this only needs to catch a bad-but-truthy value.
  minValidGameScore: 1,

  conferences: ['AFC', 'NFC'],
  divisions: {
    AFC: {
      East:  ['BUF', 'MIA', 'NE', 'NYJ'],
      North: ['BAL', 'CIN', 'CLE', 'PIT'],
      South: ['HOU', 'IND', 'JAX', 'TEN'],
      West:  ['DEN', 'KC', 'LV', 'LAC'],
    },
    NFC: {
      East:  ['DAL', 'NYG', 'PHI', 'WAS'],
      North: ['CHI', 'DET', 'GB', 'MIN'],
      South: ['ATL', 'CAR', 'NO', 'TB'],
      West:  ['ARI', 'SEA', 'SF', 'LAR'],
    },
  },

  // Playoff format: 7 seeds per conference (4 division winners + 3
  // wild cards), no play-in — the #1 seed in each conference gets a
  // bye through Wild Card weekend, so it's NOT a clean 8-vs-8 bracket
  // the way NBA's conference bracket is. Built as NflBracketTab.jsx
  // (type: 'conference-bracket-bye') rather than reusing BracketTab.jsx —
  // the #1 seed's card just appears directly in the Divisional round as
  // one side of their real game, no placeholder bye slot in Round 1.
  playoffFormat: {
    type: 'conference-bracket-bye',
    autoSeeds: 7,
    playInSeeds: 0,
    roundsPerConference: 3, // Wild Card, Divisional, Conf. Championship, then Super Bowl
    // The 4 division winners get seeds 1-4 regardless of overall
    // record, then the best 3 remaining teams fill 5-7 as wildcards —
    // this is NFL-specific and must stay opt-in, not tied to
    // hasDivisions generally: NBA also hasDivisions=true but dropped
    // this exact rule in 2015-16 (division winners now get zero
    // automatic seeding priority there, only a tiebreaker preference
    // within an already-tied group) — see lib/tiebreakers.js's
    // seedConference() for where this flag is actually read.
    divisionWinnersAutoSeed: true,
    // NFL playoff games are single-elimination (winner-take-all), not a
    // best-of-N series the way NBA/WNBA's are — one win always advances
    // a team, in every round. Keyed by round rank (see gamesData.js's
    // roundRank()/playoffRoundOrder below) for the same lookup shape
    // resolveWinsNeeded() already uses for NBA/WNBA, rather than a
    // special-cased single value.
    winsNeeded: { 1: 1, 2: 1, 3: 1, 4: 1 },
  },

  teams: {
    ARI: { name: 'Arizona Cardinals',     city: 'Glendale',        nickname: 'Cardinals',   conf: 'NFC', div: 'West',  primary: '#9B2743', secondary: '#FFFFFF', tertiary: '#A2AAAD' },
    ATL: { name: 'Atlanta Falcons',       city: 'Atlanta',         nickname: 'Falcons',     conf: 'NFC', div: 'South', primary: '#A6192E', secondary: '#010101', tertiary: '#B2B4B2' },
    BAL: { name: 'Baltimore Ravens',      city: 'Baltimore',       nickname: 'Ravens',      conf: 'AFC', div: 'North', primary: '#010101', secondary: '#24125F', tertiary: '#9A7611' },
    BUF: { name: 'Buffalo Bills',         city: 'Buffalo',         nickname: 'Bills',       conf: 'AFC', div: 'East',  primary: '#003087', secondary: '#C8102E', tertiary: '#FFFFFF' },
    CAR: { name: 'Carolina Panthers',     city: 'Charlotte',       nickname: 'Panthers',    conf: 'NFC', div: 'South', primary: '#101820', secondary: '#0085CA', tertiary: '#B2B4B2' },
    CHI: { name: 'Chicago Bears',         city: 'Chicago',         nickname: 'Bears',       conf: 'NFC', div: 'North', primary: '#091F2C', secondary: '#DC4405', tertiary: '#FFFFFF' },
    CIN: { name: 'Cincinnati Bengals',    city: 'Cincinnati',      nickname: 'Bengals',     conf: 'AFC', div: 'North', primary: '#010101', secondary: '#DC4405', tertiary: '#FFFFFF' },
    CLE: { name: 'Cleveland Browns',      city: 'Cleveland',       nickname: 'Browns',      conf: 'AFC', div: 'North', primary: '#311D00', secondary: '#EB3300', tertiary: '#FFFFFF' },
    DAL: { name: 'Dallas Cowboys',        city: 'Arlington',       nickname: 'Cowboys',     conf: 'NFC', div: 'East',  primary: '#0C2340', secondary: '#87909A', tertiary: '#FFFFFF' },
    DEN: { name: 'Denver Broncos',        city: 'Denver',          nickname: 'Broncos',     conf: 'AFC', div: 'West',  primary: '#FC4C02', secondary: '#0C2340', tertiary: '#FFFFFF' },
    DET: { name: 'Detroit Lions',         city: 'Detroit',         nickname: 'Lions',       conf: 'NFC', div: 'North', primary: '#0069B1', secondary: '#A2AAAD', tertiary: '#FFFFFF' },
    GB:  { name: 'Green Bay Packers',     city: 'Green Bay',       nickname: 'Packers',     conf: 'NFC', div: 'North', primary: '#183029', secondary: '#FFB81C', tertiary: '#FFFFFF' },
    HOU: { name: 'Houston Texans',        city: 'Houston',         nickname: 'Texans',      conf: 'AFC', div: 'South', primary: '#1D1F2A', secondary: '#E4002B', tertiary: '#FFFFFF' },
    IND: { name: 'Indianapolis Colts',    city: 'Indianapolis',    nickname: 'Colts',       conf: 'AFC', div: 'South', primary: '#003A70', secondary: '#FFFFFF', tertiary: '#A2AAAD' },
    JAX: { name: 'Jacksonville Jaguars',  city: 'Jacksonville',    nickname: 'Jaguars',     conf: 'AFC', div: 'South', primary: '#010101', secondary: '#006271', tertiary: '#9A7611' },
    KC:  { name: 'Kansas City Chiefs',    city: 'Kansas City',     nickname: 'Chiefs',      conf: 'AFC', div: 'West',  primary: '#C8102E', secondary: '#FFB81C', tertiary: '#FFFFFF' },
    MIA: { name: 'Miami Dolphins',        city: 'Miami Gardens',   nickname: 'Dolphins',    conf: 'AFC', div: 'East',  primary: '#008C95', secondary: '#FC4C02', tertiary: '#FFFFFF' },
    MIN: { name: 'Minnesota Vikings',     city: 'Minneapolis',     nickname: 'Vikings',     conf: 'NFC', div: 'North', primary: '#582C83', secondary: '#FFC72C', tertiary: '#FFFFFF' },
    NE:  { name: 'New England Patriots',  city: 'Foxborough',      nickname: 'Patriots',    conf: 'AFC', div: 'East',  primary: '#0C2340', secondary: '#C8102E', tertiary: '#A2AAAD' },
    NO:  { name: 'New Orleans Saints',    city: 'New Orleans',     nickname: 'Saints',      conf: 'NFC', div: 'South', primary: '#D3BC8D', secondary: '#010101', tertiary: '#FFFFFF' },
    NYG: { name: 'New York Giants',       city: 'East Rutherford', nickname: 'Giants',      conf: 'NFC', div: 'East',  primary: '#001E62', secondary: '#A6192E', tertiary: '#A2AAAD' },
    NYJ: { name: 'New York Jets',         city: 'East Rutherford', nickname: 'Jets',        conf: 'AFC', div: 'East',  primary: '#115740', secondary: '#FFFFFF', tertiary: '#010101' },
    LV:  { name: 'Las Vegas Raiders',     city: 'Las Vegas',       nickname: 'Raiders',     conf: 'AFC', div: 'West',  primary: '#A7A8A9', secondary: '#010101', tertiary: '#FFFFFF' },
    PHI: { name: 'Philadelphia Eagles',   city: 'Philadelphia',    nickname: 'Eagles',      conf: 'NFC', div: 'East',  primary: '#004851', secondary: '#010101', tertiary: '#545859' },
    PIT: { name: 'Pittsburgh Steelers',   city: 'Pittsburgh',      nickname: 'Steelers',    conf: 'AFC', div: 'North', primary: '#101820', secondary: '#FFB81C', tertiary: '#FFFFFF' },
    LAC: { name: 'Los Angeles Chargers',  city: 'Inglewood',       nickname: 'Chargers',    conf: 'AFC', div: 'West',  primary: '#0072CE', secondary: '#FFB81C', tertiary: '#FFFFFF' },
    SEA: { name: 'Seattle Seahawks',      city: 'Seattle',         nickname: 'Seahawks',    conf: 'NFC', div: 'West',  primary: '#0C2340', secondary: '#A2AAAD', tertiary: '#78BE21' },
    SF:  { name: 'San Francisco 49ers',   city: 'Santa Clara',     nickname: '49ers',       conf: 'NFC', div: 'West',  primary: '#A6192E', secondary: '#AF8C5C', tertiary: '#FFFFFF' },
    LAR: { name: 'Los Angeles Rams',      city: 'Inglewood',       nickname: 'Rams',        conf: 'NFC', div: 'West',  primary: '#1E22AA', secondary: '#FFD100', tertiary: '#FFFFFF' },
    TB:  { name: 'Tampa Bay Buccaneers',  city: 'Tampa',           nickname: 'Buccaneers',  conf: 'NFC', div: 'South', primary: '#A6192E', secondary: '#3D3935', tertiary: '#010101' },
    TEN: { name: 'Tennessee Titans',      city: 'Nashville',       nickname: 'Titans',      conf: 'AFC', div: 'South', primary: '#418FDE', secondary: '#C8102E', tertiary: '#FFFFFF' },
    WAS: { name: 'Washington Commanders', city: 'Landover',        nickname: 'Commanders',  conf: 'NFC', div: 'East',  primary: '#651C32', secondary: '#FFB81C', tertiary: '#010101' },
  },

  // Engine tuning — matches NFL_Elo/engine.py's BASELINE_PARAMS.
  // Reference only: NFL's real per-season params can differ from these
  // via DBs/param_schedule.json (see rebuild.py's variant_params) —
  // these are just the fallback/baseline values, same caveat as
  // NBA/WNBA's single fixed constants not applying here as literally.
  engine: {
    base: 1500,
    alpha: 0.3,           // carry-forward weight for Echo variant (baseline; per-season may differ)
    hfa: 72,               // home-field advantage, Elo points
    kMax: 46,
    kFloor: 36.2,          // floor K decays to by the last game of the regular season
    restMinor: 6,          // 1-4 day rest differential (short week)
    restMajor: 24,         // 6+ day rest differential (bye week+)
    divGameMult: 1.1,
    confGameMult: 1.02,
    poMult: { WC: 1.1, DV: 1.2, CC: 1.35, SB: 1.5 }, // default 1.0
    roundLabels: { RS: 'Reg. Season', WC: 'Wild Card', DV: 'Divisional', CC: 'Conf. Championship', SB: 'Super Bowl' },
    // See nba/config.js's playoffRoundOrder comment. NFL's round values
    // are real text codes (not stringified numbers), so this is what
    // makes champion detection / round-reached badges / All-Time depth
    // filters work at all for NFL — without it, every one of those
    // silently breaks (Number('WC') is NaN), which is what happened
    // before this was added: Season/All-Time/Team pages all rely on
    // gamesData.js functions that assumed round was numeric.
    playoffRoundOrder: ['WC', 'DV', 'CC', 'SB'],
  },
};
