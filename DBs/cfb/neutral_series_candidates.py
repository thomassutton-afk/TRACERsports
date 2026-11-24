import csv
import sqlite3
from collections import defaultdict

DB = '../cfb_elo.db'
OUT = 'neutral_series_candidates.csv'
LAST_SEASON = 2007          # 2008 on is covered by check_neutral_vs_espn.py
MIN_NEUTRAL = 3             # a pair needs at least this many neutral meetings...
MIN_SHARE = 0.6             # ...making up at least this share of all its meetings

con = sqlite3.connect(DB)
pairs = defaultdict(list)
for gid, date, season, rnd, h, a, n in con.execute(
        'select game_id, substr(date,1,10), season, round, home_code, away_code, neutral from games'):
    pairs[frozenset((h, a))].append((gid, date, season, rnd, h, a, n))

rows = []
for pair, games in pairs.items():
    neutral = sum(g[6] for g in games)
    if neutral < MIN_NEUTRAL or neutral / len(games) < MIN_SHARE:
        continue
    for gid, date, season, rnd, h, a, n in games:
        if n == 0 and season <= LAST_SEASON:
            rows.append([date, h, a, '1', rnd or '', neutral, len(games), season, gid])

rows.sort()
with open(OUT, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['date', 'home_code', 'away_code', 'new_neutral', 'round',
                'pair_neutral_games', 'pair_total_games', 'season', 'game_id'])
    w.writerows(rows)

print(f'{len(rows)} unflagged games between pairs that are neutral almost every time:')
for r in rows:
    print(f'  {r[0]}  {r[2]} @ {r[1]}   (pair is neutral in {r[5]} of {r[6]} meetings)')
print(f'\nwrote {OUT}, new_neutral prefilled with 1. Delete any row you disagree with, then run:')
print(f'  python apply_neutral_overrides.py {OUT}            (dry run)')
print(f'  python apply_neutral_overrides.py {OUT} --apply')