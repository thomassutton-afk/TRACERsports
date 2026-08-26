"use client";

/**
 * app/[league]/team/page.js — Team selector landing page.
 *
 * The old site put its team dropdown directly in the nav bar, always
 * visible on every team page, letting you jump between teams without
 * detouring through a list page first (reference/old-site/TeamPage.jsx —
 * the <select> next to Echo/Pulse). This page gets you the same outcome —
 * "pick any team, land on its page" — through a dedicated landing page
 * instead, same pattern as Season's selector: kept out of the shared
 * Nav.jsx component so a page-specific concern (which team is selected)
 * doesn't add complexity to a component every other page also depends on.
 * Nav's new "Teams" link points here.
 *
 * Once a team is picked, the URL itself (/[league]/team/[teamId]) is what
 * you'd bookmark/share/link to — this page is just the on-ramp, not
 * something a Team page itself ever redirects back to.
 */

import { useState, useEffect } from "react";
import { useParams, useSearchParams, useRouter } from "next/navigation";
import { getLeagueConfig } from "@/lib/sports/registry";
import TeamMark from "../TeamMark";
import HistoricalTeamMark from "../HistoricalTeamMark";
import { fetchLogoIndex, resolveHistoricalLogoPath } from "@/lib/historicalIdentity";
import { getFillColor, getTextColor } from "@/lib/teamColors";

// Folded franchises (e.g. WNBA's Sting/Rockers/Comets/Sol/Monarchs) never
// got a "current" logo under /logos/{league}/{code}.png — TeamMark 404s on
// them and falls back to the plain text badge. They DO have files under
// /logos/historical/{league}/{code}_{year}.png though, so for the Former
// Teams grid we resolve each one's most recent historical file instead
// (season passed as Infinity picks the latest year on file for that code).
const FAR_FUTURE_SEASON = 9999;

export default function TeamSelectorPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const router = useRouter();
  const league = params.league;
  const variant = searchParams.get("variant") || "echo";

  const [selected, setSelected] = useState("");
  const [logoIndex, setLogoIndex] = useState(null);

  useEffect(() => {
    let cancelled = false;
    fetchLogoIndex(league).then((idx) => {
      if (!cancelled) setLogoIndex(idx);
    });
    return () => {
      cancelled = true;
    };
  }, [league]);

  let leagueConfig;
  let configError = null;
  try {
    leagueConfig = getLeagueConfig(league);
  } catch (e) {
    configError = e.message;
  }

  if (configError) {
    return (
      <div style={{ padding: 40, fontFamily: "var(--font-mono)" }}>
        <p>Unknown league: &quot;{league}&quot;</p>
        <p>{configError}</p>
      </div>
    );
  }

  const teamIds = Object.keys(leagueConfig.teams).sort();
  // Folded franchises (WNBA only, e.g. Sting/Rockers/Comets/Sol/Monarchs)
  // get grouped into a separate "Former Teams" section below the active grid.
  const activeIds = teamIds.filter((id) => !leagueConfig.teams[id].folded);
  const formerIds = teamIds.filter((id) => leagueConfig.teams[id].folded);

  function goToTeam(teamId) {
    if (!teamId) return;
    router.push(`/${league}/team/${teamId}?variant=${variant}`);
  }

  return (
    <div>
      <div className="hero">
        <div>
          <div className="hero-label">Franchise History</div>
          <div className="hero-heading">Teams</div>
          <div className="hero-sub">Pick a team to see its full {leagueConfig.label} history</div>
        </div>
        <select
          value={selected}
          onChange={(e) => {
            setSelected(e.target.value);
            goToTeam(e.target.value);
          }}
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            padding: "6px 12px",
            border: "1px solid var(--border2)",
            borderRadius: 8,
            background: "var(--surface)",
            color: "var(--text)",
            cursor: "pointer",
          }}
        >
          <option value="" disabled>
            Jump to a team…
          </option>
          {teamIds.map((id) => (
            <option key={id} value={id}>
              {id} — {leagueConfig.teams[id].name}
            </option>
          ))}
        </select>
      </div>

      <div style={{ maxWidth: 1200, margin: "0 auto", padding: "1.5rem 2rem 4rem" }}>
        <TeamGrid teamIds={activeIds} teams={leagueConfig.teams} league={league} onSelect={goToTeam} />

        {formerIds.length > 0 && (
          <>
            <div className="section-label" style={{ marginTop: 32 }}>
              Former Teams
            </div>
            <TeamGrid
              teamIds={formerIds}
              teams={leagueConfig.teams}
              league={league}
              onSelect={goToTeam}
              muted
              logoIndex={logoIndex}
            />
          </>
        )}
      </div>
    </div>
  );
}

function TeamGrid({ teamIds, teams, league, onSelect, muted = false, logoIndex = null }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))",
        gap: 12,
      }}
    >
      {teamIds.map((id) => {
        const team = teams[id];
        // black/near-black primaries (Nets, Aces) fall back to tertiary —
        // see lib/teamColors.js for why this uses luminance, not a string match
        const fillColor = getFillColor(team);
        // Folded teams have no current-logo file — resolve their last
        // historical logo instead once the index has loaded (null until then,
        // which HistoricalTeamMark treats the same as "no match", i.e. badge).
        const historicalLogoPath = muted
          ? resolveHistoricalLogoPath(id, FAR_FUTURE_SEASON, {}, logoIndex ?? {}, league)
          : null;
        return (
          <button
            key={id}
            onClick={() => onSelect(id)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 12,
              padding: "14px 16px",
              borderRadius: 12,
              border: "1px solid var(--border)",
              background: fillColor,
              opacity: muted ? 0.75 : 1,
              cursor: "pointer",
              textAlign: "left",
              fontFamily: "inherit",
            }}
          >
            {muted ? (
              <HistoricalTeamMark
                logoPath={historicalLogoPath}
                currentLogoTeamId={id}
                league={league}
                abbr={id}
                color={getTextColor(team)}
                size={32}
              />
            ) : (
              <TeamMark team={team} teamId={id} league={league} size={32} />
            )}
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: getTextColor(team) }}>{team.name}</div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: getTextColor(team), opacity: 0.7, letterSpacing: 0.5 }}>
                {id}
              </div>
            </div>
          </button>
        );
      })}
    </div>
  );
}
