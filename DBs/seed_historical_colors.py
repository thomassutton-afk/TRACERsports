"""
One-time seed for team_history.{primary,secondary,tertiary}_color.

Only sets colors for eras that DIFFER from a franchise's current identity
(the one already in lib/sports/{league}/config.js) - current eras are left
NULL on purpose, so the frontend's fallback-to-config.js path is what
serves them, same source of truth as everywhere else on the site.

REV 2026-08 - full rewrite. Every value below is sourced from
TruColor.net's official franchise color archive (trucolor.net), cross-
checked against the live team_history row boundaries in nba_elo.db /
wnba_elo.db (confirmed via `franchise.py status`-equivalent query before
writing this). No more VERIFY placeholders - everything here has a real
source. Where a row currently spans MORE than one real color era (because
no relocate-based split exists yet), the DOMINANT/longest sub-era's colors
are used and the row is flagged SPLIT CANDIDATE with the exact
`franchise.py relocate` command to run if/when you want full accuracy.
Each team's "3 colors" were chosen deliberately for visual distinctiveness,
not just the first 3 TruColor happens to list - see individual comments.

USAGE - run from DBs\\ (matches every other pipeline script's convention;
do NOT run from inside DBs\\nba\\ or DBs\\wnba\\, see the Operations Guide's
"working directory is critical" note):

    python3 seed_historical_colors.py --league nba
    python3 seed_historical_colors.py --league wnba

Each targets the TOP-LEVEL db (DBs/nba_elo.db or DBs/wnba_elo.db) - the
one export_to_supabase.py actually reads - not the subfolder working copy.
If you also want the subfolder copy in sync for your next add_season.py
run, follow your normal copy convention afterward.
"""
import argparse
import importlib.util
import os
import sys

# NBA eras. team_id, start_season identify the exact team_history row
# (confirmed against the live db before writing this - see franchise.py
# status). All colors here are for OLD eras only - each of these team_ids'
# CURRENT era (NOP/BRK/OKC/MEM/CHH, and WAS-Wizards - see note below) is
# left NULL, served by config.js.
NBA_COLORS = [
    # --- Seattle SuperSonics (1996-2008) -> Oklahoma City Thunder ---
    # SPLIT CANDIDATE: this single row actually spans 2 real color eras
    # (1995-96 through 2000-01 had a red accent that later dropped; 2001-02
    # through 2007-08 simplified to green/gold/black). Using the later,
    # more-recognized era below. For full accuracy:
    #   python3 franchise.py relocate --current-code SEA --alias SEA --name "Seattle SuperSonics" --season 2001
    #   python3 franchise.py set-colors --current-code SEA --season 1996 --primary "#173F35" --secondary "#9E2B2F" --tertiary "#FFA400"
    # (2001-08 row keeps the values below)
    ("nba_0025", 1996, "#00573F", "#F6BE00", "#010101"),  # Hunter Green / Gold / Black
    # --- Vancouver Grizzlies (1996-2001) -> Memphis Grizzlies ---
    # Only ever had the one identity in this window. Turquoise+Bronze+Red
    # chosen over the also-present Black since they're the 3 colors that
    # actually read as "Grizzlies" on the jersey; black was trim only.
    ("nba_0028", 1996, "#00B2A9", "#8F654D", "#C8102E"),  # Turquoise / Bronze / Red
    # --- New Jersey Nets (1996-2012) -> Brooklyn Nets ---
    # SPLIT CANDIDATE (minor): technically the 1996-97 season alone was
    # still the older Blue #003DA5/Red #E40046 look before the 1997-98
    # navy rebrand. One season - not worth splitting unless you want
    # perfection; using the dominant 1997-2012 era below.
    ("nba_0017", 1996, "#041E42", "#BA0C2F", "#8D9093"),  # Navy / Red / Silver
    # --- Charlotte Hornets, ORIGINAL 1988-2002 era -> New Orleans Hornets ---
    ("nba_0003", 1996, "#00778B", "#280071", "#F9423A"),  # Teal / Purple / Warm Red
    # --- New Orleans Hornets 2003-2005 ---
    # CONFIRMED: purple was NOT dropped on the Charlotte->NOLA move (earlier
    # web research got this backwards) - the look carried over unchanged
    # from Charlotte until the 2008-09 Creole Blue rebrand below.
    ("nba_0003", 2003, "#00778B", "#280071", "#FFC72C"),  # Teal / Purple / Gold
    # --- New Orleans/Oklahoma City Hornets 2006-2007 (dual-market season) ---
    # Same look as 2003-2005 and 2007-08, unchanged.
    ("nba_0003", 2006, "#00778B", "#280071", "#FFC72C"),  # Teal / Purple / Gold
    # --- New Orleans Hornets 2008-2013 ---
    # Full rebrand, post-Katrina-recovery city branding push.
    ("nba_0003", 2008, "#0082BA", "#211747", "#FFC72C"),  # Creole Blue / Dark Purple / Mardi Gras Gold
    # --- Charlotte Bobcats (2005-2014) -> Charlotte Hornets (2015-present) ---
    # SPLIT CANDIDATE: this is the team you originally asked the split-era
    # question about - it's a great candidate. This single row spans 3 real
    # eras: 2004-07 (Warm Red/Bobcats Blue), 2007-12 (Bobcats Blue/Orange -
    # used below, the longest and most-recognized), 2012-14 (Navy/Light
    # Blue/Orange). For the full 3-way split:
    #   python3 franchise.py relocate --current-code CHB --alias CHB --name "Charlotte Bobcats" --season 2007
    #   python3 franchise.py relocate --current-code CHB --alias CHB --name "Charlotte Bobcats" --season 2012
    #   python3 franchise.py set-colors --current-code CHB --season 2005 --primary "#F9423A" --secondary "#1B365D" --tertiary "#8D9093"
    #   python3 franchise.py set-colors --current-code CHB --season 2012 --primary "#0C2340" --secondary "#418FDE" --tertiary "#E35205"
    ("nba_0030", 2005, "#1B365D", "#E35205", "#8D9093"),  # Bobcats Blue / Orange / Silver
    # --- Washington Bullets (1996-1997) -> Washington Wizards ---
    ("nba_0029", 1996, "#D50032", "#003DA5", "#FFFFFF"),  # Red / Blue / White
    # --- Washington Wizards (1998-present) - INTENTIONALLY NOT SET ---
    # This row currently spans 1998-2011 (Slate Blue/Black/Bronze-or-Gold)
    # AND 2011-present (Red/Navy/Silver, presumably what config.js already
    # has). Left NULL rather than guessing wrong for 13 years of one era or
    # the other - split this one before setting colors:
    #   python3 franchise.py relocate --current-code WAS --alias WAS --name "Washington Wizards" --season 2011
    #   python3 franchise.py set-colors --current-code WAS --season 1998 --primary "#236192" --secondary "#010101" --tertiary "#896C4C"
    # (2011-present row stays NULL, served by config.js as normal)
]

# WNBA eras - only the franchises that relocated/renamed but are STILL
# ACTIVE need this (their current era already covered by config.js). The
# truly-folded teams (Sting/Rockers/Comets/Monarchs/Sol) only ever had one
# identity each, so their config.js entries alone are the complete picture.
WNBA_COLORS = [
    # --- Utah Starzz (1997-2002) -> ... -> Las Vegas Aces ---
    # TruColor lists 4 colors (Green/Purple/Light Blue/Copper); Copper
    # dropped here since Green/Purple/Light Blue are the 3 that actually
    # define the look on the jersey.
    ("wnba_0008", 1997, "#006271", "#753BBD", "#00A9E0"),  # Green / Purple / Light Blue
    # --- San Antonio Silver Stars (2003-2013) ---
    ("wnba_0008", 2003, "#010101", "#8D9093", "#FFFFFF"),  # Black / Silver / White
    # --- San Antonio Stars (2014-2017, dropped "Silver") ---
    # Confirmed same palette carried through, no color change alongside
    # the name shortening.
    ("wnba_0008", 2014, "#010101", "#8D9093", "#FFFFFF"),  # Black / Silver / White
    # --- Detroit Shock (1998-2009) -> Tulsa Shock -> Dallas Wings ---
    # SPLIT CANDIDATE: spans 2 real eras (1998-2001 Black/Yellow/Green/Red,
    # 2002-2009 Blue/Dark Blue/Red - used below, the longer of the two).
    #   python3 franchise.py relocate --current-code DET --alias DET --name "Detroit Shock" --season 2002
    #   python3 franchise.py set-colors --current-code DET --season 1998 --primary "#010101" --secondary "#FFA400" --tertiary "#006271"
    ("wnba_0009", 1998, "#003DA5", "#041E42", "#D50032"),  # Blue / Dark Blue / Red
    # --- Tulsa Shock (2010-2015) ---
    ("wnba_0009", 2010, "#FFB81C", "#010101", "#A6192E"),  # Yellow / Black / Dark Red
    # --- Orlando Miracle (1999-2002) -> Connecticut Sun ---
    # Quick Silver dropped in favor of Orange - the 3 below are what
    # actually reads as distinctive; silver is closer to a neutral trim.
    ("wnba_0012", 1999, "#0057B7", "#010101", "#DC4405"),  # Miracle Blue / Black / Orange
    # --- Portland Fire (2000-2025 row only - NOT the 2026 revival row) ---
    # NOTE: you mentioned already manually editing Portland Fire's colors
    # in a prior session, but the live db currently shows NULL for this
    # row - so either that edit didn't make it into this db snapshot, or
    # got reverted. DOUBLE-CHECK before running this seed script for WNBA
    # - if you already have different intentional values live, this will
    # overwrite them.
    ("wnba_0015", 2000, "#C8102E", "#010101", "#896C4C"),  # Red / Black / Gold
    # --- Portland Fire (2026-present revival) - INTENTIONALLY NOT SET ---
    # Brand new revival, no color research done on this one yet - it's a
    # genuinely new question, not a historical-accuracy one. Left NULL.
]


def load_db_module(league: str):
    path = os.path.join(os.path.dirname(__file__), league, "db.py")
    spec = importlib.util.spec_from_file_location(f"{league}_db", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--league", required=True, choices=["nba", "wnba"])
    args = p.parse_args()

    db = load_db_module(args.league)
    db_path = os.path.join(os.path.dirname(__file__), f"{args.league}_elo.db")
    if not os.path.exists(db_path):
        print(f"Expected top-level db at {db_path} - not found. Run this from DBs\\, "
              f"not from inside DBs\\{args.league}\\.")
        sys.exit(1)

    conn = db.connect(db_path)
    rows = NBA_COLORS if args.league == "nba" else WNBA_COLORS

    applied, skipped = 0, 0
    for team_id, start_season, primary, secondary, tertiary in rows:
        ok = db.set_era_colors(conn, team_id, start_season, primary, secondary, tertiary)
        if ok:
            applied += 1
        else:
            skipped += 1
            print(f"  SKIPPED: no {team_id} era starts at {start_season} in this db - "
                  f"check 'franchise.py status' if this is unexpected.")
    conn.commit()
    print(f"{args.league}: applied {applied}, skipped {skipped} (of {len(rows)} total).")


if __name__ == "__main__":
    main()
