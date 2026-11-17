"""Print current CFB Elo ratings (read-only; nothing is rebuilt or written).

Run from DBs/cfb:
    python show_ratings.py                       # top 25, echo + pulse side by side
    python show_ratings.py --top 138             # everyone
    python show_ratings.py --variant pulse
    python show_ratings.py --season 2025 --top 10
    python show_ratings.py --team "Ohio State"   # one team (substring of the display name)

    python show_ratings.py --conf SEC            # only one conference (repeat the flag for several)
    python show_ratings.py --tier P4             # only P4 (or G6) teams
    python show_ratings.py --by conf             # grouped by conference, strongest average Elo first
    python show_ratings.py --by tier             # P4 block, then G6 block
    python show_ratings.py --tier G6 --by conf --top 5    # top 5 within each G6 conference

Below each list (and each group) is the AVERAGE rating of exactly the teams shown, per variant, so
--top 25, --conf SEC or --tier G6 each average just those rows. With --by and more than one group,
a final line averages every team shown. Groups are ordered by that average, strongest first.

Columns: '#' is the position in the list you are looking at (within the group when grouped);
'rk' is the team's rank among ALL FBS teams for that variant. Conference and tier are as of the
season being shown, so --season 2019 uses the 2019 conferences.

P4/G6 rule (edit the two constants below to taste): the four current power conferences are P4, plus
the conferences listed in POWER_THROUGH for the seasons they were power leagues. Everything else
(including independents such as UConn) is G6. Notre Dame is always P4 (ALWAYS_P4), and shows as ACC from 2020 on, as the DB has it.
"""
import argparse, json, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db, rebuild

POWER = {"ACC", "Big 12", "Big Ten", "SEC"}
POWER_THROUGH = {"Pac-12": 2023, "Pac-10": 2023, "Big East": 2012}   # conference: last season it counted as P4
ALWAYS_P4 = {"notre-dame"}                                            # independents counted as P4 in every season


def tier_of(conf, season, slug):
    if slug in ALWAYS_P4 or conf in POWER or season <= POWER_THROUGH.get(conf, -1):
        return "P4"
    return "G6"


ap = argparse.ArgumentParser()
ap.add_argument("--db", default="../cfb_elo.db")
ap.add_argument("--season", type=int)
ap.add_argument("--variant", choices=["echo", "pulse", "both"], default="both")
ap.add_argument("--top", type=int, help="rows to show (per group when grouped); default 25, or all when filtering/grouping")
ap.add_argument("--team")
ap.add_argument("--conf", action="append", help="only this conference, e.g. SEC or 'Big Ten' (repeatable)")
ap.add_argument("--tier", choices=["P4", "G6"], type=str.upper)
ap.add_argument("--by", choices=["conf", "tier"], help="group the list")
a = ap.parse_args()

conn = db.connect(a.db)
season = a.season or conn.execute("SELECT MAX(season) FROM games").fetchone()[0]
asof = conn.execute("SELECT MAX(date) FROM games WHERE season=?", (season,)).fetchone()[0]

short = {}
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "team_display_names.json")
if os.path.exists(p):
    short = {v["team_id"]: v["short"] for v in json.load(open(p, encoding="utf-8")).values()}

variants = ["echo", "pulse"] if a.variant == "both" else [a.variant]
tables = {}
for v in variants:
    rows = rebuild.standings(conn, season, v)          # sorted by rating, FBS teams only
    tables[v] = {tid: (i + 1, short.get(tid, name), w, l, t, r) for i, (tid, name, w, l, t, r) in enumerate(rows)}
main = tables[variants[0]]

slug_of = {tid: code for tid, code in conn.execute("SELECT team_id, code FROM team_history WHERE end_season IS NULL")}
info = {}
for tid in main:
    era = db.conference_for_season(conn, tid, season)
    conf = era["conference"] if era else "Ind"
    info[tid] = (conf, tier_of(conf, season, slug_of.get(tid)))

order = sorted(main, key=lambda tid: main[tid][0])
if a.conf:
    wanted = {c.lower() for c in a.conf}
    unknown = [c for c in a.conf if c.lower() not in {info[t][0].lower() for t in info}]
    if unknown:
        sys.exit(f"No such conference in {season}: {', '.join(unknown)}. "
                 f"Choices: {', '.join(sorted({c for c, _ in info.values()}))}")
    order = [t for t in order if info[t][0].lower() in wanted]
if a.tier:
    order = [t for t in order if info[t][1] == a.tier]
if a.team:
    order = [t for t in order if a.team.lower() in main[t][1].lower()]

filtered = bool(a.conf or a.tier or a.by or a.team)
limit = a.top if a.top else (None if filtered else 25)

head = f"{'#':>3}  {'Team':<24}{'Conf':<9}{'Tier':<5}{'Rec':>7}"
for v in variants:
    head += f"  {v + ' Elo':>10}{'rk':>5}"
width = len(head)


def line(pos, tid):
    rk, name, w, l, t, _ = main[tid]
    rec = f"{int(w)}-{int(l)}" + (f"-{int(t)}" if t else "")
    s = f"{pos:>3}  {name:<24}{info[tid][0]:<9}{info[tid][1]:<5}{rec:>7}"
    for v in variants:
        r = tables[v].get(tid)
        s += f"  {r[5]:>10.1f}{r[0]:>5}" if r else f"  {'-':>10}{'-':>5}"
    return s


def avg_line(label, tids):
    """Average rating of exactly the teams passed in (the ones shown), one column per variant."""
    s = f"{label:<{3 + 2 + 24 + 9 + 5 + 7}}"
    for v in variants:
        rs = [tables[v][t][5] for t in tids if t in tables[v]]
        s += f"  {sum(rs) / len(rs):>10.1f}{'':>5}" if rs else f"  {'-':>10}{'':>5}"
    return s


def block(tids):
    print(head)
    for i, t in enumerate(tids, 1): print(line(i, t))
    if len(tids) > 1:
        print("-" * width)
        print(avg_line(f"     Average of {len(tids)} teams", tids))


print(f"{season} season, through games dated {asof}  |  {len(main)} FBS teams"
      + (f"  |  {len(order)} match" if filtered else "") + "\n")
if not order:
    sys.exit("No teams match those filters.")

if a.by:
    key = (lambda t: info[t][0]) if a.by == "conf" else (lambda t: info[t][1])
    groups = defaultdict(list)
    for t in order: groups[key(t)].append(t)
    shown = {g: ts[:limit] for g, ts in groups.items()}                  # only what will be printed
    avg = lambda g: sum(main[t][5] for t in shown[g]) / len(shown[g])    # in the first variant
    names = sorted(shown, key=avg, reverse=True) if a.by == "conf" else sorted(shown)   # P4 before G6
    for g in names:
        print(f"== {g}  ({len(groups[g])} team{'s' if len(groups[g]) != 1 else ''}"
              + (f", top {len(shown[g])} shown" if len(shown[g]) < len(groups[g]) else "") + ") ==")
        block(shown[g])
        print()
    if len(names) > 1:
        everyone = [t for g in names for t in shown[g]]
        print(avg_line(f"== All shown ({len(everyone)} teams) average", everyone))
else:
    block(order[:limit])
