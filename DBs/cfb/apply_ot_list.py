import argparse, csv, os, re, sqlite3, sys
from collections import defaultdict
from datetime import datetime

DB = '../cfb_elo.db'
LIST = 'ot_games_20th_century.txt'
ESPN_CSV = 'espn_ot_proposed_all.csv'
AUTH_MAX_SEASON = 2000   # seasons <= this are set entirely from the list
MAX_DAY_GAP = 10

ALIAS = {
    'pitt': 'pittsburgh', 'ole miss': 'mississippi', 'ul monroe': 'louisiana-monroe',
    'unlv': 'nevada-las-vegas', 'ucf': 'central-florida', 'bc': 'boston-college',
    'smu': 'southern-methodist', 'byu': 'brigham-young', 'tcu': 'texas-christian',
    'usc': 'southern-california', 'lsu': 'louisiana-state',
    'nc state': 'north-carolina-state', 'uab': 'alabama-birmingham',
    'utep': 'texas-el-paso', 'miami (fl)': 'miami-fl', 'miami (oh)': 'miami-oh',
    'southern miss': 'southern-mississippi', 'oregon sate': 'oregon-state',
    'middle tennessee': 'middle-tennessee-state',
}
LINE = re.compile(
    r'^(.+?)\s+(?:@|vs\.?|at)\s+(.+?)\s+\((\w+)\.?\s+(\d+),\s*(\d{4})\)\s*$', re.I)

ap = argparse.ArgumentParser()
ap.add_argument('--apply', action='store_true')
a = ap.parse_args()

con = sqlite3.connect(DB)
games = con.execute('select game_id,date,season,home_code,away_code,'
                    'home_pts,away_pts,ot from games').fetchall()
codes = {g[3] for g in games} | {g[4] for g in games}
by_pair = defaultdict(list)
for g in games:
    by_pair[frozenset((g[3], g[4]))].append(g)


def to_code(name):
    n = name.strip().lower()
    if n in ALIAS:
        return ALIAS[n]
    s = re.sub(r'[^a-z0-9]+', '-', n.replace('&', ' ')).strip('-')
    return s if s in codes else None


def pick(sa, sb, dt):
    cands = []
    for g in by_pair.get(frozenset((sa, sb)), []):
        gap = abs((datetime.strptime(g[1][:10], '%Y-%m-%d') - dt).days)
        if gap <= MAX_DAY_GAP:
            cands.append((gap, g))
    cands.sort(key=lambda x: x[0])
    if not cands:
        return None, None, 'no game between these teams within '
        f'{MAX_DAY_GAP} days'
    if len(cands) > 1 and cands[0][0] == cands[1][0]:
        return None, None, 'two games equally close in date'
    return cands[0][1], cands[0][0], ''


problems, warnings, listed = [], [], {}
for raw in open(LIST, encoding='utf-8'):
    line = raw.strip()
    if not line:
        continue
    m = LINE.match(line)
    if not m:
        problems.append(f'cannot parse: {line}')
        continue
    t1, t2, mon, day, yr = m.groups()
    c1, c2 = to_code(t1), to_code(t2)
    if not c1 or not c2:
        problems.append(f'unknown team ({t1 if not c1 else t2}): {line}')
        continue
    dt = datetime.strptime(f'{mon[:3].title()} {day} {yr}', '%b %d %Y')
    g, gap, why = pick(c1, c2, dt)
    if not g:
        problems.append(f'{why}: {line}')
        continue
    if g[0] in listed:
        problems.append(f'same game listed twice: {line}')
        continue
    listed[g[0]] = line
    if gap > 1:
        warnings.append(f'date off by {gap} days (DB has {g[1][:10]}): {line}')

print(f'{len(listed)} list games matched to DB games')
for w in warnings:
    print('  WARNING', w)
for p in problems:
    print('  PROBLEM', p)

espn = {}
if os.path.exists(ESPN_CSV):
    for r in csv.DictReader(open(ESPN_CSV, encoding='utf-8-sig')):
        if r['espn_ot'] != '':
            espn[str(r['game_id'])] = int(r['espn_ot'])

print('\nESPN flagged OT (season <= 2001) but NOT in your list:')
n_conf = 0
for g in games:
    gid, date, season, hc, ac, hp, ap_, cur = g
    if season <= 2001 and espn.get(str(gid)) == 1 and gid not in listed:
        n_conf += 1
        print(f'  {date[:10]}  {ac} {ap_} @ {hc} {hp}   (margin {abs(hp - ap_)})')
if not n_conf:
    print('  none')

new = {}
for g in games:
    gid, date, season, hc, ac, hp, ap_, cur = g
    if gid in listed:
        new[gid] = 1
    elif season <= AUTH_MAX_SEASON:
        new[gid] = 0
    else:
        new[gid] = cur

changes = [(new[g[0]], g[0]) for g in games if new[g[0]] != g[7]]
print(f'\n{len(changes)} games would change ot')

cur_by, new_by = defaultdict(int), defaultdict(int)
for g in games:
    cur_by[g[2]] += g[7]
    new_by[g[2]] += new[g[0]]
print('season  ot_now  ot_after')
for s in range(1996, 2004):
    print(f'{s}    {cur_by[s]:4d}    {new_by[s]:4d}')

print('\nGames with ot=1 and margin > 8 (rare; needs a defensive score) - worth a box-score check:')
n_big = 0
for g in games:
    gid, date, season, hc, ac, hp, ap_, cur = g
    if new[gid] == 1 and abs(hp - ap_) > 8:
        n_big += 1
        print(f'  {date[:10]}  {ac} {ap_} @ {hc} {hp}')
if not n_big:
    print('  none')

if not a.apply:
    print('\nDRY RUN. Nothing changed. Rerun with --apply to write.')
    sys.exit(0)
if problems:
    print('\nNOT applying: fix the PROBLEM lines above first.')
    sys.exit(1)
con.executemany('update games set ot=? where game_id=?', changes)
con.commit()
print(f'\napplied: updated ot on {len(changes)} games')