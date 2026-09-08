import sqlite3

conn = sqlite3.connect("nfl_elo.db")
try:
    conn.execute("ALTER TABLE schedule_predictions ADD COLUMN predicted_spread REAL")
    conn.commit()
    print("nfl_elo.db: added predicted_spread column")
except sqlite3.OperationalError as e:
    print(f"nfl_elo.db: skipped ({e})")
conn.close()
