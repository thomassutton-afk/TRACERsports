# TRACER Sports — Technical Handoff

*Consolidates `GITHUB_SYNC_HANDOFF.md` and `Tracer_Handoff.md`, both retired 2026-08-28 once the work they were tracking (the NFL merge into production, era-correct franchise names, color pipeline) fully shipped. This doc keeps the durable facts about the codebase — the time-bound "here's what's left to merge" status content is gone on purpose.*

*Note: this consolidation is based on what was directly verified during the 2026-08-28 session (repo diffs, live pipeline runs, Supabase queries). `Tracer_Handoff.md`'s fuller original narrative (the detailed NFL build history) wasn't fully visible during that session — only fragments seen through diffs — so if anything from that history is worth preserving beyond what's below, it should be added back explicitly rather than assumed lost.*

---

## Repo structure

- **`TRACERsports`** (private) — production. The live site reads from Supabase, which is fed by this repo's pipeline scripts.
- **`tracersports-app`** (public) — sandbox. Where new features get built and tested before merging to production.

As of 2026-08-28, these two repos are believed to be fully in sync — no active merge is pending. If sandbox diverges again for a future feature, the old sync approach is worth reviving: diff file-by-file, determine direction per file (don't assume "sandbox is ahead" — it's been wrong before), port real fixes deliberately rather than blind-copying whole files.

---

## Data pipeline behavior (durable facts)

- **`export_to_supabase.py` uses unqualified `ON CONFLICT DO NOTHING`** for the `games` upsert. New games insert fine on re-run, but **corrections to existing rows do not propagate**, and **newly-added columns never backfill on existing rows** through an ordinary re-export. Fix pattern for either case: a narrowly-scoped `DELETE FROM games WHERE ...` in Supabase's SQL Editor (for corrections) or a direct `UPDATE` (for backfills), then re-export or just let the fixed value stand.
- **Never re-run `schema.sql` wholesale** against a database that already has data — the `CREATE POLICY` statements have no `IF NOT EXISTS` guard and fail outright on a second run. Schema changes should always be handed over as the specific, minimal `ALTER TABLE`/`CREATE TABLE` snippet for just that change.
- **Supabase's direct hostname (`db.xxxx.supabase.co`) is IPv6-only** unless you're on the paid IPv4 add-on. If it stops resolving but the project looks healthy in the dashboard, switch to the session pooler host instead (`aws-0-<region>.pooler.supabase.com`, port `5432`, user `postgres.<project-ref>`).
- **`rebuild_ratings()` requires an explicit `variant` argument** (`"echo"` or `"pulse"`) for NBA, WNBA, and NFL — no default. Any script calling it needs to loop over both.
- **Compare local vs. Supabase vs. any exported file by date + matchup, never `game_id`** — SQLite reassigns `game_id`s on any `add_season.py`/rebuild run.

## Script path fragility (important operational pattern)

Several per-league pipeline scripts living in `DBs\{league}\` (`add_season.py`, `franchise.py`) use a bare relative database filename (e.g. `DB_PATH = "wnba_elo.db"`) that resolves relative to **your current working directory**, not the script's own location. The safe convention: always run these from `DBs\` itself, invoking the script via its subfolder path (`python wnba\franchise.py ...`) — never `cd` into the subfolder first. Doing so silently points the script at a different, usually stale or empty, copy of the database rather than erroring.

This has caused two confirmed real incidents:
- A stale WNBA subfolder db copy that cost real time to untangle before being deleted.
- An NFL color-pipeline run that silently operated on a near-empty stub database until traced down.

**Known unfixed rough edge:** `split_color_eras.py` and `seed_historical_colors.py` hardcode their target as `DBs\{league}_elo.db` directly via the script's own file location — they don't accept a `--db` argument the way `export_to_supabase.py` does. This means they will always target the top-level file only, regardless of working directory. If a league's real working database ever ends up needing to live in its subfolder again (as NFL's did before today), it must be manually copied up to the top level before running these two scripts. A future fix: add a `--db` flag to both, matching `export_to_supabase.py`'s pattern.

## Cross-league lessons

- **A shared function that parses a value as a number can silently break for a future league with a different value type.** NFL's round codes are text (`WC`/`DV`/`CC`/`SB`), not numbers — fixed via a `playoffRoundOrder` + rank-by-array-position pattern. Worth applying proactively to any new per-league logic that assumes numeric ordering.
- **A rule true for one league isn't safe to assume for a structurally similar one.** NBA and NFL both have divisions, but only NFL guarantees division winners a playoff seed — NBA dropped that exact rule in 2015-16. Needed an explicit `divisionWinnersAutoSeed` flag rather than tying the behavior to `hasDivisions`.
- **WCAG contrast ratio is symmetric** — `contrastRatio(A, B)` always equals `contrastRatio(B, A)`. Swapping which of two fixed colors is background vs. text never changes the readability number, only which one covers more area — a style call, not a fix.
- **Team codes are not a safe lookup key across leagues.** `MIA`, `ATL`, `CHI` and others repeat across NBA/WNBA/NFL. Any per-team override or config keyed by code alone risks one team's setting leaking onto an unrelated team in a different league — key by something actually unique (a full color trio works; league+code would too).
- **A pagination loop duplicated across many functions is a load-time problem, not just a code-smell.** `lib/gamesData.js` had the same sequential-`while`-loop pattern copy-pasted into 9 functions; the fix was one shared `fetchAllPages()` helper, not 9 individual optimizations.
- **`teams.team_name` can go stale relative to `team_history`** (the real source of truth for a team's current identity/code). Worth a periodic spot-check across all teams, especially after a rebuild.
- **Commissioner's Cup games with fractional `Round` values** (e.g. `0.1`) have had import reliability issues historically — both a missing-game case and a 2021 duplicate-row case, both since fixed. Worth re-scanning other seasons for the same pattern if a game count ever looks inflated or short.

---

## Current known state (as of 2026-08-28)

- NFL is fully live in production: registered in `registry.js`, wired through every page, colors and logos complete (all 32 teams), exported to Supabase.
- **Era-correct franchise display names ("Fix B")** are already built and working for all three leagues — `lib/historicalIdentity.js`'s `getDisplayIdentity()` is league-agnostic and reads straight from `team_history`, so it required no NFL-specific work once NFL's `team_history` era splits existed. Confirmed live (Chargers correctly show San Diego pre-2017, LA after).
- Round-format backfill and NFL tie backfill both confirmed clean/applied in Supabase.
- WNBA Supabase sync confirmed current (~27,860 rows across both variants).
- Stray database copies cleaned up: the WNBA (`DBs\wnba\wnba_elo.db`) and NFL (`DBs\nfl\nfl_elo.db`) subfolder copies were both confirmed stale and deleted.
- `migrate_add_ties.py` retired — folded into each league's `db.py` `_migrate()`.

## Pick up here next

- **Finish today's WNBA update sequence**: the Toronto Tempo rename never actually ran (it hit the `cd`-into-subfolder path issue above). Still needed:
  ```
  cd C:\Users\tjsut\TRACERsports\DBs
  python wnba\franchise.py rename --current-code TOR --name "Toronto Tempo"
  python export_to_supabase.py --league wnba --db wnba_elo.db
  cd ..
  git add .
  git commit -m "Add WNBA results, rename TOR"
  git push origin main
  ```
- **`--db` flag for `split_color_eras.py`/`seed_historical_colors.py`** — not urgent, but would close the last piece of script-path fragility described above.
