from datetime import date
from pathlib import Path

import pytest

from summer_movie_wager.ingest.boxoffice import parse_year_chart

FIXTURE = Path(__file__).parent / "fixtures" / "boxofficemojo_year_2026.html"


@pytest.fixture
def chart():
    html_text = FIXTURE.read_text(encoding="utf-8")
    return parse_year_chart(html_text, year=2026)


def test_chart_has_two_hundred_rows(chart):
    # The yearly chart is capped at 200 rows; ?offset=200 is ignored by the site.
    assert len(chart) == 200


def test_long_tail_film_is_present(chart):
    # Power Ballad never enters the play-along site's top 13. Capturing it is
    # the entire reason this module exists.
    assert chart["Power Ballad"].cumulative_gross == 2_612_490.0
    assert chart["Power Ballad"].release_date == date(2026, 5, 29)


def test_faded_film_is_present(chart):
    # The Sheep Detectives dropped off the play-along site's top 13 mid-season.
    assert chart["The Sheep Detectives"].cumulative_gross == 66_078_506.0
    assert chart["The Sheep Detectives"].release_date == date(2026, 5, 8)


def test_uses_gross_column_not_total_gross_column(chart):
    # The chart carries both "Gross" (calendar-2026 domestic) and "Total Gross"
    # (lifetime). For 2026 releases the "Total Gross" cell is frequently stale or
    # outright wrong -- Obsession reads $240,017,600 there against $260,344,235
    # in the "Gross" cell, and the play-along site independently reported
    # $258,387,140 on 2026-07-20. The "Gross" cell is the correct one.
    assert chart["Obsession"].cumulative_gross == 260_344_235.0


def test_release_date_parsed_from_abbreviated_month(chart):
    assert chart["Toy Story 5"].release_date == date(2026, 6, 19)


def test_ignores_the_header_row(chart):
    assert "Release" not in chart
