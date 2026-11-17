import csv, re
for s in range(2016, 2027):
    try: rows = list(csv.reader(open(f'Results/CFB_{s}_Results.csv', encoding='utf-8-sig')))
    except FileNotFoundError: continue
    h = next(i for i, r in enumerate(rows) if r and r[0] == 'Rk'); hd = rows[h]
    w = hd.index('Winner'); ni = len(hd) - 1
    for r in rows[h+1:]:
        if len(r) > ni and r[w+2] == 'N' and r[w+1].strip() and not re.search(r'\(.*\)|\s-\s', r[ni]):
            print(s, r[w].strip(), 'v', r[w+3].strip(), '|', r[ni].strip() or '(blank)')