"""Scrape and parse the Summer Movie Wager play-along page."""

from __future__ import annotations

import html
import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser, Node

from summer_movie_wager.types import PlayerPicks, SiteSnapshot

PLAYALONG_URL = (
    "https://thesummermoviewager.com/index.php"
    "?year=2026"
    "&addPlayer=bclarke,vivrad,zmeister,brettfern,carleigh,radhadr,emsullivan,mhartje"
    "&playAlongOnly="
)

# Canonical lowercase usernames for the wager group. The site sometimes returns
# the display-cased version (e.g. "RadhaDR") in id attributes; we normalize to lowercase.
_GROUP_USERNAMES = {
    "bclarke", "vivrad", "zmeister", "brettfern",
    "carleigh", "radhadr", "emsullivan", "mhartje",
}


def fetch_snapshot(*, captured_at: date | None = None, timeout: float = 30.0) -> SiteSnapshot:
    """Fetch and parse the live play-along page."""
    
    if captured_at is None:
        captured_at = date.today()
    response = httpx.get(PLAYALONG_URL, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return parse_snapshot(response.text, captured_at=captured_at)


def parse_snapshot(html_text: str, *, captured_at: date) -> SiteSnapshot:
    """Parse the captured HTML into a SiteSnapshot.

    Selectors derived against the 2026-05-03 fixture:
      - Each player has a `<table id="scTable_<USERNAME>" class="mw playerpoints">`
        whose body holds 13 rows (10 ranked + 3 dark-horse).
      - Dark-horse rows have a `<i class="fas fa-chess-knight">` icon in the
        `<td class="mw pos">` cell instead of a numeric "N." position.
      - The top-13 box-office grosses live in `<table class="mw toptengross ...">`
        with `<td class="mw name">TITLE</td><td class="mw result">$AMOUNT</td>` rows.
      - Standings live in `<table class="mw totalscoretable">` with rows of
        `<td class="mw name">USERNAME</td>...<td class="mw result">SCORE</td>`.

    If the site changes its HTML structure, this parser will need updating - the
    live-validation scoring check (Task 11) is designed to catch that drift.
    """

    tree = HTMLParser(html_text)

    players = _parse_players(tree)
    cumulative = _parse_cumulative_grosses(tree)
    site_points = _parse_site_reported_points(tree)
    return SiteSnapshot(
        captured_at = captured_at,
        players = players,
        cumulative_grosses = cumulative,
        site_reported_points = site_points,
    )


def _clean_text(raw: str) -> str:
    """Decode HTML entities, strip non-breaking-space whitespace, collapse runs of spaces."""

    text = html.unescape(raw or "")
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_players(tree: HTMLParser) -> dict[str, PlayerPicks]:
    """Extract picks from each `<table id="scTable_<USERNAME>">`."""

    players: dict[str, PlayerPicks] = {}
    for table in tree.css("table.playerpoints, table.mw.playerpoints"):
        table_id = table.attributes.get("id", "") or ""
        if not table_id.startswith("scTable_"):
            continue
        username = table_id[len("scTable_"):]
        norm = username.lower()
        if norm not in _GROUP_USERNAMES:
            continue
        ranked, dark_horses = _extract_picks_from_table(table)
        if len(ranked) != 10 or len(dark_horses) != 3:
            continue
        players[norm] = PlayerPicks(
            username = norm,
            ranked = ranked,
            dark_horses = dark_horses,
        )
    return players


def _extract_picks_from_table(table: Node) -> tuple[list[str], list[str]]:
    """Walk the rows of a player table; classify each by the position cell.

    A ranked row has `<td class="mw pos">N.</td>` with a digit.
    A dark-horse row has `<i class="fas fa-chess-knight">` inside the position cell.
    """

    ranked_by_pos: dict[int, str] = {}
    dark_horses: list[str] = []

    for row in table.css("tr"):
        pos_cell = row.css_first("td.pos, td.mw.pos")
        if pos_cell is None:
            continue
        name_cell = row.css_first("td.name, td.mw.name")
        if name_cell is None:
            continue
        title = _clean_text(name_cell.text(deep=True))
        if not title:
            continue

        # Dark horse rows use a chess-knight icon as the position marker.
        if pos_cell.css_first("i.fa-chess-knight") is not None:
            dark_horses.append(title)
            continue

        # Otherwise expect "N." in the position cell.
        pos_text = _clean_text(pos_cell.text(deep=True))
        match = re.match(r"^(\d{1,2})\.?$", pos_text)
        if not match:
            continue
        rank = int(match.group(1))
        if 1 <= rank <= 10:
            ranked_by_pos.setdefault(rank, title)

    ranked = [ranked_by_pos[i] for i in range(1, 11) if i in ranked_by_pos]
    return ranked, dark_horses


def _parse_cumulative_grosses(tree: HTMLParser) -> dict[str, float]:
    """Read the top-N gross table: `<td class="mw name">TITLE</td><td class="mw result">$AMOUNT</td>`."""

    grosses: dict[str, float] = {}
    table = tree.css_first("table.toptengross, table.mw.toptengross")
    if table is None:
        return grosses
    for row in table.css("tr"):
        name_cell = row.css_first("td.name, td.mw.name")
        result_cell = row.css_first("td.result, td.mw.result")
        if name_cell is None or result_cell is None:
            continue
        title = _clean_text(name_cell.text(deep=True))
        amount_text = _clean_text(result_cell.text(deep=True))
        amount = _parse_dollar_amount(amount_text)
        if not title or amount is None:
            continue
        # If the same title shows up multiple times (it shouldn't in this table),
        # keep the largest cumulative figure.
        if amount > grosses.get(title, 0.0):
            grosses[title] = amount
    return grosses


def _parse_dollar_amount(text: str) -> float | None:
    """Parse strings like "$77,000,000" or "$1.5M" into a float (USD)."""

    if not text:
        return None
    cleaned = text.replace("$", "").strip()
    # Optional trailing "M" / "B" multiplier.
    multiplier = 1.0
    m = re.match(r"^([\d,]+(?:\.\d+)?)\s*([MB])?$", cleaned, re.IGNORECASE)
    if not m:
        return None
    number = float(m.group(1).replace(",", ""))
    suffix = (m.group(2) or "").upper()
    if suffix == "M":
        multiplier = 1_000_000.0
    elif suffix == "B":
        multiplier = 1_000_000_000.0
    return number * multiplier


def _parse_site_reported_points(tree: HTMLParser) -> dict[str, int]:
    """Read standings from `<table class="mw totalscoretable">`.

    Each row: `<td class="mw pos">N.</td><td class="mw name">USERNAME</td>...<td class="mw result">SCORE</td>`.
    """

    found: dict[str, int] = {}
    table = tree.css_first("table.totalscoretable, table.mw.totalscoretable")
    if table is None:
        return found
    for row in table.css("tr"):
        name_cell = row.css_first("td.name, td.mw.name")
        result_cell = row.css_first("td.result, td.mw.result")
        if name_cell is None or result_cell is None:
            continue
        username = _clean_text(name_cell.text(deep=True)).lower()
        if username not in _GROUP_USERNAMES:
            continue
        score_text = _clean_text(result_cell.text(deep=True))
        m = re.match(r"^-?\d+$", score_text)
        if not m:
            continue
        found[username] = int(score_text)
    return found
