import csv, re, sqlite3
from datetime import datetime

BAY = ['california', 'stanford', 'san-jose-state']
LOCAL = {  # city name appearing in Sports-Reference's venue note -> teams from that metro
    'Pasadena': ['southern-california', 'ucla'], 'Honolulu': ['hawaii'],
    'Tempe': ['arizona-state'], 'Phoenix': ['arizona-state'], 'Glendale': ['arizona-state'],
    'Tucson': ['arizona'], 'San Diego': ['san-diego-state'], 'Las Vegas': ['nevada-las-vegas'],
    'Albuquerque': ['new-mexico'], 'El Paso': ['texas-el-paso'], 'Boise': ['boise-state'],
    'Atlanta': ['georgia-tech', 'georgia-state'], 'Orlando': ['central-florida'],
    'Tampa': ['south-florida'], 'St. Petersburg': ['south-florida'],
    'Miami': ['miami-fl', 'florida-international'], 'Boca Raton': ['florida-atlantic'],
    'New Orleans': ['tulane'], 'Dallas': ['southern-methodist', 'texas-christian'],
    'Fort Worth': ['texas-christian', 'southern-methodist'], 'Arlington': ['texas-christian'],
    'Houston': ['houston', 'rice'], 'San Antonio': ['texas-san-antonio'], 'Memphis': ['memphis'],
    'Birmingham': ['alabama-birmingham'], 'Nashville': ['vanderbilt'],
    'San Francisco': BAY, 'Oakland': BAY, 'Santa Clara': ['stanford', 'san-jose-state'],
    'Philadelphia': ['temple'], 'Salt Lake City': ['utah'], 'Seattle': ['washington'],
    'Pittsburgh': ['pittsburgh'], 'Louisville': ['louisville'], 'Little Rock': ['arkansas'],
    'Baltimore': ['maryland', 'navy'], 'Landover': ['maryland', 'navy'], 'Annapolis': ['navy'],
    'Boston': ['boston-college'], 'Chicago': ['northwestern'],
    'East Rutherford': ['rutgers', 'army'], 'Bronx': ['army'], 'Brooklyn': ['army'],
}
db = sqlite3.connect('../cfb_elo.db')
codes = {r[0] for r in db.execute('select home_code from games union select away_code from games')}
for t in sorted({t for v in LOCAL.values() for t in v} - codes):
    print('slug not in DB (fix in LOCAL):', t)

out, both = [], []
for season in range(1996, 2027):
    try:
        rows = list(csv.reader(open(f'Results/CFB_{season}_Results.csv', encoding='utf-8-sig')))
    except FileNotFoundError:
        print('no file for', season); continue
    h = next((i for i, r in enumerate(rows) if r and r[0] == 'Rk'), None)
    if h is None:
        print('no header row in', season); continue
    hd = rows[h]; w = hd.index('Winner'); di = hd.index('Date'); ni = len(hd) - 1
    for r in rows[h+1:]:
        if len(r) <= ni or r[w+2] != 'N' or not r[w+1].strip() or not r[w+4].strip():
            continue
        note = r[ni].strip()
        cities = [c for c in LOCAL if re.search(r'\b' + re.escape(c) + r'\b', note)]
        local = {t for c in cities for t in LOCAL[c]}
        if not local:
            continue
        try:
            d = datetime.strptime(r[di].strip(), '%b %d %Y').strftime('%Y-%m-%d')
        except ValueError:
            continue
        pts = tuple(sorted((int(r[w+1]), int(r[w+4]))))
        q = ('select game_id, round, home_code, away_code, home_pts, away_pts, neutral '
             'from games where substr(date,1,10)=? and season=?')
        for g in db.execute(q, (d, season)):
            if tuple(sorted((g[4], g[5]))) != pts or g[6] != 1:
                continue
            teams = [t for t in (g[2], g[3]) if t in local]
            info = f'{note} | {g[2]} {g[4]}-{g[5]} {g[3]}'
            if len(teams) == 1:
                out.append([d, g[2], g[3], 0, g[1] or '', 1, '', season, g[0], teams[0], info])
            elif len(teams) == 2:
                both.append(info)

hdr = ['date','home_code','away_code','new_neutral','round','db_neutral','espn_neutral',
       'season','game_id','host','info']
with open('bowl_local_candidates2.csv', 'w', newline='', encoding='utf-8') as f:
    w_ = csv.writer(f); w_.writerow(hdr); w_.writerows(out)
print(len(out), 'candidates -> bowl_local_candidates2.csv')
for o in out: print(' ', o[0], o[10], '-> host', o[9])
for b in both: print('  both teams local, skipped:', b)