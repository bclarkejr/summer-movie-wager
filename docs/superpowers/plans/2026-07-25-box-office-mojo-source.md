# Box Office Mojo Data Source Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace thesummermoviewager.com as the source of cumulative box office grosses with Box Office Mojo's yearly chart, so films outside the site's top-13 (e.g. *Power Ballad*) and films that fall off it (e.g. *The Sheep Detectives*) keep producing data.

## Context

`ingest/scraper.py` reads grosses from `<table class="toptengross">` on thesummermoviewager.com. That table only lists films currently in the site's top 13. Two failure modes follow:

1. A film that never cracks the top 13 never appears at all. *Power Ballad* ($2.6M) has zero rows in `data/box_office_history.jsonl`, so it projects 0 forever.
2. A film that drops out later stops appearing. *The Sheep Detectives* has 11 history rows ending 2026-07-20 at $66,078,506. On the next run it will vanish from the site's table, `snapshot.cumulative_grosses.get(title, 0.0)` will return `0.0`, `_normalize_movies` will re-classify it `PRE_RELEASE`, and its $66M will disappear from the leaderboard — even though it may still finish top 10.

**Source selection (verified 2026-07-25 by live fetch, not assumed):**

| Endpoint | Rows | Power Ballad | Sheep Detectives | Release dates |
|---|---|---|---|---|
| `/date/2026-07-23/` | 27 | ❌ | ❌ | no |
| `/weekend/2026W29/` | 40 | ❌ | ❌ | no |
| `/year/2026/` | **200** | ✅ #104 | ✅ #23 | ✅ |

The originally proposed `/date/<yesterday>/` page does **not** fix the problem — it is a daily-reporting chart with the same long-tail truncation. It is also unreliable: `/date/2026-07-24/` returned HTTP 200 with an empty table on 2026-07-25.

`/year/2026/` is the source. Additional verified facts:

- All **28** titles in `box_office_history.jsonl` match its titles **byte-for-byte** — no alias table needed.
- Its totals already reflect the last fully-reported day (Toy Story 5: $438,555,658 on the 7/23 date page → $441,455,658 on the year chart), which is the "previous day's cumulative" semantic requested.
- Plain `httpx` with its default User-Agent gets HTTP 200. No browser UA spoofing needed.
- All 200 rows share one identical `<td>` class signature — stable to parse.
- `?offset=200` is ignored; the chart is capped at 200 rows (rank 200 = $468,400, far below anything relevant).

**Intended outcome:** every in-window film's cumulative gross is tracked continuously from release through Labor Day, regardless of whether it ever appears in the site's top 13.

## Global Constraints

- Wager window: **2026-05-01 through 2026-09-07 (Labor Day), inclusive.** Confirmed by the user. Note this contradicts the README's `2026-04-30`; the README must be corrected (Task 5). Empirical support: *The Story of Everything* (BOM release Apr 30, $1.9M) is absent from the site's 2026-05-04 gross list, while all five films the site did list that day are BOM May 1 releases.
- Python `>=3.12`. Dependency manager is `uv`; do **not** add new dependencies — `httpx` and `selectolax` are already present and sufficient.
- ruff: line-length 100, rules `E,F,I,B,UP,RUF`, `target-version = "py312"`. Run `uv run ruff format .` and `uv run ruff check .` before every commit.
- Tests must be **network-free**. Every parser test reads a committed fixture.
- **Where steps below say "append to" a test file, that applies to the test functions only. Every `import` line shown must go into the file's existing top-of-file import block, merged into the matching existing import where one exists.** Ruff's `E402` (module-level import not at top of file) and `I001` (unsorted import block) are both enabled and will fail the lint gate otherwise. `uv run ruff check --fix .` resolves `I001` ordering for you; `E402` it will not.
- Pydantic models at boundaries, per existing convention in `summer_movie_wager/types.py`.
- Run tests with `uv run pytest`.

---

### Task 1: Box Office Mojo year-chart parser

**Files:**
- Create: `summer_movie_wager/ingest/boxoffice.py`
- Create: `tests/fixtures/boxofficemojo_year_2026.html` (downloaded once, committed)
- Create: `tests/test_boxoffice.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `class BoxOfficeRow(BaseModel)` with fields `title: str`, `cumulative_gross: float`, `release_date: date`
  - `def parse_year_chart(html_text: str, *, year: int) -> dict[str, BoxOfficeRow]` — keyed by title
  - `def fetch_year_chart(*, year: int = 2026, timeout: float = 30.0) -> dict[str, BoxOfficeRow]`
  - `YEAR_CHART_URL: str` (a `{year}` format template)

- [ ] **Step 1: Download and commit the test fixture**

```bash
curl -s -A "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36" \
  -o tests/fixtures/boxofficemojo_year_2026.html \
  "https://www.boxofficemojo.com/year/2026/"
wc -c tests/fixtures/boxofficemojo_year_2026.html
```

Expected: roughly 440,000–460,000 bytes.

Sanity-check the fixture contains the two films this whole change exists for:

```bash
grep -c "Power Ballad" tests/fixtures/boxofficemojo_year_2026.html
grep -c "The Sheep Detectives" tests/fixtures/boxofficemojo_year_2026.html
```

Expected: both `1` or greater. If either is `0`, stop — the fixture is wrong and every assertion below is invalid.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_boxoffice.py`:

```python
from datetime import date
from pathlib import Path

import pytest

from summer_movie_wager.ingest.boxoffice import parse_year_chart

FIXTURE = Path(__file__).parent / "fixtures" / "boxofficemojo_year_2026.html"


@pytest.fixture
def chart():
    html_text = FIXTURE.read_text(encoding="utf-8")
    return parse_year_chart(html_text, year=2026)


def test_chart_has_two_hundred_rows(chart):
    # The yearly chart is capped at 200 rows; ?offset=200 is ignored by the site.
    assert len(chart) == 200


def test_long_tail_film_is_present(chart):
    # Power Ballad never enters the play-along site's top 13. Capturing it is
    # the entire reason this module exists.
    assert chart["Power Ballad"].cumulative_gross == 2_612_490.0
    assert chart["Power Ballad"].release_date == date(2026, 5, 29)


def test_faded_film_is_present(chart):
    # The Sheep Detectives dropped off the play-along site's top 13 mid-season.
    assert chart["The Sheep Detectives"].cumulative_gross == 66_078_506.0
    assert chart["The Sheep Detectives"].release_date == date(2026, 5, 8)


def test_uses_gross_column_not_total_gross_column(chart):
    # The chart carries both "Gross" (calendar-2026 domestic) and "Total Gross"
    # (lifetime). For 2026 releases the "Total Gross" cell is frequently stale or
    # outright wrong -- Obsession reads $240,017,600 there against $260,344,235
    # in the "Gross" cell, and the play-along site independently reported
    # $258,387,140 on 2026-07-20. The "Gross" cell is the correct one.
    assert chart["Obsession"].cumulative_gross == 260_344_235.0


def test_release_date_parsed_from_abbreviated_month(chart):
    assert chart["Toy Story 5"].release_date == date(2026, 6, 19)


def test_ignores_the_header_row(chart):
    assert "Release" not in chart
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_boxoffice.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'summer_movie_wager.ingest.boxoffice'`

- [ ] **Step 4: Write the implementation**

Create `summer_movie_wager/ingest/boxoffice.py`:

```python
"""Fetch cumulative domestic grosses from Box Office Mojo's yearly chart.

The play-along site only publishes its top 13, so films below it (or films that
fall out of it) go dark. Box Office Mojo's yearly chart lists 200 titles with
release dates, which covers every film that could plausibly finish in the
wager's top 10 -- and every film any player picked.

Row shape, verified against the 2026 chart (all 200 rows share one class
signature):

    <td class="... mojo-field-type-rank ...">1</td>
    <td class="... mojo-field-type-release ..."><a href="/release/rl...">Toy Story 5</a></td>
    <td class="... mojo-field-type-genre hidden">-</td>
    <td class="... mojo-field-type-money hidden">-</td>          <- budget
    <td class="... mojo-field-type-duration hidden">-</td>
    <td class="... mojo-field-type-money mojo-estimatable">$441,455,658</td>   <- Gross
    <td class="... mojo-field-type-positive_integer">4,425</td>
    <td class="... mojo-field-type-money mojo-estimatable">$441,455,658</td>   <- Total Gross
    <td class="... mojo-field-type-date a-nowrap">Jun 19</td>
    ...
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime

import httpx
from pydantic import BaseModel, ConfigDict
from selectolax.parser import HTMLParser

YEAR_CHART_URL = "https://www.boxofficemojo.com/year/{year}/"


class BoxOfficeRow(BaseModel):
    """One release on the yearly chart."""

    model_config = ConfigDict(frozen=True)

    title: str
    cumulative_gross: float
    release_date: date


def fetch_year_chart(*, year: int = 2026, timeout: float = 30.0) -> dict[str, BoxOfficeRow]:
    """Fetch and parse the live yearly chart, keyed by title."""

    response = httpx.get(YEAR_CHART_URL.format(year=year), timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return parse_year_chart(response.text, year=year)


def parse_year_chart(html_text: str, *, year: int) -> dict[str, BoxOfficeRow]:
    """Parse the yearly chart into `{title: BoxOfficeRow}`.

    Rows that don't yield a title, a gross, and a release date are skipped rather
    than raising -- the chart carries occasional oddities (event cinema, re-release
    rows) that aren't worth failing a build over.
    """

    tree = HTMLParser(html_text)
    rows: dict[str, BoxOfficeRow] = {}
    for row in tree.css("tr"):
        title_cell = row.css_first("td.mojo-field-type-release")
        date_cell = row.css_first("td.mojo-field-type-date")
        # The budget cell also carries `mojo-field-type-money` but is marked `hidden`;
        # the two `mojo-estimatable` money cells are [Gross, Total Gross] in that order.
        money_cells = row.css("td.mojo-field-type-money.mojo-estimatable")
        if title_cell is None or date_cell is None or not money_cells:
            continue

        title = _clean_text(title_cell.text(deep=True))
        gross = _parse_dollar_amount(_clean_text(money_cells[0].text(deep=True)))
        release = _parse_release_date(_clean_text(date_cell.text(deep=True)), year=year)
        if not title or gross is None or release is None:
            continue

        rows[title] = BoxOfficeRow(
            title=title,
            cumulative_gross=gross,
            release_date=release,
        )
    return rows


def _clean_text(raw: str) -> str:
    """Decode HTML entities, drop non-breaking spaces, collapse whitespace runs."""

    text = html.unescape(raw or "")
    text = text.replace("\xa0", " ")
    return re.sub(r"\s+", " ", text).strip()


def _parse_dollar_amount(text: str) -> float | None:
    """Parse "$441,455,658" into a float. Returns None for placeholders like "-"."""

    m = re.match(r"^\$?([\d,]+)$", text)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def _parse_release_date(text: str, *, year: int) -> date | None:
    """Parse an abbreviated "Jun 19" into a date, stamping the chart's year.

    The chart omits the year, and rows for prior-year releases still showing in
    this year's chart (e.g. a Dec 19 2025 opening) get stamped with the chart year.
    That is harmless here: those dates land outside the wager window either way,
    so the window filter in `in_window` drops them for the right reason.
    """

    try:
        return datetime.strptime(f"{text} {year}", "%b %d %Y").date()
    except ValueError:
        return None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_boxoffice.py -v`
Expected: PASS — 6 passed

- [ ] **Step 6: Lint**

Run: `uv run ruff format . && uv run ruff check .`
Expected: `All checks passed!`

- [ ] **Step 7: Verify the live fetch works once, by hand**

Run:
```bash
uv run python -c "
from summer_movie_wager.ingest.boxoffice import fetch_year_chart
c = fetch_year_chart()
print(len(c), 'rows')
print(c['Power Ballad'])
"
```
Expected: `200 rows` then a `BoxOfficeRow` for Power Ballad. This is the only network step in the plan; nothing in the test suite repeats it.

- [ ] **Step 8: Commit**

```bash
git add summer_movie_wager/ingest/boxoffice.py tests/test_boxoffice.py tests/fixtures/boxofficemojo_year_2026.html
git commit -m "feat: parse cumulative grosses from Box Office Mojo yearly chart"
```

---

### Task 2: Wager-window filter

**Files:**
- Modify: `summer_movie_wager/model/preopening.py:7` (add `WINDOW_START` beside `WINDOW_END`)
- Modify: `summer_movie_wager/ingest/boxoffice.py` (add `in_window`)
- Modify: `tests/test_boxoffice.py` (add window tests)

**Interfaces:**
- Consumes: `BoxOfficeRow`, `parse_year_chart` from Task 1.
- Produces:
  - `WINDOW_START: date` = `date(2026, 5, 1)`, exported from `summer_movie_wager.model.preopening`
  - `def in_window(chart: dict[str, BoxOfficeRow]) -> dict[str, BoxOfficeRow]`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_boxoffice.py`:

```python
from summer_movie_wager.ingest.boxoffice import in_window


def test_window_excludes_releases_before_may_first(chart):
    # Michael opened Apr 24 and is absent from the play-along site's gross table
    # despite grossing $372M -- it is not a wager film.
    assert "Michael" in chart
    assert "Michael" not in in_window(chart)


def test_window_excludes_april_thirtieth_releases(chart):
    # The Story of Everything opened Apr 30. It is absent from the site's
    # 2026-05-04 gross list, which is the evidence the window opens May 1.
    assert "The Story of Everything" in chart
    assert "The Story of Everything" not in in_window(chart)


def test_window_includes_may_first_releases(chart):
    assert "The Devil Wears Prada 2" in in_window(chart)


def test_window_excludes_releases_after_labor_day(chart):
    # Zootopia 2 carries a Nov 26 date on the 2026 chart; whatever year it
    # really belongs to, it is outside 2026-05-01..2026-09-07.
    assert "Zootopia 2" in chart
    assert "Zootopia 2" not in in_window(chart)


def test_window_keeps_the_long_tail(chart):
    windowed = in_window(chart)
    assert "Power Ballad" in windowed
    assert "The Sheep Detectives" in windowed
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_boxoffice.py -v`
Expected: FAIL with `ImportError: cannot import name 'in_window'`

- [ ] **Step 3: Add `WINDOW_START`**

In `summer_movie_wager/model/preopening.py`, replace line 7:

```python
WINDOW_END = date(2026, 9, 7)
```

with:

```python
# The wager scores domestic gross for films released inside this window, inclusive.
# WINDOW_START is May 1, not Apr 30: the play-along site's 2026-05-04 gross list
# contains only May 1 releases, and omits The Story of Everything (Apr 30).
WINDOW_START = date(2026, 5, 1)
WINDOW_END = date(2026, 9, 7)  # Labor Day 2026
```

- [ ] **Step 4: Add `in_window`**

Append to `summer_movie_wager/ingest/boxoffice.py`:

```python
def in_window(chart: dict[str, BoxOfficeRow]) -> dict[str, BoxOfficeRow]:
    """Keep only releases inside the wager window (inclusive on both ends)."""

    return {
        title: row
        for title, row in chart.items()
        if WINDOW_START <= row.release_date <= WINDOW_END
    }
```

and add the import at the top of the file, below the `selectolax` import:

```python
from summer_movie_wager.model.preopening import WINDOW_END, WINDOW_START
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_boxoffice.py -v`
Expected: PASS — 11 passed

- [ ] **Step 6: Run the whole suite and lint**

Run: `uv run pytest && uv run ruff format . && uv run ruff check .`
Expected: all tests pass, `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add summer_movie_wager/model/preopening.py summer_movie_wager/ingest/boxoffice.py tests/test_boxoffice.py
git commit -m "feat: filter Box Office Mojo chart to the 2026-05-01..2026-09-07 wager window"
```

---

### Task 3: Resolve grosses — carry-forward and Labor Day freeze

**Files:**
- Modify: `summer_movie_wager/render/build.py` (add `_resolve_grosses` near `_load_history`, around line 411)
- Modify: `tests/test_build.py` (add tests)

**Interfaces:**
- Consumes: `BoxOfficeRow`, `in_window` (Task 1/2); `WINDOW_END`.
- Produces:
  - `def _resolve_grosses(chart: dict[str, BoxOfficeRow], history: dict[str, list[tuple[date, float]]], *, today: date) -> tuple[dict[str, float], set[str]]` — returns `(grosses, carried_titles)` where `carried_titles` are titles present only in history.

Two behaviours this must get right:

1. **Carry-forward.** A film that drops off the chart keeps its last observed gross instead of collapsing to 0. Grosses are monotonic, so take `max(chart_value, last_history_value)` — this also absorbs a downward revision on Box Office Mojo's side.
2. **Labor Day freeze.** The chart's cumulative keeps growing after Labor Day, but the wager only counts gross through 2026-09-07. The chart reflects data through *yesterday*, so it stays usable on 2026-09-08 and becomes unusable from 2026-09-09 onward, at which point the frozen history values are the answer.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_build.py`:

```python
from summer_movie_wager.ingest.boxoffice import BoxOfficeRow
from summer_movie_wager.render.build import _resolve_grosses


def _row(title, gross, release=date(2026, 5, 8)):
    return BoxOfficeRow(title=title, cumulative_gross=gross, release_date=release)


def test_resolve_grosses_prefers_the_live_chart():
    chart = {"Toy Story 5": _row("Toy Story 5", 441_455_658.0, date(2026, 6, 19))}
    history = {"Toy Story 5": [(date(2026, 7, 20), 429_878_644.0)]}
    grosses, carried = _resolve_grosses(chart, history, today=date(2026, 7, 25))
    assert grosses["Toy Story 5"] == 441_455_658.0
    assert carried == set()


def test_resolve_grosses_carries_forward_a_film_that_left_the_chart():
    # The Sheep Detectives is the reason this exists: it fell out of the
    # play-along top 13 and must not collapse to zero.
    chart = {}
    history = {"The Sheep Detectives": [
        (date(2026, 7, 13), 66_042_291.0),
        (date(2026, 7, 20), 66_078_506.0),
    ]}
    grosses, carried = _resolve_grosses(chart, history, today=date(2026, 7, 25))
    assert grosses["The Sheep Detectives"] == 66_078_506.0
    assert carried == {"The Sheep Detectives"}


def test_resolve_grosses_never_lets_a_gross_go_down():
    chart = {"Obsession": _row("Obsession", 240_017_600.0, date(2026, 5, 15))}
    history = {"Obsession": [(date(2026, 7, 20), 258_387_140.0)]}
    grosses, _ = _resolve_grosses(chart, history, today=date(2026, 7, 25))
    assert grosses["Obsession"] == 258_387_140.0


def test_resolve_grosses_still_uses_the_chart_the_day_after_labor_day():
    # Run on Sep 8, the chart reports through Sep 7 -- exactly the wager cutoff.
    chart = {"Toy Story 5": _row("Toy Story 5", 460_000_000.0, date(2026, 6, 19))}
    history = {"Toy Story 5": [(date(2026, 8, 31), 455_000_000.0)]}
    grosses, _ = _resolve_grosses(chart, history, today=date(2026, 9, 8))
    assert grosses["Toy Story 5"] == 460_000_000.0


def test_resolve_grosses_freezes_after_labor_day():
    # Run on Sep 10, the chart includes Sep 8-9 gross, which the wager excludes.
    chart = {"Toy Story 5": _row("Toy Story 5", 470_000_000.0, date(2026, 6, 19))}
    history = {"Toy Story 5": [
        (date(2026, 9, 7), 461_000_000.0),
        (date(2026, 9, 9), 468_000_000.0),
    ]}
    grosses, _ = _resolve_grosses(chart, history, today=date(2026, 9, 10))
    assert grosses["Toy Story 5"] == 461_000_000.0


def test_resolve_grosses_ignores_history_after_the_cutoff():
    chart = {}
    history = {"Backrooms": [
        (date(2026, 9, 7), 200_000_000.0),
        (date(2026, 9, 14), 201_000_000.0),
    ]}
    grosses, _ = _resolve_grosses(chart, history, today=date(2026, 9, 20))
    assert grosses["Backrooms"] == 200_000_000.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_build.py -v`
Expected: FAIL with `ImportError: cannot import name '_resolve_grosses'`

- [ ] **Step 3: Write the implementation**

In `summer_movie_wager/render/build.py`, add this function immediately after `_load_history` (which ends at line 411):

```python
def _resolve_grosses(
    chart: dict[str, BoxOfficeRow],
    history: dict[str, list[tuple[date, float]]],
    *,
    today: date,
) -> tuple[dict[str, float], set[str]]:
    """Merge the live Box Office Mojo chart with recorded history.

    Returns `(grosses, carried_titles)`.

    Two things history gives us that a single chart read cannot:

    1. A film that has fallen off the 200-row chart keeps its last observed gross
       instead of collapsing to 0. Grosses only go up, so we take the max of the
       two -- which also absorbs a downward revision on Box Office Mojo's side.
    2. After Labor Day the chart keeps accumulating gross the wager doesn't count.
       The chart reports through *yesterday*, so it is still exactly right when run
       on WINDOW_END + 1 and wrong from WINDOW_END + 2 onward; past that we fall
       back to the last observation recorded on or before WINDOW_END.

    `carried_titles` is the set of titles that came from history alone. Callers
    surface it as a warning: a title carried forward while the film is plainly
    still playing means the chart title drifted from ours.
    """

    cutoff = min(today, WINDOW_END)
    # The chart reflects data through yesterday, so it is usable while that day
    # is still inside the window.
    chart_usable = (today - timedelta(days=1)) <= WINDOW_END

    grosses: dict[str, float] = {}
    for title, obs in history.items():
        # Max over gross values, not over (date, gross) tuples: tuple comparison
        # would pick the latest-DATED entry, which regresses the film's gross when
        # Box Office Mojo revises a number downward.
        in_range = [g for d, g in obs if d <= cutoff]
        if in_range:
            grosses[title] = max(in_range)

    if chart_usable:
        for title, row in chart.items():
            grosses[title] = max(row.cumulative_gross, grosses.get(title, 0.0))

    # Membership in `chart` decides this, not whether the chart's VALUES were
    # usable this run -- otherwise every tracked film reads as carried once the
    # Labor Day freeze kicks in.
    carried = {title for title in grosses if title not in chart}
    return grosses, carried
```

Then extend the imports at the top of `build.py`. Change line 9:

```python
from datetime import UTC, date, datetime
```

to:

```python
from datetime import UTC, date, datetime, timedelta
```

and add after line 16 (`from summer_movie_wager.ingest.scraper import fetch_snapshot`):

```python
from summer_movie_wager.ingest.boxoffice import BoxOfficeRow
```

Import only `BoxOfficeRow` here — `fetch_year_chart`, `in_window` and `WINDOW_START` have no caller until Task 5 and would trip ruff's `F401` now.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_build.py -v`
Expected: PASS — all tests in the file pass, including the 6 new ones

- [ ] **Step 5: Run the whole suite and lint**

Run: `uv run pytest && uv run ruff format . && uv run ruff check .`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add summer_movie_wager/render/build.py tests/test_build.py
git commit -m "feat: carry forward grosses for films off the chart and freeze after Labor Day"
```

---

### Task 4: Closed-film status and projection

**Files:**
- Modify: `summer_movie_wager/render/build.py:235-297` (`_normalize_movies`)
- Modify: `summer_movie_wager/render/build.py:310-352` (`_project_all`)
- Modify: `summer_movie_wager/render/build.py:525-593` (`_build_movie_rows`, the `src` label)
- Modify: `tests/test_build.py`

**Why this task exists:** today a played-out film silently drops to a 0 gross and gets classified `PRE_RELEASE`, so nothing downstream ever needed a `CLOSED` branch. Once Task 3 carries its real gross forward, `_project_all` would fall through to `else: gross, sigma = 0.0, 0.0` and throw away $66M. `MovieStatus.CLOSED` already exists in `types.py:14` and `_STATUS_LABELS` already maps `"closed"` (`build.py:519`) — only the two branches are missing.

A film is closed when it is absent from the current in-window chart but present in history. Absent from a 200-row chart whose floor is $468,400 means it is done; there is no threshold to tune. Films still on the chart stay `IN_THEATERS` and the decay model handles their tail — `_resolve_wow` (`model/decay.py:106`) already reads the flattening week-over-week ratios out of history and projects almost nothing further.

**Interfaces:**
- Consumes: `_resolve_grosses` (Task 3); `in_window` (Task 2).
- Produces: `_normalize_movies` gains two keyword-only parameters and its signature becomes:
  ```python
  def _normalize_movies(
      snapshot: SiteSnapshot,
      overrides: dict[str, Any],
      preopening: dict[str, PreopeningEntry],
      *,
      grosses: dict[str, float],
      chart: dict[str, BoxOfficeRow],
      carried: set[str],
      today: date,
  ) -> dict[str, dict[str, Any]]:
  ```

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_build.py`:

```python
from summer_movie_wager.render.build import _normalize_movies
from summer_movie_wager.types import PlayerPicks, SiteSnapshot


def _snapshot(picks_titles):
    picks = PlayerPicks(
        username="bclarke",
        ranked=picks_titles[:10],
        dark_horses=picks_titles[10:13],
    )
    return SiteSnapshot(
        captured_at=date(2026, 7, 25),
        players={"bclarke": picks},
        cumulative_grosses={},
        site_reported_points={},
    )


_THIRTEEN = [f"Film {i}" for i in range(13)]


def test_normalize_marks_a_carried_film_closed():
    snap = _snapshot(_THIRTEEN)
    movies = _normalize_movies(
        snap,
        {},
        {},
        grosses={"The Sheep Detectives": 66_078_506.0},
        chart={},
        carried={"The Sheep Detectives"},
        today=date(2026, 7, 25),
    )
    m = movies["The Sheep Detectives"]
    assert m["status"] == MovieStatus.CLOSED
    assert m["cumulative"] == 66_078_506.0


def test_normalize_takes_release_date_from_the_chart():
    snap = _snapshot(_THIRTEEN)
    chart = {"Moana": BoxOfficeRow(
        title="Moana", cumulative_gross=95_069_653.0, release_date=date(2026, 7, 10)
    )}
    movies = _normalize_movies(
        snap, {}, {},
        grosses={"Moana": 95_069_653.0},
        chart=chart,
        carried=set(),
        today=date(2026, 7, 25),
    )
    assert movies["Moana"]["release_date"] == date(2026, 7, 10)
    assert movies["Moana"]["status"] == MovieStatus.IN_THEATERS


def test_closed_film_projects_its_final_gross():
    movies = {
        "The Sheep Detectives": {
            "title": "The Sheep Detectives",
            "release_date": date(2026, 5, 8),
            "status": MovieStatus.CLOSED,
            "category": Category.WIDE,
            "cumulative": 66_078_506.0,
        }
    }
    projs = _project_all(movies, {}, today=date(2026, 7, 25))
    assert projs[0].median_in_window_gross == 66_078_506.0
    assert projs[0].sigma == 0.0
    assert projs[0].floor == 66_078_506.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_build.py -v`
Expected: FAIL — `_normalize_movies() got an unexpected keyword argument 'grosses'`, and the closed-projection test fails asserting `0.0 == 66078506.0`

- [ ] **Step 3: Rewrite `_normalize_movies`**

Replace the body of `_normalize_movies` in `summer_movie_wager/render/build.py` (lines 235–297) with:

```python
def _normalize_movies(
    snapshot: SiteSnapshot,
    overrides: dict[str, Any],
    preopening: dict[str, PreopeningEntry],
    *,
    grosses: dict[str, float],
    chart: dict[str, BoxOfficeRow],
    carried: set[str],
    today: date,
) -> dict[str, dict[str, Any]]:
    """
    Given the picks, the resolved grosses, the Box Office Mojo chart, the overrides
    and the preopening projections, insert all distinct movies into a single
    dictionary keyed by canonical title, carrying release date, status, category
    and cumulative gross.

    Candidates are the films that could matter to the wager: everything anyone
    picked, everything with an analyst estimate, everything already in history,
    and the top of the in-window chart. The chart's long tail is excluded from the
    movie table on purpose -- it is ~120 films that cannot reach the top 10 and
    would bury the ones that can. Picked films are always included regardless of
    where they sit on the chart, which is how Power Ballad gets displayed.
    """

    movies: dict[str, dict[str, Any]] = {}
    candidates: set[str] = set()
    for picks in snapshot.players.values():
        candidates.update(picks.ranked + picks.dark_horses)
    candidates.update(preopening.keys())
    candidates.update(grosses.keys() & _chart_contenders(chart))
    candidates.update(carried)

    for title in candidates:
        ov = overrides.get(title, {}) or {}
        canonical = ov.get("alias_of", title)
        category = Category(ov.get("category", "wide"))
        cumulative = grosses.get(canonical, 0.0)
        chart_row = chart.get(canonical)

        if "release_date" in ov:
            release = date.fromisoformat(str(ov["release_date"]))
        elif chart_row is not None:
            # An actual reported release date beats an analyst's projected one.
            release = chart_row.release_date
        elif canonical in preopening:
            release = preopening[canonical].release_date
        elif cumulative > 0:
            release = today
        else:
            release = WINDOW_END

        if "status" in ov:
            status = MovieStatus(ov["status"])
        elif release > today:
            status = MovieStatus.PRE_RELEASE
        elif cumulative > 0 and chart_row is None:
            # Has gross but is no longer on a 200-row chart whose floor is under
            # $500K: the run is over and this is the final number.
            status = MovieStatus.CLOSED
        elif cumulative > 0:
            status = MovieStatus.IN_THEATERS
        else:
            status = MovieStatus.PRE_RELEASE

        movies[canonical] = {
            "title": canonical,
            "release_date": release,
            "status": status,
            "category": category,
            "cumulative": cumulative,
        }
    return movies


# How many of the in-window chart's films to carry into the movie table beyond the
# ones players picked. The top-10 race is decided well inside this; the rest of the
# 200-row chart is noise.
_CHART_CONTENDERS = 25


def _chart_contenders(chart: dict[str, BoxOfficeRow]) -> set[str]:
    """The highest-grossing in-window films, as candidates for the top 10."""

    ranked = sorted(chart.values(), key=lambda r: r.cumulative_gross, reverse=True)
    return {r.title for r in ranked[:_CHART_CONTENDERS]}
```

- [ ] **Step 4: Add the `CLOSED` branch to `_project_all`**

In `_project_all`, insert a branch ahead of the `IN_THEATERS` check, and widen the `floor` assignment. Replace:

```python
    for title, m in movies.items():
        if m["status"] == MovieStatus.IN_THEATERS:
```

with:

```python
    for title, m in movies.items():
        if m["status"] == MovieStatus.CLOSED:
            # The run is over: the observed cumulative is the final answer, with
            # no uncertainty left to model.
            gross, sigma = m["cumulative"], 0.0
        elif m["status"] == MovieStatus.IN_THEATERS:
```

and replace:

```python
        floor = m["cumulative"] if m["status"] == MovieStatus.IN_THEATERS else 0.0
```

with:

```python
        floor = (
            m["cumulative"]
            if m["status"] in (MovieStatus.IN_THEATERS, MovieStatus.CLOSED)
            else 0.0
        )
```

- [ ] **Step 5: Fix the source label for closed films**

In `_build_movie_rows`, replace:

```python
        src = "decay model" if m["status"] == MovieStatus.IN_THEATERS else "analyst estimate"
```

with:

```python
        if m["status"] == MovieStatus.CLOSED:
            src = "final gross"
        elif m["status"] == MovieStatus.IN_THEATERS:
            src = "decay model"
        else:
            src = "analyst estimate"
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_build.py -v`
Expected: PASS

- [ ] **Step 7: Run the whole suite and lint**

Run: `uv run pytest && uv run ruff format . && uv run ruff check .`
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add summer_movie_wager/render/build.py tests/test_build.py
git commit -m "feat: classify played-out films as closed and project their final gross"
```

---

### Task 5: Wire the pipeline, keep the site check honest, update docs

**Files:**
- Modify: `summer_movie_wager/render/build.py:71-200` (`main`)
- Modify: `summer_movie_wager/render/build.py:687-706` (`_append_box_office_history`)
- Modify: `README.md` (window dates, data sources, pipeline steps)

**Interfaces:**
- Consumes: everything from Tasks 1–4.
- Produces: `def _append_box_office_history(grosses: dict[str, float], *, today: date) -> None` — note this **changes the signature**, it no longer takes a `SiteSnapshot`.

The site scrape stays. It is still the only source for picks and for `site_reported_points`, and per the decision on this change: **the leaderboard shows points computed from Box Office Mojo's more complete top 10, while `_validate_against_site` keeps scoring the site's own gross list against the site's own standings.** Comparing our BOM-derived points to the site's points would conflate "our scoring engine is broken" with "our data is fresher than theirs", destroying the guardrail.

- [ ] **Step 1: Add the Box Office Mojo fetch and gross resolution to `main`**

First extend the imports Task 3 deliberately left short. Change:

```python
from summer_movie_wager.ingest.boxoffice import BoxOfficeRow
from summer_movie_wager.model.preopening import WINDOW_END, project_preopening
```

to:

```python
from summer_movie_wager.ingest.boxoffice import BoxOfficeRow, fetch_year_chart, in_window
from summer_movie_wager.model.preopening import WINDOW_END, WINDOW_START, project_preopening
```

Then, in `summer_movie_wager/render/build.py`, replace lines 116–127 (from the `# This is the real value-add` comment through the `_warn_missing_projections(...)` call) with:

```python
    # Cumulative grosses come from Box Office Mojo, not the play-along site. The
    # site only publishes its top 13, so films below it (Power Ballad) never appear
    # and films that fall out of it (The Sheep Detectives) go dark mid-season.
    print("[build] fetching Box Office Mojo yearly chart", file=sys.stderr)
    chart = in_window(fetch_year_chart(year=WINDOW_START.year))
    history = _load_history()
    grosses, carried = _resolve_grosses(chart, history, today=today)
    if carried:
        print(
            f"[build] {len(carried)} film(s) carried forward from history "
            f"(off the chart, treated as closed):\n  - " + "\n  - ".join(sorted(carried)),
            file=sys.stderr,
        )

    # This is the real value-add of the pipeline.  Using the week-over-week decay
    # model and preopening projections, we can start to guess what each film will
    # gross in the wager window.
    overrides = _load_yaml(DATA_DIR / "movies_overrides.yaml")
    preopening_raw = _load_yaml(DATA_DIR / "preopening_projections.yaml")
    preopening = _parse_preopening(preopening_raw)

    movies = _normalize_movies(
        snapshot,
        overrides,
        preopening,
        grosses=grosses,
        chart=chart,
        carried=carried,
        today=today,
    )
    projections = _project_all(movies, preopening, today=today)
    _warn_missing_projections(movies, preopening, today=today)
```

- [ ] **Step 2: Split display scoring from the site cross-check**

Replace lines 151–157 (the `current_top10` / `current_pts` / `_validate_against_site` block) with:

```python
    # Displayed standings use the Box Office Mojo top 10 -- it sees films the play-along
    # site's top-13 table doesn't.
    current_top10 = _current_top_10(grosses)
    current_pts = {
        username: score_player(picks, current_top10) for username, picks in snapshot.players.items()
    }

    # The correctness check scores the *site's own* gross list against the site's own
    # standings. Comparing our BOM-derived points here instead would conflate a broken
    # scoring engine with data that is simply fresher than theirs.
    site_top10 = _current_top_10(snapshot.cumulative_grosses)
    site_pts = {
        username: score_player(picks, site_top10) for username, picks in snapshot.players.items()
    }
    _validate_against_site(site_pts, snapshot.site_reported_points)
```

- [ ] **Step 3: Write the resolved grosses to history, not the site's**

Replace the `_append_box_office_history` call at line 195:

```python
        _append_box_office_history(snapshot, today=today)
```

with:

```python
        _append_box_office_history(grosses, today=today)
```

and replace the function itself (lines 687–706) with:

```python
def _append_box_office_history(grosses: dict[str, float], *, today: date) -> None:
    """
    Append today's resolved cumulative grosses to `data/box_office_history.jsonl`,
    so the decay model can read week-over-week trends on the next run.

    Skipped when --local is passed. Closed films keep re-appearing at a flat value;
    that is intentional -- it is what lets a film that has left the chart entirely
    still carry its final gross into scoring.
    """

    box_path = DATA_DIR / "box_office_history.jsonl"
    with box_path.open("a") as f:
        for movie, gross in sorted(grosses.items()):
            f.write(
                json.dumps(
                    {
                        "movie": movie,
                        "date": today.isoformat(),
                        "cumulative_gross": gross,
                    }
                )
                + "\n"
            )
```

- [ ] **Step 4: Update the `main` docstring**

In the `main` docstring (lines 72–94), replace step 1 and insert a new step:

```
    1. fetch_snapshot:  Scrape thesummermoviewager.com for picks and the site's own
    reported standings.  Its top-13 gross table is used only for the correctness
    cross-check in step 7, never for projections.
    2. fetch_year_chart + in_window + _resolve_grosses:  Pull cumulative domestic
    grosses from Box Office Mojo's 2026 yearly chart, filter to films released in the
    wager window, and merge with recorded history so films that have left the chart
    keep their final gross and nothing counts gross earned after Labor Day.
```

and renumber the remaining steps 3–9.

- [ ] **Step 5: Run the whole suite and lint**

Run: `uv run pytest && uv run ruff format . && uv run ruff check .`
Expected: all pass. `tests/test_render_snapshot.py` builds its own `RenderInput` by hand and never runs the pipeline, so no golden HTML needs regenerating.

- [ ] **Step 6: Run the pipeline end to end, without touching history**

Run:
```bash
uv run python -m summer_movie_wager.render.build --local
```

Expected on stderr, in order:
- `[build] fetching site snapshot (2026-MM-DD)`
- `[build] fetching Box Office Mojo yearly chart`
- a carried-forward list that includes films no longer on the chart
- the existing missing-projection warning
- `[build] wrote .../docs/index.html`

Then verify the two films this change exists for actually landed:

```bash
uv run python -c "
import json
d = json.load(open('docs/data.json'))
p = {x['movie_title']: x for x in d['projections']}
for t in ('Power Ballad', 'The Sheep Detectives'):
    print(t, p.get(t))
"
```

Expected: both present, `The Sheep Detectives` with `median_in_window_gross` and `floor` at roughly $66,078,506 and `sigma` 0.0; `Power Ballad` with a non-zero gross around $2.6M.

- [ ] **Step 7: Eyeball the rendered page**

Run:
```bash
python3 -m http.server -d docs 8000
```

Open http://localhost:8000/ and confirm: The Sheep Detectives appears in the movies table with a "closed" badge and a "final gross" source; Power Ballad appears with a real number instead of a blank; the table is not flooded with dozens of irrelevant micro-releases. Stop the server with Ctrl-C.

- [ ] **Step 8: Update the README**

Make these edits to `README.md`:
- Line 3 and line 208 (`## Wager window`): change `2026-04-30` to `2026-05-01` in both places. Add to the Wager window section: *"May 1 is the first Friday of May and matches what the play-along site scores — its 2026-05-04 gross list contains only May 1 releases."*
- In the architecture / pipeline section (around lines 71 and the "8 steps" list): document that cumulative grosses come from `https://www.boxofficemojo.com/year/2026/` via `ingest/boxoffice.py`, and that thesummermoviewager.com is now scraped only for picks and for the standings cross-check.
- In the data-file table: note that `data/box_office_history.jsonl` now records Box Office Mojo figures for every in-window film plus every picked film, not just the site's top 13, and that closed films keep re-appearing at a flat final value by design.
- Add a short "Known limits" note: the yearly chart is capped at 200 rows (floor ≈ $468K as of July 2026); a film below that is carried forward from history and treated as closed. Also note that the non-zero-projection gate for running the simulation (25 films, `build.py`) is now easily cleared by released films alone, so it no longer implicitly waits on an analyst estimate for *Spider-Man: Brand New Day* — `_warn_missing_projections` is the remaining signal for that.

- [ ] **Step 9: Commit**

```bash
git add summer_movie_wager/render/build.py README.md
git commit -m "feat: source cumulative grosses from Box Office Mojo instead of the play-along top 13"
```

---

## Verification

After all five tasks:

1. `uv run pytest` — full suite green, including the 11 new `tests/test_boxoffice.py` tests and the 9 new `tests/test_build.py` tests. No test touches the network.
2. `uv run ruff format --check . && uv run ruff check .` — clean.
3. `uv run python -m summer_movie_wager.render.build --local` — completes, and `docs/data.json` contains projections for both *Power Ballad* and *The Sheep Detectives*.
4. `git diff --stat data/` — empty. `--local` must not have appended to either history file.
5. Serve `docs/` and confirm the four pages render, the leaderboard is populated, and the movies table shows closed films with their final gross.
6. Only after the above: run without `--local` to append a real history row, then `git diff data/box_office_history.jsonl` and confirm the new rows cover the full in-window slate rather than just the site's top 13.

## Known consequences to watch

- **The leaderboard may disagree with thesummermoviewager.com.** That is intended — our data is more complete and usually fresher. `_validate_against_site` still guards the scoring engine independently, so a warning from it remains a real bug signal.
- **Title drift is the main fragility.** All 28 existing history titles match Box Office Mojo exactly today, so no alias table is needed. If Box Office Mojo renames something, it will surface as an unexpected entry in the carried-forward warning from Task 5 Step 1; the fix is an `alias_of` entry in `data/movies_overrides.yaml`, whose schema already supports it.
- **Post-Labor-Day runs freeze.** From 2026-09-09 onward the chart is ignored and the last observation on or before 2026-09-07 is used, so a history row must exist from a run on 09-07 or 09-08 for the final numbers to be right. Schedule that run.
