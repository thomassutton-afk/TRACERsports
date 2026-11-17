import type { MetadataRoute } from "next";
import { getAllLeagueIds } from "@/lib/sports/registry";

const BASE = "https://www.tracersports.net";

export default function sitemap(): MetadataRoute.Sitemap {
  const sections = ["", "/season", "/all-time", "/team"];

  const leaguePages = getAllLeagueIds().flatMap((id) =>
    sections.map((section) => ({ url: `${BASE}/${id}${section}` }))
  );

  return [{ url: `${BASE}/` }, { url: `${BASE}/about` }, ...leaguePages];
}