import argparse, csv, json, os, sqlite3, time, urllib.request
from collections import defaultdict
from datetime import datetime, timedelta

DB = '../cfb_elo.db'
CACHE = 'espn_cache'
URL = ('https://site.api.espn.com/apis/site/v2/sports/football/'
       'college-football/scoreboard?dates={d}&groups={g}&limit=400')


def fetch(d, g):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f'{d}_{g}.json')
    if os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                URL.format(d=d, g=g), headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.load(r)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f)
            time.sleep(0.3)
            return data
        except Exception as e:
            print(f'  retry {d} g{g}: {e}')
            time.sleep(2)
    return {'events': []}


def parse(data):
    out = []
    for ev in data.get('events', []):
        try:
            comps = ev.get('competitions')
            if not comps:
                continue
            comp = comps[0]
            st = comp.get('status') or ev.get('status')
            if not st or not st['type'].get('completed'):
                continue
            t = {c['homeAway']: c for c in comp['competitors']}
            hs, as_ = int(t['home']['score']), int(t['away']['score'])
            period = st.get('period', 4)
            detail = st['type'].get('detail', '')
            out.append(dict(
                id=ev.get('id'),
                ev_date=(ev.get('date') or '')[:16],
                home=t['home']['team'].get('displayName', '?'),
                away=t['away']['team'].get('displayName', '?'),
                hs=hs, as_=as_,
                ot=int(period > 4 or 'OT' in detail),
                ot_disagree=int((period > 4) != ('OT' in detail)),
                neutral=int(bool(comp.get('neutralSite')))))
        except (KeyError, ValueError, TypeError, IndexError):
            continue
    return out


ap = argparse.ArgumentParser()
ap.add_argument('--season', type=int)
ap.add_argument('--max-season', type=int, default=2025)
ap.add_argument('--groups', default='80,81')
ap.add_argument('--apply', action='store_true')
a = ap.parse_args()

con = sqlite3.connect(DB)
q = ('select game_id,date,season,home_team,away_team,home_pts,away_pts,ot '
     'from games where season<=?')
args = [a.max_season]
if a.season:
    q += ' and season=?'
    args.append(a.season)
games = con.execute(q, args).fetchall()

dates = sorted({g[1][:10] for g in games})
needed = set()
for d in dates:
    dt = datetime.strptime(d, '%Y-%m-%d')
    for k in (-1, 0, 1):
        needed.add((dt + timedelta(days=k)).strftime('%Y%m%d'))
print(f'{len(games)} games, {len(needed)} dates to fetch (cached after first run)')

# (YYYYMMDD queried, home_score, away_score) -> {espn_event_id: event}
# keyed by event id so a game listed under both group 80 and 81 counts once
index = defaultdict(dict)
for i, d in enumerate(sorted(needed), 1):
    if i % 100 == 0:
        print(f'  fetched {i}/{len(needed)}')
    for g in a.groups.split(','):
        for e in parse(fetch(d, g)):
            index[(d, e['hs'], e['as_'])][e['id']] = e


def find(dt, hp, ap_):
    for k in (0, -1, 1):   # same date preferred
        d = (dt + timedelta(days=k)).strftime('%Y%m%d')
        c = list(index.get((d, hp, ap_), {}).values())      # same orientation
        if not c:
            c = list(index.get((d, ap_, hp), {}).values())  # flipped (neutral-site swaps)
        if c:
            return c
    return []


rows = []
samples = []
stats = defaultdict(lambda: defaultdict(int))
for gid, date, season, home, away, hp, ap_, db_ot in games:
    dt = datetime.strptime(date[:10], '%Y-%m-%d')
    cands = find(dt, hp, ap_)
    s = stats[season]
    s['games'] += 1
    ot = neutral = dis = ''
    if not cands:
        status = 'unmatched'
        s['unmatched'] += 1
    elif len(cands) == 1:
        e = cands[0]
        status = 'matched'
        ot, neutral, dis = e['ot'], e['neutral'], e['ot_disagree']
        s['unique'] += 1
        s['ot'] += e['ot']
    elif len({c['ot'] for c in cands}) == 1:
        # several ESPN events share this date+score, but they all agree on OT,
        # so which one is the real game does not change the answer
        status = 'matched_agree'
        ot = cands[0]['ot']
        neutral = cands[0]['neutral'] if len({c['neutral'] for c in cands}) == 1 else ''
        dis = max(c['ot_disagree'] for c in cands)
        s['agree'] += 1
        s['ot'] += ot
    else:
        status = 'ambiguous'
        s['ambiguous'] += 1

    info = ' || '.join(f"{c['id']} {c['ev_date']} {c['away']} @ {c['home']} "
                       f"{c['as_']}-{c['hs']} ot={c['ot']}" for c in cands)
    if len(cands) > 1 and len(samples) < 6:
        samples.append((gid, date[:10], hp, ap_, cands))
    rows.append([gid, date, season, home, away, hp, ap_, db_ot,
                 ot, neutral, dis, status, len(cands), info])

out = f"espn_ot_proposed_{a.season or 'all'}.csv"
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['game_id', 'date', 'season', 'home', 'away', 'hp', 'ap', 'db_ot',
                'espn_ot', 'espn_neutral', 'period_vs_detail_disagree', 'status',
                'n_cands', 'cand_info'])
    w.writerows(rows)

print('\nseason games unique agree ambiguous unmatched ot ot%')
for s in sorted(stats):
    x = stats[s]
    got = x['unique'] + x['agree']
    pct = 100 * x['ot'] / got if got else 0
    print(s, x['games'], x['unique'], x['agree'], x['ambiguous'],
          x['unmatched'], x['ot'], f'{pct:.1f}')

print('\nsample games with more than one ESPN candidate:')
for gid, d, hp, ap_, cands in samples:
    print(f'  game {gid} on {d}, DB score home {hp} away {ap_}')
    for c in cands:
        print(f"      id {c['id']}  {c['ev_date']}  {c['away']} @ {c['home']}  "
              f"{c['as_']}-{c['hs']}  ot={c['ot']}")

print(f'\nwrote {out}')

if a.apply:
    n = 0
    for r in rows:
        if r[11] in ('matched', 'matched_agree') and r[8] != '' and int(r[8]) != int(r[7]):
            con.execute('update games set ot=? where game_id=?', (int(r[8]), r[0]))
            n += 1
    con.commit()
    print(f'applied: updated ot on {n} games')