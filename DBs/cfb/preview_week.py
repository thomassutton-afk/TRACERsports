"""Rank upcoming FBS-vs-FBS games by 'watchability' (read-only).

Run from DBs/cfb:
    python preview_week.py                       # next 7 days from today, echo, top 15
    python preview_week.py --days 3 --top 10
    python preview_week.py --start 2026-10-24 --days 7
    python preview_week.py --variant pulse --w 0.65     # lean toward quality over closeness

Score = 100 * quality^w * closeness^(1-w)           (w = 0.5 by default, i.e. a geometric mean)

  closeness = 4 * p * (1 - p), where p is the model's win probability for the home team.
              1.0 for a coin flip, falling smoothly toward 0 for a lopsided game. It uses the model's
              probability (which already includes home field and rest), not the raw Elo gap.
  quality   = average of the two teams' percentile among all FBS teams by current rating (0-1).

Because it is a product, a game needs BOTH to score high: an elite blowout and a coin-flip between two
weak teams both come out low. Raise --w to reward quality more, lower it to reward closeness more.
Games involving an FCS team are skipped (they have no rating).
"""
import argparse, datetime, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db, rebuild

ap = argparse.ArgumentParser()
ap.add_argument("--db", default="../cfb_elo.db")
ap.add_argument("--variant", choices=["echo", "pulse"], default="echo")
ap.add_argument("--start", help="first date, YYYY-MM-DD (default: today)")
ap.add_argument("--days", type=int, default=7)
ap.add_argument("--top", type=int, default=15)
ap.add_argument("--w", type=float, default=0.5, help="weight on quality, 0-1 (default 0.5)")
a = ap.parse_args()
if not 0 <= a.w <= 1: sys.exit("--w must be between 0 and 1")

conn = db.connect(a.db)
season = conn.execute("SELECT MAX(season) FROM games").fetchone()[0]
start = datetime.date.fromisoformat(a.start) if a.start else datetime.date.today()
end = start + datetime.timedelta(days=a.days - 1)

short = {}
p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "team_display_names.json")
if os.path.exists(p):
    short = {v["team_id"]: v["short"] for v in json.load(open(p, encoding="utf-8")).values()}

standings = rebuild.standings(conn, season, a.variant)      # FBS teams only, current ratings
rating = {tid: r for tid, _, _, _, _, r in standings}
name = {tid: short.get(tid, n) for tid, n, *_ in standings}
vals = sorted(rating.values())
pct = lambda r: sum(v < r for v in vals) / (len(vals) - 1)

rows = conn.execute(
    "SELECT s.date, s.home_team, s.away_team, s.neutral, p.expected_win_home "
    "FROM schedule s JOIN schedule_predictions p ON p.schedule_id = s.schedule_id AND p.variant = ? "
    "WHERE s.season = ? AND s.date BETWEEN ? AND ?", (a.variant, season, str(start), str(end))).fetchall()

games = []
for d, h, aw, neutral, pw in rows:
    if h not in rating or aw not in rating: continue
    q = (pct(rating[h]) + pct(rating[aw])) / 2
    c = 4 * pw * (1 - pw)
    games.append((100 * q ** a.w * c ** (1 - a.w), d, h, aw, neutral, pw, q, c))
games.sort(reverse=True)

print(f"{a.variant} | {start} to {end} | {len(games)} FBS-vs-FBS games | w = {a.w}\n")
if not games: sys.exit("No upcoming FBS-vs-FBS games in that window.")
print(f"{'#':>3}  {'Date':<11}{'Game':<44}{'Home win':>9}{'Avg Elo':>9}{'Elo gap':>9}{'Qual':>6}{'Close':>7}{'Score':>7}")
for i, (sc, d, h, aw, neutral, pw, q, c) in enumerate(games[:a.top], 1):
    game = f"{name[aw]} {'vs' if neutral else '@'} {name[h]}"
    print(f"{i:>3}  {d:<11}{game:<44}{pw:>8.0%}{(rating[h] + rating[aw]) / 2:>9.0f}"
          f"{abs(rating[h] - rating[aw]):>9.0f}{q:>6.2f}{c:>7.2f}{sc:>7.0f}")
