"""Tests for build.py orchestration helpers (the parts that don't need full pipeline I/O)."""

from summer_movie_wager.render.build import (
    _count_non_zero_projections,
    _current_top_10,
)
from summer_movie_wager.types import Projection


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
        Projection(movie_title=f"M{i}", median_in_window_gross=0.0, sigma=0.0)
        for i in range(20)
    ]
    assert _count_non_zero_projections(projections) == 0
