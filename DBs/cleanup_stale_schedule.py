import sqlite3, sys

DB = sys.argv[1] if len(sys.argv) > 1 else "wnba_elo.db"
conn = sqlite3.connect(DB)
conn.execute("PRAGMA foreign_keys = ON")

rows = conn.execute("""
    SELECT s.schedule_id, s.date, s.type, s.round, h.team_name, a.team_name
    FROM schedule s
    JOIN teams h ON h.team_id = s.home_team
    JOIN teams a ON a.team_id = s.away_team
    WHERE s.date = '2026-09-29'
""").fetchall()

if not rows:
    print("No schedule rows dated 2026-09-29 found — nothing to do.")
    sys.exit(0)

print("About to delete these stale schedule row(s):")
ids = []
for schedule_id, d, type_, rnd, home, away in rows:
    print(f"  schedule_id={schedule_id}  {d}  Type={type_} Round={rnd}  {away} @ {home}")
    ids.append(schedule_id)

placeholders = ",".join("?" * len(ids))
conn.execute(f"DELETE FROM schedule_predictions WHERE schedule_id IN ({placeholders})", ids)
conn.execute(f"DELETE FROM schedule WHERE schedule_id IN ({placeholders})", ids)
conn.commit()
print(f"\nDeleted {len(ids)} schedule row(s) and their predictions.")
