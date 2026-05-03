"""In-theaters projection (Mode A) — weekly decay model with optional history blending."""

from datetime import date

from summer_movie_wager.model.preopening import WINDOW_END
from summer_movie_wager.types import Category

_DEFAULT_WOW: dict[Category, float] = {
    Category.WIDE: 0.55,
    Category.ANIMATED_FAMILY: 0.65,
}


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

    week_1_gross = _calibrate_week_1(
        cumulative_gross_to_date=cumulative_gross_to_date,
        days_since_release=(today - release_date).days,
        wow=wow,
    )

    days_remaining = (WINDOW_END - today).days
    projected_remaining = _sum_weekly_remaining(
        week_1_gross=week_1_gross,
        wow=wow,
        weeks_already_played=weeks_observed,
        days_already_in_current_week=(today - release_date).days % 7,
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
    *, cumulative_gross_to_date: float, days_since_release: int, wow: float
) -> float:
    """Solve for week_1_gross such that the modeled cumulative-to-date matches input."""
    if days_since_release <= 0:
        return 0.0
    full_weeks = days_since_release // 7
    partial_days = days_since_release % 7

    # Modeled cumulative = sum_{k=0..full_weeks-1} W*wow^k + W*wow^full_weeks * partial/7
    geo_full = sum(wow**k for k in range(full_weeks))
    partial_term = (wow**full_weeks) * (partial_days / 7.0) if partial_days > 0 else 0.0
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
