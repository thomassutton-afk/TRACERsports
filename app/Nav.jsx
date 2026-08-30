"use client";

/**
 * Shared site nav — brand mark, page links, league switcher, and Echo/Pulse
 * variant toggle. All shared chrome lives in the URL (league as a path
 * segment, variant as a ?variant= search param) so any page can read the
 * current selection without needing a separate state-management layer.
 *
 * Dashboard/Season/All-Time/Teams are league-aware (built from
 * currentLeague, so they follow whichever league is active); About is
 * league-agnostic.
 *
 * Mobile (<=768px): nav-links / nav-right are hidden via CSS and replaced
 * by a hamburger button that toggles a dropdown drawer containing the same
 * links, variant toggle, and league select, stacked for touch. Desktop is
 * unaffected — the drawer only ever renders because the hamburger (the only
 * way to set menuOpen true) is itself hidden above the breakpoint.
 */

import { useState } from "react";
import Link from "next/link";
import { usePathname, useSearchParams, useRouter } from "next/navigation";
import { SPORTS, getAllLeagueIds, getLeagueConfig } from "@/lib/sports/registry";

const VARIANTS = [
  { id: "echo", label: "Echo" },
  { id: "pulse", label: "Pulse" },
];

export default function Nav() {
  const [menuOpen, setMenuOpen] = useState(false);
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const router = useRouter();
  const currentLeague = pathname.split("/")[1]; // "" | "nba" | "wnba" | "about" | ...
  const currentVariant = searchParams.get("variant") || "echo";
  const leagueIds = getAllLeagueIds();

  // Dashboard/Season links need *some* league to point at even when the
  // current route isn't a league route (homepage, About) — falls back to
  // the first registered league rather than hardcoding "nba", so this
  // still makes sense if the registry's league order ever changes.
  const navLeague = leagueIds.includes(currentLeague) ? currentLeague : leagueIds[0];
  const onSeasonPage = pathname.endsWith("/season");
  const onAllTimePage = pathname.endsWith("/all-time");
  const onTeamPage = pathname.endsWith("/team") || pathname.includes("/team/");
  const onDashboard = leagueIds.includes(currentLeague) && !onSeasonPage && !onAllTimePage && !onTeamPage;

  // Which page "type" (Dashboard/Season/All-Time/Team) the sport dropdown
  // should preserve when switching leagues — e.g. picking WNBA while on
  // /nba/all-time should land on /wnba/all-time, not reset to Dashboard.
  // A specific team ID (/nba/team/BOS) doesn't carry over since the same
  // ID rarely means anything in another league, so that case just lands
  // on the new league's team list (/wnba/team) instead.
  const currentSection = onSeasonPage ? "/season" : onAllTimePage ? "/all-time" : onTeamPage ? "/team" : "";

  function goToLeague(newLeagueId) {
    router.push(`/${newLeagueId}${currentSection}?variant=${currentVariant}`);
  }

  return (
    <>
      <nav className="nav">
        <Link href="/" className="nav-brand">
          <span className="brand-dot" />
          <span>
            <span style={{ color: "#663399" }}>TR</span>
            <span style={{ color: "#BF5700" }}>AC</span>
            <span style={{ color: "#154733" }}>ER</span>
          </span>
        </Link>

        <div className="nav-links">
          <Link
            href={`/${navLeague}?variant=${currentVariant}`}
            className={`nav-link${onDashboard ? " active" : ""}`}
          >
            Dashboard
          </Link>
          <Link
            href={`/${navLeague}/season?variant=${currentVariant}`}
            className={`nav-link${onSeasonPage ? " active" : ""}`}
          >
            Season
          </Link>
          <Link
            href={`/${navLeague}/all-time?variant=${currentVariant}`}
            className={`nav-link${onAllTimePage ? " active" : ""}`}
          >
            All-Time
          </Link>
          <Link
            href={`/${navLeague}/team?variant=${currentVariant}`}
            className={`nav-link${onTeamPage ? " active" : ""}`}
          >
            Teams
          </Link>
          <Link
            href="/about"
            className={`nav-link${pathname === "/about" ? " active" : ""}`}
          >
            About
          </Link>
        </div>

        <div className="nav-right">
          <div className="variant-toggle">
            {VARIANTS.map((v) => (
              <Link
                key={v.id}
                href={`${pathname}?variant=${v.id}`}
                className={`vt-btn${currentVariant === v.id ? " active" : ""}`}
              >
                {v.label}
              </Link>
            ))}
          </div>
          <select
            value={currentLeague && leagueIds.includes(currentLeague) ? currentLeague : navLeague}
            onChange={(e) => goToLeague(e.target.value)}
            className="league-select"
            aria-label="Switch league"
          >
            {Object.values(SPORTS).map((sport) => (
              <optgroup key={sport.id} label={sport.label}>
                {sport.leagues.map((id) => (
                  <option key={id} value={id}>
                    {getLeagueConfig(id).label}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
        </div>

        <button
          type="button"
          className={`nav-hamburger${menuOpen ? " open" : ""}`}
          onClick={() => setMenuOpen((open) => !open)}
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          aria-expanded={menuOpen}
        >
          <span />
          <span />
          <span />
        </button>
      </nav>

      {menuOpen && (
        <div className="mobile-drawer">
          <div className="mobile-drawer-links">
            <Link
              href={`/${navLeague}?variant=${currentVariant}`}
              className={`mobile-drawer-link${onDashboard ? " active" : ""}`}
              onClick={() => setMenuOpen(false)}
            >
              Dashboard
            </Link>
            <Link
              href={`/${navLeague}/season?variant=${currentVariant}`}
              className={`mobile-drawer-link${onSeasonPage ? " active" : ""}`}
              onClick={() => setMenuOpen(false)}
            >
              Season
            </Link>
            <Link
              href={`/${navLeague}/all-time?variant=${currentVariant}`}
              className={`mobile-drawer-link${onAllTimePage ? " active" : ""}`}
              onClick={() => setMenuOpen(false)}
            >
              All-Time
            </Link>
            <Link
              href={`/${navLeague}/team?variant=${currentVariant}`}
              className={`mobile-drawer-link${onTeamPage ? " active" : ""}`}
              onClick={() => setMenuOpen(false)}
            >
              Teams
            </Link>
            <Link
              href="/about"
              className={`mobile-drawer-link${pathname === "/about" ? " active" : ""}`}
              onClick={() => setMenuOpen(false)}
            >
              About
            </Link>
          </div>

          <div className="mobile-drawer-divider" />

          <div className="mobile-drawer-controls">
            <div className="variant-toggle">
              {VARIANTS.map((v) => (
                <Link
                  key={v.id}
                  href={`${pathname}?variant=${v.id}`}
                  className={`vt-btn${currentVariant === v.id ? " active" : ""}`}
                  onClick={() => setMenuOpen(false)}
                >
                  {v.label}
                </Link>
              ))}
            </div>
            <select
              value={currentLeague && leagueIds.includes(currentLeague) ? currentLeague : navLeague}
              onChange={(e) => {
                goToLeague(e.target.value);
                setMenuOpen(false);
              }}
              className="league-select"
              aria-label="Switch league"
            >
              {Object.values(SPORTS).map((sport) => (
                <optgroup key={sport.id} label={sport.label}>
                  {sport.leagues.map((id) => (
                    <option key={id} value={id}>
                      {getLeagueConfig(id).label}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
          </div>
        </div>
      )}

      <div className="color-stripe">
        <div className="stripe-acc" />
        <div className="stripe-ut" />
        <div className="stripe-uo" />
      </div>
    </>
  );
}
