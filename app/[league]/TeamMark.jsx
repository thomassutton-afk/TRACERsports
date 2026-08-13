"use client";

import { useState } from "react";

/**
 * TeamMark — league-agnostic replacement for the old single-league
 * TeamLogo component. Renders the real logo image (with the same glow
 * drop-shadow as the original) and falls back to a bordered abbreviation
 * badge — NOT a flat filled circle — if the image 404s, exactly matching
 * the old TeamLogo's `errored` state.
 *
 * Needs `teamId` + `league` to build the image path
 * (`/logos/${league}/${teamId}.png`). If either is missing, it skips
 * straight to the badge fallback.
 *
 * FILENAME_OVERRIDES: a few team IDs collide with reserved Windows device
 * names (CON, PRN, AUX, NUL, COM1-9, LPT1-9), so a file literally named
 * e.g. `CON.png` can't exist on disk on Windows. For any such ID, the
 * actual asset on disk is named differently (convention: trailing
 * underscore) — this map is the ONLY place that needs to know about it.
 * teamId itself (used for DB lookups, display, etc.) is untouched.
 */
const FILENAME_OVERRIDES = {
  CON: "CON_", // WNBA Connecticut Sun — reserved Windows device name
};

export default function TeamMark({ team, teamId, league, size = 28 }) {
  const [errored, setErrored] = useState(false);
  const color = team.primary || "#663399";
  const abbr = teamId || team.abbr || team.id || (team.nickname ? team.nickname.slice(0, 3).toUpperCase() : "??");
  const canLoadImage = !!(teamId && league);
  const fileName = FILENAME_OVERRIDES[teamId] || teamId;

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
