# Decay Week-1 Calibration Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `_calibrate_week_1` in `decay.py` so that the first-week gross estimate is based on realistic day-of-week earnings weights rather than a uniform `partial_days / 7.0` assumption, eliminating the 2–3× overestimation of in-window totals for movies in their first few days.

**Architecture:** Add a `_DOW_WEIGHTS` table (Mon–Sun daily fractions summing to 1.0) and a `_week1_fraction_earned(release_date, days)` helper to `decay.py`. Thread `release_date` into `_calibrate_week_1` and `_sum_weekly_remaining` so both use the realistic fraction instead of uniform prorating. No other files change.

**Tech Stack:** Python 3.12+, `pytest` (tests), `uv run pytest` to execute.

---

## File Structure

Files modified during this plan:

```
summer_movie_wager/model/decay.py   — add DOW weights + helper; update two functions
tests/test_decay.py                 — update two existing tests; add two new tests
```

No new files. No other files touched.

---

### Task 1: Add `_DOW_WEIGHTS` and `_week1_fraction_earned` to `decay.py`

**Files:**
- Modify: `summer_movie_wager/model/decay.py`
- Test: `tests/test_decay.py`

These weights represent the fraction of a typical week's gross earned on each day of the week (Monday = index 0 through Sunday = index 6). They sum to 1.0 and are derived from industry box-office day-of-week patterns.

- [ ] **Step 1: Write a failing test for `_week1_fraction_earned`**

Add this test to the bottom of `tests/test_decay.py`:

```python
from summer_movie_wager.model.decay import _week1_fraction_earned


def test_week1_fraction_earned_thursday_open_four_days():
    # Mandalorian scenario: opened Thursday May 22, 4 days elapsed (Thu–Sun)
    # Thu=0.09, Fri=0.21, Sat=0.26, Sun=0.21 → 0.77
    frac = _week1_fraction_earned(date(2026, 5, 22), 4)
    assert frac == pytest.approx(0.77, abs=0.001)


def test_week1_fraction_earned_friday_open_three_days():
    # Standard Friday opening: Fri=0.21, Sat=0.26, Sun=0.21 → 0.68
    frac = _week1_fraction_earned(date(2026, 5, 23), 3)
    assert frac == pytest.approx(0.68, abs=0.001)


def test_week1_fraction_earned_full_week_is_one():
    frac = _week1_fraction_earned(date(2026, 5, 22), 7)
    assert frac == pytest.approx(1.0, abs=0.001)


def test_week1_fraction_earned_zero_days_is_zero():
    frac = _week1_fraction_earned(date(2026, 5, 22), 0)
    assert frac == pytest.approx(0.0, abs=0.001)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_decay.py::test_week1_fraction_earned_thursday_open_four_days tests/test_decay.py::test_week1_fraction_earned_friday_open_three_days tests/test_decay.py::test_week1_fraction_earned_full_week_is_one tests/test_decay.py::test_week1_fraction_earned_zero_days_is_zero -v
```

Expected: `ImportError` or `FAILED` — `_week1_fraction_earned` does not exist yet.

- [ ] **Step 3: Add `_DOW_WEIGHTS` and `_week1_fraction_earned` to `decay.py`**

Insert after the `_DEFAULT_WOW` block (after line 11) in `summer_movie_wager/model/decay.py`:

```python
# Fraction of a typical week's gross earned on each day (Mon=0 … Sun=6).
# Weights sum to 1.0. Source: industry box-office day-of-week distribution.
_DOW_WEIGHTS: list[float] = [0.08, 0.07, 0.08, 0.09, 0.21, 0.26, 0.21]


def _week1_fraction_earned(release_date: date, days_in_partial_week: int) -> float:
    """Fraction of week-1 gross expected to have been earned in the first N days.

    Uses day-of-week weights so that opening-weekend days (Fri/Sat/Sun) count
    for their true share (~68%) rather than a uniform 3/7 = 43%.
    Clamped to [0, 1].
    """
    if days_in_partial_week <= 0:
        return 0.0
    days = min(days_in_partial_week, 7)
    dow_start = release_date.weekday()  # 0=Mon … 6=Sun
    return sum(_DOW_WEIGHTS[(dow_start + i) % 7] for i in range(days))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_decay.py::test_week1_fraction_earned_thursday_open_four_days tests/test_decay.py::test_week1_fraction_earned_friday_open_three_days tests/test_decay.py::test_week1_fraction_earned_full_week_is_one tests/test_decay.py::test_week1_fraction_earned_zero_days_is_zero -v
```

Expected: all 4 `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add summer_movie_wager/model/decay.py tests/test_decay.py
git commit -m "feat: add DOW weights and _week1_fraction_earned helper to decay model"
```

---

### Task 2: Update `_calibrate_week_1` to use day-of-week weights

**Files:**
- Modify: `summer_movie_wager/model/decay.py`
- Test: `tests/test_decay.py`

`_calibrate_week_1` currently uses `partial_days / 7.0` for the first partial week. We replace that with `_week1_fraction_earned` so the back-solved `week_1_gross` reflects reality.

The function's signature must gain `release_date` because the fraction depends on which day of the week the movie opened.

- [ ] **Step 1: Write a failing test for the corrected calibration**

Add to `tests/test_decay.py`:

```python
def test_calibrate_week1_thursday_open_four_days():
    # Mandalorian: opened Thu May 22, 4 days elapsed, $102M cumulative.
    # Thu+Fri+Sat+Sun = 0.09+0.21+0.26+0.21 = 0.77 of week 1.
    # week_1_gross should be 102M / 0.77 ≈ 132.5M (not 178M from uniform 4/7).
    from summer_movie_wager.model.decay import _calibrate_week_1
    w1 = _calibrate_week_1(
        release_date=date(2026, 5, 22),
        cumulative_gross_to_date=102_000_000.0,
        days_since_release=4,
        wow=0.55,
    )
    assert 130_000_000 < w1 < 135_000_000


def test_calibrate_week1_full_week_returns_cumulative():
    # After a full 7 days, week_1_gross == cumulative (no partial adjustment needed).
    from summer_movie_wager.model.decay import _calibrate_week_1
    w1 = _calibrate_week_1(
        release_date=date(2026, 5, 19),  # Monday open
        cumulative_gross_to_date=80_000_000.0,
        days_since_release=7,
        wow=0.55,
    )
    assert w1 == pytest.approx(80_000_000.0, rel=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_decay.py::test_calibrate_week1_thursday_open_four_days tests/test_decay.py::test_calibrate_week1_full_week_returns_cumulative -v
```

Expected: `TypeError` (missing `release_date` argument) or wrong assertion value.

- [ ] **Step 3: Update `_calibrate_week_1` signature and body**

Replace the existing `_calibrate_week_1` function in `summer_movie_wager/model/decay.py`:

```python
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
```

**Note:** Day-of-week weights only apply to the first partial week (`full_weeks == 0`). For weeks 2+ the uniform `partial_days / 7.0` is an acceptable approximation — the numbers are much smaller by then and the day-of-week effect is less pronounced.

- [ ] **Step 4: Update the call site in `project_decay`**

In `project_decay`, the call to `_calibrate_week_1` (currently around line 53) must pass `release_date`:

```python
    week_1_gross = _calibrate_week_1(
        release_date=release_date,
        cumulative_gross_to_date=cumulative_gross_to_date,
        days_since_release=days_since_release,
        wow=wow,
    )
```

- [ ] **Step 5: Run new tests to verify they pass**

```bash
uv run pytest tests/test_decay.py::test_calibrate_week1_thursday_open_four_days tests/test_decay.py::test_calibrate_week1_full_week_returns_cumulative -v
```

Expected: both `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add summer_movie_wager/model/decay.py tests/test_decay.py
git commit -m "fix: use day-of-week weights in _calibrate_week_1 for opening-week movies"
```

---

### Task 3: Update `_sum_weekly_remaining` to use day-of-week weights for the current partial week

**Files:**
- Modify: `summer_movie_wager/model/decay.py`
- Test: `tests/test_decay.py`

When projecting the remaining days in the *current* partial week (inside `_sum_weekly_remaining`), the code uses `chunk_days / 7.0`. If we're still in week 1, the remaining days should be the complementary fraction `1 - _week1_fraction_earned(release_date, days_already_in_current_week)` of `week_1_gross`. For weeks 2+, uniform is fine.

- [ ] **Step 1: Write a failing integration test**

Add to `tests/test_decay.py`:

```python
def test_projection_thursday_open_not_inflated():
    # Mandalorian scenario: Thu open, 4 days in, $102M, WIDE.
    # With the fix, total projection must be well under $300M.
    # Industry expectation is ~$200–240M for this opening pace.
    gross, sigma = project_decay(
        release_date=date(2026, 5, 22),
        today=date(2026, 5, 25),
        cumulative_gross_to_date=102_000_000.0,
        category=Category.WIDE,
        observed_history=[],
    )
    assert gross < 300_000_000, f"Projection {gross/1e6:.0f}M is unrealistically high"
    assert gross > 102_000_000, "Projection must exceed current gross"
    assert sigma == pytest.approx(0.30)
```

- [ ] **Step 2: Run test to observe current behavior**

```bash
uv run pytest tests/test_decay.py::test_projection_thursday_open_not_inflated -v
```

Expected: `FAILED` — projection likely exceeds $300M even after Task 2 (the remaining-week step still uses uniform weighting, so the "rest of week 1" chunk is still too large).

- [ ] **Step 3: Update `_sum_weekly_remaining` signature and first-partial-week logic**

Replace the existing `_sum_weekly_remaining` function in `summer_movie_wager/model/decay.py`:

```python
def _sum_weekly_remaining(
    *,
    week_1_gross: float,
    wow: float,
    weeks_already_played: int,
    days_already_in_current_week: int,
    days_remaining: int,
    release_date: date | None = None,
) -> float:
    """Sum modeled grosses for the next `days_remaining` days starting at the current point.

    For week-1 partial-week completion, uses day-of-week weights when release_date is
    provided; falls back to uniform prorating for weeks 2+ or when release_date is absent.
    """
    if days_remaining <= 0 or week_1_gross <= 0:
        return 0.0

    total = 0.0
    days_left = days_remaining
    week_index = weeks_already_played

    # Finish out the current partial week first
    if days_already_in_current_week > 0:
        days_left_in_current_week = 7 - days_already_in_current_week
        chunk_days = min(days_left, days_left_in_current_week)

        if week_index == 0 and release_date is not None:
            # Week 1: use complementary DOW fraction instead of chunk_days/7
            earned_so_far = _week1_fraction_earned(release_date, days_already_in_current_week)
            total_remaining_frac = 1.0 - earned_so_far
            # If window ends before end of week 1, prorate the remaining fraction
            if chunk_days < days_left_in_current_week:
                full_remaining_frac = _week1_fraction_earned(release_date, days_already_in_current_week + chunk_days) - earned_so_far
                total += week_1_gross * full_remaining_frac
            else:
                total += week_1_gross * total_remaining_frac
        else:
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
```

- [ ] **Step 4: Update the call site in `project_decay` to pass `release_date`**

In `project_decay`, the call to `_sum_weekly_remaining` (currently around line 59) must pass `release_date`:

```python
    projected_remaining = _sum_weekly_remaining(
        week_1_gross=week_1_gross,
        wow=wow,
        weeks_already_played=weeks_observed,
        days_already_in_current_week=days_since_release % 7,
        days_remaining=days_remaining,
        release_date=release_date,
    )
```

Also update the degenerate-case call (the `days_since_release == 0 and cumulative_gross_to_date > 0` branch, currently around line 46) — that branch doesn't have a meaningful release_date to use, so omit `release_date` there (it will default to `None` and fall back to uniform).

- [ ] **Step 5: Run new integration test to verify it passes**

```bash
uv run pytest tests/test_decay.py::test_projection_thursday_open_not_inflated -v
```

Expected: `PASSED` with gross somewhere in the $200–290M range.

- [ ] **Step 6: Commit**

```bash
git add summer_movie_wager/model/decay.py tests/test_decay.py
git commit -m "fix: use DOW weights for week-1 remaining-days projection in _sum_weekly_remaining"
```

---

### Task 4: Update existing tests broken by the new behavior

**Files:**
- Modify: `tests/test_decay.py`

Two existing tests were written assuming uniform `partial_days / 7.0` weighting and will now fail because the calibrated `week_1_gross` is lower (and thus the projection is lower). We need to update their expected ranges to match the corrected behavior.

- [ ] **Step 1: Run the full test suite to see which tests fail**

```bash
uv run pytest tests/test_decay.py -v
```

Expected: `test_just_opened_uses_default_wow_and_high_sigma` likely fails because its comment says "~6/7 of week 1 = 50M → week_1 ≈ 58.3M" — that was the uniform assumption. With DOW weights for a Monday-opening movie (release_date=2026-04-27, 6 days later = 2026-05-03), the fraction is Mon+Tue+Wed+Thu+Fri+Sat = 0.08+0.07+0.08+0.09+0.21+0.26 = 0.79, so week_1 ≈ 50M/0.79 ≈ 63.3M. The assertion bounds `100M < gross < 160M` may or may not still hold.

- [ ] **Step 2: Compute the corrected expected range for `test_just_opened_uses_default_wow_and_high_sigma`**

For release_date=2026-04-27 (Monday), 6 days elapsed (through Saturday 2026-05-02):
- Mon=0.08, Tue=0.07, Wed=0.08, Thu=0.09, Fri=0.21, Sat=0.26 → fraction=0.79
- week_1_gross = 50M / 0.79 ≈ 63.3M
- Remaining of week 1 (Sunday only): 63.3M × 0.21 = 13.3M
- Then sum of weeks 2–18 at wow=0.55: 63.3M × 0.55 / (1–0.55) × (1–0.55^18) ≈ 63.3M × 1.222 ≈ 77.4M
- Total ≈ 50M + 13.3M + 77.4M ≈ 140.7M

Update the test bounds and comment:

```python
def test_just_opened_uses_default_wow_and_high_sigma():
    # Movie opened 6 days ago (Monday Apr 27) with $50M earned.
    # DOW weights for Mon–Sat = 0.79 → week_1 ≈ 63.3M.
    # Rest of week 1 (Sunday = 0.21): +13.3M.
    # ~17 weeks remaining at wow=0.55: 63.3M * 1.22 ≈ 77M.
    # Total ≈ 140M, so assertion window is 110M–170M.
    gross, sigma = project_decay(
        release_date=date(2026, 4, 27),
        today=date(2026, 5, 3),
        cumulative_gross_to_date=50_000_000.0,
        category=Category.WIDE,
        observed_history=[],
    )
    assert 110_000_000 < gross < 170_000_000
    assert sigma == pytest.approx(0.30)
```

- [ ] **Step 3: Run the full test suite to confirm all tests pass**

```bash
uv run pytest tests/test_decay.py -v
```

Expected: all tests `PASSED`.

- [ ] **Step 4: Run the broader test suite to check for regressions**

```bash
uv run pytest -v
```

Expected: all tests pass. If `tests/test_render_snapshot.py` fails, the `docs/data.json` fixture may need regeneration — run `uv run python -m summer_movie_wager.render.build` and check the output, then update `tests/fixtures/expected_index.html` if needed.

- [ ] **Step 5: Commit**

```bash
git add tests/test_decay.py
git commit -m "test: update decay test bounds to match corrected DOW-weight calibration"
```

---

## Self-Review

**Spec coverage:**
- ✅ `_DOW_WEIGHTS` table defined in Task 1
- ✅ `_week1_fraction_earned` helper defined and tested in Task 1
- ✅ `_calibrate_week_1` updated to use DOW weights for first partial week (Task 2)
- ✅ `_sum_weekly_remaining` updated to use DOW weights for week-1 remainder (Task 3)
- ✅ Existing tests updated to reflect corrected behavior (Task 4)
- ✅ Integration test confirms projection is no longer inflated (Task 3, Step 1–5)

**Placeholder scan:** No TBDs, no "similar to Task N" references, all code blocks are complete.

**Type consistency:**
- `_week1_fraction_earned` is defined in Task 1 and called in Tasks 2 and 3 — signature matches
- `_calibrate_week_1` gains `release_date: date` in Task 2, call site in `project_decay` updated in same task
- `_sum_weekly_remaining` gains `release_date: date | None = None` in Task 3, call sites updated in same task
- All internal calls use keyword arguments matching the updated signatures
