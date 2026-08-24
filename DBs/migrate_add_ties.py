import sqlite3

for dbfile in ["nba_elo.db", "wnba_elo.db"]:
    conn = sqlite3.connect(dbfile)
    try:
        conn.execute("ALTER TABLE ratings ADD COLUMN t REAL DEFAULT 0")
        conn.commit()
        print(f"{dbfile}: added t column")
    except sqlite3.OperationalError as e:
        print(f"{dbfile}: skipped ({e})")
    conn.close()