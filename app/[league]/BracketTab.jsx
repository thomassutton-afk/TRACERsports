"use client";

/**
 * BracketTab — conference-bracket + play-in playoff view.
 *
 * Ported from the old single-league Dashboard.jsx's BracketTab, generalized
 * to run off leagueConfig instead of hardcoded NBA constants:
 *   - EAST_TEAMS/WEST_TEAMS (hardcoded sets)      -> leagueConfig.teams[id].conf
 *   - TEAM_COLORS/TEAM_SECONDARY (hardcoded maps) -> leagueConfig.teams[id].primary/secondary
 *   - custom TeamLogo component                   -> shared TeamMark.jsx
 *   - "NBA Finals" / "NBA Champion" / "2025–26"    -> leagueConfig.label + season prop
 *   - WEST_SEED_OVERRIDES/EAST_SEED_OVERRIDES      -> dropped (were one-off
 *     tiebreaker patches for a specific past season, not evergreen)
 *
 * Only wired up for conference-bracket + play-in formats right now
 * (leagueConfig.playoffFormat.type === 'conference-bracket'). A league whose
 * playoffFormat.playInSeeds is 0 will simply never show the play-in toggle.
 * Overall-bracket leagues (WNBA) get their own separate component — this one
 * assumes two conferences funneling into a Finals column.
 */

import { useState } from "react";
import TeamMark from "./TeamMark";
import { getFillColor, getTextColor } from "@/lib/teamColors";

const mono = "var(--font-mono)";
const serif = "var(--font-display)";
const C = {
  acc: "var(--acc)",
  ut: "var(--ut)",
  uo: "var(--uo)",
  text: "var(--text)",
  text2: "var(--text2)",
  text3: "var(--text3)",
  border2: "var(--border2)",
};

function winPct(t) {
  return t.w / (t.w + t.l || 1);
}

function standingsSort(a, b) {
  const pa = winPct(a), pb = winPct(b);
  if (Math.abs(pa - pb) > 0.0001) return pb - pa;
  return b.w - a.w;
}

// ── Bracket builder ───────────────────────────────────────────────────────
// poGames: rows shaped like { team_id, opponent_id, round, result, post_gm_rate,
//   home_away, points_for, points_against, date, game_id }, type='P' only,
// with round=0.1 (in-season tournament) already excluded by the caller.
// Round comes back from Supabase as TEXT, and the export pipeline writes
// SQLite's raw float through unstringified — so it can land as "1" or "1.0"
// depending on export path. Always compare rounds via parseFloat, never
// string equality, so "1" and "1.0" are treated as the same round.
function roundNum(round) {
  return round == null ? null : parseFloat(round);
}

function buildBracket(poGames) {
  const map = {};
  for (const g of poGames) {
    const pair = [g.team_id, g.opponent_id].sort().join("_");
    const rNum = roundNum(g.round);
    const key = `${rNum}_${pair}`;
    if (!map[key]) {
      const [a, b] = [g.team_id, g.opponent_id].sort();
      map[key] = { round: rNum, t1: a, t2: b, wins: { [a]: 0, [b]: 0 }, latestRating: {}, latestDate: "", games: [] };
    }
    const s = map[key];
    s.games.push(g);
    if (g.result === 1) s.wins[g.team_id] = (s.wins[g.team_id] || 0) + 1;
    if (g.date >= s.latestDate) {
      s.latestDate = g.date;
      s.latestRating[g.team_id] = g.post_gm_rate;
    }
  }
  return Object.values(map).map((s) => {
    const { t1, t2 } = s;
    const w1 = s.wins[t1] || 0, w2 = s.wins[t2] || 0;
    const maxWins = s.round === 0.5 ? 1 : 4;
    const winner = w1 >= maxWins ? t1 : w2 >= maxWins ? t2 : null;
    const loser = winner ? (winner === t1 ? t2 : t1) : null;
    return { ...s, w1, w2, winner, loser, maxWins };
  });
}

export default function BracketTab({ poGames, standings, leagueConfig, season }) {
  const [bracketView, setBracketView] = useState("playoffs");
  const playInSeeds = leagueConfig.playoffFormat?.playInSeeds ?? 0;
  const hasPlayIn = playInSeeds > 0;

  const teams = leagueConfig.teams;
  const tc = (abbr) => (teams[abbr] ? getFillColor(teams[abbr]) : null) || "#663399";
  const ts = (abbr) => (teams[abbr] ? getTextColor(teams[abbr]) : null) || "#663399";
  const tn = (abbr) => teams[abbr]?.name || abbr;

  const teamMap = {};
  for (const t of standings) teamMap[t.team_id] = t;

  const series = buildBracket(poGames);

  const conferences = leagueConfig.conferences || [];
  const [confA, confB] = conferences; // e.g. ['East','West']

  const teamsIn = (confName) => standings.filter((t) => teams[t.team_id]?.conf === confName).sort(standingsSort);
  const aSorted = teamsIn(confA);
  const bSorted = teamsIn(confB);
  const seedMap = {};
  aSorted.forEach((t, i) => { seedMap[t.team_id] = i + 1; });
  bSorted.forEach((t, i) => { seedMap[t.team_id] = i + 1; });

  const isConf = (confName) => (s) => teams[s.t1]?.conf === confName && teams[s.t2]?.conf === confName;
  // series[].round is already numeric (normalized in buildBracket), so this
  // is a plain numeric comparison — no string-format mismatch risk.
  const byRound = (rnd, pred) => series.filter((s) => s.round === rnd && pred(s));

  const aR1 = byRound(1, isConf(confA)), aR2 = byRound(2, isConf(confA)), aR3 = byRound(3, isConf(confA));
  const bR1 = byRound(1, isConf(confB)), bR2 = byRound(2, isConf(confB)), bR3 = byRound(3, isConf(confB));
  const finals = byRound(4, () => true);
  const playIn = hasPlayIn ? series.filter((s) => s.round === 0.5) : [];
  const champion = finals.find((s) => s.winner);

  // ── Seed-agnostic play-in game detection ──────────────────────────────
  function detectPlayInGames(confPlayIn) {
    if (!confPlayIn.length) return { game78: null, game910: null, secondary: null };
    if (confPlayIn.length === 1) return { game78: confPlayIn[0], game910: null, secondary: null };
    if (confPlayIn.length === 2) {
      const [a, b] = confPlayIn;
      const teamsA = new Set([a.t1, a.t2]);
      const teamsB = new Set([b.t1, b.t2]);
      const shared = [...teamsA].some((t) => teamsB.has(t));
      if (shared) {
        if (b.loser && teamsA.has(b.loser)) return { game78: b, game910: null, secondary: a };
        if (a.loser && teamsB.has(a.loser)) return { game78: a, game910: null, secondary: b };
        return { game78: a, game910: null, secondary: b };
      }
      return { game78: a, game910: b, secondary: null };
    }
    for (let i = 0; i < confPlayIn.length; i++) {
      const s = confPlayIn[i];
      const others = confPlayIn.filter((_, j) => j !== i);
      const teamsS = new Set([s.t1, s.t2]);
      const sharesWithBoth = others.every((o) => [o.t1, o.t2].some((t) => teamsS.has(t)));
      if (sharesWithBoth) {
        const [o1, o2] = others;
        if (o1.loser && teamsS.has(o1.loser)) return { game78: o1, game910: o2, secondary: s };
        return { game78: o2, game910: o1, secondary: s };
      }
    }
    return { game78: confPlayIn[0], game910: confPlayIn[1], secondary: confPlayIn[2] || null };
  }

  const aPI = hasPlayIn ? detectPlayInGames(playIn.filter(isConf(confA))) : { game78: null, game910: null, secondary: null };
  const bPI = hasPlayIn ? detectPlayInGames(playIn.filter(isConf(confB))) : { game78: null, game910: null, secondary: null };

  const prePatchSeedMap = { ...seedMap };

  function patchPlayInSeeds(pi) {
    if (pi.game78?.winner) seedMap[pi.game78.winner] = 7;
    if (pi.secondary?.winner) seedMap[pi.secondary.winner] = 8;
    if (pi.secondary?.loser) seedMap[pi.secondary.loser] = 9;
    if (!pi.secondary?.winner && pi.game78?.loser) seedMap[pi.game78.loser] = 8;
    if (pi.game910?.winner && !pi.secondary?.winner) seedMap[pi.game910.winner] = 9;
  }
  if (hasPlayIn) {
    patchPlayInSeeds(aPI);
    patchPlayInSeeds(bPI);
  }

  function placeholder(t1, t2) {
    return { t1: t1 || null, t2: t2 || null, w1: 0, w2: 0, winner: null, loser: null, games: [], latestRating: {}, latestDate: "", round: null, maxWins: 4 };
  }

  function findOrBuild(r1a, r1b, existingList, fallbackIdx) {
    const wa = r1a?.winner, wb = r1b?.winner;
    if (wa && wb) {
      const found = existingList.find((s) => (s.t1 === wa || s.t2 === wa) && (s.t1 === wb || s.t2 === wb));
      if (found) return found;
    }
    if (wa) {
      const found = existingList.find((s) => s.t1 === wa || s.t2 === wa);
      if (found) return found;
    }
    if (wb) {
      const found = existingList.find((s) => s.t1 === wb || s.t2 === wb);
      if (found) return found;
    }
    if (wa || wb) return placeholder(wa || null, wb || null);
    return existingList[fallbackIdx] || existingList[0] || null;
  }

  function findOrBuildCF(r2a, r2b, existingList) {
    const wa = r2a?.winner, wb = r2b?.winner;
    if (wa && wb) {
      const found = existingList.find((s) => (s.t1 === wa || s.t2 === wa) && (s.t1 === wb || s.t2 === wb));
      if (found) return found;
      return placeholder(wa, wb);
    }
    if (wa) {
      const found = existingList.find((s) => s.t1 === wa || s.t2 === wa);
      if (found) return found;
      return placeholder(wa, null);
    }
    if (wb) {
      const found = existingList.find((s) => s.t1 === wb || s.t2 === wb);
      if (found) return found;
      return placeholder(wb, null);
    }
    return existingList[0] || null;
  }

  function findOrBuildFinals(cfA, cfB, existingList) {
    if (existingList.length) return existingList[0];
    const wa = cfA?.winner, wb = cfB?.winner;
    if (wa || wb) return placeholder(wa || null, wb || null);
    return null;
  }

  function sortBySeed(list) {
    return [...list].sort((a, b) => {
      const aMin = Math.min(seedMap[a.t1] || 99, seedMap[a.t2] || 99);
      const bMin = Math.min(seedMap[b.t1] || 99, seedMap[b.t2] || 99);
      return aMin - bMin;
    });
  }

  function bracketOrder(list) {
    const sorted = sortBySeed(list);
    const find = (a, b) =>
      sorted.find((s) => {
        const seeds = [seedMap[s.t1] || 0, seedMap[s.t2] || 0].sort((x, y) => x - y);
        return seeds[0] === a && seeds[1] === b;
      }) || null;
    return [find(1, 8), find(4, 5), find(2, 7), find(3, 6)];
  }

  const aR1o = bracketOrder(aR1);
  const bR1o = bracketOrder(bR1);

  const aR2top = findOrBuild(aR1o[0], aR1o[1], aR2, 0);
  const aR2bot = findOrBuild(aR1o[2], aR1o[3], aR2.filter((s) => s !== aR2top), 1);
  const bR2top = findOrBuild(bR1o[0], bR1o[1], bR2, 0);
  const bR2bot = findOrBuild(bR1o[2], bR1o[3], bR2.filter((s) => s !== bR2top), 1);

  const aCF = findOrBuildCF(aR2top, aR2bot, aR3);
  const bCF = findOrBuildCF(bR2top, bR2bot, bR3);
  const fin = findOrBuildFinals(aCF, bCF, finals);

  // ── Layout constants ────────────────────────────────────────────────────
  const CARD_H = 76;
  const CARD_GAP = 5;
  const PAIR_GAP = 14;
  const LABEL_H = 30;

  const PAIR_H = CARD_H * 2 + CARD_GAP;
  const r2Top = (i) => i * (PAIR_H + PAIR_GAP) + (PAIR_H - CARD_H) / 2;
  const r2BotTop = r2Top(1);
  const CONF_H = r2BotTop + CARD_H;
  const cfTopVal = (r2Top(0) + CARD_H / 2 + r2BotTop + CARD_H / 2) / 2 - CARD_H / 2;
  const cfBottomEdge = cfTopVal + CARD_H;
  const finTopVal = cfBottomEdge + 20;

  const CW = { r1: 152, r2: 152, cf: 152, finals: 202 };

  // ── Team row ─────────────────────────────────────────────────────────────
  function BracketTeamRow({ abbr, wins, isWinner, seriesObj, isPlayIn = false, cardH = CARD_H }) {
    if (!abbr)
      return (
        <div style={{ height: cardH / 2, display: "flex", alignItems: "center", padding: "0 10px", borderLeft: "3px solid transparent" }}>
          <span style={{ fontFamily: mono, fontSize: 11, color: "rgba(255,255,255,0.25)" }}>TBD</span>
        </div>
      );
    const color = tc(abbr);
    const sec = ts(abbr);
    const seed = seedMap[abbr];
    const rating = seriesObj?.latestRating?.[abbr] ?? teamMap[abbr]?.rating ?? null;
    const displayScore = wins;
    const scale = cardH / CARD_H;
    return (
      <div
        style={{
          height: cardH / 2, display: "flex", alignItems: "center", overflow: "hidden",
          background: `${color}cc`,
          borderLeft: isWinner ? `3px solid ${color}` : "3px solid transparent",
          paddingRight: 6, position: "relative",
        }}
      >
        <div style={{ width: Math.round(26 * scale), textAlign: "center", fontFamily: mono, fontSize: Math.round(13 * scale), color: sec, flexShrink: 0, fontWeight: isWinner ? 700 : 600 }}>
          {seed ?? "—"}
        </div>
        <div style={{ width: Math.round(30 * scale), display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginRight: Math.round(3 * scale) }}>
          <TeamMark team={teams[abbr]} teamId={abbr} league={leagueConfig.id} size={Math.round(20 * scale)} />
        </div>
        <div
          style={{
            fontFamily: mono, fontSize: Math.round(9 * scale), fontWeight: 700,
            padding: `${Math.round(1 * scale)}px ${Math.round(4 * scale)}px`, borderRadius: 3,
            flexShrink: 0, minWidth: Math.round(32 * scale), textAlign: "center",
            border: `1.5px solid ${sec}`, color: sec, background: "transparent",
            marginRight: Math.round(5 * scale), letterSpacing: 0.3,
          }}
        >
          {abbr}
        </div>
        {rating != null && (
          <div style={{ fontFamily: mono, fontSize: Math.round(11 * scale), color: sec, opacity: 0.75, flexShrink: 0, fontWeight: 500 }}>
            {rating.toFixed(0)}
          </div>
        )}
        <div style={{ flex: 1 }} />
        <div
          style={{
            fontFamily: mono, fontSize: Math.round(20 * scale), fontWeight: 900, flexShrink: 0,
            minWidth: Math.round(18 * scale), textAlign: "center", lineHeight: 1, color: sec,
            textShadow: isWinner ? `0 0 10px ${color}60` : "none", marginRight: Math.round(6 * scale),
          }}
        >
          {displayScore ?? ""}
        </div>
      </div>
    );
  }

  // ── Series card ──────────────────────────────────────────────────────────
  function BracketCard({ s, cardH = CARD_H }) {
    if (!s)
      return (
        <div style={{ background: "rgba(255,255,255,0.4)", border: "1px dashed rgba(0,0,0,0.15)", borderRadius: 8, overflow: "hidden", height: cardH, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <span style={{ fontFamily: mono, fontSize: 10, color: "rgba(0,0,0,0.3)", letterSpacing: 0.5 }}>TBD</span>
        </div>
      );

    let { t1, t2, w1, w2, winner } = s;
    if (t1 && t2) {
      const s1 = seedMap[t1] ?? 99, s2 = seedMap[t2] ?? 99;
      if (s2 < s1) { [t1, t2] = [t2, t1]; [w1, w2] = [w2, w1]; }
    }

    const hasStarted = w1 > 0 || w2 > 0;
    const isActive = !winner && hasStarted;
    const isComplete = !!winner;
    const winnerColor = winner ? tc(winner) : null;

    return (
      <div
        style={{
          background: "transparent", borderRadius: 8, overflow: "hidden",
          border: isActive ? `1.5px solid ${C.acc}80` : isComplete ? `1px solid ${winnerColor}50` : `1px solid rgba(0,0,0,0.12)`,
          boxShadow: isActive ? `0 2px 16px ${C.acc}20` : isComplete ? `0 2px 12px ${winnerColor}20` : `0 1px 3px rgba(0,0,0,0.08)`,
          position: "relative",
        }}
      >
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 1, background: "rgba(255,255,255,0.3)", zIndex: 1, pointerEvents: "none" }} />
        <BracketTeamRow abbr={t1} wins={w1} isWinner={winner === t1} seriesObj={s} cardH={cardH} />
        <div style={{ height: 1, background: isComplete ? `${winnerColor}30` : "rgba(0,0,0,0.08)" }} />
        <BracketTeamRow abbr={t2} wins={w2} isWinner={winner === t2} seriesObj={s} cardH={cardH} />
      </div>
    );
  }

  // ── Conference bracket half ─────────────────────────────────────────────
  function ConfBracket({ r1, r2top, r2bot, cf, confColor, confName, mirror = false }) {
    const cols = mirror
      ? [
          { render: () => (
              <div style={{ width: CW.cf, flexShrink: 0, position: "relative", height: CONF_H }}>
                <div style={{ position: "absolute", top: cfTopVal, left: 0, right: 0 }}><BracketCard s={cf || null} /></div>
              </div>
            ) },
          { render: () => (
              <div style={{ width: CW.r2, flexShrink: 0, position: "relative", height: CONF_H }}>
                {[[r2top, r2Top(0)], [r2bot, r2BotTop]].map(([s, top], i) => (
                  <div key={i} style={{ position: "absolute", top, left: 0, right: 0 }}><BracketCard s={s || null} /></div>
                ))}
              </div>
            ) },
          { render: () => (
              <div style={{ width: CW.r1, flexShrink: 0, height: CONF_H, position: "relative" }}>
                <div style={{ position: "absolute", top: 0, left: 0, right: 0, display: "flex", flexDirection: "column", gap: 0 }}>
                  {[0, 1, 2, 3].map((i) => (
                    <div key={i}>
                      {i === 2 && <div style={{ height: PAIR_GAP }} />}
                      {i > 0 && i !== 2 && <div style={{ height: CARD_GAP }} />}
                      <BracketCard s={r1[i] || null} />
                    </div>
                  ))}
                </div>
              </div>
            ) },
        ]
      : [
          { render: () => (
              <div style={{ width: CW.r1, flexShrink: 0, height: CONF_H, position: "relative" }}>
                <div style={{ position: "absolute", top: 0, left: 0, right: 0, display: "flex", flexDirection: "column", gap: 0 }}>
                  {[0, 1, 2, 3].map((i) => (
                    <div key={i}>
                      {i === 2 && <div style={{ height: PAIR_GAP }} />}
                      {i > 0 && i !== 2 && <div style={{ height: CARD_GAP }} />}
                      <BracketCard s={r1[i] || null} />
                    </div>
                  ))}
                </div>
              </div>
            ) },
          { render: () => (
              <div style={{ width: CW.r2, flexShrink: 0, position: "relative", height: CONF_H }}>
                {[[r2top, r2Top(0)], [r2bot, r2BotTop]].map(([s, top], i) => (
                  <div key={i} style={{ position: "absolute", top, left: 0, right: 0 }}><BracketCard s={s || null} /></div>
                ))}
              </div>
            ) },
          { render: () => (
              <div style={{ width: CW.cf, flexShrink: 0, position: "relative", height: CONF_H }}>
                <div style={{ position: "absolute", top: cfTopVal, left: 0, right: 0 }}><BracketCard s={cf || null} /></div>
              </div>
            ) },
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
        <div style={{ display: "flex", alignItems: "flex-start", gap: 6, position: "relative" }}>
          {cols.map((col, i) => (
            <div key={i} style={{ flexShrink: 0 }}>{col.render()}</div>
          ))}
        </div>
      </div>
    );
  }

  // ── Finals column ────────────────────────────────────────────────────────
  function FinalsCard({ s }) {
    const finW = CW.finals;
    const finalsLabel = `${leagueConfig.label} Finals`;
    if (!s)
      return (
        <div style={{ width: finW, flexShrink: 0 }}>
          <div style={{ fontFamily: mono, fontSize: 10, fontWeight: 700, color: C.ut, textTransform: "uppercase", letterSpacing: 1.6, marginBottom: 8, paddingBottom: 8, borderBottom: `1px solid ${C.ut}40`, textAlign: "center" }}>
            {finalsLabel}
          </div>
          <div style={{ background: "rgba(255,255,255,0.4)", border: "1px dashed rgba(0,0,0,0.15)", borderRadius: 8, height: CARD_H, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <span style={{ fontFamily: mono, fontSize: 10, color: "rgba(0,0,0,0.3)" }}>TBD</span>
          </div>
        </div>
      );

    let { t1, t2, w1, w2, winner } = s;
    if (t1 && t2) {
      const s1 = seedMap[t1] ?? 99, s2 = seedMap[t2] ?? 99;
      if (s2 < s1) { [t1, t2] = [t2, t1]; [w1, w2] = [w2, w1]; }
    }
    const isComplete = !!winner;
    const winnerColor = winner ? tc(winner) : null;
    const FROW_H = 52;

    function FinalsTeamRow({ abbr, wins, isWin }) {
      if (!abbr)
        return (
          <div style={{ height: FROW_H, display: "flex", alignItems: "center", padding: "0 12px" }}>
            <span style={{ fontFamily: mono, fontSize: 11, color: "rgba(0,0,0,0.3)" }}>TBD</span>
          </div>
        );
      const color = tc(abbr);
      const sec = ts(abbr);
      const seed = seedMap[abbr];
      const rating = s.latestRating?.[abbr] ?? teamMap[abbr]?.rating ?? null;
      return (
        <div style={{ height: FROW_H, display: "flex", alignItems: "center", overflow: "hidden", position: "relative", background: `${color}cc`, borderLeft: isWin ? `4px solid ${color}` : "4px solid transparent", paddingRight: 8 }}>
          <div style={{ width: 24, textAlign: "center", fontFamily: mono, fontSize: 13, color: sec, fontWeight: isWin ? 700 : 600, flexShrink: 0 }}>{seed ?? "—"}</div>
          <div style={{ width: 34, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
            <TeamMark team={teams[abbr]} teamId={abbr} league={leagueConfig.id} size={24} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontFamily: mono, fontSize: 10, fontWeight: 700, color: sec, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{tn(abbr)}</div>
            {rating != null && <div style={{ fontFamily: mono, fontSize: 11, color: sec, opacity: 0.75, marginTop: 1, fontWeight: 500 }}>{rating.toFixed(0)}</div>}
          </div>
          <div style={{ fontFamily: mono, fontSize: 26, fontWeight: 900, lineHeight: 1, color: isWin ? sec : "rgba(0,0,0,0.4)", textShadow: isWin ? `0 0 12px ${color}80` : "none", marginLeft: 4, flexShrink: 0 }}>{wins}</div>
        </div>
      );
    }

    return (
      <div style={{ width: finW, flexShrink: 0 }}>
        <div style={{ fontFamily: mono, fontSize: 10, fontWeight: 700, color: C.ut, textTransform: "uppercase", letterSpacing: 1.6, marginBottom: 8, paddingBottom: 8, borderBottom: `1px solid ${C.ut}40`, textAlign: "center" }}>
          {finalsLabel}
        </div>
        <div style={{ borderRadius: 8, overflow: "hidden", border: isComplete ? `1px solid ${winnerColor}50` : "1px solid rgba(0,0,0,0.12)", boxShadow: isComplete ? `0 2px 12px ${winnerColor}20` : "0 1px 3px rgba(0,0,0,0.08)" }}>
          <FinalsTeamRow abbr={t1} wins={w1} isWin={winner === t1 || (!winner && w1 >= w2)} />
          <div style={{ height: 1, background: isComplete ? `${winnerColor}30` : "rgba(0,0,0,0.08)" }} />
          <FinalsTeamRow abbr={t2} wins={w2} isWin={winner === t2 || (!winner && w2 > w1)} />
        </div>
      </div>
    );
  }

  // ── Column headers row ───────────────────────────────────────────────────
  function BracketHeaders() {
    let activeRound = 1;
    for (const rnd of [1, 2, 3, 4]) {
      const inRound = series.filter((s) => s.round === rnd);
      if (!inRound.length) break;
      const anyInProgress = inRound.some((s) => !s.winner && (s.w1 > 0 || s.w2 > 0));
      const allDone = inRound.every((s) => s.winner);
      if (anyInProgress) { activeRound = rnd; break; }
      activeRound = rnd;
      if (!allDone) break;
    }
    const roundToKey = { 1: "r1", 2: "r2", 3: "cf", 4: "finals" };
    const activeKey = roundToKey[activeRound];

    const glowColor = "#D4AF37";
    const h = (label, w, colKey, side) => {
      const isActive = colKey === activeKey;
      return (
        <div
          key={`${colKey}-${side}`}
          style={{
            width: w, flexShrink: 0, fontFamily: mono, fontSize: 9, fontWeight: isActive ? 900 : 700,
            color: isActive ? glowColor : "rgba(0,0,0,0.45)", textTransform: "uppercase", letterSpacing: 1.6,
            paddingBottom: 8, borderBottom: isActive ? `2px solid ${glowColor}` : "1px solid rgba(0,0,0,0.15)",
            marginBottom: 12, textAlign: "center", textShadow: isActive ? `0 0 10px ${glowColor}90` : "none", transition: "all 0.2s",
          }}
        >
          {label}
        </div>
      );
    };
    return (
      <div style={{ display: "flex", gap: 6, marginBottom: 0 }}>
        {h("Round 1", CW.r1, "r1", "left")}
        {h("Conf Semis", CW.r2, "r2", "left")}
        {h("Conf Finals", CW.cf, "cf", "left")}
        {h(`${leagueConfig.label} Finals`, CW.finals, "finals", "center")}
        {h("Conf Finals", CW.cf, "cf", "right")}
        {h("Conf Semis", CW.r2, "r2", "right")}
        {h("Round 1", CW.r1, "r1", "right")}
      </div>
    );
  }

  // ── PLAY-IN BRACKET ───────────────────────────────────────────────────────
  function PlayInBracket() {
    const { game78: aGame78, game910: aGame910, secondary: aSecondary } = aPI;
    const { game78: bGame78, game910: bGame910, secondary: bSecondary } = bPI;

    function PICard({ s }) {
      if (!s)
        return (
          <div style={{ background: "rgba(255,255,255,0.4)", border: "1px dashed rgba(0,0,0,0.15)", borderRadius: 8, height: CARD_H, display: "flex", alignItems: "center", justifyContent: "center" }}>
            <span style={{ fontFamily: mono, fontSize: 10, color: "rgba(0,0,0,0.3)" }}>TBD</span>
          </div>
        );
      const game = s.games.find((g) => g.home_away === "H") || s.games[0];
      const homeTeam = game?.team_id;
      const awayTeam = game?.opponent_id;
      const homeScore = game?.points_for ?? null;
      const awayScore = game?.points_against ?? null;

      let { t1, t2 } = s;
      if (t1 && t2) {
        const s1 = prePatchSeedMap[t1] ?? 99, s2 = prePatchSeedMap[t2] ?? 99;
        if (s2 < s1) [t1, t2] = [t2, t1];
      }

      const score1 = t1 === homeTeam ? homeScore : t1 === awayTeam ? awayScore : null;
      const score2 = t2 === homeTeam ? homeScore : t2 === awayTeam ? awayScore : null;
      const isComplete = !!s.winner;
      const winnerColor = s.winner ? tc(s.winner) : null;

      function PIRow({ abbr, score, isWin }) {
        if (!abbr)
          return (
            <div style={{ height: CARD_H / 2, display: "flex", alignItems: "center", padding: "0 10px" }}>
              <span style={{ fontFamily: mono, fontSize: 10, color: "rgba(0,0,0,0.3)" }}>TBD</span>
            </div>
          );
        const color = tc(abbr);
        const sec = ts(abbr);
        const seed = prePatchSeedMap[abbr];
        return (
          <div style={{ height: CARD_H / 2, display: "flex", alignItems: "center", overflow: "hidden", background: `${color}cc`, borderLeft: isWin ? `3px solid ${color}` : "3px solid transparent", paddingRight: 6, position: "relative" }}>
            <div style={{ width: 22, textAlign: "center", fontFamily: mono, fontSize: 10, color: sec, fontWeight: isWin ? 700 : 500, flexShrink: 0 }}>{seed ?? "—"}</div>
            <div style={{ width: 28, display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0, marginRight: 2 }}>
              <TeamMark team={teams[abbr]} teamId={abbr} league={leagueConfig.id} size={18} />
            </div>
            <div style={{ fontFamily: mono, fontSize: 9, fontWeight: 700, minWidth: 32, textAlign: "center", padding: "1px 4px", borderRadius: 3, flexShrink: 0, border: `1.5px solid ${sec}`, color: sec, background: "transparent", marginRight: 4, letterSpacing: 0.3 }}>{abbr}</div>
            <div style={{ flex: 1 }} />
            {score != null && (
              <div style={{ fontFamily: mono, fontSize: 18, fontWeight: 900, color: isWin ? sec : "rgba(0,0,0,0.5)", textShadow: isWin ? `0 0 10px ${color}60` : "none", marginRight: 4 }}>{score}</div>
            )}
          </div>
        );
      }

      return (
        <div style={{ borderRadius: 8, overflow: "hidden", border: isComplete ? `1px solid ${winnerColor}50` : "1px solid rgba(0,0,0,0.12)", boxShadow: isComplete ? `0 2px 12px ${winnerColor}20` : "0 1px 3px rgba(0,0,0,0.08)" }}>
          <PIRow abbr={t1} score={score1} isWin={s.winner === t1} />
          <div style={{ height: 1, background: isComplete ? `${winnerColor}30` : "rgba(0,0,0,0.08)" }} />
          <PIRow abbr={t2} score={score2} isWin={s.winner === t2} />
        </div>
      );
    }

    function PIConf({ confName, game78, game910, secondary, confColor }) {
      const winner78 = game78?.winner || null;
      const secondary8 = secondary?.winner || null;
      return (
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontFamily: mono, fontSize: 10, fontWeight: 700, color: confColor, textTransform: "uppercase", letterSpacing: 2, marginBottom: 12, paddingBottom: 6, borderBottom: "1px solid rgba(0,0,0,0.12)" }}>
            {confName} Conference
          </div>
          <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: mono, fontSize: 8, color: "rgba(0,0,0,0.45)", textTransform: "uppercase", letterSpacing: 1, marginBottom: 5, fontWeight: 600 }}>7 vs 8 · winner = 7-seed</div>
              <PICard s={game78} />
              {winner78 && (
                <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 6, padding: "4px 7px", background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 5 }}>
                  <span style={{ fontFamily: mono, fontSize: 8, color: confColor, fontWeight: 700 }}>7-seed →</span>
                  <TeamMark team={teams[winner78]} teamId={winner78} league={leagueConfig.id} size={14} />
                  <span style={{ fontFamily: mono, fontSize: 9, fontWeight: 700, color: tc(winner78), padding: "1px 4px", borderRadius: 3, border: `1.5px solid ${tc(winner78)}`, background: `${tc(winner78)}20` }}>{winner78}</span>
                </div>
              )}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontFamily: mono, fontSize: 8, color: "rgba(0,0,0,0.45)", textTransform: "uppercase", letterSpacing: 1, marginBottom: 5, fontWeight: 600 }}>9 vs 10</div>
              <PICard s={game910} />
              <div style={{ marginTop: 10 }}>
                <div style={{ fontFamily: mono, fontSize: 8, color: "rgba(0,0,0,0.45)", textTransform: "uppercase", letterSpacing: 1, marginBottom: 5, fontWeight: 600 }}>
                  9/10 winner vs 7/8 loser · winner = 8-seed
                </div>
                <PICard s={secondary} />
                {secondary8 && (
                  <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 6, padding: "4px 7px", background: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.12)", borderRadius: 5 }}>
                    <span style={{ fontFamily: mono, fontSize: 8, color: confColor, fontWeight: 700 }}>8-seed →</span>
                    <TeamMark team={teams[secondary8]} teamId={secondary8} league={leagueConfig.id} size={14} />
                    <span style={{ fontFamily: mono, fontSize: 9, fontWeight: 700, color: tc(secondary8), padding: "1px 4px", borderRadius: 3, border: `1.5px solid ${tc(secondary8)}`, background: `${tc(secondary8)}20` }}>{secondary8}</span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      );
    }

    return (
      <div style={{ background: "#DDD5C4", borderRadius: 14, padding: "20px 18px 24px", boxShadow: "0 4px 24px rgba(0,0,0,0.10), inset 0 1px 0 rgba(255,255,255,0.4)", border: "1px solid #C8BFB1", position: "relative", overflow: "hidden", width: "fit-content", margin: "0 auto" }}>
        <div style={{ position: "absolute", top: 0, left: "50%", transform: "translateX(-50%)", width: "80%", height: "40%", borderRadius: "50%", background: "radial-gradient(ellipse, rgba(255,255,255,0.04) 0%, transparent 70%)", pointerEvents: "none" }} />
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
          <div style={{ flex: 1, height: 1, background: "rgba(0,0,0,0.12)" }} />
          <span style={{ fontFamily: mono, fontSize: 10, fontWeight: 700, color: "rgba(0,0,0,0.45)", textTransform: "uppercase", letterSpacing: 2 }}>
            Play-In Tournament {leagueConfig.seasonLabel ? leagueConfig.seasonLabel(season) : season}
          </span>
          <div style={{ flex: 1, height: 1, background: "rgba(0,0,0,0.12)" }} />
        </div>
        <div style={{ display: "flex", gap: 28 }}>
          <PIConf confName={confA} game78={aGame78} game910={aGame910} secondary={aSecondary} confColor="rgba(102,51,153,0.9)" />
          <PIConf confName={confB} game78={bGame78} game910={bGame910} secondary={bSecondary} confColor="rgba(191,87,0,0.9)" />
        </div>
        <div style={{ marginTop: 16, padding: "10px 14px", background: "rgba(255,255,255,0.5)", border: "1px solid rgba(0,0,0,0.1)", borderRadius: 8, fontFamily: mono, fontSize: 10, color: "rgba(0,0,0,0.55)" }}>
          <strong style={{ color: "rgba(0,0,0,0.75)" }}>How it works:</strong> The 7 vs 8 winner earns the 7-seed directly.
          The loser plays the 9 vs 10 winner — that winner earns the 8-seed.
        </div>
      </div>
    );
  }

  // ── Main render ────────────────────────────────────────────────────────
  return (
    <div>
      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        {[["playoffs", "Playoff Bracket"], ...(hasPlayIn ? [["playin", "Play-In Tournament"]] : [])].map(([v, l]) => (
          <button
            key={v}
            onClick={() => setBracketView(v)}
            style={{
              fontFamily: mono, fontSize: 11, padding: "5px 14px", borderRadius: 6, cursor: "pointer",
              border: `1px solid ${bracketView === v ? C.acc : C.border2}`,
              background: bracketView === v ? C.acc : "transparent",
              color: bracketView === v ? "#fff" : C.text2, transition: "all 0.15s",
            }}
          >
            {l}
          </button>
        ))}
        <span style={{ marginLeft: "auto", fontFamily: mono, fontSize: 9, color: C.text3, alignSelf: "center" }}>
          Seeds reflect RS standings (win%) · Ratings = latest in series
        </span>
      </div>

      {bracketView === "playin" && hasPlayIn && <PlayInBracket />}

      {bracketView === "playoffs" && (
        <div>
          <div style={{ background: "#DDD5C4", borderRadius: 14, padding: "16px 14px 20px", boxShadow: "0 4px 24px rgba(0,0,0,0.10), inset 0 1px 0 rgba(255,255,255,0.4)", border: "1px solid #C8BFB1", position: "relative", overflow: "hidden", width: "fit-content", margin: "0 auto" }}>
            <div style={{ position: "absolute", top: 0, left: "50%", transform: "translateX(-50%)", width: "80%", height: "40%", borderRadius: "50%", background: "radial-gradient(ellipse, rgba(255,255,255,0.04) 0%, transparent 70%)", pointerEvents: "none" }} />
            <BracketHeaders />
            <div style={{ display: "flex", gap: 6, alignItems: "flex-start", position: "relative" }}>
              <ConfBracket r1={aR1o} r2top={aR2top} r2bot={aR2bot} cf={aCF} confColor="rgba(102,51,153,0.9)" confName={confA} mirror={false} />
              <div style={{ flexShrink: 0, width: CW.finals, alignSelf: "stretch", position: "relative", minHeight: LABEL_H + finTopVal + CARD_H + 20 }}>
                {champion && (
                  <div style={{ position: "absolute", top: 0, left: 0, right: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "flex-start", paddingTop: LABEL_H + 6, gap: 8 }}>
                    <TeamMark team={teams[champion.winner]} teamId={champion.winner} league={leagueConfig.id} size={64} />
                    <div style={{ textAlign: "center" }}>
                      <div style={{ fontFamily: mono, fontSize: 9, fontWeight: 700, color: C.ut, textTransform: "uppercase", letterSpacing: 2, marginBottom: 4 }}>
                        {leagueConfig.seasonLabel ? leagueConfig.seasonLabel(season) : season} {leagueConfig.label} Champion
                      </div>
                      <div style={{ fontFamily: serif, fontSize: 20, fontWeight: 900, color: C.text, lineHeight: 1.1 }}>
                        {tn(champion.winner)}
                      </div>
                    </div>
                  </div>
                )}
                <div style={{ position: "absolute", top: LABEL_H + finTopVal, left: 0, right: 0 }}>
                  <FinalsCard s={fin} />
                </div>
              </div>
              <ConfBracket r1={bR1o} r2top={bR2top} r2bot={bR2bot} cf={bCF} confColor="rgba(191,87,0,0.9)" confName={confB} mirror={true} />
            </div>
            <div style={{ display: "flex", gap: 20, marginTop: 28, fontFamily: mono, fontSize: 9, color: "rgba(0,0,0,0.35)", flexWrap: "wrap" }}>
              <span># = Conference seed (RS standings)</span>
              <span>Rating = end-of-series post-game rating</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
