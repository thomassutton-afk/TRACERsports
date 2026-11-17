import csv, glob, re, sqlite3
from collections import Counter

db = sqlite3.connect('../cfb_elo.db')
dbn = dict(db.execute('select season, sum(neutral) from games group by season').fetchall())
strip = lambda s: re.sub(r'^\(\d+\)\s*', '', s).strip()

print('season  csv_N  db_neutral')
for f in sorted(glob.glob('Results/CFB_*_Results.csv')):
    season = int(re.search(r'CFB_(\d{4})_', f).group(1))
    rows = list(csv.reader(open(f, encoding='utf-8-sig')))
    h = next(i for i, r in enumerate(rows) if r and r[0] == 'Rk')
    n = [r for r in rows[h+1:] if len(r) > 7 and r[6] == 'N' and r[5]]  # played games only
    teams = Counter()
    for r in n:
        if not re.match(r'(Dec (1[6-9]|2\d|3\d)|Jan)', r[2]):  # skip bowl-season dates
            teams[strip(r[4])] += 1; teams[strip(r[7])] += 1
    sus = [t for t, c in teams.items() if c >= 3]
    print(f'{season}   {len(n):4d}   {dbn.get(season)}   {"off-campus-home suspects: " + str(sus) if sus else ""}')