import csv, re, sqlite3
from datetime import datetime

BAY = ['california', 'stanford', 'san-jose-state']
LOCAL = {  # venue city as Sports-Reference writes it -> teams from that metro
    'Pasadena CA': ['southern-california', 'ucla'], 'Honolulu HI': ['hawaii'],
    'Tempe AZ': ['arizona-state'], 'Phoenix AZ': ['arizona-state'], 'Tucson AZ': ['arizona'],
    'San Diego CA': ['san-diego-state'], 'Las Vegas NV': ['nevada-las-vegas'],
    'Albuquerque NM': ['new-mexico'], 'El Paso TX': ['texas-el-paso'], 'Boise ID': ['boise-state'],
    'Atlanta GA': ['georgia-tech'], 'Orlando FL': ['central-florida'], 'Tampa FL': ['south-florida'],
    'Miami FL': ['miami-fl', 'florida-international'], 'New Orleans LA': ['tulane'],
    'Dallas TX': ['southern-methodist', 'texas-christian'],
    'Fort Worth TX': ['texas-christian', 'southern-methodist'],
    'Houston TX': ['houston', 'rice'], 'Memphis TN': ['memphis'],
    'Birmingham AL': ['alabama-birmingham'], 'Nashville TN': ['vanderbilt'],
    'San Francisco CA': BAY, 'Oakland CA': BAY, 'Philadelphia PA': ['temple'],
    'Salt Lake City UT': ['utah'], 'Seattle WA': ['washington'],
    'Pittsburgh PA': ['pittsburgh'], 'Louisville KY': ['louisville'],
}
db = sqlite3.connect('../cfb_elo.db')
codes = {r[0] for r in db.execute('select home_code from games union select away_code from games')}
for t in sorted({t for v in LOCAL.values() for t in v} - codes):
    print('slug not in DB (fix in LOCAL):', t)

pending = set()   # games already set to non-neutral in the earlier sheet
try:
    for r in csv.DictReader(open('pre2008_neutral_review.csv', encoding='utf-8-sig', newline='')):
        if r['new_neutral'].strip() == '0':
            pending.add(str(r['game_id']))
except FileNotFoundError:
    pass

out, both = [], []
for season in range(2008, 2013):
    rows = list(csv.reader(open(f'Results/CFB_{season}_Results.csv', encoding='utf-8-sig')))
    h = next(i for i, r in enumerate(rows) if r and r[0] == 'Rk')
    for r in rows[h+1:]:
        if len(r) < 10 or not r[5].strip() or not r[8].strip():
            continue
        m = re.search(r'\(([^)]+)\)\s*$', r[9])
        local = LOCAL.get(m.group(1)) if m else None
        if not local:
            continue
        try:
            d = datetime.strptime(r[2].strip(), '%b %d %Y').strftime('%Y-%m-%d')
        except ValueError:
            continue
        pts = tuple(sorted((int(r[5]), int(r[8]))))
        q = ('select game_id, round, home_code, away_code, home_pts, away_pts, neutral '
             'from games where substr(date,1,10)=? and season=?')
        for g in db.execute(q, (d, season)):
            if tuple(sorted((g[4], g[5]))) != pts or g[6] != 1 or str(g[0]) in pending:
                continue
            teams = [t for t in (g[2], g[3]) if t in local]
            info = f'{r[9].strip()} | {g[2]} {g[4]}-{g[5]} {g[3]}'
            if len(teams) == 1:
                out.append([d, g[2], g[3], 0, g[1] or '', 1, '', season, g[0], teams[0], info])
            elif len(teams) == 2:
                both.append(info)

hdr = ['date','home_code','away_code','new_neutral','round','db_neutral','espn_neutral',
       'season','game_id','host','info']
with open('bowl_local_candidates.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(hdr); w.writerows(out)
print(len(out), 'candidates -> bowl_local_candidates.csv (new_neutral=0, host = the local team)')
for o in out: print(' ', o[0], o[10], '-> host', o[9])
for b in both: print('  both teams local, skipped:', b)