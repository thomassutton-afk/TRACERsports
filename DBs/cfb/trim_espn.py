import csv
p = 'espn_local_candidates.csv'
drop = {('2022-12-03', frozenset({'kansas-state', 'texas-christian'})),
        ('2024-08-29', frozenset({'arkansas', 'arkansas-pine-bluff'})),
        ('2024-11-30', frozenset({'northwestern', 'illinois'}))}
rows = list(csv.DictReader(open(p, encoding='utf-8', newline='')))
keep = [r for r in rows if (r['date'], frozenset({r['home_code'], r['away_code']})) not in drop]
with open(p, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(keep)
print('dropped', len(rows) - len(keep), 'kept', len(keep), '(expect 3 and 7)')