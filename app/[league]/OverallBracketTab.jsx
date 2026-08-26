"use client";

/**
 * OverallBracketTab — top-N-overall single-elimination bracket (no
 * conference split, no play-in). Built for WNBA's format
 * (playoffFormat.type === 'overall-bracket') but league-agnostic so any
 * future league with the same shape can reuse it.
 *
 * PROJECTED, not live: this only reads `standings` (current win% record),
 * not actual playoff game results. Round 1 seeding is real, concrete data —
 * it's exactly who'd play whom if the regular season ended today. Rounds
 * beyond that stay TBD on purpose: who advances is unknown until Round 1 is
 * actually played, and guessing would just be a fabricated prediction.
 *
 * NOT YET WIRED FOR LIVE PLAYOFF GAMES. Once WNBA playoffs actually start,
 * this will need updating to pull real `type='P'` games and track series
 * wins the same way BracketTab.jsx does for the NBA. Series length per
 * round is now confirmed in wnba/config.js (playoffFormat.winsNeeded:
 * best-of-3 Round 1, best-of-5 Semis, best-of-7 Finals) — that was the
 * blocking unknown, so this is ready to build whenever real playoff games
 * exist to track.
 */

import TeamMark from "./TeamMark";
import { getFillColor, getTextColor } from "@/lib/teamColors";

const mono = "var(--font-mono)";
const C = {
  acc: "var(--acc)",
  ut: "var(--ut)",
  text: "var(--text)",
  text2: "var(--text2)",
  text3: "var(--text3)",
};

function winPct(t) {
  return t.w / (t.w + t.l || 1);
}

function standingsSort(a, b) {
  const pa = winPct(a), pb = winPct(b);
  if (Math.abs(pa - pb) > 0.0001) return pb - pa;
  return b.w - a.w;
}

export default function OverallBracketTab({ standings, leagueConfig, season }) {
  const teams = leagueConfig.teams;
  const autoSeeds = leagueConfig.playoffFormat?.autoSeeds ?? 8;
  const roundLabels = leagueConfig.engine?.roundLabels || {};
  const r1Label = roundLabels["1"] || "Round 1";
  const r2Label = roundLabels["2"] || "Semifinals";
  const r3Label = roundLabels["3"] || `${leagueConfig.label} Finals`;
  const seasonLabel = leagueConfig.seasonLabel ? leagueConfig.seasonLabel(season) : season;

  const seeded = [...standings].sort(standingsSort).slice(0, autoSeeds);
  const teamBySeed = {};
  seeded.forEach((t, i) => { teamBySeed[i + 1] = t; });

  // Standard 8-team bracket pairing: 1v8 and 4v5 feed the top semifinal
  // slot, 2v7 and 3v6 feed the bottom one — same pairing convention used
  // in BracketTab's conference brackets.
  const r1Pairs = [[1, 8], [4, 5], [2, 7], [3, 6]];

  // Same exact card dimensions as BracketTab.jsx's NBA conference bracket.
  const CARD_H = 76;
  const CARD_GAP = 5;
  const PAIR_GAP = 14;
  const LABEL_H = 30;

  const PAIR_H = CARD_H * 2 + CARD_GAP;
  const r2Top = (i) => i * (PAIR_H + PAIR_GAP) + (PAIR_H - CARD_H) / 2;
  const r2BotTop = r2Top(1);
  const BRACKET_H = r2BotTop + CARD_H;
  const r3Top = (r2Top(0) + CARD_H / 2 + r2BotTop + CARD_H / 2) / 2 - CARD_H / 2;

  // Finals column matches BracketTab.jsx's NBA Finals bubble width (202,
  // not the 152 the other columns use). The champion-banner block gets its
  // own column of the same width, placed to the right of the bracket
  // instead of stacked above the Finals card like the NBA layout does.
  const CW = { r1: 152, r2: 152, r3: 202, champion: 202 };

  function SeedRow({ seed, team }) {
    const rowH = CARD_H / 2;
    if (!team) return <div style={{ height: rowH }} />;
    const teamCfg = teams[team.team_id];
    const color = (teamCfg ? getFillColor(teamCfg) : null) || "#663399";
    const sec = (teamCfg ? getTextColor(teamCfg) : null) || color;
    return (
      <div
        style={{
          height: rowH, display: "flex", alignItems: "center", overflow: "hidden",
          background: `${color}cc`, borderLeft: "3px solid transparent", paddingRight: 6,
        }}
      >
        <div style={{ width: 26, textAlign: "center", fontFamily: mono, fontSize: 13, color: sec, flexShrink: 0, fontWeight: 600 }}>
          {seed}
        </div>
        <div style={{ width: 30, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginRight: 3 }}>
          <TeamMark team={teamCfg} teamId={team.team_id} league={leagueConfig.id} size={20} />
        </div>
        <div
          style={{
            fontFamily: mono, fontSize: 9, fontWeight: 700,
            padding: "1px 4px", borderRadius: 3, flexShrink: 0, minWidth: 32, textAlign: "center",
            border: `1.5px solid ${sec}`, color: sec, background: "transparent",
            marginRight: 5, letterSpacing: 0.3,
          }}
        >
          {team.team_id}
        </div>
        <div style={{ flex: 1 }} />
        {/* Intentionally nothing in the series-score slot here — once real
            playoff games exist this becomes an actual 0-0 series score, same
            spot BracketTab.jsx uses for the NBA. Showing a rating (or any
            other number) there right now would look like a score for a
            series that hasn't been played. */}
      </div>
    );
  }

  function R1Card({ pair }) {
    const [seedA, seedB] = pair;
    const teamA = teamBySeed[seedA], teamB = teamBySeed[seedB];
    return (
      <div style={{ borderRadius: 8, overflow: "hidden", border: "1px solid rgba(0,0,0,0.12)", boxShadow: "0 1px 3px rgba(0,0,0,0.08)" }}>
        <SeedRow seed={seedA} team={teamA} />
        <div style={{ height: 1, background: "rgba(0,0,0,0.08)" }} />
        <SeedRow seed={seedB} team={teamB} />
      </div>
    );
  }

  function TBDCard({ h = CARD_H, w }) {
    return (
      <div style={{ width: w, background: "rgba(255,255,255,0.4)", border: "1px dashed rgba(0,0,0,0.15)", borderRadius: 8, overflow: "hidden", height: h }} />
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
        }}
      >
        {label}
      </div>
    );
  }

  return (
    <div>
      <div
        style={{
          background: "#DDD5C4", borderRadius: 14, padding: "16px 14px 20px",
          boxShadow: "0 4px 24px rgba(0,0,0,0.10), inset 0 1px 0 rgba(255,255,255,0.4)",
          border: "1px solid #C8BFB1", position: "relative", overflow: "hidden", width: "fit-content", margin: "0 auto",
        }}
      >
        <div style={{ display: "flex", gap: 6, marginBottom: 0 }}>
          <ColHeader label={r1Label} w={CW.r1} isActive={true} />
          <ColHeader label={r2Label} w={CW.r2} isActive={false} />
          <ColHeader label={r3Label} w={CW.r3} isActive={false} />
        </div>

        <div style={{ display: "flex", gap: 6, alignItems: "flex-start" }}>
          {/* Round 1 — real seeding, two pair-blocks with a gap between them */}
          <div style={{ width: CW.r1, flexShrink: 0, height: BRACKET_H, position: "relative" }}>
            <div style={{ position: "absolute", top: 0, left: 0, right: 0, display: "flex", flexDirection: "column" }}>
              {r1Pairs.map((pair, i) => (
                <div key={i}>
                  {i === 2 && <div style={{ height: PAIR_GAP }} />}
                  {i > 0 && i !== 2 && <div style={{ height: CARD_GAP }} />}
                  <R1Card pair={pair} />
                </div>
              ))}
            </div>
          </div>

          {/* Semifinals — TBD until Round 1 is played */}
          <div style={{ width: CW.r2, flexShrink: 0, position: "relative", height: BRACKET_H }}>
            {[r2Top(0), r2BotTop].map((top, i) => (
              <div key={i} style={{ position: "absolute", top, left: 0, right: 0 }}>
                <TBDCard />
              </div>
            ))}
          </div>

          {/* Finals — TBD, widened to match BracketTab.jsx's NBA Finals bubble */}
          <div style={{ width: CW.r3, flexShrink: 0, position: "relative", height: BRACKET_H }}>
            <div style={{ position: "absolute", top: r3Top, left: 0, right: 0 }}>
              <TBDCard w={CW.r3} />
            </div>
          </div>

          {/* Champion banner block — placed as its own column to the right of
              the bracket (not stacked above the Finals card like the NBA
              layout). Nothing shown here at all until there's a resolved
              champion — no placeholder icon, no placeholder name. */}
          <div style={{ width: CW.champion, flexShrink: 0, height: BRACKET_H, position: "relative" }}>
            <div style={{ position: "absolute", top: r3Top - 4, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
              <div style={{ textAlign: "center" }}>
                <div style={{ fontFamily: mono, fontSize: 9, fontWeight: 700, color: C.ut, textTransform: "uppercase", letterSpacing: 2 }}>
                  {seasonLabel} {leagueConfig.label} Champion
                </div>
              </div>
            </div>
          </div>
        </div>

        <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 24, fontFamily: mono, fontSize: 9, color: "rgba(0,0,0,0.35)" }}>
          <span># = Seed (top {autoSeeds} overall, no conference split · win% · tiebreak: wins)</span>
        </div>
      </div>

      {/* "Not final" note — small footnote below the bracket, not a big banner up top */}
      <div
        style={{
          display: "flex", alignItems: "baseline", gap: 8, marginTop: 16,
          padding: "6px 12px", fontFamily: mono, fontSize: 10, color: C.text3,
        }}
      >
        <span style={{ fontWeight: 700, color: C.ut, textTransform: "uppercase", letterSpacing: 0.8, flexShrink: 0 }}>Projected</span>
        <span>
          {`Round 1 reflects current ${seasonLabel} standings.`}
        </span>
      </div>
    </div>
  );
}
