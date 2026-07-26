from datetime import date
from pathlib import Path

import pytest

from summer_movie_wager.ingest.boxoffice import BoxOfficeRow, in_window, parse_year_chart

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


def test_window_excludes_releases_before_may_first(chart):
    # Michael opened Apr 24 and is absent from the play-along site's gross table
    # despite grossing $372M -- it is not a wager film.
    assert "Michael" in chart
    assert "Michael" not in in_window(chart)


def test_window_excludes_april_thirtieth_releases(chart):
    # The Story of Everything opened Apr 30. It is absent from the site's
    # 2026-05-04 gross list, which is the evidence the window opens May 1.
    assert "The Story of Everything" in chart
    assert "The Story of Everything" not in in_window(chart)


def test_window_includes_may_first_releases(chart):
    assert "The Devil Wears Prada 2" in in_window(chart)


def test_window_excludes_releases_after_labor_day(chart):
    # Zootopia 2 carries a Nov 26 date on the 2026 chart; whatever year it
    # really belongs to, it is outside 2026-05-01..2026-09-07.
    assert "Zootopia 2" in chart
    assert "Zootopia 2" not in in_window(chart)


def test_window_keeps_the_long_tail(chart):
    windowed = in_window(chart)
    assert "Power Ballad" in windowed
    assert "The Sheep Detectives" in windowed


def test_rerelease_row_title_is_not_mangled(chart):
    # The release cell of a re-release row holds a note element after the title
    # link; text(deep=True) glued it onto the title with no separator, producing
    # 'Top Gun/Top Gun: Maverick2026 Re-release (Top Gun 40th Anniversary)' --
    # which then got written into the append-only history file.
    row = chart["Top Gun/Top Gun: Maverick"]
    assert row.is_rerelease
    assert not any("Re-release" in title for title in chart)


def test_original_releases_are_not_flagged_as_rereleases(chart):
    assert not chart["Toy Story 5"].is_rerelease
    assert not chart["Power Ballad"].is_rerelease


def test_window_excludes_rereleases(chart):
    # All five in-window re-release rows on the 2026 chart are revivals of older
    # films (Top Gun 40th, Shrek 25th, End of Evangelion, and two Ghibli Fest
    # bookings) -- none is a 2026 original, so none is a wager film.
    windowed = in_window(chart)
    for title in (
        "Top Gun/Top Gun: Maverick",
        "Shrek",
        "Neon Genesis Evangelion: The End of Evangelion",
        "My Neighbor Totoro",
        "Ponyo",
    ):
        assert chart[title].is_rerelease
        assert title not in windowed
    assert not any(row.is_rerelease for row in windowed.values())


def test_window_end_boundary_with_synthetic_rows():
    # The fixture contains no Sep 6/7/8 releases, so this test constructs
    # synthetic BoxOfficeRow objects to cover the WINDOW_END boundary
    # precisely. This catches the off-by-one error where < WINDOW_END
    # would silently drop Sep 7 releases (the inclusive end).
    synthetic_chart = {
        "Sep 6 Release": BoxOfficeRow(
            title="Sep 6 Release",
            cumulative_gross=1_000_000.0,
            release_date=date(2026, 9, 6),
        ),
        "Sep 7 Release": BoxOfficeRow(
            title="Sep 7 Release",
            cumulative_gross=2_000_000.0,
            release_date=date(2026, 9, 7),
        ),
        "Sep 8 Release": BoxOfficeRow(
            title="Sep 8 Release",
            cumulative_gross=3_000_000.0,
            release_date=date(2026, 9, 8),
        ),
    }

    windowed = in_window(synthetic_chart)

    assert "Sep 6 Release" in windowed
    assert "Sep 7 Release" in windowed
    assert "Sep 8 Release" not in windowed
