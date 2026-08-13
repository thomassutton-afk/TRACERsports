/**
 * lib/teamColors.js — shared "fill color" resolution for anywhere a team's
 * primary color is used as a solid background/bar/line (Dashboard rankings
 * table, All-Time/Season tables, Team pages, SeasonRatingChart, Teams grid).
 *
 * Several teams' primary is black or near-black (Nets #000000, Aces
 * #010101 after their 2024 rebrand) — unreadable as a solid fill, so those
 * fall back to `tertiary` instead. Originally this was a per-call-site
 * `primary === "#000000"` string check, which is exactly why the Aces slipped
 * through: #010101 isn't literally "#000000" even though it's just as dark.
 * getFillColor() uses perceived luminance instead, so it catches any
 * sufficiently-dark primary without needing to know its exact hex value.
 *
 * Threshold of 10 (0-255 scale) was chosen by checking the darkest
 * non-black primaries actually in use (navy/purple teams like Mavericks
 * #0C2340 ~31, Pacers #1D1160 ~30, Kings #330072 ~28) — all comfortably
 * above 10, so this only catches true black/near-black, not dark colors
 * generally.
 */

const DARK_LUMINANCE_THRESHOLD = 10;

function luminance(hex) {
  if (!hex || hex.length < 7) return 255; // malformed/missing -> treat as "not dark", don't force a fallback
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  if ([r, g, b].some(Number.isNaN)) return 255;
  return 0.299 * r + 0.587 * g + 0.114 * b;
}

// Accepts anything with { primary, tertiary } (a team config entry, or a
// resolved historical identity object) and returns the color to actually
// paint. Falls back to `primary` itself if `tertiary` is missing, same as
// the SeasonRatingChart call sites already did.
export function getFillColor(identity) {
  const primary = identity?.primary;
  if (primary && luminance(primary) < DARK_LUMINANCE_THRESHOLD) {
    return identity.tertiary || primary;
  }
  return primary;
}
