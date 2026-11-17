import sqlite3
db = sqlite3.connect('../cfb_elo.db')
for d, a, b in [('2007-01-01','auburn','nebraska'), ('2007-01-01','wisconsin','arkansas'),
                ('2010-10-30','florida','georgia'), ('2012-09-01','alabama','michigan'),
                ('2012-09-29','houston','rice'), ('2012-11-24','baylor','texas-tech')]:
    print(d, a, b)
    q = ('select game_id,date,season,round,home_code,away_code,home_pts,away_pts,neutral from games '
         'where ((home_code=? and away_code=?) or (home_code=? and away_code=?)) '
         'and abs(julianday(substr(date,1,10))-julianday(?))<=3')
    for r in db.execute(q, (a, b, b, a, d)):
        print('  ', r)