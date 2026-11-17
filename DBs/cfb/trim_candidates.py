import csv
p = 'bowl_local_candidates2.csv'
drop = {('2006-12-27', frozenset({'florida-state', 'ucla'})),
        ('2015-11-28', frozenset({'illinois', 'northwestern'})),
        ('2015-12-05', frozenset({'southern-california', 'stanford'})),
        ('2017-12-01', frozenset({'southern-california', 'stanford'})),
        ('2017-12-02', frozenset({'oklahoma', 'texas-christian'}))}
rows = list(csv.DictReader(open(p, encoding='utf-8', newline='')))
keep = [r for r in rows if (r['date'], frozenset({r['home_code'], r['away_code']})) not in drop]
with open(p, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(keep)
print('dropped', len(rows) - len(keep), 'kept', len(keep), '(expect 5 and 29)')