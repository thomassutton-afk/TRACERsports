"""
normalize_sr_games.py

Converts a raw Sports-Reference CFB schedule/scores export (one row per
GAME - Winner, Winner's Pts, an unlabeled site-indicator column, Loser,
Loser's Pts, Notes) into the standardized per-team-perspective shape
add_season.py expects: Date, Season, Type, Round, Team, Opp, HomeAway,
PointsFor, PointsAgainst, OT, TeamAPRank, OppAPRank - one row per team
per game (both perspectives), same convention as NFL_Elo's
normalize_parsed_games.py.

SITE-INDICATOR COLUMN: Sports-Reference's raw export has no header for
this column (it sits between the winner's points and the loser's name),
so pandas reads it in as "Unnamed: N". Its values:
    ""  (blank) -> the Winner was the HOME team
    "@"         -> the Winner was the AWAY team (played at the Loser's
                   home stadium - the Loser was actually the home team)
    "N"         -> neutral site; neither team was truly "home"

WHAT THIS DOES:
  - Emits TWO output rows per raw game row (one per team's own
    perspective), each carrying that team's own HomeAway tag
    ('H'/'A'/'N') for this game.
  - Strips and preserves the AP poll rank prefix, e.g. "(11) Penn
    State" -> name="Penn State", rank=11 -> into TeamAPRank/OppAPRank.
    Display-only; the Elo engine never reads these (see db.py's module
    docstring).
  - Derives a stable team CODE by slugifying the full team name (e.g.
    "Southern California" -> "southern-california", "Miami (FL)" ->
    "miami-fl", "Louisiana-Monroe" -> "louisiana-monroe") - CFB has no
    standard stable abbreviation the way NFL codes exist, so
    add_season.py's franchise auto-registration keys off these slugs
    going forward. A genuine program name change later goes through
    team_history/team_aliases, same as any other rename - this script
    does not need to know about that; it just slugifies whatever name
    appears in a given season's file.
  - Assigns Season as the FALL year a season is conventionally labeled
    under, even for games played in January/February of the following
    calendar year (bowl games) - date.month <= 6 means "belongs to
    last year's season."
  - Type is ALWAYS 'R' for every game, including bowls and conference
    championships - postseason games are NOT reclassified as type='P'.
    Round classification (PHASE 2 - see classify_round() below) is
    era-branched, since the postseason FORMAT itself changed multiple
    times across 1996-2025 (no unified system pre-1998, BCS 1998-2013,
    4-team CFP 2014-2023, 12-team CFP 2024+):
      - "NC" (national championship): explicit in Notes from 2006
        onward ("BCS Championship" 2006-2013, "College Football
        Playoff National Championship" 2014+). For 1998-2005, the BCS
        title game was just whichever of Rose/Sugar/Orange/Fiesta was
        that year's designated host in the normal rotation, with NO
        distinguishing text in Notes - see BCS_EMBEDDED_TITLE_BOWL,
        cross-referenced against BCS history and confirmed directly
        against the 1998 and 2000 raw files.
      - "CFP-R1" (12-team first round): explicit in Notes from 2024
        onward ("College Football Playoff - First Round").
      - "CFP-SF" (semifinal): explicit host-bowl-pair-by-season lookup
        (CFP_SEMIFINAL_PAIR) - the semifinal bowls are NEVER named as
        such in Notes (just the host bowl's normal name), in either
        the 4-team (2014-2023) or 12-team (2024+) era.
      - "CFP-QF" (12-team quarterfinal, 2024+ only): whichever New
        Year's Six bowl isn't that season's semifinal host - also
        never explicitly named as a quarterfinal in Notes.
      - "CCG" (conference championship): "Championship" appearing in
        Notes, e.g. "SEC Championship (Atlanta GA)" - reliable across
        every era regardless of exact conference name, but ONLY once
        NC is ruled out first (both "BCS Championship" and "College
        Football Playoff National Championship" also contain the
        word "Championship").
      - "BOWL" (every other bowl, non-playoff): "Bowl" appearing in
        Notes. Deliberately NOT split into a hardcoded "major bowl"
        list - the engine instead scores a BOWL game's importance
        directly off the two teams' own AP ranks (TeamAPRank/
        OppAPRank, already carried through below), which needs no
        era-branching and better reflects that a mediocre edition of
        a historically major bowl isn't actually more important than
        an elite matchup in a smaller one.
      - None: regular season.
    The raw Notes text is carried through to the output CSV regardless
    of era, so this classification can be revised later without
    re-running this normalizer against the original raw file again.
  - OT is hardcoded to 0 for every row - this source format carries no
    overtime flag. Revisit if/when a source with real OT data is added.

WHAT THIS DOES NOT DO:
  - No conference/division assignment (`team_conference_history` is
    populated through a separate process - this source has no
    conference column at all).
  - No FBS/FCS filtering - every team that appears (including an FCS
    opponent in a given box score) gets registered, consistent with
    the "start FBS, leave door open" scope decision.

Usage:
    python3 normalize_sr_games.py raw_sports_ref_1996.csv parsed_games_1996.csv
"""
import re
import sys

import pandas as pd

RANK_RE = re.compile(r"^\((\d+)\)\s*(.+)$")

# PHASE 2 POSTSEASON LOOKUP TABLES - see module docstring. Static
# historical fact, not derived from the data itself, so these are
# plain constants rather than something computed per-file.

# 1998-2005: the BCS title game WAS one of the four rotating bowls
# (no standalone game existed yet), and Notes carries no marker
# distinguishing it from a non-title edition of that same bowl in a
# different year. Confirmed directly against the 1998 (Fiesta) and
# 2000 (Orange) raw files; the remaining years follow the same
# well-documented Rose/Sugar/Orange/Fiesta rotation.
BCS_EMBEDDED_TITLE_BOWL = {
    1998: "Fiesta", 1999: "Sugar", 2000: "Orange", 2001: "Rose",
    2002: "Fiesta", 2003: "Sugar", 2004: "Orange", 2005: "Rose",
}

# 2014-2025: the two CFP semifinal host bowls each season, on a
# 3-year cycle. Never marked as "semifinal" in Notes in either the
# 4-team (2014-2023) or 12-team (2024+) era - just the host bowl's
# ordinary name. 2024 and 2025 confirmed directly against this
# dataset's own raw files; 2014-2023 confirmed against independent
# sources following the same cycle.
CFP_SEMIFINAL_PAIR = {
    2014: ("Rose", "Sugar"), 2015: ("Orange", "Cotton"), 2016: ("Fiesta", "Peach"),
    2017: ("Rose", "Sugar"), 2018: ("Orange", "Cotton"), 2019: ("Fiesta", "Peach"),
    2020: ("Rose", "Sugar"), 2021: ("Orange", "Cotton"), 2022: ("Fiesta", "Peach"),
    2023: ("Rose", "Sugar"), 2024: ("Orange", "Cotton"), 2025: ("Fiesta", "Peach"),
}

# The New Year's Six bowls - used only to detect a 12-team-era (2024+)
# quarterfinal (whichever of these isn't hosting that year's
# semifinal - see CFP_SEMIFINAL_PAIR).
NY6_BOWLS = ("Rose", "Sugar", "Orange", "Cotton", "Fiesta", "Peach")


def classify_round(notes: str, season: int, date) -> "str | None":
    """PHASE 2 postseason round classification - see module docstring
    for the full era-by-era rationale. Order matters: NC must be ruled
    out before the CCG check, since both "BCS Championship" and
    "College Football Playoff National Championship" contain the word
    "Championship" too.

    Every "___ Bowl"-style check below is a plain substring/regex
    match against Sports-Reference's free-text Notes field, which
    ALSO carries venue names for plenty of regular-season games - and
    several stadiums are themselves named "___ Bowl" (Memphis's
    Liberty Bowl Memorial Stadium, UTEP's Sun Bowl Stadium, UCLA's
    Rose Bowl), and one annual regular-season rivalry game
    (Texas-Oklahoma) is played every October at the Cotton Bowl in
    Dallas. Confirmed against 104 such false positives across
    1996-2025 (including the SAME collision independently breaking
    the CFP-SF embedded-bowl-name check in 2015 and 2017, when the
    Cotton Bowl/Rose Bowl happened to be that year's semifinal host).
    Real postseason games only ever happen from December through the
    following June (see season_for_date's own Dec/Jan year-boundary
    convention, reused here) - so every "___ Bowl" check is gated on
    that window. Conference championship games are NOT gated the same
    way: "Championship" never collides with a venue name (confirmed:
    zero false positives across 30 seasons), and Championship Saturday
    itself sometimes falls on November 30 (MAC/Pac-12, seen in 2001,
    2006, 2012, 2018) - gating it to December would incorrectly drop
    those. Widening the "___ Bowl" window into late November to catch
    those same six games would reintroduce the venue-name false
    positives (Memphis/UTEP/Toledo/UCLA all play regular-season home
    games that late too) - confirmed 12 such collisions in the Nov
    20-30 range alone. So the two checks need different gates, not one
    shared cutoff.
    """
    if not notes:
        return None
    in_bowl_window = date.month == 12 or date.month <= 6

    if "BCS Championship" in notes or "College Football Playoff National Championship" in notes:
        return "NC"
    embedded_host = BCS_EMBEDDED_TITLE_BOWL.get(season)
    if embedded_host and in_bowl_window and f"{embedded_host} Bowl" in notes:
        return "NC"

    if "College Football Playoff - First Round" in notes:
        return "CFP-R1"

    sf_pair = CFP_SEMIFINAL_PAIR.get(season)
    if sf_pair and in_bowl_window and any(f"{b} Bowl" in notes for b in sf_pair):
        return "CFP-SF"

    if season >= 2024 and in_bowl_window and any(f"{b} Bowl" in notes for b in NY6_BOWLS):
        return "CFP-QF"

    if re.search(r"\bChampionship\b", notes):
        return "CCG"

    if in_bowl_window and re.search(r"\bBowl\b", notes):
        return "BOWL"

    return None


def dedupe_raw_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Sports-Reference occasionally emits two rows for the same real
    game with different Notes text: one copy carrying the actual bowl/
    event name, the other just a generic venue name (or blank). Left
    alone, this used to dedupe by accident (every game had Round=None
    regardless of which copy survived) - but now that Round
    classification can differ between the two copies (one recognizes
    a bowl/event name, the other doesn't), keeping both would let them
    collide on DIFFERENT (date, home, away, type, round) keys and
    double-insert into the DB, double-counting that game's Elo impact.
    Confirmed against 8 real cases across 1996-2025 (six bowl games
    plus the 2010 SEC Championship Game). Groups by (Date, Winner,
    Loser) and keeps whichever copy's Notes actually names a
    recognizable event, dropping the other."""
    def informativeness(notes: str) -> int:
        if not notes:
            return 0
        if re.search(r"\bBowl\b|\bChampionship\b|Playoff|BCS", notes):
            return 2
        return 1

    working = df.copy()
    working["_info"] = working["Notes"].fillna("").astype(str).map(informativeness)
    working = working.sort_values("_info", ascending=False)
    before = len(working)
    working = working.drop_duplicates(subset=["Date", "Winner", "Loser"], keep="first")
    dropped = before - len(working)
    if dropped:
        print(f"NOTE: dropped {dropped} duplicate raw row(s) (same date/winner/loser, "
              f"kept whichever copy's Notes named a recognizable bowl/championship).")
    return working.drop(columns=["_info"]).sort_index()


def parse_team(raw: str) -> tuple[str, "int | None"]:
    """Split a Sports-Reference team field like '(11) Penn State' into
    (name, rank). Returns (raw, None) if there's no rank prefix - most
    teams most weeks are unranked."""
    m = RANK_RE.match(str(raw).strip())
    if m:
        return m.group(2).strip(), int(m.group(1))
    return str(raw).strip(), None


def slugify(name: str) -> str:
    """Derive a stable team code from a full name. See module docstring
    - CFB has no standard abbreviation source, so this IS the code."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def season_for_date(d) -> int:
    """The fall year a game's season is conventionally labeled under -
    e.g. a January 2, 1997 bowl game belongs to the "1996 season"."""
    return d.year - 1 if d.month <= 6 else d.year


def _find_header_row(path: str) -> int:
    """Sports-Reference's raw export has a citation-request preamble
    (and sometimes blank lines) before the real header row. Scan for
    the actual 'Rk,Wk,Date,...' header line rather than assuming it's
    line 0."""
    with open(path, encoding="utf-8", errors="ignore") as f:
        for i, line in enumerate(f):
            if line.startswith("Rk,Wk,Date"):
                return i
    return 0


def normalize(path: str) -> pd.DataFrame:
    header_row = _find_header_row(path)
    df = pd.read_csv(path, skiprows=header_row)

    # The raw export's unlabeled site-indicator column loads as
    # "Unnamed: N" - rename it to something addressable regardless of
    # its exact position.
    site_cols = [c for c in df.columns if c.startswith("Unnamed")]
    if site_cols:
        df = df.rename(columns={site_cols[0]: "Site"})
    else:
        df["Site"] = ""
    df["Site"] = df["Site"].fillna("")

    # Sports-Reference sometimes repeats the header row mid-file (page
    # breaks in the original HTML table); drop those, plus any row
    # missing a real Winner/Loser matchup.
    df = df[df["Winner"].notna() & df["Loser"].notna()].copy()
    df = df[df["Winner"] != "Winner"].copy()

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    n_bad_dates = df["Date"].isna().sum()
    if n_bad_dates:
        print(f"WARNING: skipping {n_bad_dates} row(s) with unparseable dates.")
    df = df[df["Date"].notna()].copy()

    # The winner's and loser's points columns both come in as "Pts" in
    # the raw header, so pandas suffixes the second one "Pts.1".
    loser_pts_col = "Pts.1" if "Pts.1" in df.columns else "Pts"

    # A row with a real matchup but NO score (blank Pts on either side)
    # falls into one of two buckets, distinguished by date:
    #   - UPCOMING: the game's date is today or in the future (or within
    #     RECENT_UNSCORED_BUFFER_DAYS just past, since Sports-Reference
    #     can take a day to post a final score) - a legitimate game that
    #     just hasn't been played yet. These rows are KEPT, with
    #     PointsFor/PointsAgainst left blank; add_season.py already
    #     knows a scoreless row belongs in `schedule`, not `games`, so
    #     nothing further is needed here.
    #   - STALE: the date is further in the past than the buffer and it
    #     STILL has no score - a postponed, cancelled, or forfeited game
    #     that never actually happened. Drop these, same as always;
    #     they're genuinely rare (a handful across 30 seasons). This
    #     distinction matters: unlike an upcoming game, a stale
    #     cancellation will never get a real result to match against, so
    #     letting it through to `schedule` would leave it showing up as
    #     an "upcoming game" forever (db.upcoming_games() does no date
    #     filtering of its own).
    RECENT_UNSCORED_BUFFER_DAYS = 3
    no_score = df["Pts"].isna() | df[loser_pts_col].isna()
    cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=RECENT_UNSCORED_BUFFER_DAYS)
    is_upcoming = no_score & (df["Date"] >= cutoff)
    is_stale = no_score & (df["Date"] < cutoff)

    n_upcoming = is_upcoming.sum()
    if n_upcoming:
        print(f"NOTE: {n_upcoming} row(s) with no final score are upcoming/unplayed "
              f"games - keeping them (routed to the schedule table downstream):")
        for _, sr in df[is_upcoming].iterrows():
            print(f"  {sr['Date'].date()}: {sr['Winner']} vs {sr['Loser']}")

    n_stale = is_stale.sum()
    if n_stale:
        skipped = df[is_stale]
        print(f"WARNING: skipping {n_stale} row(s) with no final score "
              f"(likely postponed/cancelled games):")
        for _, sr in skipped.iterrows():
            print(f"  {sr['Date'].date()}: {sr['Winner']} vs {sr['Loser']}")
    df = df[~is_stale].copy()

    # Sports-Reference source-data dedup (see dedupe_raw_rows' docstring) -
    # must happen before classification, not after, since it's exactly
    # the classification differing between two copies of the same game
    # that creates the double-count risk.
    df = dedupe_raw_rows(df)

    rows = []
    for _, r in df.iterrows():
        season = season_for_date(r["Date"])
        winner_name, winner_rank = parse_team(r["Winner"])
        loser_name, loser_rank = parse_team(r["Loser"])
        winner_code = slugify(winner_name)
        loser_code = slugify(loser_name)
        site = str(r["Site"]).strip()

        if site == "@":
            winner_ha, loser_ha = "A", "H"
        elif site == "N":
            winner_ha, loser_ha = "N", "N"
        else:
            winner_ha, loser_ha = "H", "A"

        date_str = r["Date"].date().isoformat()
        has_score = pd.notna(r["Pts"]) and pd.notna(r[loser_pts_col])
        win_pts = int(r["Pts"]) if has_score else None
        lose_pts = int(r[loser_pts_col]) if has_score else None

        # PHASE 2 POSTSEASON (see this module's docstring and
        # classify_round() above for the full era-by-era rationale).
        notes = str(r["Notes"]).strip() if "Notes" in df.columns and pd.notna(r["Notes"]) else ""
        round_ = classify_round(notes, season, r["Date"])

        rows.append(dict(
            Date=date_str, Season=season, Type="R", Round=round_,
            Team=winner_code, Opp=loser_code, HomeAway=winner_ha,
            PointsFor=win_pts, PointsAgainst=lose_pts, OT=0,
            TeamAPRank=winner_rank, OppAPRank=loser_rank, Notes=notes,
        ))
        rows.append(dict(
            Date=date_str, Season=season, Type="R", Round=round_,
            Team=loser_code, Opp=winner_code, HomeAway=loser_ha,
            PointsFor=lose_pts, PointsAgainst=win_pts, OT=0,
            TeamAPRank=loser_rank, OppAPRank=winner_rank, Notes=notes,
        ))

    return pd.DataFrame(rows, columns=[
        "Date", "Season", "Type", "Round", "Team", "Opp", "HomeAway",
        "PointsFor", "PointsAgainst", "OT", "TeamAPRank", "OppAPRank", "Notes",
    ])


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 normalize_sr_games.py raw_sports_ref.csv parsed_games_YYYY.csv")
        sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    out = normalize(src)
    out.to_csv(dst, index=False)
    seasons = sorted(out["Season"].unique())
    print(f"Wrote {len(out)} team-game rows ({len(out) // 2} games) to {dst}.")
    print(f"Season(s) covered: {seasons}")


if __name__ == "__main__":
    main()
