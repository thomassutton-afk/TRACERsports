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
do NOT run from inside DBs\\nba\\, DBs\\wnba\\, or DBs\\nfl\\, see the
Operations Guide's "working directory is critical" note):

    python3 seed_historical_colors.py --league nba
    python3 seed_historical_colors.py --league wnba
    python3 seed_historical_colors.py --league nfl

Each targets the TOP-LEVEL db (DBs/nba_elo.db, DBs/wnba_elo.db, or
DBs/nfl_elo.db) - the one export_to_supabase.py actually reads - not the
subfolder working copy. If you also want the subfolder copy in sync for
your next add_season.py run, follow your normal copy convention afterward.

NFL note: run split_color_eras.py --league nfl FIRST - NFL_COLORS below
targets team_history rows that only exist after that script creates them
(same NBA_CURRENT30_COLORS dependency as above, now true for NFL too).
NFL's current (most recent, still-open) era per team was written directly
into lib/sports/nfl/config.js instead of left for a later "confirm this
matches config.js" pass - TJ confirmed the TruColor doc is now the site's
source of truth for NFL colors, current era included, so config.js itself
was updated to TruColor's current-era values rather than the NBA/WNBA
pattern of only ever touching config.js's colors in a separate, deferred
decision.
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
    # --- Seattle SuperSonics era 1 (1996-2001) ---
    # Now split from era 2 via NBA_RELOCATED_ADDITIONAL_SPLITS in
    # split_color_eras.py. Forest Green/Brick Red/Deep Yellow per TJ.
    ("nba_0025", 1996, "#173F35", "#9E2B2F", "#FFA400"),  # Forest Green / Brick Red / Deep Yellow
    # --- Seattle SuperSonics era 2 (2002-2008) -> Oklahoma City Thunder ---
    # Tertiary corrected to White per TJ (was Black).
    ("nba_0025", 2002, "#00573F", "#F6BE00", "#FFFFFF"),  # Hunter Green / Gold / White
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
    # Per TJ: exact TruColor hex for the 95-96 (1990-91 through 1996-97
    # era per TruColor) Nets - Blue #003DA5 / Red #E40046 / White. My
    # earlier guess (keeping the existing Navy/Red) was wrong on both
    # primary and secondary, just happened to be close on hue.
    ("nba_0017", 1996, "#003DA5", "#E40046", "#FFFFFF"),  # Blue / Red / White
    # --- Charlotte Hornets, ORIGINAL 1988-2002 era -> New Orleans Hornets ---
    ("nba_0003", 1996, "#00778B", "#280071", "#F9423A"),  # Teal / Purple / Warm Red
    # --- New Orleans Hornets 2003-2005 ---
    # CONFIRMED: purple was NOT dropped on the Charlotte->NOLA move (earlier
    # web research got this backwards) - the look carried over unchanged
    # from Charlotte until the 2008-09 Creole Blue rebrand below.
    # Per TJ: secondary/tertiary (yellow/purple) swapped across this whole
    # 2003-2013 span (all 3 rows below).
    ("nba_0003", 2003, "#00778B", "#FFC72C", "#280071"),  # Teal / Gold / Purple
    # --- New Orleans/Oklahoma City Hornets 2006-2007 (dual-market season) ---
    # Same look as 2003-2005 and 2007-08, unchanged.
    ("nba_0003", 2006, "#00778B", "#FFC72C", "#280071"),  # Teal / Gold / Purple
    # --- New Orleans Hornets 2008-2013 ---
    # Full rebrand, post-Katrina-recovery city branding push.
    ("nba_0003", 2008, "#0082BA", "#FFC72C", "#211747"),  # Creole Blue / Mardi Gras Gold / Dark Purple
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
    # --- Washington Wizards (1998-present) ---
    # Bullets/Wizards rename split (1996/1998) only - the color-only split
    # within the Wizards row (1998-2011 vs 2012-present) is handled in
    # NBA_CURRENT30_COLORS below, now that split_color_eras.py has created
    # that row.
]

# NBA eras for franchises that have NEVER relocated or renamed (same code,
# same name, since at least 1996) but DID have real color/logo changes.
# These rows didn't exist until split_color_eras.py ran - see that script
# for the season-numbering methodology (every "Recommended" shorthand year
# in the doc needs +1 to become the correct start_season; this list already
# has that applied, do not re-derive from the doc's shorthand directly).
# Same rule as above: each team's CURRENT (most recent, still-open) era is
# intentionally left unset here, served by config.js as the single source
# of truth. "3 colors" are a deliberate visual-distinctiveness pick out of
# whatever TruColor listed (sometimes 4-6) - see individual comments.
NBA_CURRENT30_COLORS = [
    # --- Atlanta Hawks ---
    # Per TJ: secondary/tertiary (yellow/black) swapped for 1996-2007;
    # secondary/tertiary (red/silver) swapped for 2008-2015.
    ("nba_0001", 1996, "#C8102E", "#FFC72C", "#010101"),  # Red / Yellow / Black
    ("nba_0001", 2008, "#0C2340", "#B1B3B3", "#C8102E"),  # Navy / Silver / Red
    ("nba_0001", 2016, "#C8102E", "#25282A", "#C4D600"),  # Torch Red / Granite Gray / Volt Green
    # 2021-present intentionally left NULL

    # --- Cleveland Cavaliers ---
    # 1996 era start uses the doc's documented 1994-95 date (TJ flagged
    # 1997 from memory, likely tracking the Shawn Kemp trade's visibility,
    # not the actual color change - doc's date used here, override if you
    # find a source confirming 1997).
    ("nba_0005", 1996, "#010101", "#5C88DA", "#E35205"),  # Black / Blue / Orange
    ("nba_0005", 2004, "#9D2235", "#8C714C", "#041E42"),  # Wine / Metallic Gold / Navy
    ("nba_0005", 2011, "#6F263D", "#FFB81C", "#041E42"),  # Wine / Gold / Navy
    # 2023-present intentionally left NULL

    # --- Dallas Mavericks ---
    ("nba_0006", 1996, "#002855", "#00843D", "#FFFFFF"),  # Blue / Green / White
    ("nba_0006", 2002, "#041E42", "#0057B7", "#8D9093"),  # Navy / Light Royal / Silver
    # 2018-present intentionally left NULL

    # --- Denver Nuggets ---
    ("nba_0007", 1996, "#041E42", "#9D2235", "#896C4C"),  # Navy / Red / Metallic Gold
    # Per TJ: secondary/tertiary (yellow/dark blue) swapped for 2004-2018.
    ("nba_0007", 2004, "#418FDE", "#FFC72C", "#041E42"),  # Light Blue / Yellow Gold / Navy
    # 2019-present intentionally left NULL

    # --- Detroit Pistons ---
    # Per TJ: 95-96 season is its own era, still Blue/Red/White - I had
    # wrongly merged this single season into the Teal Era below (my own
    # +1-rule slip, not a doc issue). No exact hex given for this one -
    # using Blue #1D42BA (matches the blue already used in NBA_CURRENT's
    # Pistons entry) / Red #C8102E / White. Flag if you had different
    # values in mind.
    ("nba_0008", 1996, "#1D42BA", "#C8102E", "#FFFFFF"),  # Blue / Red / White
    ("nba_0008", 1997, "#006271", "#9D2235", "#FFA400"),  # Green ("Teal Era") / Red / Yellow
    ("nba_0008", 2002, "#003DA5", "#D50032", "#8D9093"),  # Royal Blue / Red / Silver
    # 2021-present intentionally left NULL

    # --- Golden State Warriors ---
    ("nba_0009", 1996, "#002F6C", "#FFCD00", "#FFFFFF"),  # Blue / Gold / White
    ("nba_0009", 1998, "#041E42", "#BE3A34", "#00A9E0"),  # Midnight Blue / Golden Gate Orange / Sky Blue
    # 2011-present intentionally left NULL

    # --- Houston Rockets ---
    ("nba_0010", 1996, "#041E42", "#BA0C2F", "#2C7AA1"),  # Midnight Blue / Rockets Red / Mercury Blue
    # Per TJ: secondary should be White (was Black) for this era.
    ("nba_0010", 2004, "#BA0C2F", "#FFFFFF", "#8D9093"),  # Red / White / Silver
    ("nba_0010", 2020, "#BA0C2F", "#010101", "#373A36"),  # Red / Black / Anthracite
    # 2027-present intentionally left NULL - see NBA_CURRENT30_COLORS note
    # below, this is now handled via config.js per TJ's correction.

    # --- Indiana Pacers ---
    ("nba_0011", 1996, "#041E42", "#FFCD00", "#FFFFFF"),  # Navy / Gold / White
    ("nba_0011", 2011, "#041E42", "#FFC72C", "#B1B3B3"),  # Navy / Gold / Cool Gray
    # 2026-present intentionally left NULL

    # --- LA Clippers ---
    # Per TJ: Blue should be tertiary in every era, swapped with whatever
    # was there before (white/gray/black respectively).
    ("nba_0012", 1996, "#D50032", "#FFFFFF", "#003DA5"),  # Red / White / Blue
    ("nba_0012", 2001, "#D50032", "#B1B3B3", "#003DA5"),  # Red / Gray / Blue
    ("nba_0012", 2016, "#D50032", "#010101", "#003DA5"),  # Red / Black / Blue
    # 2025-present intentionally left NULL

    # --- LA Lakers ---
    ("nba_0013", 1996, "#9063CD", "#FFC72C", "#FFFFFF"),  # Royal Purple / Gold / White
    # 2000-present intentionally left NULL

    # --- Memphis Grizzlies - additional splits beyond the Vancouver-palette
    # entry already in NBA_COLORS above (that entry covers 1996-2001 as
    # VAN; these cover the post-relocation eras before the current scheme,
    # which per TJ doesn't actually start until 2019, not 2005) ---
    ("nba_0028", 2002, "#00B2A9", "#C8102E", "#8F654D"),  # Turquoise / Red / Bronze (Vancouver-palette holdover)
    ("nba_0028", 2005, "#0C2340", "#7D9CC0", "#FFC72C"),  # Memphis Midnight Blue / Beale Street Blue / Grizzlies Gold
    # 2019-present intentionally left NULL (current config.js scheme)

    # --- Miami Heat ---
    ("nba_0014", 1996, "#2C2A29", "#DF192C", "#F2672C"),  # Black / Red / Orange
    # 2000-present intentionally left NULL

    # --- Milwaukee Bucks ---
    ("nba_0015", 1996, "#702F8A", "#2C5234", "#8D9093"),  # Purple / Hunter Green / Silver
    ("nba_0015", 2007, "#2C5234", "#A6192E", "#8D9093"),  # Hunter Green / Dark Red / Silver
    # 2016-present intentionally left NULL

    # --- Minnesota Timberwolves ---
    # First row is a single season (1995-96 only) before the 1996-97 slate
    # blue rebrand - per TJ's note this and the 2008 shade-tweak row are
    # really one continuous era, using the longer/dominant 1996-2008
    # sub-era's Green value (#00843D) rather than the later Tree Green.
    ("nba_0016", 1996, "#0032A0", "#009A44", "#8D9093"),  # Royal Blue / Kelly Green / Silver
    ("nba_0016", 1997, "#236192", "#010101", "#00843D"),  # Slate Blue / Black / Green
    ("nba_0016", 2018, "#0C2340", "#236192", "#78BE21"),  # Midnight Blue / Lake Blue / Aurora Green
    # 2027-present intentionally left NULL

    # --- Orlando Magic ---
    ("nba_0019", 1996, "#010101", "#007FC5", "#8D9093"),  # Magic Black / Electric Blue / Quick Silver
    ("nba_0019", 1999, "#0057B7", "#010101", "#8D9093"),  # Light Royal / Black / Silver
    # 2026-present intentionally left NULL

    # --- Philadelphia 76ers ---
    # Per TJ: secondary/tertiary (blue/white) swapped for the 1996-97 era.
    ("nba_0020", 1996, "#D50032", "#FFFFFF", "#002F6C"),  # Red / White / Blue
    ("nba_0020", 1998, "#010101", "#D50032", "#896C4C"),  # Black / Red / Gold
    ("nba_0020", 2010, "#D50032", "#003DA5", "#B1B3B3"),  # Red / Royal Blue / Silver
    # 2023-present intentionally left NULL

    # --- Phoenix Suns ---
    ("nba_0021", 1996, "#5F249F", "#FE5000", "#FF6900"),  # Purple / Orange / Yellow (gradient era)
    # This row is now 2001-2013 (was 2001-2017) - split_color_eras.py
    # carved 2014-2017 out of it per TJ's new correction below. Colors
    # unchanged for the 2001-2013 portion.
    ("nba_0021", 2001, "#582C83", "#CB6015", "#5B6770"),  # Purple / Burnt Orange / Gray
    # New era per TJ, 2014-2017.
    ("nba_0021", 2014, "#CB6015", "#010101", "#211747"),  # Orange / Black / Purple
    # 2018-present intentionally left NULL

    # --- Sacramento Kings ---
    ("nba_0023", 1996, "#010101", "#753BBD", "#8D9093"),  # Black / Purple / Silver
    # New era per TJ, 2017-2023 (previously left NULL as "current" - now
    # split off since the real current scheme (2024+) is different colors
    # entirely, set in NBA_CURRENT below).
    ("nba_0023", 2017, "#582C83", "#5B6770", "#FFFFFF"),  # Royal Purple / Granite / White
    # 2024-present intentionally left NULL - see NBA_CURRENT update below

    # --- Toronto Raptors ---
    # FLAGGED FOR YOUR CALL: split_color_eras.py used the "purple carried
    # through 2008" reading (era1 = 1996-2008) rather than the doc's own
    # "1995-2006" bullet header, since the header conflicts with its own
    # description and with the raw row boundary for era 2. If you actually
    # want the header taken literally, era 1 should end at 2007 instead -
    # that would require re-running split_color_eras.py with season 2007
    # in place of 2009 before this entry would apply correctly.
    ("nba_0026", 1996, "#753BBD", "#BA0C2F", "#010101"),  # Purple / Raptor Red / Black
    ("nba_0026", 2009, "#BA0C2F", "#010101", "#8D9093"),  # Red / Black / Silver
    # 2021-present intentionally left NULL

    # --- Utah Jazz ---
    # Per TJ: full color correction, was Purple/Green/Copper, should be:
    ("nba_0027", 1996, "#572C5F", "#FFC72C", "#046A38"),  # Purple / Gold / Green
    ("nba_0027", 2005, "#0C2340", "#418FDE", "#582C83"),  # Utah Blue / Jazz Blue / Purple
    ("nba_0027", 2011, "#0C2340", "#2C5234", "#FFA400"),  # Navy / Dark Green / Dark Yellow
    ("nba_0027", 2023, "#010101", "#FBE122", "#DBE2E9"),  # Black Key / Spotlight Yellow / Light Gray
    # 2026-present intentionally left NULL

    # --- Washington Wizards - additional split beyond the Bullets/Wizards
    # rename entry already in NBA_COLORS above (that entry covers the
    # 1996-97 Bullets season; this covers the Wizards' slate-blue era
    # before the 2012 red/navy/silver rebrand) ---
    ("nba_0029", 1998, "#236192", "#010101", "#8F654D"),  # Slate Blue / Black / Bronze
    # 2012-present intentionally left NULL
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
    # --- Detroit Shock, "Black/Yellow/Green" era (1998-2001) ---
    # Per TJ + TruColor. TruColor lists 6 colors (Black/Yellow/Green/Red/
    # Silver/White) - Black/Yellow/Green kept as the 3 that read as
    # distinctive; Red/Silver/White were trim-level per this era's own
    # framing (matches how the 2002-2009 era below was originally scoped
    # before this split existed).
    ("wnba_0009", 1998, "#010101", "#FFA400", "#006271"),  # Black / Yellow / Green
    # --- Detroit Shock, "Blue/Dark Blue/Red" era (2002-2009) ---
    # Now split from the era above via WNBA_SPLITS - same 3 colors I'd
    # already had here, just moved from start_season=1998 (wrong, that
    # season belonged to the Black/Yellow/Green era) to the correct 2002.
    ("wnba_0009", 2002, "#003DA5", "#041E42", "#D50032"),  # Blue / Dark Blue / Red
    # --- Tulsa Shock (2010-2015) ---
    ("wnba_0009", 2010, "#FFB81C", "#010101", "#A6192E"),  # Yellow / Black / Dark Red
    # --- Orlando Miracle (1999-2002) -> Connecticut Sun ---
    # Quick Silver dropped in favor of Orange - the 3 below are what
    # actually reads as distinctive; silver is closer to a neutral trim.
    ("wnba_0012", 1999, "#0057B7", "#010101", "#DC4405"),  # Miracle Blue / Black / Orange
    # --- Connecticut Sun, "Blue/Red/Yellow" era (2003-2015) ---
    # Per TJ + TruColor: TruColor's 2003-06/2007-11/2012-15 rows are all
    # identical hex (Navy/Red/Yellow) despite being listed as 3 separate
    # eras - treated as one continuous look here since nothing actually
    # changed.
    ("wnba_0012", 2003, "#041E42", "#A6192E", "#FFC72C"),  # Navy / Red / Yellow
    # --- Connecticut Sun, "Orange/Blue" era (2016-2020) ---
    # Per TJ: Orange promoted to primary, Navy demoted to secondary. Yellow
    # still present in TruColor's swatch set for this era even though TJ
    # only named 2 colors - kept as tertiary rather than dropped.
    ("wnba_0012", 2016, "#DC4405", "#041E42", "#FFC72C"),  # Orange / Navy / Yellow
    # 2021-present intentionally left NULL - matches the current
    # wnba/config.js CON entry (#FC4C02 / #0C2340 / #FFFFFF), confirmed.
    # --- Portland Fire (2000-2025 row only - NOT the 2026 revival row) ---
    # NOTE: you mentioned already manually editing Portland Fire's colors
    # in a prior session, but the live db currently shows NULL for this
    # row - so either that edit didn't make it into this db snapshot, or
    # got reverted. DOUBLE-CHECK before running this seed script for WNBA
    # - if you already have different intentional values live, this will
    # overwrite them.
    ("wnba_0015", 2000, "#C8102E", "#010101", "#896C4C"),  # Red / Black / Gold
    # --- Portland Fire (2026-present revival) - INTENTIONALLY NOT SET ---
    # Per TJ + TruColor: Red #C8102E / Black #010101 / Pink #E93CAC is
    # confirmed for this era, but it's the CURRENT (only) era for this
    # row - matches wnba/config.js's POR entry exactly already (that
    # entry's inline comment is stale/wrong about which color is primary,
    # worth a quick comment fix in config.js, but the actual field values
    # are already correct). Left NULL here per the usual convention.

    # --- Atlanta Dream (2008-present) ---
    # 3 real eras. FLAG: config.js's current ATL entry (#E31837/#000000/
    # #C3996B) does NOT match TruColor's 2020-present swatch at all
    # (#C8102E/#373A36/#418FDE) - worth checking whether config.js needs
    # updating too, independent of these historical rows.
    ("wnba_0018", 2008, "#418FDE", "#C8102E", "#CED9E5"),  # Sky Blue / Red / Star Blue
    ("wnba_0018", 2016, "#0C2340", "#C8102E", "#418FDE"),  # Navy / Red / Sky Blue
    # 2020-present intentionally left NULL - see FLAG above

    # --- Las Vegas Aces - additional split beyond the Utah Starzz/San
    # Antonio entries already above (those cover 1997-2017; this splits
    # the LVA-code portion, previously one row 2018-present) ---
    ("wnba_0008", 2018, "#010101", "#BA0C2F", "#89734C"),  # Black / Red / Gold
    # 2024-present intentionally left NULL - matches current config.js
    # LVA entry exactly, confirmed.

    # --- LA Sparks (1997-present) ---
    # FLAG: config.js's current LAS tertiary (#000000 black) doesn't
    # match TruColor's White for 2021-present - no black at all in that
    # era's swatch set. Worth checking config.js.
    ("wnba_0004", 1997, "#702F8A", "#FFC72C", "#00B398"),  # Purple / Gold / Pacific Green
    # 2021-present intentionally left NULL - see FLAG above

    # --- Minnesota Lynx (1999-present) ---
    # 3 real eras. FLAG: config.js's current MIN secondary (#78BE21
    # green) doesn't match TruColor's Midnight Blue #0C2340 for
    # 2018-present - worth checking config.js.
    ("wnba_0011", 1999, "#00843D", "#236192", "#8D9093"),  # Green / Slate Blue / Silver
    ("wnba_0011", 2011, "#236192", "#010101", "#8D9093"),  # Slate Blue / Black / Silver
    # 2018-present intentionally left NULL - see FLAG above

    # --- New York Liberty (1997-present) ---
    # TruColor's 1997-2002 and 2003-2011 rows are the same 5 colors just
    # reordered (one has an extra alternate uniform shade) - treated as
    # one continuous era through 2011, not 2 separate ones.
    ("wnba_0005", 1997, "#010101", "#0057B7", "#6ECEB2"),  # Gotham Black / Harbor Blue / Liberty Green
    ("wnba_0005", 2012, "#010101", "#003DA5", "#FF6720"),  # Black / Blue / Orange
    # 2020-present intentionally left NULL - reasonably close match to
    # config.js's current NYL entry, no flag needed.

    # --- Phoenix Mercury (1997-present) ---
    # 4 real eras. 2026-present already matches config.js exactly.
    ("wnba_0006", 1997, "#EF3340", "#5F249F", "#EEDC00"),  # Planet Red / Purple / Chartreuse
    ("wnba_0006", 2011, "#582C83", "#CB6015", "#8D9093"),  # Purple / Orange / Silver
    ("wnba_0006", 2015, "#211747", "#CB6015", "#010101"),  # Dark Purple / Burnt Orange / Black
    # 2026-present intentionally left NULL - matches current config.js
    # PHX entry exactly, confirmed.

    # --- Seattle Storm (2000-present) ---
    # 3 real eras. FLAG: config.js's current SEA tertiary (#003087 blue)
    # doesn't match TruColor's Bolt Green #78BE21 for 2021-present -
    # worth checking config.js.
    ("wnba_0016", 2000, "#00573F", "#9E2B2F", "#F6BE00"),  # Hunter Green / Maroon / Yellow
    ("wnba_0016", 2016, "#2C5234", "#FBE122", "#A2AAAD"),  # Storm Green / Lightning Yellow / Thunder Gray
    # 2021-present intentionally left NULL - see FLAG above

    # --- Washington Mystics (1998-present) ---
    # 2 real eras. 2011-present already matches config.js exactly.
    ("wnba_0010", 1998, "#236192", "#8F654D", "#010101"),  # Slate Blue / Bronze / Black
    # 2011-present intentionally left NULL - matches current config.js
    # WAS entry exactly, confirmed.

    # --- Charlotte Sting (1997-2006, folded) ---
    # 2 real eras. The later era (2004-2006) is left NULL same as an
    # active team's "current" era - config.js's folded CHA entry already
    # holds exactly those values (#F9423A/#1B365D/#010101), confirmed
    # against this same TruColor data, so no separate entry needed here.
    ("wnba_0001", 1997, "#00778B", "#280071", "#DC4405"),  # Teal / Purple / Orange
    # 2004-2006 intentionally left NULL - matches config.js's folded CHA
    # entry exactly, confirmed.
]


NFL_COLORS = [
    # Source: TJ-provided NFL_Team_Color_History.txt (TruColor-derived),
    # cross-checked against nfl_elo.db team_history row boundaries. Rows here
    # match the start_season of an EXISTING team_history row - either an
    # original 1996 franchise row, a rename/relocate row (OAK/SD/STL/TEN/WAS),
    # or a new row created by split_color_eras.py --league nfl (run that FIRST,
    # this script will SKIP any row that does not exist yet). Current (open,
    # most recent) era intentionally NOT included below - now that TJ has
    # confirmed the TruColor doc supersedes config.js, current colors were
    # already written directly into nfl/config.js, so leaving current NULL
    # here matches the same convention as NBA/WNBA (served by config.js).
    # Franchises that renamed WITHOUT a real color change (TEN 1996 Houston
    # Oilers -> 1997 Tennessee Oilers; OAK/SD/STL/WAS across their respective
    # relocations) get the SAME colors written to multiple team_id/start_season
    # rows below, since team_history splits on rename regardless of whether the
    # look actually changed.
    # --- Arizona Cardinals ---
    ("nfl_0001", 1996, "#9B2743", "#FFFFFF", "#010101"),
    ("nfl_0001", 2005, "#9B2743", "#010101", "#FFFFFF"),
    # --- Atlanta Falcons ---
    ("nfl_0002", 1996, "#010101", "#C8102E", "#B1B3B3"),
    ("nfl_0002", 2003, "#010101", "#A6192E", "#FFFFFF"),
    # --- Buffalo Bills ---
    ("nfl_0004", 1996, "#003087", "#C8102E", "#FFFFFF"),
    ("nfl_0004", 2002, "#091F2C", "#C8102E", "#003087"),
    # --- Carolina Panthers ---
    ("nfl_0005", 1996, "#101820", "#0085CA", "#A2AAAD"),
    # --- Cincinnati Bengals ---
    ("nfl_0007", 1996, "#101820", "#FA4616", "#FFFFFF"),
    ("nfl_0007", 2002, "#010101", "#DC4405", "#FFFFFF"),
    ("nfl_0007", 2012, "#010101", "#FC4C02", "#FFFFFF"),
    # --- Cleveland Browns ---
    ("nfl_0031", 1999, "#22150C", "#FC4C02", "#FFFFFF"),
    # --- Dallas Cowboys ---
    ("nfl_0008", 1996, "#041E42", "#869397", "#FFFFFF"),
    # --- Denver Broncos ---
    ("nfl_0009", 1996, "#FA4616", "#001489", "#FFFFFF"),
    ("nfl_0009", 1997, "#0C2340", "#FC4C02", "#FFFFFF"),
    # --- Detroit Lions ---
    ("nfl_0010", 1996, "#003DA5", "#A2AAAD", "#FFFFFF"),
    ("nfl_0010", 1997, "#407EC9", "#A2AAAD", "#FFFFFF"),
    ("nfl_0010", 2003, "#00558C", "#A2AAAD", "#010101"),
    # --- Green Bay Packers ---
    ("nfl_0011", 1996, "#285C4D", "#FFB81C", "#FFFFFF"),
    # --- Houston Texans ---
    ("nfl_0032", 2002, "#091F2C", "#A6192E", "#FFFFFF"),
    # --- Indianapolis Colts ---
    ("nfl_0012", 1996, "#001489", "#FFFFFF", None),
    ("nfl_0012", 2002, "#012169", "#FFFFFF", None),
    # --- Jacksonville Jaguars ---
    ("nfl_0013", 1996, "#00677F", "#101820", "#B58500"),
    ("nfl_0013", 2002, "#006271", "#010101", "#9A7611"),
    # --- Kansas City Chiefs ---
    ("nfl_0014", 1996, "#C8102E", "#FFB81C", "#FFFFFF"),
    ("nfl_0014", 2002, "#A6192E", "#FFB81C", "#FFFFFF"),
    # --- Miami Dolphins ---
    ("nfl_0015", 1996, "#005F61", "#FF6720", "#FFFFFF"),
    ("nfl_0015", 1997, "#005F61", "#FC4C02", "#0C2340"),
    ("nfl_0015", 2013, "#008C95", "#FF8200", "#005776"),
    # --- Minnesota Vikings ---
    ("nfl_0016", 1996, "#512D6D", "#FFB81C", "#FFFFFF"),
    ("nfl_0016", 2002, "#330072", "#FFB81C", "#FFFFFF"),
    ("nfl_0016", 2010, "#582C83", "#FFB81C", "#FFFFFF"),
    # --- New England Patriots ---
    ("nfl_0017", 1996, "#012169", "#C8102E", "#A2AAAD"),
    # --- New Orleans Saints ---
    ("nfl_0018", 1996, "#B3A369", "#101820", "#FFFFFF"),
    ("nfl_0018", 2002, "#B9975B", "#010101", "#FFFFFF"),
    # --- New York Giants ---
    ("nfl_0019", 1996, "#003087", "#C8102E", "#FFFFFF"),
    # --- New York Jets ---
    ("nfl_0020", 1996, "#046A38", "#101820", "#FFFFFF"),
    ("nfl_0020", 1998, "#285C4D", "#FFFFFF", None),
    ("nfl_0020", 2002, "#183029", "#FFFFFF", "#B5BD00"),
    # --- Oakland/Las Vegas Raiders (code OAK, permanent) ---
    ("nfl_0021", 1996, "#A2AAAD", "#010101", "#FFFFFF"),
    ("nfl_0021", 2020, "#A2AAAD", "#010101", "#FFFFFF"),
    # --- Philadelphia Eagles ---
    ("nfl_0022", 1996, "#004851", "#101820", "#919D9D"),
    # --- San Diego/LA Chargers (code SD, permanent) ---
    ("nfl_0024", 1996, "#0C2340", "#FFB81C", "#FFFFFF"),
    ("nfl_0024", 2017, "#0C2340", "#FFB81C", "#FFFFFF"),
    # --- Seattle Seahawks ---
    ("nfl_0025", 1996, "#003087", "#00843D", "#A2AAAD"),
    ("nfl_0025", 2002, "#2D5980", "#091F2C", "#64A70B"),
    ("nfl_0025", 2009, "#213D5A", "#091F2C", "#43B02A"),
    # --- San Francisco 49ers ---
    ("nfl_0026", 1996, "#9B2743", "#B9975B", "#101820"),
    ("nfl_0026", 2002, "#9D2235", "#B9975B", "#010101"),
    ("nfl_0026", 2009, "#A6192E", "#B9975B", "#FFFFFF"),
    # --- St. Louis/LA Rams (code STL, permanent) ---
    ("nfl_0027", 1996, "#002D72", "#FFB81C", "#FFFFFF"),
    ("nfl_0027", 2000, "#041E42", "#AD841F", "#FFFFFF"),
    ("nfl_0027", 2002, "#0C2340", "#C6AA76", "#FFFFFF"),
    ("nfl_0027", 2016, "#0C2340", "#FFFFFF", "#C6AA76"),
    # --- Tampa Bay Buccaneers ---
    ("nfl_0028", 1996, "#FF8200", "#C8102E", "#FFFFFF"),
    ("nfl_0028", 1997, "#A6192E", "#696158", "#010101"),
    ("nfl_0028", 2014, "#C8102E", "#3D3935", "#B2B4B2"),
    # --- Houston Oilers -> Tennessee Oilers -> Tennessee Titans (code TEN) ---
    ("nfl_0029", 1996, "#418FDE", "#C8102E", "#FFFFFF"),
    ("nfl_0029", 1997, "#418FDE", "#C8102E", "#FFFFFF"),
    ("nfl_0029", 1999, "#0C2340", "#418FDE", "#FFFFFF"),
    ("nfl_0029", 2018, "#0C2340", "#418FDE", "#B2B4B2"),
    # --- Washington Redskins -> Football Team -> Commanders (code WAS) ---
    ("nfl_0030", 1996, "#651C32", "#FFB81C", "#FFFFFF"),
    ("nfl_0030", 2020, "#651C32", "#FFB81C", "#FFFFFF"),
]


def load_db_module(league: str):
    path = os.path.join(os.path.dirname(__file__), league, "db.py")
    spec = importlib.util.spec_from_file_location(f"{league}_db", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--league", required=True, choices=["nba", "wnba", "nfl"])
    args = p.parse_args()

    db = load_db_module(args.league)
    db_path = os.path.join(os.path.dirname(__file__), f"{args.league}_elo.db")
    if not os.path.exists(db_path):
        print(f"Expected top-level db at {db_path} - not found. Run this from DBs\\, "
              f"not from inside DBs\\{args.league}\\.")
        sys.exit(1)

    conn = db.connect(db_path)
    # NBA_CURRENT30_COLORS requires split_color_eras.py --league nba to
    # have already been run - those rows don't exist otherwise, and any
    # entry here will just print as SKIPPED (harmless, but check
    # franchise.py status if you weren't expecting that). Same story for
    # NFL_COLORS and split_color_eras.py --league nfl.
    if args.league == "nba":
        rows = NBA_COLORS + NBA_CURRENT30_COLORS
    elif args.league == "wnba":
        rows = WNBA_COLORS
    else:
        rows = NFL_COLORS

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
