from datetime import date

import pytest

from summer_movie_wager.model.decay import project_decay, _week1_fraction_earned, _calibrate_week_1
from summer_movie_wager.types import Category


def test_just_opened_uses_default_wow_and_high_sigma():
    # Movie opened 6 days ago with 50M earned. With default wow=0.55, week_1_gross calibrates
    # so that ~6/7 of week 1 = 50M → week_1 ≈ 58.3M. Project full window.
    gross, sigma = project_decay(
        release_date=date(2026, 4, 27),
        today=date(2026, 5, 3),
        cumulative_gross_to_date=50_000_000.0,
        category=Category.WIDE,
        observed_history=[],
    )
    # Movie has ~18 weeks of window remaining. With wow=0.55:
    # week_1 ≈ 58M, sum_{k=0..18} 58M * 0.55^k ≈ 58M / 0.45 ≈ 129M
    assert 100_000_000 < gross < 160_000_000
    assert sigma == pytest.approx(0.30)


def test_six_weeks_in_uses_low_sigma():
    gross, sigma = project_decay(
        release_date=date(2026, 5, 1),
        today=date(2026, 6, 12),  # 6 weeks later
        cumulative_gross_to_date=300_000_000.0,
        category=Category.WIDE,
        observed_history=[],
    )
    assert sigma == pytest.approx(0.10)
    assert gross > 300_000_000  # at minimum the cumulative is locked in


def test_modeled_cumulative_matches_scraped_cumulative():
    # The calibration step must set week_1_gross so modeled cumulative-to-date == input.
    # We test this indirectly: gross(release_date, today=window_end) == cumulative_gross_to_date
    gross, _ = project_decay(
        release_date=date(2026, 5, 1),
        today=date(2026, 9, 7),  # window_end
        cumulative_gross_to_date=250_000_000.0,
        category=Category.WIDE,
        observed_history=[],
    )
    assert gross == pytest.approx(250_000_000.0, rel=0.01)


def test_observed_history_pulls_wow_toward_observed():
    # Movie observed dropping 30% week-over-week (wow=0.70) for 6 snapshots.
    # Default is 0.55. Blended fully observed (n=6 → weight 1.0) → wow=0.70.
    history = [
        (date(2026, 5, 8), 60_000_000),   # week 1 cumulative
        (date(2026, 5, 15), 102_000_000),  # +42M (week 2)
        (date(2026, 5, 22), 131_400_000),  # +29.4M (week 3)
        (date(2026, 5, 29), 152_000_000),  # +20.6M (week 4)
        (date(2026, 6, 5), 166_400_000),   # +14.4M (week 5)
        (date(2026, 6, 12), 176_500_000),  # +10.1M (week 6)
    ]
    gross_observed, _ = project_decay(
        release_date=date(2026, 5, 1),
        today=date(2026, 6, 12),
        cumulative_gross_to_date=176_500_000.0,
        category=Category.WIDE,
        observed_history=history,
    )
    gross_default, _ = project_decay(
        release_date=date(2026, 5, 1),
        today=date(2026, 6, 12),
        cumulative_gross_to_date=176_500_000.0,
        category=Category.WIDE,
        observed_history=[],  # no history, use default 0.55
    )
    # Observed wow is higher (0.70 > 0.55 default) → leg-out is bigger → larger total
    assert gross_observed > gross_default


def test_animated_family_uses_higher_default_wow():
    gross_animated, _ = project_decay(
        release_date=date(2026, 6, 19),
        today=date(2026, 6, 26),
        cumulative_gross_to_date=120_000_000.0,
        category=Category.ANIMATED_FAMILY,
        observed_history=[],
    )
    gross_wide, _ = project_decay(
        release_date=date(2026, 6, 19),
        today=date(2026, 6, 26),
        cumulative_gross_to_date=120_000_000.0,
        category=Category.WIDE,
        observed_history=[],
    )
    # Higher wow (0.65 vs 0.55) → slower decay → larger projected total
    assert gross_animated > gross_wide


def test_today_after_window_end_returns_cumulative():
    gross, _ = project_decay(
        release_date=date(2026, 5, 1),
        today=date(2026, 9, 30),  # past window end
        cumulative_gross_to_date=275_000_000.0,
        category=Category.WIDE,
        observed_history=[],
    )
    assert gross == pytest.approx(275_000_000.0, rel=0.01)


def test_today_before_release_raises():
    with pytest.raises(ValueError):
        project_decay(
            release_date=date(2026, 6, 1),
            today=date(2026, 5, 15),
            cumulative_gross_to_date=0.0,
            category=Category.WIDE,
            observed_history=[],
        )


def test_release_date_defaults_to_today_projects_forward():
    # When a movie has no known release date, _normalize_movies defaults release_date=today.
    # days_since_release == 0 but cumulative > 0 (opening weekend already captured).
    # The projection must exceed the current gross — it should not be capped at the current gross.
    today = date(2026, 5, 4)
    gross, sigma = project_decay(
        release_date=today,
        today=today,
        cumulative_gross_to_date=77_000_000.0,
        category=Category.WIDE,
        observed_history=[],
    )
    assert gross > 77_000_000, "projection must exceed current gross when movie is still running"
    assert sigma == pytest.approx(0.30)


def test_week1_fraction_earned_thursday_open_four_days():
    # Mandalorian scenario: opened Thursday May 21, 4 days elapsed (Thu–Sun)
    # Thu=0.09, Fri=0.21, Sat=0.26, Sun=0.21 → 0.77
    frac = _week1_fraction_earned(date(2026, 5, 21), 4)
    assert frac == pytest.approx(0.77, abs=0.001)


def test_week1_fraction_earned_friday_open_three_days():
    # Standard Friday opening: Fri=0.21, Sat=0.26, Sun=0.21 → 0.68
    frac = _week1_fraction_earned(date(2026, 5, 22), 3)
    assert frac == pytest.approx(0.68, abs=0.001)


def test_week1_fraction_earned_full_week_is_one():
    frac = _week1_fraction_earned(date(2026, 5, 21), 7)
    assert frac == pytest.approx(1.0, abs=0.001)


def test_week1_fraction_earned_zero_days_is_zero():
    frac = _week1_fraction_earned(date(2026, 5, 21), 0)
    assert frac == pytest.approx(0.0, abs=0.001)


def test_week1_fraction_earned_monday_open_four_days():
    # Monday open: Mon=0.08, Tue=0.07, Wed=0.08, Thu=0.09 → 0.32
    # Tests that the % 7 wrap in the index calculation is correct
    frac = _week1_fraction_earned(date(2026, 5, 25), 4)
    assert frac == pytest.approx(0.32, abs=0.001)


def test_calibrate_week1_thursday_open_four_days():
    # Mandalorian: opened Thu May 22, 4 days elapsed, $102M cumulative.
    # Thu+Fri+Sat+Sun = 0.09+0.21+0.26+0.21 = 0.77 of week 1.
    # week_1_gross should be 102M / 0.77 ≈ 132.5M (not 178M from uniform 4/7).
    w1 = _calibrate_week_1(
        release_date=date(2026, 5, 22),
        cumulative_gross_to_date=102_000_000.0,
        days_since_release=4,
        wow=0.55,
    )
    assert 130_000_000 < w1 < 135_000_000


def test_calibrate_week1_full_week_returns_cumulative():
    # After a full 7 days, week_1_gross == cumulative (no partial adjustment needed).
    w1 = _calibrate_week_1(
        release_date=date(2026, 5, 19),  # Monday open
        cumulative_gross_to_date=80_000_000.0,
        days_since_release=7,
        wow=0.55,
    )
    assert w1 == pytest.approx(80_000_000.0, rel=0.01)
