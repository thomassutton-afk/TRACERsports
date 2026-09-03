"use client";

/**
 * NflBracketTab — 7-seeds-per-conference bracket with a #1 seed bye
 * (leagueConfig.playoffFormat.type === 'conference-bracket-bye').
 *
 * Structurally different from BracketTab.jsx (NBA) in two ways:
 *   1. No play-in — playoffFormat.playInSeeds is always 0 for this format.
 *   2. NFL playoff games are single-elimination (winner-take-all), not a
 *      best-of-N series — so unlike BracketTab's buildBracket() (which
 *      tallies wins across multiple games to find a series winner), each
 *      round here is exactly one game per matchup. buildMatches() below
 *      is the simpler equivalent: one row per (round, team-pair).
 *
 * The #1 seed's bye is handled by simply never drawing a Wild Card game
 * for them — their card first appears normally as one side of their real
 * Divisional-round game, the same as every other team's card appears in
 * whatever round they first play in. No placeholder/BYE card, no special
 * Round 1 slot reserved for them (per-project decision — see HANDOFF).
 *
 * LIVE, not projected: unlike OverallBracketTab.jsx (WNBA), this reads
 * actual completed playoff games (poGames), not standings alone. A round
 * that hasn't been played yet simply doesn't render a matchup for it —
 * no fabricated "who'd win" guess.
 */

import { useState } from "react";
import TeamMark from "./TeamMark";
import { displayAbbr } from "../../lib/logoFilenameOverrides";
import { rankTeams, buildContext } from "../../lib/tiebreakers";
import tiebreakerOverrides from "../../lib/sports/tiebreakerOverrides.json";
import { getFillColor, getTextColor } from "../../lib/teamColors";

const mono = "var(--font-mono)";
const serif = "var(--font-display)";
const C = {
  acc: "var(--acc)",
  ut: "var(--ut)",
  text: "var(--text)",
  text2: "var(--text2)",
  text3: "var(--text3)",
};

// One row per (round, team-pair) — NFL playoff games are single-elimination,
// so unlike BracketTab.jsx's series win-tallying, a "match" here is complete
// as soon as its one game has a result. round comes back from Supabase as
// TEXT ('WC'/'DV'/'CC'/'SB'), compared as plain strings — no float-parsing
// needed the way BracketTab.jsx needs for NBA/WNBA's numeric rounds.
function buildMatches(poGames) {
  const map = {};
  for (const g of poGames) {
    const pair = [g.team_id, g.opponent_id].sort().join("_");
    const key = `${g.round}_${pair}`;
    if (!map[key]) {
      const [a, b] = [g.team_id, g.opponent_id].sort();
      map[key] = { round: g.round, t1: a, t2: b, scores: {}, ratings: {}, winner: null, date: g.date };
    }
    const m = map[key];
    m.scores[g.team_id] = g.points_for;
    m.ratings[g.team_id] = g.post_gm_rate;
    if (g.result === 1) m.winner = g.team_id;
  }
  return Object.values(map);
}

export default function NflBracketTab({ poGames, standings, games = [], leagueConfig, season, variant }) {
  const teams = leagueConfig.teams;
  const tc = (abbr) => (teams[abbr] ? getFillColor(teams[abbr]) : null) || "#663399";
  const ts = (abbr) => (teams[abbr] ? getTextColor(teams[abbr]) : null) || tc(abbr);
  const tn = (abbr) => teams[abbr]?.name || abbr;
  const roundLabels = leagueConfig.engine?.roundLabels || {};
  const seasonLabel = leagueConfig.seasonLabel ? leagueConfig.seasonLabel(season) : season;

  const conferences = leagueConfig.conferences || [];
  const [confA, confB] = conferences; // e.g. ['AFC', 'NFC']

  const matches = buildMatches(poGames);
  const isConf = (confName) => (m) => teams[m.t1]?.conf === confName && teams[m.t2]?.conf === confName;

  // Real tiebreaker context, shared with StandingsTab.jsx (lib/tiebreakers.js)
  // rather than a plain win%/wins sort — used below for both picking each
  // division's winner and ordering the non-bye winners into seeds 2-4.
  // Wildcard order (seeds 5-7) and the #1 seed still come from ground
  // truth (the real games), which is even more reliable than a computed
  // tiebreaker — see the comments at those two spots below for why.
  const ctx = buildContext(standings, games, leagueConfig, season, variant, tiebreakerOverrides);

  // Seed NUMBERS (the "#" badge) follow real NFL rules: the 4 division
  // winners get seeds 1-4 (ranked among themselves by real tiebreaker
  // criteria), then the best 3 remaining teams get seeds 5-7 as
  // wildcards — this is NOT the same as "top 7 teams by win%" (a
  // division winner can have a worse overall record than a non-division-
  // winner and still outrank them).
  //
  // Who actually MADE the playoffs, though, is read from the real games
  // themselves (poGames) rather than re-derived from win/loss alone —
  // trying to independently recompute the field risked seeding a team
  // that didn't actually make it (exactly what happened before this
  // fix: naive win%-sort put Detroit in over Carolina, who's the real
  // division winner in this data). Using real participants as ground
  // truth for WHO, and rankTeams (real criteria) only for the ORDER
  // among them, can't produce that failure mode.
  function computeSeeds(confName) {
    const confTeams = standings.filter((t) => teams[t.team_id]?.conf === confName);
    const realParticipants = new Set();
    const wcParticipants = new Set();
    for (const m of matches) {
      if (!isConf(confName)(m)) continue;
      if (["WC", "DV", "CC", "SB"].includes(m.round)) { realParticipants.add(m.t1); realParticipants.add(m.t2); }
      if (m.round === "WC") { wcParticipants.add(m.t1); wcParticipants.add(m.t2); }
    }
    const played = confTeams.filter((t) => realParticipants.has(t.team_id));
    // The real bye team is ground truth, not a tiebreak guess: only the
    // true #1 seed skips Wild Card weekend, so whichever real
    // participant never appears in a WC game for this conference IS
    // seed 1 — this matters when two division winners are tied on
    // record (e.g. both 14-3), since even the real tiebreaker criteria
    // are worth double-checking against ground truth where it exists.
    const byeTeam = played.find((t) => !wcParticipants.has(t.team_id));

    const byDiv = {};
    for (const t of played) {
      const div = teams[t.team_id]?.div;
      (byDiv[div] ||= []).push(t);
    }
    // Division winner = whichever team ranks first among the OTHER real
    // playoff teams sharing that division, per rankTeams' real criteria
    // (not a plain sort — two teams within a division can themselves be
    // tied, same failure mode as the winners-vs-winners tie below).
    const winners = Object.values(byDiv).map((list) => {
      const ranked = rankTeams(list.map((t) => t.team_id), ctx);
      return list.find((t) => t.team_id === ranked[0]);
    });
    const winnerIds = new Set(winners.map((w) => w.team_id));
    const wildcards = played.filter((t) => !winnerIds.has(t.team_id));

    // Seeds 2-4 among the non-bye winners: real tiebreaker criteria, not
    // a plain sort — this is the exact spot that silently mis-seeded
    // Chicago/Philadelphia (both real 11-6 ties) before this fix. It
    // happened to still display the right order by luck (arbitrary sort
    // stability), which is exactly why ground truth alone wasn't enough
    // here the way it was for the bye and wildcard tiers below.
    const restOfWinnerIds = rankTeams(
      winners.filter((w) => w.team_id !== byeTeam?.team_id).map((w) => w.team_id),
      ctx
    );
    const restOfWinners = restOfWinnerIds.map((id) => winners.find((w) => w.team_id === id));
    const orderedWinners = byeTeam ? [byeTeam, ...restOfWinners] : restOfWinners;

    // Wildcard ORDER (which of the 3 gets seed 5 vs 6 vs 7) comes from
    // the real Wild Card pairing, not a plain record sort — two
    // wildcards tied on record (e.g. both 12-5) have no real tiebreak
    // available from win/loss alone, and guessing produced exactly this
    // failure mode before: Buffalo/Houston and SF/LA Rams were each a
    // real 12-5 tie, and a plain sort put them in the wrong order
    // relative to the real bracket. NFL Wild Card pairings are fixed
    // (2-seed plays 7, 3-seed plays 6, 4-seed plays 5), and the real
    // games in poGames already show who actually played whom — so a
    // wildcard's seed is fully determined by which already-known
    // winner (seeds 2-4) it played, no independent ranking needed.
    const seedForWinnerRank = { 2: 7, 3: 6, 4: 5 };
    const wcMatchesForConf = matches.filter((m) => m.round === "WC" && isConf(confName)(m));
    const orderedWildcards = [];
    restOfWinners.forEach((winner, i) => {
      const winnerRank = i + 2; // restOfWinners[0] is seed 2, etc.
      const wcGame = wcMatchesForConf.find((m) => m.t1 === winner.team_id || m.t2 === winner.team_id);
      const oppId = wcGame ? (wcGame.t1 === winner.team_id ? wcGame.t2 : wcGame.t1) : null;
      const opp = wildcards.find((w) => w.team_id === oppId);
      if (opp) orderedWildcards[seedForWinnerRank[winnerRank] - 5] = opp;
    });
    // Any wildcard whose real WC game wasn't found (shouldn't happen in
    // practice) falls back to record order rather than being dropped.
    const placed = new Set(orderedWildcards.filter(Boolean).map((w) => w.team_id));
    const leftoverIds = rankTeams(wildcards.filter((w) => !placed.has(w.team_id)).map((w) => w.team_id), ctx);
    const leftover = leftoverIds.map((id) => wildcards.find((w) => w.team_id === id));
    const finalWildcards = [0, 1, 2].map((i) => orderedWildcards[i] ?? leftover.shift());

    return orderedWinners.concat(finalWildcards.filter(Boolean)).slice(0, 7);
  }

  const seedMap = {};
  computeSeeds(confA).forEach((t, i) => { seedMap[t.team_id] = i + 1; });
  computeSeeds(confB).forEach((t, i) => { seedMap[t.team_id] = i + 1; });

  const minSeed = (m) => Math.min(seedMap[m.t1] ?? 99, seedMap[m.t2] ?? 99);
  const byRound = (rnd, pred) => matches.filter((m) => m.round === rnd && pred(m)).sort((x, y) => minSeed(x) - minSeed(y));

  const aWC = byRound("WC", isConf(confA));
  const aDV = byRound("DV", isConf(confA));
  const aCC = byRound("CC", isConf(confA));
  const bWC = byRound("WC", isConf(confB));
  const bDV = byRound("DV", isConf(confB));
  const bCC = byRound("CC", isConf(confB));
  const sb = matches.find((m) => m.round === "SB");
  const champion = sb?.winner || null;

  // ── Geometry ────────────────────────────────────────────────────────────
  // Same card dimensions as BracketTab.jsx/OverallBracketTab.jsx, for a
  // consistent look across every league's bracket. Wild Card has 3 games
  // (not the 4-pairs-of-2 shape NBA's Round 1 has), so the grouping/gap
  // pattern here is simpler: just 3 stacked cards, evenly gapped.
  const CARD_H = 76;
  const CARD_GAP = 10;
  const WC_H = CARD_H * 3 + CARD_GAP * 2;

  // Divisional cards spread across the FULL Wild Card column height,
  // matching how NBA's Round 2 cards fill their column edge-to-edge
  // rather than clustering — first card top-aligned, second bottom-
  // aligned, matching the same "fill available height" convention
  // BracketTab.jsx uses (see its r2Top formula), even though NFL's
  // bye means there isn't a clean "2 WC games merge into 1 DV game"
  // pairing to center against the way NBA's R1->R2 has.
  const dvTop = (i) => (aDV.length > 1 ? i * (WC_H - CARD_H) : (WC_H - CARD_H) / 2);

  const ccTop = (WC_H - CARD_H) / 2;

  // The Super Bowl card sits BELOW the Conference Championship row,
  // not vertically centered in the whole bracket the way ccTop is —
  // matching NBA's actual finals-card placement (BracketTab.jsx's
  // `cfBottomEdge + 20`, i.e. below Conf Finals, not centered in
  // Round 1's full height). Centering it instead (this component's
  // original approach) left the champion banner and the score card
  // competing for the same vertical space near the middle, which is
  // exactly why they visibly overlapped — this frees the whole upper
  // portion of the column for the banner instead.
  const sbTop = ccTop + CARD_H + 20;
  const BRACKET_H = WC_H;

  const CW = { wc: 152, dv: 152, cc: 152, sb: 202 };

  function TeamRow({ abbr, score, isWin, seed, showSeed }) {
    if (!abbr) return <div style={{ height: CARD_H / 2 }} />;
    const color = tc(abbr);
    const sec = ts(abbr);
    return (
      <div
        style={{
          height: CARD_H / 2, display: "flex", alignItems: "center", overflow: "hidden",
          background: isWin ? `${color}cc` : `${color}55`, paddingRight: 6, gap: 4,
        }}
      >
        {showSeed && (
          <div style={{ width: 16, textAlign: "center", fontFamily: mono, fontSize: 11, color: isWin ? sec : "rgba(0,0,0,0.4)", flexShrink: 0, fontWeight: 600 }}>
            {seed ?? ""}
          </div>
        )}
        <div style={{ width: 26, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
          <TeamMark team={teams[abbr]} teamId={abbr} league={leagueConfig.id} size={18} />
        </div>
        <div
          style={{
            fontFamily: mono, fontSize: 9, fontWeight: 700, padding: "1px 4px", borderRadius: 3,
            flexShrink: 0, minWidth: 28, textAlign: "center",
            border: `1.5px solid ${isWin ? sec : "rgba(0,0,0,0.2)"}`, color: isWin ? sec : "rgba(0,0,0,0.5)",
            background: "transparent", letterSpacing: 0.3,
          }}
        >
          {displayAbbr(abbr)}
        </div>
        <div style={{ flex: 1 }} />
        {score != null && (
          <div style={{ fontFamily: mono, fontSize: 13, fontWeight: 900, color: isWin ? sec : "rgba(0,0,0,0.45)" }}>
            {score}
          </div>
        )}
      </div>
    );
  }

  function MatchCard({ m, w = 152 }) {
    if (!m) {
      return <div style={{ width: w, background: "rgba(255,255,255,0.4)", border: "1px dashed rgba(0,0,0,0.15)", borderRadius: 8, height: CARD_H }} />;
    }
    let { t1, t2 } = m;
    const s1 = seedMap[t1] ?? 99, s2 = seedMap[t2] ?? 99;
    if (s2 < s1) [t1, t2] = [t2, t1];
    const isComplete = !!m.winner;
    const winnerColor = isComplete ? tc(m.winner) : null;
    return (
      <div style={{ width: w, borderRadius: 8, overflow: "hidden", border: isComplete ? `1px solid ${winnerColor}50` : "1px solid rgba(0,0,0,0.12)", boxShadow: isComplete ? `0 2px 12px ${winnerColor}20` : "0 1px 3px rgba(0,0,0,0.08)" }}>
        <TeamRow abbr={t1} score={m.scores[t1]} isWin={m.winner === t1} seed={seedMap[t1]} showSeed />
        <div style={{ height: 1, background: isComplete ? `${winnerColor}30` : "rgba(0,0,0,0.08)" }} />
        <TeamRow abbr={t2} score={m.scores[t2]} isWin={m.winner === t2} seed={seedMap[t2]} showSeed />
      </div>
    );
  }

  function ColHeader({ label, w }) {
    return (
      <div style={{ width: w, flexShrink: 0, fontFamily: mono, fontSize: 9, fontWeight: 700, color: "rgba(0,0,0,0.45)", textTransform: "uppercase", letterSpacing: 1.6, paddingBottom: 8, borderBottom: "1px solid rgba(0,0,0,0.15)", marginBottom: 12, textAlign: "center" }}>
        {label}
      </div>
    );
  }

  function ConfBracket({ wc, dv, cc, confColor, confName, mirror }) {
    const cols = [
      <div key="wc" style={{ width: CW.wc, flexShrink: 0, height: BRACKET_H, position: "relative" }}>
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, display: "flex", flexDirection: "column", gap: CARD_GAP }}>
          {[0, 1, 2].map((i) => <MatchCard key={i} m={wc[i] || null} w={CW.wc} />)}
        </div>
      </div>,
      <div key="dv" style={{ width: CW.dv, flexShrink: 0, height: BRACKET_H, position: "relative" }}>
        {[0, 1].map((i) => (
          <div key={i} style={{ position: "absolute", top: dvTop(i), left: 0, right: 0 }}>
            <MatchCard m={dv[i] || null} w={CW.dv} />
          </div>
        ))}
      </div>,
      <div key="cc" style={{ width: CW.cc, flexShrink: 0, height: BRACKET_H, position: "relative" }}>
        <div style={{ position: "absolute", top: ccTop, left: 0, right: 0 }}>
          <MatchCard m={cc[0] || null} w={CW.cc} />
        </div>
      </div>,
    ];
    return (
      <div>
        <div style={{ display: "flex", alignItems: "center", gap: 10, height: 30, flexDirection: mirror ? "row-reverse" : "row" }}>
          <div style={{ width: 3, height: 16, borderRadius: 2, background: confColor, flexShrink: 0 }} />
          <span style={{ fontFamily: mono, fontSize: 11, fontWeight: 700, color: confColor, textTransform: "uppercase", letterSpacing: 2 }}>
            {confName} Conference
          </span>
          <div style={{ flex: 1, height: 1, background: `${confColor}30` }} />
        </div>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 6 }}>
          {mirror ? [...cols].reverse() : cols}
        </div>
      </div>
    );
  }

  // ── Mobile round-by-round view ────────────────────────────────────────
  // Same rationale as BracketTab.jsx: a multi-column bracket doesn't
  // shrink well, so mobile gets a round selector + stacked matchup cards
  // instead of scrolling the desktop diagram sideways. NFL games are
  // single-elimination (one score each, no series win-count), so this
  // reads from m.scores/m.winner directly rather than BracketTab's
  // series w1/w2 tally.
  function MobileTeamRow({ abbr, score, isWin, seed }) {
    if (!abbr) {
      return (
        <div className="mobile-matchup-row">
          <span className="mobile-matchup-seed">—</span>
          <span className="mobile-matchup-name" style={{ color: C.text3 }}>TBD</span>
        </div>
      );
    }
    const color = tc(abbr);
    return (
      <div className="mobile-matchup-row" style={{ background: isWin ? `${color}12` : "transparent" }}>
        <span className="mobile-matchup-seed">{seed ?? "—"}</span>
        <TeamMark team={teams[abbr]} teamId={abbr} league={leagueConfig.id} size={22} />
        <span className="mobile-matchup-name" style={{ fontWeight: isWin ? 700 : 500 }}>{tn(abbr)}</span>
        <span className="mobile-matchup-score">{score ?? "—"}</span>
      </div>
    );
  }

  function MobileMatchCard({ m }) {
    if (!m) return <div className="mobile-bracket-tbd">TBD</div>;
    return (
      <div className="mobile-matchup-card">
        <MobileTeamRow abbr={m.t1} score={m.scores[m.t1]} isWin={m.winner === m.t1} seed={seedMap[m.t1]} />
        <div className="mobile-matchup-divider" />
        <MobileTeamRow abbr={m.t2} score={m.scores[m.t2]} isWin={m.winner === m.t2} seed={seedMap[m.t2]} />
      </div>
    );
  }

  function MobileBracketRounds() {
    const rounds = [
      { id: "wc", label: roundLabels.WC || "Wild Card", groups: [{ name: confA, list: aWC }, { name: confB, list: bWC }] },
      { id: "dv", label: roundLabels.DV || "Divisional", groups: [{ name: confA, list: aDV }, { name: confB, list: bDV }] },
      { id: "cc", label: roundLabels.CC || "Conf Champ", groups: [{ name: confA, list: aCC }, { name: confB, list: bCC }] },
      { id: "sb", label: roundLabels.SB || "Super Bowl", groups: [{ name: `${leagueConfig.label} Championship`, list: sb ? [sb] : [] }] },
    ];
    const defaultId = sb ? "sb" : aCC.length || bCC.length ? "cc" : aDV.length || bDV.length ? "dv" : "wc";
    const [round, setRound] = useState(defaultId);
    const active = rounds.find((r) => r.id === round) || rounds[0];

    return (
      <>
        <div className="mobile-bracket-round-tabs">
          {rounds.map((r) => (
            <button key={r.id} className={`mobile-bracket-round-btn${round === r.id ? " active" : ""}`} onClick={() => setRound(r.id)}>
              {r.label}
            </button>
          ))}
        </div>
        {active.groups.map((g) => (
          <div key={g.name}>
            <div className="mobile-bracket-group-label">{g.name}</div>
            {g.list.length === 0 ? <div className="mobile-bracket-tbd">TBD</div> : g.list.map((m, i) => <MobileMatchCard key={i} m={m} />)}
          </div>
        ))}
        {round === "sb" && champion && (
          <div className="mobile-bracket-champion">
            <TeamMark team={teams[champion]} teamId={champion} league={leagueConfig.id} size={48} />
            <div style={{ fontFamily: mono, fontSize: 10, fontWeight: 700, color: C.ut, textTransform: "uppercase", letterSpacing: 2 }}>
              {seasonLabel} {leagueConfig.label} Champion
            </div>
            <div style={{ fontFamily: serif, fontSize: 20, fontWeight: 900, color: C.text }}>{tn(champion)}</div>
          </div>
        )}
      </>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12, flexWrap: "wrap" }}>
        <span style={{ fontFamily: mono, fontSize: 9, color: C.text3 }}>Seeds reflect RS standings (win%) · #1 seed has a Wild Card bye</span>
      </div>

      <div className="bracket-scroll desktop-only">
      <div style={{ background: "#DDD5C4", borderRadius: 14, padding: "16px 14px 20px", boxShadow: "0 4px 24px rgba(0,0,0,0.10), inset 0 1px 0 rgba(255,255,255,0.4)", border: "1px solid #C8BFB1", position: "relative", overflow: "hidden", width: "fit-content", margin: "0 auto" }}>
        <div style={{ position: "absolute", top: 0, left: "50%", transform: "translateX(-50%)", width: "80%", height: "40%", borderRadius: "50%", background: "radial-gradient(ellipse, rgba(255,255,255,0.04) 0%, transparent 70%)", pointerEvents: "none" }} />

        <div style={{ display: "flex", gap: 6, marginBottom: 0 }}>
          <ColHeader label={roundLabels.WC || "Wild Card"} w={CW.wc} />
          <ColHeader label={roundLabels.DV || "Divisional"} w={CW.dv} />
          <ColHeader label={roundLabels.CC || "Conf. Championship"} w={CW.cc} />
          <ColHeader label={roundLabels.SB || "Super Bowl"} w={CW.sb} />
          <ColHeader label={roundLabels.CC || "Conf. Championship"} w={CW.cc} />
          <ColHeader label={roundLabels.DV || "Divisional"} w={CW.dv} />
          <ColHeader label={roundLabels.WC || "Wild Card"} w={CW.wc} />
        </div>

        <div style={{ display: "flex", gap: 6, alignItems: "flex-start", position: "relative" }}>
          <ConfBracket wc={aWC} dv={aDV} cc={aCC} confColor="rgba(191,45,45,0.9)" confName={confA} mirror={false} />

          <div style={{ flexShrink: 0, width: CW.sb, alignSelf: "stretch", position: "relative", minHeight: Math.max(BRACKET_H, sbTop + CARD_H) }}>
            {champion && (
              <div style={{ position: "absolute", top: 0, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-start", gap: 8 }}>
                <TeamMark team={teams[champion]} teamId={champion} league={leagueConfig.id} size={64} />
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontFamily: mono, fontSize: 9, fontWeight: 700, color: C.ut, textTransform: "uppercase", letterSpacing: 2, marginBottom: 4 }}>
                    {seasonLabel} {leagueConfig.label} Champion
                  </div>
                  <div style={{ fontFamily: serif, fontSize: 20, fontWeight: 900, color: C.text, lineHeight: 1.1 }}>
                    {tn(champion)}
                  </div>
                </div>
              </div>
            )}
            <div style={{ position: "absolute", top: sbTop, left: 0, right: 0 }}>
              <MatchCard m={sb || null} w={CW.sb} />
            </div>
          </div>

          <ConfBracket wc={bWC} dv={bDV} cc={bCC} confColor="rgba(45,80,191,0.9)" confName={confB} mirror={true} />
        </div>

        <div style={{ display: "flex", gap: 20, marginTop: 28, fontFamily: mono, fontSize: 9, color: "rgba(0,0,0,0.35)", flexWrap: "wrap" }}>
          <span># = Conference seed (RS standings)</span>
        </div>
      </div>
      </div>

      <div className="mobile-only" style={{ flexDirection: "column" }}>
        <MobileBracketRounds />
      </div>
    </div>
  );
}
