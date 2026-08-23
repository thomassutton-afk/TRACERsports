"use client";

import { useState } from "react";
import { logoFileName } from "../../lib/logoFilenameOverrides";

/**
 * HistoricalTeamMark — season-aware version of TeamMark.jsx.
 *
 * TeamMark always shows a team's CURRENT logo/color regardless of season —
 * correct for the live Dashboard/Season Page (which shows this season's
 * team, in this season's identity), wrong for All-Time/Team pages showing
 * a 2001 Seattle SuperSonics row, which should look like the Sonics, not
 * the Thunder. Takes a resolved historical logo path (from
 * lib/historicalIdentity.js's resolveHistoricalLogoPath) as a prop rather
 * than resolving it itself, so the expensive logo-index fetch happens once
 * per page load, not once per row.
 *
 * Falls back to the CURRENT logo (not just a text badge) when no
 * historical file matches — most seasons for most teams have no dedicated
 * historical logo, and the current logo is a better default than a plain
 * badge for a team that's simply never rebranded. Only falls all the way
 * through to a text badge if the current logo is missing too.
 */
export default function HistoricalTeamMark({
  logoPath,
  currentLogoTeamId,
  league,
  abbr,
  color,
  size = 28,
}) {
  const [historicalErrored, setHistoricalErrored] = useState(false);
  const [currentErrored, setCurrentErrored] = useState(false);

  const badgeStyle = {
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
  };

  const imgStyle = {
    width: size,
    height: size,
    objectFit: "contain",
    flexShrink: 0,
    display: "block",
    filter: "drop-shadow(0 0 4px rgba(255,255,255,0.95)) drop-shadow(0 0 10px rgba(255,255,255,0.6))",
  };

  if (logoPath && !historicalErrored) {
    return (
      <img
        src={logoPath}
        alt={abbr}
        width={size}
        height={size}
        onError={() => setHistoricalErrored(true)}
        style={imgStyle}
      />
    );
  }

  if (currentLogoTeamId && league && !currentErrored) {
    return (
      <img
        src={`/logos/${league}/${logoFileName(currentLogoTeamId)}.png`}
        alt={abbr}
        width={size}
        height={size}
        onError={() => setCurrentErrored(true)}
        style={imgStyle}
      />
    );
  }

  return <span style={badgeStyle}>{abbr}</span>;
}
