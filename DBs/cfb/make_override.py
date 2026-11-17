import csv, sqlite3
db = sqlite3.connect('../cfb_elo.db')
want = [(2023, 'ucla', 'boise-state', 'ucla'),
        (2023, 'boston-college', 'southern-methodist', 'boston-college'),
        (2025, 'houston', 'louisiana-state', 'houston')]
rows = []
for season, a, b, host in want:
    g = db.execute('select substr(date,1,10), home_code, away_code, neutral from games '
                   'where season=? and ((home_code=? and away_code=?) or (home_code=? and away_code=?))',
                   (season, a, b, b, a)).fetchall()
    if len(g) != 1 or g[0][3] != 1:
        print('CHECK', season, a, b, g); continue
    rows.append([g[0][0], g[0][1], g[0][2], 0, host])
with open('override_2022plus.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['date', 'home_code', 'away_code', 'new_neutral', 'host']); w.writerows(rows)
print(len(rows), 'rows -> override_2022plus.csv')