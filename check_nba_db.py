import sqlite3

def list_tables(path):
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("select name from sqlite_master where type='table' order by name;")
    tables = [row[0] for row in cur.fetchall()]
    conn.close()
    return tables

top = list_tables("nba_elo.db")
nested = list_tables("DBs/nba/nba_elo.db")

print("Top-level nba_elo.db tables:", top)
print("DBs/nba/nba_elo.db tables:", nested)

missing = set(nested) - set(top)
if missing:
    print("MISMATCH — tables missing from top-level copy:", missing)
else:
    print("Table sets match.")