# TRACER Sports — GitHub Sync Handoff

*Last updated: 2026-08-27*

## The two repos

- **`TRACERsports`** — the production/live repo. Deployed site reads from here (indirectly, via Supabase).
- **`tracersports-app`** — the sandbox/testing repo. Where new features (NFL, CFB) get built out before they're ready for production.

NFL is now **production-ready in sandbox** (full pipeline retrofit, frontend wiring, playoff bracket, real tiebreaker logic — see `Tracer_Handoff.md` for the full build narrative). The active work is merging it into main to bring it online on the live site — see "Status" below.

**Why they diverge:** sandbox is where active feature work happens, so it regularly gets ahead of main. But sandbox doesn't always stay in sync with bug fixes that land in main first, and vice versa. Periodic compatibility checks (comparing file-by-file across both repos) are how we catch drift in either direction.

## The general sync workflow

1. Pull the full file tree from both repos, diff shared (non-NFL) files.
2. For each difference, determine **direction**: is one repo ahead with a real fix the other needs, or is the difference just expected NFL-only code that hasn't shipped to main yet?
3. Port real fixes in whichever direction is correct — usually sandbox → main for bug fixes discovered while building NFL, but sometimes main → sandbox.
4. Never blindly copy a whole file without checking direction first — a couple of "sandbox is ahead" assumptions turned out to be backwards (e.g. sandbox's team colors were actually wrong, main's were correct).

## Data pipeline gotcha: `ON CONFLICT DO NOTHING`

Local SQLite (`*_elo.db`) → `export_to_supabase.py` → Supabase Postgres → live site reads from Supabase. The `games` upsert uses an unqualified `ON CONFLICT DO NOTHING`:

- New games insert fine on a normal re-run.
- **Corrections to existing games do NOT propagate.** If a game's score is fixed locally, re-running the export silently skips that row since it already "exists" in Supabase by its natural key.
- **Fix pattern:** `DELETE FROM games WHERE league=... AND season=...` (scoped as narrowly as safe) in Supabase's SQL Editor, then re-run the export so it inserts clean. Used successfully for the WNBA games mismatch fixed 2026-08-26.
- **Also bites newly-added columns** — a new column never backfills itself on existing rows through ordinary re-exports. NFL's `t` (ties) column needed a one-time backfill once added: `UPDATE games SET t = 1 WHERE result = 0.5 AND league = 'nfl';` (see `Tracer_Handoff.md` for how that proxy was confirmed safe). The same pattern will apply once `t` lands in main's `schema.sql`.
- Worth considering changing this to a real upsert (`ON CONFLICT ... DO UPDATE`) so re-exports self-heal. Not yet done.

**Supabase connection note:** the direct hostname (`db.xxxx.supabase.co`) is IPv6-only unless you're on Supabase's paid IPv4 add-on. If it stops resolving (DNS failure, but the project is otherwise healthy in the dashboard), switch `.env` to the **session pooler** host instead (`aws-0-<region>.pooler.supabase.com`, port `5432`, user becomes `postgres.<project-ref>`).

**`schema.sql` is not safe to re-run wholesale** once a database has data in it — `CREATE POLICY` statements have no `IF NOT EXISTS` guard, so a second run fails outright. Schema changes should be handed over as the specific, minimal `ALTER TABLE`/`CREATE TABLE` snippet, never as "run schema.sql."

## Status as of 2026-08-26

### ⚠️ Needs re-check — color/bracket infrastructure (was Phase 1, marked done 2026-08-26)
`lib/teamColors.js`'s dark-color detection + `getTextColor()` helper was ported to main on 2026-08-26 — but sandbox's version of this file has since been substantially rewritten (2026-08-27, see "Site polish pass" below) and is no longer just the dark-color/`getTextColor()` logic that was ported. Treat this file as needing a fresh port, not confirmed in sync. `BracketTab.jsx`/`OverallBracketTab.jsx` are still correctly wired to call `getTextColor()`/`getFillColor()` either way — it's the logic *inside* those two functions that's now out of date in main.

### ✅ Done — `update_wnba_results.py` (was Phase 2)
Adopted in main. Pulls final scores from ESPN's scoreboard API with built-in mirror-row validation.

### 🔲 Small leftover from the WNBA Commissioner's Cup work
`lib/sports/wnba/config.js` in main is still missing `'0.1': "Commissioner's Cup"` in `roundLabels` (sandbox has it). One-line port.

### 🔲 NFL merge into main (was Phase 3 — active work now)
NFL is fully built and production-ready in sandbox. Current file-by-file status for bringing it into main:

| File | Status in main |
|---|---|
| `lib/sports/registry.js` | Not registered yet |
| `lib/sports/nfl/config.js` | File exists in main but isn't imported/wired by registry.js yet |
| `DBs/team_divisions.py` | Missing NFL conference/division mapping |
| `lib/gamesData.js` | Missing per-league min-score threshold + generalized round-ranking (`playoffRoundOrder`) logic. **Also now missing the parallel-pagination rewrite** — sandbox's version replaced 9 duplicated sequential-pagination loops with one shared `fetchAllPages()` helper (2026-08-27, see below); this is a real load-time improvement independent of NFL, worth porting on its own merit even before the NFL-specific gap is closed |
| `app/[league]/page.js`, `season/page.js`, `all-time/page.js`, `team/page.js` | Still NBA/WNBA-only logic |
| `app/[league]/NflBracketTab.jsx` | Already exists in main, nearly identical to sandbox — just needs the same `getFillColor()`/`getTextColor()` swap the other two bracket tabs already got |
| `app/about/page.js` | Content not updated for NFL |
| `schema.sql` | Missing the `t` (ties) column — now a real blocker, since NFL actually populates ties (NBA/WNBA never do). Needs the `ALTER TABLE` + a backfill for any already-exported NFL rows once NFL export begins (see gotcha above) |

Watch for interaction with the color-infra port above — some of these files may touch the same color-function calls.

## Data quality watch-items

- **`teams.team_name` can go stale** relative to `team_history` (the actual source of truth for a team's current identity/code). Worth a spot-check across all teams if this hasn't been done recently, especially after any rebuild.
- **Commissioner's Cup games with fractional `Round` values** (e.g. `0.1`) have had import reliability issues before (both a missing-game case and a 2021 duplicate-row case, both since fixed) — worth scanning other seasons for the same pattern if an inflated or missing game count ever shows up again.

## Site polish pass (sandbox, 2026-08-27 — pre-main-merge cleanup)

TJ wanted a set of sandbox fixes done before the NFL merge into main, so this landed as a separate pass on top of the NFL work above. All of it is in `tracersports-app` only — none of it has been ported to main yet.

- **`NFL_Elo/` deleted** — the old pre-retrofit folder (27 files, including the 15 leftover one-off tuning/dev scripts flagged as "not yet triaged" in `Tracer_Handoff.md`) is gone. Confirmed via repo-wide grep that nothing outside the folder referenced any of them before deleting.
- **Homepage NFL bug fixed** — `app/page.tsx` hardcoded a single `CURRENT_SEASON = 2026` applied to every league, so NFL's homepage card showed 0 teams (NFL's 2026 season doesn't start until September, so there's no `season=2026` data yet). Now uses the same `getCurrentSeason(league)` helper `app/[league]/page.js` already used, resolved per-league instead of once globally.
- **Teams grid** — removed the redundant 3-letter code shown under each team's name (`app/[league]/team/page.js`).
- **About page accuracy tracker** — added an NFL row alongside NBA/WNBA (`fetchLeagueAccuracy`/`buildSeasonAccuracy` were already league-agnostic, so this was just wiring). Left "Combined" as NBA+WNBA only, not +NFL — pooling a structurally different sport's game-level accuracy into one number wasn't an obvious call, so it's flagged in a code comment rather than decided silently.
- **"AI-explanation" text removed** — 5 spots where a subtitle just re-explained the page heading or a term the toggle button already labeled (homepage tagline, the repeated "Echo ratings — carry-forward variant" subtitle on 4 different pages, the Teams grid subtitle, the About page subtitle).
- **Nav redesigned** — the NBA/WNBA/NFL button row is now a single dropdown (`<select>` with `<optgroup>` per sport, reading straight from the `SPORTS` registry, so a new sport added later shows up automatically with zero nav changes). Switching leagues also now preserves which page type you're on (Dashboard/Season/All-Time/Team) instead of always resetting to Dashboard — the one exception is an individual team page, which falls back to the new league's team list since a specific team ID rarely means anything across leagues.
- **`lib/teamColors.js` rewritten** — `getTextColor()` used to just return `secondary` (or `primary` for black-primary teams) with zero contrast checking. Audited all 82 NBA/WNBA/NFL teams against real WCAG contrast math: 48 of 82 were below 4.5:1, 29 of those below 3:1 (genuinely unreadable, e.g. Dolphins teal-on-orange at 1.19:1). New logic: try each team's own colors in brand-preference order against the real fill color (target is 3.0, not 4.5 — see rationale in the file's comments, it's a deliberate call given team-name text runs 9-13px, under WCAG's large-text bold cutoff); if none pass, try a **capped** same-hue lightness tint (max 20 points — an uncapped tint can drift a color into looking like a different color entirely, e.g. a light-pushed red reads as pink) on each candidate; only then fall through to flat white/black. A small hardcoded `MANUAL_OVERRIDES` table (keyed by each team's exact color trio, not team code — codes like `MIA`/`ATL`/`CHI` repeat across leagues) handles ~9 teams where TJ wanted a specific stylistic result over the algorithm's pick (Grizzlies and Sky now flip to their navy color as the *background* with gold text, for example). Two of those overrides are explicitly flagged in-code for review: Titans (red text, ratio 3.11 — barely over the floor) and Falcons (black text, ratio 2.78 — the one team on the site currently *below* the 3.0 floor, kept by deliberate choice).
- **`lib/gamesData.js` pagination parallelized** — 9 different functions each awaited Supabase's paginated results one page at a time in a sequential `while` loop (a 30-season league's All-Time query needs ~150 pages at 1000 rows/page, so that was ~150 sequential round-trips before the page could render). Replaced with one shared `fetchAllPages()` helper that fetches page 1 with an exact row count, then fires every remaining page in parallel — wait time drops from "sum of every page" to "roughly the slowest single page." Benefits All-Time most, but also Season, Team pages, and the About page's accuracy tracker.



- **Always verify blob content directly (via Git's blob API) rather than trusting `raw.githubusercontent.com`** — that CDN can lag behind a fresh push.
- **Both `[team]` and `[league]` bracket-notation paths in URLs need percent-encoding** (`%5B`/`%5D`) when hitting GitHub's Contents API directly — plain brackets return 404s.
- **`rebuild_ratings()` requires an explicit `variant` argument** (`"echo"` or `"pulse"`) in NBA, WNBA, and now NFL — no default. Any script calling it needs to loop over both.
- When comparing local vs. Supabase vs. any exported reference file, the safest check is always by **date + matchup**, not `game_id` — SQLite reassigns `game_id`s on any `delete_season`/`add_season` rebuild.
- **A shared function that parses a value as a number can silently break for a future league with a different value type.** NFL's round codes are text (`WC`/`DV`/`CC`/`SB`), not numbers — several places assumed `Number(round)` was meaningful. Fixed via `playoffRoundOrder` + rank-by-array-position, which generalizes with zero behavior change for leagues that already worked.
- **A rule true for one league isn't safe to assume for a structurally similar one.** NFL's "division winners get guaranteed seeds" needed an explicit `divisionWinnersAutoSeed` flag rather than being tied to `hasDivisions`, since NBA (which also has divisions) dropped that exact rule in 2015-16.
- **WCAG contrast ratio is symmetric** — `contrastRatio(A, B)` always equals `contrastRatio(B, A)`. Swapping which of two fixed colors is the background vs. the text never changes the readability number; it only changes which one covers more area, which is a pure style call, not a fix.
- **Team codes are not a safe lookup key across leagues.** `MIA` is both the NBA Heat and the NFL Dolphins; `ATL`, `CHI`, and others repeat too. Any per-team override or config keyed by code alone risks one team's setting leaking onto an unrelated team in a different league — key by something actually unique (a full color trio worked for the `teamColors.js` override table; league+code would also work).
- **A pagination loop duplicated across many functions is a load-time problem, not just a code-smell.** `lib/gamesData.js` had the identical sequential-`while`-loop pattern copy-pasted into 9 different functions; the fix was one shared helper, not 9 individual optimizations.
