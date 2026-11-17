import argparse
import csv
import re
import sqlite3

DB = '../cfb_elo.db'
ESPN = 'espn_ot_proposed_all.csv'

ap = argparse.ArgumentParser()
ap.add_argument('sheet', nargs='?', default='neutral_review.csv')
ap.add_argument('--apply', action='store_true')
a = ap.parse_args()

con = sqlite3.connect(DB)

# ESPN's events per game, used to find the real host when a game goes from
# neutral to non-neutral (see espn_host below).
espn_info = {}
try:
    with open(ESPN, encoding='utf-8-sig', newline='') as f:
        for r in csv.DictReader(f):
            espn_info[r['game_id']] = r['cand_info']
except FileNotFoundError:
    pass


def espn_host(game_id, home_pts, away_pts):
    """'same' if ESPN's home team is the one stored as home, 'FLIPPED' if it
    is the stored away team, None if ESPN's events don't settle it. Compares
    scores, not names: a football game never ends level, so the score pair
    tells which side was ESPN's home team."""
    seen = set()
    for ev in espn_info.get(str(game_id), '').split('||'):
        m = re.search(r'(\d+)-(\d+)\s+ot=', ev)
        if not m:
            continue
        away_s, home_s = int(m.group(1)), int(m.group(2))
        if (away_s, home_s) == (away_pts, home_pts):
            seen.add('same')
        elif (away_s, home_s) == (home_pts, away_pts):
            seen.add('FLIPPED')
    return seen.pop() if len(seen) == 1 else None


changes, unchanged, problems = [], 0, []
with open(a.sheet, encoding='utf-8-sig', newline='') as f:
    for r in csv.DictReader(f):
        v = (r.get('new_neutral') or '').strip()
        if v == '':
            continue
        d, h, aw = r['date'].strip()[:10], r['home_code'].strip(), r['away_code'].strip()
        if v not in ('0', '1'):
            problems.append(f'bad new_neutral {v!r}: {d} {aw} @ {h}')
            continue
        # Matched by date and the two teams in either order, so the sheet keeps
        # working after a swap and after a reload that restores the original order.
        found = con.execute(
            'select game_id, neutral, home_pts, away_pts, home_code, away_code from games '
            'where substr(date,1,10)=? and ((home_code=? and away_code=?) or (home_code=? and away_code=?))',
            (d, h, aw, aw, h)).fetchall()
        if len(found) != 1:
            problems.append(f'{len(found)} games match {d} {aw} @ {h}')
            continue
        gid, cur, hp, ap_, h, aw = found[0]     # from here on, the stored orientation
        new = int(v)
        if cur == new:
            unchanged += 1
            continue

        # A game stored as neutral has its "home" team chosen alphabetically
        # (add_season.py), so before it becomes a normal home game the
        # real host has to be put in the home slot.
        swap = False
        if cur == 1 and new == 0:
            host = (r.get('host') or '').strip()      # optional: the host's team code
            if host:
                if host == aw:
                    swap = True
                elif host != h:
                    problems.append(f'host {host!r} is neither team: {d} {aw} @ {h}')
                    continue
            else:
                o = espn_host(gid, hp, ap_)
                if o is None:
                    problems.append(f'cannot tell who hosted {d} {aw} @ {h}; add the host team code '
                                    'in a "host" column')
                    continue
                swap = (o == 'FLIPPED')
        changes.append((new, swap, gid, d, aw, h, cur))

swaps = [c for c in changes if c[1]]
print(f'{len(changes)} games would change ({len(swaps)} with home and away swapped), '
      f'{unchanged} already match\n')
for new, swap, gid, d, aw, h, cur in changes:
    if swap:
        print(f'  {d}  {aw} @ {h}: neutral {cur} -> {new}, SWAP so {aw} is home')
    else:
        print(f'  {d}  {aw} @ {h}: neutral {cur} -> {new}')
for p in problems:
    print('  PROBLEM', p)

if not a.apply:
    print('\nDRY RUN. Rerun with --apply to write.')
elif problems:
    print('\nNOT applying: fix the PROBLEM lines first.')
else:
    for new, swap, gid, *_ in changes:
        if swap:
            con.execute(
                'update games set home_team=away_team, away_team=home_team, '
                'home_code=away_code, away_code=home_code, home_pts=away_pts, away_pts=home_pts, '
                'home_ap_rank=away_ap_rank, away_ap_rank=home_ap_rank, neutral=? where game_id=?',
                (new, gid))
        else:
            con.execute('update games set neutral=? where game_id=?', (new, gid))
    con.commit()
    print(f'\napplied {len(changes)} changes. Now run: python rebuild_ratings_only.py')
