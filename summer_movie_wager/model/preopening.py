"""Pre-release projection (Mode B) — analyst-estimate driven — and the wager window constants."""

from datetime import date

from summer_movie_wager.types import Category, Confidence

# The wager scores domestic gross for films released inside this window, inclusive.
# WINDOW_START is May 1, not Apr 30: the play-along site's 2026-05-04 gross list
# contains only May 1 releases, and omits The Story of Everything (Apr 30).
WINDOW_START = date(2026, 5, 1)
WINDOW_END = date(2026, 9, 7)  # Labor Day 2026

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
    """
    Convert an analyst pre-release estimate into (in_window_gross, sigma).

    Returns (0.0, 0.0) if the movie won't open inside the window.
    """
    if release_date > WINDOW_END:
        return 0.0, 0.0

    sigma = _SIGMA_BY_CONFIDENCE[confidence]

    if total_domestic_estimate <= 0 or opening_weekend_estimate <= 0:
        return 0.0, sigma

    # TODO BAC 2026-06-20:
    # This math isn't quite right. It assumes that the movie is playing for an infinite number of
    # weeks.
    # While that's mostly fine for a guesstimate, a movie is only playing for ~8 weeks. Anything
    # beyond that
    # adds essentially zero gross.
    # Maybe that's worth considering here? Effectively, find the decay rate to go from the opening
    # weekend
    # to the total domestic in 8 weeks time.
    #
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

    # The value returned here becomes the "median" displayed on the site
    # (median_in_window_gross). It is the IN-WINDOW gross only (release_date -> WINDOW_END),
    # so it diverges from total_domestic_estimate in preopening_projections.yaml — most
    # noticeably for titles releasing late in the window, where much of the theatrical run
    # falls after WINDOW_END (Sep 7). We could consider making the displayed median equal
    # total_domestic_estimate (or otherwise reconciling the two) so the site value always
    # matches the analyst total in the YAML. Caveat to weigh when implementing: the wager
    # only scores in-window box office, so the simulator's ranking should likely keep using
    # the in-window figure even if the *displayed* median changes.
    #
    # TODO BAC 2026-06-20:
    # A happy medium here could be to display the total domestic estimate for any movie that
    # will play for 8+ weeks in the window.  And for any movie that will play for less than
    # 8 weeks, we would display the estimated in-window gross.
    return in_window, sigma


def _sum_weekly(*, week_1_gross: float, wow: float, start: date, end: date) -> float:
    """
    Sum modeled weekly grosses for the date range [start, end] (inclusive on both ends).

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
