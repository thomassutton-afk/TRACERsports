"use client";

/**
 * AllTimeChart.jsx — franchise rating history line chart.
 *
 * Ported from reference/old-site/TeamPage.jsx's AllTimeChart. Logic is
 * unchanged (season-banded hover, peak/trough markers, 1500 baseline);
 * only the styling was touched — hardcoded hex colors swapped for the
 * site's CSS variables so it matches the rest of the app's theme instead
 * of the old site's cream/parchment palette.
 */

import { useState } from "react";

export default function AllTimeChart({ points, color, seasonLabel, width = 960, height = 340 }) {
  const [hover, setHover] = useState(null);

  if (!points || points.length < 2) {
    return (
      <div
        style={{
          height,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "var(--text3)",
          fontSize: 13,
          fontFamily: "var(--font-mono)",
        }}
      >
        No chart data available
      </div>
    );
  }

  const ratings = points.map((p) => p.rating);
  const dates = points.map((p) => p.date);
  const minR = Math.min(...ratings) - 20;
  const maxR = Math.max(...ratings) + 20;
  const minD = Math.min(...dates);
  const maxD = Math.max(...dates);
  const pad = { top: 20, right: 24, bottom: 36, left: 56 };
  const W = width - pad.left - pad.right;
  const H = height - pad.top - pad.bottom;

  const xS = (d) => ((d - minD) / (maxD - minD || 1)) * W;
  const yS = (r) => H - ((r - minR) / (maxR - minR || 1)) * H;

  const rawStep = (maxR - minR) / 5;
  const step = Math.ceil(rawStep / 10) * 10 || 10;
  const yTicks = [];
  for (let v = Math.ceil(minR / step) * step; v <= maxR; v += step) yTicks.push(v);

  const firstSeason = points.reduce((min, p) => Math.min(min, p.season), Infinity);
  const lastSeason = points.reduce((max, p) => Math.max(max, p.season), -Infinity);
  const seasonTicks = [];
  const seenSeason = new Set();
  [...points]
    .sort((a, b) => a.date - b.date)
    .forEach((p) => {
      if (!seenSeason.has(p.season)) {
        seenSeason.add(p.season);
        if ((p.season - firstSeason) % 5 === 0 || p.season === lastSeason) {
          seasonTicks.push({ d: p.date, label: String(p.season) });
        }
      }
    });

  const sortedPts = [...points].sort((a, b) => a.date - b.date);
  const polylineStr = sortedPts.map((p) => `${pad.left + xS(p.date)},${pad.top + yS(p.rating)}`).join(" ");

  const areaStr =
    `${pad.left + xS(minD)},${pad.top + H} ` +
    sortedPts.map((p) => `${pad.left + xS(p.date)},${pad.top + yS(p.rating)}`).join(" ") +
    ` ${pad.left + xS(maxD)},${pad.top + H}`;

  const firstBySeason = {};
  sortedPts.forEach((p) => {
    if (!firstBySeason[p.season]) firstBySeason[p.season] = p.date;
  });
  const seasonBoundaries = Object.values(firstBySeason);

  const peak = sortedPts.reduce((a, b) => (b.rating > a.rating ? b : a), sortedPts[0]);
  const trough = sortedPts.reduce((a, b) => (b.rating < a.rating ? b : a), sortedPts[0]);

  const seasonList = [...new Set(sortedPts.map((p) => p.season))].sort((a, b) => a - b);
  const seasonSummaries = seasonList.map((season, i) => {
    const seasonPts = sortedPts.filter((p) => p.season === season);
    const endPoint = seasonPts[seasonPts.length - 1];
    return {
      season,
      bandStart: firstBySeason[season],
      bandEnd: i < seasonList.length - 1 ? firstBySeason[seasonList[i + 1]] : maxD + 1,
      endPoint,
    };
  });

  function seasonAt(svgX) {
    const targetDate = minD + ((svgX - pad.left) / (W || 1)) * (maxD - minD);
    return (
      seasonSummaries.find((s) => targetDate >= s.bandStart && targetDate < s.bandEnd) ||
      seasonSummaries[seasonSummaries.length - 1]
    );
  }

  function handleMove(e) {
    const svgEl = e.currentTarget.ownerSVGElement || e.currentTarget;
    const rect = svgEl.getBoundingClientRect();
    const fracX = (e.clientX - rect.left) / rect.width;
    const svgX = fracX * width;
    const s = seasonAt(svgX);
    setHover({
      point: s.endPoint,
      x: pad.left + xS(s.endPoint.date),
      y: pad.top + yS(s.endPoint.rating),
      bandStart: pad.left + xS(s.bandStart),
      bandEnd: pad.left + xS(Math.min(s.bandEnd, maxD)),
    });
  }

  return (
    <svg width="100%" viewBox={`0 0 ${width} ${height}`} style={{ overflow: "visible" }} role="img" aria-label="All-time rating chart">
      <defs>
        <linearGradient id="atc-area-grad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.18} />
          <stop offset="100%" stopColor={color} stopOpacity={0.01} />
        </linearGradient>
      </defs>

      {seasonBoundaries.map((d, i) => (
        <line key={i} x1={pad.left + xS(d)} y1={pad.top} x2={pad.left + xS(d)} y2={pad.top + H} stroke="var(--border)" strokeWidth={1} strokeDasharray="2,4" />
      ))}

      {yTicks.map((v) => (
        <g key={v}>
          <line x1={pad.left} y1={pad.top + yS(v)} x2={pad.left + W} y2={pad.top + yS(v)} stroke="var(--border)" strokeWidth={1} />
          <text x={pad.left - 8} y={pad.top + yS(v) + 4} textAnchor="end" fontSize={9} fill="var(--text3)" fontFamily="var(--font-mono)">
            {v.toFixed(0)}
          </text>
        </g>
      ))}

      {1500 >= minR && 1500 <= maxR && (
        <line x1={pad.left} y1={pad.top + yS(1500)} x2={pad.left + W} y2={pad.top + yS(1500)} stroke="var(--border2)" strokeWidth={1.5} strokeDasharray="6,3" opacity={0.6} />
      )}

      {seasonTicks.map(({ d, label }) => (
        <text key={label} x={pad.left + xS(d)} y={pad.top + H + 20} textAnchor="middle" fontSize={9} fill="var(--text3)" fontFamily="var(--font-mono)">
          {label}
        </text>
      ))}

      <polygon points={areaStr} fill="url(#atc-area-grad)" />
      <polyline points={polylineStr} fill="none" stroke={color} strokeWidth={2.5} strokeLinejoin="round" strokeLinecap="round" />

      <circle cx={pad.left + xS(peak.date)} cy={pad.top + yS(peak.rating)} r={4} fill={color} stroke="var(--surface)" strokeWidth={2} />
      <text x={pad.left + xS(peak.date)} y={pad.top + yS(peak.rating) - 10} textAnchor="middle" fontSize={9} fill={color} fontFamily="var(--font-mono)" fontWeight="700">
        {peak.rating.toFixed(0)}
      </text>

      {peak.rating - trough.rating > 30 && (
        <>
          <circle cx={pad.left + xS(trough.date)} cy={pad.top + yS(trough.rating)} r={3} fill="var(--border2)" stroke="var(--surface)" strokeWidth={1.5} />
          <text x={pad.left + xS(trough.date)} y={pad.top + yS(trough.rating) + 16} textAnchor="middle" fontSize={9} fill="var(--text3)" fontFamily="var(--font-mono)">
            {trough.rating.toFixed(0)}
          </text>
        </>
      )}

      {hover && (
        <g style={{ pointerEvents: "none" }}>
          <rect x={hover.bandStart} y={pad.top} width={Math.max(0, hover.bandEnd - hover.bandStart)} height={H} fill={color} opacity={0.05} />
          <line x1={hover.x} y1={pad.top} x2={hover.x} y2={pad.top + H} stroke={color} strokeWidth={1} strokeDasharray="3,3" opacity={0.5} />
          <circle cx={hover.x} cy={hover.y} r={5} fill={color} stroke="var(--surface)" strokeWidth={2} />
          {(() => {
            const boxW = 108;
            const boxH = 46;
            const flip = hover.x + 14 + boxW > pad.left + W;
            const boxX = flip ? hover.x - 14 - boxW : hover.x + 14;
            const boxY = Math.max(pad.top, Math.min(hover.y - boxH / 2, pad.top + H - boxH));
            return (
              <g>
                <rect x={boxX} y={boxY} width={boxW} height={boxH} rx={6} fill="var(--surface)" stroke="var(--border)" strokeWidth={1} style={{ filter: "drop-shadow(0 2px 6px rgba(0,0,0,0.25))" }} />
                <text x={boxX + 10} y={boxY + 17} fontSize={11} fontWeight="700" fill="var(--text)" fontFamily="var(--font-mono)">
                  {seasonLabel(hover.point.season)}
                </text>
                <text x={boxX + 10} y={boxY + 31} fontSize={10} fill="var(--text3)" fontFamily="var(--font-mono)">
                  {new Date(hover.point.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })} · Final
                </text>
                <text x={boxX + 10} y={boxY + 42} fontSize={12} fontWeight="700" fill={color} fontFamily="var(--font-mono)">
                  {hover.point.rating.toFixed(1)}
                </text>
              </g>
            );
          })()}
        </g>
      )}

      <rect x={pad.left} y={pad.top} width={W} height={H} fill="transparent" onMouseMove={handleMove} onMouseLeave={() => setHover(null)} style={{ cursor: "crosshair" }} />
    </svg>
  );
}
