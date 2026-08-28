import re, pathlib

ROOT = pathlib.Path("DBs")
LEAGUES = ["nba", "wnba", "nfl"]
changed = []

for league in LEAGUES:
    league_dir = ROOT / league
    for f in league_dir.glob("*.py"):
        text = f.read_text()
        m = re.search(r'^DB_PATH = "(\w+_elo\.db)"$', text, flags=re.MULTILINE)
        if not m:
            continue
        dbname = m.group(1)
        old_line = f'DB_PATH = "{dbname}"'
        new_line = (
            f'DB_PATH = os.path.join(\n'
            f'    os.path.dirname(os.path.abspath(__file__)), "..", "{dbname}"\n'
            f')'
        )
        text = text.replace(old_line, new_line, 1)
        if not re.search(r'^import os$', text, flags=re.MULTILINE):
            text = "import os\n" + text
        f.write_text(text)
        changed.append(str(f))

print("Patched", len(changed), "files:")
for c in changed:
    print(" ", c)