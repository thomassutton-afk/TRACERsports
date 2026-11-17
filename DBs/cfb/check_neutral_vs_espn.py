import csv
import sqlite3
from collections import Counter

DB = '../cfb_elo.db'
ESPN = 'espn_ot_proposed_all.csv'
OUT = 'neutral_review.csv'
FIRST_SEASON = 2008      # ESPN's neutral flag is empty or 0 before this
SHOW = 60

con = sqlite3.connect(DB)
games = {str(r[0]): r for r in con.execute(
    'select game_id, date, season, round, home_code, away_code, neutral '
    'from games where season >= ?', (FIRST_SEASON,))}

espn = {}
with open(ESPN, encoding='utf-8-sig', newline='') as f:
    for r in csv.DictReader(f):
        if r['espn_neutral'] != '' and r['status'] in ('matched', 'matched_agree', 'matched_name'):
            espn[r['game_id']] = int(r['espn_neutral'])

both = [(g, espn[gid]) for gid, g in games.items() if gid in espn]
print(f'{len(games)} games from {FIRST_SEASON} on in the DB, {len(both)} with an ESPN neutral flag')

agree = sum(1 for g, e in both if g[6] == e)
print(f'agree: {agree}   disagree: {len(both) - agree}\n')


def label(g):
    return g[3] or 'regular season'


tally = Counter()
for g, e in both:
    if g[6] != e:
        tally[(label(g), 'ESPN neutral, DB not' if e else 'DB neutral, ESPN not')] += 1
print('disagreements by round:')
for k, n in sorted(tally.items()):
    print(f'  {k[0]:15s} {k[1]:22s} {n}')

for title, want_espn in (('ESPN says neutral, DB does not (bowls skipped: ESPN calls every bowl neutral):', 1),
                         ('DB says neutral, ESPN does not:', 0)):
    rows = sorted((g for g, e in both if g[6] != e and e == want_espn
                   and not (want_espn == 1 and g[3] == 'BOWL')), key=lambda g: g[1])
    print(f'\n{title} {len(rows)}')
    for g in rows[:SHOW]:
        print(f'  {g[1][:10]}  {g[5]} @ {g[4]}  round={g[3]}')
    if len(rows) > SHOW:
        print(f'  ... and {len(rows) - SHOW} more')

# Everything that disagrees goes into a review sheet. Fill in new_neutral
# (1 or 0) on the rows you want to change, leave the rest blank, and feed the
# file to apply_neutral_overrides.py. You can also add rows by hand (the
# pre-2008 games ESPN can't check); only date, home_code, away_code and
# new_neutral are read back.
with open(OUT, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['date', 'home_code', 'away_code', 'new_neutral',
                'round', 'db_neutral', 'espn_neutral', 'season', 'game_id'])
    for g, e in sorted(both, key=lambda x: x[0][1]):
        if g[6] != e:
            w.writerow([g[1][:10], g[4], g[5], '', g[3] or '', g[6], e, g[2], g[0]])
print(f'\nwrote {OUT} ({sum(tally.values())} rows to review)')