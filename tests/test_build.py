"""Tests for build.py orchestration helpers (the parts that don't need full pipeline I/O)."""

from datetime import date

import pytest

from summer_movie_wager.ingest.boxoffice import BoxOfficeRow, in_window
from summer_movie_wager.render.build import (
    _apply_chart_aliases,
    _build_raw_sim_fields,
    _count_non_zero_projections,
    _current_top_10,
    _normalize_movies,
    _project_all,
    _require_nonempty_chart,
    _require_nonempty_windowed_chart,
    _resolve_grosses,
)
from summer_movie_wager.types import (
    Category,
    MovieStatus,
    PlayerPicks,
    PreopeningEntry,
    Projection,
    SiteSnapshot,
)


def test_project_all_treats_incomplete_preopening_entry_as_no_projection():
    # An entry with an opening estimate but no total/confidence (a half-filled
    # placeholder) must project 0, not crash inside project_preopening.
    movies = {
        "Half Entry": {
            "title": "Half Entry",
            "release_date": date(2026, 7, 10),
            "status": MovieStatus.PRE_RELEASE,
            "category": Category.WIDE,
            "cumulative": 0.0,
        }
    }
    preopening = {
        "Half Entry": PreopeningEntry(
            release_date=date(2026, 7, 10),
            opening_weekend_estimate=50_000_000.0,
        )
    }
    projs = _project_all(movies, preopening, today=date(2026, 7, 5), history={})
    assert projs[0].median_in_window_gross == 0.0
    assert projs[0].sigma == 0.0


def test_current_top_10_excludes_zero_gross_movies():
    grosses = {"A": 100.0, "B": 50.0, "C": 0.0, "D": 0.0}
    assert _current_top_10(grosses) == ["A", "B"]


def test_current_top_10_returns_at_most_ten():
    grosses = {f"M{i}": float(100 - i) for i in range(15)}
    out = _current_top_10(grosses)
    assert len(out) == 10
    assert out[0] == "M0"


def test_current_top_10_handles_empty():
    assert _current_top_10({}) == []


def test_count_non_zero_projections_only_counts_positive_medians():
    projections = [
        Projection(movie_title="A", median_in_window_gross=100.0, sigma=0.2),
        Projection(movie_title="B", median_in_window_gross=0.0, sigma=0.0),
        Projection(movie_title="C", median_in_window_gross=50.0, sigma=0.3),
    ]
    assert _count_non_zero_projections(projections) == 2


def test_count_non_zero_projections_zero_when_all_zero():
    projections = [
        Projection(movie_title=f"M{i}", median_in_window_gross=0.0, sigma=0.0) for i in range(20)
    ]
    assert _count_non_zero_projections(projections) == 0


def test_in_theaters_row_band_respects_floor():
    # _build_movie_rows should produce p10 >= floor and a tight band for a
    # deep-run film whose median is just above its banked gross.
    import math

    from summer_movie_wager.render.build import _build_movie_rows
    from summer_movie_wager.types import MovieStatus, Projection

    movies = {
        "The Devil Wears Prada 2": {
            "title": "The Devil Wears Prada 2",
            "release_date": __import__("datetime").date(2026, 5, 1),
            "status": MovieStatus.IN_THEATERS,
            "category": __import__("summer_movie_wager.types", fromlist=["Category"]).Category.WIDE,
            "cumulative": 219_602_888.0,
        }
    }
    projections = [
        Projection(
            movie_title="The Devil Wears Prada 2",
            median_in_window_gross=221_000_000.0,
            sigma=0.10,
            floor=219_602_888.0,
        )
    ]
    rows = _build_movie_rows(movies, projections)
    row = rows[0]
    assert row.p10 >= 219_602_888.0
    assert row.p90 <= 219_602_888.0 + 10_000_000
    # exact formula check
    remaining = 221_000_000.0 - 219_602_888.0
    assert math.isclose(row.p90, 219_602_888.0 + remaining * math.exp(1.2816 * 0.10))


def test_raw_has_winning_scenarios_when_forecast_available():
    from summer_movie_wager.model.simulate import SimulationResult
    from summer_movie_wager.types import WinningScenario

    ws = WinningScenario(
        films=["A"] * 10,
        grid={"alice": [0] * 10},
        totals={"alice": 42},
        win_pct=100.0,
        margin=5,
    )
    sim = SimulationResult(
        win_prob={"alice": 1.0},
        tie_prob={"alice": 0.0},
        median_final_pts={"alice": 100.0},
        p10_final_pts={"alice": 90.0},
        p90_final_pts={"alice": 110.0},
        winning_scenarios={"alice": ws},
    )
    raw: dict = {}
    _build_raw_sim_fields(raw, sim, {"alice": object()}, True, "")
    assert "winning_scenarios" in raw
    entry = raw["winning_scenarios"]["alice"]
    assert {"films", "grid", "totals", "win_pct", "margin"} <= set(entry)


def test_raw_winning_scenarios_all_null_when_forecast_off():
    raw: dict = {}
    _build_raw_sim_fields(raw, None, {"alice": object(), "bob": object()}, False, "not enough")
    assert set(raw["winning_scenarios"].values()) == {None}


def test_forecast_history_payload_dedupes_and_gaps(tmp_path):
    from summer_movie_wager.render.build import _build_forecast_history_payload

    p = tmp_path / "forecast_history.jsonl"
    rows = [
        '{"date": "2026-05-11", "player": "alice", "win_prob": 0.10, '
        '"median_final_pts": 50, "p10": 40, "p90": 60}',
        '{"date": "2026-05-11", "player": "alice", "win_prob": 0.20, '
        '"median_final_pts": 50, "p10": 40, "p90": 60}',
        '{"date": "2026-05-11", "player": "bob", "win_prob": 0.30, '
        '"median_final_pts": 50, "p10": 40, "p90": 60}',
        '{"date": "2026-05-18", "player": "bob", "win_prob": 0.40, '
        '"median_final_pts": 50, "p10": 40, "p90": 60}',
    ]
    p.write_text("\n".join(rows) + "\n")
    payload = _build_forecast_history_payload(p)
    assert payload["dates"] == ["2026-05-11", "2026-05-18"]
    # same-day re-run wins; alice has no 05-18 row so her line gaps with None
    assert payload["series"][0] == {"player": "alice", "win_prob": [0.20, None]}
    assert payload["series"][1] == {"player": "bob", "win_prob": [0.30, 0.40]}


def test_forecast_history_payload_empty_when_file_missing(tmp_path):
    from summer_movie_wager.render.build import _build_forecast_history_payload

    assert _build_forecast_history_payload(tmp_path / "nope.jsonl") == {"dates": [], "series": []}


def _row(title, gross, release=date(2026, 5, 8)):
    return BoxOfficeRow(title=title, cumulative_gross=gross, release_date=release)


def test_resolve_grosses_prefers_the_live_chart():
    chart = {"Toy Story 5": _row("Toy Story 5", 441_455_658.0, date(2026, 6, 19))}
    history = {"Toy Story 5": [(date(2026, 7, 20), 429_878_644.0)]}
    grosses, carried = _resolve_grosses(chart, history, today=date(2026, 7, 25))
    assert grosses["Toy Story 5"] == 441_455_658.0
    assert carried == set()


def test_resolve_grosses_carries_forward_a_film_that_left_the_chart():
    # The Sheep Detectives is the reason this exists: it fell out of the
    # play-along top 13 and must not collapse to zero.
    chart = {}
    history = {
        "The Sheep Detectives": [
            (date(2026, 7, 13), 66_042_291.0),
            (date(2026, 7, 20), 66_078_506.0),
        ]
    }
    grosses, carried = _resolve_grosses(chart, history, today=date(2026, 7, 25))
    assert grosses["The Sheep Detectives"] == 66_078_506.0
    assert carried == {"The Sheep Detectives"}


def test_resolve_grosses_never_lets_a_gross_go_down():
    chart = {"Obsession": _row("Obsession", 240_017_600.0, date(2026, 5, 15))}
    history = {"Obsession": [(date(2026, 7, 20), 258_387_140.0)]}
    grosses, _ = _resolve_grosses(chart, history, today=date(2026, 7, 25))
    assert grosses["Obsession"] == 258_387_140.0


def test_resolve_grosses_still_uses_the_chart_the_day_after_labor_day():
    # Run on Sep 8, the chart reports through Sep 7 -- exactly the wager cutoff.
    chart = {"Toy Story 5": _row("Toy Story 5", 460_000_000.0, date(2026, 6, 19))}
    history = {"Toy Story 5": [(date(2026, 8, 31), 455_000_000.0)]}
    grosses, _ = _resolve_grosses(chart, history, today=date(2026, 9, 8))
    assert grosses["Toy Story 5"] == 460_000_000.0


def test_resolve_grosses_freezes_after_labor_day():
    # Run on Sep 10, the chart includes Sep 8-9 gross, which the wager excludes.
    chart = {"Toy Story 5": _row("Toy Story 5", 470_000_000.0, date(2026, 6, 19))}
    history = {
        "Toy Story 5": [
            (date(2026, 9, 7), 461_000_000.0),
            (date(2026, 9, 9), 468_000_000.0),
        ]
    }
    grosses, _ = _resolve_grosses(chart, history, today=date(2026, 9, 10))
    assert grosses["Toy Story 5"] == 461_000_000.0


def test_resolve_grosses_ignores_history_after_the_cutoff():
    chart = {}
    history = {
        "Backrooms": [
            (date(2026, 9, 7), 200_000_000.0),
            (date(2026, 9, 14), 201_000_000.0),
        ]
    }
    grosses, _ = _resolve_grosses(chart, history, today=date(2026, 9, 20))
    assert grosses["Backrooms"] == 200_000_000.0


def test_resolve_grosses_uses_highest_gross_not_latest_date():
    # A revision (or a late-arriving lower report) recorded after an earlier,
    # higher observation must not pull the resolved gross back down. max() on
    # (date, gross) tuples picks the greatest DATE first -- this pins the
    # highest GROSS on or before the cutoff instead.
    chart = {}
    history = {
        "X": [
            (date(2026, 7, 10), 100_000_000.0),
            (date(2026, 7, 20), 90_000_000.0),
        ]
    }
    grosses, _ = _resolve_grosses(chart, history, today=date(2026, 7, 25))
    assert grosses["X"] == 100_000_000.0


def test_resolve_grosses_carried_titles_correct_during_freeze():
    # After the freeze, chart VALUES are ignored but chart MEMBERSHIP still
    # tells us whether a title is actually on the live chart. A title present
    # in chart must never be reported as carried, even past the cutoff.
    chart = {"Toy Story 5": _row("Toy Story 5", 999_000_000.0, date(2026, 6, 19))}
    history = {"Toy Story 5": [(date(2026, 9, 7), 461_000_000.0)]}
    grosses, carried = _resolve_grosses(chart, history, today=date(2026, 9, 20))
    assert grosses["Toy Story 5"] == 461_000_000.0
    assert "Toy Story 5" not in carried


def test_resolve_grosses_freezes_exactly_on_sep_9():
    # Sep 9 is the exact flip day: the chart would report through Sep 8, one
    # day past WINDOW_END (Sep 7), so it is already frozen -- the live chart's
    # gross must not leak in.
    chart = {"Toy Story 5": _row("Toy Story 5", 470_000_000.0, date(2026, 6, 19))}
    history = {"Toy Story 5": [(date(2026, 9, 7), 461_000_000.0)]}
    grosses, _ = _resolve_grosses(chart, history, today=date(2026, 9, 9))
    assert grosses["Toy Story 5"] == 461_000_000.0


def test_resolve_grosses_handles_out_of_order_history():
    # History rows aren't guaranteed to arrive in chronological order; the
    # resolved gross must still be the max, not the last element.
    chart = {}
    history = {
        "X": [
            (date(2026, 7, 20), 90_000_000.0),
            (date(2026, 7, 10), 100_000_000.0),
        ]
    }
    grosses, _ = _resolve_grosses(chart, history, today=date(2026, 7, 25))
    assert grosses["X"] == 100_000_000.0


def test_resolve_grosses_keeps_the_history_row_written_the_day_after_labor_day():
    # The Sep 8 row was written from a chart reporting through Sep 7 -- it holds
    # the exact through-Labor-Day number and is the answer for every later run.
    # Dropping it regresses the final standings to the previous week's, on the
    # most likely click of the season ("show me the final result").
    chart = {"Toy Story 5": _row("Toy Story 5", 500_000_000.0, date(2026, 6, 19))}
    history = {
        "Toy Story 5": [
            (date(2026, 8, 31), 400_000_000.0),
            (date(2026, 9, 8), 480_000_000.0),
        ]
    }
    grosses, _ = _resolve_grosses(chart, history, today=date(2026, 9, 9))
    assert grosses["Toy Story 5"] == 480_000_000.0
    # ...and it stays the answer a week later, not just on the flip day.
    grosses, _ = _resolve_grosses(chart, history, today=date(2026, 9, 14))
    assert grosses["Toy Story 5"] == 480_000_000.0


def test_resolve_grosses_drops_the_history_row_written_two_days_after_labor_day():
    # The other side of the same boundary: a row dated Sep 9 was written from a
    # chart reporting through Sep 8, so it contains gross the wager excludes.
    chart = {"Toy Story 5": _row("Toy Story 5", 500_000_000.0, date(2026, 6, 19))}
    history = {
        "Toy Story 5": [
            (date(2026, 9, 8), 480_000_000.0),
            (date(2026, 9, 9), 490_000_000.0),
        ]
    }
    grosses, _ = _resolve_grosses(chart, history, today=date(2026, 9, 14))
    assert grosses["Toy Story 5"] == 480_000_000.0


def test_resolve_grosses_rejects_a_carried_title_above_the_chart_floor():
    # Box Office Mojo renamed Moana mid-season. The old key survives in history
    # (frozen, "closed") while the new key arrives live from the chart, and both
    # would compete for a slot in the scoring top 10.
    chart = {
        "Moana (2026)": _row("Moana (2026)", 95_000_000.0, date(2026, 7, 10)),
        "Tiny Film": _row("Tiny Film", 468_400.0, date(2026, 5, 15)),
    }
    history = {"Moana": [(date(2026, 7, 20), 81_019_028.0)]}
    with pytest.raises(ValueError, match="Moana"):
        _resolve_grosses(chart, history, today=date(2026, 7, 25))


def test_resolve_grosses_allows_a_carried_title_below_the_chart_floor():
    # The legitimate case: the film really did fade under the 200-row chart's
    # floor, so it is carried forward from history without complaint.
    chart = {"Tiny Film": _row("Tiny Film", 468_400.0, date(2026, 5, 15))}
    history = {"Faded": [(date(2026, 7, 20), 400_000.0)]}
    grosses, carried = _resolve_grosses(chart, history, today=date(2026, 7, 25))
    assert carried == {"Faded"}
    assert grosses["Faded"] == 400_000.0


def test_resolve_grosses_carry_check_does_not_fire_during_the_post_labor_day_freeze():
    # After Labor Day the chart's VALUES are ignored but its membership still
    # decides what is carried. A frozen carried gross is by construction no
    # larger than the film's live total, so the freeze cannot make this fire.
    chart = {"Tiny Film": _row("Tiny Film", 900_000.0, date(2026, 5, 15))}
    history = {"Faded": [(date(2026, 9, 7), 500_000.0)]}
    grosses, carried = _resolve_grosses(chart, history, today=date(2026, 9, 20))
    assert carried == {"Faded"}
    assert grosses["Faded"] == 500_000.0


def test_apply_chart_aliases_merges_a_renamed_chart_title_with_its_history():
    # (a) one key, (b) no double count in the top 10, (c) no impossible-carry raise.
    chart = _apply_chart_aliases(
        {
            "Moana (2026)": _row("Moana (2026)", 95_069_653.0, date(2026, 7, 10)),
            "Tiny Film": _row("Tiny Film", 468_400.0, date(2026, 5, 15)),
        },
        {"Moana (2026)": {"alias_of": "Moana"}},
    )
    assert set(chart) == {"Moana", "Tiny Film"}
    assert chart["Moana"].title == "Moana"

    history = {"Moana": [(date(2026, 7, 20), 81_019_028.0)]}
    grosses, carried = _resolve_grosses(chart, history, today=date(2026, 7, 25))
    assert grosses["Moana"] == 95_069_653.0
    assert carried == set()
    assert _current_top_10(grosses) == ["Moana", "Tiny Film"]


def test_apply_chart_aliases_collapses_both_titles_onto_the_higher_gross():
    # The chart briefly carrying old and new titles at once must not survive as
    # two films; grosses only go up, so the bigger number is the current one.
    chart = _apply_chart_aliases(
        {
            "Moana": _row("Moana", 81_019_028.0, date(2026, 7, 10)),
            "Moana (2026)": _row("Moana (2026)", 95_069_653.0, date(2026, 7, 10)),
        },
        {"Moana (2026)": {"alias_of": "Moana"}},
    )
    assert set(chart) == {"Moana"}
    assert chart["Moana"].cumulative_gross == 95_069_653.0


def test_apply_chart_aliases_is_a_no_op_without_overrides():
    chart = {"Toy Story 5": _row("Toy Story 5", 441_455_658.0, date(2026, 6, 19))}
    assert _apply_chart_aliases(chart, {}) == chart


def _snapshot(picks_titles):
    picks = PlayerPicks(
        username="bclarke",
        ranked=picks_titles[:10],
        dark_horses=picks_titles[10:13],
    )
    return SiteSnapshot(
        captured_at=date(2026, 7, 25),
        players={"bclarke": picks},
        cumulative_grosses={},
        site_reported_points={},
    )


_THIRTEEN = [f"Film {i}" for i in range(13)]


def test_normalize_marks_a_carried_film_closed():
    snap = _snapshot(_THIRTEEN)
    movies = _normalize_movies(
        snap,
        {},
        {},
        grosses={"The Sheep Detectives": 66_078_506.0},
        chart={},
        carried={"The Sheep Detectives"},
        today=date(2026, 7, 25),
    )
    m = movies["The Sheep Detectives"]
    assert m["status"] == MovieStatus.CLOSED
    assert m["cumulative"] == 66_078_506.0


def test_normalize_takes_release_date_from_the_chart():
    snap = _snapshot(_THIRTEEN)
    chart = {
        "Moana": BoxOfficeRow(
            title="Moana", cumulative_gross=95_069_653.0, release_date=date(2026, 7, 10)
        )
    }
    movies = _normalize_movies(
        snap,
        {},
        {},
        grosses={"Moana": 95_069_653.0},
        chart=chart,
        carried=set(),
        today=date(2026, 7, 25),
    )
    assert movies["Moana"]["release_date"] == date(2026, 7, 10)
    assert movies["Moana"]["status"] == MovieStatus.IN_THEATERS


def test_closed_film_projects_its_final_gross():
    movies = {
        "The Sheep Detectives": {
            "title": "The Sheep Detectives",
            "release_date": date(2026, 5, 8),
            "status": MovieStatus.CLOSED,
            "category": Category.WIDE,
            "cumulative": 66_078_506.0,
        }
    }
    projs = _project_all(movies, {}, today=date(2026, 7, 25), history={})
    assert projs[0].median_in_window_gross == 66_078_506.0
    assert projs[0].sigma == 0.0
    assert projs[0].floor == 66_078_506.0


def test_require_nonempty_chart_raises_on_empty_chart():
    # An empty chart means the scrape broke (markup changed, bad fetch, etc.) --
    # it must fail loudly rather than being processed as "every film has closed".
    with pytest.raises(ValueError, match="Box Office Mojo"):
        _require_nonempty_chart({})


def test_require_nonempty_chart_passes_through_a_real_chart():
    chart = {"Toy Story 5": _row("Toy Story 5", 441_455_658.0, date(2026, 6, 19))}
    assert _require_nonempty_chart(chart) is chart


def test_require_nonempty_windowed_chart_raises_on_empty_chart():
    with pytest.raises(ValueError, match="filtered out"):
        _require_nonempty_windowed_chart({})


def test_require_nonempty_windowed_chart_passes_through_a_real_chart():
    chart = {"Toy Story 5": _row("Toy Story 5", 441_455_658.0, date(2026, 6, 19))}
    assert _require_nonempty_windowed_chart(chart) is chart


def test_require_nonempty_windowed_chart_catches_a_raw_chart_that_all_flags_rerelease():
    # Reproduces the reported gap: a raw chart that passes
    # `_require_nonempty_chart` (it has rows) but where every row is flagged as
    # a re-release -- e.g. Box Office Mojo wraps release cells in a layout <div>
    # that `parse_year_chart`'s re-release detection mistakes for a re-release
    # note. `in_window()` then drops every row, and without this guard that
    # empty windowed chart would sail through unnoticed.
    raw = {
        "Toy Story 5": BoxOfficeRow(
            title="Toy Story 5",
            cumulative_gross=441_455_658.0,
            release_date=date(2026, 6, 19),
            is_rerelease=True,
        )
    }
    assert _require_nonempty_chart(raw) is raw
    windowed = in_window(raw)
    assert windowed == {}
    with pytest.raises(ValueError, match="filtered out"):
        _require_nonempty_windowed_chart(windowed)


def test_normalize_movies_unions_picks_with_top_chart_contenders():
    # 29 chart films ranked purely by gross, plus a picked film (Power Ballad,
    # modeled on its real chart rank ~104 with $2.6M) that sits far below the
    # top-25 cut. If candidates were built by intersecting picks with the chart
    # contenders instead of unioning them, Power Ballad would vanish here.
    chart = {}
    for i in range(29):
        title = f"Chart Film {i}"
        chart[title] = _row(title, 200_000_000.0 - i * 1_000_000.0, date(2026, 6, 1))
    chart["Power Ballad"] = _row("Power Ballad", 2_600_000.0, date(2026, 5, 20))
    grosses = {title: row.cumulative_gross for title, row in chart.items()}

    snap = _snapshot(
        ["Power Ballad"]
        + [f"Extra Pick {i}" for i in range(9)]
        + [f"Extra DH {i}" for i in range(3)]
    )
    movies = _normalize_movies(
        snap, {}, {}, grosses=grosses, chart=chart, carried=set(), today=date(2026, 7, 25)
    )

    # Picked long-shot survives despite ranking far below the top 25.
    assert "Power Ballad" in movies
    # Top of the chart (rank 1, and rank 25 exactly at the cut) is included.
    assert "Chart Film 0" in movies
    assert "Chart Film 24" in movies
    # Unpicked film just past the cut (rank 26) is excluded by the truncation.
    assert "Chart Film 25" not in movies


def test_normalize_movies_unions_carried_titles():
    # A film that fell off the chart (carried forward from history) must appear
    # even though it is neither picked, nor in preopening, nor a chart contender.
    snap = _snapshot(_THIRTEEN)
    movies = _normalize_movies(
        snap,
        {},
        {},
        grosses={"The Sheep Detectives": 66_078_506.0},
        chart={},
        carried={"The Sheep Detectives"},
        today=date(2026, 7, 25),
    )
    assert "The Sheep Detectives" in movies


def test_normalize_film_released_today_with_gross_is_in_theaters():
    # release == today falls past the `> today` PRE_RELEASE branch and must
    # reach IN_THEATERS, not get caught by the CLOSED check ahead of it.
    today = date(2026, 7, 25)
    snap = _snapshot(_THIRTEEN)
    chart = {"New Today": _row("New Today", 5_000_000.0, today)}
    movies = _normalize_movies(
        snap, {}, {}, grosses={"New Today": 5_000_000.0}, chart=chart, carried=set(), today=today
    )
    assert movies["New Today"]["status"] == MovieStatus.IN_THEATERS


def test_normalize_unreleased_film_stays_pre_release():
    today = date(2026, 7, 25)
    snap = _snapshot(["Not Yet Released", *_THIRTEEN[1:]])
    overrides = {"Not Yet Released": {"release_date": "2026-08-01"}}
    movies = _normalize_movies(
        snap, overrides, {}, grosses={}, chart={}, carried=set(), today=today
    )
    assert movies["Not Yet Released"]["status"] == MovieStatus.PRE_RELEASE


def test_normalize_zero_gross_film_stays_pre_release():
    today = date(2026, 7, 25)
    snap = _snapshot(["No Gross Yet", *_THIRTEEN[1:]])
    overrides = {"No Gross Yet": {"release_date": "2026-07-01"}}
    movies = _normalize_movies(
        snap, overrides, {}, grosses={}, chart={}, carried=set(), today=today
    )
    assert movies["No Gross Yet"]["status"] == MovieStatus.PRE_RELEASE


def _catalog_for(titles):
    """A projected catalog for `titles`, grossing strictly descending in list order.

    Returns (projections, movie_rows) — the same pair main() hands to
    _build_player_details, so film N in `titles` lands at catalog rank N+1.
    """
    from summer_movie_wager.render.build import _build_movie_rows

    movies = {
        t: {
            "title": t,
            "release_date": date(2026, 6, 1),
            "status": MovieStatus.IN_THEATERS,
            "category": Category.WIDE,
            "cumulative": 0.0,
        }
        for t in titles
    }
    projections = [
        Projection(movie_title=t, median_in_window_gross=float(1300 - 100 * i), sigma=0.1)
        for i, t in enumerate(titles)
    ]
    return projections, _build_movie_rows(movies, projections)


def test_projected_rank_covers_films_outside_the_top_10():
    # projected_rank is the film's row number in the Movies table, not its
    # position inside the projected top 10. A pick that misses the top 10 scores
    # nothing but still carries a rank, so the per-player table can show "#11".
    from summer_movie_wager.render.build import _build_player_details

    snap = _snapshot(_THIRTEEN)
    projections, movie_rows = _catalog_for(_THIRTEEN)

    details = _build_player_details(snap, projections, {"bclarke": 0}, None, movie_rows)

    assert [p.projected_rank for p in details[0].ranked] == list(range(1, 11))
    # Film 10 is the first dark horse and finishes 11th — outside the top 10.
    dh = details[0].dark_horses[0]
    assert dh.projected_rank == 11
    assert dh.projected_pts == 0


def test_pick_gross_matches_the_movie_catalog():
    # The dollar figure in a player's table must be the same number the Movies
    # table prints for that film — both now come from movie_rows.
    from summer_movie_wager.render.build import _build_player_details

    snap = _snapshot(_THIRTEEN)
    projections, movie_rows = _catalog_for(_THIRTEEN)

    details = _build_player_details(snap, projections, {"bclarke": 0}, None, movie_rows)

    by_title = {row.title: row.median_in_window_gross for row in movie_rows}
    for pick in details[0].ranked + details[0].dark_horses:
        assert pick.projected_gross == by_title[pick.title]
