import csv, glob, re
pat = re.compile(r'(?<![A-Za-z])(\d*)OT(?![A-Za-z])')
for f in sorted(glob.glob(r'Results\CFB_*_Results.csv')):
    with open(f, newline='', encoding='utf-8-sig') as fh:
        rows = list(csv.DictReader(fh))
    hits = [r for r in rows if pat.search(r.get('Notes') or '')]
    print(f, len(rows), len(hits), [r['Notes'] for r in hits[:2]])