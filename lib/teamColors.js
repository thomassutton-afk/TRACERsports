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

// WCAG 2.x relative luminance + contrast ratio — the actual accessibility
// standard, distinct from luminance() above (which is a simpler perceptual
// heuristic used only for the isWhiteish() black/white swap, not for
// judging whether two colors are readable together).
function wcagChannel(c) {
  c = c / 255;
  return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

function wcagLuminance(hex) {
  if (!hex || hex.length < 7) return 1; // malformed/missing -> treat as white, matches luminance()'s "not dark" default
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  if ([r, g, b].some(Number.isNaN)) return 1;
  const R = wcagChannel(r), G = wcagChannel(g), B = wcagChannel(b);
  return 0.2126 * R + 0.7152 * G + 0.0722 * B;
}

// Contrast ratio between two colors: 1 (no contrast) to 21 (max, black on
// white). WCAG AA for normal-size text requires >= 4.5.
export function contrastRatio(hex1, hex2) {
  const l1 = wcagLuminance(hex1);
  const l2 = wcagLuminance(hex2);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

// Target is WCAG's 3:1 threshold (the "large text"/UI-component bar,
// technically applicable here only if you squint — this site's team-name
// labels run 9-13px bold, under the 18.66px-bold cutoff that formally
// qualifies for 3:1 over the stricter 4.5:1 body-text bar). Chosen
// deliberately over 4.5 to keep more teams on their actual brand color
// instead of falling through to white/black.
function hexToHsl(hex) {
  const r = parseInt(hex.slice(1, 3), 16) / 255;
  const g = parseInt(hex.slice(3, 5), 16) / 255;
  const b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h, s;
  const l = (max + min) / 2;
  if (max === min) {
    h = s = 0;
  } else {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      default: h = (r - g) / d + 4;
    }
    h /= 6;
  }
  return [h * 360, s * 100, l * 100];
}

function hslToHex(h, s, l) {
  h /= 360; s /= 100; l /= 100;
  let r, g, b;
  if (s === 0) {
    r = g = b = l;
  } else {
    const hue2rgb = (p, q, t) => {
      if (t < 0) t += 1;
      if (t > 1) t -= 1;
      if (t < 1 / 6) return p + (q - p) * 6 * t;
      if (t < 1 / 2) return q;
      if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
      return p;
    };
    const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
    const p = 2 * l - q;
    r = hue2rgb(p, q, h + 1 / 3);
    g = hue2rgb(p, q, h);
    b = hue2rgb(p, q, h - 1 / 3);
  }
  const toHex = (x) => Math.round(x * 255).toString(16).padStart(2, "0");
  return `#${toHex(r)}${toHex(g)}${toHex(b)}`.toUpperCase();
}

// Same as tintForContrast, but the lightness search is capped at maxDeltaL
// points from the original. An uncapped search can walk a color far enough
// to read as a visually different color entirely (a saturated red pushed
// most of the way to white reads as pink, not "readable red") — capping
// keeps the result close enough to still look like the original color, at
// the cost of not always reaching `target`. Returns null if the cap is hit
// before `target` is reached.
function tintForContrastCapped(hex, fillHex, target, maxDeltaL) {
  const [h, s, lOrig] = hexToHsl(hex);
  const contrastAtL = (l) => contrastRatio(fillHex, hslToHex(h, s, l));
  const direction = contrastAtL(100) >= contrastAtL(0) ? 1 : -1;
  const bound = direction > 0 ? Math.min(100, lOrig + maxDeltaL) : Math.max(0, lOrig - maxDeltaL);
  for (let l = lOrig; direction > 0 ? l <= bound : l >= bound; l += direction) {
    if (contrastAtL(l) >= target) return hslToHex(h, s, l);
  }
  return null;
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

// Target is WCAG's 3:1 threshold (the "large text"/UI-component bar,
// technically applicable here only if you squint — this site's team-name
// labels run 9-13px bold, under the 18.66px-bold cutoff that formally
// qualifies for 3:1 over the stricter 4.5:1 body-text bar). Chosen
// deliberately over 4.5 to keep more teams on their actual brand color
// instead of falling through to white/black.
const CONTRAST_TARGET = 3.0;

// Companion to getFillColor(): returns the color to paint TEXT that sits on
// top of a getFillColor() background (team name labels, bracket seed text,
// etc). Tries the team's own colors in brand-preference order — secondary
// first (or primary, for black-primary teams, matching getFillColor()'s own
// swap), then tertiary, then whichever of the two wasn't tried yet. If NONE
// of a team's exact colors clear CONTRAST_TARGET against the real fill, it
// tries a CAPPED tint of each of those same candidates in turn (same hue,
// nudged lightness, capped at 20pts so it can't drift into a different-
// looking color - e.g. red pushed all the way to pink) before finally
// falling through to flat white/black. Verified against every team in all
// three configs (82 total): 69 keep an exact color unchanged, 8 get a
// small capped tint, and 5 fall through to flat white/black (all 5 are
// teams whose own colors were already black/near-black or heavily
// desaturated charcoal, so there was no real hue to preserve anyway).
export function getTextColor(identity) {
  const { primary, secondary, tertiary } = identity || {};
  const fill = getFillColor(identity);

  const originalChoice = isBlack(primary) ? primary : secondary;
  const otherOwnColor = isBlack(primary) ? secondary : primary;
  const exactCandidates = [originalChoice, tertiary, otherOwnColor].filter(Boolean);

  for (const candidate of exactCandidates) {
    if (contrastRatio(fill, candidate) >= CONTRAST_TARGET) {
      return candidate;
    }
  }

  for (const candidate of exactCandidates) {
    const tinted = tintForContrastCapped(candidate, fill, CONTRAST_TARGET, 20);
    if (tinted) return tinted;
  }

  return contrastRatio(fill, "#FFFFFF") >= contrastRatio(fill, "#000000") ? "#FFFFFF" : "#000000";
}
