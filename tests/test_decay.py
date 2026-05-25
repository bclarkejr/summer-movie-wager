from datetime import date

import pytest

from summer_movie_wager.model.decay import project_decay, _week1_fraction_earned, _calibrate_week_1, _sum_weekly_remaining
from summer_movie_wager.types import Category


def test_just_opened_uses_default_wow_and_high_sigma():
    # Movie opened 6 days ago (Monday Apr 27) with $50M earned.
    # DOW weights for Mon–Sat = 0.79 → week_1_gross ≈ 63.3M.
    # Remaining of week 1 (Sunday = 0.21): +13.3M.
    # ~17 weeks remaining at wow=0.55: 63.3M * 1.22 ≈ 77.2M.
    # Total ≈ 140.5M → assertion window 120M–165M.
    gross, sigma = project_decay(
        release_date=date(2026, 4, 27),
        today=date(2026, 5, 3),
        cumulative_gross_to_date=50_000_000.0,
        category=Category.WIDE,
        observed_history=[],
    )
    assert 120_000_000 < gross < 165_000_000
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


def test_calibrate_week1_friday_open_four_days():
    # Fri May 22, 4 days elapsed (Fri–Mon, Memorial Day weekend)
    # Fri=0.21, Sat=0.26, Sun=0.21, Mon=0.08 → 0.76
    # week_1_gross should be 102M / 0.76 ≈ 134.2M
    w1 = _calibrate_week_1(
        release_date=date(2026, 5, 22),
        cumulative_gross_to_date=102_000_000.0,
        days_since_release=4,
        wow=0.55,
    )
    assert 133_000_000 < w1 < 136_000_000


def test_calibrate_week1_full_week_returns_cumulative():
    # After a full 7 days, week_1_gross == cumulative (no partial adjustment needed).
    w1 = _calibrate_week_1(
        release_date=date(2026, 5, 19),  # Monday open
        cumulative_gross_to_date=80_000_000.0,
        days_since_release=7,
        wow=0.55,
    )
    assert w1 == pytest.approx(80_000_000.0, rel=0.01)


def test_calibrate_week1_second_week_partial_uses_uniform():
    # Movie at day 10 (full_weeks=1, partial_days=3).
    # Fallback path: partial term uses 3/7 uniform prorating (not DOW weights).
    # denominator = wow^0 + wow^1 * (3/7) = 1.0 + 0.55 * 0.4286 = 1.2357
    # week_1_gross = 80M / 1.2357 ≈ 64.7M
    w1 = _calibrate_week_1(
        release_date=date(2026, 5, 1),  # Friday (day-of-week doesn't affect result here)
        cumulative_gross_to_date=80_000_000.0,
        days_since_release=10,
        wow=0.55,
    )
    assert 63_000_000 < w1 < 67_000_000


def test_projection_friday_open_not_inflated():
    # Mandalorian scenario: Fri May 22 open, 4 days in (Fri–Mon), $102M, WIDE.
    # Measuring "through Monday" = Tuesday date (4-day difference).
    # With the fix, total projection must be well under $300M.
    # Industry expectation is ~$200-250M for this opening pace.
    gross, sigma = project_decay(
        release_date=date(2026, 5, 22),
        today=date(2026, 5, 26),  # Tuesday: 4 days after Friday
        cumulative_gross_to_date=102_000_000.0,
        category=Category.WIDE,
        observed_history=[],
    )
    assert 280_000_000 < gross < 310_000_000, f"Projection {gross/1e6:.0f}M is outside expected range"
    assert gross > 102_000_000, "Projection must exceed current gross"
    assert sigma == pytest.approx(0.30)


def test_sum_weekly_remaining_week1_truncated_by_window():
    # Exercises the branch where WINDOW_END cuts off week 1 early.
    # Movie opened on a Thursday (2026-09-03), 2 days elapsed (Thu+Fri).
    # days_already_in_current_week=2, days_remaining=4 (Sat Sep 5 through Tue Sep 9,
    # but WINDOW_END=Sep 7, so days_remaining must respect that).
    # We test _sum_weekly_remaining directly with a short days_remaining that
    # cuts off the partial week before it finishes.
    #
    # Setup: Thu open, 2 days elapsed (Thu=0.09, Fri=0.21 → 0.30 earned).
    # Remaining of week 1 normally = 5 days. But days_remaining=3 cuts it at Sat+Sun+Mon.
    # Sat=0.26, Sun=0.21, Mon=0.08 → extra frac = 0.55.
    # week_1_gross * 0.55 = 100M * 0.55 = 55M
    result = _sum_weekly_remaining(
        week_1_gross=100_000_000.0,
        wow=0.55,
        weeks_already_played=0,
        days_already_in_current_week=2,
        days_remaining=3,
        release_date=date(2026, 9, 3),  # Thursday
    )
    # Sat(0.26) + Sun(0.21) + Mon(0.08) = 0.55 of week_1_gross
    assert result == pytest.approx(55_000_000, rel=0.01)
