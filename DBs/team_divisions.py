"""
Conference/division lookup used only for tiebreaker math in export_to_supabase.py.

Source of truth for this data is really lib/sports/{league}/config.js (the
frontend's `teams` map, `conf`/`div` fields). It's duplicated here in Python
form because export_to_supabase.py needs it too, and parsing a .js file from
a Python script is fragile. If a division/conference ever changes (expansion,
realignment — rare), update both this file and the matching config.js.
"""

LEAGUE_HAS_DIVISIONS = {
    "nba": True,
    "wnba": False,
}

LEAGUE_HAS_CONFERENCES = {
    "nba": True,
    "wnba": True,
}

# league -> team_id (code) -> (conference, division)
# division is None for leagues without divisions (e.g. WNBA) or for teams
# with no current conference (e.g. folded WNBA franchises — never relevant
# to tiebreakers since they don't appear in a current season).
TEAM_CONF_DIV = {
    "nba": {
        "ATL": ("East", "Southeast"),
        "BOS": ("East", "Atlantic"),
        "BRK": ("East", "Atlantic"),
        "CHH": ("East", "Southeast"),
        "CHI": ("East", "Central"),
        "CLE": ("East", "Central"),
        "DAL": ("West", "Southwest"),
        "DEN": ("West", "Northwest"),
        "DET": ("East", "Central"),
        "GSW": ("West", "Pacific"),
        "HOU": ("West", "Southwest"),
        "IND": ("East", "Central"),
        "LAC": ("West", "Pacific"),
        "LAL": ("West", "Pacific"),
        "MEM": ("West", "Southwest"),
        "MIA": ("East", "Southeast"),
        "MIL": ("East", "Central"),
        "MIN": ("West", "Northwest"),
        "NOP": ("West", "Southwest"),
        "NYK": ("East", "Atlantic"),
        "OKC": ("West", "Northwest"),
        "ORL": ("East", "Southeast"),
        "PHI": ("East", "Atlantic"),
        "PHX": ("West", "Pacific"),
        "POR": ("West", "Northwest"),
        "SAS": ("West", "Southwest"),
        "SAC": ("West", "Pacific"),
        "TOR": ("East", "Atlantic"),
        "UTA": ("West", "Northwest"),
        "WAS": ("East", "Southeast"),
    },
    "wnba": {
        "ATL": ("East", None),
        "CHI": ("East", None),
        "CON": ("East", None),
        "IND": ("East", None),
        "NYL": ("East", None),
        "TOR": ("East", None),
        "WAS": ("East", None),
        "DAL": ("West", None),
        "GSV": ("West", None),
        "LVA": ("West", None),
        "LAS": ("West", None),
        "MIN": ("West", None),
        "PHX": ("West", None),
        "POR": ("West", None),
        "SEA": ("West", None),
    },
}


def conf_div(league, team_id):
    """Returns (conference, division) for a team, or (None, None) if unknown."""
    return TEAM_CONF_DIV.get(league, {}).get(team_id, (None, None))
