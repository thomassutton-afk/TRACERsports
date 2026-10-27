"""Copy ESPN final scores from CFB_2026_Results.xlsx into rows of the Sports-Reference CSV
that have no score yet, so the normal pipeline (normalize_sr_games -> add_season) can load them.

Run from DBs/cfb:
    python fill_csv_from_xlsx.py Results\\CFB_2026_Results.xlsx Results\\CFB_2026_Results.csv           # dry run
    python fill_csv_from_xlsx.py Results\\CFB_2026_Results.xlsx Results\\CFB_2026_Results.csv --apply   # writes

Only fills a CSV row when ALL of these hold: both Pts cells are blank, the xlsx has a final score
for that exact date + pair of teams, the score is not tied / 0-0, and the date is today or earlier.
Every other row is left as it was (the file just ends with a newline), and a backup copy is saved first.

CSV orientation rules (same ones normalize_sr_games.py reads):
    Winner column first, Loser second.   '@' = the Winner was the AWAY team.
    '' = the Winner was home.            'N' = neutral site.
So if the real winner is not the team listed first, the two team cells and the markers are swapped.
"""
import argparse, csv, datetime, re, shutil, sys
from openpyxl import load_workbook

ap = argparse.ArgumentParser()
ap.add_argument("xlsx"); ap.add_argument("csv")
ap.add_argument("--through", help="latest date to fill, YYYY-MM-DD (default: today)")
ap.add_argument("--apply", action="store_true")
a = ap.parse_args()
through = datetime.date.fromisoformat(a.through) if a.through else datetime.date.today()
rank = re.compile(r"^\(\d+\)\s+")
bare = lambda t: rank.sub("", t.strip())

# ESPN scores from the xlsx: {(date, team): (points_for, points_against)}
ws = load_workbook(a.xlsx, data_only=True).worksheets[0]
head = [c.value for c in ws[1]]; ix = {h: head.index(h) for h in ("Date", "Team", "PointsFor", "PointsAgainst")}
espn = {}
for r in ws.iter_rows(min_row=2, values_only=True):
    if r[ix["PointsFor"]] is None or r[ix["PointsAgainst"]] is None: continue
    d = r[ix["Date"]]; d = d.date() if hasattr(d, "date") else d
    espn[(d, r[ix["Team"]])] = (int(r[ix["PointsFor"]]), int(r[ix["PointsAgainst"]]))

# the CSV, read so it can be written back unchanged (encoding and line endings preserved)
raw = open(a.csv, "rb").read()
eol = "\r\n" if b"\r\n" in raw else "\n"
f = open(a.csv, newline="", encoding="utf-8", errors="surrogateescape")
rows = list(csv.reader(f)); f.close()

filled, skipped = [], []
for r in rows:
    if len(r) < 10 or r[6].strip() or r[9].strip(): continue            # not a blank-score game row
    try: d = datetime.datetime.strptime(r[2].strip(), "%b %d %Y").date()
    except ValueError: continue
    if d > through: continue
    first, second = bare(r[5]), bare(r[8])
    s1, s2 = espn.get((d, first)), espn.get((d, second))
    if not s1 or not s2:
        skipped.append(f"{d} {first} vs {second}: no final score in the xlsx yet"); continue
    if s1 != (s2[1], s2[0]):
        skipped.append(f"{d} {first} vs {second}: xlsx rows disagree {s1} vs {s2} - skipped"); continue
    p1, p2 = s1
    if p1 == p2:
        skipped.append(f"{d} {first} vs {second}: tied score {p1}-{p2} - skipped (FBS has no ties)"); continue
    if p1 > p2:                         # listed-first team won: keep order
        r[6], r[9] = str(p1), str(p2)
    else:                               # listed-second team won: swap teams, flip the marker
        r[5], r[8] = r[8], r[5]
        r[6], r[9] = str(p2), str(p1)
        r[7] = {"@": "", "": "@"}.get(r[7].strip(), r[7])
    filled.append(f"{d} {bare(r[5])} {r[6]}, {bare(r[8])} {r[9]}  [{r[7] or 'home win'}]")

print(f"{len(filled)} game(s) can be filled (through {through}):")
for x in filled: print("   ", x)
if skipped:
    print(f"{len(skipped)} blank game(s) left alone:")
    for x in skipped[:10]: print("   ", x)
    if len(skipped) > 10: print(f"    ... and {len(skipped) - 10} more (future games)")
if not a.apply:
    print("\nDry run only. Add --apply to write."); sys.exit()
if filled:
    backup = a.csv.replace(".csv", "") + ".before_espn_fill.csv"
    shutil.copyfile(a.csv, backup)
    with open(a.csv, "w", newline="", encoding="utf-8", errors="surrogateescape") as out:
        csv.writer(out, lineterminator=eol).writerows(rows)
    print(f"\nWrote {a.csv} (backup: {backup}).")
