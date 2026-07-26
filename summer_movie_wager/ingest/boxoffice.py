"""Fetch cumulative domestic grosses from Box Office Mojo's yearly chart.

The play-along site only publishes its top 13, so films below it (or films that
fall out of it) go dark. Box Office Mojo's yearly chart lists 200 titles with
release dates, which covers every film that could plausibly finish in the
wager's top 10 -- and every film any player picked.

Row shape, verified against the 2026 chart (all 200 rows share one class
signature):

    <td class="... mojo-field-type-rank ...">1</td>
    <td class="... mojo-field-type-release ..."><a href="/release/rl...">Toy Story 5</a></td>
    <td class="... mojo-field-type-genre hidden">-</td>
    <td class="... mojo-field-type-money hidden">-</td>          <- budget
    <td class="... mojo-field-type-duration hidden">-</td>
    <td class="... mojo-field-type-money mojo-estimatable">$441,455,658</td>   <- Gross
    <td class="... mojo-field-type-positive_integer">4,425</td>
    <td class="... mojo-field-type-money mojo-estimatable">$441,455,658</td>   <- Total Gross
    <td class="... mojo-field-type-date a-nowrap">Jun 19</td>
    ...
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime

import httpx
from pydantic import BaseModel, ConfigDict
from selectolax.parser import HTMLParser

from summer_movie_wager.model.preopening import WINDOW_END, WINDOW_START

YEAR_CHART_URL = "https://www.boxofficemojo.com/year/{year}/"


class BoxOfficeRow(BaseModel):
    """One release on the yearly chart."""

    model_config = ConfigDict(frozen=True)

    title: str
    cumulative_gross: float
    release_date: date
    # Re-release / anniversary / festival booking of an older film, flagged by a
    # note element in the release cell. Never a wager film -- see `in_window`.
    is_rerelease: bool = False


def fetch_year_chart(*, year: int = 2026, timeout: float = 30.0) -> dict[str, BoxOfficeRow]:
    """Fetch and parse the live yearly chart, keyed by title."""

    response = httpx.get(YEAR_CHART_URL.format(year=year), timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return parse_year_chart(response.text, year=year)


def parse_year_chart(html_text: str, *, year: int) -> dict[str, BoxOfficeRow]:
    """Parse the yearly chart into `{title: BoxOfficeRow}`.

    Rows that don't yield a title, a gross, and a release date are skipped rather
    than raising -- the chart carries occasional oddities (event cinema, re-release
    rows) that aren't worth failing a build over.
    """

    tree = HTMLParser(html_text)
    rows: dict[str, BoxOfficeRow] = {}
    for row in tree.css("tr"):
        title_cell = row.css_first("td.mojo-field-type-release")
        date_cell = row.css_first("td.mojo-field-type-date")
        # The budget cell also carries `mojo-field-type-money` but is marked `hidden`;
        # the two `mojo-estimatable` money cells are [Gross, Total Gross] in that order.
        money_cells = row.css("td.mojo-field-type-money.mojo-estimatable")
        if title_cell is None or date_cell is None or not money_cells:
            continue

        # A re-release row carries a note element after the title link ("2026
        # Re-release", "25th Anniversary", "Studio Ghibli Fest 2026"), which
        # `text(deep=True)` would concatenate onto the title with no separator.
        # Take the title from the link and keep the note as a flag.
        title_link = title_cell.css_first("a")
        note = title_cell.css_first("div")
        title = _clean_text((title_link or title_cell).text(deep=True))
        gross = _parse_dollar_amount(_clean_text(money_cells[0].text(deep=True)))
        release = _parse_release_date(_clean_text(date_cell.text(deep=True)), year=year)
        if not title or gross is None or release is None:
            continue

        rows[title] = BoxOfficeRow(
            title=title,
            cumulative_gross=gross,
            release_date=release,
            is_rerelease=note is not None,
        )
    return rows


def _clean_text(raw: str) -> str:
    """Decode HTML entities, drop non-breaking spaces, collapse whitespace runs."""

    text = html.unescape(raw or "")
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _parse_dollar_amount(text: str) -> float | None:
    """Parse "$441,455,658" into a float. Returns None for placeholders like "-"."""

    m = re.match(r"^\$?([\d,]+)$", text)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def _parse_release_date(text: str, *, year: int) -> date | None:
    """Parse an abbreviated "Jun 19" into a date, stamping the chart's year.

    The chart omits the year, and rows for prior-year releases still showing in
    this year's chart (e.g. a Dec 19 2025 opening) get stamped with the chart year.
    That is harmless here: those dates land outside the wager window either way,
    so the window filter in `in_window` drops them for the right reason.
    """

    try:
        return datetime.strptime(f"{text} {year}", "%b %d %Y").date()
    except ValueError:
        return None


def in_window(chart: dict[str, BoxOfficeRow]) -> dict[str, BoxOfficeRow]:
    """Keep only wager films: released inside the window (inclusive both ends),
    original releases only.

    Re-releases are dropped. The wager is about 2026's new movies, and every
    re-release row on the July 2026 chart is a revival of an older title (Top
    Gun, Shrek, two Ghibli Fest bookings, End of Evangelion in-window; LOTR,
    Fight Club and friends out of window) -- none is a 2026 original. Letting
    them through would also write their gross into the append-only history.
    """

    return {
        title: row
        for title, row in chart.items()
        if WINDOW_START <= row.release_date <= WINDOW_END and not row.is_rerelease
    }
