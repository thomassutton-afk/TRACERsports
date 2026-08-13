/**
 * GET /api/logo-index?league=nba
 *
 * Scans public/logos/historical/ for files named `{CODE}_{year}.png` and
 * returns { [CODE]: [year, year, ...] } — the manifest lib/historicalIdentity.js's
 * resolveHistoricalLogoPath() picks the best-matching file from. File-driven
 * on purpose (same as the old site): drop a new logo file in, it shows up,
 * no manifest to hand-edit.
 *
 * League scoping: several abbreviations exist in BOTH NBA and WNBA (DAL,
 * DET, ORL, UTA, WAS, ATL, CHI, IND, MIN, PHX, POR, TOR...), so historical
 * logos are stored per league — public/logos/historical/nba/ and
 * public/logos/historical/wnba/ — rather than flat, to keep those from
 * resolving to the wrong league's team. This route checks the league
 * subfolder first and only falls back to the flat top-level folder if
 * that subfolder doesn't exist, for backward compatibility with anything
 * ever dropped in flat.
 */
import { readdir } from "fs/promises";
import path from "path";

const FILE_PATTERN = /^([A-Za-z0-9]+)_(\d{4})\.png$/i;

async function buildIndexFromDir(dir) {
  let files;
  try {
    files = await readdir(dir);
  } catch {
    return null; // directory doesn't exist
  }

  const index = {};
  for (const file of files) {
    const match = file.match(FILE_PATTERN);
    if (!match) continue;
    const [, code, year] = match;
    (index[code.toUpperCase()] ??= []).push(Number(year));
  }
  return index;
}

export async function GET(request) {
  const { searchParams } = new URL(request.url);
  const league = searchParams.get("league");

  const historicalRoot = path.join(process.cwd(), "public", "logos", "historical");

  let index = null;
  if (league) {
    index = await buildIndexFromDir(path.join(historicalRoot, league));
  }
  if (!index) {
    index = await buildIndexFromDir(historicalRoot);
  }

  return Response.json(index ?? {});
}
