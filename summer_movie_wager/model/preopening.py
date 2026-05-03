"""Pre-release projection (Mode B) — analyst-estimate driven."""

from datetime import date

from summer_movie_wager.types import Category, Confidence

WINDOW_END = date(2026, 9, 7)

_DEFAULT_WOW: dict[Category, float] = {
    Category.WIDE: 0.55,
    Category.ANIMATED_FAMILY: 0.65,
}

_SIGMA_BY_CONFIDENCE: dict[Confidence, float] = {
    Confidence.HIGH: 0.20,
    Confidence.MED: 0.30,
    Confidence.LOW: 0.45,
}


def project_preopening(
    *,
    release_date: date,
    opening_weekend_estimate: float,
    total_domestic_estimate: float,
    confidence: Confidence,
    category: Category,
) -> tuple[float, float]:
    """Convert an analyst pre-release estimate into (in_window_gross, sigma).

    Returns (0.0, 0.0) if the movie won't open inside the window.
    """
    if release_date > WINDOW_END:
        return 0.0, 0.0

    sigma = _SIGMA_BY_CONFIDENCE[confidence]

    if total_domestic_estimate <= 0 or opening_weekend_estimate <= 0:
        return 0.0, sigma

    # Derive implied week-over-week multiplier so the infinite geometric series
    # sums to total_domestic_estimate when week_1 = opening_weekend_estimate.
    implied_wow = 1.0 - (opening_weekend_estimate / total_domestic_estimate)
    if not (0.0 < implied_wow < 1.0):
        implied_wow = _DEFAULT_WOW[category]

    week_1_gross = opening_weekend_estimate
    in_window = _sum_weekly(
        week_1_gross=week_1_gross,
        wow=implied_wow,
        start=release_date,
        end=WINDOW_END,
    )
    in_window = min(in_window, total_domestic_estimate)
    return in_window, sigma


def _sum_weekly(*, week_1_gross: float, wow: float, start: date, end: date) -> float:
    """Sum modeled weekly grosses for the date range [start, end] (inclusive on both ends).

    Week k contributes week_1_gross * wow**(k-1). Final partial week is prorated by
    (days_remaining / 7).
    """
    days_in_window = (end - start).days + 1
    if days_in_window <= 0:
        return 0.0
    full_weeks = days_in_window // 7
    partial_days = days_in_window % 7

    total = 0.0
    for week_index in range(full_weeks):
        total += week_1_gross * (wow**week_index)
    if partial_days > 0:
        total += week_1_gross * (wow**full_weeks) * (partial_days / 7.0)
    return total
