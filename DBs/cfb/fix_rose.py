import csv
p = 'pre2008_neutral_review.csv'
rows = list(csv.DictReader(open(p, encoding='utf-8-sig', newline='')))
for r in rows:
    if r['date'][:10] == '2008-01-01' and 'southern-california' in (r['home_code'], r['away_code']):
        r['new_neutral'] = '0'; r['host'] = 'southern-california'
with open(p, 'w', encoding='utf-8', newline='') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)