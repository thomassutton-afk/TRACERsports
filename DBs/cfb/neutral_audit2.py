import csv, re, sqlite3
from datetime import datetime
from collections import Counter, defaultdict

db = sqlite3.connect('../cfb_elo.db')
strip = lambda s: re.sub(r'^\(\d+\)\s*', '', s).strip()

def csv_games(season):
    rows = list(csv.reader(open(f'Results/CFB_{season}_Results.csv', encoding='utf-8-sig')))
    h = next(i for i, r in enumerate(rows) if r and r[0] == 'Rk')
    out = []
    for r in rows[h+1:]:
        if len(r) < 9 or not r[5].strip() or not r[8].strip():
            continue
        try:
            d = datetime.strptime(r[2].strip(), '%b %d %Y').strftime('%Y-%m-%d')
        except ValueError:
            continue
        out.append(dict(date=d, w=strip(r[4]), l=strip(r[7]), n=(r[6] == 'N'),
                        key=(d, tuple(sorted((int(r[5]), int(r[8])))))))
    return out

def db_games(season):
    q = ('select game_id,substr(date,1,10),round,home_team,away_team,home_code,away_code,'
         'home_pts,away_pts,neutral from games where season=?')
    m = defaultdict(list)
    for g in db.execute(q, (season,)):
        m[(g[1], tuple(sorted((g[7], g[8]))))].append(g)
    return m

review, mismatch = [], []

for season in range(1996, 2013):
    cg, dm = csv_games(season), db_games(season)
    n_keys = {g['key'] for g in cg if g['n']}
    all_db = [g for lst in dm.values() for g in lst]

    # 1) mismatches (2006-2012 is where counts differ)
    if season >= 2006:
        for g in cg:
            if not g['n']:
                continue
            hit = dm.get(g['key'], [])
            if len(hit) != 1:
                mismatch.append([season, g['date'], 'CSV N, no unique DB match', g['w'], g['l'], '', '', '', ''])
            elif hit[0][9] != 1:
                d = hit[0]
                mismatch.append([season, g['date'], 'CSV N, DB not neutral', g['w'], g['l'], 5, d[6], d[2], d[0]])
        for d in all_db:
            if d[9] == 1 and (d[1], tuple(sorted((d[7], d[8])))) not in n_keys:
                mismatch.append([season, d[1], 'DB neutral, CSV not N', '', '', d[5], d[6], d[2], d[0]])

    # 2) pre-2008 review sheet
    if season <= 2007:
        neutral = [d for d in all_db if d[9] == 1]
        reg = Counter()
        for d in neutral:
            if d[2] is None:
                reg[d[5]] += 1; reg[d[6]] += 1
        for d in neutral:
            rep = [t for t in (d[5], d[6]) if reg[t] >= 3 and d[2] is None]
            ckey = (d[1], tuple(sorted((d[7], d[8]))))
            review.append([d[1], d[5], d[6], '', d[2] or '', 1, '', season, d[0],
                           'Y' if ckey in n_keys else 'N', ';'.join(rep), f'{d[5]} v {d[6]} {d[7]}-{d[8]}'])

# Army-Navy omissions
for season in (1997, 2000, 2002, 2007):
    for lst in db_games(season).values():
        for d in lst:
            if {d[5], d[6]} == {'army', 'navy'} and d[9] == 0:
                review.append([d[1], d[5], d[6], 1, d[2] or '', 0, '', season, d[0],
                               'N', '', 'Army-Navy: SR omitted N'])

review.sort(key=lambda r: (r[7], r[0]))
hdr = ['date','home_code','away_code','new_neutral','round','db_neutral','espn_neutral','season','game_id',
       'csv_N','repeat_team','info']
with open('pre2008_neutral_review.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(hdr); w.writerows(review)
with open('csv_vs_db_neutral_mismatch.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['season','date','issue','csv_winner','csv_loser','db_home','db_away','round','game_id'])
    w.writerows(mismatch)

print(len(review), 'rows -> pre2008_neutral_review.csv')
print(len(mismatch), 'rows -> csv_vs_db_neutral_mismatch.csv')
for r in mismatch: print(r[0], r[1], r[2], '|', r[3] or r[5], 'v', r[4] or r[6])