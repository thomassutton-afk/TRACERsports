"""
One-time migration for DBs/split_color_eras.py and DBs/seed_historical_colors.py,
needed because the NFL rebuild reassigned every team's internal numeric team_id
(order-of-first-appearance during the fresh season-by-season reload no longer
matches the old db's numbering). Run this ONCE, after copying the new nfl_elo.db
and nfl/ pipeline files from sandbox into place, and BEFORE running
split_color_eras.py or seed_historical_colors.py.

Run from DBs\\:
    python remap_nfl_colors.py

What it does:
1. In split_color_eras.py's NFL_SPLITS dict, renames three keys from their
   pre-relocation code to the post-relocation code, since those specific
   color changes happened after the relocation:
     "OAK": [2025]        -> "LV":  [2025]
     "SD":  [2020]        -> "LAC": [2020]
     "STL": [2000,2002,2020] -> "STL": [2000,2002]  (unaffected years stay)
                              + new "LAR": [2020]
2. In seed_historical_colors.py's NFL_COLORS list, remaps every old numeric
   team_id to its new equivalent (verified against both dbs' `teams` tables
   by matching current team_name), preserving every color value as-is.

Verified: after this migration, split_color_eras.py --league nfl applies all
55/55 splits (0 skipped) and seed_historical_colors.py --league nfl applies
all 62/62 entries (0 skipped) against the rebuilt nfl_elo.db.
"""
import re

# --- Part 1: fix NFL_SPLITS keys in split_color_eras.py ---

SPLITS_PATH = "split_color_eras.py"
text = open(SPLITS_PATH).read()

text = text.replace(
    '    "OAK": [2025],  # lands inside the open 2020-present (Las Vegas) row\n',
    ''
)
text = text.replace(
    '    "SD": [2020],  # lands inside the open 2017-present (LA Chargers) row\n',
    ''
)
text = text.replace(
    '    "STL": [2000, 2002, 2020],  # 2000/2002 land inside the closed 1996-2015\n'
    '                                  # (St. Louis) row, 2020 inside the open\n'
    '                                  # 2016-present (LA Rams) row\n',
    '    "STL": [2000, 2002],  # both land inside the closed 1996-2015 row\n'
)
text = text.replace(
    '    "TEN": [2018, 2026],  # both land inside the open 1999-present (Titans) row\n',
    '    "TEN": [2018, 2026],  # both land inside the open 1999-present (Titans) row\n'
    '    "LV": [2025],  # post-relocation color tweak, lands inside the open 2020-present row\n'
    '    "LAC": [2020],  # post-relocation color change, lands inside the open 2017-present row\n'
    '    "LAR": [2020],  # post-relocation color change, lands inside the open 2016-present row\n'
)
open(SPLITS_PATH, "w").write(text)
print("Patched NFL_SPLITS in", SPLITS_PATH)

# --- Part 2: remap NFL_COLORS team_ids in seed_historical_colors.py ---

# old_id -> new_id, derived by matching current team_name between the old
# (pre-rebuild) and new (post-rebuild) `teams` tables. Teams not listed here
# kept the same id across the rebuild.
ID_MAP = {
    "nfl_0012": "nfl_0013",  # Colts
    "nfl_0013": "nfl_0014",  # Jaguars
    "nfl_0014": "nfl_0015",  # Chiefs
    "nfl_0015": "nfl_0016",  # Dolphins
    "nfl_0016": "nfl_0017",  # Vikings
    "nfl_0017": "nfl_0018",  # Patriots
    "nfl_0018": "nfl_0019",  # Saints
    "nfl_0019": "nfl_0020",  # Giants
    "nfl_0020": "nfl_0021",  # Jets
    "nfl_0021": "nfl_0022",  # Raiders
    "nfl_0022": "nfl_0023",  # Eagles
    "nfl_0023": "nfl_0024",  # Steelers
    "nfl_0024": "nfl_0025",  # Chargers
    "nfl_0025": "nfl_0026",  # Seahawks
    "nfl_0026": "nfl_0027",  # 49ers
    "nfl_0027": "nfl_0028",  # Rams
    "nfl_0028": "nfl_0029",  # Buccaneers
    "nfl_0029": "nfl_0012",  # Titans/Oilers
}

COLORS_PATH = "seed_historical_colors.py"
text = open(COLORS_PATH).read()
start = text.index("NFL_COLORS = [")
end = text.index("]", start) + 1
block = text[start:end]

# Two-pass substitution via placeholders, so overlapping id ranges
# (e.g. nfl_0021 -> nfl_0022, and separately nfl_0022 -> nfl_0023) don't
# collide with each other mid-replacement.
placeholder = {old: f"__TMP_{old}__" for old in ID_MAP}
for old, ph in placeholder.items():
    block = block.replace(f'"{old}"', f'"{ph}"')
for old, ph in placeholder.items():
    block = block.replace(f'"{ph}"', f'"{ID_MAP[old]}"')

assert "__TMP_" not in block, "leftover placeholder - remap failed"

new_text = text[:start] + block + text[end:]
open(COLORS_PATH, "w").write(new_text)
print("Remapped", len(ID_MAP), "team_ids in NFL_COLORS in", COLORS_PATH)
