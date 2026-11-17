import argparse, csv, json, os, re, sqlite3, sys, time, urllib.request
from collections import defaultdict
from datetime import datetime, timedelta

DB = '../cfb_elo.db'
CACHE = 'espn_cache'
URL = ('https://site.api.espn.com/apis/site/v2/sports/football/'
       'college-football/scoreboard?dates={d}&groups={g}&limit=400')
FAILED = []


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
    FAILED.append((d, g))   # not cached, so a rerun will try again
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
            ls = max(len(t['home'].get('linescores') or []),
                     len(t['away'].get('linescores') or []))
            sigs = [period > 4, 'OT' in detail]
            if ls:
                sigs.append(ls > 4)      # more than 4 periods of scoring
            out.append(dict(
                id=ev.get('id'),
                ev_date=(ev.get('date') or '')[:16],
                home=t['home']['team'].get('displayName', '?'),
                away=t['away']['team'].get('displayName', '?'),
                hs=hs, as_=as_,
                ot=int(any(sigs)),
                ot_disagree=int(any(sigs) and not all(sigs)),
                neutral=int(bool(comp.get('neutralSite')))))
        except (KeyError, ValueError, TypeError, IndexError):
            continue
    return out


def slug(s):
    s = (s or '').lower().replace('&', ' ')
    return re.sub(r'[^a-z0-9]+', '-', s).strip('-')


def side_hit(code, name):
    if not code:
        return 0
    n = slug(name)
    return int(n == code or n.startswith(code + '-'))


def name_score(c, hcode, acode):
    same = side_hit(hcode, c['home']) + side_hit(acode, c['away'])
    flip = side_hit(hcode, c['away']) + side_hit(acode, c['home'])
    return max(same, flip)


ap = argparse.ArgumentParser()
ap.add_argument('--season', type=int)
ap.add_argument('--max-season', type=int, default=2025)
ap.add_argument('--groups', default='80,81')
ap.add_argument('--apply', action='store_true')
a = ap.parse_args()

con = sqlite3.connect(DB)
q = ('select game_id,date,season,home_team,away_team,home_pts,away_pts,ot,'
     'home_code,away_code from games where season<=?')
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
index = defaultdict(dict)
for i, d in enumerate(sorted(needed), 1):
    if i % 100 == 0:
        print(f'  fetched {i}/{len(needed)}')
    for g in a.groups.split(','):
        for e in parse(fetch(d, g)):
            index[(d, e['hs'], e['as_'])][e['id']] = e


def find(dt, hp, ap_):
    for k in (0, -1, 1):
        d = (dt + timedelta(days=k)).strftime('%Y%m%d')
        c = list(index.get((d, hp, ap_), {}).values())
        if not c:
            c = list(index.get((d, ap_, hp), {}).values())
        if c:
            return c
    return []


rows = []
review = []
still_ambiguous = []
stats = defaultdict(lambda: defaultdict(int))
for gid, date, season, home, away, hp, ap_, db_ot, hcode, acode in games:
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
        s['ot'] += ot
    elif len({c['ot'] for c in cands}) == 1:
        status = 'matched_agree'
        ot = cands[0]['ot']
        neutral = cands[0]['neutral'] if len({c['neutral'] for c in cands}) == 1 else ''
        dis = max(c['ot_disagree'] for c in cands)
        s['agree'] += 1
        s['ot'] += ot
    else:
        scores = [name_score(c, hcode, acode) for c in cands]
        best = max(scores)
        top = [c for c, sc in zip(cands, scores) if sc == best]
        if best >= 1 and len(top) == 1:
            e = top[0]
            status = 'matched_name'
            ot, neutral, dis = e['ot'], e['neutral'], e['ot_disagree']
            s['name'] += 1
            s['ot'] += ot
        else:
            status = 'ambiguous'
            s['ambiguous'] += 1
            still_ambiguous.append((gid, date[:10], hcode, acode, hp, ap_, cands))

    if dis == 1:
        s['dis'] += 1
    if status in ('unmatched', 'ambiguous'):
        review.append([season, date[:10], gid, home, away, hcode, acode,
                       hp, ap_, abs(hp - ap_), status])

    info = ' || '.join(f"{c['id']} {c['ev_date']} {c['away']} @ {c['home']} "
                       f"{c['as_']}-{c['hs']} ot={c['ot']}" for c in cands)
    rows.append([gid, date, season, home, away, hcode, acode, hp, ap_, db_ot,
                 ot, neutral, dis, status, len(cands), info])

tag = a.season or 'all'
out = f'espn_ot_proposed_{tag}.csv'
with open(out, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['game_id', 'date', 'season', 'home', 'away', 'home_code', 'away_code',
                'hp', 'ap', 'db_ot', 'espn_ot', 'espn_neutral',
                'signals_disagree', 'status', 'n_cands', 'cand_info'])
    w.writerows(rows)

rev_out = f'espn_ot_unmatched_{tag}.csv'
with open(rev_out, 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f)
    w.writerow(['season', 'date', 'game_id', 'home', 'away', 'home_code',
                'away_code', 'hp', 'ap', 'margin', 'status'])
    w.writerows(sorted(review))

print('\nseason games unique agree name ambiguous unmatched ot ot% sig_disagree')
for s in sorted(stats):
    x = stats[s]
    got = x['unique'] + x['agree'] + x['name']
    pct = 100 * x['ot'] / got if got else 0
    print(s, x['games'], x['unique'], x['agree'], x['name'], x['ambiguous'],
          x['unmatched'], x['ot'], f'{pct:.1f}', x['dis'])

if still_ambiguous:
    print(f'\n{len(still_ambiguous)} still ambiguous (showing up to 15):')
    for gid, d, hc, ac, hp, ap_, cands in still_ambiguous[:15]:
        print(f'  game {gid} on {d}: {ac} @ {hc}  (DB score {ap_}-{hp})')
        for c in cands:
            print(f"      id {c['id']}  {c['away']} @ {c['home']}  ot={c['ot']}")

print(f'\nFETCH FAILURES: {len(FAILED)}', FAILED[:10])
print(f'wrote {out} and {rev_out}')

if a.apply:
    if FAILED:
        print('NOT applying: some ESPN requests failed. Rerun (cached pages are '
              'reused) until FETCH FAILURES is 0.')
        sys.exit(1)
    n = 0
    for r in rows:
        if r[13] in ('matched', 'matched_agree', 'matched_name') and r[10] != '' \
                and int(r[10]) != int(r[9]):
            con.execute('update games set ot=? where game_id=?', (int(r[10]), r[0]))
            n += 1
    con.commit()
    print(f'applied: updated ot on {n} games')