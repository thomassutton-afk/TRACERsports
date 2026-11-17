import argparse, re, sqlite3
from collections import defaultdict
import openpyxl

DB = '../cfb_elo.db'

ap = argparse.ArgumentParser()
ap.add_argument('xlsx', nargs='?', default=r'Results\CFB_2026_Results.xlsx')
ap.add_argument('--season', type=int, default=2026)
ap.add_argument('--apply', action='store_true')
a = ap.parse_args()

ws = openpyxl.load_workbook(a.xlsx, read_only=True, data_only=True).worksheets[0]
rows = list(ws.iter_rows(values_only=True))
hdr = list(rows[0])
col = {h: hdr.index(h) for h in
       ('Date', 'Season', 'Team', 'Opp', 'PointsFor', 'PointsAgainst', 'OT')}


def slug(s):
    return re.sub(r'[^a-z0-9]+', '-', (s or '').lower().replace('&', ' ')).strip('-')


def close(code, name_slug):
    return (code == name_slug or name_slug.startswith(code)
            or code.startswith(name_slug))


# one entry per played game that has an OT value (the sheet has two rows per game)
seen, games = set(), []
for r in rows[1:]:
    if (r[col['Season']] != a.season or r[col['PointsFor']] is None
            or r[col['OT']] is None):
        continue
    d = r[col['Date']].strftime('%Y-%m-%d')
    key = (d, frozenset((r[col['Team']], r[col['Opp']])))
    if key in seen:
        continue
    seen.add(key)
    games.append((d, r[col['Team']], r[col['Opp']],
                  int(r[col['PointsFor']]), int(r[col['PointsAgainst']]),
                  int(r[col['OT']])))

con = sqlite3.connect(DB)
db = con.execute('select game_id, substr(date,1,10), home_code, away_code, '
                 'home_pts, away_pts, ot from games where season=?',
                 (a.season,)).fetchall()
by_date = defaultdict(list)
for g in db:
    by_date[g[1]].append(g)

changes, missing, ambiguous = [], [], []
for d, t, o, pf, pa, ot in games:
    c = [g for g in by_date.get(d, [])
         if (g[4], g[5]) == (pf, pa) or (g[5], g[4]) == (pf, pa)]
    if len(c) > 1:
        ts, os_ = slug(t), slug(o)

        def fit(g):
            return (int(close(g[2], ts) or close(g[3], ts))
                    + int(close(g[2], os_) or close(g[3], os_)))
        best = max(fit(g) for g in c)
        c = [g for g in c if fit(g) == best]
    if len(c) == 1:
        if c[0][6] != ot:
            changes.append((ot, c[0][0], d, t, o, pf, pa))
    elif not c:
        missing.append((d, t, o, pf, pa))
    else:
        ambiguous.append((d, t, o, pf, pa))

print(f'{len(games)} played games in the sheet for {a.season}')
print(f'{len(missing)} not in the DB yet (run add_season first), '
      f'{len(ambiguous)} ambiguous')
for x in ambiguous:
    print('  AMBIGUOUS', x)
print(f'{len(changes)} games would change ot:')
for ot, gid, d, t, o, pf, pa in changes:
    print(f'  game {gid}  {d}  {t} {pf}, {o} {pa}  -> ot={ot}')

if not a.apply:
    print('\nDRY RUN. Rerun with --apply to write.')
else:
    con.executemany('update games set ot=? where game_id=?',
                    [(ot, gid) for ot, gid, *_ in changes])
    con.commit()
    n = con.execute('select count(*) from games where season=? and ot=1',
                    (a.season,)).fetchone()[0]
    print(f'\napplied {len(changes)} changes; {n} games now have ot=1 in {a.season}')
    print('Now run: python rebuild_ratings_only.py')