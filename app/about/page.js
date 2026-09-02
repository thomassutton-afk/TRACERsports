"use client";

/**
 * app/about/page.js — About / Methodology page.
 *
 * Content ported as-is from reference/old-site/AboutPage.jsx per TJ's
 * call — including the "for the NBA" line in the first section, which is
 * now inaccurate on a multi-sport site (flagged, not silently fixed;
 * tracked as an open item).
 *
 * Structural changes (not content changes):
 *   - Uses the real shared Nav.jsx instead of hand-rolled inline nav markup.
 *   - Uses the new components/Footer.jsx instead of a missing import.
 *   - CTA links point at real routes that exist today (no /all-time or
 *     /team/:abbr yet), and default to NBA as this page is otherwise
 *     league-agnostic.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import Footer from "@/components/Footer";
import { fetchLeagueAccuracy, buildSeasonAccuracy } from "@/lib/gamesData";

function Section({ title, eyebrow, children }) {
  return (
    <div style={S.section}>
      {eyebrow && <div style={S.eyebrow}>{eyebrow}</div>}
      <h2 style={S.sectionHeading}>{title}</h2>
      {children}
    </div>
  );
}

// Live, all-time (every season on record, no date cutoff) accuracy across
// both leagues and both rating variants, plus a Combined row merging NBA
// and WNBA's raw rows together before recomputing (not an average of the
// two percentages, which would over-weight whichever league has fewer
// games) - requested directly to replace the previous hardcoded/static
// "66.8%" copy, which never updated as new games were added.
function useAllTimeAccuracyTable() {
  const [table, setTable] = useState(null); // { NBA: {echo, pulse}, WNBA: {...}, Combined: {...} }
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [nbaEcho, nbaPulse, wnbaEcho, wnbaPulse, nflEcho, nflPulse] = await Promise.all([
        fetchLeagueAccuracy("nba", "echo"),
        fetchLeagueAccuracy("nba", "pulse"),
        fetchLeagueAccuracy("wnba", "echo"),
        fetchLeagueAccuracy("wnba", "pulse"),
        fetchLeagueAccuracy("nfl", "echo"),
        fetchLeagueAccuracy("nfl", "pulse"),
      ]);
      if (cancelled) return;

      setTable({
        NBA: { echo: buildSeasonAccuracy(nbaEcho.rows), pulse: buildSeasonAccuracy(nbaPulse.rows) },
        WNBA: { echo: buildSeasonAccuracy(wnbaEcho.rows), pulse: buildSeasonAccuracy(wnbaPulse.rows) },
        NFL: { echo: buildSeasonAccuracy(nflEcho.rows), pulse: buildSeasonAccuracy(nflPulse.rows) },
        // Combined is intentionally NBA+WNBA only, not +NFL — kept as-is
        // pending a call on whether pooling a different sport's game-level
        // accuracy into one "Combined" number is meaningful. Flagged for
        // TJ, not decided here.
        Combined: {
          echo: buildSeasonAccuracy([...nbaEcho.rows, ...wnbaEcho.rows]),
          pulse: buildSeasonAccuracy([...nbaPulse.rows, ...wnbaPulse.rows]),
        },
      });
      setLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { table, loading };
}

export default function AboutPage() {
  const { table, loading } = useAllTimeAccuracyTable();

  return (
    <div>
      <div className="hero">
        <div>
          <div className="hero-label">Methodology</div>
          <div className="hero-heading">About TRACER</div>
        </div>
      </div>

      <div className="about-wrap">
        <Section title="What is TRACER?">
          <p style={S.body}>
            TRACER is an Elo-based rating system for the NBA, calculating a single number
            for every team after every game, going back to the 1995–96 season. An Elo
            rating is a predictive system that calculates the probability of who will win
            a game based on both teams&apos; current ratings.
          </p>
        </Section>

        <div style={S.divider} />

        <Section title="What's the difference between Pulse and Echo?">
          <p style={S.body}>
            Pulse and Echo ratings are identical in calculation. The only difference is
            how they handle season-to-season carryover. The Pulse rating is an in-season
            snapshot only. Every team begins the season with an identical rating, and only
            the games in that season affect it. The Echo rating never fully resets: teams
            carry forward 60% of their rating gap from average, resetting the rest of the
            way toward a league-average baseline.
          </p>
        </Section>

        <div style={S.divider} />

        <Section title="How are the ratings calculated?">
          <p style={S.body}>
            At its core, it&apos;s a standard Elo logistic model. Before each game, both teams&apos;
            current ratings are converted into a win probability using a logistic curve.
            Every game moves a team&apos;s rating up or down based on the result, how
            surprising it was, and the margin of victory. Other factors also affect the
            size of the change, like home-court advantage, rest, and whether the game went
            to overtime.
          </p>
        </Section>

        <div style={S.divider} />

        <Section title="How accurate is it?">
          <p style={S.body}>
            The table below is computed live, straight off every game on record for each
            league — not a fixed snapshot, so it moves as new games get added. After
            finishing the system, I tested the NBA Echo rating against the now-defunct NBA
            Elo ratings that used to be available on FiveThirtyEight. Echo beat the
            FiveThirtyEight model on accuracy, a result confirmed by significance testing.
          </p>
          {loading ? (
            <div style={S.tableLoading}>Loading live accuracy…</div>
          ) : (
            <>
            <div style={S.tableWrap} className="desktop-only">
              <table style={S.table}>
                <thead>
                  <tr>
                    <th style={S.th("left")}>League</th>
                    <th style={S.th("right")}>Echo Accuracy</th>
                    <th style={S.th("right")}>Echo Brier</th>
                    <th style={S.th("right")}>Pulse Accuracy</th>
                    <th style={S.th("right")}>Pulse Brier</th>
                    <th style={S.th("right")}>Games</th>
                  </tr>
                </thead>
                <tbody>
                  {["NBA", "WNBA", "NFL", "Combined"].map((label) => {
                    const row = table[label];
                    // Combined Brier is deliberately omitted, not just
                    // hidden with CSS - averaging a proper-scoring-rule
                    // metric across two SEPARATELY tuned models (NBA and
                    // WNBA have different engine params) doesn't measure
                    // anything either model actually has. Accuracy % is
                    // fine to combine (it's just "fraction of all games
                    // picked correctly"); Brier isn't, since it's a
                    // calibration measure and pooling two different
                    // models' calibration together isn't a real quantity.
                    const isCombined = label === "Combined";
                    return (
                      <tr key={label} style={isCombined ? S.trTotal : undefined}>
                        <td style={S.td("left")}>{label}</td>
                        <td style={S.td("right")}>{row.echo ? `${row.echo.pct}%` : "—"}</td>
                        <td style={S.td("right")}>{isCombined ? "—" : row.echo?.brier ?? "—"}</td>
                        <td style={S.td("right")}>{row.pulse ? `${row.pulse.pct}%` : "—"}</td>
                        <td style={S.td("right")}>{isCombined ? "—" : row.pulse?.brier ?? "—"}</td>
                        <td style={S.td("right")}>{Number(row.echo?.n ?? 0).toLocaleString()}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile replacement — the desktop table is ~790px wide even
                with overflow-x scroll available, which on a phone shows
                maybe two columns before hitting a wall with no visual hint
                there's more. Only 4 rows exist, so a card each is simpler
                than forcing horizontal scroll on a data table this small. */}
            <div className="mobile-only" style={{ flexDirection: "column", gap: 10, margin: "0.5rem 0 1rem" }}>
              {["NBA", "WNBA", "NFL", "Combined"].map((label) => {
                const row = table[label];
                const isCombined = label === "Combined";
                return (
                  <div
                    key={label}
                    style={{
                      border: "1px solid var(--border)",
                      borderRadius: 10,
                      padding: "12px 14px",
                      background: isCombined ? "var(--surface2)" : "var(--surface)",
                    }}
                  >
                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 700, marginBottom: 8 }}>{label}</div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)", marginBottom: 4 }}>
                      <span>Echo</span>
                      <span>
                        {row.echo ? `${row.echo.pct}%` : "—"}
                        {!isCombined && row.echo?.brier != null ? ` · Brier ${row.echo.brier}` : ""}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text2)", marginBottom: 4 }}>
                      <span>Pulse</span>
                      <span>
                        {row.pulse ? `${row.pulse.pct}%` : "—"}
                        {!isCombined && row.pulse?.brier != null ? ` · Brier ${row.pulse.brier}` : ""}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--text3)" }}>
                      <span>Games</span>
                      <span>{Number(row.echo?.n ?? 0).toLocaleString()}</span>
                    </div>
                  </div>
                );
              })}
            </div>
            </>
          )}
        </Section>

        <div style={S.divider} />

        <Section title="Who makes this?">
          <p style={S.body}>
            TRACER was designed and built by me, TJ Sutton, during the downtime between
            graduation and starting grad school. I graduated from the University of Texas
            with a degree in Sport Management and a minor in sports analytics. The system
            came together as a learn-as-you-go process. I set out to teach myself about
            rating systems, which led me to Elo ratings in sports outside of chess. For the
            first four months, it only lived in Excel spreadsheets on my computer. In May,
            I decided to move it online to share with others. Hope you enjoy!
          </p>
          <p style={S.body}>
            If you have any questions or feedback, you can reach me at{" "}
            <a href="mailto:tracersports4@gmail.com" style={S.link}>
              tracersports4@gmail.com
            </a>
            , or find TRACER on{" "}
            <a href="https://twitter.com/tracersports" style={S.link} target="_blank" rel="noopener noreferrer">
              X
            </a>{" "}
            and{" "}
            <a href="https://instagram.com/tracersports" style={S.link} target="_blank" rel="noopener noreferrer">
              Instagram
            </a>
            .
          </p>
        </Section>

        <div style={S.ctaRow}>
          <Link href="/nba" style={S.ctaPrimary}>
            View current ratings →
          </Link>
          <Link href="/nba/season" style={S.ctaSecondary}>
            Explore season history →
          </Link>
        </div>
      </div>

      <Footer />
    </div>
  );
}

const S = {
  section: { padding: "3rem 0 0" },
  eyebrow: {
    fontFamily: "var(--font-mono)",
    fontSize: 10,
    fontWeight: 500,
    color: "var(--acc)",
    letterSpacing: 2,
    textTransform: "uppercase",
    marginBottom: 8,
  },
  sectionHeading: {
    fontFamily: "var(--font-display)",
    fontSize: 28,
    fontWeight: 900,
    letterSpacing: -0.5,
    color: "var(--text)",
    margin: "0 0 1.25rem",
  },
  body: { fontSize: 15, lineHeight: 1.75, color: "var(--text2)", marginBottom: "1.1rem" },
  divider: { height: 1, background: "var(--border)", marginTop: "2rem" },
  link: { color: "var(--acc)", textDecoration: "underline" },

  tableWrap: { overflowX: "auto", border: "1px solid var(--border)", borderRadius: 12, margin: "0.5rem 0 1rem" },
  table: { width: "100%", borderCollapse: "collapse", background: "var(--surface)" },
  th: (align) => ({
    fontFamily: "var(--font-mono)",
    fontSize: 10,
    fontWeight: 500,
    color: "var(--text3)",
    textTransform: "uppercase",
    letterSpacing: 1,
    padding: "10px 14px",
    textAlign: align,
    whiteSpace: "nowrap",
    borderBottom: "2px solid var(--border)",
  }),
  td: (align) => ({
    fontFamily: "var(--font-mono)",
    fontSize: 13,
    color: "var(--text)",
    padding: "10px 14px",
    textAlign: align,
    whiteSpace: "nowrap",
  }),
  trTotal: { borderTop: "1px solid var(--border)", fontWeight: 700 },
  tableLoading: {
    fontFamily: "var(--font-mono)",
    fontSize: 13,
    color: "var(--text3)",
    padding: "24px 0",
    margin: "0.5rem 0 1rem",
  },

  ctaRow: { display: "flex", gap: 12, marginTop: "3rem", paddingTop: "2rem", borderTop: "1px solid var(--border)" },
  ctaPrimary: {
    fontFamily: "var(--font-mono)",
    fontSize: 13,
    fontWeight: 600,
    padding: "10px 22px",
    borderRadius: 8,
    background: "var(--acc)",
    color: "#fff",
    textDecoration: "none",
  },
  ctaSecondary: {
    fontFamily: "var(--font-mono)",
    fontSize: 13,
    fontWeight: 500,
    padding: "10px 22px",
    borderRadius: 8,
    background: "none",
    border: "1px solid var(--acc)",
    color: "var(--acc)",
    textDecoration: "none",
  },
};
