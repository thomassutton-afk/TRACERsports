"use client";

import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Wraps a horizontal row of cards with:
 *  - hidden native scrollbar + snap-scroll (was already CSS-only)
 *  - small, low-contrast circular arrow buttons that appear ONLY on the
 *    side(s) there's actually more content to scroll to, and sit right on
 *    top of the existing fade-edge mask instead of adding a heavier UI
 *    element. Deliberately not always-visible chevrons or a scrollbar
 *    replacement — the fade already signals "more content"; these just
 *    give people a click target instead of requiring a swipe/drag.
 *
 * This needs to be a client component (state + scroll listener + onClick),
 * so it's split out of the server-rendered page.tsx rather than inlined.
 */
export default function GameScrollRow({ children }: { children: React.ReactNode }) {
  const rowRef = useRef<HTMLDivElement>(null);
  const [canScrollLeft, setCanScrollLeft] = useState(false);
  const [canScrollRight, setCanScrollRight] = useState(false);

  const updateArrows = useCallback(() => {
    const el = rowRef.current;
    if (!el) return;
    setCanScrollLeft(el.scrollLeft > 4);
    setCanScrollRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 4);
  }, []);

  useEffect(() => {
    updateArrows();
    const el = rowRef.current;
    if (!el) return;
    el.addEventListener("scroll", updateArrows, { passive: true });
    window.addEventListener("resize", updateArrows);
    return () => {
      el.removeEventListener("scroll", updateArrows);
      window.removeEventListener("resize", updateArrows);
    };
  }, [updateArrows]);

  const scroll = (direction: 1 | -1) => {
    rowRef.current?.scrollBy({ left: direction * 280, behavior: "smooth" });
  };

  const arrowStyle: React.CSSProperties = {
    position: "absolute",
    top: "50%",
    transform: "translateY(-50%)",
    width: 26,
    height: 26,
    borderRadius: "50%",
    border: "1px solid var(--border)",
    background: "var(--surface)",
    color: "var(--text2)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
    fontSize: 13,
    lineHeight: 1,
    fontFamily: "var(--font-mono)",
    boxShadow: "0 1px 4px rgba(0,0,0,0.10)",
    opacity: 0.8,
    zIndex: 2,
    padding: 0,
  };

  return (
    <div style={{ position: "relative" }}>
      <style>{`
        .game-scroll-row {
          scrollbar-width: none;
          -ms-overflow-style: none;
          scroll-snap-type: x proximity;
          scroll-behavior: smooth;
        }
        .game-scroll-row::-webkit-scrollbar {
          display: none;
        }
        .game-scroll-row > * {
          scroll-snap-align: start;
        }
        .game-scroll-arrow:hover {
          opacity: 1 !important;
        }
      `}</style>

      <div
        ref={rowRef}
        className="game-scroll-row"
        style={{
          display: "flex",
          gap: 12,
          overflowX: "auto",
          paddingBottom: 4,
          maskImage:
            "linear-gradient(to right, transparent 0, black 24px, black calc(100% - 24px), transparent 100%)",
          WebkitMaskImage:
            "linear-gradient(to right, transparent 0, black 24px, black calc(100% - 24px), transparent 100%)",
        }}
      >
        {children}
      </div>

      {canScrollLeft && (
        <button
          aria-label="Scroll left"
          onClick={() => scroll(-1)}
          className="game-scroll-arrow"
          style={{ ...arrowStyle, left: -4 }}
        >
          ‹
        </button>
      )}
      {canScrollRight && (
        <button
          aria-label="Scroll right"
          onClick={() => scroll(1)}
          className="game-scroll-arrow"
          style={{ ...arrowStyle, right: -4 }}
        >
          ›
        </button>
      )}
    </div>
  );
}
