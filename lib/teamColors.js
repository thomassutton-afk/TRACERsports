/**
 * lib/teamColors.js — shared "fill color" and "text color" resolution for
 * anywhere a team's colors are used as a solid background/bar/line, or as
 * text painted on top of one (Dashboard rankings table, All-Time/Season
 * tables, Team pages, Bracket tabs, SeasonRatingChart, Teams grid).
 *
 * Several teams' primary is a "black" swatch (Nets #000000, most teams'
 * #010101 "Black C", and #101820 "Black 6 C" - used by Panthers, Steelers,
 * pre-2002 Bengals, and several teams' 1996-2001 eras) - unreadable as a
 * solid fill, so those fall back to `secondary` instead (or `tertiary` if
 * `secondary` is itself white/near-white, since white-on-page-background
 * has the exact same problem black-on-black did).
 *
 * isBlack() checks against an explicit allowlist of the actual "black" hex
 * values used across the NBA/WNBA/NFL color data, rather than a luminance
 * threshold. A threshold was tried first and doesn't work: Black 6 C
 * (#101820, luminance ~22.5) sits within 1.3 luminance points of the
 * Browns' original brown (#22150C, ~23.9) and within 3.4 of legitimate dark
 * navy (Bears' #091F2C, ~25.9) - brightness alone can't separate "this is
 * black" from "this is a dark brown/navy that happens to be similarly
 * dark." The three hex values below are the actual, complete, discrete set
 * of black swatches used across every league's color data - if TruColor
 * (or a future league) introduces a new distinct black hex, it needs to be
 * added here explicitly, same as the original tertiary-fallback fix in
 * this file replaced a brittle per-call-site "#000000" string check for
 * exactly this reason (the Aces' #010101 slipped through that one).
 *
 * White/near-white secondary uses luminance instead of an allowlist,
 * since white doesn't have brown/navy's close-neighbor collision problem -
 * anything visually indistinguishable from white behaves like white here.
 */

const BLACK_HEXES = new Set(["#000000", "#010101", "#101820"]);
const WHITE_LUMINANCE_THRESHOLD = 250;

function luminance(hex) {
  if (!hex || hex.length < 7) return 255; // malformed/missing -> treat as "not dark", don't force a fallback
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  if ([r, g, b].some(Number.isNaN)) return 255;
  return 0.299 * r + 0.587 * g + 0.114 * b;
}

function isBlack(hex) {
  return !!hex && BLACK_HEXES.has(hex.toUpperCase());
}

function isWhiteish(hex) {
  return !!hex && luminance(hex) >= WHITE_LUMINANCE_THRESHOLD;
}

// Accepts anything with { primary, secondary, tertiary } (a team config
// entry, or a resolved historical identity object) and returns the color
// to actually paint as a solid fill.
export function getFillColor(identity) {
  const { primary, secondary, tertiary } = identity || {};
  if (isBlack(primary)) {
    // secondary is the first fallback, UNLESS it's white/near-white, in
    // which case it has the same "invisible against a light page" problem
    // black did - drop to tertiary (or back to primary as a last resort).
    if (isWhiteish(secondary)) {
      return tertiary || primary;
    }
    return secondary || tertiary || primary;
  }
  return primary;
}

// Companion to getFillColor(): returns the color to paint TEXT that sits on
// top of a getFillColor() background (team name labels, bracket seed text,
// etc). Normally `secondary`, matching every call site's original hardcoded
// behavior - but for black-primary teams, the fill itself becomes
// `secondary` (or `tertiary`), so text falls back to `primary` instead to
// avoid painting text the same color as its own background.
export function getTextColor(identity) {
  const { primary, secondary } = identity || {};
  if (isBlack(primary)) {
    return primary;
  }
  return secondary;
}
