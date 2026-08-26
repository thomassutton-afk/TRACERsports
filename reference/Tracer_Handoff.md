# TRACER Sports — Handoff

## Purpose & context

TJ (GitHub: `thomassutton-afk`) is building **TRACER Sports** (tracersports.net), a multi-sport Elo power-ratings website. TJ is not a coder and builds everything through guided Claude sessions — he needs explicit, step-by-step terminal/UI instructions. He works from **Windows cmd.exe** (not PowerShell or bash).

**Two repos:**
- `tracersports-app` (`C:\Users\tjsut\tracersports-app`, branch `main`) — production Next.js/TypeScript site with Supabase backend, public on GitHub. This is where all daily work happens.
- `TracerProjects2` (`C:\Users\tjsut\TracerProjects2`, branch `master`) — dev/staging only, not connected to the live site. Not touched this session.

**NBA, WNBA, and NFL are all production-ready as of this session.** NFL went from "a separate, half-built `NFL_Elo\` folder with no variant support" to "fully integrated, live on the site, real bugs found and fixed" over the course of this session — this is the single largest piece of work in the project's history and the bulk of this handoff.

TJ's stated preferences, reconfirmed this session: confirm before writing code, launch sports one at a time, keep visual changes minimal — but push back constructively and precisely when something's actually wrong (see "How this session actually went," below). TJ also reviews delivered work carefully and catches real bugs by comparing against reference material (a real ESPN-style bracket screenshot caught a genuine seeding bug that automated checks had missed) — treat his bug reports as precise and worth fully investigating, not just plausible-sounding feedback to placate.

---

## NFL: what got built this session

### 1. Pipeline retrofit — Echo/Pulse variant support
`NFL_Elo\` predated the Echo/Pulse architecture entirely (no `variant` column, no `schedule_predictions`/`season_projections` tables, not registered in `export_to_supabase.py`). Retrofitted to match `DBs\nba\`/`DBs\wnba\`'s exact pattern:
- `db.py` — `variant` column added to `ratings`' primary key; new `schedule_predictions`/`season_projections` tables; `save_schedule_prediction`, `schedule_with_predictions`, `save_season_projection`, `clear_season_projection`, `load_season_projection`; a `_migrate()` function that auto-upgrades an existing pre-variant `.db` file in place (tested against TJ's real 8,029-game file — confirmed it upgrades cleanly with zero data loss).
- `rebuild.py` — `VARIANTS = ("echo", "pulse")`; `variant_params()` composes with NFL's existing per-season `param_schedule.json` tuning (Pulse = same season's tuned params, `alpha` forced to 0) rather than replacing that system.
- `add_season.py` — loops `for variant in VARIANTS`, same `=== echo ===` / `=== pulse ===` pattern as NBA/WNBA.
- `predict.py`, `simulate_season.py` — gained `--variant` flags.

**Real bugs found and fixed during this retrofit** (not just the planned work):
- `delete_season.py` (NFL, **and pre-existing in NBA and WNBA too**) called `rebuild_ratings(conn)` with no `variant` argument — would have crashed with `TypeError` if ever run. Fixed in all three leagues.
- `test_db.py`'s `fresh_conn()` never closed its sqlite connections — harmless on Linux, but crashes on Windows with a `PermissionError` during cleanup since Windows locks open files. Fixed.
- `rebuild.py`'s `build_current_engine()` crashed with an `IndexError` on a database with zero completed games (only worked with real history already present) — surfaced when TJ's first real run hit an accidentally-empty database. Fixed to fall back to the schedule table's season, then today's year, if no games exist yet.
- `db.py` was missing the `era_info`/`set_era_colors`/`primary_color`/`secondary_color`/`tertiary_color` infrastructure NBA/WNBA already have on `team_history`. This wasn't optional — `export_to_supabase.py` queries these columns unconditionally for every league, so NFL's export crashed without them. Added the same migration pattern (columns are nullable; actual color values are TJ's separate, ongoing work).

Files now live at `DBs\nfl\` (12 files, matching `DBs\nba\`/`DBs\wnba\` exactly), not the old `NFL_Elo\` folder. `nfl_elo.db` and `param_schedule.json` moved to `DBs\` (top level, alongside `nba_elo.db`/`wnba_elo.db` — same reasoning: `DB_PATH` is relative to wherever the command runs from). Confirmed via a real, non-dry-run `add_season.py` run against TJ's actual 8,029-game database: real 2025 standings check out, no errors.

**Deliberately not carried over**: 15 one-off tuning/dev scripts (`nfl_tune_engine.py`, `build_nfl_db.py`, `retune_season.py`, etc.) and their scratch data — none of the 12 core pipeline scripts reference them, confirmed by grep. `NFL_Elo\` has nothing left worth keeping once the file moves above are done.

### 2. Frontend wiring
- `lib/sports/nfl/config.js` — all 32 teams, cross-checked byte-for-byte against the real database's registered codes. Team codes are the pipeline's **permanent** franchise identities (`OAK`/`SD`/`STL` for the current Las Vegas Raiders/LA Chargers/LA Rams — same convention as NBA's `CHH`), while `name`/`city` fields show the current identity. Conferences/divisions reflect the current alignment only (not era-correct historically — that's a separate, not-yet-built concern, same status as NBA's "Fix B").
- `lib/sports/registry.js` — NFL added to `LEAGUES` and a new `football` entry in `SPORTS`. TJ explicitly confirmed he wanted this live now, overriding the file's own "don't add future leagues until ready to ship" comment.
- `DBs/export_to_supabase.py` — `nfl` → `"football"` in `SPORT_FOR_LEAGUE`; real `ACTIVE_CODES` set. Real bug found and fixed: `format_round()` assumed every round value was a stringified float (NBA/WNBA's `"1.0"` → `"1"` pattern) and crashed on NFL's real text round codes (`WC`/`DV`/`CC`/`SB`) — now passes non-numeric round values through unchanged.

Verified with a real (non-dummy) production `npm run build` — compiles, type-checks, generates every route clean, including with NFL live in the registry.

### 3. Playoff bracket — built from scratch, several real bugs found via TJ's own comparison against a reference bracket
NFL's format is structurally different from both existing brackets: 7 seeds per conference (not NBA's 8-with-play-in or WNBA's top-8-overall), a bye for the #1 seed, and single-elimination games (not best-of-series). Built as a new `NflBracketTab.jsx` rather than adapting `BracketTab.jsx`.

Per TJ's decision, the #1 seed's bye has **no placeholder card** — their card just appears normally as one side of their real Divisional-round game, first time they show up.

**Real bugs found and fixed, most caught by TJ comparing the live output against a real reference bracket screenshot:**
- **Seeding was structurally wrong.** Original approach flat-sorted all 16 conference teams by win% and cut at 7 — but NFL seeding guarantees the 4 division winners seeds 1–4 regardless of overall record, then the best 3 non-winners fill 5–7. This let a team that never actually made the playoffs (Detroit) get seeded ahead of the real division winner (Carolina). Rewrote to use the real games as ground truth for *who* made it, with proper division-winner-first ordering for the *number*.
- **A tied #1 seed picked the wrong team.** Denver and New England were both 14-3; a plain sort arbitrarily gave New England the top seed. Fixed by using ground truth directly: whichever team never plays a Wild Card game **is** the #1 seed, by definition — no tiebreak needed or wanted.
- **Wildcard seeds were swapped for two real ties.** Buffalo/Houston and SF/LA Rams were each genuinely tied 12-5, and a plain sort landed on the wrong order for both, confirmed by comparing directly against TJ's reference bracket. Fixed by deriving wildcard seed numbers from the real Wild Card pairing structure itself (2-seed always plays 7, 3-seed plays 6, 4-seed plays 5) rather than trying to independently re-rank tied teams.
- **A division-winner tie was "correct" by luck, not logic.** Chicago and Philadelphia were both 11-6; the plain sort happened to land on the right order, but for no real reason — confirmed this by tracing the actual code path. This is what motivated the tiebreaker consolidation (see below).
- **Bracket didn't fit/render the same as NBA's.** Two separate bugs: (a) a data-fetching condition in `page.js` still checked for the old `"conference-bracket"` type string after the render logic had moved to a new `"conference-bracket-bye"` type, so `poGames` never loaded for NFL and every card rendered as an empty placeholder shell; (b) Divisional-round cards were clustered with a small fixed gap instead of spreading across the full column height the way NBA's Round 2 cards do; (c) the champion banner and the Super Bowl score card were both trying to occupy the same centered vertical space and visually overlapped — fixed by moving the score card below the Conference Championship row (matching NBA's actual layout) instead of centering it.
- **Logos and text labels showed stale codes** for the three relocated franchises (`OAK`/`SD`/`STL` showing instead of `LV`/`LAC`/`LAR`). Fixed via a new shared `lib/logoFilenameOverrides.js` (`logoFileName()` for image paths, `displayAbbr()` for text labels) — used by `TeamMark.jsx` (site-wide) and the bracket. Deliberately **not** applied to `HistoricalTeamMark.jsx`, which is supposed to show era-correct old codes.

### 4. Season/All-Time/Team pages — "stopped working" after NFL went live
Real root cause: several functions in `lib/gamesData.js` (`tallyPlayoffResults`, `getSeasonMaxRounds`, `resolveWinsNeeded`) and in `all-time/page.js` (`buildDepthFilters`) all did `Number(round)` to determine playoff depth. That's fine for NBA/WNBA's numeric round strings (`"1"`–`"4"`), but NFL's real round codes are text (`WC`/`DV`/`CC`/`SB`) — `Number("WC")` is `NaN`, so champion detection, round-reached badges, and the All-Time depth filters all silently broke for NFL specifically.

Fixed with a proper generalization, not a patch: added an explicit `playoffRoundOrder` array to every league's config (`['1','2','3','4']` for NBA, `['1','2','3']` for WNBA, `['WC','DV','CC','SB']` for NFL — lives inside each config's `engine` block, alongside `roundLabels`) and a shared `roundRank()` helper that uses array position instead of parsing the value as a number. Verified NBA's behavior — including Play-In handling — is byte-for-byte unchanged; verified NFL's now correctly shows Seattle as 2025 champion.

### 5. Standings — ties column, and a real tiebreaker gap
NFL games can end in a tie (34 real instances in TJ's actual data, going back to 1997). Added proper support across the full chain — this genuinely needed all three layers, not just the frontend:
- `schema.sql` / Supabase — new `t` column on `games` (added via `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`, **not** by re-running the whole `schema.sql`, which fails on already-existing `CREATE POLICY` statements that lack `IF NOT EXISTS` guards).
- `export_to_supabase.py` — now selects/writes `t`.
- `StandingsTab.jsx` — tie-aware win% formula (a tie counts as half a win, not zero games), a conditional Ties column, dynamic `colSpan`.
- **One-time production fix needed and applied**: `games` upserts via unqualified `ON CONFLICT DO NOTHING`, so every game row already exported before the `t` column existed stayed permanently stuck at the column's default (`0`) — future exports alone couldn't fix already-existing rows. Backfilled with `UPDATE games SET t = 1 WHERE result = 0.5 AND league = 'nfl';`, confirmed safe by checking `result = 0.5` is an exact, zero-exception stand-in for `t = 1` across all of TJ's real data.

**Bigger finding: real tiebreaker formulas didn't exist for NFL anywhere, and there were three separate, inconsistent seeding implementations across the site.** Looked up the actual current official NFL tiebreaker procedure directly from nfl.com (not from memory) and implemented it in `DBs/tiebreakers.py` (common games, strength of victory, strength of schedule, combined points-scored/allowed ranking — the works; deliberately not implementing "net touchdowns," since this pipeline has no touchdown-count data anywhere to compute it from). Verified against every real tied group in TJ's actual 2025 season, including a genuine 5-way tie — all resolve completely.

Then consolidated: `StandingsTab.jsx` had its **own separate, hand-maintained JS reimplementation** of this same logic that silently fell through to **NBA's** criteria for any league that wasn't explicitly WNBA — meaning NFL ties on the Standings page were being resolved with NBA's rules the whole time. Extracted a single shared `lib/tiebreakers.js` (ported from the now-correct Python), fixed the NBA-fallback bug, and pointed both `StandingsTab.jsx` and `NflBracketTab.jsx`'s division-winner-tier seeding at this one real implementation. Verified the exact Chicago/Philadelphia tie that was previously "correct by luck" now resolves for the real reason (real head-to-head: Chicago beat Philadelphia).

**Also added `seedConference()`** — the Standings page's "Automatic Playoff Berths" section was ranking straight by win%/tiebreaker with no awareness that NFL division winners get guaranteed seeds 1–4 regardless of record. Checked first whether this was safe to generalize: **NBA actually eliminated this exact rule in 2015-16** (division winners get zero automatic seeding now, only a tiebreaker preference within an already-tied group), so this had to be gated behind an explicit `divisionWinnersAutoSeed` config flag (true only for NFL) rather than tied to `hasDivisions` generally, which NBA also has. Confirmed NBA's behavior is completely unchanged.

---

## WNBA: Commissioner's Cup Championship games added (new session)

Added the WNBA Commissioner's Cup Championship game for each season 2021–2026 (one extra game per season, real box scores, previously missing from the database entirely). Followed the same convention NBA already uses for its Cup Championship game: `type='P', round=0.1`, with a `0.1: 1.02` entry added to WNBA's `playoff_mult` in `engine.py` (baseline params — WNBA has no tuned `active_params.json` yet, so this baseline value is what's actually live). Added `'0.1': "Commissioner's Cup"` to `roundLabels` in `lib/sports/wnba/config.js`. Confirmed via the real engine code that `type='P'` with `round < 1` is already excluded from official win-loss tallying and from playoff-round-max detection (`getSeasonMaxRounds()` filters `n >= 1`) — the same protection NBA's own Cup/Play-In rounds already rely on — so this needed zero changes to standings or bracket logic.

**Real bug found and fixed along the way: 2021's playoff games existed twice in the database** — once correctly (`type='P'`, real round), and once as long-standing stale rows (`type='R'`, `round=NULL`) that had been there since a much earlier build. Re-running `add_season.py` on the corrected 2021 results file didn't recognize the new `'P'`-typed rows as duplicates of the old `'R'`-typed ones (the dedup key includes both `type` and `round`), so both copies coexisted — inflating every 2021 team's game count and win-loss record. Fixed with a targeted `DELETE` (stale `'R'`/`NULL` rows with a matching `'P'`-typed counterpart on the same date/matchup), followed by `rebuild.py`. **This wasn't caused by anything in this session — it was a pre-existing data problem that only surfaced because the newly-corrected file's proper typing no longer matched the old wrong typing.** Worth checking other seasons for the same pattern if anything ever looks like an inflated game count again.

**Costly mistake this session, now corrected: Claude told TJ to `cd` into `DBs\wnba\` before running `add_season.py`/`rebuild.py`/diagnostic scripts.** This directly violates the existing "run from `DBs\`, always" rule (see Operations Guide §Rules of thumb) — and running from the subfolder meant a chunk of this session's diagnostic work initially landed on a small, irrelevant stray file at `DBs\wnba\wnba_elo.db` rather than the real `DBs\wnba_elo.db`. No real data was lost (the stray file was never the source of truth), but it cost significant time to untangle. **Multiple stray copies of `wnba_elo.db` currently exist** (repo root — empty, no `games` table; `DBs\wnba\` — small/stale) alongside the real one at `DBs\wnba_elo.db`. Recommend deleting the stray copies once confirmed nothing depends on them, specifically to prevent this exact confusion from recurring.

**Also found and fixed: a small (sub-1-point) Elo precision drift between the database's continuous Echo chain and TJ's reference spreadsheet, first visible at the 2023→2024 season boundary.** Traced to the season-transition regression-to-mean step, not to anything 2024-specific — end-of-2023 ratings already differed by ~0.01 points between the two systems (invisible at 2-decimal display, but compounding through 2024's games until visible). **Root cause confirmed: the issue was in TJ's reference Excel files, not in the database or the Python engine.** No engine/pipeline changes were needed — TJ fixed it on the spreadsheet side and confirmed everything now matches exactly. Worth remembering if a similar small discrepancy ever shows up again at a season boundary: check the Excel reference file itself before assuming the pipeline regressed.

---

## How this session actually went (worth internalizing for next time)

This was not a smooth one-pass build — it involved a long chain of real bugs, several only found because TJ personally compared the live output against ground truth (a real reference bracket screenshot, his own knowledge of a real 2025 tie) rather than accepting "looks plausible" results. Two patterns worth carrying forward:

1. **A component that looks structurally correct (right layout, right columns, right colors) can still be feeding the wrong data underneath it.** The bracket rendered a clean, professional-looking shell multiple times in a row while the actual seed numbers or game data behind it were wrong — visual polish is not evidence of correctness.
2. **"It happens to show the right answer" is not the same as "it's computing the right answer."** The Chicago/Philadelphia tie displayed correctly for an entire session before anyone realized it was arbitrary sort-order luck, not real tiebreaker logic — this only came up because TJ asked "is the bracket right because of the tiebreaker or because you just matched it to the real bracket," a genuinely important distinction that's worth asking proactively next time similar ground-truth-matching tricks are used as a shortcut.

---

## Open items / where to pick up next

**New from this session:**
1. **Delete the stray `wnba_elo.db` copies** (repo root, `DBs\wnba\`) once confirmed nothing depends on them.
2. **NFL colors and logos** — TJ has this in progress separately. `lib/sports/nfl/config.js`'s current hex values are real official colors used as placeholders; safe to overwrite whenever that work lands. Logo image files need to exist at `/logos/nfl/{code}.png` using **current** abbreviations for the three relocated franchises (`LV.png`/`LAC.png`/`LAR.png`, not `OAK`/`SD`/`STL`) — `lib/logoFilenameOverrides.js` already expects this.
3. **Era-correct NFL team identity** (the equivalent of NBA/WNBA's "Fix B") — not built. `lib/sports/nfl/config.js` only reflects current conferences/divisions/names; historical games would show today's alignment, not what was true at the time.
4. **The 15 leftover one-off scripts in `NFL_Elo\`** — never triaged individually beyond confirming none of them are load-bearing for the 12 core files now in `DBs\nfl\`. `NFL_Elo\` itself is safe to delete once TJ's confirmed the moved files are all working.
5. **Confirm the tie backfill SQL and the `t` column addition were both actually run** — flagged and given to TJ, not independently re-confirmed in a follow-up session.

**Carried forward, still open (unchanged by this session):**
- WNBA live playoff series tracking still not built (config gap closed in an earlier session; tracking logic itself still isn't).
- `reference/old-site/` still has stray "continelo" references — archived, doesn't affect the live site.

---

## Key learnings & principles (carried forward + new this session)

- **When a shared function's behavior depends on parsing a value as a number, a future league with fundamentally different (but equally valid) value types can silently break it.** NFL's real round codes are text, not numbers — several places across the codebase assumed `Number(round)` was meaningful, and every one of them broke silently (no crash, just wrong/missing output) until traced individually. The fix (`playoffRoundOrder` + rank-by-array-position) generalizes correctly for both numeric and text round schemes with zero behavior change for the leagues that already worked.
- **Ground truth beats a computed tiebreaker, when it's available — but a computed tiebreaker is required when ground truth isn't (e.g., a season still in progress).** The bracket's bye-seed and wildcard-seed logic deliberately use the real recorded games as ground truth rather than trying to replicate the real-world tiebreaker rule that produced them — this is more reliable, not a shortcut, *for a completed season*. The Standings page can't use this trick (a season without playoff games yet has no "real games" to derive ground truth from), which is exactly why it needs the real, general-purpose `seedConference()`/`rankTeams()` logic instead.
- **A rule that's true for one league in a sport-comparison isn't safe to assume for a structurally similar league.** NFL's "division winners get guaranteed seeds" needed to be explicitly opt-in per league (not tied to `hasDivisions`) specifically because NBA — which also has divisions — dropped this exact rule in 2015-16. Confirmed via a real search rather than assumed from a general "sports have divisions, divisions matter" intuition.
- **`schema.sql` is not safe to re-run wholesale once a database already has data in it**, even though every `CREATE TABLE`/`CREATE INDEX` in it uses `IF NOT EXISTS` — `CREATE POLICY` statements in the same file don't have an equivalent guard, so a second run fails outright. Schema changes should always be handed to TJ as the specific, minimal `ALTER TABLE`/`CREATE TABLE` snippet for just that change, never as "run schema.sql."
- **`ON CONFLICT DO NOTHING` (already an established pattern in this project for performance) means a newly-added column will never backfill itself on existing rows through ordinary re-exports.** Any future column addition to `games` needs either a one-time backfill computed from data already in the table (what happened here, since `result = 0.5` was an exact proxy for the missing `t` values) or an explicit plan for rows where no such proxy exists.
- **Colocate a new config field with the data it's paired with, not just anywhere convenient.** `playoffRoundOrder` was initially added as a sibling of `engine.roundLabels` (correct) but referenced from consumer code as if it were top-level on the league config (wrong) — a real, self-inflicted bug caught immediately by testing against real data before shipping, not by code review alone.

## Approach & patterns (unchanged, reconfirmed this session)
- Claude writes files locally → TJ downloads → copies to correct folders → runs the app/build to verify → commits and pushes. Claude cannot push to GitHub, run a live dev server, or connect to Supabase directly from its sandbox.
- **Every fix this session was verified against a real, extracted copy of TJ's actual production data** (not synthetic/invented test cases) before being handed off — real 2025 standings, real tied groups, real playoff games, a real production `npm run build`. This caught several bugs (the stale-fixture false alarm on Pittsburgh's seed, the Windows-only test cleanup crash, the empty-database `IndexError`) that would not have been caught by code review or a clean compile alone.
- Claude can clone TJ's actual GitHub repo directly to inspect real current state rather than relying on prior handoff claims or TJ's own description — used repeatedly and effectively this session.
- Windows cmd.exe throughout — no PowerShell/bash syntax in instructions to TJ.
