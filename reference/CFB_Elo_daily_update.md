# CFB Elo: daily update steps

All commands are for Windows `cmd`. Project root: `C:\Users\tjsut\tracersports-app`.
Three folders matter: `DBs` (updater, compare script, exporter), `DBs\cfb` (the Elo pipeline), and `DBs\cfb\Results` (the CSV and xlsx).

## The refresh loop

Run this each time a batch of games has finished. It is safe to run mid-slate and safe to repeat. Anything not final yet is just picked up next time.

### 1. Pull final scores from ESPN (from `DBs`)

```bat
cd C:\Users\tjsut\tracersports-app\DBs
python update_cfb_results.py --file cfb\Results\CFB_2026_Results.xlsx
```

- Only completed games are written. In-progress scores are never saved.
- Note the number on the `Scores filled for N game(s)` line.
- Ignore the long list of `[!]` lines. They are FCS-vs-FCS games that are not on your sheet.
- `past game(s) still blank` means games that have not finished yet. That is normal during a slate.

### 2. Copy those scores into the CSV (from `DBs\cfb`)

```bat
cd cfb
python fill_csv_from_xlsx.py Results\CFB_2026_Results.xlsx Results\CFB_2026_Results.csv
```

Read the dry run. It should list exactly N games with sensible scores and no ties. Then write it:

```bat
python fill_csv_from_xlsx.py Results\CFB_2026_Results.xlsx Results\CFB_2026_Results.csv --apply
```

A backup is saved as `CFB_2026_Results.before_espn_fill.csv`.

### 3. Load into the Elo database (still in `DBs\cfb`)

```bat
python normalize_sr_games.py Results\CFB_2026_Results.csv parsed_results\parsed_games_2026.csv
python add_season.py parsed_results\parsed_games_2026.csv
```

Check that `add_season` reports `Inserted N new completed game(s)` with the same N and that both variants say `Sanity checks passed`. If N does not match, stop and sort that out before going further.

### 4. Look at the ratings

```bat
python show_ratings.py
```

The first line shows the date of the last game loaded. Useful variations:

```bat
python show_ratings.py --top 138
python show_ratings.py --by conf
python show_ratings.py --by tier
python show_ratings.py --conf SEC
python show_ratings.py --team "Ohio State"
```

### 5. Check the xlsx against the CSV (from `DBs`)

```bat
cd ..
python compare_xlsx_vs_csv.py cfb\Results\CFB_2026_Results.xlsx cfb\Results\CFB_2026_Results.csv
cd cfb
```

You want `missing: 0`, `mismatches: 0`, `in xlsx but not CSV: 0`. A nonzero "extra" means step 2 was skipped or did not apply.

## End of the day

From `DBs\cfb`:

```bat
python simulate_season.py --season 2026
python show_ratings.py --top 25
```

Then push the data to Supabase (from `DBs`). Always do the dry run first:

```bat
cd ..
python export_to_supabase.py --league cfb --db cfb_elo.db --dry-run
python export_to_supabase.py --league cfb --db cfb_elo.db
```

Then commit and push to git: `cfb_elo.db`, the Results CSV and xlsx, `parsed_results`, and `reports`. Leave the `cfb_elo_backup_*.db` files out of the commit.

## When something comes up

**A game looks wrong or shows as a tie / 0-0.** The fill script refuses to write ties, but Sports-Reference rows can be bad. Fix the score in the CSV first. The database ignores a game it already has, so the old row has to be deleted before reloading (run from `DBs\cfb`, and change the date):

```bat
python -c "import sqlite3;c=sqlite3.connect('../cfb_elo.db');print(c.execute('select game_id,home_code,away_code,home_pts,away_pts from games where date like ?',('2026-10-06',)).fetchall())"
python -c "import sqlite3;c=sqlite3.connect('../cfb_elo.db');n=c.execute('delete from games where date=? and home_pts=0 and away_pts=0',('2026-10-06',)).rowcount;c.commit();print('deleted',n)"
```

Run the delete only if the first command shows the bad game, and adjust its condition if the score is not 0-0. Then rerun step 3. If that game was already exported to Supabase, the corrected row will not overwrite it. Delete that season's rows in the Supabase SQL editor and re-export:

```sql
delete from games where league='cfb' and season=2026;
```

**The updater says it cannot map a team.** Add it to `ALIASES` in `update_cfb_results.py`, matching the name your sheet uses (`DBs\update_cfb_results.py --diagnose-date YYYY-MM-DD` lists every ESPN name and what it maps to). Unmapped FCS teams that are not on your sheet are harmless.

**Sports-Reference publishes an updated CSV.** Replace `CFB_2026_Results.csv` with their export and run steps 2 to 5. Step 2 should find nothing to fill. The database keeps the first score it loaded for a game, so run step 5 and look for mismatches.

**A new team shows up as a slug (like `new-school-name`).** Add a row for it in `cfb_team_names.xlsx`, then from `DBs\cfb`:

```bat
python apply_display_names.py cfb_team_names.xlsx
python apply_display_names.py cfb_team_names.xlsx --apply
```

The first command is a dry run. It lists any team missing from the sheet.

**Before anything risky,** copy the database:

```bat
copy ..\cfb_elo.db ..\cfb_elo_backup_YYYYMMDD.db
```

## Where things live

| File | Folder | What it does |
|---|---|---|
| `update_cfb_results.py` | `DBs` | ESPN scores into the xlsx |
| `compare_xlsx_vs_csv.py` | `DBs` | checks xlsx scores against the CSV |
| `export_to_supabase.py` | `DBs` | pushes CFB data to Supabase |
| `fill_csv_from_xlsx.py` | `DBs\cfb` | ESPN scores into blank CSV rows |
| `normalize_sr_games.py` | `DBs\cfb` | CSV into the parsed games file |
| `add_season.py` | `DBs\cfb` | loads games, rebuilds ratings and predictions |
| `simulate_season.py` | `DBs\cfb` | season projections (end of day) |
| `show_ratings.py` | `DBs\cfb` | prints current ratings |
| `apply_display_names.py` | `DBs\cfb` | applies team display names |
| `CFB_2026_Results.csv` / `.xlsx` | `DBs\cfb\Results` | the results data |
| `cfb_team_names.xlsx` | `DBs\cfb` | team display names |
