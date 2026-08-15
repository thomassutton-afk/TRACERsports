# TRACER Sports — Day-to-Day Operations Guide

## The two folders, and what they're for

| Folder | Branch | Purpose |
|---|---|---|
| `C:\Users\tjsut\tracersports-app` | `main` | **Production.** The live site (public GitHub repo) + only the sports that are ready (currently NBA, WNBA). |
| `C:\Users\tjsut\TracerProjects2` | `master` | **Dev/staging.** Full historical archive, all sports, where new pipelines get built/tested before going live. |

You do daily update work in `tracersports-app` (`main`). `TracerProjects2` is for building new things, not routine updates.

The site's root URL (`tracersports.net` / `localhost:3000` with nothing after it) is now a real homepage — a "Today's Games" strip (only shows leagues with something happening today) plus live top-3 rankings per league. Nothing about your daily routine changes because of this — it updates automatically off the same `games`/`schedule` tables everything else reads from.

---

## Rating variants: Echo and Pulse

The site computes **two** Elo rating variants for every league, side by side:

- **Echo** — the original continuous model. A team's rating partially carries over from one season to the next (season-to-season regression toward the mean, not a hard reset).
- **Pulse** — same underlying engine, but every team resets fully to the base rating (1500) at the start of each season.

You never trigger these separately — every command in this guide (`add_season.py`, `export_to_supabase.py`) updates **both** variants automatically in one run. There's no `--variant` flag to remember for daily updates; the split only matters when you're checking output or browsing the site (see below).

---

## 1. Daily update: add new game results (WNBA example — same for NBA)

**Always run this from `DBs\`, not from inside `DBs\nba\` or `DBs\wnba\`.** Both leagues'
`add_season.py` write to a `DB_PATH` that's relative to whatever directory you're standing
in when you run the command — running from the wrong directory doesn't error, it just
silently starts writing to a second, different copy of the database in the subfolder that
the rest of the pipeline (and the export script) never sees again. This has happened for
real, more than once, with both NBA and WNBA, and it's always a pain to untangle. Always
running from `DBs\` means there's only ever one file per league, and it's always the one
the export script reads from — no separate "copy it up" step needed.

```
cd C:\Users\tjsut\TRACERsports\DBs
python wnba\add_season.py wnba\Results\WNBA_2026_Results.xlsx
```
*(Swap `wnba` for `nba`, both places, for the NBA side.)*

This updates `DBs\wnba_elo.db` directly — the same file the export script reads from. The
printed output now runs through **both variants, one after the other** — you'll see an
`=== echo ===` block followed by an `=== pulse ===` block, each with its own standings, its
own "Updated Elo predictions for N upcoming game(s)" line, and its own "Updated season
projection for [season]: N team(s)" line. Both blocks are normal and expected on every run —
seeing standings printed twice isn't a bug.

Two things worth knowing:
- The projection step runs 1,000 Monte Carlo trials over the remaining schedule, and it now
  does this **once per variant** — so the command takes roughly twice as long to finish as it
  used to. That's expected, not a hang.
- Once a league's regular season ends (no games left to simulate), you'll stop seeing the
  "Updated season projection" line for that league — that's expected too, not an error.
  `Proj. W` / `10th–90th` / `P(1st)` columns on that league's Power Rankings page
  automatically disappear when this happens, and come back on their own once the next
  season starts producing projection data again. Nothing to do on your end either way.

## 2. Push the update to the live site (Supabase)
```
python export_to_supabase.py --league wnba --db wnba_elo.db
```
(Still run from `DBs\`.) This is what actually updates what visitors see — teams, games,
schedule, and season projections, **for both Echo and Pulse in the same run**. Skipping this
step means the site shows stale data even though your local files are correct.

## 3. Commit and push to GitHub (so the update is backed up / on record)
```
cd C:\Users\tjsut\TRACERsports
git add .
git commit -m "Add [date] results"
git push origin main
```

**Full daily sequence, back to back:**
```
cd C:\Users\tjsut\tracersports-app\DBs
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
cd C:\Users\tjsut\tracersports-app
npm run dev
```
Then open `http://localhost:3000/wnba?variant=echo` (or `/nba`) in a browser. Use the
**Echo / Pulse toggle** in the site's nav bar to switch between variants — it updates the
`?variant=` URL param for you. `echo` is the default if the param is left off entirely.
Bare `http://localhost:3000` shows the new homepage.

## 5. Syncing your local folder with what's on GitHub

If you're not sure your local `tracersports-app` folder matches GitHub (e.g. you made changes elsewhere, or it's been a while):
```
cd C:\Users\tjsut\tracersports-app
git status
git pull origin main
```
Run `git status` first — if it shows uncommitted changes, commit or stash them before pulling, or you'll get an error.

## 6. Switching between the two folders' branches

You generally shouldn't need to do this day-to-day, but if you ever end up on the wrong branch:
```
cd C:\Users\tjsut\tracersports-app
git branch          (shows which branch you're currently on — should be main)
git checkout main   (switches back to main if you're not already there)
```

## 7. When the database structure itself changes (new tables/columns)

Most days you'll never touch this section — it only applies when a new feature adds
something new to `schema.sql`. Two separate things need to happen, and neither one happens
automatically:

- **Locally:** nothing extra to do. `add_season.py` (via `db.py`) applies any new table
  definitions to your local `.db` file automatically the next time you run it — including,
  if needed, a one-time migration of existing tables.
- **On Supabase:** this does NOT happen automatically. `schema.sql` is just a blueprint —
  Supabase only picks up a new table or index when you manually paste its `CREATE TABLE` /
  `CREATE INDEX` statements into the Supabase SQL Editor and run them, one time. If you skip
  this, `export_to_supabase.py` will fail with an error like `relation "season_projections"
  does not exist` (or similar, for whatever's new) — that error means the Supabase side
  hasn't been updated yet, not that anything is broken locally.

If you're ever unsure whether a given schema change has already been applied to Supabase,
just ask Claude to check, or try running the export — a clean run means it's already there.

---

## Rules of thumb

- **Run `add_season.py` from `DBs\`, always** — `python wnba\add_season.py wnba\Results\...`
  or `python nba\add_season.py nba\Results\...`, never `cd` into the league's own subfolder
  first. This is the single most important habit in this whole guide — running from the
  wrong place doesn't error, it just silently starts writing to a second, different file
  that the rest of the pipeline never sees again until someone notices the site looks stale.
- **Always run `export_to_supabase.py` after `add_season.py`.** The local `.db` update alone does nothing for the live site.
- **Echo and Pulse update together, automatically, on every run.** There's no separate command or flag for the second variant — if the site's numbers look right for Echo but wrong for Pulse (or vice versa), that points to a real bug worth flagging, not a step you forgot.
- **`TracerProjects2` is not connected to the live site at all.** Nothing you do there shows up on tracersports.net until you manually bring specific files over to `tracersports-app`.
- **If site numbers ever look wrong** (bad records, mismatched standings, missing recent games), the first thing to check is: was the last `add_season.py` run actually from `DBs\`? If there's any doubt, compare `DBs\{league}_elo.db`'s row/date via
  ```
  python -c "import sqlite3; c=sqlite3.connect('nba_elo.db'); print(c.execute('SELECT COUNT(*) FROM games').fetchone()); print(c.execute('SELECT MAX(date) FROM games').fetchone())"
  ```
  against the same check on `DBs\nba\nba_elo.db` (or `wnba\...`) — if they don't match, the
  subfolder file drifted again; whichever one is more current is almost certainly the real
  one, but confirm before overwriting anything.
- **If `export_to_supabase.py` errors with "no such table" for something you know exists locally,** it almost always means the same thing as the point above: you're reading a copy of the `.db` that predates whatever feature added that table (or you're reading the wrong copy entirely — see the point above). Re-run `add_season.py` from `DBs\` first, then re-try the export.
- **If `add_season.py` crashes partway through**, nothing from that run is saved — the whole file's worth of changes is one transaction that only commits at the very end, so a crash rolls everything back cleanly rather than leaving partial data. Once the underlying bug is fixed, just re-run the exact same command on the exact same file; it's a full clean run, not a resume.
- **New — if you ever see a game's "round" badge showing something like `4.0` instead of a real label (`NBA Finals`, `Round 1`, etc.):** that's old-format data left over in Supabase from before a formatting fix landed — cosmetic only, not a data problem. One-time fix, run once in the Supabase SQL Editor (safe to re-run if you're ever unsure whether it already ran — it only touches rows still in the old format):
  ```sql
  UPDATE games SET round = regexp_replace(round, '\.0$', '') WHERE round ~ '^[0-9]+\.0$';
  UPDATE schedule SET round = regexp_replace(round, '\.0$', '') WHERE round ~ '^[0-9]+\.0$';
  ```
- **If you ever need to rebuild a league's local database from scratch** (not just add new games), do that in `TracerProjects2` first, test it, then bring the finished `.db` and pipeline scripts over — don't experiment directly in `tracersports-app`.

---

## Getting help from Claude

Paste in:
1. What command you ran and its full output
2. What you expected vs. what happened
3. Whether it's `tracersports-app` or `TracerProjects2`

That's usually enough to pick up right where we left off. Since the repo is public, Claude can also just clone `github.com/thomassutton-afk/tracersports-app` directly to check real current state instead of relying on your description alone.
