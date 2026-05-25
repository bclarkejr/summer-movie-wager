"""In-theaters projection (Mode A) — weekly decay model with optional history blending."""

from datetime import date

from summer_movie_wager.model.preopening import WINDOW_END
from summer_movie_wager.types import Category

_DEFAULT_WOW: dict[Category, float] = {
    Category.WIDE: 0.55,
    Category.ANIMATED_FAMILY: 0.65,
}

# Fraction of a typical week's gross earned on each day (Mon=0 … Sun=6).
# Weights sum to 1.0. Source: industry box-office day-of-week distribution.
_DOW_WEIGHTS: list[float] = [0.08, 0.07, 0.08, 0.09, 0.21, 0.26, 0.21]


def _week1_fraction_earned(release_date: date, days_in_partial_week: int) -> float:
    """Fraction of week-1 gross expected to have been earned in the first N days.

    Uses day-of-week weights so that opening-weekend days (Fri/Sat/Sun) count
    for their true share (~68%) rather than a uniform 3/7 = 43%.
    Result is always in [0, 1] because weights sum to 1.0 and `days` is bounded to [0, 7].
    """
    if days_in_partial_week <= 0:
        return 0.0
    days = min(days_in_partial_week, 7)
    dow_start = release_date.weekday()  # 0=Mon … 6=Sun
    return sum(_DOW_WEIGHTS[(dow_start + i) % 7] for i in range(days))


def project_decay(
    *,
    release_date: date,
    today: date,
    cumulative_gross_to_date: float,
    category: Category,
    observed_history: list[tuple[date, float]],
) -> tuple[float, float]:
    """Project total in-window gross given current state and optional history.

    Returns (projected_total_in_window_gross, sigma).
    """
    if today < release_date:
        raise ValueError(f"today ({today}) is before release_date ({release_date})")

    wow = _resolve_wow(category, observed_history)
    weeks_observed = (today - release_date).days // 7
    sigma = _sigma_from_weeks(weeks_observed)

    # If today is at or past window end, no further projection needed.
    if today >= WINDOW_END:
        return cumulative_gross_to_date, sigma

    days_since_release = (today - release_date).days
    days_remaining = (WINDOW_END - today).days

    # Degenerate case: release_date defaulted to today but we already have gross data
    # (movie opened over a prior weekend with no known release date in our records).
    # Treat the current cumulative as the opening-week gross and project from week 2.
    if days_since_release == 0 and cumulative_gross_to_date > 0:
        projected_remaining = _sum_weekly_remaining(
            week_1_gross=cumulative_gross_to_date,
            wow=wow,
            weeks_already_played=1,
            days_already_in_current_week=0,
            days_remaining=days_remaining,
        )
        return cumulative_gross_to_date + projected_remaining, sigma

    week_1_gross = _calibrate_week_1(
        release_date=release_date,
        cumulative_gross_to_date=cumulative_gross_to_date,
        days_since_release=days_since_release,
        wow=wow,
    )

    projected_remaining = _sum_weekly_remaining(
        week_1_gross=week_1_gross,
        wow=wow,
        weeks_already_played=weeks_observed,
        days_already_in_current_week=days_since_release % 7,
        days_remaining=days_remaining,
    )
    return cumulative_gross_to_date + projected_remaining, sigma


def _resolve_wow(category: Category, history: list[tuple[date, float]]) -> float:
    default = _DEFAULT_WOW[category]
    if len(history) < 2:
        return default
    sorted_history = sorted(history, key=lambda row: row[0])
    deltas = [
        sorted_history[i + 1][1] - sorted_history[i][1]
        for i in range(len(sorted_history) - 1)
    ]
    # WoW estimated as geometric mean of consecutive delta ratios
    ratios = [
        deltas[i + 1] / deltas[i]
        for i in range(len(deltas) - 1)
        if deltas[i] > 0 and deltas[i + 1] > 0
    ]
    if not ratios:
        return default
    geo_mean = 1.0
    for r in ratios:
        geo_mean *= r
    geo_mean = geo_mean ** (1.0 / len(ratios))
    weight = min(1.0, (len(history) - 1) / 5.0)
    return weight * geo_mean + (1.0 - weight) * default


def _sigma_from_weeks(weeks_observed: int) -> float:
    if weeks_observed >= 6:
        return 0.10
    if weeks_observed <= 0:
        return 0.30
    return 0.30 - (0.20 * weeks_observed / 6.0)


def _calibrate_week_1(
    *, release_date: date, cumulative_gross_to_date: float, days_since_release: int, wow: float
) -> float:
    """Solve for week_1_gross such that the modeled cumulative-to-date matches input.

    Uses day-of-week weights for the first partial week instead of uniform prorating,
    so that opening-weekend days count for their true share of week-1 gross.
    """
    if days_since_release <= 0:
        return 0.0
    full_weeks = days_since_release // 7
    partial_days = days_since_release % 7

    geo_full = sum(wow**k for k in range(full_weeks))
    if partial_days > 0:
        partial_frac = _week1_fraction_earned(release_date, partial_days) if full_weeks == 0 else partial_days / 7.0
        partial_term = (wow**full_weeks) * partial_frac
    else:
        partial_term = 0.0
    denominator = geo_full + partial_term
    if denominator <= 0:
        return 0.0
    return cumulative_gross_to_date / denominator


def _sum_weekly_remaining(
    *,
    week_1_gross: float,
    wow: float,
    weeks_already_played: int,
    days_already_in_current_week: int,
    days_remaining: int,
) -> float:
    """Sum modeled grosses for the next `days_remaining` days starting at the current point."""
    if days_remaining <= 0 or week_1_gross <= 0:
        return 0.0

    total = 0.0
    days_left = days_remaining
    week_index = weeks_already_played

    # Finish out the current partial week first
    if days_already_in_current_week > 0:
        days_left_in_current_week = 7 - days_already_in_current_week
        chunk_days = min(days_left, days_left_in_current_week)
        total += week_1_gross * (wow**week_index) * (chunk_days / 7.0)
        days_left -= chunk_days
        week_index += 1

    # Full weeks
    while days_left >= 7:
        total += week_1_gross * (wow**week_index)
        days_left -= 7
        week_index += 1

    # Final partial week
    if days_left > 0:
        total += week_1_gross * (wow**week_index) * (days_left / 7.0)

    return total
