"use client";

/**
 * OverallBracketTab — top-N-overall bracket (no conference split, no
 * play-in). Built for WNBA's format (playoffFormat.type === 'overall-bracket')
 * but league-agnostic so any future league with the same shape can reuse it.
 *
 * SEEDING: ranked with the same real tiebreaker code the Standings tab uses
 * (lib/tiebreakers.js rankTeams -> WNBA procedure: head-to-head first), NOT
 * a plain win% sort. Records are rebuilt from REGULAR-SEASON rows only
 * (the `games` prop, type='R'), because page.js's `standings` w/l sums every
 * row for the season — including playoff games once they exist — which
 * would shuffle the seeds mid-playoffs.
 *
 * LIVE SERIES: real type='P' rows (poGames, round 1/2/3; round 0.1 is the
 * Commissioner's Cup and is ignored) are tallied into series scores.
 * Winners advance automatically; slots whose feeder series isn't decided
 * stay TBD. With zero playoff games this renders as the old projected
 * Round-1 view.
 *
 * Series length per round comes from wnba/config.js playoffFormat.winsNeeded
 * ({1:2, 2:3, 3:4}); the Finals length is era-resolved via winsNeededByEra.
 * Structure assumes the current top-8 / 3-round format (2022+).
 */

import { useState } from "react";
import TeamMark from "./TeamMark";
import { getFillColor, getTextColor } from "@/lib/teamColors";
import { rankTeams, buildContext } from "@/lib/tiebreakers";
import tiebreakerOverrides from "@/lib/sports/tiebreakerOverrides.json";

const mono = "var(--font-mono)";
const serif = "var(--font-display)";
const C = {
  acc: "var(--acc)",
  ut: "var(--ut)",
  text: "var(--text)",
  text2: "var(--text2)",
  text3: "var(--text3)",
};

// Standard 8-team bracket pairing: 1v8 and 4v5 feed the top semifinal
// slot, 2v7 and 3v6 feed the bottom one.
const R1_PAIRS = [[1, 8], [4, 5], [2, 7], [3, 6]];

const hasTeam = (s, id) => s.t1 === id || s.t2 === id;

// Round comes back from Supabase as TEXT ("1" or "1.0"), so always parseFloat.
function roundNum(round) {
  return round == null ? null : parseFloat(round);
}

// Rolls playoff game rows (one mirror row per team per game) into series
// with win counts. Only the winner's mirror row has result === 1.
function buildSeries(poGames, winsFor) {
  const map = {};
  for (const g of poGames) {
    const rNum = roundNum(g.round);
    if (![1, 2, 3].includes(rNum)) continue; // skips Commissioner's Cup (0.1) etc.
    const [a, b] = [g.team_id, g.opponent_id].sort();
    const key = `${rNum}_${a}_${b}`;
    const s = (map[key] ??= { round: rNum, t1: a, t2: b, wins: { [a]: 0, [b]: 0 }, gameIds: new Set() });
    if (g.game_id != null) s.gameIds.add(g.game_id);
    if (Number(g.result) === 1) s.wins[g.team_id] = (s.wins[g.team_id] || 0) + 1;
  }
  return Object.values(map).map((s) => {
    const need = winsFor(s.round);
    const w1 = s.wins[s.t1] || 0, w2 = s.wins[s.t2] || 0;
    const winner = w1 >= need ? s.t1 : w2 >= need ? s.t2 : null;
    return { round: s.round, t1: s.t1, t2: s.t2, w1, w2, winner };
  });
}

export default function OverallBracketTab({ poGames = [], standings, games = [], leagueConfig, season, variant }) {
  const teams = leagueConfig.teams;
  const autoSeeds = leagueConfig.playoffFormat?.autoSeeds ?? 8;
  const roundLabels = leagueConfig.engine?.roundLabels || {};
  const r1Label = roundLabels["1"] || "Round 1";
  const r2Label = roundLabels["2"] || "Semifinals";
  const r3Label = roundLabels["3"] || `${leagueConfig.label} Finals`;
  const seasonLabel = leagueConfig.seasonLabel ? leagueConfig.seasonLabel(season) : season;

  // ── Seeding: regular-season-only records + real tiebreakers ─────────────
  const rsByTeam = {};
  for (const g of games) {
    const r = (rsByTeam[g.team_id] ??= { team_id: g.team_id, w: 0, l: 0, t: 0 });
    r.w += g.w ?? 0;
    r.l += g.l ?? 0;
    r.t += g.t ?? 0;
  }
  // Fall back to `standings` only if the RS rows haven't loaded / carry no w/l.
  const rsStandings = Object.values(rsByTeam).some((t) => t.w + t.l > 0) ? Object.values(rsByTeam) : standings;
  const ctx = buildContext(rsStandings, games, leagueConfig, season, variant, tiebreakerOverrides);
  const ranked = rankTeams(rsStandings.map((t) => t.team_id), ctx).slice(0, autoSeeds);
  const teamBySeed = {};
  const seedOf = {};
  ranked.forEach((id, i) => { teamBySeed[i + 1] = id; seedOf[id] = i + 1; });

  // ── Live series ──────────────────────────────────────────────────────────
  const winsNeeded = leagueConfig.playoffFormat?.winsNeeded || {};
  const eras = leagueConfig.playoffFormat?.winsNeededByEra;
  const era = eras?.find((e) => season >= e.fromSeason && (e.toSeason == null || season <= e.toSeason));
  const winsFor = (round) => (round === 3 && era?.winsNeeded != null ? era.winsNeeded : winsNeeded[round] ?? (round === 1 ? 2 : round === 2 ? 3 : 4));

  const seriesList = buildSeries(poGames, winsFor);
  const started = seriesList.length > 0;

  // Finds the real series for a slot (or builds a TBD/placeholder one), then
  // orients it so the better seed is on top. Returns a card model:
  //   { a, b, wa, wb, winner }
  function slot(round, ta, tb) {
    const list = seriesList.filter((s) => s.round === round);
    let found = null;
    if (ta && tb) found = list.find((s) => hasTeam(s, ta) && hasTeam(s, tb));
    else if (ta || tb) found = list.find((s) => hasTeam(s, ta || tb));
    let m;
    if (found) m = { a: found.t1, b: found.t2, wa: found.w1, wb: found.w2, winner: found.winner };
    else m = { a: ta || null, b: tb || null, wa: 0, wb: 0, winner: null };
    if (m.a && m.b && (seedOf[m.b] ?? 99) < (seedOf[m.a] ?? 99)) {
      m = { a: m.b, b: m.a, wa: m.wb, wb: m.wa, winner: m.winner };
    }
    return m;
  }

  const r1 = R1_PAIRS.map(([sa, sb]) => slot(1, teamBySeed[sa], teamBySeed[sb]));
  const r2 = [slot(2, r1[0].winner, r1[1].winner), slot(2, r1[2].winner, r1[3].winner)];
  const r3 = slot(3, r2[0].winner, r2[1].winner);
  const champion = r3.winner;

  const roundDone = (r, expected) => {
    const l = seriesList.filter((s) => s.round === r);
    return l.length >= expected && l.every((s) => s.winner);
  };
  const activeRound = !roundDone(1, 4) ? 1 : !roundDone(2, 2) ? 2 : 3;

  const [mobileRound, setMobileRound] = useState(null);
  const mobileActive = mobileRound || (["r1", "r2", "r3"][activeRound - 1]);

  // ── Layout (same card dimensions as BracketTab.jsx) ─────────────────────
  const CARD_H = 76;
  const CARD_GAP = 5;
  const PAIR_GAP = 14;

  const PAIR_H = CARD_H * 2 + CARD_GAP;
  const r2Top = (i) => i * (PAIR_H + PAIR_GAP) + (PAIR_H - CARD_H) / 2;
  const r2BotTop = r2Top(1);
  const BRACKET_H = r2BotTop + CARD_H;
  const r3Top = (r2Top(0) + CARD_H / 2 + r2BotTop + CARD_H / 2) / 2 - CARD_H / 2;

  const CW = { r1: 152, r2: 152, r3: 202, champion: 202 };

  const tc = (id) => (teams[id] ? getFillColor(teams[id]) : null) || "#663399";
  const ts = (id) => (teams[id] ? getTextColor(teams[id]) : null) || "#663399";
  const tn = (id) => teams[id]?.name || id;

  function SeriesRow({ id, wins, isWinner, dim, showScore }) {
    const rowH = CARD_H / 2;
    if (!id) {
      return (
        <div style={{ height: rowH, display: "flex", alignItems: "center", padding: "0 10px", borderLeft: "3px solid transparent" }}>
          <span style={{ fontFamily: mono, fontSize: 11, color: "rgba(0,0,0,0.3)" }}>TBD</span>
        </div>
      );
    }
    const color = tc(id);
    const sec = ts(id);
    return (
      <div
        style={{
          height: rowH, display: "flex", alignItems: "center", overflow: "hidden",
          background: `${color}cc`, borderLeft: isWinner ? `3px solid ${color}` : "3px solid transparent",
          paddingRight: 6, opacity: dim ? 0.55 : 1,
        }}
      >
        <div style={{ width: 26, textAlign: "center", fontFamily: mono, fontSize: 13, color: sec, flexShrink: 0, fontWeight: isWinner ? 700 : 600 }}>
          {seedOf[id] ?? "—"}
        </div>
        <div style={{ width: 30, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginRight: 3 }}>
          <TeamMark team={teams[id]} teamId={id} league={leagueConfig.id} size={20} />
        </div>
        <div
          style={{
            fontFamily: mono, fontSize: 9, fontWeight: 700,
            padding: "1px 4px", borderRadius: 3, flexShrink: 0, minWidth: 32, textAlign: "center",
            border: `1.5px solid ${sec}`, color: sec, background: "transparent",
            marginRight: 5, letterSpacing: 0.3,
          }}
        >
          {id}
        </div>
        <div style={{ flex: 1 }} />
        {showScore && (
          <div
            style={{
              fontFamily: mono, fontSize: 20, fontWeight: 900, flexShrink: 0, minWidth: 18, textAlign: "center",
              lineHeight: 1, color: sec, textShadow: isWinner ? `0 0 10px ${color}60` : "none", marginRight: 6,
            }}
          >
            {wins}
          </div>
        )}
      </div>
    );
  }

  function SeriesCard({ m, w }) {
    if (!m.a && !m.b) {
      return (
        <div style={{ width: w, background: "rgba(255,255,255,0.4)", border: "1px dashed rgba(0,0,0,0.15)", borderRadius: 8, overflow: "hidden", height: CARD_H }} />
      );
    }
    const complete = !!m.winner;
    const active = !complete && (m.wa > 0 || m.wb > 0);
    const winnerColor = complete ? tc(m.winner) : null;
    const showScore = started && !!m.a && !!m.b;
    return (
      <div
        style={{
          width: w, borderRadius: 8, overflow: "hidden",
          border: active ? `1.5px solid ${C.acc}80` : complete ? `1px solid ${winnerColor}50` : "1px solid rgba(0,0,0,0.12)",
          boxShadow: active ? `0 2px 16px ${C.acc}20` : complete ? `0 2px 12px ${winnerColor}20` : "0 1px 3px rgba(0,0,0,0.08)",
        }}
      >
        <SeriesRow id={m.a} wins={m.wa} isWinner={m.winner === m.a} dim={complete && m.winner !== m.a} showScore={showScore} />
        <div style={{ height: 1, background: complete ? `${winnerColor}30` : "rgba(0,0,0,0.08)" }} />
        <SeriesRow id={m.b} wins={m.wb} isWinner={m.winner === m.b} dim={complete && m.winner !== m.b} showScore={showScore} />
      </div>
    );
  }

  function ColHeader({ label, w, isActive }) {
    return (
      <div
        style={{
          width: w, flexShrink: 0, fontFamily: mono, fontSize: 9, fontWeight: isActive ? 900 : 700,
          color: isActive ? "#D4AF37" : "rgba(0,0,0,0.45)", textTransform: "uppercase", letterSpacing: 1.6,
          paddingBottom: 8, borderBottom: isActive ? "2px solid #D4AF37" : "1px solid rgba(0,0,0,0.15)",
          marginBottom: 12, textAlign: "center",
          textShadow: isActive ? "0 0 10px #D4AF3790" : "none",
        }}
      >
        {label}
      </div>
    );
  }

  // ── Mobile view (round tabs, same pattern as BracketTab/NflBracketTab) ──
  function MobileRow({ id, wins, isWinner, showScore }) {
    if (!id) {
      return (
        <div className="mobile-matchup-row">
          <span className="mobile-matchup-seed">—</span>
          <span className="mobile-matchup-name" style={{ color: C.text3 }}>TBD</span>
        </div>
      );
    }
    return (
      <div className="mobile-matchup-row" style={{ background: isWinner ? `${tc(id)}12` : "transparent" }}>
        <span className="mobile-matchup-seed">{seedOf[id] ?? "—"}</span>
        <TeamMark team={teams[id]} teamId={id} league={leagueConfig.id} size={22} />
        <span className="mobile-matchup-name" style={{ fontWeight: isWinner ? 700 : 500 }}>{tn(id)}</span>
        {showScore && <span className="mobile-matchup-score">{wins ?? 0}</span>}
      </div>
    );
  }

  function MobileCard({ m }) {
    if (!m.a && !m.b) return <div className="mobile-bracket-tbd">TBD</div>;
    const showScore = started && !!m.a && !!m.b;
    return (
      <div className="mobile-matchup-card">
        <MobileRow id={m.a} wins={m.wa} isWinner={m.winner === m.a} showScore={showScore} />
        <div className="mobile-matchup-divider" />
        <MobileRow id={m.b} wins={m.wb} isWinner={m.winner === m.b} showScore={showScore} />
      </div>
    );
  }

  const mobileRounds = [
    { id: "r1", label: r1Label, series: r1 },
    { id: "r2", label: r2Label, series: r2 },
    { id: "r3", label: r3Label, series: [r3] },
  ];
  const mobileCur = mobileRounds.find((r) => r.id === mobileActive) || mobileRounds[0];

  return (
    <div>
      <div className="bracket-scroll desktop-only">
        <div
          style={{
            background: "#DDD5C4", borderRadius: 14, padding: "16px 14px 20px",
            boxShadow: "0 4px 24px rgba(0,0,0,0.10), inset 0 1px 0 rgba(255,255,255,0.4)",
            border: "1px solid #C8BFB1", position: "relative", overflow: "hidden", width: "fit-content", margin: "0 auto",
          }}
        >
          <div style={{ display: "flex", gap: 6, marginBottom: 0 }}>
            <ColHeader label={r1Label} w={CW.r1} isActive={activeRound === 1} />
            <ColHeader label={r2Label} w={CW.r2} isActive={activeRound === 2} />
            <ColHeader label={r3Label} w={CW.r3} isActive={activeRound === 3} />
          </div>

          <div style={{ display: "flex", gap: 6, alignItems: "flex-start" }}>
            {/* Round 1 */}
            <div style={{ width: CW.r1, flexShrink: 0, height: BRACKET_H, position: "relative" }}>
              <div style={{ position: "absolute", top: 0, left: 0, right: 0, display: "flex", flexDirection: "column" }}>
                {r1.map((m, i) => (
                  <div key={i}>
                    {i === 2 && <div style={{ height: PAIR_GAP }} />}
                    {i > 0 && i !== 2 && <div style={{ height: CARD_GAP }} />}
                    <SeriesCard m={m} />
                  </div>
                ))}
              </div>
            </div>

            {/* Semifinals */}
            <div style={{ width: CW.r2, flexShrink: 0, position: "relative", height: BRACKET_H }}>
              {[r2Top(0), r2BotTop].map((top, i) => (
                <div key={i} style={{ position: "absolute", top, left: 0, right: 0 }}>
                  <SeriesCard m={r2[i]} />
                </div>
              ))}
            </div>

            {/* Finals */}
            <div style={{ width: CW.r3, flexShrink: 0, position: "relative", height: BRACKET_H }}>
              <div style={{ position: "absolute", top: r3Top, left: 0, right: 0 }}>
                <SeriesCard m={r3} w={CW.r3} />
              </div>
            </div>

            {/* Champion banner — nothing shown until a champion is resolved */}
            <div style={{ width: CW.champion, flexShrink: 0, height: BRACKET_H, position: "relative" }}>
              <div style={{ position: "absolute", top: r3Top - 4, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
                {champion && <TeamMark team={teams[champion]} teamId={champion} league={leagueConfig.id} size={64} />}
                <div style={{ textAlign: "center" }}>
                  <div style={{ fontFamily: mono, fontSize: 9, fontWeight: 700, color: C.ut, textTransform: "uppercase", letterSpacing: 2 }}>
                    {seasonLabel} {leagueConfig.label} Champion
                  </div>
                  {champion && (
                    <div style={{ fontFamily: serif, fontSize: 20, fontWeight: 900, color: C.text, lineHeight: 1.1, marginTop: 4 }}>
                      {tn(champion)}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 24, fontFamily: mono, fontSize: 9, color: "rgba(0,0,0,0.35)", flexWrap: "wrap" }}>
            <span># = Seed (top {autoSeeds} overall, no conference split · win% · WNBA tiebreakers, head-to-head first)</span>
          </div>
        </div>
      </div>

      <div className="mobile-only" style={{ flexDirection: "column" }}>
        <div className="mobile-bracket-round-tabs">
          {mobileRounds.map((r) => (
            <button
              key={r.id}
              className={`mobile-bracket-round-btn${mobileActive === r.id ? " active" : ""}`}
              onClick={() => setMobileRound(r.id)}
            >
              {r.label}
            </button>
          ))}
        </div>
        {mobileCur.series.map((m, i) => (
          <MobileCard key={i} m={m} />
        ))}
        {mobileCur.id === "r3" && champion && (
          <div className="mobile-bracket-champion">
            <TeamMark team={teams[champion]} teamId={champion} league={leagueConfig.id} size={48} />
            <div style={{ fontFamily: mono, fontSize: 10, fontWeight: 700, color: C.ut, textTransform: "uppercase", letterSpacing: 2 }}>
              {seasonLabel} {leagueConfig.label} Champion
            </div>
            <div style={{ fontFamily: serif, fontSize: 20, fontWeight: 900, color: C.text }}>{tn(champion)}</div>
          </div>
        )}
      </div>

      <div
        style={{
          display: "flex", alignItems: "baseline", gap: 8, marginTop: 16,
          padding: "6px 12px", fontFamily: mono, fontSize: 10, color: C.text3,
        }}
      >
        <span style={{ fontWeight: 700, color: C.ut, textTransform: "uppercase", letterSpacing: 0.8, flexShrink: 0 }}>
          {started ? "Live" : "Projected"}
        </span>
        <span>
          {started
            ? "Series scores reflect completed playoff games; winners advance automatically."
            : `Round 1 reflects current ${seasonLabel} standings.`}
        </span>
      </div>
    </div>
  );
}
