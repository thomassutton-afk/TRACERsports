# CFB_Elo — Project Handoff

**Status as of this handoff (Nov 16, 2026):** The Elo engine's design is
unchanged (§4–§8 describe it), but two engine-side facts are now written down
because this session made them matter: **overtime games and neutral-site games
both feed the ratings** (§5f, §5g). What changed since the Oct 24 handoff is
data quality plus the last pieces needed before the CFB pages go fully live:
(1) **the OT flag is now in the database for every season** — 1996–2000 from
TJ's own box-score list, 2001–2025 from ESPN, 2026 from the xlsx — and the
ratings were rebuilt with it (§5f); (2) **`ratings.neutral` exists**, and the
neutral flags were audited in two passes: 37 corrected against ESPN on Nov 7
(13 needing the home and away sides swapped), then on Nov 14 a pre-2008 and
local-team-rule audit changed 48 more games to non-neutral (20 of them
swapped) (§5g); (3) three duplicated games and two phantom 2026 schedule
games (women's-basketball rows in the source CSV) were removed (§2); (4) the
exporter now sends the real neutral flag and gives scheduled FCS opponents a
preseason rating (§12); (5) a new `accuracy_report.py` in the NFL report's
style (§3d), with §8 refreshed for both variants on Nov 14; (6) a set of
safety scripts — appliers that dry-run by default, and a ratings
snapshot/compare tool (§3d, §9d). CFB games were re-exported to Supabase on Nov 16, after both
neutral passes (§12). **Still open** (§10): guards against the duplicate-row
and tie problems, restoring the Games panel on the site, and the Postseason tab
(not needed until December).

**How to read this document:** §1 and §4–§8 describe the Elo engine and were
written in earlier sessions — wherever they say "this session" they mean
*that* session, not the most recent one. New or rewritten material is in §2's
first block, §3b–§3d, §5f–§5g, §7's note, §8, §9, §10 and §11–§13.

This document is meant to let a fresh conversation (or future-you) pick up
exactly where this one left off, without re-deriving any of the design
reasoning below. Read this fully before making further changes — several
design decisions here look arbitrary in isolation but were deliberately
chosen after working through real alternatives.

---

## 1. What this project is

`CFB_Elo` is a College Football Elo rating pipeline, forked from an existing
`NFL_Elo` codebase (part of a larger multi-sport project — `tracersports-app`
on GitHub, feeding a site called TRACER Sports). It computes weekly Elo
ratings for every FBS program, going back to the 1996 season, from
Sports-Reference schedule/standings exports.

Repo: `github.com/thomassutton-afk/tracersports-app`, now in `DBs/cfb/`
(migrated from a root-level `CFB_Elo/` this session — a separate
Python/SQLite data-engineering project, distinct from the site's
Next.js/Supabase frontend, but now following the same layout convention as
`DBs/nba`, `DBs/nfl`, `DBs/wnba`). The database itself is `DBs/cfb_elo.db`
(one level up from the scripts, sibling to `nba_elo.db`/`nfl_elo.db`/
`wnba_elo.db`) — every script's `DB_PATH` resolves via
`os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "cfb_elo.db")`,
matching the sibling leagues' convention exactly. A few structural gaps
remain beyond the move itself — see §10, item 5.

## 2. Current data state

### Where the data stands now (Oct–Nov 2026)

- **31 seasons loaded (1996–2026); 2026 is in progress and updated daily.**
  Snapshot on Nov 16, 2026: 24,736 games in `games` and 46,735 `ratings` rows per
  variant (93,470 in total); the last game still on the 2026 schedule is
  Navy–Army, Dec 12. Counts move every
  day — query `games` / `schedule` rather than trusting any number written
  here.
- **263 teams in `teams`; 138 are FBS in 2026** (`fbs_membership`) — not 136
  as older notes say (Sacramento State, Delaware, Missouri State, Kennesaw
  State, Jacksonville State and Sam Houston are all FBS now). The other 125
  teams are FCS/historical and inactive.
- **Regular-season vs postseason inside the DB:** every game is `type = 'R'`;
  bowls, the CFP and conference title games are told apart by `round`:
  `BOWL` (923), `CCG` (148), `NC` (28), `CFP-SF` (24), `CFP-R1` (8),
  `CFP-QF` (8), everything else NULL. The *site* needs a different split —
  see §12 (`site_type_round`).
- **Team display names are real names now**, not slugs (§11): `teams.team_name`
  and each team's current `team_history.name` hold the "full" display name
  (e.g. "Alabama Crimson Tide"). The slug is still the team *code*
  (`team_history.code`, `team_aliases`) and is what every game row, the
  exporter and the site use as `team_id`. Anything that joined
  `teams.team_name` to a slug (e.g. `check_bowl_accuracy.py`) is now broken.
- **Active model parameters:** `param_schedule.json` governs every season,
  not `engine.py`'s `BASELINE_PARAMS` (whose comments still call them
  untuned). 2026 has no entry and inherits 2025's: `alpha 0.58, kmax 100.5,
  hfa 45.5, fcs_rating 925`. See §7's note.
- **Data-quality incident worth remembering (Oct 6, Troy–Southern Miss):**
  the Sports-Reference CSV carried the game as 0–0 and it loaded as a real
  tie (both teams showed a tie in the standings); ESPN had it 55–34.
  Nothing in `normalize_sr_games.py` / `add_season.py` rejects ties or 0–0 yet
  (§10, item 12), and `add_season` ignores a game it already has, so fixing
  the CSV alone does nothing — the old row must be deleted first (§9b).
- **The overtime flag is populated for every season (Nov 2026).** `games.ot`
  and `ratings.ot` were 0 for every game until this session, because the
  Sports-Reference CSV has no OT field — so the engine's OT multiplier had
  never actually fired. Sources: **1996–2000** TJ's hand-compiled list of
  box-score overtime games (`ot_games_20th_century.txt`); **2001–2025** ESPN's
  scoreboard (`backfill_ot.py`); **2026** the xlsx `OT` column
  (`apply_ot_xlsx.py`). About 990 OT games through 2025 plus 20 so far in 2026.
  ESPN's flag is unreliable before 2001, and there is one known ESPN false
  positive that a re-run would bring back — both in §5f. TJ's stated intent is
  that OT belongs in the ratings.
- **`ratings.neutral` exists and the neutral flags were audited (Nov 2026).**
  The engine already removed home-field advantage for neutral games; what was
  missing was the column on `ratings` (so the exporter always sent 0) and a
  check that the flags were right. Details, the home/away trap and the two audit
  passes (ESPN for 2008+ on Nov 7, a local-team rule for 1996–2026 on Nov 14)
  are in §5g.
- **Two kinds of bad source rows were found and removed (Nov 2026).**
  - *Phantom 2026 games.* The 2026 CSV contained two games that are not
    football: Maryland vs South Carolina (Mon Nov 2, flagged `N`) and South
    Carolina vs USC (Sun Nov 15, flagged `N`) — rows 623 and 754 of
    `CFB_2026_Results.csv`. TJ identified them as women's basketball games. Both
    double-booked real football teams (Maryland hosts Illinois and South
    Carolina plays at Oklahoma on Oct 31; South Carolina plays at Arkansas and
    USC at Indiana on Nov 14), and South Carolina showed 14 games against 12
    for most teams. How they got into the CSV is unknown. They were deleted
    from the CSV, the xlsx and the DB's `schedule` / `schedule_predictions`
    (upcoming games 268 → 266; exported schedule rows 1,072 → 1,064). They had
    been inflating Maryland's, South Carolina's and USC's projected win totals.
  - *Echo duplicates.* Three games appear twice in the historical CSVs, one day
    apart, the second row with a blank `Notes` (a time-zone echo):
    California–Hawaii 2016 (Aug 26/27, played in Sydney), Rice–Stanford 2017
    (Aug 26/27, Sydney) and Army–Missouri 2021 Armed Forces Bowl (Dec 22/23).
    Each was counted twice in the Elo. The second CSV rows (Rk 2 in 2016, Rk 6
    in 2017, Rk 862 in 2021) and the DB rows (`game_id` 88125, 89013, 93093)
    were deleted and ratings rebuilt. `dedupe_raw_rows()` (keyed on
    `(Date, Winner, Loser)`) cannot catch these because the dates differ. A
    sweep for teams playing twice within three days found only these three
    across 1996–2026 (§9e).

### Earlier notes on the data (previous session)

- **30 full historical seasons (1996–2025), plus an in-progress 2026 season**
  — 24,247 total games in the database. 260 completed 2026 games plus 630
  correctly-scheduled upcoming 2026 games (fixed this session — see below and
  §10, item 1, now resolved).
- Both rating variants (Echo = continuous carryover with conference-average
  season entry, Pulse = regression toward a flat base each season with no
  conference information; §5c) computed and stored in `cfb_elo.db`.
- Conference membership (`team_conference_history`) and FBS status
  (`fbs_membership`) loaded for every season through 2026 via
  `load_conference_membership.py`.
- **Data-integrity cleanup done this session:** found and fixed duplicate raw
  rows in the Sports-Reference source data. Two distinct patterns:
  - Some games have two rows with *different* `Notes` text (one with the
    real bowl/event name, one with just a generic venue name) — 25 such
    pairs across 1996–2025, 8 of which would have silently double-counted a
    game's Elo impact once postseason classification could tell the two
    copies apart (six bowl games plus the 2010 SEC Championship Game).
  - A separate, older, unrelated bug: some games have two **fully
    identical** rows already sitting in the database (same teams, same
    score) — confirmed in at least 10 of the 1996–2005 seasons (3–5 extra
    rows each), pre-dating this session's work entirely. Root cause not
    fully traced; likely from an earlier double-load at some point in the
    project's history.
  - Both are now fixed by `normalize_sr_games.dedupe_raw_rows()`, keyed on
    `(Date, Winner, Loser)`, run before classification. **This required a
    full re-ingest of every season** (delete + reload from raw CSVs, not
    just a code fix) to actually take effect in `cfb_elo.db` — done this
    session. If you ever see game counts change unexpectedly after a
    reload, check this section before assuming something's broken.
- **New this session: fixed the unplayed-games/schedule bug (former §10 item
  1).** `normalize_sr_games.py` was unconditionally dropping every scoreless
  row. Now a scoreless row's DATE decides its fate: today-or-future (within a
  small buffer for a same-day result not yet posted) → kept and routed to
  `schedule` for prediction; further in the past → still dropped as a
  genuine postponement, same as before. Validated end-to-end against the
  real 630 upcoming 2026 games — all correctly landed in `schedule`, not
  `games`. See §5e for a second, related classification fix found and
  fixed the same session.
- **New this session: found and fixed a real classification bug behind the
  BOWL-accuracy gap (former §10 item 3) — see §5e and §8.** Not a modeling
  gap; `classify_round()`'s bare `"Bowl"` regex match was catching venue
  names (Memphis's Liberty Bowl Memorial Stadium, UTEP's Sun Bowl Stadium,
  UCLA's Rose Bowl, and the annual regular-season Texas-Oklahoma game at the
  Cotton Bowl), misclassifying 104-113 ordinary regular-season games as
  postseason across 1996-2025 depending on exactly how it's counted. Fixed
  with a December-June date gate on the `"___ Bowl"`-based checks
  specifically (NOT on the `"Championship"`/CCG check, which needed to stay
  open through Nov 30 for years when Championship Saturday falls there, and
  never had this collision risk anyway). Re-ingested and confirmed: the
  corrected BOWL accuracy is actually a bit LOWER (60.1-60.2%, was
  61.2-61.9%) since the misclassified games had been propping the number up
  — the real postseason gap is slightly worse than originally reported, but
  now trustworthy. CFP-SF accuracy improved substantially (was suffering the
  same venue-collision bug via a different code path) once its false
  positives were removed.

## 3. File-by-file summary

| File | What it does |
|---|---|
| `db.py` | SQLite schema + all data-access helpers. See §4 for the CFB-specific schema additions. **Nov 2026:** `ratings` gained a `neutral` column; `_migrate()` adds it to an existing database automatically the next time anything calls `db.connect()` (existing rows read 0 until the next rebuild), and `save_ratings` writes it. |
| `engine.py` | The actual Elo math (`EloEngine`, weekly-batch replay). See §5 for the season-entry/FCS/postseason mechanics — these are the parts that differ meaningfully from the NFL version. **Nov 2026:** each team's ratings row now carries `neutral`; the overtime multiplier (`ot_mult = 0.7`, hard-coded) and the neutral-site home-field switch are documented in §5f and §5g. |
| `rebuild.py` | Replays all games from `games` into `ratings`, from scratch, for one rating variant. Owns `apply_season_entry()` — the actual implementation of the conference-average algorithm (engine.py just executes what this hands it). |
| `add_season.py` | Loads one season's normalized CSV into `games`/`schedule`, registers new teams, triggers a full rebuild, writes schedule predictions. |
| `franchise.py` | `rename` (cosmetic name fix), `realign` (conference change), `revive` (fold+revival reset). No `relocate` — CFB programs don't physically relocate the way NFL/NBA franchises do. |
| `normalize_sr_games.py` | Converts a raw Sports-Reference schedule CSV into the standardized per-team-row shape `add_season.py` expects. Handles AP rank parsing, team-code slugification, season-year logic for bowl games, source-data dedup, and full postseason `Round` classification (see §5e). Unplayed-game routing and the venue-name-collision fix (both former known bugs) are fixed this session — see §2 and §5e. |
| `load_conference_membership.py` | Loads one season's Standings CSV into `team_conference_history` + `fbs_membership`. Triggers a full rebuild (FBS status now affects rating math, not just display). **Must be run for a season AFTER `add_season.py` has loaded that season's games** — otherwise every team in it silently scores as FCS (fixed rating, no persisted `ratings` row, invisible in standings) until this catches up. Confirmed directly loading 2026: games loaded fine, but standings came back completely empty until this was run. Re-run for 2026 this session with the full real Standings export: 0 unresolved teams, no `KNOWN_ALIASES` gaps. |
| `cfb_tune_engine.py` | Coordinate-ascent tuner over `alpha`/`kmax`/`hfa`/`fcs_rating` for one window, using the real engine (not a reimplementation). |
| `cfb_tune_fcs_rating.py` | Separate era-block tuning for `fcs_rating` specifically (too thin a sample to tune on the same rolling cadence as the others). |
| `cfb_build_param_schedule.py` | Builds the actual `param_schedule.json` (see §7) via a rolling 10-year walk-forward search, seeded from one continuous engine's real snapshotted state at each window boundary (not a fresh flat restart per window) — genuinely equivalent to what production's continuous replay does. Heavy compute job (30 seasons × coordinate-ascent search × real multi-season replay per candidate) — a "kick off and let it churn" script. |
| `cfb_accuracy_report.py` | **Superseded — not in the repo as of Nov 2026** (a search of `TRACERsports` found it nowhere), and the sibling leagues' `report.py` is a standings/game-log dumper, not an accuracy report. Replaced by `accuracy_report.py` (§3d), written in the style of the NFL league's `accuracy_report.py`, so the name now matches the siblings. See §8 for current output. |
| `rebuild_ratings_only.py` | Thin wrapper that just re-runs `rebuild.rebuild_ratings()` for both variants against an existing `cfb_elo.db` without touching `games` — useful after a params or engine change that doesn't need a re-ingest. |
| `reingest_phase2.py` | Backs up `cfb_elo.db`, re-normalizes and reloads every season 1996-2026 through the current `normalize_sr_games.py`/`classify_round()`, then rebuilds ratings for both variants. The right tool whenever a classification or normalization fix needs to retroactively apply to already-loaded history — used twice this session (the unplayed-games fix and the venue-collision fix each needed a full re-ingest, not just a code change, to take effect in `cfb_elo.db`). **Warning (Nov 2026):** it reloads games from the CSVs, which carry no OT flag and Sports-Reference's home/away order, so a full re-ingest very likely discards the OT flags, the neutral/host corrections and any DB-only deletions — see §9d for the re-apply sequence before running it. |
| `test_phase2.py` | Sanity-checks the postseason classification against a copy of the real db (never touches `cfb_elo.db` directly). |
| `cfb_worst_season_endings.py` | Analysis script — not part of the core pipeline. |
| `predict.py` | Predicts upcoming/unplayed games from current ratings. Has one known simplification — see §10, item 9 (deferred by deliberate decision this session, not urgent). |
| `simulate_season.py` | **New this session** — ported from `TRACERsports/DBs/nfl/simulate_season.py`. Monte Carlo season projection (remaining schedule simulated many times from current ratings). One real CFB-specific addition beyond a straight port: remaining games need `home_conf`/`away_conf`/`home_div`/`away_div`/`home_is_fbs`/`away_is_fbs` annotated (via `rebuild._annotate_conferences()`) before `process_week()`/`preview_matchup()` can use them correctly — the NFL original doesn't need this. Also filters final projections to FBS teams only, since a same-season FCS "buy game" opponent otherwise gets a meaningless fragment-of-a-season win projection. Validated against the real 2026 season (1000 trials, 630 remaining games) — sane output across all ~136 teams, no errors. |

### 3b. Scripts and data files added since the last handoff

| File | Where | What it does |
|---|---|---|
| `update_cfb_results.py` | `DBs/` | Fills final scores (and the OT flag) from ESPN's scoreboard into `Results/CFB_2026_Results.xlsx`, a long-format sheet (two rows per game, NFL layout). Only writes **completed** games. Names are matched through an `ALIASES` dict plus inference from the sheet; `--diagnose-date YYYY-MM-DD` prints every ESPN team name and what it maps to (a `[?]` is fine if the team is not on the sheet, otherwise add an alias). With no date flags it fetches only dates that still have blank scores/OT. |
| `csv_to_long.py` | `DBs/cfb/` | Builds that long-format xlsx from the Sports-Reference CSV. Treat it as once per season: re-running it on a sheet the updater has already filled would rebuild from the CSV and lose the ESPN-filled OT flags (check the script before re-running). |
| `fill_csv_from_xlsx.py` | `DBs/cfb/` | **The bridge.** Copies ESPN finals from the xlsx into score-less rows of the Sports-Reference CSV so the normal pipeline can load them. Fills a row only if the xlsx has a final for that exact date + team pair, the score is not tied/0–0, and the date is today or earlier. Swaps winner/loser and flips the `@` marker when the listed-first team lost (CSV convention: Winner first; `@` = winner was away; blank = winner home). Dry run by default, `--apply` writes (saves `*.before_espn_fill.csv`). |
| `compare_xlsx_vs_csv.py` | `DBs/` | Checks xlsx scores against the CSV: want `missing 0 / mismatches 0 / in xlsx but not CSV 0`. |
| `show_ratings.py` | `DBs/cfb/` | Read-only current ratings (echo + pulse). `--conf`, `--tier P4/G6`, `--by conf/tier`, `--team`, `--season`, `--top`; every list ends with the **average rating of exactly the teams shown**. `#` is position in the shown list, `rk` is national rank. The tiering rule is three constants at the top (`POWER`, `POWER_THROUGH` for the Pac-12/Pac-10/Big East power years, `ALWAYS_P4` = Notre Dame). |
| `preview_week.py` | `DBs/cfb/` | Ranks upcoming FBS-vs-FBS games by "watchability": score = 100 × quality^w × closeness^(1−w), with closeness = 4p(1−p) from the model's home win probability (so home field/rest are included) and quality = mean of the two teams' rating percentiles; `w` defaults to 0.5. Replaces a total/gap ratio that collapsed into 1/gap. |
| `apply_display_names.py` | `DBs/cfb/` | Applies the names in `cfb_team_names.xlsx` to the DB and writes `team_display_names.json`. Dry run by default; refuses to write on blanks or key mismatches; warns about teams in the DB but not in the sheet (how a newly registered team shows up). |
| `cfb_team_names.xlsx` / `team_display_names.json` | `DBs/cfb/` | Source of truth for names: one row per team (263) with the Sports-Reference name, ESPN name, and TJ's **Display full name** and **Display short name**. The JSON is the machine copy read by the config generator, `show_ratings.py` and `rename_cfb_logos.py`. |
| `rename_cfb_logos.py` | `DBs/cfb/` | One-time: renamed the 138 logo files in `public/logos/cfb` from school names (`Air_Force.png`) to slugs (`air-force.png`) with `git mv`, matching through the names file. Idempotent. |
| `generate_cfb_config.py` | `DBs/cfb/` | Writes `lib/sports/cfb/config.js` from `team_display_names.json`, the DB's 2026 FBS list and `cfb_team_colors.csv`; `--require-verified` refuses to write unless every team's colors are verified. Never hand-edit the generated config. |
| `cfb_team_colors.csv` | `DBs/cfb/` | Colors source of truth: `slug, conference, team, primary, secondary, tertiary, status, source`. Its `conference` column is what the config uses (it starts as the DB's 2026 alignment and is hand-editable — Notre Dame and UConn are `Ind`). |
| `CFB_Elo_daily_update.md` | `DBs/cfb/` | The short step-by-step version of §9's daily loop. |

### 3c. Repo files outside `DBs/cfb/` that CFB now touches

| File | What changed |
|---|---|
| `DBs/export_to_supabase.py` | CFB support — exact changes in §12. |
| `lib/sports/cfb/config.js` | **Generated.** League config: conferences, per-team name/city/nickname/conf/tier/colors, `rankingsView: 'tiered'`, `standingsView: 'conference'`, `alignmentSeason`, `bracketTabLabel: 'Postseason'`, `conferenceLabels`, `conferenceGroups`, `hasTies: false`, `minValidGameScore: 1`, `playoffFormat.type: 'cfp'` (no bracket component exists for it), and a reference-only `engine` block. |
| `lib/sports/registry.js` | `cfb` added to the football sport and to `LEAGUES` (patch `cfb_registry.patch`). |
| `lib/cfbRankings.js` | Pure helpers: ranking, tier/conference filtering, averages, Sports-Reference-compatible week numbering for the "updated after Week N" label, and conference standings. Unit-testable in plain node. |
| `app/[league]/CfbRankings.jsx`, `CfbStandings.jsx`, `ConferenceSelect.jsx` | The CFB Rankings and Standings tabs and the shared conference dropdown. |
| `app/[league]/page.js` | Small edits: a `tiered` flag read from the config, hero text, the tab relabel, the standings swap. Other leagues render exactly as before. |
| `public/logos/cfb/{slug}.png` | 138 logos, now keyed by team code. |

### 3d. Scripts and files added in the Nov 2026 data-quality session

All live in `DBs/cfb/` and are run from there (the DB is `../cfb_elo.db`).
Every script that changes the database is a **dry run unless you pass
`--apply`**, and every one that changes something the ratings depend on should
be followed by `rebuild_ratings_only.py` and a snapshot compare (below).

| File | What it does |
|---|---|
| `backfill_ot.py` | Puts ESPN's overtime flag into `games.ot`. Reads every game date from the DB, fetches ESPN's college-football scoreboard (`groups` 80 and 81) for each date ±1 day, and caches every response in `espn_cache/` (a rerun is free). Matches each DB game to an ESPN event by date + score (same orientation first, flipped as a fallback), de-duplicating events by ESPN event id, with a team-name tie-break. "OT" = period > 4, "OT" in the status text, or more than four line-score periods. Writes `espn_ot_proposed_<season\|all>.csv` (one row per game: status, ESPN's OT and neutral flags, candidate events, a `signals_disagree` column) and `espn_ot_unmatched_*.csv`. `--apply` refuses while any ESPN request failed. **Trust its OT flags only from 2001 on** (§5f). Its proposed CSV and the cache are also inputs to the neutral scripts below — keep them. |
| `ot_games_20th_century.txt` + `apply_ot_list.py` | TJ's list of 157 overtime games (1996 through Dec 19, 2001), compiled by hand from Sports-Reference's daily box scores, and the script that applies it. Matches each line by date (within 10 days, with a warning — Idaho–Boise State 1998 was typed Nov 14 but played Nov 21) and the two teams. For seasons through 2000 it sets `ot` from the list for *every* game, which clears ESPN's wrong flags; for 2001 it only adds. Refuses to apply while any line is unmatched. |
| `apply_ot_xlsx.py` | Copies the `OT` column of `Results/CFB_2026_Results.xlsx` into `games.ot` (match on date + score, name tie-break). Run after step 3 of the daily loop, then `rebuild_ratings_only.py` (§9a). |
| `ratings_snapshot.py` | `dump <db> <prefix>` writes every `ratings*` table to CSV; `compare <prefixA> <prefixB>` compares two dumps column by column (columns that exist in only one dump are reported, the shared ones compared); `neutral <db>` checks that `ratings.neutral` equals `games.neutral` on every row. **The standard check for any change that should not move ratings**: dump, rebuild, dump, compare. |
| `accuracy_report.py` | CFB version of the NFL accuracy report: accuracy / Brier / log loss overall, by round, season, month and calibration bucket, biggest upsets and worst misses. Differences from the NFL script: `--variant echo\|pulse` (default echo); FBS-vs-FBS games only unless `--include-fcs`; a By-round block (`type` is `R` for every CFB game, so postseason is read from `round`); an Overtime line; the always-pick-home baseline uses non-neutral games only; team ids are mapped to display names; `--db` scores another copy of the database (for before/after comparisons). Reads `accuracy`, `brier` and `test` straight from `ratings` — **`test` is the log loss**. Writes `reports/accuracy_summary_<tag>.txt` and `accuracy_by_game_<tag>.csv`. |
| `check_neutral_vs_espn.py` | Compares `games.neutral` with ESPN's neutral flag for 2008 onward (ESPN's flag is empty before that), prints the disagreements by round, and writes `neutral_review.csv` — a sheet to fill in (`new_neutral` = 1 or 0 on the rows to change). Re-running it overwrites the sheet. |
| `apply_neutral_overrides.py` | Applies such a sheet. Matches games by date + the two teams in either order (so it survives a reload and a swap, and a second run is a no-op). Going from neutral to non-neutral it first puts the real host in the home slot — taken from ESPN's home team (by score orientation) or from an optional `host` column — and refuses when it cannot tell. **Prefer an explicit `host`**: ESPN's orientation for neutral games was wrong for at least two of the Nov 14 games (Tulane–Southeastern Louisiana 2005, Washington State–Idaho 1999). See §5g for why. |
| `neutral_review.csv` | The reviewed sheet from Nov 7, 2026 (69 rows; 37 changes applied; two of its decisions were reversed on Nov 14 — §5g). It is the record of those decisions and re-applies cleanly after a re-ingest (§9d). |
| `probe_old_venues.py`, `neutral_series_candidates.py` | Run for the pre-2008 audit (Nov 14). The probe found no usable venue data in ESPN before 2008 (no `neutralSite` flag; the venue strings for 2001–2007 looked wrong) and reported 0 `Notes` for old Sports-Reference files because it reads the 2013+ column position (§13), so no venue-based detector was built. `neutral_series_candidates.py` lists unflagged games between pairs that are neutral almost every time; it surfaced Army–Navy 1997/2000/2002/2007, which stay non-neutral under the local-team rule (§5g) — most of its other 12 rows were campus games and were discarded. |
| `neutral_audit.py`, `neutral_audit2.py` | Nov 14 audit scripts for the 1996–2012 results files (fixed column positions: no `Time` column, §13). `neutral_audit.py` prints the CSV `N` count next to the DB's neutral count per season. `neutral_audit2.py` writes `pre2008_neutral_review.csv` (every game the DB has as neutral for 1996–2007, with `csv_N`, `repeat_team` and `info` columns for review, plus the four Army–Navy rows) and `csv_vs_db_neutral_mismatch.csv` (2006–2012 disagreements). |
| `add_host.py` | Writes the `host` column of `pre2008_neutral_review.csv` from a `hosts` list inside the script (Eastern Washington 1999, Tulane 2005 ×3, Washington State 1999). Rebuilds the column on every run. |
| `bowl_local_candidates2.py` | Scans the results files' venue `Notes` (postseason games, and neutral regular-season games from about 2013 to 2021) for neutral-flagged games with a team from the venue's metro area; writes `bowl_local_candidates2.csv` (`new_neutral` = 0, `host` = the local team). Finds columns from the header, so it handles both file layouts. The city-to-team table is inside the script, written from memory; slugs are checked against the DB at start. **Re-running overwrites the CSV, and once the flags are applied it finds nothing — treat the CSV as a record.** (`bowl_local_candidates.py` is the earlier 1996–2007-only version.) |
| `espn_local_candidates.py` | The same scan using ESPN's venue city from `espn_cache/*_80.json` (2008 onward), matching DB games by date + score pair; it covers 2022+ regular-season games, whose `Notes` are blank. A `SKIP` set inside holds the calls that were rejected. Writes `espn_local_candidates.csv`. |
| `audit_magnitude.py` | After a flag change: merges `before_audit_ratings.csv` and `after_audit_ratings.csv` (from `ratings_snapshot.py dump`) on variant + season + game + team and prints the largest and mean `post_rate` change, and whether seasons before the earliest changed game moved (they must not). Works when the two dumps have different row counts, which `compare` does not. |
| Nov 14 override sheets | `pre2008_neutral_review.csv` (402 rows, with a `host` column), `usf_override.csv` (1), `bowl_local_candidates2.csv` (29), `override_2022plus.csv` (3), `espn_local_candidates.csv` (7), `arkansas_override.csv` (1): the record of the Nov 14 decisions, re-applied in order by §9d. One-off helpers not worth keeping: `fix_rose.py`, `make_override.py`, `lookup6.py`, `trim_*.py`, `verify_candidates.py`, `unresolved_notes.py`. |
| `ot_overrides.py`, `ot_worklist.csv` | **Obsolete** — made redundant by the hand-compiled list; safe to delete. |

Changed files outside this table: `db.py`, `engine.py` (§3) and
`DBs/export_to_supabase.py` (§12).

## 4. Schema additions beyond NFL_Elo

- **`team_conference_history`** — era-scoped conference/division per team
  (`team_id, conference, division, start_season, end_season`). Deliberately
  separate from `team_history` (which is for renames/relocations) — a
  conference switch isn't a relocation.
- **`fbs_membership`** — `(team_id, season)`. The actual "is this team FBS
  this season" signal. Populated for every school in a season's Standings
  file, **including independents** (who deliberately get no
  `team_conference_history` row — see §5). **No row for a (team, season) is
  treated identically to "genuinely FCS" by `db.is_fbs()`** — there's no way
  to distinguish "actually FCS" from "just hasn't been loaded yet" from
  inside the engine. See §3's `load_conference_membership.py` entry.
- **`conference_tier`** — `(conference, start_season, end_season, tier)`,
  `tier ∈ {power, midmajor}`. Used only to bucket FBS independents (who have
  no literal conference) for season-entry averaging. Auto-seeded on first
  `db.connect()` via `seed_conference_tiers()`:
  - SEC, Big Ten, ACC, Big 12 → power, 1996–present
  - Pac-12 → power, 1996–2023 (dissolved after 2023)
  - Old football-playing Big East → power, 1996–2012 (split into the
    American in 2013)
  - Everything else defaults to `midmajor` via `tier_for_conference()`'s
    fallback — **this seed list is not exhaustive**, see §10.
- **`games`/`schedule`** carry nullable `home_ap_rank`/`away_ap_rank`.
  **Changed this session:** previously display-only and never read by the
  engine; now actually read for `Round=="BOWL"` games specifically, to
  score bowl importance by the two teams' own rank instead of a hardcoded
  bowl-name list — see §5e.
- **`ratings.neutral`** (Nov 2026) — 0/1, copied from `games.neutral` by the
  engine when it builds each row, so CFB's ratings table now matches the
  other leagues'. It is derived (rewritten with every rebuild); `games.neutral`
  stays the source of truth, and its quirks are in §5g.

## 5. Key architecture decisions (read this before changing the engine)

### 5a. Team identity
No canonical abbreviation table exists for CFB (unlike NFL). Team codes are
slugified full names (`brigham-young`, `texas-a-m`, `miami-fl`). Sports-
Reference's *standings* exports use shorter common names (`BYU`, `USC`) that
don't match the *schedule* export's full names — `load_conference_membership.py`'s
`KNOWN_ALIASES` dict bridges this gap. It currently covers: byu, usc,
ole-miss, utep, lsu, smu, pitt, ucf, unlv, uconn, umass, uab, utsa. Extend it
whenever `reports/unresolved_conference_teams_*.csv` flags a new mismatch.

### 5b. FCS handling
Any team with no `fbs_membership` row for a season is treated as a
**fixed-strength opponent** (`fcs_rating` — see §7 for its tuned values):
- Used only to compute the *FBS* opponent's expected outcome/rating change.
- Never gets a `TeamState`, never gets a persisted `ratings` row, never
  appears in standings.
- This was specifically chosen to sidestep a real identity-continuity bug:
  Texas A&M-Commerce renamed to East Texas A&M in 2025 while remaining FCS
  the whole time, which split one program across two `team_id`s with no
  clean way to merge them. Since neither ever gets a real tracked rating,
  the split is harmless.
- **Same mechanism is the cause of the empty-standings trap** described in
  §3/§10 — a season with no `fbs_membership` rows yet looks, from the
  engine's point of view, exactly like a season where every FBS team
  suddenly became FCS.

### 5c. Conference-average season-entry (replaces flat-1500 reversion)
This is the single biggest structural change from NFL_Elo. NFL_Elo blends
every team toward one shared constant (`base`, 1500) between seasons. CFB
programs sit at wildly different competitive tiers that roughly track their
conference, so this blends toward a **conference (or tier) average** instead.

Implemented as `rebuild.apply_season_entry()`, called **once per season
boundary**, before that season's first `process_week()` call — this is a
genuine restructuring, not a parameter tweak. `engine.py`'s `process_week()`
now *requires* every FBS team to already have a `TeamState` before it runs
(raises `KeyError` otherwise) — season entry is no longer lazy/per-team the
way NFL_Elo's was.

**Four-step algorithm** (see `apply_season_entry()`'s docstring for the full
version):
1. **Step A** — group every returning team's current rating by its **last**
   season's conference (or power/midmajor tier, for a returning independent).
2. **Step B** — average each group; regress every returning team toward its
   own group's average via `regress_returning_team()`.
3. **Step C** — recompute conference averages using **this** season's
   membership, but only from the now-regressed returning teams (never from a
   team debuting the same season — avoids circularity when multiple teams
   join the same conference simultaneously).
4. **Step D** — any team never tracked before (true debut, or a former
   fixed-rating FCS opponent) gets inducted via `induct_new_team()` at
   **0.5 × fcs_rating + 0.5 × (its new conference's Step-C average)**.

**Realignment-year rule:** a team's target always uses **last** season's
conference, never the season being entered. This means a team switching
conferences (e.g. Oklahoma Big 12→SEC in 2024) still contributes to and
draws from its *old* conference's average in the transition year, and only
starts drawing from the *new* conference the following season. No special-
casing needed — this falls out of "always use last season's conference"
applied uniformly.

**Independents:** Notre Dame → power tier pool. Every other independent →
midmajor tier pool (`db.INDEPENDENT_TIER`, currently just `{"notre-dame":
"power"}`, defaults everyone else to midmajor).

**Pulse stays flat.** Only Echo uses conference-average reversion — Pulse
still blends toward the shared `base` constant, preserving its meaning as a
pure "no information" comparison baseline. If both variants encoded
conference strength, the distinction between them would blur.

**First-ever loaded season (1996) is a special case:** every team starts
flat at `base`, bypassing the Step D blend entirely (`is_first_season=True`
flag). There's no genuine "graduated from FCS" signal when every team is new
simultaneously — the blend logic is specifically for a team debuting into an
*already-established* league.

**Still unsolved:** genuine first-year-FBS teams (a real promotion, not just
a renamed-but-still-FCS case) likely start overrated by the 50/50 blend —
newcomers are usually behind their new conference-mates initially. This was
deliberately left as "start simple, calibrate later" — see §10.

### 5d. Conference multiplier (collapsed from NFL's two-tier system)
NFL_Elo had separate `div_game_mult` (1.1) and `conf_game_mult` (1.02).
CFB's remaining divisions are largely vestigial post-2020s realignment, so
these collapsed into a single `conf_game_mult` (seeded at 1.1, the old
division-tier value). `div_game` is still computed and stored on every
`ratings` row for potential future display use — it just no longer moves the
K-multiplier.

### 5e. Postseason — full classification done, values still untuned

**Round now takes one of:** `"CCG"`, `"NC"`, `"CFP-R1"`, `"CFP-QF"`,
`"CFP-SF"`, `"BOWL"`, or `None` (regular season). Classification happens in
`normalize_sr_games.classify_round(notes, season, date)` (the `date` param
was added this session — see the venue-collision fix below), checked in this
order (order matters — see the NC/CCG note below):

1. **`NC`** (national championship) — explicit in `Notes` from 2006 onward
   (`"BCS Championship"` 2006–2013, `"College Football Playoff National
   Championship"` 2014+). For 1998–2005, the BCS title game was just
   whichever of Rose/Sugar/Orange/Fiesta was that year's designated host in
   the normal bowl rotation, with **no distinguishing text in `Notes`** —
   handled via a hardcoded year→bowl lookup (`BCS_EMBEDDED_TITLE_BOWL`),
   cross-referenced against BCS history and confirmed directly against the
   1998 and 2000 raw files.
2. **`CFP-R1`** (12-team first round) — explicit in `Notes` from 2024 onward
   (`"College Football Playoff - First Round"`).
3. **`CFP-SF`** (semifinal) — **never** named as such in `Notes`, in either
   the 4-team (2014–2023) or 12-team (2024+) era — just the host bowl's
   ordinary name. Handled via a season→bowl-pair lookup (`CFP_SEMIFINAL_PAIR`),
   a 3-year rotation cycle (Rose/Sugar → Orange/Cotton → Fiesta/Peach),
   confirmed directly against the 2024/2025 raw files and against
   independent sources for 2014–2023.
4. **`CFP-QF`** (12-team quarterfinal, 2024+ only) — whichever New Year's Six
   bowl isn't that season's semifinal host (`NY6_BOWLS`) — also never
   explicitly named as a quarterfinal in `Notes`.
5. **`CCG`** (conference championship) — `"Championship"` appearing in
   `Notes`. **Only checked after NC is ruled out** — both `"BCS
   Championship"` and `"College Football Playoff National Championship"`
   also contain the word "Championship," and would otherwise be
   misclassified as a conference championship game. This was a real bug in
   the codebase before this session (harmless in practice only because
   `conf_championship_mult` was still `1.0`).
6. **`BOWL`** — every other bowl, identified by `"Bowl"` appearing in
   `Notes`. **Deliberately not split into a hardcoded "major bowl" name
   list** (the earlier design direction, which would have needed its own
   era-branching — BCS-era "major" bowls ≠ NY6 bowls ≠ the pre-BCS "big
   bowls," and the set changes again once a bowl becomes a CFP host some
   years and not others). Instead, bowl importance is scored directly off
   the two teams' own AP ranks at the multiplier level — see below.
7. `None` — regular season.

**New this session — every `"___ Bowl"`-based check above (NC's
embedded-title case, CFP-SF, CFP-QF, and plain BOWL) is gated to a
December-through-June window** (`date.month == 12 or date.month <= 6`,
reusing `season_for_date()`'s own year-boundary convention). Root cause:
Sports-Reference's `Notes` field also carries venue names for ordinary
regular-season games, and several stadiums are themselves named `"___ Bowl"`
— Memphis's Liberty Bowl Memorial Stadium, UTEP's Sun Bowl Stadium, Toledo's
Glass Bowl, UCLA's Rose Bowl — plus the annual regular-season
Texas-Oklahoma game, played every October at the Cotton Bowl in Dallas.
Without the date gate, `"\bBowl\b"` matches those venue names directly, and
the CFP-SF semifinal-pair check had the *identical* collision independently
(2015's semifinal host was the Cotton Bowl, 2017's was the Rose Bowl — every
UCLA or Texas-OU regular-season game those years was already being
misclassified as `CFP-SF` before this fix). Confirmed and fixed: 113 real
false positives across 1996-2025, re-ingested via `reingest_phase2.py`.

**The CCG (`"Championship"`) check is deliberately NOT gated the same way —
this needed its own, different reasoning, not just a wider version of the
same date window.** Two things ruled out a shared gate: (1) `"Championship"`
has zero observed collision risk with any venue name across 30 years of
data, so it doesn't need a gate at all; (2) Championship Saturday itself
sometimes falls on **November 30** (confirmed: MAC/Pac-12 in 2001, 2006,
2012, 2018) — gating CCG to December would have incorrectly dropped those,
and widening the BOWL-side gate into late November to cover them instead
would reintroduce the venue-collision bug (Memphis/UTEP/Toledo/UCLA all play
real regular-season home games that late too — confirmed 12 such collisions
checking just the Nov 20-30 window).

**Two multiplier mechanisms apply these, both firing regardless of `type`**
(every CFB game, postseason included, is still `type='R'` by design — see
`normalize_sr_games.py`'s docstring):

- **`_postseason_mult()` / `postseason_round_mult`** — a CCG-style,
  type-agnostic parallel to NFL_Elo's inherited `playoff_round_mult`. This
  is necessary because `playoff_round_mult`/`_po_mult()` are **permanently
  inert for CFB** — they only ever fire for `type='P'` games, which never
  happens here. `playoff_round_mult` is kept only for structural parity
  with NFL_Elo; don't confuse the two when reading `engine.py`.
- **`_bowl_mult()` / `bowl_mult` + `bowl_rank_*`** — for `Round=="BOWL"`
  only. Both teams ranked → bonus decays **exponentially** off the best
  possible combined AP rank (`home_ap_rank + away_ap_rank`, ranges 3
  best-case to 49 worst-case) — a top-5-vs-top-5 bowl is disproportionately
  more major than a linear falloff would give it (explicit design choice —
  linear was the first draft, rejected). Exactly one team ranked → a much
  smaller, compressed-scale exponential bump using that team's own rank
  (deliberately small: this tier is rare and rarely involves a
  highly-ranked team anyway). Neither ranked → the flat `bowl_mult` base
  only.

**All of `postseason_round_mult`, `bowl_rank_bonus_max`, and
`bowl_one_ranked_bonus_max` are still at their no-op defaults** (`{}` /
`0.0`) — same "untuned placeholder" convention as `conf_championship_mult`
always has been. **Classification is done and now trustworthy (the
venue-collision bug above is fixed); the actual multiplier VALUES remain
untuned by deliberate decision** — see §10, item 2 for the reasoning on why
this is being left alone for now rather than tuned opportunistically.

**Source-data dedup** (`normalize_sr_games.dedupe_raw_rows()`) runs
immediately before classification, for a specific reason: `add_season.py`'s
insert uses `INSERT OR IGNORE` keyed on `(date, home, away, type, round)`.
Two raw rows for the same real game that differ only in `Notes` text used to
dedupe by accident (both got `Round=None` under the old CCG-only
classification) — but once classification can tell them apart (one
recognizes a bowl/event name, the other doesn't), they'd get *different*
`round` values and both insert successfully, double-counting that game. See
§2 for the concrete cases this actually caught.

### 5f. Overtime games (Nov 2026)

- **In the engine:** `ot_mult = 0.7 if g.get("ot") else 1.0` (`engine.py`, around
  line 508) — overtime games get a 0.7 multiplier, which I read as scaling the
  game's rating update (check the code before relying on that detail). It is a
  hard-coded constant inherited from the NFL version: not in
  `param_schedule.json`, never tuned for CFB. TJ's intent is that OT is part of
  the ratings.
- **Why it matters now:** until this session every CFB game had `ot = 0`, so the
  multiplier never fired and every tuned parameter (§7) and the old accuracy
  snapshot were produced without it. Turning on ~990 flags moved nearly every
  rating slightly (Elo is path-dependent — the first rebuild changed
  `pre_rate` in 99% of rows) but **did not change accuracy**: weighted over
  1996–2025, accuracy 72.88% → 72.94%, Brier 0.1781 → 0.1781, log loss 0.5283
  → 0.5283. That says OT does no harm; it says nothing about whether 0.7 is the
  right value.
- **Sources and how far to trust them:**
  - *1996–2000 — TJ's list.* ESPN is wrong in both directions here: against the
    list it flagged only about 40% of the real overtime games even when it had
    the game, it lacks 8–9% of these seasons' games altogether, and about 4 of
    its ~55 flags were false. That is why the early seasons first looked like
    1–2% OT rates (the real rate is ~4%).
  - *2001 — agreement.* ESPN matched TJ's list exactly (17 of 17, no extras),
    which is also why the list stops where it does.
  - *2002–2025 — ESPN, only spot-checked.* Three games with margins above 8
    were checked on Sports-Reference box scores: 2019 Wake Forest–Syracuse and
    2022 Kansas–West Virginia are real overtime games, and **2015-10-24 NC State
    at Wake Forest (35–17) is not** — four quarters only. The Wyoming–UNLV 2002
    game flagged by `signals_disagree` is real. **The 2015 game is a known ESPN
    false positive: `backfill_ot.py --apply` sets it back to 1, so clear it
    again after any re-run** (command in §9d). One suspected false negative is
    unchecked: the 2021 Army–Missouri Armed Forces Bowl (ESPN has `ot = 0`;
    worth a look at the box score). An independent audit of all ~830 flagged
    games against Sports-Reference box scores is possible (≈45 minutes at a
    polite request rate) and not done — §10, item 25.
  - *2026 — the xlsx.* `update_cfb_results.py` writes OT from ESPN's period
    count only (one signal, no cross-check), so glance at Sports-Reference's box
    score for the handful of OT games each week.
- **A margin above 8 does not rule out overtime.** A defensive score in overtime
  can make it larger (confirmed: 1996 USC–Arizona State, 1997 Duke–Clemson,
  1998 Central Michigan–Eastern Michigan, 2019 Wake Forest–Syracuse, 2022
  Kansas–West Virginia). Do not use margin as an OT sanity filter.

### 5g. Neutral-site games (Nov 2026)

- **In the engine:** `hfa = 0.0 if g.get("neutral") else params["hfa"]`
  (`engine.py`, around line 497; `preview_matchup` does the same), so a game
  flagged neutral gets no home-field advantage in the ratings, the predictions
  and the projections.
- **Where the flag comes from, and the trap in it.** Sports-Reference marks `N`
  in the `@` column; `add_season.py` (around line 157) stores each such game
  **once, with the alphabetically-first team in the home slot** (`Team <
  opponent`) and `neutral = 1`. So **the home/away labels on a neutral game are
  arbitrary.** That is harmless while the game stays neutral. It is wrong the
  moment a game is turned into a normal home game without fixing the host — the
  engine would give the home-field bump to whichever team sorts first. Of the 27
  games TJ switched from neutral to non-neutral on Nov 7, 13 had the stored home
  team backwards (and 20 of the 48 switched on Nov 14); `apply_neutral_overrides.py` fixes the orientation (swapping team,
  code, points and AP rank together) before it changes the flag.
- **What Sports-Reference's `N` means.** It covers real neutral sites *and*
  home games moved off campus (UMass at Gillette Stadium, Illinois at Soldier
  Field, Washington State "hosting" in Seattle). ESPN's `neutralSite` follows
  the nominal host instead. So "neutral" versus "relocated home game" is a
  judgment call; TJ made those calls in the Nov 2026 review (the review sheet is
  the record). Three of his non-neutral picks are worth revisiting if anyone
  cares, from my memory of the venues, which is unverified: Toledo–Ohio State
  2009 (Cleveland), SMU–Army 2010 (Armed Forces Bowl, Fort Worth) and
  Washington State–Stanford 2013 (Seattle).
- **Before the corrections** (neutral / games): BOWL 880/923, CCG 102/148, NC
  26/28, CFP-SF 24/24, CFP-QF 8/8, CFP-R1 0/8 (campus sites — correct), regular
  season 381/23,414. Florida–Georgia 31/31, Texas–Oklahoma 32/32, Army–Navy
  24/30. Of the 43 non-neutral bowls, most are a team hosting a bowl in its own
  stadium (Hawaii, Boise State, UNLV, FAU, Navy, Memphis...); a handful (the
  three USC Rose Bowls, some Peach/Music City bowls) were hosted in the home
  team's city but not its stadium — about a dozen games, left alone.
- **The 2008–2025 audit.** ESPN's flag is empty or near zero for every season
  before 2008, so only 2008 onward can be compared. Of 15,267 comparable games
  99.5% agreed; the 69 disagreements (errors on both sides) went into
  `neutral_review.csv`, and TJ reviewed all of them. **37 changes were applied**:
  10 games to neutral (Memphis–USF 2008, Missouri–Kansas 2009, Grambling–Louisiana
  Tech 2010, Arkansas–Texas A&M 2010, Notre Dame–Army 2010, Iowa–Northern Illinois
  2012, USC–Syracuse 2012, Tarleton State–New Mexico State 2021,
  Arkansas–Arkansas-Pine Bluff 2024, Illinois–Northwestern 2024) and 27 to
  non-neutral, of which 13 were swapped so the real host is home (Toledo–Ohio
  State 2009, SMU–Army 2010 bowl, Washington State–Stanford 2013,
  Houston–BYU 2013, UMass–Akron 2013, Buffalo–Bowling Green 2013,
  Washington State–Rutgers 2014, UMass–Colorado 2014, Vanderbilt–Ole Miss 2014,
  UMass–Eastern Michigan 2014, UCF–Arkansas State 2016 bowl, Hawaii–BYU 2019 bowl,
  USF–Memphis 2024). Flagged rows per variant were 2,789 after this review (lower after the Nov 14 audit below; current count: `select variant, sum(neutral) from ratings group by variant`).
- **Left as they were (judgment calls, all in the review sheet).** Of the games
  where ESPN says neutral and the database does not, TJ kept 22 non-neutral: 11
  bowls hosted in the home team's own stadium, and 11 regular-season games —
  Oregon State–TCU 2010, Boise State–Virginia Tech 2010, BYU–TCU 2011, Notre
  Dame–Maryland 2011, Army–Navy 2011, Louisiana-Monroe–Arkansas 2012,
  Wyoming–New Mexico 2020, Louisville–Georgia Tech 2023, Appalachian
  State–Charlotte 2025, Georgia–Georgia Tech 2025 and Maryland–Michigan State
  2025. From memory some of those were played at neutral venues (Arlington,
  Landover, Atlanta) and a few of ESPN's flags look wrong; unverified. Of the
  games where the database says neutral and ESPN does not, TJ kept 10 neutral
  (e.g. Georgia–Florida 2008, Oklahoma–BYU 2009, Washington State–Notre Dame
  2009, Texas–Oklahoma 2023).
- **The 1996–2007 audit and the local-team rule (Nov 14, 2026).** The results
  CSVs' `N` marker matched the DB's neutral flag exactly for 1996–2005 (and to
  within a few games after that, from the ESPN review and the echo
  duplicates), so the question was judgment, not data entry. ESPN cannot help
  before 2008 (no `neutralSite` flag, and the venue strings the probe printed
  for 2001–2007 looked wrong), so the audit used the CSV's `N` marker and venue
  `Notes` (§13), then ESPN's venue city from 2008 on. **Rule: a team playing in
  its own city or metro area counts as the home team** — non-neutral, with that
  team in the home slot — while mixed-crowd games stay neutral. TJ's calls:
  Navy or Army in the Maryland or New York area is home for that academy
  (Baltimore, Landover, the Bronx, East Rutherford); Stanford is home in bowls
  at Santa Clara but not in the Pac-12 championship; TCU is home at AT&T
  Stadium except in the Big 12 championship; Arkansas in Little Rock is home,
  even against Arkansas-Pine Bluff; Washington is home for an Apple Cup in
  Seattle; FIU is home over FAU in Miami; Northwestern is home at Wrigley Field
  except against Illinois (Illinois–Northwestern at Soldier Field 2015 and
  Wrigley 2024 stay neutral); Eastern Washington is home in Cheney but not in
  Spokane.
- **Result: 48 games changed to non-neutral, 20 of them swapped so the host is
  home** (seven batches, each applied, rebuilt and snapshot-compared):
  `pre2008_neutral_review.csv` (7: Eastern Washington–Idaho and Idaho–Washington
  State 1999, USC–Virginia Tech 2004, three Tulane home games in 2005, and the
  2008 Rose Bowl); `usf_override.csv` (1: South Florida–Memphis, the 2008
  St. Petersburg Bowl); `bowl_local_candidates2.csv` (29, 2013–2021);
  `override_2022plus.csv` (3: LA Bowl 2023, Fenway Bowl 2023, Texas Bowl 2025);
  `espn_local_candidates.csv` (7: FAU–FIU 2008 and six games from 2022–2025);
  `arkansas_override.csv` (1). Two of the Nov 7 decisions were reversed:
  Memphis–USF 2008 and Arkansas–Arkansas-Pine Bluff 2024 are non-neutral now.
  Army–Navy 1997/2000/2002/2007 stay non-neutral. The ratings moved little
  (largest single-game shift about 20 points, mean change under 0.2, nothing
  before 1999); §8 shows the accuracy effect.
- **Not covered, and known gaps.** Same-state-but-not-same-city games (Georgia
  in Atlanta, Florida's in-state bowls, Texas teams in Texas bowls) stay
  neutral on purpose. The city-to-team tables in the two scan scripts were
  written from memory, so a local team in a city missing from them was not
  caught; regular-season venue notes were only seen from about 2013 to 2021,
  so earlier regular-season neutral games rest on the CSV's `N` alone. One CSV
  note is wrong: Florida State–UCLA 2006 (the Emerald Bowl, in San Francisco)
  is labelled Rose Bowl - Pasadena. USC–Virginia Tech 2004 is the one flip whose
  host came from ESPN's orientation, not an explicit `host` (§10, item 28).
- After any batch, `ratings` and `games` should agree on neutral on every row
  (`ratings_snapshot.py neutral ../cfb_elo.db`).

## 6. Tuning philosophy — two tracks, not one grid search

- **Track A (log-loss coordinate ascent)** — `alpha`, `kmax`, `hfa`,
  `fcs_rating`, and (not yet added) `conf_game_mult`/`conf_championship_mult`/
  the new postseason multipliers. These directly reshape a game's predicted
  outcome, so minimizing prediction error is the right objective.
- **Track B (data-driven calibration, NOT grid search)** — things like the
  first-year-FBS discount (§5c/§10). These should be *measured* from
  observed outcomes, not searched for by minimizing overall log-loss, which
  risks quietly overfitting one noisy number to a handful of newcomer-seasons.

## 7. Tuning results — now a real walk-forward schedule, not a single window

**This is the biggest change since the last handoff.** `param_schedule.json`
now exists and is populated for every season 1996–2025 (built by
`cfb_build_param_schedule.py` — see §3 for its methodology). Sample values,
showing genuine era drift rather than one flat number everywhere:

| Season | alpha | kmax | hfa | fcs_rating |
|---|---|---|---|---|
| 1996 | 0.7 | 96 | 68 | 1100 |
| 2006 | 0.7 | 96 | 68 | 1075 |
| 2010 | 0.7 | 88 | 68 | 1075 |
| 2014 | 0.6 | 100 | 60 | 1075 |
| 2020 | 0.6 | 100 | 44 | 925 |
| 2025 | 0.6 | 100 | 44 | 925 |

`fcs_rating` is tuned separately (`cfb_tune_fcs_rating.py`, era-block values:
1100 for 1996–2005, 1075 for 2006–2015, 925 for 2016–2025 — too thin a
sample to tune on the same rolling cadence as the other three) and slotted
in by season when the schedule is built. `alpha`/`kmax`/`hfa` are searched
per rolling 10-year window, seeded from one continuous engine's real
snapshotted state at each window boundary — genuinely equivalent to what
production's continuous replay does, not an artificial fresh-restart-per-window
search. **Confirmed this session: `param_schedule.json` contains no entries
for `postseason_round_mult`/`bowl_mult`/`conf_championship_mult`** — those
still fall back to `engine.py`'s untuned `BASELINE_PARAMS` defaults for
every season, regardless of the schedule. This is the concrete gap behind
§10, item 1.

**Note added Oct 2026 — what is actually in force.** The table above shows
rounded values. The exact 2025 entry in `param_schedule.json` is
`alpha 0.58, kmax 100.5, hfa 45.5, fcs_rating 925`, and **2026 has no entry,
so it reuses those** (seasons past the last entry fall back to it).
`engine.py`'s `BASELINE_PARAMS` (`alpha 0.3, kmax 46, hfa 72, fcs_rating 1200`,
…) is only the fallback for parameters the schedule does not set (the
postseason/bowl/conference-championship multipliers), and its comment calling
the whole dict "untuned" is stale. If you add a 2026 entry, re-run
`cfb_build_param_schedule.py` rather than editing the JSON by hand. Two further
caveats (Nov 2026): the overtime multiplier (`ot_mult = 0.7`, §5f) is a
hard-coded constant in `engine.py`, not a schedule parameter; and the whole
schedule was fit **before** any OT flag existed (every game had `ot = 0`) and
before the neutral-flag corrections (§5g). It has not been re-tuned since; the
measured effect on accuracy was nil, so a re-tune is optional.

The original "2006 parameters" walk-forward validation from the previous
handoff (`alpha=0.7, kmax=96, hfa=68`, holdout log-loss 0.4998 vs. untuned
baseline's 0.5176) is superseded by this full schedule — no need to keep
re-deriving that one-window proof of concept, it's been generalized into
the real cadence now.

## 8. Accuracy snapshot — Nov 14, 2026, Echo and Pulse, after the neutral-site audit

Produced by `accuracy_report.py` (§3d): Echo with the defaults, Pulse with
`--variant pulse` (the first Pulse run). **FBS-vs-FBS games only**, all seasons
1996–2026, 21,960 games, through the results loaded in the first week of
November. It was run **after** the three duplicate games were removed and after
the neutral-site audit (§2, §5g): 48 games the data had as neutral were changed
to non-neutral under the local-team rule (a team playing in its own city or
metro area counts as home), 20 of them with the real host moved into the home
slot. The audit covered the 1996–2007 flags, the 2008+ ESPN-disagreement
review, the bowl and championship games, and an ESPN-venue scan; scripts and
rubric are in §5g. The full output (by season and month, upsets, worst misses)
is in `reports/accuracy_summary_echo.txt` and `reports/accuracy_summary_pulse.txt`.

**What the audit moved (Echo, vs. the Nov 7 snapshot).** The postseason rows,
where most of the changed games sit, improved slightly: Postseason Brier
0.2370 → 0.2369 and log loss 0.6676 → 0.6672; BOWL Brier 0.2382 → 0.2380 and
log loss 0.6705 → 0.6701; accuracy is unchanged. The All-games and Regular-season
figures also include 70 additional games (73 new, minus the 3 duplicates), so
their small changes (All-games Brier 0.1782 → 0.1783) can't be attributed to
the audit. The always-pick-home baseline moved 59.4% → 59.3%.

**Echo**

| Group | n | Accuracy | Brier | Log loss |
|---|---|---|---|---|
| All games | 21,960 | 72.9% | 0.1783 | 0.5290 |
| Regular season (incl. CCG, as the site counts it) | 20,970 | 73.5% | 0.1756 | 0.5225 |
| Postseason (BOWL, CFP, NC) | 990 | 60.0% | 0.2369 | 0.6672 |
| Overtime games | 961 | 54.8% | 0.2675 | 0.7472 |

By round:

| Round | n | Accuracy | Brier | Log loss |
|---|---|---|---|---|
| Regular season (excl. CCG) | 20,822 | 73.5% | 0.1755 | 0.5222 |
| CCG | 148 | 72.3% | 0.1891 | 0.5606 |
| BOWL | 922 | 59.9% | 0.2380 | 0.6701 |
| CFP-R1 | 8 | 87.5% | 0.1310 | 0.4208 |
| CFP-QF | 8 | 50.0% | 0.2661 | 0.7262 |
| CFP-SF | 24 | 62.5% | 0.2040 | 0.5918 |
| NC | 28 | 57.1% | 0.2489 | 0.6911 |

Calibration (predicted → actual win rate): 50–60% 55.1 → 55.1 (2,455 games);
60–70% 65.0 → 65.1 (2,567); 70–80% 75.1 → 73.1 (2,813); 80–90% 85.0 → 84.1
(2,973); 90%+ 94.5 → 95.2 (2,856). Always-pick-home baseline: 59.3%
(non-neutral FBS-vs-FBS games). Coin-flip Brier: 0.2500.

**Pulse**

| Group | n | Accuracy | Brier | Log loss |
|---|---|---|---|---|
| All games | 21,960 | 70.8% | 0.1882 | 0.5540 |
| Regular season (incl. CCG, as the site counts it) | 20,970 | 71.3% | 0.1859 | 0.5487 |
| Postseason (BOWL, CFP, NC) | 990 | 60.4% | 0.2370 | 0.6674 |
| Overtime games | 961 | 55.0% | 0.2638 | 0.7325 |

By round:

| Round | n | Accuracy | Brier | Log loss |
|---|---|---|---|---|
| Regular season (excl. CCG) | 20,822 | 71.3% | 0.1858 | 0.5484 |
| CCG | 148 | 68.9% | 0.2002 | 0.5871 |
| BOWL | 922 | 60.0% | 0.2387 | 0.6711 |
| CFP-R1 | 8 | 75.0% | 0.1563 | 0.4778 |
| CFP-QF | 8 | 62.5% | 0.2409 | 0.6721 |
| CFP-SF | 24 | 66.7% | 0.1980 | 0.5810 |
| NC | 28 | 64.3% | 0.2383 | 0.6712 |

Calibration (predicted → actual win rate): 50–60% 55.2 → 53.3 (3,373 games);
60–70% 64.9 → 65.1 (3,314); 70–80% 74.9 → 75.4 (3,035); 80–90% 85.0 → 86.2
(2,840); 90%+ 93.6 → 95.4 (1,829).

**Pulse vs. Echo.** Pulse is less accurate overall (70.8% vs. 72.9%, Brier
0.1882 vs. 0.1783), which fits its design: no conference information, and
regression toward a flat base each season (§5c). It makes fewer confident
predictions (1,829 games at 90%+ vs. Echo's 2,856) and is underconfident at the
top (93.6% predicted vs. 95.4% actual) and overconfident in its 50–60% bucket
(55.2% vs. 53.3%). The postseason is close to a tie: 60.4% / 0.2370 for Pulse
vs. 60.0% / 0.2369 for Echo. CCG favors Echo (72.3% vs. 68.9%), and Pulse's
higher NC accuracy (64.3% vs. 57.1%) is two games out of 28.

*The three notes below are from the Nov 7 snapshot and kept for history; their figures are not the ones in the tables above.*

**Before and after overtime.** The same script on a backup taken before the OT
rebuild (`--db`) reproduced the previous snapshot's postseason rows to four
decimals — BOWL 60.2% / 0.2382, CCG 72.3% / 0.1892, CFP-R1 87.5% / 0.1325,
CFP-QF 50.0% / 0.2689, CFP-SF 62.5% / 0.2056, NC 53.6% / 0.2500 — which
validates both the script and the database. Turning OT on moved those rows by
about a game each (BOWL 60.2% → 59.9%, NC 53.6% → 57.1% = one game of 28) and
the 1996–2025 aggregate by +0.06 points of accuracy (§5f).

**Not comparable with the earlier "Regular season 21,750 games, 74.7%,
Brier 0.1683" line.** That used a broader set of games (apparently including
FCS opponents, who are easy to predict) and the old "always-pick-home ≈ 62%"
had the same cause. On FBS-vs-FBS games the pre-OT figure was 73.4% / 0.1753
(20,696 games). Use the tables above.

**Earlier notes (still true):**

**What changed vs. the contaminated numbers, and why it matters:** BOWL
accuracy actually went DOWN (60.2%, was 61.9%) — the misclassified games
(mostly Memphis/UTEP/Toledo beating overmatched non-conference opponents)
were easy, correctly-predicted games that had been quietly propping the
number up. The real postseason gap is a bit worse than originally reported,
but now it's measuring the right thing. CFP-SF improved substantially
(62.5%, was 51.5%) now that its own independent venue-collision false
positives (2015 Cotton Bowl, 2017 Rose Bowl — see §5e) are gone.

**Reading the BOWL gap:** TJ's read, which the data doesn't contradict — a
lot of non-CFP bowl games are closer to preseason exhibitions than
high-stakes postseason football for a lot of the teams in them (opt-outs,
portal departures, low stakes for a 6-6 team in a minor bowl), which an Elo
model that only ever sees team-vs-team results has no way to see. `CFP-SF`/
`NC` sitting near a coin flip is a small sample (24-28 games) and may partly
reflect that a title-adjacent game is, by construction, a matchup between
two elite teams with a genuinely small true gap — not necessarily a
calibration failure.

## 9. Standard per-season / update-season workflow

### 9a. Daily loop during the season (Windows `cmd`, project root `...\tracersports-app`)

Run it each time a batch of games has finished. It is safe to run mid-slate
and safe to repeat — anything not final yet is simply picked up next time.

```
:: 1. ESPN finals into the xlsx           (from DBs)
python update_cfb_results.py --file cfb\Results\CFB_2026_Results.xlsx

:: 2. xlsx -> blank CSV rows               (from DBs\cfb; dry run, read it, then --apply)
python fill_csv_from_xlsx.py Results\CFB_2026_Results.xlsx Results\CFB_2026_Results.csv
python fill_csv_from_xlsx.py Results\CFB_2026_Results.xlsx Results\CFB_2026_Results.csv --apply

:: 3. load the Elo DB                      (from DBs\cfb)
python normalize_sr_games.py Results\CFB_2026_Results.csv parsed_results\parsed_games_2026.csv
python add_season.py parsed_results\parsed_games_2026.csv

:: 3b. overtime flags into the DB       (from DBs\cfb; dry run, read it, then --apply)
python apply_ot_xlsx.py Results\CFB_2026_Results.xlsx
python apply_ot_xlsx.py Results\CFB_2026_Results.xlsx --apply
python rebuild_ratings_only.py

:: 4. look at it
python show_ratings.py

:: 5. check xlsx vs CSV                    (from DBs; want 0 / 0 / 0)
python compare_xlsx_vs_csv.py cfb\Results\CFB_2026_Results.xlsx cfb\Results\CFB_2026_Results.csv
```

Checks along the way: step 1's `Scores filled for N game(s)`; step 2's dry run
should list exactly N games and no ties; step 3's `add_season` must report
`Inserted N new completed game(s)` (same N) and `Sanity checks passed` for
both variants — stop if N differs; step 3b's dry run should list only the OT
games from that slate. **Why 3b exists:** `add_season.py` loads every new game
with `ot = 0` and rebuilds the ratings before the flags are set, so without the
second rebuild an overtime game's rating change would miss the 0.7 multiplier
(§5f); as far as I can tell, the schedule predictions written in step 3 predate
that rebuild and are rewritten by the next `add_season` run. When the CSV is refreshed from
Sports-Reference, also run the §9e checks. End of day: `python simulate_season.py
--season 2026`, then the Supabase export (§12). A Saturday finishes across
roughly four windows (noon / 3:30 / 7:00–7:30 / 10:15–10:30 ET). The loop
reads Sports-Reference's CSV as the base and layers ESPN on top; when
Sports-Reference publishes its own update, replace the CSV and run steps 2–5
(step 2 then finds nothing to fill) and use step 5 to see any disagreement —
the DB keeps the **first** score it loaded for a game.

### 9b. Fixing a wrong or tied score

`add_season.py` inserts with `INSERT OR IGNORE` on (date, teams, round), so a
corrected CSV row does **not** replace an existing one. Fix the score in the
CSV, delete the bad DB row, then reload (run from `DBs\cfb`; change the date):

```
python -c "import sqlite3;c=sqlite3.connect('../cfb_elo.db');print(c.execute('select game_id,home_code,away_code,home_pts,away_pts from games where date like ?',('2026-10-06',)).fetchall())"
python -c "import sqlite3;c=sqlite3.connect('../cfb_elo.db');n=c.execute('delete from games where date=? and home_pts=0 and away_pts=0',('2026-10-06',)).rowcount;c.commit();print('deleted',n)"
```

then step 3 again. If the game was already exported, the corrected row will not
overwrite it in Supabase (§12) — delete that season's CFB game rows there and
re-export.

### 9c. Loading a new season from scratch

```
python3 normalize_sr_games.py Results/CFB_YYYY_Results.csv parsed_results/parsed_games_YYYY.csv
python3 add_season.py parsed_results/parsed_games_YYYY.csv
python3 load_conference_membership.py Standings/CFB_YYYY_Standings.csv --season YYYY
```

**Order matters:** conference membership must load *after* games for that
season, or every team in it will look FCS (no `fbs_membership` row yet) and
get excluded from standings until the conference step catches up. Confirmed
directly: running these out of order on 2026 produced a successful-looking
load (260 games inserted, 0 sanity warnings) with completely empty standings.
Both `add_season.py` and `load_conference_membership.py` trigger their own
full rebuild, so re-running either is always safe. In-progress seasons work:
`normalize_sr_games.py` routes a score-less row to `schedule` if its date is
today-or-future (small buffer for a same-day result not yet posted) and drops
it only if it is further in the past. For a new season also: build that
season's xlsx with `csv_to_long.py` and point `update_cfb_results.py` at it;
pass the new season to the config generator (`--season`) and regenerate
`config.js` (§12); add any new team to `cfb_team_names.xlsx` and
`cfb_team_colors.csv` (the generator and `apply_display_names.py` both list
missing teams).

### 9d. After a re-ingest (`reingest_phase2.py`) — or whenever the games table is reloaded

A reload brings back Sports-Reference's data exactly as the CSVs hold it:
**no OT flags, its home/away order for neutral games, and no DB-only fixes.**
(That `reingest_phase2.py` really does discard them is very likely but has not
been tested.) The appliers are keyed on date + teams, not `game_id`, so they
re-apply cleanly. Run from `DBs\cfb`, dry run first for each:

```
python backfill_ot.py --apply                                   :: ESPN flags, all seasons (reuses espn_cache)
python apply_ot_list.py --apply                                 :: 1996-2000 from the hand list (overrides ESPN)
python apply_ot_xlsx.py Results\CFB_2026_Results.xlsx --apply   :: 2026
python apply_neutral_overrides.py neutral_review.csv --apply            :: Nov 7 neutral flags + host swaps
python apply_neutral_overrides.py pre2008_neutral_review.csv --apply    :: Nov 14 batches, in this order
python apply_neutral_overrides.py usf_override.csv --apply
python apply_neutral_overrides.py bowl_local_candidates2.csv --apply
python apply_neutral_overrides.py override_2022plus.csv --apply
python apply_neutral_overrides.py espn_local_candidates.csv --apply
python apply_neutral_overrides.py arkansas_override.csv --apply
python -c "import sqlite3;c=sqlite3.connect('../cfb_elo.db');c.execute('update games set ot=0 where substr(date,1,10)=? and home_code=? and away_code=?',('2015-10-24','wake-forest','north-carolina-state'));c.commit();print('cleared the known ESPN false positive')"
python rebuild_ratings_only.py
python ratings_snapshot.py neutral ../cfb_elo.db
```

The order of the neutral sheets matters: `usf_override.csv` and
`arkansas_override.csv` reverse two decisions in `neutral_review.csv`, so they
must run after it. Replaying all seven sheets on a rebuilt database was tested on Nov 16: it
reproduced the same ratings (largest change 0.0) and the same flags
(`ratings_snapshot.py neutral`: 0 disagreements). Keep every sheet in the repo
as the record — and do not
re-run `check_neutral_vs_espn.py`, `bowl_local_candidates2.py` or
`espn_local_candidates.py` to regenerate them (they overwrite the sheets, and
on a database whose flags are already applied they would find nothing).

Also confirm the CSV edits survived (they are what stop the bad rows coming
back): the second rows for the three echo duplicates are gone (§2) and the two
phantom 2026 games are not in the CSV or the xlsx. The pattern for any change
that should *not* move ratings: `ratings_snapshot.py dump` → change →
`rebuild_ratings_only.py` → `dump` → `compare`; only the intended columns may
differ.

### 9e. Sanity checks for a refreshed CSV / schedule

The Nov 2026 phantom games and duplicate rows were all findable by one idea: a
football team cannot play twice in three days, and plays 12–13 games. Run this
over `games` after loading a season (history should print nothing, apart from
possible postponed games):

```
python -c "import sqlite3;c=sqlite3.connect('../cfb_elo.db');q='with t as (select game_id,season,date,home_code as team from games union all select game_id,season,date,away_code from games) select a.team,a.date,b.date from t a join t b on a.team=b.team and a.season=b.season and a.game_id<b.game_id and abs(julianday(a.date)-julianday(b.date))<=3 order by a.date';r=c.execute(q).fetchall();print(len(r));[print(x) for x in r[:40]]"
```

For the **unplayed** part of a season (the same check on `schedule`, or on the
sheet): any team listed twice within three days, a team with more than 13
games, a game on a Sunday or Monday, or a neutral-flagged game between two
teams that play each other on a campus (Central Michigan–Eastern Michigan on
Wed Nov 4, 2026 is flagged `N` in the sheet and looked wrong to me; unchecked)
is worth a look before it reaches the site.

## 10. What's left to do (in rough priority order)

Items 1, 3, 4, 8, 11, 13, 14 (played games) and 16 are done. Items 2 and 9 are
deliberately deferred. Item 6 (site integration) is **mostly done** — its
remaining pieces are listed under it. Items 20–27 are new since Nov 2026.

1. ~~Fix the unplayed-games/schedule bug.~~ **DONE** (§2, §9c).

2. **Tune the postseason multipliers — explicitly SKIPPED for now, by
   decision, not an oversight.** `postseason_round_mult`, `bowl_rank_bonus_max`,
   `bowl_one_ranked_bonus_max` and `conf_championship_mult` are still at their
   no-op defaults. Classification is trustworthy (§5e), so this is a
   legitimate Track A job whenever it is picked back up. Re-read §8's reading
   of the BOWL gap first: TJ's view is that much of it reflects real
   low-stakes/opt-out dynamics an Elo model cannot see.

3. ~~Investigate the BOWL-accuracy gap.~~ **DONE** (§5e, §8).

4. ~~Port `simulate_season.py`.~~ **DONE** (§3).

5. **`DBs/` migration — core move DONE, structural gaps remain:**
   `delete_season.py`, `stabilization_check.py`, `test_db.py` and
   `test_engine.py` exist for nba/nfl/wnba but not CFB. (The accuracy-report
   naming gap is closed — `accuracy_report.py`, §3d. The siblings' `report.py`
   is a standings/game-log dumper that CFB does not have.)

6. **Supabase/site integration — MOSTLY DONE (details in §12).** Done: exporter
   support, schema migration, two real pushes, generated config, registry
   entry, renamed logos, verified colors, Rankings + conference-only
   Standings pages (running on localhost). **Remaining:**
   - **Verify the Nov 16 re-export** (item 20): in Supabase, that bowl/CFP rows
     are `type = 'P'` and no `R` row has a `round` (query in §12) — not yet
     confirmed. The game type is part of the natural key and games
     are insert-only, so always `delete from games where league='cfb'` first.
   - Review the pages against **live** data on a preview branch: desktop and
     mobile, the Team / Season / All-Time routes (never exercised for CFB), and
     what the shared code does with 138 teams.
   - Merge/deploy once reviewed (the registry entry is what makes `/cfb` exist).
   - **Restore the Games panel on the Rankings tab** — TJ wants it back (it was
     dropped to match the mockup's full-width table).
   - **Postseason tab** — currently a "coming soon" placeholder (the CFP has
     no bracket component; `playoffFormat.type: 'cfp'` is unrecognized on
     purpose). **Not needed until December**, by TJ's decision; needs a CFP
     bracket and/or a bowl list.
   - **Conferences tab** (average rating by conference, as in
     `show_ratings.py --by conf`) — TJ does not want it (at most leaning
     no). **History** tab from the mockup — not started.

7. **First-year-FBS discount calibration (Track B) — still not actionable.**
   Needs enough real newcomer-season data. Do not grid-search this (§6).

8. ~~Fix `add_season.py`'s stale docstring.~~ **DONE.**

9. **Close `predict.py`'s known gap — deliberately deferred, low urgency**
   (flat `base` rating instead of conference-average before a season's first
   game is loaded; matters again only at next preseason).

10. ~~Extend `conference_tier` seed data.~~ **REVIEWED, no change.** WAC and
    American were never power-equivalent, so the existing binary fallback is
    right. **Open question for TJ:** is a third tier wanted for the American,
    or is binary fine? Note P4/G6 is now also defined in `show_ratings.py`
    (constants at the top) and in the config generator (`P4_CONFS`,
    `ALWAYS_P4`) — if the definition changes, change all three places.

11. **Routine maintenance:** check `reports/unresolved_conference_teams_*.csv`
    whenever a season is loaded (0 unresolved for 2026), and keep
    `update_cfb_results.py`'s `ALIASES` current — the 2026 FBS names all
    resolve; unmapped FCS names are harmless unless the team is on the sheet.

12. **Add a tie / 0–0 guard to `normalize_sr_games.py`** (still open). FBS has
    had no ties since 1996, and a 0–0 is a placeholder, not a result (the Troy–
    Southern Miss incident, §2). Treat a tied or 0–0 score as unplayed (route
    to `schedule`) and print a warning. The site config already has
    `minValidGameScore: 1` as a second line of defense. **Add the second guard
    from Nov 2026 alongside it:** drop a game when the same two teams and the
    same score appear within a day and the later row has a blank `Notes` (the
    time-zone echo duplicates, §2) — `dedupe_raw_rows()` cannot see those.

13. ~~Carry the OT flag into the DB.~~ **DONE (Nov 2026)** for every season
    (§5f, §3d). The one caveat that remains is item 25.

14. ~~Neutral-site flag for played games.~~ **DONE (Nov 2026)**:
    `ratings.neutral` exists, the exporter sends it, the 2008+ flags were
    audited against ESPN (Nov 7) and 1996–2026 against the local-team rule
    (Nov 14, item 21) — §5g.

15. **Supabase corrections caveat / current-season replace.** Games are
    inserted `ON CONFLICT DO NOTHING`; a score or flag corrected after export
    never reaches Supabase, nor do the rating changes it causes downstream.
    Today's workaround is delete-and-re-export (§9b, item 20). The durable fix
    is to patch the exporter to replace the current season's CFB rows each run
    (the way `schedule` and projections already are).

16. ~~FCS opponents have no preseason rating.~~ **DONE (Nov 2026)** — §12.

17. **Export per-season conference membership.** Supabase `teams` has
    `conference = NULL` for CFB; the site groups by the config's *current*
    alignment, so past seasons' conference standings are approximate (the tab
    says so whenever the season is not `alignmentSeason`). Lower value now that
    the Conferences tab is off the table; it still affects past-season
    Standings.

18. **Housekeeping.** `check_bowl_accuracy.py` is gone from the repo (replaced
    by `accuracy_report.py`); correct `engine.py`'s stale "untuned
    `BASELINE_PARAMS`" comments (§7 note); consider adding a 2026 entry to
    `param_schedule.json`; delete the obsolete `ot_overrides.py` and
    `ot_worklist.csv`.

19. **Split team IDs are intentional.** Dixie State / Utah Tech and Texas A&M–
    Commerce / East Texas A&M are separate `team_id`s because the program was
    renamed while FCS. The FCS fixed-rating mechanism (§5b) makes the split
    harmless to Elo; each ID has its own era-accurate display name. There is
    no merge command in `franchise.py` and none is needed.

20. ~~Re-export CFB games to Supabase.~~ **DONE (Nov 16, 2026)** — §12.
    The first push after the audit did *not* delete the old CFB rows, and
    Supabase kept the pre-audit flags (the Apple Cup, 2024-09-14, still showed
    `neutral = 1`); `delete from games where league = 'cfb';` followed by a
    second run of the exporter fixed it, and the same query then showed
    `neutral = 0` on both rows (§13).

21. ~~Pre-2008 neutral-site audit.~~ **DONE (Nov 14, 2026)** — §5g. The
    venue-based detector was dropped (ESPN has no usable pre-2008 venue data,
    and `probe_old_venues.py` read the wrong `Notes` column, §13); the audit
    used the CSV `N` markers, the venue `Notes`, ESPN's venue city (2008+) and
    a local-team rule instead, and 48 games changed. Army–Navy
    1997/2000/2002/2007 stay non-neutral.

22. **Guards in `normalize_sr_games.py` (new)** — see item 12 (tie/0–0 and
    blank-notes echo duplicates).

23. ~~Refresh §8.~~ **DONE (Nov 14, 2026)** — both variants, after the
    duplicate removal and both neutral passes. Re-run it after the next flag
    change.

24. **Make the data fixes survive a reload (new).** The OT flags, neutral
    corrections, host swaps and the ESPN false-positive exception live only in
    the DB (re-applied by §9d). A reload wrapper — or folding OT and the
    overrides into the normalize/add_season path — would remove the manual
    re-apply step. Until then, never run `reingest_phase2.py` without §9d. The Nov 14 override
    sheets (§9d) are part of that record — commit them.

25. **Optional: audit ESPN's OT flags for 2002–2025 (new).** Fetch the
    Sports-Reference box score for each flagged game (~830, ≈45 minutes under
    Sports-Reference's rate limit) and check for an overtime column; check the
    2021 Army–Missouri game first. This catches false positives, not missed
    games (ESPN's recall looked complete from 2001).

26. **Optional: tune `ot_mult` (new).** The 0.7 is a hard-coded constant from
    the NFL version (§5f); a walk-forward test of other values is possible once
    it is made a parameter. Low priority — turning OT on changed accuracy by
    +0.06 points.

27. **Small checks (new):** the Central Michigan–Eastern Michigan `N` flag on
    Wed Nov 4, 2026 (§9e); the judgment calls in §5g if anyone wants them
    revisited (the three games switched to non-neutral at venues I remember as
    off-campus, and the 11 regular-season games ESPN calls neutral that were
    left non-neutral, Army–Navy 2011 among them, which matches the Nov 14
    local-team rule); and a look at how the phantom games got into
    the 2026 CSV, so a refresh does not bring them back (§9e).

28. **Confirm the USC–Virginia Tech 2004 host (new).** The one flip in the
    Nov 14 audit whose home slot came from ESPN's orientation instead of an
    explicit `host` (the sheet put Virginia Tech at home). If that is wrong, the
    two sides need swapping (team, code, points and AP rank together) and the
    ratings rebuilt; either way put the host in `pre2008_neutral_review.csv`'s
    `host` column so the record is explicit.

29. **Optional: widen the local-team scan (new).** The city-to-team tables in
    `bowl_local_candidates2.py` and `espn_local_candidates.py` were written from
    memory, and same-state cases were left neutral on purpose (§5g). A local team
    in a city missing from the tables was not caught.

## 11. Team names, colors and logos — how they are keyed

- **Identity:** slug = team code = `team_id` on the site (`ohio-state`,
  `miami-fl`, `texas-a-m`). Never rename a code; rename the *display name*.
- **Names:** `cfb_team_names.xlsx` → `apply_display_names.py` →
  `teams.team_name` + the current `team_history.name`, plus
  `team_display_names.json`. "Full" is school + mascot ("Ohio State
  Buckeyes"); "short" is what compact views use ("Ohio State", "Ole Miss",
  "UConn", "UAB"). The config derives `city` (school) and `nickname` (mascot)
  by splitting the full name against the short and Sports-Reference names; the
  generator reports any it cannot split (none currently).
- **Colors:** all 138 FBS teams are `verified` in `cfb_team_colors.csv`. TJ's
  own sheet (`CFB_Team_Colors.xlsx`) is the source of truth — several values
  differ from the school brand guides on purpose (e.g. Ole Miss). The process
  used: look up each school's brand guide (hex first, Pantone converted only
  when no hex is published), propose one conference at a time, confirm, then
  flip `status`. Order is primary / secondary / tertiary; tertiary defaults to
  white. `lib/teamColors.js` only treats `#000000`, `#010101`, `#101820` as
  black and only inspects the **primary** (a black primary falls back to the
  secondary), so use one of those for a black primary; the generator warns
  about any other near-black primary.
- **Logos:** `public/logos/cfb/{slug}.png`, 138 files.
- **Conference labels** in the config: `SEC, Big Ten, Big 12, ACC, American,
  Sun Belt, MWC, MAC, CUSA, Pac-12, Ind` (shown as "Mountain West", "C-USA",
  "Independent"). 2026 sizes: 16 / 18 / 16 / 17 / 14 / 14 / 10 / 13 / 10 / 8 / 2
  in that order — ACC is 17 and `Ind` is 2 because the colors CSV lists Notre
  Dame as `Ind` (the DB still has it in the ACC; `show_ratings.py` reads the DB
  and counts it P4 regardless). P4 = SEC, Big Ten, Big 12, ACC + Notre Dame
  (68 teams); G6 = everything else (70).

## 12. Supabase export and site pages

**Exporter changes (all in `DBs/export_to_supabase.py`):**
`"cfb": "football"` in `SPORT_FOR_LEAGUE`; `ACTIVE_CODES["cfb"]` is built at run
time from the latest `fbs_membership` season (138 teams) instead of a hand
list; `NO_TIEBREAKER_LEAGUES = {"cfb"}` skips the NBA/NFL-style tiebreaker check
(it prompts interactively and writes into `lib/sports/tiebreakerOverrides.json`,
and CFB has no single league table); `build_schedule()` selects `NULL AS
predicted_spread` when the column does not exist (CFB has no betting-lines
dataset, so no calibrated spread); and `site_type_round()` re-labels postseason
rows because the site reads `type = 'R'` as "counts toward the regular-season
record" and `'P'` as postseason — `BOWL, CFP-R1, CFP-QF, CFP-SF, NC` export as
`P` (round kept), and `CCG` exports as plain `R` with no round (a conference
title game counts toward the regular-season record). Patches:
`cfb_exporter.patch`, `cfb_postseason_type.patch`.

**Exporter changes, Nov 2026** (same file, two edits):
- *Neutral flag.* `build_games()` takes `neutral` from `ratings.neutral` when
  the column exists (CFB's now does, §4); if a league's ratings table lacks it,
  it falls back to `games.neutral` through a subquery on `game_id` (a join would
  make the SELECT's unqualified column names ambiguous), and then to a constant
  0, so a league with neither still exports instead of crashing.
- *Scheduled FCS opponents.* `add_fcs_preseason_ratings()` (CFB only, called just
  before the coverage check) gives every scheduled team outside the active FBS
  set a preseason rating when it has none. The rating is read back from the
  data: each FBS-vs-FCS game row already carries the FCS team's fixed rating in
  `opp_pre_gm_rate`, constant within a season, so the function uses the most
  common value among opponents with no rows of their own (and warns if there is
  more than one). A season with no FBS-vs-FCS game played yet borrows the latest
  earlier season's value and says so. It never touches an FBS team, so an FBS
  team that is genuinely missing a rating still trips the coverage warning.
  Result: Chattanooga, Merrimack, Samford, Tennessee Tech and Wofford export at
  925.0 in both variants (preseason rows 7,654 → 7,664), and the "scheduled
  season without preseason ratings" warning is gone.

**Supabase side:** the live `games` and `schedule` tables needed
`ALTER TABLE ... ADD COLUMN IF NOT EXISTS neutral INTEGER NOT NULL DEFAULT 0`
(the exporter writes it; `schema.sql` already has it) and `schedule` needed
`predicted_spread FLOAT`. League is a plain TEXT column, so a new league needs
no schema change.

**Behavior to know:** one transaction, committed once at the end (a crash leaves
nothing half-written). `games`: insert-only. `schedule` and `season_projections`:
replaced per league each run. `teams` / `team_history`: upserted, so renamed
display names flow through. First-push sizes: 263 teams (138 active), 46,258
game rows per variant, 380 upcoming games × 4 schedule rows, 276 projection
rows, 7,654 preseason rows. **Second push (Nov 7, 2026):** 263 teams, 263
team_history rows, 92,952 game rows (46,476 per variant), 1,064 schedule rows
(266 upcoming games × 4), 276 projection rows, 7,664 preseason rows — sent
*before* the neutral corrections of Nov 7 and Nov 14. **Third push (Nov 16,
2026), after both neutral passes and after deleting the old CFB game rows:**
263 teams, 263 team_history rows, 93,470 game rows (46,735 per variant), 544
schedule rows (136 upcoming games × 4), 276 projection rows, 7,662 preseason
rows. Check made afterwards: the 2024 Apple Cup shows `neutral = 0` on both
rows (Washington H, Washington State A).

**Check the postseason mapping landed:**

```sql
select type, round, count(*) from games where league='cfb' group by 1,2 order by 3 desc;
-- want: type P with BOWL (largest), NC, CFP-SF, CFP-QF, CFP-R1; type R with round NULL only
```

and, after any export, that a team's latest `post_gm_rate` matches what
`show_ratings.py` prints for it. Also compare the totals with the local
database — the exporter's game rows should equal `ratings` rows (93,470 on Nov 16), and
these should match:

```
python -c "import sqlite3;c=sqlite3.connect('cfb_elo.db');print(c.execute('select variant,count(*),sum(ot),sum(neutral) from ratings group by variant').fetchall())"
```
```sql
select variant, count(*), sum(ot), sum(neutral) from games where league = 'cfb' group by variant;
```

**Site pages (built and running on localhost; not yet reviewed on live data):**
- *Rankings* (`CfbRankings.jsx`, driven by `rankingsView: 'tiered'`): header
  "Power Rankings · College Football · updated after Week N" (the week
  numbering reproduces Sports-Reference's `Wk` on 889 of 890 games; weeks run
  Tuesday–Monday); small Tier (All/P4/G6) and Show (25/50/100/All) toggles plus
  a conference dropdown styled like the league selector; RK is the national
  rank and Conf RK the rank inside the conference, and neither changes under a
  filter; a G6 tag while unfiltered; a summary line with the average rating of
  the teams shown.
- *Standings* (`CfbStandings.jsx`, `standingsView: 'conference'`): conference
  cards only (a 138-team league table would imply the playoff field is "the 12
  best records"). Columns Conf and Overall, regular season only, sorted by
  conference win% → overall win% → rating (real conference tiebreakers are not
  modelled). Conference records are computed in the browser from the game rows
  (a game counts when both teams share a config conference; FCS opponents never
  do) and were cross-checked against an independent tally for all 138 teams.
- *Postseason* tab: placeholder. *Conferences* and *History* tabs from the
  mockup: not built.
- Checks run when these were built: pure-logic tests in node, server-rendered
  HTML assertions under many filter combinations, `next build`, and ESLint.
  Not done: a real browser pass. `page.js` carries two ESLint "setState in
  effect" errors that predate the CFB work.

## 13. Gotchas learned the hard way (new)

- The CSV's score-less rows list the **away** team first with `@`; a filled row
  lists the **winner** first. Anything that edits the CSV must swap the teams
  *and* flip `@` together (`fill_csv_from_xlsx.py` does).
- `add_season.py` never updates an existing game; corrections need a delete
  first (§9b). The same is true one layer up in Supabase (§10, item 15).
- Sports-Reference can lag ESPN by a day or more and can be wrong (the 0–0).
  ESPN is only written once a game is final.
- `cmd` does not treat `::` as a comment after a command, and `sqlite3` is not
  installed on the Windows machine — use `python -c` one-liners (§9b).
- Windows is case-insensitive: renaming `Duke.png` to `duke.png` needs
  `git mv` or git will not record it (`rename_cfb_logos.py` uses it); Linux
  deploys are case-sensitive.
- Never trust a count written in a document — see §2.
- **Overtime and neutral flags are inputs to the ratings, not display extras**
  (§5f, §5g). Changing either moves ratings, so change them deliberately, then
  rebuild and snapshot-compare (§9d).
- **ESPN's flags are only as good as the era.** Its OT flag is unreliable before
  2001 (§5f) and has at least one false positive since; its neutral flag is
  empty before 2008 and follows the nominal host after (§5g). Sports-Reference's
  `N` means "not on the home team's campus", which is not the same thing.
- **A "neutral" game's home team is arbitrary** — alphabetical, not the host.
  Never flip a game to non-neutral by editing `games.neutral` alone; use
  `apply_neutral_overrides.py` (§5g).
- **`backfill_ot.py --apply` will undo hand corrections.** It writes ESPN's
  value wherever it differs from the DB. Re-apply `apply_ot_list.py` and clear
  the 2015 NC State–Wake Forest game afterwards (§9d).
- **A real football team never plays twice in three days.** Two phantom
  women's-basketball games and three time-zone echo duplicates were found with
  that one rule (§9e). Check it whenever the CSV is refreshed.
- **Sports-Reference lists some games twice, a day apart, when the venue is in
  another time zone** (the Sydney games and a 2021 bowl). The second row has a
  blank `Notes`.
- **`rebuild_ratings_only.py` runs the schema migration** (it connects through
  `db.connect`), so the first run after pulling a newer `db.py` adds any new
  `ratings` column.
- **A re-export without the delete silently keeps the old rows.** `games` is
  insert-only, so after the neutral audit the first push left every changed game
  as it was (Nov 16: the Apple Cup still read `neutral = 1`). Always run
  `delete from games where league = 'cfb';` first, then check a game whose flag
  changed (the Apple Cup, 2024-09-14, `team_id in ('washington',
  'washington-state')`) and the totals: rows and `sum(neutral)` per variant
  should equal the local `ratings` table.
- **Venue sources.** Old Sports-Reference box scores carry no venue
  (1996–2015 pages show a date, sometimes a time, nothing else). The results
  CSV's `Notes` column does give the venue city for postseason games in the
  files checked, and for most neutral regular-season games from about 2013 to
  2021 (blank for regular-season games from 2022 on). The column sits at
  index 9 in the 1996–2012 files and index 10 from 2013 on, because a `Time`
  column was added — `probe_old_venues.py` reads index 10 only, which is why it
  reported 0 notes for older seasons. ESPN's venue city (`espn_cache`) is usable
  from 2008; the 2001–2007 venue strings looked wrong in the probe's samples
  (the same Tempe stadium on unrelated games).
- **Never trust a single signal for a file refresh:** the Maryland–South
  Carolina game looked fine in every downstream table because the bad row was
  in the source CSV itself.

