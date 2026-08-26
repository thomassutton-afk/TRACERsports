# TRACER Sports — GitHub Sync Handoff

*Last updated: 2026-08-26*

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

### ✅ Done — color/bracket infrastructure (was Phase 1)
`lib/teamColors.js`'s dark-color detection + `getTextColor()` helper is ported to main, and both `BracketTab.jsx`/`OverallBracketTab.jsx` are wired to use it.

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
| `lib/gamesData.js` | Missing per-league min-score threshold + generalized round-ranking (`playoffRoundOrder`) logic |
| `app/[league]/page.js`, `season/page.js`, `all-time/page.js`, `team/page.js` | Still NBA/WNBA-only logic |
| `app/[league]/NflBracketTab.jsx` | Already exists in main, nearly identical to sandbox — just needs the same `getFillColor()`/`getTextColor()` swap the other two bracket tabs already got |
| `app/about/page.js` | Content not updated for NFL |
| `schema.sql` | Missing the `t` (ties) column — now a real blocker, since NFL actually populates ties (NBA/WNBA never do). Needs the `ALTER TABLE` + a backfill for any already-exported NFL rows once NFL export begins (see gotcha above) |

Watch for interaction with the color-infra port above — some of these files may touch the same color-function calls.

## Data quality watch-items

- **`teams.team_name` can go stale** relative to `team_history` (the actual source of truth for a team's current identity/code). Worth a spot-check across all teams if this hasn't been done recently, especially after any rebuild.
- **Commissioner's Cup games with fractional `Round` values** (e.g. `0.1`) have had import reliability issues before (both a missing-game case and a 2021 duplicate-row case, both since fixed) — worth scanning other seasons for the same pattern if an inflated or missing game count ever shows up again.

## General lessons

- **Always verify blob content directly (via Git's blob API) rather than trusting `raw.githubusercontent.com`** — that CDN can lag behind a fresh push.
- **Both `[team]` and `[league]` bracket-notation paths in URLs need percent-encoding** (`%5B`/`%5D`) when hitting GitHub's Contents API directly — plain brackets return 404s.
- **`rebuild_ratings()` requires an explicit `variant` argument** (`"echo"` or `"pulse"`) in NBA, WNBA, and now NFL — no default. Any script calling it needs to loop over both.
- When comparing local vs. Supabase vs. any exported reference file, the safest check is always by **date + matchup**, not `game_id` — SQLite reassigns `game_id`s on any `delete_season`/`add_season` rebuild.
- **A shared function that parses a value as a number can silently break for a future league with a different value type.** NFL's round codes are text (`WC`/`DV`/`CC`/`SB`), not numbers — several places assumed `Number(round)` was meaningful. Fixed via `playoffRoundOrder` + rank-by-array-position, which generalizes with zero behavior change for leagues that already worked.
- **A rule true for one league isn't safe to assume for a structurally similar one.** NFL's "division winners get guaranteed seeds" needed an explicit `divisionWinnersAutoSeed` flag rather than being tied to `hasDivisions`, since NBA (which also has divisions) dropped that exact rule in 2015-16.
