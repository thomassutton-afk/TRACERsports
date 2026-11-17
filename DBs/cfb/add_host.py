import csv
p = 'pre2008_neutral_review.csv'
rows = list(csv.DictReader(open(p, encoding='utf-8-sig', newline='')))
hosts = [('1999-09-02', 'eastern-washington'),
         ('2005-09-17', 'tulane'), ('2005-10-01', 'tulane'), ('2005-10-08', 'tulane'),
         ('1999-09-18', 'washington-state')]
for r in rows:
    r['host'] = ''
    for d, h in hosts:
        if r['date'][:10] == d and h in (r['home_code'], r['away_code']):
            r['host'] = h
fields = list(rows[0].keys())
with open(p, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
print('host column written;', sum(1 for r in rows if r['host']), 'rows filled')