/**
 * NBA league config.
 * Ported 1:1 from the old Dashboard.jsx/SeasonPage.jsx/TeamPage.jsx TEAM_* objects.
 *
 * Team IDs NYK, GSW, SAS, NOP, and CHH (not the shorter NY/GS/SA/NO/CHA
 * used on the old site) to match the codes used in the Elo database
 * source data. CHH specifically: the *current* Charlotte Hornets
 * (formerly the Bobcats, renamed 2015) needed a code distinct from CHA,
 * since CHA was already the original 1996-2002 Charlotte Hornets — the
 * franchise that relocated and is now the New Orleans Pelicans (NOP).
 * Two different franchises have both been "the Charlotte Hornets" at
 * different points in NBA history.
 */

export const nbaConfig = {
  id: 'nba',
  sport: 'basketball',
  label: 'NBA',
  fullName: 'National Basketball Association',

  // Season runs across a calendar-year boundary (Oct–June); "season" = the
  // year the season ENDS in, e.g. season 2026 = the 2025–26 season.
  seasonFormat: 'split-year',
  seasonLabel: (year) => `${year - 1}\u2013${String(year).slice(2)}`,

  hasConferences: true,
  hasDivisions: true,

  conferences: ['East', 'West'],
  divisions: {
    East: {
      Atlantic:  ['BOS', 'BRK', 'NYK', 'PHI', 'TOR'],
      Central:   ['CHI', 'CLE', 'DET', 'IND', 'MIL'],
      Southeast: ['ATL', 'CHH', 'MIA', 'ORL', 'WAS'],
    },
    West: {
      Northwest: ['DEN', 'MIN', 'OKC', 'POR', 'UTA'],
      Pacific:   ['GSW', 'LAC', 'LAL', 'PHX', 'SAC'],
      Southwest: ['DAL', 'HOU', 'MEM', 'NOP', 'SAS'],
    },
  },

  // Playoff format: conference-bracketed, 6 auto seeds + 4-team play-in per conference
  playoffFormat: {
    type: 'conference-bracket',
    autoSeeds: 6,
    playInSeeds: 4,
    roundsPerConference: 3, // R1, Conf Semis, Conf Finals, then Finals
  },

  teams: {
    ATL: { name: 'Atlanta Hawks',          city: 'Atlanta',       nickname: 'Hawks',        conf: 'East', div: 'Southeast', primary: '#C8102E', secondary: '#FDB927', tertiary: '#FFFFFF' },
    BOS: { name: 'Boston Celtics',         city: 'Boston',        nickname: 'Celtics',      conf: 'East', div: 'Atlantic',  primary: '#007A33', secondary: '#FFFFFF', tertiary: '#BA9653' },
    BRK: { name: 'Brooklyn Nets',          city: 'Brooklyn',      nickname: 'Nets',         conf: 'East', div: 'Atlantic',  primary: '#000000', secondary: '#FFFFFF', tertiary: '#707372' },
    CHH: { name: 'Charlotte Hornets',      city: 'Charlotte',     nickname: 'Hornets',      conf: 'East', div: 'Southeast', primary: '#00778B', secondary: '#1D1160', tertiary: '#FFFFFF' },
    CHI: { name: 'Chicago Bulls',          city: 'Chicago',       nickname: 'Bulls',        conf: 'East', div: 'Central',   primary: '#CE1141', secondary: '#000000', tertiary: '#FFFFFF' },
    CLE: { name: 'Cleveland Cavaliers',    city: 'Cleveland',     nickname: 'Cavaliers',    conf: 'East', div: 'Central',   primary: '#860038', secondary: '#B9975B', tertiary: '#000000' },
    DAL: { name: 'Dallas Mavericks',       city: 'Dallas',        nickname: 'Mavericks',    conf: 'West', div: 'Southwest', primary: '#0050B5', secondary: '#B8C4CA', tertiary: '#9EA2A2' },
    DEN: { name: 'Denver Nuggets',         city: 'Denver',        nickname: 'Nuggets',      conf: 'West', div: 'Northwest', primary: '#0E2240', secondary: '#FEC524', tertiary: '#8B2131' },
    DET: { name: 'Detroit Pistons',        city: 'Detroit',       nickname: 'Pistons',      conf: 'East', div: 'Central',   primary: '#1D42BA', secondary: '#C8102E', tertiary: '#FFFFFF' },
    GSW: { name: 'Golden State Warriors',  city: 'San Francisco', nickname: 'Warriors',     conf: 'West', div: 'Pacific',   primary: '#1D428A', secondary: '#FFC72C', tertiary: '#FFFFFF' },
    HOU: { name: 'Houston Rockets',        city: 'Houston',       nickname: 'Rockets',      conf: 'West', div: 'Southwest', primary: '#CE1141', secondary: '#000000', tertiary: '#C4CED4' },
    IND: { name: 'Indiana Pacers',         city: 'Indianapolis',  nickname: 'Pacers',       conf: 'East', div: 'Central',   primary: '#002D62', secondary: '#FDBB30', tertiary: '#FFFFFF' },
    LAC: { name: 'LA Clippers',            city: 'Los Angeles',   nickname: 'Clippers',     conf: 'West', div: 'Pacific',   primary: '#0C2340', secondary: '#C8102E', tertiary: '#FFFFFF' },
    LAL: { name: 'Los Angeles Lakers',     city: 'Los Angeles',   nickname: 'Lakers',       conf: 'West', div: 'Pacific',   primary: '#552583', secondary: '#FDB927', tertiary: '#000000' },
    MEM: { name: 'Memphis Grizzlies',      city: 'Memphis',       nickname: 'Grizzlies',    conf: 'West', div: 'Southwest', primary: '#5D76A9', secondary: '#F5B112', tertiary: '#12173F' },
    MIA: { name: 'Miami Heat',             city: 'Miami',         nickname: 'Heat',         conf: 'East', div: 'Southeast', primary: '#98002E', secondary: '#F9A01B', tertiary: '#000000' },
    MIL: { name: 'Milwaukee Bucks',        city: 'Milwaukee',     nickname: 'Bucks',        conf: 'East', div: 'Central',   primary: '#00471B', secondary: '#EEE1C6', tertiary: '#000000' },
    MIN: { name: 'Minnesota Timberwolves', city: 'Minneapolis',   nickname: 'Timberwolves', conf: 'West', div: 'Northwest', primary: '#236192', secondary: '#78BE21', tertiary: '#0C2340' },
    NOP: { name: 'New Orleans Pelicans',   city: 'New Orleans',   nickname: 'Pelicans',     conf: 'West', div: 'Southwest', primary: '#0C2340', secondary: '#B9975B', tertiary: '#C8102E' },
    NYK: { name: 'New York Knicks',        city: 'New York',      nickname: 'Knicks',       conf: 'East', div: 'Atlantic',  primary: '#1D4289', secondary: '#FF8200', tertiary: '#FFFFFF' },
    OKC: { name: 'Oklahoma City Thunder',  city: 'Oklahoma City', nickname: 'Thunder',      conf: 'West', div: 'Northwest', primary: '#0072CE', secondary: '#F9423A', tertiary: '#FFB81C' },
    ORL: { name: 'Orlando Magic',          city: 'Orlando',       nickname: 'Magic',        conf: 'East', div: 'Southeast', primary: '#0050B5', secondary: '#000000', tertiary: '#9EA2A2' },
    PHI: { name: 'Philadelphia 76ers',     city: 'Philadelphia',  nickname: '76ers',        conf: 'East', div: 'Atlantic',  primary: '#006BB6', secondary: '#ED174C', tertiary: '#FFFFFF' },
    PHX: { name: 'Phoenix Suns',           city: 'Phoenix',       nickname: 'Suns',         conf: 'West', div: 'Pacific',   primary: '#1D1160', secondary: '#E56020', tertiary: '#FFFFFF' },
    POR: { name: 'Portland Trail Blazers', city: 'Portland',      nickname: 'Trail Blazers',conf: 'West', div: 'Northwest', primary: '#E03A3E', secondary: '#000000', tertiary: '#FFFFFF' },
    SAS: { name: 'San Antonio Spurs',      city: 'San Antonio',   nickname: 'Spurs',        conf: 'West', div: 'Southwest', primary: '#9EA2A2', secondary: '#000000', tertiary: '#FFFFFF' },
    SAC: { name: 'Sacramento Kings',       city: 'Sacramento',    nickname: 'Kings',        conf: 'West', div: 'Pacific',   primary: '#5A2D81', secondary: '#FFFFFF', tertiary: '#707372' },
    TOR: { name: 'Toronto Raptors',        city: 'Toronto',       nickname: 'Raptors',      conf: 'East', div: 'Atlantic',  primary: '#BA0C2F', secondary: '#000000', tertiary: '#FFFFFF' },
    UTA: { name: 'Utah Jazz',              city: 'Salt Lake City',nickname: 'Jazz',         conf: 'West', div: 'Northwest', primary: '#330072', secondary: '#FFFFFF', tertiary: '#000000' },
    WAS: { name: 'Washington Wizards',     city: 'Washington',    nickname: 'Wizards',      conf: 'East', div: 'Southeast', primary: '#E31837', secondary: '#002B5C', tertiary: '#9EA2A2' },
  },

  // Engine tuning — matches continelo_engine.py constants
  engine: {
    base: 1500,
    alpha: 0.6,          // carry-forward weight for Echo variant
    hca: 84,              // home-court advantage, Elo points
    kMax: 58,
    kMin: 6,
    kDecay: 0.15,
    restScale: 8,
    restCap: 16,
    gamesPlayedCap: 82,
    poMult: { RS: 1.00, INS: 1.02, 0.5: 1.05, 1: 1.10, 2: 1.20, 3: 1.35, 4: 1.50 },
    // '0.1' (not the old 'INS' string) — export_to_supabase.py's format_round()
    // stringifies the source REAL round column, and in-season tournament games
    // are stored as round=0.1 there, not the literal text 'INS'.
    roundLabels: { RS: 'Reg. Season', '0.5': 'Play-In', '0.1': 'In-Season Tourn.', '1': 'Round 1', '2': 'Conf. Semis', '3': 'Conf. Finals', '4': 'NBA Finals' },
  },
};
