"""Tests for build.py orchestration helpers (the parts that don't need full pipeline I/O)."""

from datetime import date

from summer_movie_wager.ingest.boxoffice import BoxOfficeRow
from summer_movie_wager.render.build import (
    _build_raw_sim_fields,
    _count_non_zero_projections,
    _current_top_10,
    _normalize_movies,
    _project_all,
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
    projs = _project_all(movies, preopening, today=date(2026, 7, 5))
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
    projs = _project_all(movies, {}, today=date(2026, 7, 25))
    assert projs[0].median_in_window_gross == 66_078_506.0
    assert projs[0].sigma == 0.0
    assert projs[0].floor == 66_078_506.0
