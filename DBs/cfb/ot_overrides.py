import csv, sqlite3, sys

DB = '../cfb_elo.db'
SRC = 'espn_ot_unmatched_all.csv'
WL = 'ot_worklist.csv'


def make():
    rows = [r for r in csv.DictReader(open(SRC, encoding='utf-8-sig'))
            if r['status'] == 'unmatched' and int(r['margin']) <= 8]
    rows.sort(key=lambda r: (r['date'], r['home_code']))
    with open(WL, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['game_id', 'date', 'away', 'home',
                    'away_pts', 'home_pts', 'ot'])
        for r in rows:
            w.writerow([r['game_id'], r['date'], r['away_code'],
                        r['home_code'], r['ap'], r['hp'], ''])
    print(f'wrote {WL} with {len(rows)} games')


def apply():
    con = sqlite3.connect(DB)
    n = blank = 0
    for r in csv.DictReader(open(WL, encoding='utf-8-sig')):
        v = r['ot'].strip()
        if not v:
            blank += 1
            continue
        if v not in ('0', '1'):
            print('skipping bad value:', r)
            continue
        gid = r['game_id']
        gid = int(gid) if gid.isdigit() else gid
        con.execute('update games set ot=? where game_id=?', (int(v), gid))
        n += 1
    con.commit()
    print(f'applied {n} rows, left {blank} blank')


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] in ('make', 'apply'):
        make() if sys.argv[1] == 'make' else apply()
    else:
        print('usage: python ot_overrides.py make | apply')