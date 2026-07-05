"""Tests for build.py orchestration helpers (the parts that don't need full pipeline I/O)."""

from datetime import date

from summer_movie_wager.render.build import (
    _build_raw_sim_fields,
    _count_non_zero_projections,
    _current_top_10,
    _project_all,
)
from summer_movie_wager.types import Category, MovieStatus, PreopeningEntry, Projection


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
