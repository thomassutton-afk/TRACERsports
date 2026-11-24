"""Run the new normalize_sr_games.py over every Results file and show only the
files where a tie/0-0 or echo-duplicate guard fired. Writes nothing.
Run from DBs/cfb:  python check_guards.py"""
import contextlib, glob, io

import normalize_sr_games as n

KEYS = ("tied or 0-0", "echo duplicate")
for f in sorted(glob.glob("Results/CFB_*_Results.csv")):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        n.normalize(f)
    text = buf.getvalue()
    if any(k in text for k in KEYS):
        print(f"=== {f}\n{text}")
    else:
        print(f"{f}: clean")
