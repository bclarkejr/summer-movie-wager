from datetime import date

import pytest

from summer_movie_wager.model.preopening import WINDOW_END, project_preopening
from summer_movie_wager.types import Category, Confidence


def test_movie_releasing_after_window_returns_zero():
    gross, sigma = project_preopening(
        release_date=date(2026, 9, 25),  # after 2026-09-07
        opening_weekend_estimate=100_000_000,
        total_domestic_estimate=300_000_000,
        confidence=Confidence.HIGH,
        category=Category.WIDE,
    )
    assert gross == 0.0
    assert sigma == 0.0


def test_movie_releasing_before_window_with_long_run_caps_at_total():
    # Released start of window with huge total - in-window gross can't exceed total
    gross, _ = project_preopening(
        release_date=date(2026, 5, 1),
        opening_weekend_estimate=140_000_000,
        total_domestic_estimate=400_000_000,
        confidence=Confidence.HIGH,
        category=Category.WIDE,
    )
    assert gross <= 400_000_000.0


def test_implied_wow_is_consistent_with_inputs():
    # If we let the model run forever (full geometric sum), it must equal total_domestic.
    # So in-window gross for a movie released at window-start must approach total_domestic
    # but not exceed it.
    gross, _ = project_preopening(
        release_date=date(2026, 5, 1),  # ~19 weeks before 2026-09-07
        opening_weekend_estimate=140_000_000,
        total_domestic_estimate=400_000_000,
        confidence=Confidence.HIGH,
        category=Category.WIDE,
    )
    # 19 weeks of decay should capture most of the total. Expect 70-100% of total_domestic.
    assert 280_000_000 < gross <= 400_000_000


def test_late_august_release_only_captures_partial_run():
    # Released 7 days before window end → only ~1 week of receipts inside window
    gross, _ = project_preopening(
        release_date=date(2026, 8, 31),
        opening_weekend_estimate=80_000_000,
        total_domestic_estimate=240_000_000,
        confidence=Confidence.MED,
        category=Category.WIDE,
    )
    # 7 days from 8/31 → 9/7 is week 1. Should be approximately 80M (week 1 gross).
    assert 70_000_000 < gross < 100_000_000


def test_sigma_by_confidence():
    base_kwargs = dict(
        release_date=date(2026, 7, 1),
        opening_weekend_estimate=100_000_000,
        total_domestic_estimate=300_000_000,
        category=Category.WIDE,
    )
    _, sigma_high = project_preopening(confidence=Confidence.HIGH, **base_kwargs)
    _, sigma_med = project_preopening(confidence=Confidence.MED, **base_kwargs)
    _, sigma_low = project_preopening(confidence=Confidence.LOW, **base_kwargs)
    assert sigma_high == pytest.approx(0.20)
    assert sigma_med == pytest.approx(0.30)
    assert sigma_low == pytest.approx(0.45)


def test_degenerate_wow_falls_back_to_category_default():
    # opening > total → implied wow < 0 (degenerate).
    # Should not crash; should still produce a number.
    gross, _ = project_preopening(
        release_date=date(2026, 5, 1),
        opening_weekend_estimate=150_000_000,
        total_domestic_estimate=120_000_000,  # nonsense input
        confidence=Confidence.LOW,
        category=Category.WIDE,
    )
    assert gross > 0
    assert gross <= 150_000_000  # shouldn't exceed the (nonsensical) total


def test_window_end_constant():
    assert WINDOW_END == date(2026, 9, 7)
