# TRACER Sports — Day-to-Day Operations Guide

## The two folders, and what they're for

| Folder | Branch | Purpose |
|---|---|---|
| `C:\Users\tjsut\TRACERsports` | `main` | **Production.** The live site (private GitHub repo) + all three ready sports: NBA, WNBA, NFL. |
| `C:\Users\tjsut\TracerProjects2` | `master` | **Dev/staging.** Full historical archive, all sports, where new pipelines get built/tested before going live. |

You do daily update work in `TRACERsports` (`main`). `TracerProjects2` is for building new things, not routine updates.

The site's root URL (`tracersports.net` / `localhost:3000` with nothing after it) is a homepage — a "Today's Games" strip (only shows leagues with something happening today) plus live top-3 rankings per league. Nothing about your daily routine changes because of this — it updates automatically off the same `games`/`schedule` tables everything else reads from.

---

## Rating variants: Echo and Pulse

The site computes **two** Elo rating variants for every league, side by side:

- **Echo** — the original continuous model. A team's rating partially carries over from one season to the next.
- **Pulse** — same underlying engine, but every team resets fully to the base rating at the start of each season.

You never trigger these separately — every command in this guide updates **both** variants automatically in one run. There's no `--variant` flag to remember for daily updates.

**NFL-specific note:** NFL also has its own per-season tuning system (`param_schedule.json`), separate from the Echo/Pulse split — Pulse always uses whatever tuned parameters Echo has for that season, just with the carryover (`alpha`) forced to 0. You don't need to do anything differently for this; it's automatic.

---

## 1. Daily update: add new game results

**Always run this from `DBs\`, not from inside `DBs\nfl\`, `DBs\nba\`, or `DBs\wnba\`.** Every league's `add_season.py`/`export_to_supabase.py` write to a path that's relative to whatever directory you're standing in — running from the wrong directory doesn't error, it just silently starts writing to a second, different copy of the database that the rest of the pipeline never sees again.

### NBA / NFL
```
cd C:\Users\tjsut\TRACERsports\DBs
python nfl\add_season.py nfl\Results\NFL_2026_Results.xlsx
```
*(Swap `nfl` for `nba`, both places, for that league.)*

### WNBA — one extra step first
WNBA's results sheet ships with blank score columns that need to be filled in from ESPN before `add_season.py` can process them. Run `update_wnba_results.py` first, then `add_season.py` as normal:
```
cd C:\Users\tjsut\TRACERsports\DBs
python update_wnba_results.py --file wnba\Results\WNBA_2026_Results.xlsx --start 2026-05-08 --end today
python wnba\add_season.py wnba\Results\WNBA_2026_Results.xlsx
```
`update_wnba_results.py` pulls final scores from ESPN's public scoreboard API and validates that every game's home/away rows agree before saving — if a date's game doesn't match cleanly, it prints the problem and leaves that row untouched rather than guessing, so it's safe to run repeatedly. If `--start`/`--end`/`--date` are left off entirely, it scans the whole sheet and fetches every date that's still blank and not in the future.

This updates `DBs\{league}_elo.db` directly (top level of `DBs\`, **not** `DBs\{league}\{league}_elo.db`) — the same file the export script reads from. The printed output runs through **both variants**, one after the other — you'll see an `=== echo ===` block followed by an `=== pulse ===` block. Both are normal and expected on every run.

Two things worth knowing:
- The projection step runs 1,000 Monte Carlo trials per variant, so the command takes roughly twice as long as a single-variant run would.
- Once a league's regular season ends (no games left to simulate), you'll stop seeing the "Updated season projection" line for that league — expected, not an error. The relevant projection columns on that league's Power Rankings page automatically disappear when this happens and come back on their own once the next season starts.

## 2. Push the update to the live site (Supabase)
```
python export_to_supabase.py --league nfl --db nfl_elo.db
```
(Still run from `DBs\`.) This is what actually updates what visitors see, **for both Echo and Pulse in the same run**. Skipping this step means the site shows stale data even though your local files are correct.

Worth running with `--dry-run` first any time you're unsure — it reports what it *would* do without touching Supabase:
```
python export_to_supabase.py --league nfl --db nfl_elo.db --dry-run
```

## 3. Commit and push to GitHub
```
cd C:\Users\tjsut\TRACERsports
git add .
git commit -m "Add [date] results"
git push origin main
```

**Full daily sequence, back to back:**

NBA / NFL:
```
cd C:\Users\tjsut\TRACERsports\DBs
python nfl\add_season.py nfl\Results\NFL_2026_Results.xlsx
python export_to_supabase.py --league nfl --db nfl_elo.db
cd ..
git add .
git commit -m "Add [date] results"
git push origin main
```

WNBA:
```
cd C:\Users\tjsut\TRACERsports\DBs
python update_wnba_results.py --file wnba\Results\WNBA_2026_Results.xlsx --start 2026-05-08 --end today
python wnba\add_season.py wnba\Results\WNBA_2026_Results.xlsx
python export_to_supabase.py --league wnba --db wnba_elo.db
cd ..
git add .
git commit -m "Add [date] results"
git push origin main
```

---

## 4. Checking the site locally before/after an update
```
cd C:\Users\tjsut\TRACERsports
npm run dev
```
Then open `http://localhost:3000/nfl?variant=echo` (or `/nba`, `/wnba`) in a browser. Use the **Echo / Pulse toggle** in the site's nav bar to switch — it updates the `?variant=` URL param for you. `echo` is the default if the param is left off. Bare `http://localhost:3000` shows the homepage.

## 5. Syncing your local folder with what's on GitHub
```
cd C:\Users\tjsut\TRACERsports
git status
git pull origin main
```
Run `git status` first — if it shows uncommitted changes, commit or stash them before pulling.

## 6. Switching between the two folders' branches
```
cd C:\Users\tjsut\TRACERsports
git branch          (shows which branch you're currently on — should be main)
git checkout main   (switches back to main if you're not already there)
```

## 7. When the database structure itself changes (new tables/columns)

- **Locally:** nothing extra to do. `add_season.py` (via each league's `db.py`) applies new table definitions to your local `.db` file automatically the next time you run it.
- **On Supabase:** this does **not** happen automatically. **Never re-run the whole `schema.sql` file against a database that already has data in it** — the table/index definitions in it are all safe to re-run (`IF NOT EXISTS` guards), but the `CREATE POLICY` statements aren't, and a second run fails outright on those. Whenever a schema change is needed, ask Claude for the **specific, minimal SQL snippet** for just that change (e.g. `ALTER TABLE games ADD COLUMN IF NOT EXISTS t INTEGER DEFAULT 0;`) and run only that in the Supabase SQL Editor.
- If you're ever unsure whether a schema change has already been applied, just ask Claude to check, or try running the export with `--dry-run` — a clean run means it's already there.

---

## Rules of thumb

- **Run `add_season.py` from `DBs\`, always.** This is the single most important habit in this whole guide.
- **WNBA needs `update_wnba_results.py` run first, every time**, before `add_season.py` — the sheet won't have real scores otherwise.
- **Always run `export_to_supabase.py` after `add_season.py`.** The local `.db` update alone does nothing for the live site.
- **Echo and Pulse update together, automatically, on every run.**
- **`TracerProjects2` is not connected to the live site at all.**
- **If site numbers ever look wrong**, the first thing to check is: was the last `add_season.py` run actually from `DBs\`? Compare row/date counts between `DBs\{league}_elo.db` and `DBs\{league}\{league}_elo.db` if there's ever doubt — if they don't match, the subfolder file drifted again. **This isn't hypothetical** — it happened for real with WNBA (see handoff), cost a chunk of a session to untangle, and left a stray copy of `wnba_elo.db` sitting around that has since been deleted. NFL currently has a similar two-copy situation for a different reason (its color/export scripts always target the top-level file, while its day-to-day pipeline commands run against the subfolder copy) — a permanent fix for that is still on the to-do list.
- **A Cup/in-season-tournament Championship game (NBA or WNBA) is `type='P'`, `round=0.1`.** This is deliberately below `1`, so it's automatically excluded from win-loss records and from playoff-round-max detection without any special-casing — don't invent a new `type` value for this, the existing convention already handles it correctly.
- **If a season's game count or win-loss record ever looks inflated**, check for duplicate rows first: same date/matchup appearing twice with different `type`/`round` values (e.g., an old `type='R'`/`round=NULL` row alongside a correctly-retyped `type='P'` row). This happened for real in 2021's WNBA data — the dedup key in `add_season.py` includes both `type` and `round`, so a game whose typing gets corrected later won't be recognized as the same game as its old, wrongly-typed version.
- **If `export_to_supabase.py` errors with "no such table" or "no such column,"** it almost always means either (a) you're reading a stale copy of the `.db` predating whatever feature added it — re-run `add_season.py` from `DBs\` first — or (b) a schema change hasn't been applied to Supabase yet (see section 7 above). It does **not** mean something is broken; both are normal, expected states mid-rollout.
- **If `add_season.py` crashes partway through**, nothing from that run is saved — it's one transaction that only commits at the very end. Once the underlying bug is fixed, just re-run the exact same command.
- **NFL-specific: if a game's "round" badge ever shows a raw code you don't recognize** instead of a real label (Wild Card, Divisional, etc.), that's a display bug worth flagging to Claude — NFL's round values are text codes (`WC`/`DV`/`CC`/`SB`), not the numbers NBA/WNBA use, and anywhere that assumes otherwise needs the fix pattern used elsewhere in the codebase (`playoffRoundOrder` + rank-by-position), not a one-off patch.
- **If you ever need to rebuild a league's local database from scratch**, do that in `TracerProjects2` first, test it, then bring the finished `.db` and pipeline scripts over — don't experiment directly in `TRACERsports`.

---

## Getting help from Claude

Paste in:
1. What command you ran and its full output
2. What you expected vs. what happened
3. Whether it's `TRACERsports` or `TracerProjects2`

Since the repo is private, Claude may need to be re-added or reconnected to clone `github.com/thomassutton-afk/TRACERsports` directly to check real current state instead of relying on your description alone. If something looks wrong on the site, a screenshot compared against a real reference (a real bracket, a known real stat) is genuinely one of the most effective ways to catch a bug — that's exactly how several real issues got found and fixed this session.
