"use client";

import { useState } from "react";
import { logoFileName, displayAbbr } from "../../lib/logoFilenameOverrides";

/**
 * TeamMark — league-agnostic replacement for the old single-league
 * TeamLogo component. Renders the real logo image (with the same glow
 * drop-shadow as the original) and falls back to a bordered abbreviation
 * badge — NOT a flat filled circle — if the image 404s, exactly matching
 * the old TeamLogo's `errored` state.
 *
 * Needs `teamId` + `league` to build the image path
 * (`/logos/${league}/${logoFileName(teamId)}.png`). If either is
 * missing, it skips straight to the badge fallback. See
 * lib/logoFilenameOverrides.js for why the filename can differ from
 * teamId itself.
 */

export default function TeamMark({ team, teamId, league, size = 28 }) {
  const [errored, setErrored] = useState(false);
  const color = team.primary || "#663399";
  const abbr = displayAbbr(teamId || team.abbr || team.id || (team.nickname ? team.nickname.slice(0, 3).toUpperCase() : "??"));
  const canLoadImage = !!(teamId && league);
  const fileName = logoFileName(teamId);

  if (!canLoadImage || errored) {
    return (
      <span
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: Math.max(8, size * 0.38),
          fontWeight: 700,
          padding: "2px 6px",
          borderRadius: 4,
          border: `1.5px solid ${color}`,
          color,
          letterSpacing: 0.3,
          flexShrink: 0,
          lineHeight: 1,
          display: "inline-flex",
          alignItems: "center",
        }}
      >
        {abbr}
      </span>
    );
  }

  return (
    <img
      src={`/logos/${league}/${fileName}.png`}
      alt={abbr}
      width={size}
      height={size}
      onError={() => setErrored(true)}
      style={{
        width: size,
        height: size,
        objectFit: "contain",
        flexShrink: 0,
        display: "block",
        filter:
          "drop-shadow(0 0 4px rgba(255,255,255,0.95)) drop-shadow(0 0 10px rgba(255,255,255,0.6))",
      }}
    />
  );
}
