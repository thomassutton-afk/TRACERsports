import csv
import glob
import json
import os
from collections import defaultdict

CACHE = 'espn_cache'
FIRST, LAST = 1996, 2008

# 1) Sports-Reference CSVs: how many games carry anything in the Notes column?
print('Sports-Reference CSV: rows with a Notes entry')
sr = {}
for y in range(FIRST, LAST + 1):
    path = os.path.join('Results', f'CFB_{y}_Results.csv')
    if not os.path.exists(path):
        continue
    with open(path, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.reader(f))[1:]
    withnotes = [r for r in rows if len(r) > 10 and r[10].strip()]
    sr[y] = (len(rows), len(withnotes), [r[10].strip() for r in withnotes[:2]])
    print(f'  {y}: {len(rows):4d} rows, {len(withnotes):4d} with notes   e.g. {sr[y][2]}')

# 2) ESPN pages already cached by backfill_ot.py: is there venue data for old games?
print('\nESPN cache: events, events with a venue name, events flagged neutralSite')
stats = defaultdict(lambda: [0, 0, 0])
samples = defaultdict(list)
armynavy = []
for path in sorted(glob.glob(os.path.join(CACHE, '*_80.json'))):
    y = int(os.path.basename(path)[:4])
    if not FIRST <= y <= LAST:
        continue
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    for ev in data.get('events', []):
        comps = ev.get('competitions') or [{}]
        comp = comps[0]
        venue = comp.get('venue') or {}
        stats[y][0] += 1
        if venue.get('fullName'):
            stats[y][1] += 1
            if len(samples[y]) < 2:
                addr = venue.get('address') or {}
                samples[y].append(f"{ev.get('shortName')} | {venue['fullName']} | {addr.get('city')}, {addr.get('state')}")
        if comp.get('neutralSite'):
            stats[y][2] += 1
        name = (ev.get('shortName') or '').upper()
        if 'ARMY' in name and 'NAVY' in name:
            armynavy.append((ev.get('date', '')[:10], ev.get('shortName'), venue.get('fullName'), comp.get('neutralSite')))
for y in sorted(stats):
    n, v, nt = stats[y]
    print(f'  {y}: {n:4d} events, {v:4d} with venue, {nt:3d} neutralSite   e.g. {samples[y]}')
print('\nArmy-Navy events seen (date, game, venue, neutralSite):')
for a in sorted(set(armynavy)):
    print(' ', a)