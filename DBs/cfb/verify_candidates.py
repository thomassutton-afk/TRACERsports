import csv, re, sqlite3
db = sqlite3.connect('../cfb_elo.db'); bad = 0
for r in csv.DictReader(open('bowl_local_candidates2.csv', encoding='utf-8', newline='')):
    h0, hp0, ap0, a0 = re.search(r'\| (\S+) (\d+)-(\d+) (\S+)$', r['info']).groups()
    home, hp, ap, neu = db.execute(
        'select home_code, home_pts, away_pts, neutral from games where game_id=?',
        (r['game_id'],)).fetchone()
    exp = (hp0, ap0) if home == h0 else (ap0, hp0)
    if not (home == r['host'] and neu == 0 and (str(hp), str(ap)) == exp):
        bad += 1; print('CHECK', r['date'], home, hp, ap, neu, '| expected host', r['host'])
print('checked 29 games, problems:', bad)