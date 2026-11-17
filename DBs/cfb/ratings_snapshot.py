import csv, glob, os, sqlite3, sys


def tables(con):
    return [r[0] for r in con.execute(
        "select name from sqlite_master where type='table' "
        "and name like 'ratings%' order by name")]


def dump(db, prefix):
    con = sqlite3.connect(db)
    for t in tables(con):
        cur = con.execute(f'select * from "{t}" order by rowid')
        cols = [d[0] for d in cur.description]
        path = f'{prefix}_{t}.csv'
        n = 0
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(cols)
            for row in cur:
                w.writerow(row)
                n += 1
        print(f'{t}: {n} rows, {len(cols)} columns -> {path}')


def load(path):
    with open(path, newline='', encoding='utf-8') as f:
        r = csv.reader(f)
        cols = next(r)
        return cols, list(r)


def same(a, b):
    if a == b:
        return True
    try:
        return abs(float(a) - float(b)) < 1e-9
    except ValueError:
        return False


def compare(pa, pb):
    for fa in sorted(glob.glob(f'{pa}_*.csv')):
        table = fa[len(pa) + 1:-4]
        fb = f'{pb}_{table}.csv'
        print(f'\n{table}')
        if not os.path.exists(fb):
            print('  missing', fb)
            continue
        ca, ra = load(fa)
        cb, rb = load(fb)
        only_a = [c for c in ca if c not in cb]
        only_b = [c for c in cb if c not in ca]
        if only_a:
            print('  columns only in the first dump: ', only_a)
        if only_b:
            print('  columns only in the second dump:', only_b)
        if len(ra) != len(rb):
            print(f'  row count differs: {len(ra)} vs {len(rb)}')
            continue
        shared = [c for c in ca if c in cb]
        ia = {c: i for i, c in enumerate(ca)}
        ib = {c: i for i, c in enumerate(cb)}
        diff = {c: 0 for c in shared}
        for x, y in zip(ra, rb):
            for c in shared:
                if not same(x[ia[c]], y[ib[c]]):
                    diff[c] += 1
        bad = {c: n for c, n in diff.items() if n}
        print(f'  compared {len(shared)} shared columns over {len(ra)} rows')
        print('  shared columns that changed:', bad if bad else 'none')


def check_neutral(db):
    """ratings.neutral must equal games.neutral for every row, in every variant."""
    con = sqlite3.connect(db)
    cols = [r[1] for r in con.execute('pragma table_info(ratings)')]
    if 'neutral' not in cols:
        print('ratings has no neutral column yet')
        return
    total, bad = con.execute(
        'select count(*), sum(case when r.neutral <> coalesce(g.neutral, 0) then 1 else 0 end) '
        'from ratings r left join games g on g.game_id = r.game_id').fetchone()
    print(f'{total} ratings rows; {bad or 0} disagree with games.neutral')
    for v, n, k in con.execute(
            'select variant, count(*), sum(neutral) from ratings group by variant'):
        print(f'  {v}: {n} rows, {k} flagged neutral')


if __name__ == '__main__' and len(sys.argv) >= 4 and sys.argv[1] == 'dump':
    dump(sys.argv[2], sys.argv[3])
elif __name__ == '__main__' and len(sys.argv) >= 4 and sys.argv[1] == 'compare':
    compare(sys.argv[2], sys.argv[3])
elif __name__ == '__main__' and len(sys.argv) >= 3 and sys.argv[1] == 'neutral':
    check_neutral(sys.argv[2])
else:
    print('usage: python ratings_snapshot.py dump <db> <prefix>')
    print('       python ratings_snapshot.py compare <prefixA> <prefixB>')
    print('       python ratings_snapshot.py neutral <db>')
