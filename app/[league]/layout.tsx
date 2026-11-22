import type { Metadata } from "next";
import { getAllLeagueIds, getLeagueConfig } from "@/lib/sports/registry";

// Descriptions for each league. Any league not listed here falls back to
// the generic line further down.
const DESCRIPTIONS: Record<string, string> = {
  nba: "Elo power rankings for every NBA team, updated daily, with win probabilities for upcoming games.",
  wnba: "Elo power rankings for every WNBA team, updated daily, with win probabilities for upcoming games.",
  nfl: "Elo power rankings for every NFL team, updated daily, with win probabilities for upcoming games.",
};

export async function generateMetadata({
  params,
}: {
  params: Promise<{ league: string }>;
}): Promise<Metadata> {
  const { league } = await params;

  // Unknown league (like the old /sitemap.xml mix-up): keep the site default.
  if (!getAllLeagueIds().includes(league)) return {};

  const label = getLeagueConfig(league).label;

  return {
    title: `${label} Power Rankings (Elo) | TRACER Sports`,
    description:
      DESCRIPTIONS[league] ??
      `Elo power rankings for every ${label} team, updated daily.`,
  };
}

export default function LeagueLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return children;
}
