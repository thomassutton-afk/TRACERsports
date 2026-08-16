"""
social_card.py — renders an Instagram-ready PNG of Elo's picks for the
next upcoming slate, styled to match the live site's Games panel
(app/[league]/GamesPanel.jsx: cream background, dashed "upcoming" card,
IBM Plex Mono throughout, purple accent).

Shared by DBs/nba/add_season.py and DBs/wnba/add_season.py - each just
calls generate_next_slate_card(conn, league) once, after that variant's
ratings/predictions are rebuilt for "echo" (the card always uses Echo,
the site's default variant, regardless of which variant loop is
currently running - see the call site in add_season.py for why that's
safe to do unconditionally).

Output: social_posts/{league}/{date}.png at the repo root (sibling of
DBs/, public/, app/) - 1080x1080, the standard Instagram square feed
size. That folder is plain files, so it rides along with the normal
`git add . && git commit && git push` step at the end of the daily
routine - no separate backup step needed.

Requires: Pillow (`pip install pillow`). Everything else (fonts, team
logos) is read from inside this repo, so there's nothing else to
install.
"""
from __future__ import annotations

import colorsys
import sqlite3
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageEnhance

from export_to_supabase import resolve_current_codes

CANVAS_SIZE = 1080  # Instagram square feed post
PAD = 56
MAX_GAMES_SHOWN = 8  # beyond this, extras are summarized in the footer line

# A few team codes collide with reserved Windows device names (CON, PRN,
# AUX, NUL, COM1-9, LPT1-9), so the logo file can't be saved with that
# exact name - same problem, same fix (trailing underscore) as
# app/[league]/TeamMark.jsx's own FILENAME_OVERRIDES. Keep these two in
# sync if a new colliding code ever comes up.
FILENAME_OVERRIDES = {
    "CON": "CON_",  # WNBA Connecticut Sun
}

FONT_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
LOGO_PATH = Path(__file__).resolve().parent / "assets" / "tracer_logo.png"
LOGO_ROOT = Path(__file__).resolve().parent.parent / "public" / "logos"
OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "social_posts"

# Ported 1:1 from app/globals.css :root
BG = "#F5F0E8"
SURFACE = "#FDFAF5"
BORDER2 = (0, 0, 0, 46)   # rgba(0,0,0,0.18) - a touch darker than the
                          # site's 0.15 so the dashed outline still
                          # reads clearly at Instagram's smaller preview size
TEXT = "#1A1816"
TEXT2 = "#5C5650"
TEXT3 = "#9A9490"
ACC = "#663399"
ACC_DIM = (102, 51, 153, 31)  # rgba(102,51,153,0.12), the site's --acc-dim
UT = "#BF5700"
UO = "#154733"
# ACC blended ~22% over BG, precomputed to a flat color - used as a solid
# "spotlight" tint behind the picked team's logo. Flat color instead of
# true RGBA alpha since everything else on this canvas is drawn opaque.
HALO = (214, 198, 215)

_FONT_CACHE: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def _font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    key = (weight, size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(str(FONT_DIR / f"IBMPlexMono-{weight}.ttf"), size)
    return _FONT_CACHE[key]


def _next_slate(conn: sqlite3.Connection) -> tuple[date, list[dict]] | None:
    """Soonest date in `schedule` with at least one unplayed game and a
    saved Echo prediction. `schedule` only ever holds unplayed games
    (prune_played_schedule_rows() clears entries the moment they're
    scored - see add_season.py), so the minimum date here is always
    exactly "the next slate with games left to play", matching what
    the site's GamesPanel would show if you opened it right now."""
    row = conn.execute("SELECT MIN(date) FROM schedule").fetchone()
    if not row or not row[0]:
        return None
    next_date = row[0]
    cur = conn.execute(
        "SELECT s.home_team, s.away_team, p.expected_win_home "
        "FROM schedule s LEFT JOIN schedule_predictions p "
        "ON p.schedule_id = s.schedule_id AND p.variant = 'echo' "
        "WHERE s.date = ? ORDER BY s.schedule_id",
        (next_date,),
    )
    cols = [d[0] for d in cur.description]
    games = [dict(zip(cols, r)) for r in cur.fetchall()]
    return date.fromisoformat(next_date), games


def _load_logo(league: str, code: str, size: int) -> Image.Image | None:
    filename = FILENAME_OVERRIDES.get(code, code)
    path = LOGO_ROOT / league / f"{filename}.png"
    if not path.exists():
        return None
    img = Image.open(path).convert("RGBA")
    img.thumbnail((size, size), Image.LANCZOS)
    return img


def _triangle(draw: ImageDraw.ImageDraw, cx: float, cy: float, size: int, direction: str, fill: str) -> None:
    """Small filled triangle standing in for the site's \u25c0/\u25b6 pick-arrow -
    IBM Plex Mono doesn't include those glyphs, so a font render leaves a
    blank box instead of an arrow."""
    h, w = size, size * 0.8
    if direction == "left":
        pts = [(cx + w / 2, cy - h / 2), (cx + w / 2, cy + h / 2), (cx - w / 2, cy)]
    else:
        pts = [(cx - w / 2, cy - h / 2), (cx - w / 2, cy + h / 2), (cx + w / 2, cy)]
    draw.polygon(pts, fill=fill)


def _draw_placeholder_mark(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, code: str) -> None:
    """Used only if a team code has no logo file yet (e.g. a brand-new
    expansion team whose art hasn't been added to public/logos/ - see
    the WNBA config's own note about 2026 expansion teams). A plain
    circle with the team code beats leaving a blank hole in the post."""
    r = size / 2
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=SURFACE, outline=BORDER2, width=2)
    f = _font("SemiBold", int(size * 0.32))
    draw.text((cx, cy), code, font=f, fill=TEXT2, anchor="mm")


def _heat_color(pct: float) -> tuple[int, int, int]:
    """Maps pick confidence to a red -> green scale, read as a risk cue
    (red=toss-up, green=safe) rather than a temperature scale. Stretched
    across 50-85% rather than 50-100%, since picks rarely land above
    ~85% - stretching keeps the range you actually see spread out
    instead of everything landing red/orange."""
    pct = max(50.0, min(85.0, pct))
    t = (pct - 50) / 35
    hue = t * 120  # 0=red .. 120=green
    r, g, b = colorsys.hsv_to_rgb(hue / 360, 0.78, 0.72)
    return (int(r * 255), int(g * 255), int(b * 255))


_brand_logo_cache: dict = {}


def _load_brand_logo(target_h: int) -> Image.Image | None:
    """Loads assets/tracer_logo.png once and caches it resized to the
    requested header height, preserving aspect ratio. Returns None if
    the file isn't present, so callers can fall back gracefully."""
    key = target_h
    if key in _brand_logo_cache:
        return _brand_logo_cache[key]
    if not LOGO_PATH.exists():
        _brand_logo_cache[key] = None
        return None
    logo = Image.open(LOGO_PATH).convert("RGBA")
    scale = target_h / logo.height
    resized = logo.resize((max(1, int(logo.width * scale)), target_h), Image.LANCZOS)
    _brand_logo_cache[key] = resized
    return resized


def _mute_logo(img: Image.Image) -> Image.Image:
    """Fades the non-picked team's logo (desaturate + lower alpha) so the
    eye is pulled to the picked team's logo without having to read any
    text - the pick should be visible at a glance, not just legible."""
    muted = ImageEnhance.Color(img).enhance(0.12)
    muted = ImageEnhance.Brightness(muted).enhance(1.06)
    r, g, b, a = muted.split()
    a = a.point(lambda v: int(v * 0.5))
    muted.putalpha(a)
    return muted


def _dashed_rounded_rect(draw: ImageDraw.ImageDraw, box, radius: int) -> None:
    """Solid rounded-rect fill (card background), then a dashed outline
    on top - mirrors the site's `border: 1px dashed var(--border2)` on
    upcoming-game cards. Pillow has no native dashed outline, so the
    straight edges are dashed by hand; the four rounded corners are
    left solid (matching how CSS dashed borders render at a radius)."""
    x0, y0, x1, y1 = box
    draw.rounded_rectangle(box, radius=radius, fill=SURFACE)
    # corners (solid)
    draw.arc((x0, y0, x0 + 2 * radius, y0 + 2 * radius), 180, 270, fill=BORDER2, width=2)
    draw.arc((x1 - 2 * radius, y0, x1, y0 + 2 * radius), 270, 360, fill=BORDER2, width=2)
    draw.arc((x0, y1 - 2 * radius, x0 + 2 * radius, y1), 90, 180, fill=BORDER2, width=2)
    draw.arc((x1 - 2 * radius, y1 - 2 * radius, x1, y1), 0, 90, fill=BORDER2, width=2)
    dash, gap = 7, 5
    for x in range(int(x0 + radius), int(x1 - radius), dash + gap):
        draw.line([(x, y0), (min(x + dash, x1 - radius), y0)], fill=BORDER2, width=2)
        draw.line([(x, y1), (min(x + dash, x1 - radius), y1)], fill=BORDER2, width=2)
    for y in range(int(y0 + radius), int(y1 - radius), dash + gap):
        draw.line([(x0, y), (x0, min(y + dash, y1 - radius))], fill=BORDER2, width=2)
        draw.line([(x1, y), (x1, min(y + dash, y1 - radius))], fill=BORDER2, width=2)


def generate_next_slate_card(conn: sqlite3.Connection, league: str) -> Path | None:
    """Render and save the card for whichever slate is soonest in
    `schedule`. Returns the saved path, or None if there's nothing
    upcoming to show (e.g. the offseason) - callers should treat None
    as "nothing to post today", not an error."""
    slate = _next_slate(conn)
    if slate is None:
        return None
    slate_date, all_games = slate
    games = [g for g in all_games if g["expected_win_home"] is not None]
    if not games:
        return None
    extra = max(0, len(games) - MAX_GAMES_SHOWN)
    games = games[:MAX_GAMES_SHOWN]

    # schedule.home_team/away_team hold the opaque internal team_id
    # (e.g. "wnba_0005"), not the short code shown on-site (e.g. "NYL") -
    # same translation export_to_supabase.py does before anything is
    # ever shown to a user, reused here rather than reimplemented.
    id_to_code = resolve_current_codes(conn)
    for g in games:
        g["away_code"] = id_to_code.get(g["away_team"], (g["away_team"], None))[0]
        g["home_code"] = id_to_code.get(g["home_team"], (g["home_team"], None))[0]

    img = Image.new("RGB", (CANVAS_SIZE, CANVAS_SIZE), BG)
    draw = ImageDraw.Draw(img)
    cx = CANVAS_SIZE / 2

    # --- top color stripe, matching the site's own .color-stripe (3 equal
    # thirds: acc/ut/uo) - a small brand-recognition anchor so the post
    # reads as TRACER at a glance even cropped to a feed thumbnail ---
    stripe_h = 8
    third = CANVAS_SIZE / 3
    draw.rectangle((0, 0, third, stripe_h), fill=ACC)
    draw.rectangle((third, 0, 2 * third, stripe_h), fill=UT)
    draw.rectangle((2 * third, 0, CANVAS_SIZE, stripe_h), fill=UO)

    # --- header: kept as compact as possible (one brand line + one
    # context line) so almost the entire canvas goes to the logos below ---
    header_inset = 24
    logo_h = 34
    brand_logo = _load_brand_logo(logo_h)
    if brand_logo:
        logo_y = int(32 - logo_h / 2)
        img.paste(brand_logo, (header_inset, logo_y), brand_logo)
    else:
        # Fallback if the logo asset is missing - dot + wordmark text
        dot_r = 6
        dot_cx, dot_cy = header_inset + dot_r, 32
        draw.ellipse((dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r), fill=UT)
        draw.text((dot_cx + dot_r + 8, dot_cy), "TRACER SPORTS", font=_font("Bold", 24), fill=TEXT, anchor="lm")
    header_right = (f"{league.upper()} \u00b7 ELO'S PICKS \u00b7 "
                     f"{slate_date.strftime('%a %b').upper()} {slate_date.day}")
    draw.text((CANVAS_SIZE - header_inset, 32), header_right, font=_font("SemiBold", 19), fill=ACC, anchor="rm")
    header_h = 60

    footer_h = 30
    rows_top, rows_bottom = header_h, CANVAS_SIZE - footer_h
    n = len(games)
    row_h = (rows_bottom - rows_top) / n
    half_w = CANVAS_SIZE / 2

    # Logos are sized off the row/half geometry itself - not a fixed px
    # value - so they dominate the row (~85-90% of its height) instead of
    # floating in it. Everything else (labels, badge) is layered on top
    # of/around the logo rather than pushed into its own reserved band.
    logo_size = int(min(row_h * 0.75, half_w * 0.61))
    ring_r = logo_size / 2 + 14
    badge_r = max(30, int(logo_size * 0.15))
    team_font = _font("Bold", 22)
    badge_font = _font("Bold", 22)

    for i, g in enumerate(games):
        row_y0 = rows_top + i * row_h
        row_y1 = row_y0 + row_h
        row_cy = (row_y0 + row_y1) / 2
        away_x, home_x = half_w / 2, half_w + half_w / 2

        home_prob = g["expected_win_home"]
        home_fav = home_prob >= 0.5
        pct = round((home_prob if home_fav else 1 - home_prob) * 100)

        # Pick cue is color contrast only now: picked logo stays full
        # color, the other is muted - no ring/halo shape behind it.
        pick_x = home_x if home_fav else away_x

        away_logo = _load_logo(league, g["away_code"], logo_size)
        home_logo = _load_logo(league, g["home_code"], logo_size)
        if not home_fav and away_logo:
            pass  # away is the pick, drawn full-color below
        elif away_logo:
            away_logo = _mute_logo(away_logo)
        if home_fav and home_logo:
            pass  # home is the pick, drawn full-color below
        elif home_logo:
            home_logo = _mute_logo(home_logo)

        if away_logo:
            img.paste(away_logo, (int(away_x - away_logo.width / 2), int(row_cy - away_logo.height / 2)), away_logo)
        else:
            _draw_placeholder_mark(draw, int(away_x), int(row_cy), logo_size, g["away_code"])
        if home_logo:
            img.paste(home_logo, (int(home_x - home_logo.width / 2), int(row_cy - home_logo.height / 2)), home_logo)
        else:
            _draw_placeholder_mark(draw, int(home_x), int(row_cy), logo_size, g["home_code"])

        # Team code, small, tucked at the top of each half
        draw.text((away_x, row_y0 + 22), g["away_code"], font=team_font, fill=TEXT, anchor="mm")
        draw.text((home_x, row_y0 + 22), g["home_code"], font=team_font, fill=TEXT, anchor="mm")

        # Percentage badge: solid circle pinned just outside the picked
        # logo's ring - anchored to ring_r itself (not a fraction of it)
        # so it sits past the logo artwork regardless of logo size,
        # instead of drifting back onto the logo/wordmark when scaled.
        badge_cx = pick_x + ring_r * 0.90
        badge_cy = row_cy + ring_r * 0.90
        draw.ellipse((badge_cx - badge_r, badge_cy - badge_r, badge_cx + badge_r, badge_cy + badge_r),
                     fill=_heat_color(pct), outline=BG, width=4)
        draw.text((badge_cx, badge_cy), f"{pct}%", font=badge_font, fill="#FFFFFF", anchor="mm")

        # Thin divider between rows and down the middle (no gap - the
        # rows themselves tile edge to edge)
        if i > 0:
            draw.line([(0, row_y0), (CANVAS_SIZE, row_y0)], fill=BORDER2, width=2)
        draw.line([(half_w, row_y0 + 10), (half_w, row_y1 - 10)], fill=BORDER2, width=2)

    # --- footer ---
    draw.text((cx, CANVAS_SIZE - footer_h / 2), "tracersports.net", font=_font("Medium", 16), fill=TEXT3, anchor="mm")
    if extra:
        draw.text((cx - 200, CANVAS_SIZE - footer_h / 2), f"+{extra} more",
                   font=_font("Regular", 15), fill=TEXT3, anchor="mm")

    out_dir = OUTPUT_ROOT / league
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{slate_date.isoformat()}.png"
    img.save(out_path)
    return out_path
