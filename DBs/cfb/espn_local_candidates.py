import csv, glob, json, os, re, sqlite3

BAY = ['california', 'stanford', 'san-jose-state']
LA = ['southern-california', 'ucla']
LOCAL = {  # ESPN venue city -> teams from that metro
    'Pasadena': LA, 'Inglewood': LA, 'Los Angeles': LA, 'Honolulu': ['hawaii'],
    'Tempe': ['arizona-state'], 'Phoenix': ['arizona-state'], 'Glendale': ['arizona-state'],
    'Tucson': ['arizona'], 'San Diego': ['san-diego-state'], 'Las Vegas': ['nevada-las-vegas'],
    'Albuquerque': ['new-mexico'], 'El Paso': ['texas-el-paso'], 'Boise': ['boise-state'],
    'Atlanta': ['georgia-tech', 'georgia-state'], 'Orlando': ['central-florida'],
    'Tampa': ['south-florida'], 'St. Petersburg': ['south-florida'],
    'Miami': ['miami-fl', 'florida-international'], 'Boca Raton': ['florida-atlantic'],
    'New Orleans': ['tulane'], 'Lafayette': ['louisiana'], 'Mobile': ['south-alabama'],
    'Dallas': ['southern-methodist', 'texas-christian'],
    'Fort Worth': ['texas-christian', 'southern-methodist'], 'Arlington': ['texas-christian'],
    'Houston': ['houston', 'rice'], 'San Antonio': ['texas-san-antonio'], 'Memphis': ['memphis'],
    'Birmingham': ['alabama-birmingham'], 'Nashville': ['vanderbilt'],
    'San Francisco': BAY, 'Oakland': BAY, 'Santa Clara': ['stanford', 'san-jose-state'],
    'Philadelphia': ['temple'], 'Salt Lake City': ['utah'], 'Seattle': ['washington'],
    'Pittsburgh': ['pittsburgh'], 'Louisville': ['louisville'], 'Little Rock': ['arkansas'],
    'Baltimore': ['maryland', 'navy'], 'Landover': ['maryland', 'navy'], 'Annapolis': ['navy'],
    'Boston': ['boston-college'], 'Chicago': ['northwestern'], 'Charlotte': ['charlotte'],
    'East Rutherford': ['rutgers', 'army'], 'Bronx': ['army'], 'Brooklyn': ['army'],
}
SKIP = {('2015-11-28', frozenset({'illinois', 'northwestern'})),      # Soldier Field: neutral
        ('2015-12-05', frozenset({'southern-california', 'stanford'})),  # Pac-12 CCG
        ('2017-12-01', frozenset({'southern-california', 'stanford'})),
        ('2017-12-02', frozenset({'oklahoma', 'texas-christian'}))}      # Big 12 CCG

db = sqlite3.connect('../cfb_elo.db')
codes = {r[0] for r in db.execute('select home_code from games union select away_code from games')}
for t in sorted({t for v in LOCAL.values() for t in v} - codes):
    print('slug not in DB (fix in LOCAL):', t)

out, both, seen = [], [], set()
for path in sorted(glob.glob('espn_cache/*_80.json')):
    ymd = os.path.basename(path)[:8]
    if int(ymd[:4]) < 2008:
        continue
    d = f'{ymd[:4]}-{ymd[4:6]}-{ymd[6:8]}'
    try:
        data = json.load(open(path, encoding='utf-8'))
    except Exception:
        continue
    for ev in data.get('events', []):
        comp = (ev.get('competitions') or [{}])[0]
        venue = comp.get('venue') or {}
        city = (venue.get('address') or {}).get('city') or ''
        local = {t for c in LOCAL if re.search(r'\b' + re.escape(c) + r'\b', city) for t in LOCAL[c]}
        if not local:
            continue
        try:
            sc = tuple(sorted(int(c['score']) for c in comp.get('competitors', [])))
        except (KeyError, ValueError, TypeError):
            continue
        if len(sc) != 2:
            continue
        q = ('select game_id, round, home_code, away_code, home_pts, away_pts, neutral, season '
             'from games where substr(date,1,10)=?')
        for g in db.execute(q, (d,)):
            if g[0] in seen or g[6] != 1 or tuple(sorted((g[4], g[5]))) != sc:
                continue
            if (d, frozenset({g[2], g[3]})) in SKIP:
                continue
            teams = [t for t in (g[2], g[3]) if t in local]
            info = f"{venue.get('fullName')} ({city}) | {g[2]} {g[4]}-{g[5]} {g[3]}"
            if len(teams) == 1:
                seen.add(g[0])
                out.append([d, g[2], g[3], 0, g[1] or '', 1, comp.get('neutralSite'), g[7], g[0], teams[0], info])
            elif len(teams) == 2:
                both.append(info)

hdr = ['date','home_code','away_code','new_neutral','round','db_neutral','espn_neutral',
       'season','game_id','host','info']
out.sort(key=lambda r: r[0])
with open('espn_local_candidates.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(hdr); w.writerows(out)
print(len(out), 'candidates -> espn_local_candidates.csv')
for o in out: print(' ', o[0], o[10], '-> host', o[9])
for b in both: print('  both teams local, skipped:', b)