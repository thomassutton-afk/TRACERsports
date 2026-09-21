"""
weekly_risers_card.py — renders an Instagram-ready PNG ranking a week's
biggest Elo risers (this week's winners, ordered by how much their rating
climbed), styled to match social_card.py / the live site's look: cream
background, dashed card border, IBM Plex Mono throughout, purple accent.

Unlike social_card.py (which reads the next slate straight out of the
league db), this one takes a simple pasted list - the same
"Team<TAB>delta" block you'd copy out of the ratings output after Monday
Night Football wraps up a week - so there's nothing to wire into
add_season.py. Call it by hand once a week:

    from weekly_risers_card import generate_weekly_risers_card
    generate_weekly_risers_card(
        league="nfl",
        week=1,
        standings_text='''
            49ers   44.1
            Bears   42.8
            ...
        ''',
    )

Output: social_posts/{league}/week{week}-risers.png at the repo root
(sibling of DBs/, public/, app/), 1080x1080 - same square feed size as
social_card.py's posts, so the two post types sit side by side in the
grid without looking like they're from different accounts.

Requires: Pillow (`pip install pillow`). Reuses social_card.py's color
palette, fonts and brand-logo loader so the two never drift apart -
if you retheme one, retheme both from the same place.
"""
from __future__ import annotations

import colorsys
import re
from pathlib import Path

from PIL import Image, ImageDraw

from social_card import (
    ACC, BG, BORDER2, SURFACE, TEXT, TEXT2, TEXT3, UT, UO,
    CANVAS_SIZE, PAD, _font, _load_brand_logo, _dashed_rounded_rect,
)

OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "social_posts"


def _parse_standings(text: str) -> list[tuple[str, float]]:
    """Parses a pasted "Team<whitespace>delta" block, one per line, in
    the order given (i.e. already ranked - this doesn't re-sort, so a
    pre-sorted paste stays in that order and a re-sort is on the
    caller). Blank lines are skipped so a paste with stray spacing
    still works."""
    rows = []
    for line in text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^(.+?)\s+([+-]?\d+(?:\.\d+)?)$", line)
        if not m:
            raise ValueError(f"Couldn't parse standings line: {line!r}")
        rows.append((m.group(1).strip(), float(m.group(2))))
    return rows


def _riser_color(value: float, lo: float, hi: float) -> tuple[int, int, int]:
    """Same red->green heat mapping as social_card._heat_color, but
    stretched across this week's own min/max rather than a fixed 50-85
    band, since a week's rating gains don't sit on a fixed known scale
    the way a win% does. A flat range would leave every week's bars
    looking identically colored (all-green if gains run 5-45, all-red
    if the scale doesn't match) - always finding the highs and lows in
    what actually happened is what makes the color meaningful here."""
    if hi <= lo:
        t = 1.0
    else:
        t = (value - lo) / (hi - lo)
    hue = max(0.0, min(1.0, t)) * 120  # 0=red .. 120=green
    r, g, b = colorsys.hsv_to_rgb(hue / 360, 0.72, 0.70)
    return (int(r * 255), int(g * 255), int(b * 255))


def generate_weekly_risers_card(
    league: str,
    week: int,
    standings_text: str,
    out_dir: Path | None = None,
) -> Path:
    """Renders and saves one 1080x1080 leaderboard card ranking this
    week's winners by rating gain, most-improved first (the order the
    text block is given in - see _parse_standings).

    Returns the saved path."""
    rows = _parse_standings(standings_text)
    if not rows:
        raise ValueError("No rows to render - standings_text was empty.")

    values = [v for _, v in rows]
    lo, hi = min(values), max(values)
    max_val = max(values)

    img = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), BG)
    draw = ImageDraw.Draw(img)
    cx = CANVAS_SIZE / 2

    # --- top color stripe (brand signature, matches social_card.py) ---
    stripe_h = 8
    third = CANVAS_SIZE / 3
    draw.rectangle((0, 0, third, stripe_h), fill=ACC)
    draw.rectangle((third, 0, 2 * third, stripe_h), fill=UT)
    draw.rectangle((2 * third, 0, CANVAS_SIZE, stripe_h), fill=UO)

    # --- header: brand mark left, context line right ---
    header_inset = 24
    logo_h = 34
    brand_logo = _load_brand_logo(logo_h)
    if brand_logo:
        img.paste(brand_logo, (header_inset, int(32 - logo_h / 2)), brand_logo)
    else:
        dot_r = 6
        dot_cx, dot_cy = header_inset + dot_r, 32
        draw.ellipse((dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r), fill=UT)
        draw.text((dot_cx + dot_r + 8, dot_cy), "TRACER SPORTS", font=_font("Bold", 24), fill=TEXT, anchor="lm")
    header_right = f"{league.upper()} \u00b7 WEEK {week} \u00b7 BIGGEST RISERS"
    draw.text((CANVAS_SIZE - header_inset, 32), header_right, font=_font("SemiBold", 19), fill=ACC, anchor="rm")
    header_h = 60
    footer_h = 30

    # --- outer dashed card, holding the whole ranked list ---
    card_box = (PAD, header_h + 8, CANVAS_SIZE - PAD, CANVAS_SIZE - footer_h - 8)
    _dashed_rounded_rect(draw, card_box, radius=18)
    inner_pad_x, inner_pad_top, inner_pad_bottom = 26, 20, 16
    list_x0 = card_box[0] + inner_pad_x
    list_x1 = card_box[2] - inner_pad_x
    list_y0 = card_box[1] + inner_pad_top
    list_y1 = card_box[3] - inner_pad_bottom

    # column heading row
    rank_col_w = 46
    name_col_w = 150
    value_col_w = 84
    bar_x0 = list_x0 + rank_col_w + name_col_w
    bar_x1 = list_x1 - value_col_w
    bar_max_w = bar_x1 - bar_x0

    heading_font = _font("SemiBold", 15)
    draw.text((list_x0 + rank_col_w, list_y0), "TEAM", font=heading_font, fill=TEXT3, anchor="lm")
    draw.text((bar_x0, list_y0), "RATING GAIN", font=heading_font, fill=TEXT3, anchor="lm")
    heading_h = 30
    draw.line([(list_x0, list_y0 + heading_h - 6), (list_x1, list_y0 + heading_h - 6)], fill=BORDER2, width=2)

    rows_top = list_y0 + heading_h
    n = len(rows)
    row_h = (list_y1 - rows_top) / n
    bar_h = min(28, row_h * 0.5)

    rank_font = _font("SemiBold", 17)
    name_font = _font("Bold", 20)
    value_font = _font("Bold", 18)

    for i, (name, value) in enumerate(rows):
        row_cy = rows_top + row_h * (i + 0.5)

        # rank number
        draw.text((list_x0, row_cy), f"{i + 1}", font=rank_font, fill=TEXT3, anchor="lm")
        # team name
        draw.text((list_x0 + rank_col_w, row_cy), name, font=name_font, fill=TEXT, anchor="lm")

        # bar, scaled against this week's own max so #1 always reads full-width
        bar_w = max(6, bar_max_w * (value / max_val))
        bar_color = _riser_color(value, lo, hi)
        bar_box = (bar_x0, row_cy - bar_h / 2, bar_x0 + bar_w, row_cy + bar_h / 2)
        draw.rounded_rectangle(bar_box, radius=bar_h / 2, fill=bar_color)

        # value, just past the end of its own bar
        value_text = f"+{value:.1f}"
        draw.text((bar_x0 + bar_w + 12, row_cy), value_text, font=value_font, fill=TEXT, anchor="lm")

        # row divider (skip after the last row - the card border closes it)
        if i < n - 1:
            draw.line([(list_x0, rows_top + row_h * (i + 1)), (list_x1, rows_top + row_h * (i + 1))],
                      fill=BORDER2, width=1)

    # --- footer ---
    draw.text((cx, CANVAS_SIZE - footer_h / 2), "tracersports.net", font=_font("Medium", 16), fill=TEXT3, anchor="mm")

    out_dir = out_dir or (OUTPUT_ROOT / league)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"week{week}-risers.png"
    img.save(out_path)
    return out_path
