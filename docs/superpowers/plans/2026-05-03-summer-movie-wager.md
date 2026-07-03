# Summer Movie Wager 2026 — Tracker & Forecaster Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a static GitHub Pages site that scrapes the play-along URL on `thesummermoviewager.com` for picks and current box office, projects each picked movie's domestic gross during the wager window via a weekly-decay model (in-theaters) or hand-curated analyst estimates (pre-release), and runs a Monte Carlo simulation to surface per-player win probabilities and 80% prediction intervals.

**Architecture:** Python package with five pure-ish stages (ingest → normalize → project → score+simulate → render). No server, no DB. Refresh runs only when the user clicks "Run workflow" on a manually-triggered GitHub Action that regenerates `docs/` and commits.

**Tech Stack:** Python 3.12+ (uv-managed), `httpx`, `selectolax`, `pydantic` v2, `numpy`, `jinja2`, `pyyaml`, `pytest`, `ruff`. No web framework, no database, no JS framework.

---

## File Structure

Files created during this plan (in roughly the order they appear):

```
pyproject.toml                                   — project metadata, deps, ruff/pytest config
.python-version                                  — pin 3.12 for uv
summer_movie_wager/__init__.py
summer_movie_wager/types.py                      — Pydantic models (single source of truth)
summer_movie_wager/score/__init__.py
summer_movie_wager/score/rules.py                — wager scoring engine (pure)
summer_movie_wager/model/__init__.py
summer_movie_wager/model/preopening.py           — Mode B pre-release projection (pure)
summer_movie_wager/model/decay.py                — Mode A in-theaters projection (pure)
summer_movie_wager/model/simulate.py             — Monte Carlo orchestrator (pure, numpy)
summer_movie_wager/ingest/__init__.py
summer_movie_wager/ingest/scraper.py             — fetch + parse play-along URL
summer_movie_wager/ingest/picks_guard.py         — drift detection vs. picks_snapshot_2026.yaml
summer_movie_wager/render/__init__.py
summer_movie_wager/render/build.py               — pipeline glue + CLI entrypoint
summer_movie_wager/render/templates/index.html.j2
summer_movie_wager/render/static/style.css
data/picks_snapshot_2026.yaml                    — source-of-truth locked picks
data/preopening_projections.yaml                 — analyst estimates (hand-curated)
data/movies_overrides.yaml                       — scraper-drift fixes + category tags
data/box_office_history.jsonl                    — append-only per-run snapshots
data/forecast_history.jsonl                      — append-only win-odds snapshots
docs/index.html                                  — generated GitHub Pages entry point
docs/data.json                                   — generated full snapshot
.github/workflows/refresh.yml                    — workflow_dispatch only
tests/__init__.py
tests/conftest.py
tests/fixtures/playalong.html                    — committed live capture for offline tests
tests/fixtures/expected_index.html               — render snapshot fixture
tests/test_scoring.py
tests/test_preopening.py
tests/test_decay.py
tests/test_simulate.py
tests/test_scraper.py
tests/test_picks_guard.py
tests/test_render_snapshot.py
```

Files already present and not modified:
- `README.md`, `.gitignore`, `docs/superpowers/specs/2026-05-03-summer-movie-wager-design.md`

---

## Task 1: Project Skeleton (uv + pyproject + pytest)

**Goal:** Empty package, pinned Python, ruff configured, pytest can be invoked and finds zero tests cleanly.

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `summer_movie_wager/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Confirm `uv` is installed**

Run: `uv --version`
Expected: prints a version like `uv 0.5.x` or higher. If "command not found", install via `curl -LsSf https://astral.sh/uv/install.sh | sh` and re-run.

- [ ] **Step 2: Pin Python**

Create `.python-version`:
```
3.12
```

- [ ] **Step 3: Create `pyproject.toml`**

Create `pyproject.toml`:
```toml
[project]
name = "summer-movie-wager"
version = "0.1.0"
description = "Tracker and forecaster for the 2026 Summer Movie Wager"
requires-python = ">=3.12"
dependencies = [
    "httpx>=0.27",
    "selectolax>=0.3.21",
    "pydantic>=2.7",
    "numpy>=2.0",
    "jinja2>=3.1",
    "pyyaml>=6.0",
]

[dependency-groups]
dev = [
    "pytest>=8.2",
    "pytest-snapshot>=0.9",
    "ruff>=0.6",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["summer_movie_wager"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "RUF"]
```

- [ ] **Step 4: Create empty package + test scaffolding**

Create `summer_movie_wager/__init__.py`:
```python
"""Summer Movie Wager 2026 — tracker and forecaster."""
```

Create `tests/__init__.py` (empty file).

Create `tests/conftest.py`:
```python
"""Shared pytest fixtures."""
```

- [ ] **Step 5: Sync deps and run pytest**

Run: `uv sync`
Expected: writes `uv.lock`, creates `.venv/`.

Run: `uv run pytest`
Expected: `0 items` collected, exit code 5 (no tests found) — that's fine for a skeleton.

Run: `uv run ruff check .`
Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock .python-version summer_movie_wager/__init__.py tests/__init__.py tests/conftest.py
git commit -m "chore: bootstrap uv project with pytest and ruff"
```

---

## Task 2: Pydantic Types

**Goal:** Single source of truth for the typed records used throughout the pipeline. Validate every type with a tiny round-trip test.

**Files:**
- Create: `summer_movie_wager/types.py`
- Create: `tests/test_types.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_types.py`:
```python
from datetime import date

import pytest

from summer_movie_wager.types import (
    Category,
    Confidence,
    MovieRecord,
    MovieStatus,
    PlayerPicks,
    Projection,
    SiteSnapshot,
)


def test_player_picks_validates_counts():
    picks = PlayerPicks(
        username="bclarke",
        ranked=["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        dark_horses=["K", "L", "M"],
    )
    assert picks.username == "bclarke"
    assert len(picks.ranked) == 10
    assert len(picks.dark_horses) == 3


def test_player_picks_rejects_wrong_ranked_count():
    with pytest.raises(ValueError):
        PlayerPicks(username="x", ranked=["A"] * 9, dark_horses=["K", "L", "M"])


def test_player_picks_rejects_wrong_dark_horse_count():
    with pytest.raises(ValueError):
        PlayerPicks(username="x", ranked=["A"] * 10, dark_horses=["K", "L"])


def test_player_picks_rejects_duplicate_titles():
    with pytest.raises(ValueError):
        PlayerPicks(
            username="x",
            ranked=["A", "A", "B", "C", "D", "E", "F", "G", "H", "I"],
            dark_horses=["J", "K", "L"],
        )


def test_movie_record_round_trip():
    m = MovieRecord(
        title="Toy Story 5",
        release_date=date(2026, 6, 19),
        status=MovieStatus.PRE_RELEASE,
        category=Category.ANIMATED_FAMILY,
        cumulative_gross_in_window=0.0,
        source="seed",
    )
    assert m.model_dump()["status"] == "pre_release"
    assert m.model_dump()["category"] == "animated_family"


def test_projection_records_median_and_sigma():
    p = Projection(movie_title="Toy Story 5", median_in_window_gross=180_000_000.0, sigma=0.30)
    assert p.median_in_window_gross == 180_000_000.0
    assert p.sigma == 0.30


def test_confidence_values():
    assert Confidence.HIGH.value == "high"
    assert Confidence.MED.value == "med"
    assert Confidence.LOW.value == "low"


def test_site_snapshot_holds_picks_and_grosses():
    snapshot = SiteSnapshot(
        captured_at=date(2026, 5, 3),
        players={
            "bclarke": PlayerPicks(
                username="bclarke",
                ranked=["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
                dark_horses=["K", "L", "M"],
            ),
        },
        cumulative_grosses={"A": 32_500_000.0},
        site_reported_points={"bclarke": 3},
    )
    assert snapshot.players["bclarke"].ranked[0] == "A"
    assert snapshot.cumulative_grosses["A"] == 32_500_000.0
    assert snapshot.site_reported_points["bclarke"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'summer_movie_wager.types'`.

- [ ] **Step 3: Implement the module**

Create `summer_movie_wager/types.py`:
```python
"""Typed records used across the pipeline."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MovieStatus(str, Enum):
    PRE_RELEASE = "pre_release"
    IN_THEATERS = "in_theaters"
    CLOSED = "closed"


class Category(str, Enum):
    WIDE = "wide"
    ANIMATED_FAMILY = "animated_family"


class Confidence(str, Enum):
    HIGH = "high"
    MED = "med"
    LOW = "low"


class PlayerPicks(BaseModel):
    model_config = ConfigDict(frozen=True)

    username: str
    ranked: list[str] = Field(min_length=10, max_length=10)
    dark_horses: list[str] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def _no_duplicate_titles(self) -> PlayerPicks:
        all_titles = self.ranked + self.dark_horses
        if len(set(all_titles)) != len(all_titles):
            raise ValueError("a player's 13 picks must all be distinct movie titles")
        return self


class MovieRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    release_date: date
    status: MovieStatus
    category: Category = Category.WIDE
    cumulative_gross_in_window: float = 0.0
    source: str = "scrape"


class PreopeningEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    release_date: date
    opening_weekend_estimate: float
    total_domestic_estimate: float
    confidence: Confidence
    source: str
    as_of: date
    notes: str = ""


class Projection(BaseModel):
    model_config = ConfigDict(frozen=True)

    movie_title: str
    median_in_window_gross: float
    sigma: float


class SiteSnapshot(BaseModel):
    """One scrape of the play-along URL."""

    model_config = ConfigDict(frozen=True)

    captured_at: date
    players: dict[str, PlayerPicks]
    cumulative_grosses: dict[str, float]
    site_reported_points: dict[str, int]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_types.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add summer_movie_wager/types.py tests/test_types.py
git commit -m "feat(types): add Pydantic models for picks, movies, projections, and snapshots"
```

---

## Task 3: Scoring Engine

**Goal:** Pure function `score_player(picks, top_10) -> int` that implements the full wager scoring rules. Tested against every rule branch.

**Files:**
- Create: `summer_movie_wager/score/__init__.py`
- Create: `summer_movie_wager/score/rules.py`
- Create: `tests/test_scoring.py`

- [ ] **Step 1: Create score package**

Create `summer_movie_wager/score/__init__.py`:
```python
"""Wager scoring engine."""

from summer_movie_wager.score.rules import score_player

__all__ = ["score_player"]
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_scoring.py`:
```python
import pytest

from summer_movie_wager.score import score_player
from summer_movie_wager.types import PlayerPicks


def make_picks(ranked: list[str], dark_horses: list[str] | None = None) -> PlayerPicks:
    if dark_horses is None:
        dark_horses = ["DH1", "DH2", "DH3"]
    # Pad ranked to 10 with disposable titles if caller passed fewer
    padded = list(ranked)
    i = 0
    while len(padded) < 10:
        padded.append(f"_filler_{i}")
        i += 1
    return PlayerPicks(username="t", ranked=padded[:10], dark_horses=dark_horses)


def test_correct_number_one_scores_13():
    picks = make_picks(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"])
    top_10 = ["A", "X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9"]
    assert score_player(picks, top_10) == 13  # A in #1 = 13; rest of picks miss top 10


def test_correct_number_ten_scores_13():
    picks = make_picks(["X", "Y", "Z", "Q", "R", "S", "T", "U", "V", "W"])
    top_10 = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "W"]  # W is in #10
    assert score_player(picks, top_10) == 13


def test_correct_middle_position_scores_10():
    picks = make_picks(["X", "X2", "X3", "X4", "TARGET", "X5", "X6", "X7", "X8", "X9"])
    top_10 = ["A1", "A2", "A3", "A4", "TARGET", "A6", "A7", "A8", "A9", "A10"]
    assert score_player(picks, top_10) == 10


def test_off_by_one_scores_7():
    # TARGET picked at #5, actual #6 → off by 1
    picks = make_picks(["X", "X2", "X3", "X4", "TARGET", "X5", "X6", "X7", "X8", "X9"])
    top_10 = ["A1", "A2", "A3", "A4", "A5", "TARGET", "A7", "A8", "A9", "A10"]
    assert score_player(picks, top_10) == 7


def test_off_by_two_scores_5():
    picks = make_picks(["X", "X2", "X3", "TARGET", "X4", "X5", "X6", "X7", "X8", "X9"])
    top_10 = ["A1", "A2", "A3", "A4", "A5", "TARGET", "A7", "A8", "A9", "A10"]
    assert score_player(picks, top_10) == 5


def test_in_top_ten_off_by_three_scores_3():
    picks = make_picks(["TARGET", "X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9"])
    top_10 = ["A1", "A2", "A3", "TARGET", "A5", "A6", "A7", "A8", "A9", "A10"]
    assert score_player(picks, top_10) == 3


def test_missed_top_ten_scores_zero():
    picks = make_picks(["TARGET", "X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9"])
    top_10 = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10"]
    assert score_player(picks, top_10) == 0


def test_dark_horse_in_top_ten_scores_1():
    picks = make_picks(
        ["X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9", "X10"],
        dark_horses=["DARK", "DH2", "DH3"],
    )
    top_10 = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "DARK"]
    assert score_player(picks, top_10) == 1


def test_dark_horse_outside_top_ten_scores_zero():
    picks = make_picks(
        ["X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9", "X10"],
        dark_horses=["DARK", "DH2", "DH3"],
    )
    top_10 = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10"]
    assert score_player(picks, top_10) == 0


def test_combined_realistic_scenario():
    # Picks: #1 perfect, #4 off by 1, #6 in top 10 off by 4, #9 missed; one dark horse hits.
    picks = make_picks(
        [
            "PERFECT_1",
            "X2",
            "X3",
            "OFF_BY_ONE",
            "X5",
            "TOP10_BUT_FAR",
            "X7",
            "X8",
            "MISSED",
            "X10",
        ],
        dark_horses=["DARK_HIT", "DH2", "DH3"],
    )
    top_10 = [
        "PERFECT_1",   # picked #1, actual #1 → 13
        "TOP10_BUT_FAR",  # picked #6, actual #2 → in top 10 off by 4 → 3
        "A3",
        "A4",
        "OFF_BY_ONE",  # picked #4, actual #5 → off by 1 → 7
        "A6",
        "A7",
        "A8",
        "A9",
        "DARK_HIT",  # dark horse in top 10 → 1
    ]
    # MISSED isn't in top 10 → 0
    assert score_player(picks, top_10) == 13 + 3 + 7 + 1


def test_top_10_must_have_exactly_ten_entries():
    picks = make_picks(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"])
    with pytest.raises(ValueError):
        score_player(picks, ["A", "B", "C"])
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_scoring.py -v`
Expected: ImportError on `summer_movie_wager.score.rules`.

- [ ] **Step 4: Implement the scoring engine**

Create `summer_movie_wager/score/rules.py`:
```python
"""Wager scoring rules per https://thesummermoviewager.com/help.php."""

from summer_movie_wager.types import PlayerPicks


def _ranked_pick_points(predicted_position: int, actual_position: int) -> int:
    """Points for a single ranked pick. Positions are 1-indexed; actual_position is 0 for missed."""
    if actual_position == 0:  # not in top 10
        return 0
    distance = abs(predicted_position - actual_position)
    if distance == 0:
        # 13 if at endpoints (#1 or #10), 10 otherwise
        return 13 if actual_position in (1, 10) else 10
    if distance == 1:
        return 7
    if distance == 2:
        return 5
    return 3  # in top 10 but off by 3+


def score_player(picks: PlayerPicks, top_10: list[str]) -> int:
    """Compute the wager points a player earns given the final top 10 (rank-ordered)."""
    if len(top_10) != 10:
        raise ValueError(f"top_10 must have exactly 10 entries, got {len(top_10)}")

    actual_position: dict[str, int] = {title: i + 1 for i, title in enumerate(top_10)}

    total = 0
    for predicted_index, title in enumerate(picks.ranked, start=1):
        total += _ranked_pick_points(predicted_index, actual_position.get(title, 0))
    for dh in picks.dark_horses:
        if dh in actual_position:
            total += 1
    return total
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_scoring.py -v`
Expected: 11 passed.

- [ ] **Step 6: Commit**

```bash
git add summer_movie_wager/score/__init__.py summer_movie_wager/score/rules.py tests/test_scoring.py
git commit -m "feat(score): implement wager scoring engine with full rule coverage"
```

---

## Task 4: Pre-Release Projection (Mode B)

**Goal:** Pure function that converts an analyst's `(opening_weekend_estimate, total_domestic_estimate, confidence, release_date, category)` into `(in_window_gross, sigma)`.

**Files:**
- Create: `summer_movie_wager/model/__init__.py`
- Create: `summer_movie_wager/model/preopening.py`
- Create: `tests/test_preopening.py`

**Modeling assumptions baked in:**
- Treat `opening_weekend_estimate` as `week_1_gross` (Fri-Sun ≈ Fri-Thu for the purposes of this projection — the residual error is small relative to analyst uncertainty).
- Implied week-over-week multiplier `wow = 1 - opening_weekend_estimate / total_domestic_estimate`. This makes the implied infinite geometric series sum equal `total_domestic_estimate` exactly.
- If implied `wow` is degenerate (`<= 0` or `>= 1`), fall back to category default (0.55 wide / 0.65 animated_family).
- σ by confidence: high → 0.20, med → 0.30, low → 0.45.
- Movies with `release_date > window_end` return `(0.0, 0.0)`.

- [ ] **Step 1: Create model package**

Create `summer_movie_wager/model/__init__.py`:
```python
"""Projection and simulation models."""
```

- [ ] **Step 2: Write the failing tests**

Create `tests/test_preopening.py`:
```python
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
    # opening > total → implied wow < 0 (degenerate). Should not crash; should still produce a number.
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
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_preopening.py -v`
Expected: ImportError on `summer_movie_wager.model.preopening`.

- [ ] **Step 4: Implement Mode B**

Create `summer_movie_wager/model/preopening.py`:
```python
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_preopening.py -v`
Expected: 7 passed.

- [ ] **Step 6: Commit**

```bash
git add summer_movie_wager/model/__init__.py summer_movie_wager/model/preopening.py tests/test_preopening.py
git commit -m "feat(model): add pre-release projection (Mode B) with confidence-tagged sigma"
```

---

## Task 5: In-Theaters Projection (Mode A — Weekly Decay)

**Goal:** Pure function that takes `(release_date, today, cumulative_gross_to_date, category, observed_history)` and returns `(in_window_total, sigma)`. Uses defaults for week-over-week multiplier, blended toward observed values when ≥2 history snapshots exist.

**Files:**
- Create: `summer_movie_wager/model/decay.py`
- Create: `tests/test_decay.py`

**Modeling assumptions baked in:**
- Default WoW: `0.55` wide / `0.65` animated_family.
- With `n` snapshots (where `n ≥ 2`): observed WoW = geometric mean of inter-snapshot WoW ratios. Blend weight: `min(1.0, (n - 1) / 5)` toward observed (so 0.2 at 2 snapshots, 1.0 at 6+).
- Calibrate `week_1_gross` so the modeled cumulative-to-date matches the scraped cumulative-to-date.
- σ ranges from `0.30` (0 weeks observed) to `0.10` (≥6 weeks observed), interpolated linearly.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_decay.py`:
```python
from datetime import date

import pytest

from summer_movie_wager.model.decay import project_decay
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_decay.py -v`
Expected: ImportError on `summer_movie_wager.model.decay`.

- [ ] **Step 3: Implement Mode A**

Create `summer_movie_wager/model/decay.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_decay.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add summer_movie_wager/model/decay.py tests/test_decay.py
git commit -m "feat(model): add in-theaters weekly-decay projection (Mode A) with history blending"
```

---

## Task 6: Monte Carlo Simulator

**Goal:** Given per-movie `(median, sigma)` and the 8 players' picks, simulate 10,000 seasons and produce per-player win probabilities + final-score distribution percentiles.

**Files:**
- Create: `summer_movie_wager/model/simulate.py`
- Create: `tests/test_simulate.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_simulate.py`:
```python
import numpy as np
import pytest

from summer_movie_wager.model.simulate import simulate_season
from summer_movie_wager.types import PlayerPicks, Projection


def _picks(username: str, ranked: list[str]) -> PlayerPicks:
    return PlayerPicks(
        username=username,
        ranked=ranked,
        dark_horses=["DH1", "DH2", "DH3"],
    )


def test_certain_winner_has_high_win_prob():
    # Player A picks the 10 movies guaranteed to be top 10 (sigma 0). Should win every sim.
    movie_titles = [f"M{i}" for i in range(1, 11)]
    projections = [
        Projection(movie_title=t, median_in_window_gross=1_000_000_000 - i * 1_000_000, sigma=0.001)
        for i, t in enumerate(movie_titles)
    ]
    players = [
        _picks("perfect", movie_titles),
        _picks("bad", [f"X{i}" for i in range(1, 11)]),
    ]
    result = simulate_season(players, projections, n_trials=2000, seed=42)
    assert result.win_prob["perfect"] > 0.95
    assert result.win_prob["bad"] < 0.05
    # tie + win must be ≤ 1.0 per player; sum across all players ≥ 1 (some sim has a winner each time)
    for username in ["perfect", "bad"]:
        assert 0.0 <= result.win_prob[username] <= 1.0
        assert 0.0 <= result.tie_prob[username] <= 1.0


def test_prediction_intervals_make_sense():
    movie_titles = [f"M{i}" for i in range(1, 11)]
    projections = [
        Projection(movie_title=t, median_in_window_gross=200_000_000 - i * 5_000_000, sigma=0.30)
        for i, t in enumerate(movie_titles)
    ]
    players = [_picks("a", movie_titles)]
    result = simulate_season(players, projections, n_trials=5000, seed=1)
    p10 = result.p10_final_pts["a"]
    median = result.median_final_pts["a"]
    p90 = result.p90_final_pts["a"]
    assert p10 <= median <= p90


def test_deterministic_with_seed():
    movie_titles = [f"M{i}" for i in range(1, 11)]
    projections = [
        Projection(movie_title=t, median_in_window_gross=100_000_000, sigma=0.20)
        for t in movie_titles
    ]
    players = [_picks("a", movie_titles), _picks("b", list(reversed(movie_titles)))]
    r1 = simulate_season(players, projections, n_trials=500, seed=99)
    r2 = simulate_season(players, projections, n_trials=500, seed=99)
    assert r1.win_prob == r2.win_prob


def test_win_and_tie_probs_sum_to_one_across_players():
    # Across all players: P(win) + P(tied with anyone) sum to ~total trials worth of outcomes.
    # Simpler invariant: sum(win_prob[p]) + max(tie_prob[p]) >= 1 - epsilon when there is always a winner.
    movie_titles = [f"M{i}" for i in range(1, 11)]
    projections = [
        Projection(movie_title=t, median_in_window_gross=100_000_000, sigma=0.20)
        for t in movie_titles
    ]
    players = [_picks(f"p{i}", movie_titles) for i in range(3)]
    result = simulate_season(players, projections, n_trials=1000, seed=7)
    total_outcomes = sum(result.win_prob[p.username] for p in players) + max(
        result.tie_prob[p.username] for p in players
    )
    assert total_outcomes == pytest.approx(1.0, abs=0.05)


def test_zero_sigma_movies_make_outcome_deterministic():
    # All projections have sigma=0; result should be a single deterministic ranking per sim.
    movie_titles = [f"M{i}" for i in range(1, 11)]
    projections = [
        Projection(movie_title=t, median_in_window_gross=100_000_000 - i * 1_000_000, sigma=0.0)
        for i, t in enumerate(movie_titles)
    ]
    players = [_picks("a", movie_titles), _picks("b", list(reversed(movie_titles)))]
    result = simulate_season(players, projections, n_trials=500, seed=3)
    # Either a wins all or b wins all (depending on actual scoring) — but no variance.
    assert (
        result.win_prob["a"] in (0.0, 1.0) or result.win_prob["b"] in (0.0, 1.0)
        or abs(result.win_prob["a"] - result.win_prob["b"]) > 0.5
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_simulate.py -v`
Expected: ImportError on `summer_movie_wager.model.simulate`.

- [ ] **Step 3: Implement the simulator**

Create `summer_movie_wager/model/simulate.py`:
```python
"""Monte Carlo season simulator → per-player win probabilities + score percentiles."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from summer_movie_wager.score import score_player
from summer_movie_wager.types import PlayerPicks, Projection


@dataclass(frozen=True)
class SimulationResult:
    win_prob: dict[str, float]
    tie_prob: dict[str, float]
    median_final_pts: dict[str, float]
    p10_final_pts: dict[str, float]
    p90_final_pts: dict[str, float]


def simulate_season(
    players: list[PlayerPicks],
    projections: list[Projection],
    *,
    n_trials: int = 10_000,
    seed: int | None = None,
) -> SimulationResult:
    """Run Monte Carlo over per-movie lognormal samples.

    For each trial: sample each movie's gross, rank top 10, score every player, record outcome.
    """
    rng = np.random.default_rng(seed)
    movie_titles = [p.movie_title for p in projections]
    n_movies = len(movie_titles)
    if n_movies < 10:
        raise ValueError(f"need at least 10 projected movies, got {n_movies}")

    medians = np.array([p.median_in_window_gross for p in projections], dtype=float)
    sigmas = np.array([p.sigma for p in projections], dtype=float)

    # samples shape: (n_trials, n_movies)
    # Lognormal draw: exp(mu + sigma * Z) where mu = log(median).
    # Guard against median=0 (would produce log(0)). Treat zero-median movies as fixed at 0.
    samples = np.zeros((n_trials, n_movies), dtype=float)
    nonzero = medians > 0
    if nonzero.any():
        log_medians = np.log(medians[nonzero])
        z = rng.standard_normal((n_trials, int(nonzero.sum())))
        samples[:, nonzero] = np.exp(log_medians + sigmas[nonzero] * z)

    # Rank each row, take top-10 indices descending by gross
    # argsort ascending; reverse and slice first 10
    top_10_indices = np.argsort(-samples, axis=1)[:, :10]

    # Score each player against each trial's top-10
    pts_per_player: dict[str, np.ndarray] = {}
    for player in players:
        scores = np.empty(n_trials, dtype=int)
        for trial in range(n_trials):
            top_titles = [movie_titles[i] for i in top_10_indices[trial]]
            scores[trial] = score_player(player, top_titles)
        pts_per_player[player.username] = scores

    # Aggregate outcomes per player
    score_matrix = np.stack([pts_per_player[p.username] for p in players])  # (n_players, n_trials)
    max_per_trial = score_matrix.max(axis=0)
    is_top = score_matrix == max_per_trial
    n_winners_per_trial = is_top.sum(axis=0)

    win_prob: dict[str, float] = {}
    tie_prob: dict[str, float] = {}
    median_pts: dict[str, float] = {}
    p10_pts: dict[str, float] = {}
    p90_pts: dict[str, float] = {}

    for i, player in enumerate(players):
        is_top_player = is_top[i]
        strict_wins = (is_top_player & (n_winners_per_trial == 1)).sum()
        ties = (is_top_player & (n_winners_per_trial > 1)).sum()
        win_prob[player.username] = float(strict_wins) / n_trials
        tie_prob[player.username] = float(ties) / n_trials
        s = score_matrix[i]
        median_pts[player.username] = float(np.median(s))
        p10_pts[player.username] = float(np.percentile(s, 10))
        p90_pts[player.username] = float(np.percentile(s, 90))

    return SimulationResult(
        win_prob=win_prob,
        tie_prob=tie_prob,
        median_final_pts=median_pts,
        p10_final_pts=p10_pts,
        p90_final_pts=p90_pts,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_simulate.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add summer_movie_wager/model/simulate.py tests/test_simulate.py
git commit -m "feat(model): add Monte Carlo season simulator with win/tie probs and percentiles"
```

---

## Task 7: Capture HTML Fixture

**Goal:** Save one real capture of the play-along URL into `tests/fixtures/playalong.html` so all scraper tests run offline.

**Files:**
- Create: `tests/fixtures/playalong.html`

- [ ] **Step 1: Create fixtures directory**

Run: `mkdir -p tests/fixtures`

- [ ] **Step 2: Capture the page**

Run:
```bash
curl -L --fail \
  'https://thesummermoviewager.com/index.php?year=2026&addPlayer=bclarke,vivrad,zmeister,brettfern,carleigh,radhadr,emsullivan,mhartje&playAlongOnly=' \
  -o tests/fixtures/playalong.html
```
Expected: file is created with a non-trivial size (likely 100KB+).

Run: `wc -c tests/fixtures/playalong.html`
Expected: prints a byte count > 50000.

- [ ] **Step 3: Sanity check the capture**

Run: `grep -c 'a_bclarke' tests/fixtures/playalong.html`
Expected: ≥ 1 (the bclarke anchor exists).

Run: `grep -c 'a_vivrad' tests/fixtures/playalong.html`
Expected: ≥ 1.

If either grep returns 0, the page format may have changed — investigate before continuing.

- [ ] **Step 4: Commit**

```bash
git add tests/fixtures/playalong.html
git commit -m "test(fixtures): capture live play-along page for offline scraper tests"
```

---

## Task 8: Scraper

**Goal:** Parse the captured HTML into a `SiteSnapshot`. The exact selectors will be discovered while implementing — the test asserts the *outcome*, not the parsing approach.

**Files:**
- Create: `summer_movie_wager/ingest/__init__.py`
- Create: `summer_movie_wager/ingest/scraper.py`
- Create: `tests/test_scraper.py`

- [ ] **Step 1: Create ingest package**

Create `summer_movie_wager/ingest/__init__.py`:
```python
"""Site ingestion (scraping + drift guards)."""
```

- [ ] **Step 2: Write the failing tests against the fixture**

Create `tests/test_scraper.py`:
```python
from datetime import date
from pathlib import Path

import pytest

from summer_movie_wager.ingest.scraper import parse_snapshot

FIXTURE = Path(__file__).parent / "fixtures" / "playalong.html"
EXPECTED_USERNAMES = {
    "bclarke", "vivrad", "zmeister", "brettfern",
    "carleigh", "radhadr", "emsullivan", "mhartje",
}


@pytest.fixture
def snapshot():
    html = FIXTURE.read_text(encoding="utf-8")
    return parse_snapshot(html, captured_at=date(2026, 5, 3))


def test_all_eight_players_parsed(snapshot):
    assert set(snapshot.players.keys()) == EXPECTED_USERNAMES


def test_each_player_has_ten_ranked_and_three_dark_horses(snapshot):
    for username, picks in snapshot.players.items():
        assert len(picks.ranked) == 10, f"{username} ranked count wrong"
        assert len(picks.dark_horses) == 3, f"{username} dark horse count wrong"


def test_known_pick_present(snapshot):
    # bclarke's #1 pick is Toy Story 5 (verified by hand at /index.php inspection time)
    assert snapshot.players["bclarke"].ranked[0] == "Toy Story 5"


def test_cumulative_grosses_include_known_movie(snapshot):
    # The Devil Wears Prada 2 had ~$32.5M cumulative at 2026-05-03 capture
    keys_lower = {k.lower(): v for k, v in snapshot.cumulative_grosses.items()}
    matched = [
        v for k, v in keys_lower.items() if "devil wears prada" in k
    ]
    assert matched, "Devil Wears Prada 2 not found in cumulative_grosses"
    assert max(matched) > 1_000_000  # any reasonable post-opening number


def test_site_reported_points_present_for_all_players(snapshot):
    assert set(snapshot.site_reported_points.keys()) == EXPECTED_USERNAMES
    for v in snapshot.site_reported_points.values():
        assert isinstance(v, int)
        assert v >= 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_scraper.py -v`
Expected: ImportError on `summer_movie_wager.ingest.scraper`.

- [ ] **Step 4: Inspect the fixture to discover the structure**

Open `tests/fixtures/playalong.html` and look for:
- `id="a_<username>"` anchors and the surrounding markup that holds the picks list
- The "Total Score" / current points table — find a stable selector for player → integer score
- Per-movie box office figures — find a stable selector for movie title → cumulative dollar value

Useful tools while exploring:
- `grep -A 50 'a_bclarke' tests/fixtures/playalong.html | head -100` — see the markup around bclarke's section
- `grep -i 'devil wears prada' tests/fixtures/playalong.html | head -20` — see how movie/gross rows are formatted
- `grep -i 'total score' tests/fixtures/playalong.html | head -20` — find the standings table

Take notes on selectors before writing the parser.

- [ ] **Step 5: Implement the scraper**

Create `summer_movie_wager/ingest/scraper.py`:
```python
"""Scrape and parse the Summer Movie Wager play-along page."""

from __future__ import annotations

import re
from datetime import date

import httpx
from selectolax.parser import HTMLParser, Node

from summer_movie_wager.types import PlayerPicks, SiteSnapshot

PLAYALONG_URL = (
    "https://thesummermoviewager.com/index.php"
    "?year=2026"
    "&addPlayer=bclarke,vivrad,zmeister,brettfern,carleigh,radhadr,emsullivan,mhartje"
    "&playAlongOnly="
)


def fetch_snapshot(*, captured_at: date | None = None, timeout: float = 30.0) -> SiteSnapshot:
    """Fetch and parse the live play-along page."""
    if captured_at is None:
        captured_at = date.today()
    response = httpx.get(PLAYALONG_URL, timeout=timeout, follow_redirects=True)
    response.raise_for_status()
    return parse_snapshot(response.text, captured_at=captured_at)


def parse_snapshot(html: str, *, captured_at: date) -> SiteSnapshot:
    """Parse the captured HTML into a SiteSnapshot.

    NOTE: Selectors below were derived against the 2026-05-03 fixture. If the site
    changes its HTML structure, this parser will need updating — that's exactly the
    drift our live-validation scoring check (Task 11) is designed to catch.
    """
    tree = HTMLParser(html)

    players = _parse_players(tree)
    cumulative = _parse_cumulative_grosses(tree)
    site_points = _parse_site_reported_points(tree)
    return SiteSnapshot(
        captured_at=captured_at,
        players=players,
        cumulative_grosses=cumulative,
        site_reported_points=site_points,
    )


def _parse_players(tree: HTMLParser) -> dict[str, PlayerPicks]:
    """Find every `id=a_<username>` anchor and pull 10 ranked + 3 dark horses from its section."""
    players: dict[str, PlayerPicks] = {}
    for anchor in tree.css("[id^='a_']"):
        username = anchor.attributes.get("id", "")[2:]
        if not username:
            continue
        section = _section_for_anchor(anchor)
        if section is None:
            continue
        ranked, dark_horses = _extract_picks_from_section(section)
        if len(ranked) != 10 or len(dark_horses) != 3:
            # Not a player section; skip
            continue
        players[username] = PlayerPicks(
            username=username,
            ranked=ranked,
            dark_horses=dark_horses,
        )
    return players


def _section_for_anchor(anchor: Node) -> Node | None:
    """The picks live in a sibling/parent container after the anchor. Walk up until
    we find a container that has both 'Ranked' (or numbered list) and 'Dark horse' text.
    """
    node = anchor.parent
    for _ in range(6):  # walk up at most 6 levels
        if node is None:
            return None
        text = (node.text() or "").lower()
        if "dark horse" in text:
            return node
        node = node.parent
    return None


_RANK_PREFIX = re.compile(r"^\s*(\d{1,2})[.)]\s*(.+?)\s*$")


def _extract_picks_from_section(section: Node) -> tuple[list[str], list[str]]:
    """Within a player section, distinguish ranked picks (numbered) from dark horses.

    Strategy: walk all text-bearing leaf elements. Lines starting with `1.` through `10.`
    (in order) are ranked picks. Lines after a "Dark Horse" header are dark horses.
    """
    text_blob = section.text(separator="\n")
    lines = [line.strip() for line in text_blob.splitlines() if line.strip()]

    ranked: list[str] = []
    dark_horses: list[str] = []
    in_dark_horse_section = False

    for line in lines:
        lower = line.lower()
        if "dark horse" in lower:
            in_dark_horse_section = True
            continue
        if not in_dark_horse_section:
            match = _RANK_PREFIX.match(line)
            if match:
                rank = int(match.group(1))
                title = match.group(2)
                if 1 <= rank <= 10 and len(ranked) == rank - 1:
                    ranked.append(_clean_title(title))
        else:
            # In dark horse section. Skip lines that look like rank prefixes (carry-over).
            if _RANK_PREFIX.match(line):
                continue
            # Pick the first 3 plausible movie-title lines
            if 3 <= len(line) <= 120 and not line.endswith(":") and len(dark_horses) < 3:
                dark_horses.append(_clean_title(line))

    return ranked, dark_horses


def _clean_title(raw: str) -> str:
    """Trim trailing box-office annotations like '— $32.5M' or '(2026)' if present."""
    title = re.split(r"\s+[—–-]\s*\$", raw, maxsplit=1)[0]
    title = re.sub(r"\s*\(\s*\d{4}\s*\)\s*$", "", title)
    return title.strip()


_GROSS_LINE = re.compile(r"^(?P<title>.+?)\s+\$?(?P<amount>[\d,.]+)\s*M?\s*$", re.IGNORECASE)


def _parse_cumulative_grosses(tree: HTMLParser) -> dict[str, float]:
    """Find per-movie cumulative dollar amounts. Strategy: scan the page for rows that
    contain a movie title followed by a $-formatted figure.
    """
    grosses: dict[str, float] = {}
    for row in tree.css("tr, li, p"):
        text = (row.text() or "").strip()
        if "$" not in text:
            continue
        for match in re.finditer(
            r"(?P<title>[A-Z][\w':!&., \-]+?)\s+\$(?P<amount>[\d,]+(?:\.\d+)?)(?P<scale>\s*M)?",
            text,
        ):
            title = _clean_title(match.group("title"))
            amount = float(match.group("amount").replace(",", ""))
            if match.group("scale"):
                amount *= 1_000_000
            elif amount < 1000:  # bare dollars unlikely; assume millions
                amount *= 1_000_000
            # Keep the largest match per title (cumulative tends to be the biggest figure shown)
            if amount > grosses.get(title, 0.0):
                grosses[title] = amount
    return grosses


_PLAYER_SCORE_LINE = re.compile(
    r"(?P<name>bclarke|vivrad|zmeister|brettfern|carleigh|radhadr|emsullivan|mhartje)"
    r"\D+(?P<score>\d{1,3})",
    re.IGNORECASE,
)


def _parse_site_reported_points(tree: HTMLParser) -> dict[str, int]:
    """Find the 'Total Score' table and pull each player's integer score."""
    text = tree.body.text(separator="\n") if tree.body else ""
    matches = _PLAYER_SCORE_LINE.finditer(text)
    found: dict[str, int] = {}
    for match in matches:
        name = match.group("name").lower()
        score = int(match.group("score"))
        if name not in found:
            found[name] = score
    return found
```

- [ ] **Step 6: Run tests, debug, iterate**

Run: `uv run pytest tests/test_scraper.py -v`

If any tests fail, the parser needs adjustment. Iterate by:
1. Read the failing assertion to see what was returned vs. expected.
2. Look at the fixture HTML around the relevant area.
3. Adjust selectors / regex in `scraper.py`.
4. Re-run tests.

Expected (after iteration): 5 passed.

- [ ] **Step 7: Commit**

```bash
git add summer_movie_wager/ingest/__init__.py summer_movie_wager/ingest/scraper.py tests/test_scraper.py
git commit -m "feat(ingest): scrape play-along URL into typed snapshot"
```

---

## Task 9: Picks Drift Guard

**Goal:** Compare freshly-scraped picks against `data/picks_snapshot_2026.yaml`. On the first run (file missing), persist the snapshot and continue. On subsequent runs, fail loudly on any divergence.

**Files:**
- Create: `summer_movie_wager/ingest/picks_guard.py`
- Create: `tests/test_picks_guard.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_picks_guard.py`:
```python
from pathlib import Path

import pytest
import yaml

from summer_movie_wager.ingest.picks_guard import (
    PicksDriftError,
    bootstrap_or_validate,
)
from summer_movie_wager.types import PlayerPicks


def _picks(username: str, ranked: list[str], dark_horses: list[str]) -> PlayerPicks:
    return PlayerPicks(username=username, ranked=ranked, dark_horses=dark_horses)


def test_bootstrap_writes_snapshot_when_missing(tmp_path: Path):
    snapshot_path = tmp_path / "picks_snapshot_2026.yaml"
    scraped = {
        "bclarke": _picks("bclarke", [f"M{i}" for i in range(1, 11)], ["DH1", "DH2", "DH3"])
    }
    bootstrap_or_validate(scraped, snapshot_path)
    assert snapshot_path.exists()
    written = yaml.safe_load(snapshot_path.read_text())
    assert "bclarke" in written
    assert written["bclarke"]["ranked"][0] == "M1"


def test_validate_passes_on_match(tmp_path: Path):
    snapshot_path = tmp_path / "picks_snapshot_2026.yaml"
    scraped = {
        "bclarke": _picks("bclarke", [f"M{i}" for i in range(1, 11)], ["DH1", "DH2", "DH3"])
    }
    bootstrap_or_validate(scraped, snapshot_path)
    # Second call with identical input must not raise
    bootstrap_or_validate(scraped, snapshot_path)


def test_validate_raises_on_drift(tmp_path: Path):
    snapshot_path = tmp_path / "picks_snapshot_2026.yaml"
    original = {
        "bclarke": _picks("bclarke", [f"M{i}" for i in range(1, 11)], ["DH1", "DH2", "DH3"])
    }
    bootstrap_or_validate(original, snapshot_path)

    # Now scraper returns different picks → must raise
    drifted = {
        "bclarke": _picks(
            "bclarke",
            ["DIFFERENT"] + [f"M{i}" for i in range(2, 11)],
            ["DH1", "DH2", "DH3"],
        )
    }
    with pytest.raises(PicksDriftError):
        bootstrap_or_validate(drifted, snapshot_path)


def test_validate_raises_on_missing_player(tmp_path: Path):
    snapshot_path = tmp_path / "picks_snapshot_2026.yaml"
    original = {
        "bclarke": _picks("bclarke", [f"M{i}" for i in range(1, 11)], ["DH1", "DH2", "DH3"]),
        "vivrad": _picks("vivrad", [f"V{i}" for i in range(1, 11)], ["VD1", "VD2", "VD3"]),
    }
    bootstrap_or_validate(original, snapshot_path)

    # Scraper returns only one of two players → must raise
    drifted = {"bclarke": original["bclarke"]}
    with pytest.raises(PicksDriftError):
        bootstrap_or_validate(drifted, snapshot_path)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_picks_guard.py -v`
Expected: ImportError on `summer_movie_wager.ingest.picks_guard`.

- [ ] **Step 3: Implement the guard**

Create `summer_movie_wager/ingest/picks_guard.py`:
```python
"""Detect drift between scraped picks and the season's locked-in snapshot."""

from pathlib import Path

import yaml

from summer_movie_wager.types import PlayerPicks


class PicksDriftError(RuntimeError):
    """Raised when scraped picks no longer match the persisted snapshot."""


def bootstrap_or_validate(
    scraped: dict[str, PlayerPicks],
    snapshot_path: Path,
) -> None:
    """If snapshot file exists, validate scraped picks match it. Otherwise persist scraped as new snapshot."""
    if not snapshot_path.exists():
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        _write(scraped, snapshot_path)
        return

    persisted = _read(snapshot_path)
    diffs: list[str] = []

    persisted_users = set(persisted.keys())
    scraped_users = set(scraped.keys())
    missing = persisted_users - scraped_users
    extra = scraped_users - persisted_users
    if missing:
        diffs.append(f"snapshot has players not in scrape: {sorted(missing)}")
    if extra:
        diffs.append(f"scrape has players not in snapshot: {sorted(extra)}")

    for user in persisted_users & scraped_users:
        if persisted[user].ranked != scraped[user].ranked:
            diffs.append(f"{user}: ranked picks changed")
        if persisted[user].dark_horses != scraped[user].dark_horses:
            diffs.append(f"{user}: dark horses changed")

    if diffs:
        raise PicksDriftError(
            "Picks drift detected vs. picks_snapshot_2026.yaml:\n  - "
            + "\n  - ".join(diffs)
            + "\n\nIf the change is intentional, delete the snapshot file and re-run to "
            "rebootstrap. Otherwise, investigate the scraper or the source page."
        )


def _read(path: Path) -> dict[str, PlayerPicks]:
    raw = yaml.safe_load(path.read_text()) or {}
    return {
        username: PlayerPicks(
            username=username,
            ranked=entry["ranked"],
            dark_horses=entry["dark_horses"],
        )
        for username, entry in raw.items()
    }


def _write(picks: dict[str, PlayerPicks], path: Path) -> None:
    out = {
        username: {"ranked": p.ranked, "dark_horses": p.dark_horses}
        for username, p in picks.items()
    }
    path.write_text(yaml.safe_dump(out, sort_keys=True, allow_unicode=True))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_picks_guard.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add summer_movie_wager/ingest/picks_guard.py tests/test_picks_guard.py
git commit -m "feat(ingest): add picks drift guard with first-run bootstrap"
```

---

## Task 10: Renderer (Jinja Template + data.json)

**Goal:** A render function that takes per-player simulation results, per-movie projections, and the current snapshot, and writes `docs/index.html` and `docs/data.json`. Tested via snapshot diff against a fixture.

**Files:**
- Create: `summer_movie_wager/render/__init__.py`
- Create: `summer_movie_wager/render/templates/index.html.j2`
- Create: `summer_movie_wager/render/static/style.css`
- Create: `summer_movie_wager/render/page.py` (template loader and render function — `build.py` will glue the pipeline in Task 12)
- Create: `tests/test_render_snapshot.py`
- Create: `tests/fixtures/expected_index.html` (will be generated, then committed)

- [ ] **Step 1: Create render package and template directory**

Run: `mkdir -p summer_movie_wager/render/templates summer_movie_wager/render/static`

Create `summer_movie_wager/render/__init__.py`:
```python
"""Static site rendering."""
```

- [ ] **Step 2: Create the Jinja template**

Create `summer_movie_wager/render/templates/index.html.j2`:

{% raw %}
```jinja
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Summer Movie Wager 2026</title>
<style>{{ inline_css }}</style>
</head>
<body>
<header>
  <h1>Summer Movie Wager 2026</h1>
  <p class="meta">Window 2026-04-30 → 2026-09-07 · refreshed {{ generated_at }}</p>
</header>

<section class="leaderboard">
  <h2>Leaderboard</h2>
  <table>
    <thead>
      <tr><th>Player</th><th>Current</th><th>Projected median</th><th>80% range</th><th>Win odds</th></tr>
    </thead>
    <tbody>
    {% for row in leaderboard %}
      <tr data-player="{{ row.username }}" class="player-row">
        <td>{{ row.username }}</td>
        <td>{{ row.current_pts }}</td>
        <td>{{ row.median_pts | int }}</td>
        <td>[{{ row.p10_pts | int }} – {{ row.p90_pts | int }}]</td>
        <td title="tie odds: {{ '%.0f'|format(row.tie_prob*100) }}%">{{ '%.0f'|format(row.win_prob*100) }}%</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
</section>

<section class="movies">
  <h2>Movies (projected window gross)</h2>
  <table>
    <thead>
      <tr><th>Movie</th><th>Released</th><th>Status</th><th>Projected median</th><th>80% range</th><th>Cumulative</th><th>Source</th></tr>
    </thead>
    <tbody>
    {% for movie in movies %}
      <tr>
        <td>{{ movie.title }}</td>
        <td>{{ movie.release_date }}</td>
        <td><span class="badge badge-{{ movie.status }}">{{ movie.status_label }}</span></td>
        <td>${{ '{:,.0f}'.format(movie.median_in_window_gross) }}</td>
        <td>[${{ '{:,.0f}'.format(movie.p10) }} – ${{ '{:,.0f}'.format(movie.p90) }}]</td>
        <td>{% if movie.cumulative_to_date %}${{ '{:,.0f}'.format(movie.cumulative_to_date) }}{% else %}—{% endif %}</td>
        <td class="source">{{ movie.source }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
</section>

<section class="players">
  <h2>Per-player detail</h2>
  {% for player in player_details %}
  <details data-player="{{ player.username }}">
    <summary>{{ player.username }} — projected {{ player.median_pts | int }}, current {{ player.current_pts }}</summary>
    <ol class="ranked-picks">
    {% for pick in player.ranked %}
      <li>
        <strong>{{ pick.title }}</strong>
        <span class="muted">→ projected #{{ pick.projected_rank or '—' }} ·
          ${{ '{:,.0f}'.format(pick.projected_gross) }} ·
          contributes {{ pick.projected_pts }} pts
        </span>
      </li>
    {% endfor %}
    </ol>
    <p class="dark-horse-label">Dark horses</p>
    <ul class="dark-horses">
    {% for dh in player.dark_horses %}
      <li>{{ dh.title }} <span class="muted">→ projected #{{ dh.projected_rank or '—' }} · {{ dh.projected_pts }} pt</span></li>
    {% endfor %}
    </ul>
  </details>
  {% endfor %}
</section>

<footer>
  <p>Source data: <a href="https://thesummermoviewager.com/help.php">Summer Movie Wager rules</a>. Raw snapshot: <a href="data.json">data.json</a>.</p>
</footer>
</body>
</html>
```
{% endraw %}

- [ ] **Step 3: Create the stylesheet**

Create `summer_movie_wager/render/static/style.css`:
```css
:root { color-scheme: light dark; }
body { font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; max-width: 980px; margin: 1.5em auto; padding: 0 1em; }
h1 { font-size: 1.5em; margin-bottom: 0.2em; }
h2 { font-size: 1.1em; margin-top: 1.6em; border-bottom: 1px solid #888; padding-bottom: 0.2em; }
.meta { color: #888; font-size: 0.9em; }
table { width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 0.35em 0.6em; border-bottom: 1px solid #4443; }
th { font-weight: 600; }
td:first-child { font-weight: 500; }
.badge { font-size: 0.75em; padding: 0.1em 0.5em; border-radius: 3px; background: #8884; }
.badge-pre_release { background: #88f4; }
.badge-in_theaters { background: #4a4; color: white; }
.badge-closed, .badge-wont_score, .badge-no_projection { background: #8884; }
.muted { color: #888; font-size: 0.9em; }
details { margin: 0.6em 0; }
summary { cursor: pointer; padding: 0.3em 0; }
.dark-horse-label { font-weight: 600; margin-top: 0.6em; margin-bottom: 0.2em; }
.source { font-size: 0.85em; color: #888; }
footer { margin-top: 3em; padding-top: 1em; border-top: 1px solid #4443; color: #888; font-size: 0.85em; }
@media (max-width: 600px) {
  body { font-size: 13px; }
  th, td { padding: 0.25em 0.4em; }
}
```

- [ ] **Step 4: Implement the page renderer**

Create `summer_movie_wager/render/page.py`:
```python
"""Render the static site from pipeline outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

_TEMPLATES = Path(__file__).parent / "templates"
_STATIC = Path(__file__).parent / "static"


@dataclass(frozen=True)
class LeaderboardRow:
    username: str
    current_pts: int
    median_pts: float
    p10_pts: float
    p90_pts: float
    win_prob: float
    tie_prob: float


@dataclass(frozen=True)
class MovieRow:
    title: str
    release_date: str
    status: str  # machine value (pre_release, in_theaters, won't_score, no_projection)
    status_label: str  # human label
    median_in_window_gross: float
    p10: float
    p90: float
    cumulative_to_date: float | None
    source: str


@dataclass(frozen=True)
class PickDetail:
    title: str
    projected_rank: int | None
    projected_gross: float
    projected_pts: int


@dataclass(frozen=True)
class PlayerDetail:
    username: str
    median_pts: float
    current_pts: int
    ranked: list[PickDetail]
    dark_horses: list[PickDetail]


@dataclass(frozen=True)
class RenderInput:
    generated_at: datetime
    leaderboard: list[LeaderboardRow]
    movies: list[MovieRow]
    player_details: list[PlayerDetail]
    raw_snapshot: dict[str, Any] = field(default_factory=dict)


def render(out_dir: Path, data: RenderInput) -> None:
    """Render index.html and data.json into out_dir."""
    out_dir.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("index.html.j2")
    inline_css = (_STATIC / "style.css").read_text()
    html = template.render(
        generated_at=data.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        leaderboard=data.leaderboard,
        movies=data.movies,
        player_details=data.player_details,
        inline_css=inline_css,
    )
    (out_dir / "index.html").write_text(html)
    (out_dir / "data.json").write_text(json.dumps(data.raw_snapshot, indent=2, default=str))
```

- [ ] **Step 5: Write the snapshot test**

Create `tests/test_render_snapshot.py`:
```python
from datetime import datetime
from pathlib import Path

import pytest

from summer_movie_wager.render.page import (
    LeaderboardRow,
    MovieRow,
    PickDetail,
    PlayerDetail,
    RenderInput,
    render,
)

EXPECTED = Path(__file__).parent / "fixtures" / "expected_index.html"


def _fixture_input() -> RenderInput:
    return RenderInput(
        generated_at=datetime(2026, 5, 3, 14, 22, 0),
        leaderboard=[
            LeaderboardRow(
                username="vivrad", current_pts=3, median_pts=91.0,
                p10_pts=62.0, p90_pts=134.0, win_prob=0.28, tie_prob=0.04,
            ),
            LeaderboardRow(
                username="bclarke", current_pts=3, median_pts=85.0,
                p10_pts=58.0, p90_pts=128.0, win_prob=0.19, tie_prob=0.05,
            ),
        ],
        movies=[
            MovieRow(
                title="Spider-Man: Brand New Day", release_date="2026-07-31",
                status="pre_release", status_label="pre-release",
                median_in_window_gross=380_000_000, p10=290_000_000, p90=470_000_000,
                cumulative_to_date=None, source="Box Office Pro · high",
            ),
            MovieRow(
                title="The Devil Wears Prada 2", release_date="2026-05-01",
                status="in_theaters", status_label="in theaters",
                median_in_window_gross=170_000_000, p10=140_000_000, p90=210_000_000,
                cumulative_to_date=32_500_000, source="decay model · 1 wk",
            ),
        ],
        player_details=[
            PlayerDetail(
                username="bclarke", median_pts=85.0, current_pts=3,
                ranked=[
                    PickDetail(title="Toy Story 5", projected_rank=2, projected_gross=290_000_000, projected_pts=10),
                ],
                dark_horses=[
                    PickDetail(title="Backrooms", projected_rank=None, projected_gross=0, projected_pts=0),
                ],
            )
        ],
        raw_snapshot={"placeholder": True},
    )


def test_render_matches_expected_snapshot(tmp_path: Path):
    render(tmp_path, _fixture_input())
    actual = (tmp_path / "index.html").read_text()
    if not EXPECTED.exists():
        EXPECTED.write_text(actual)
        pytest.fail(
            "expected_index.html did not exist — wrote it now from this run. "
            "Inspect it visually, then re-run the test to lock the snapshot."
        )
    expected = EXPECTED.read_text()
    assert actual == expected, (
        "Render output drifted from snapshot. If intentional, delete "
        "tests/fixtures/expected_index.html and re-run to regenerate."
    )


def test_render_writes_data_json(tmp_path: Path):
    render(tmp_path, _fixture_input())
    assert (tmp_path / "data.json").exists()
```

- [ ] **Step 6: Run tests — first pass writes the snapshot**

Run: `uv run pytest tests/test_render_snapshot.py -v`
Expected: First test FAILS with "wrote it now from this run". The fixture file is now created.

- [ ] **Step 7: Sanity-check the snapshot**

Open `tests/fixtures/expected_index.html` in a browser. Confirm:
- Leaderboard renders with the two test rows
- Movies table renders with the two test movies
- Per-player details collapsible card is present and expandable
- No raw {% raw %}`{{ ... }}`{% endraw %} template placeholders are visible

- [ ] **Step 8: Re-run tests to verify the snapshot locks**

Run: `uv run pytest tests/test_render_snapshot.py -v`
Expected: 2 passed.

- [ ] **Step 9: Commit**

```bash
git add summer_movie_wager/render/__init__.py summer_movie_wager/render/page.py summer_movie_wager/render/templates summer_movie_wager/render/static tests/test_render_snapshot.py tests/fixtures/expected_index.html
git commit -m "feat(render): add Jinja-based static page renderer with snapshot test"
```

---

## Task 11: Pipeline Glue (build.py CLI + Live Validation)

**Goal:** A single `python -m summer_movie_wager.render.build` entrypoint that runs the full pipeline: fetch → drift-guard → normalize → project → simulate → validate-against-site → render. Supports a `--local` flag to skip writing the live capture history.

**Files:**
- Create: `summer_movie_wager/render/build.py`
- Create: `data/preopening_projections.yaml` (initial seed — empty mapping is acceptable; populated in Task 12)
- Create: `data/movies_overrides.yaml` (initial seed — empty mapping is acceptable)

- [ ] **Step 1: Seed empty data files**

Run: `mkdir -p data`

Create `data/preopening_projections.yaml`:
```yaml
# Hand-curated analyst pre-release box office estimates.
# Schema per entry:
#   <movie_title>:
#     release_date: YYYY-MM-DD
#     opening_weekend_estimate: <int dollars>
#     total_domestic_estimate: <int dollars>
#     confidence: high | med | low
#     source: "<analyst source + date>"
#     as_of: YYYY-MM-DD
#     notes: "<freeform>"
# Movies missing from this file get projected_in_window_gross=0 and a "no projection" badge.
```

Create `data/movies_overrides.yaml`:
```yaml
# Per-movie corrections / classifications. Schema per entry:
#   <movie_title>:
#     release_date: YYYY-MM-DD       # override scraper's value
#     category: wide | animated_family   # default 'wide' if unspecified
#     status: pre_release | in_theaters | closed   # override status inference
#     alias_of: <canonical_title>    # if scraper returned a variant title
```

- [ ] **Step 2: Implement build.py**

Create `summer_movie_wager/render/build.py`:
```python
"""End-to-end pipeline: ingest → project → simulate → render."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from summer_movie_wager.ingest.picks_guard import bootstrap_or_validate
from summer_movie_wager.ingest.scraper import fetch_snapshot
from summer_movie_wager.model.decay import project_decay
from summer_movie_wager.model.preopening import WINDOW_END, project_preopening
from summer_movie_wager.model.simulate import simulate_season
from summer_movie_wager.render.page import (
    LeaderboardRow,
    MovieRow,
    PickDetail,
    PlayerDetail,
    RenderInput,
    render,
)
from summer_movie_wager.score import score_player
from summer_movie_wager.types import (
    Category,
    Confidence,
    MovieStatus,
    PlayerPicks,
    PreopeningEntry,
    Projection,
    SiteSnapshot,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DOCS_DIR = REPO_ROOT / "docs"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the Summer Movie Wager site")
    parser.add_argument(
        "--local", action="store_true",
        help="Run pipeline locally; do not append to history files.",
    )
    args = parser.parse_args(argv)

    today = date.today()
    print(f"[build] fetching site snapshot ({today})", file=sys.stderr)
    snapshot = fetch_snapshot(captured_at=today)

    print(f"[build] validating picks against snapshot", file=sys.stderr)
    bootstrap_or_validate(snapshot.players, DATA_DIR / "picks_snapshot_2026.yaml")

    overrides = _load_yaml(DATA_DIR / "movies_overrides.yaml")
    preopening_raw = _load_yaml(DATA_DIR / "preopening_projections.yaml")
    preopening = _parse_preopening(preopening_raw)

    movies = _normalize_movies(snapshot, overrides, preopening, today=today)
    projections = _project_all(movies, preopening, snapshot, overrides, today=today)

    sim = simulate_season(
        list(snapshot.players.values()),
        projections,
        n_trials=10_000,
        seed=20260907,
    )

    current_top10 = _current_top_10(snapshot.cumulative_grosses)
    current_pts = {
        username: score_player(picks, current_top10)
        for username, picks in snapshot.players.items()
    }
    _validate_against_site(current_pts, snapshot.site_reported_points)

    leaderboard = _build_leaderboard(snapshot, sim, current_pts)
    movie_rows = _build_movie_rows(movies, projections, snapshot, sim, current_top10)
    player_details = _build_player_details(snapshot, projections, current_pts, sim)

    raw = {
        "captured_at": str(snapshot.captured_at),
        "site_reported_points": snapshot.site_reported_points,
        "computed_current_points": current_pts,
        "win_prob": sim.win_prob,
        "tie_prob": sim.tie_prob,
        "median_final_pts": sim.median_final_pts,
        "p10_final_pts": sim.p10_final_pts,
        "p90_final_pts": sim.p90_final_pts,
        "projections": [p.model_dump() for p in projections],
    }

    render(
        DOCS_DIR,
        RenderInput(
            generated_at=datetime.utcnow(),
            leaderboard=leaderboard,
            movies=movie_rows,
            player_details=player_details,
            raw_snapshot=raw,
        ),
    )

    if not args.local:
        _append_history(snapshot, sim, today=today)

    print(f"[build] wrote {DOCS_DIR}/index.html", file=sys.stderr)
    return 0


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _parse_preopening(raw: dict[str, Any]) -> dict[str, PreopeningEntry]:
    out: dict[str, PreopeningEntry] = {}
    for title, entry in raw.items():
        out[title] = PreopeningEntry(
            release_date=date.fromisoformat(str(entry["release_date"])),
            opening_weekend_estimate=float(entry["opening_weekend_estimate"]),
            total_domestic_estimate=float(entry["total_domestic_estimate"]),
            confidence=Confidence(entry["confidence"]),
            source=str(entry["source"]),
            as_of=date.fromisoformat(str(entry["as_of"])),
            notes=str(entry.get("notes", "")),
        )
    return out


def _normalize_movies(
    snapshot: SiteSnapshot,
    overrides: dict[str, Any],
    preopening: dict[str, PreopeningEntry],
    *,
    today: date,
) -> dict[str, dict[str, Any]]:
    """Build a unified per-movie record. Keyed by canonical title."""
    movies: dict[str, dict[str, Any]] = {}

    # Every picked movie + every preopening entry + every grossed movie is a candidate
    candidates: set[str] = set()
    for picks in snapshot.players.values():
        candidates.update(picks.ranked + picks.dark_horses)
    candidates.update(preopening.keys())
    candidates.update(snapshot.cumulative_grosses.keys())

    for title in candidates:
        ov = overrides.get(title, {})
        canonical = ov.get("alias_of", title)
        category = Category(ov.get("category", "wide"))
        cumulative = snapshot.cumulative_grosses.get(canonical, 0.0)

        if "release_date" in ov:
            release = date.fromisoformat(str(ov["release_date"]))
        elif canonical in preopening:
            release = preopening[canonical].release_date
        elif cumulative > 0:
            release = today  # unknown but already grossing → assume opened today
        else:
            release = WINDOW_END  # unknown release → defer to no_projection

        if "status" in ov:
            status = MovieStatus(ov["status"])
        elif release > today:
            status = MovieStatus.PRE_RELEASE
        elif cumulative > 0:
            status = MovieStatus.IN_THEATERS
        else:
            status = MovieStatus.PRE_RELEASE  # picked but not grossing yet

        movies[canonical] = {
            "title": canonical,
            "release_date": release,
            "status": status,
            "category": category,
            "cumulative": cumulative,
        }
    return movies


def _project_all(
    movies: dict[str, dict[str, Any]],
    preopening: dict[str, PreopeningEntry],
    snapshot: SiteSnapshot,
    overrides: dict[str, Any],
    *,
    today: date,
) -> list[Projection]:
    projections: list[Projection] = []
    history = _load_history()
    for title, m in movies.items():
        if m["status"] == MovieStatus.IN_THEATERS:
            obs = history.get(title, [])
            gross, sigma = project_decay(
                release_date=m["release_date"],
                today=today,
                cumulative_gross_to_date=m["cumulative"],
                category=m["category"],
                observed_history=obs,
            )
        elif m["status"] == MovieStatus.PRE_RELEASE and title in preopening:
            entry = preopening[title]
            gross, sigma = project_preopening(
                release_date=entry.release_date,
                opening_weekend_estimate=entry.opening_weekend_estimate,
                total_domestic_estimate=entry.total_domestic_estimate,
                confidence=entry.confidence,
                category=m["category"],
            )
        else:
            gross, sigma = 0.0, 0.0
        projections.append(
            Projection(movie_title=title, median_in_window_gross=gross, sigma=sigma)
        )
    return projections


def _load_history() -> dict[str, list[tuple[date, float]]]:
    path = DATA_DIR / "box_office_history.jsonl"
    if not path.exists():
        return {}
    history: dict[str, list[tuple[date, float]]] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        history.setdefault(row["movie"], []).append(
            (date.fromisoformat(row["date"]), float(row["cumulative_gross"]))
        )
    return history


def _current_top_10(grosses: dict[str, float]) -> list[str]:
    return [title for title, _ in sorted(grosses.items(), key=lambda kv: kv[1], reverse=True)[:10]]


def _validate_against_site(
    computed: dict[str, int],
    site: dict[str, int],
) -> None:
    diffs = []
    for username, site_score in site.items():
        ours = computed.get(username, 0)
        if ours != site_score:
            diffs.append(f"{username}: site={site_score}, ours={ours}")
    if diffs:
        print(
            "[build] WARNING: scoring engine disagrees with site standings:\n  - "
            + "\n  - ".join(diffs),
            file=sys.stderr,
        )
        # Don't raise — early in season the top 10 is volatile and our reconstruction
        # of "current top 10" from cumulative grosses is approximate. Re-evaluate later
        # in the season once we have full top-10 data from the site.


def _build_leaderboard(snapshot, sim, current_pts):
    rows = []
    for username in snapshot.players:
        rows.append(LeaderboardRow(
            username=username,
            current_pts=current_pts.get(username, 0),
            median_pts=sim.median_final_pts[username],
            p10_pts=sim.p10_final_pts[username],
            p90_pts=sim.p90_final_pts[username],
            win_prob=sim.win_prob[username],
            tie_prob=sim.tie_prob[username],
        ))
    rows.sort(key=lambda r: r.median_pts, reverse=True)
    return rows


_STATUS_LABELS = {
    "pre_release": "pre-release",
    "in_theaters": "in theaters",
    "closed": "closed",
    "wont_score": "won't score",
    "no_projection": "no projection",
}


def _build_movie_rows(movies, projections, snapshot, sim, current_top10):
    proj_by_title = {p.movie_title: p for p in projections}
    rows: list[MovieRow] = []
    for title, m in movies.items():
        proj = proj_by_title.get(title)
        if proj is None or proj.median_in_window_gross == 0:
            if m["status"] == MovieStatus.PRE_RELEASE and m["release_date"] > WINDOW_END:
                status_key = "wont_score"
                src = "release after window"
            elif m["status"] == MovieStatus.PRE_RELEASE:
                status_key = "no_projection"
                src = "no analyst entry"
            else:
                status_key = m["status"].value
                src = "—"
            rows.append(MovieRow(
                title=title, release_date=m["release_date"].isoformat(),
                status=status_key, status_label=_STATUS_LABELS[status_key],
                median_in_window_gross=0, p10=0, p90=0,
                cumulative_to_date=m["cumulative"] or None, source=src,
            ))
            continue
        # Approximate p10/p90 from sigma using lognormal quantiles
        median = proj.median_in_window_gross
        p10 = median * math.exp(-1.2816 * proj.sigma)
        p90 = median * math.exp(1.2816 * proj.sigma)
        status_key = m["status"].value
        src = "decay model" if m["status"] == MovieStatus.IN_THEATERS else "analyst estimate"
        rows.append(MovieRow(
            title=title, release_date=m["release_date"].isoformat(),
            status=status_key, status_label=_STATUS_LABELS[status_key],
            median_in_window_gross=median, p10=p10, p90=p90,
            cumulative_to_date=m["cumulative"] or None, source=src,
        ))
    rows.sort(key=lambda r: r.median_in_window_gross, reverse=True)
    return rows


def _build_player_details(snapshot, projections, current_pts, sim):
    proj_by_title = {p.movie_title: p for p in projections}
    median_top_10 = sorted(
        proj_by_title.values(),
        key=lambda p: p.median_in_window_gross,
        reverse=True,
    )[:10]
    median_top_titles = [p.movie_title for p in median_top_10]
    median_position = {t: i + 1 for i, t in enumerate(median_top_titles)}

    out: list[PlayerDetail] = []
    for username, picks in snapshot.players.items():
        ranked_details = [
            _pick_detail(title, idx + 1, proj_by_title, median_position, kind="ranked")
            for idx, title in enumerate(picks.ranked)
        ]
        dh_details = [
            _pick_detail(title, None, proj_by_title, median_position, kind="dark_horse")
            for title in picks.dark_horses
        ]
        out.append(PlayerDetail(
            username=username,
            median_pts=sim.median_final_pts[username],
            current_pts=current_pts.get(username, 0),
            ranked=ranked_details,
            dark_horses=dh_details,
        ))
    out.sort(key=lambda p: p.median_pts, reverse=True)
    return out


def _pick_detail(title, predicted_rank, proj_by_title, median_position, *, kind):
    proj = proj_by_title.get(title)
    median_gross = proj.median_in_window_gross if proj else 0.0
    actual_rank = median_position.get(title, 0)
    if kind == "ranked" and actual_rank > 0 and predicted_rank is not None:
        from summer_movie_wager.score.rules import _ranked_pick_points
        pts = _ranked_pick_points(predicted_rank, actual_rank)
    elif kind == "dark_horse" and actual_rank > 0:
        pts = 1
    else:
        pts = 0
    return PickDetail(
        title=title,
        projected_rank=actual_rank or None,
        projected_gross=median_gross,
        projected_pts=pts,
    )


def _append_history(snapshot: SiteSnapshot, sim, *, today: date) -> None:
    box_path = DATA_DIR / "box_office_history.jsonl"
    forecast_path = DATA_DIR / "forecast_history.jsonl"
    with box_path.open("a") as f:
        for movie, gross in snapshot.cumulative_grosses.items():
            f.write(json.dumps({
                "movie": movie,
                "date": today.isoformat(),
                "cumulative_gross": gross,
            }) + "\n")
    with forecast_path.open("a") as f:
        for username in snapshot.players:
            f.write(json.dumps({
                "date": today.isoformat(),
                "player": username,
                "win_prob": sim.win_prob[username],
                "median_final_pts": sim.median_final_pts[username],
                "p10": sim.p10_final_pts[username],
                "p90": sim.p90_final_pts[username],
            }) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Smoke-test the build script locally**

Run: `uv run python -m summer_movie_wager.render.build --local`

Expected: prints status messages to stderr (`fetching site snapshot...`, `validating picks...`, `wrote .../docs/index.html`); creates `docs/index.html` and `docs/data.json`. May print a "WARNING: scoring engine disagrees with site standings" line — that's expected this early in the season because we can't reconstruct the full top-10 from partial cumulative data; it's a soft warning, not a failure.

If the script errors on missing data, fix the immediate issue and re-run.

- [ ] **Step 4: Verify the output renders**

Run: `open docs/index.html` (macOS) or open in your browser.

Confirm visually:
- Leaderboard shows all 8 players
- Movies table is populated
- Per-player detail cards expand on click
- No Jinja {% raw %}`{{ ... }}`{% endraw %} placeholder leakage
- The "current pts" column matches the site (3 for everyone except RadhaDR who has 8, as of 2026-05-03)

- [ ] **Step 5: Commit**

```bash
git add data/preopening_projections.yaml data/movies_overrides.yaml summer_movie_wager/render/build.py
git commit -m "feat(render): wire up end-to-end build pipeline with CLI entrypoint"
```

---

## Task 12: Seed `preopening_projections.yaml` (Research Pass)

**Goal:** Populate analyst-driven projections for every unreleased movie that any of the 8 lists picked. After this task, `--local` build runs produce realistic projected medians.

**Files:**
- Modify: `data/preopening_projections.yaml`

**Distinct unreleased movies appearing in any pick list (compiled from the 2026-05-03 snapshot):**
Spider-Man: Brand New Day, Toy Story 5, Moana (live action), Supergirl, Star Wars: The Mandalorian and Grogu, Animal Farm, The Breadwinner, PAW Patrol: The Dino Movie, Tom and Jerry: Forbidden Compass, Passenger, Minions & Monsters, The Odyssey, Disclosure Day, Mortal Kombat II, Backrooms, Scary Movie, Evil Dead Burn, Coyote vs. Acme, Masters of the Universe, The End of Oak Street, Young Washington, Power Ballad, I Love Boosters, The Sheep Detectives, Finding Emily, Insidious: Out of the Further, Billie Eilish: Hit Me Hard and Soft - The Tour Live in 3D.

(Movies already in theaters as of 2026-05-03: The Devil Wears Prada 2, Animal Farm, Hokum — these go through Mode A automatically.)

- [ ] **Step 1: Research current analyst tracking for each unreleased title**

For each title above, search Box Office Pro long-range tracking, Variety / Deadline tracking pieces, and BoxOffice.com for:
- Current consensus opening weekend estimate (USD)
- Current consensus total domestic estimate (USD)
- Article publication date
- A confidence read (high = blockbuster with multiple corroborating analyst reports; med = single source or wide range across analysts; low = indie / limited / unknown)

Suggested approach: ask the user to share the most recent Box Office Pro long-range tracking link, and use it to populate as many titles as possible in one pass. For titles with no published forecast, leave them out — they'll get the "no projection" badge automatically (per the design's explicit fallback rule).

- [ ] **Step 2: Populate the YAML**

Edit `data/preopening_projections.yaml`. Append entries in the schema documented at the top of the file. Example for a single title:
```yaml
"Spider-Man: Brand New Day":
  release_date: 2026-07-31
  opening_weekend_estimate: 145000000
  total_domestic_estimate: 410000000
  confidence: high
  source: "Box Office Pro long-range tracking, 2026-04-15"
  as_of: 2026-04-15
  notes: ""
```

Important: titles must match exactly what the scraper returns. Run `uv run python -c "from summer_movie_wager.ingest.scraper import parse_snapshot; from pathlib import Path; from datetime import date; s = parse_snapshot(Path('tests/fixtures/playalong.html').read_text(), captured_at=date(2026,5,3)); print(sorted({p for picks in s.players.values() for p in picks.ranked + picks.dark_horses}))"` to dump the canonical title set.

- [ ] **Step 3: Re-run the build with new projections**

Run: `uv run python -m summer_movie_wager.render.build --local`
Expected: pipeline completes; many movies in the projection table now have non-zero medians.

Open `docs/index.html` and sanity-check that the leaderboard ordering reflects the new projections.

- [ ] **Step 4: Commit**

```bash
git add data/preopening_projections.yaml
git commit -m "data(preopening): seed analyst pre-release projections"
```

---

## Task 13: GitHub Action

**Goal:** Manually-triggered workflow that re-runs the pipeline and publishes the result via GitHub Pages.

**Files:**
- Create: `.github/workflows/refresh.yml`

- [ ] **Step 1: Create the workflow**

Run: `mkdir -p .github/workflows`

Create `.github/workflows/refresh.yml`:
```yaml
name: Refresh site
on:
  workflow_dispatch:

permissions:
  contents: write

jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: latest

      - name: Set up Python
        run: uv python install 3.12

      - name: Sync dependencies
        run: uv sync --frozen

      - name: Run tests
        run: uv run pytest

      - name: Build site
        run: uv run python -m summer_movie_wager.render.build

      - name: Commit refreshed docs and history
        run: |
          if [[ -n $(git status --porcelain docs data) ]]; then
            git config user.name "github-actions[bot]"
            git config user.email "github-actions[bot]@users.noreply.github.com"
            git add docs data
            git commit -m "chore: refresh site for $(date -u +%Y-%m-%dT%H:%MZ)"
            git push
          else
            echo "No changes to commit."
          fi
```

- [ ] **Step 2: Verify workflow YAML parses**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/refresh.yml'))"`
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/refresh.yml
git commit -m "ci: add manually-triggered refresh workflow"
```

- [ ] **Step 4: Push and enable GitHub Pages**

Push to GitHub:
```bash
git push origin main
```

Then in the GitHub UI: **Settings → Pages → Source → Deploy from branch → `main` / `docs` → Save**. Wait ~1 minute, then confirm the site is reachable at `https://<your-github-username>.github.io/summer-movie-wager/` (or whatever the configured URL is).

- [ ] **Step 5: Trigger the first scheduled refresh**

In the GitHub UI: **Actions → Refresh site → Run workflow → main → Run workflow**.

Expected:
- Workflow completes green within ~2 minutes
- A new commit appears on `main` from `github-actions[bot]` with "chore: refresh site for ..."
- The Pages site reflects the latest data

If the workflow fails, read the failed step's log, fix the underlying issue locally, push, and re-trigger.

---

## Task 14: End-to-End Verification

**Goal:** Confirm every spec verification step passes before declaring the project complete.

- [ ] **Step 1: All tests pass**

Run: `uv run pytest -v`
Expected: every test green; total count ≥ 35 (7 types + 11 scoring + 7 preopening + 7 decay + 5 simulate + 5 scraper + 4 picks_guard + 2 render).

- [ ] **Step 2: Local build succeeds**

Run: `uv run python -m summer_movie_wager.render.build --local`
Expected: exits 0; `docs/index.html` and `docs/data.json` are regenerated.

- [ ] **Step 3: Visual inspection of headline metrics**

Open `docs/index.html`. Confirm:
- "Current points" column matches site exactly (use the live URL to cross-check).
- Projected median ordering matches intuition: Spider-Man: Brand New Day, Toy Story 5, Moana, The Odyssey should appear among the top projected grossers.
- Win odds across all 8 players sum to ~100% (with `tie_prob` accounting for the residual).

- [ ] **Step 4: GitHub Pages is live**

Open the GitHub Pages URL in a browser. Confirm the page loads, and matches the local `docs/index.html`.

- [ ] **Step 5: Sensitivity check**

Add a fake entry to `data/preopening_projections.yaml`:
```yaml
"FAKE BLOCKBUSTER":
  release_date: 2026-05-15
  opening_weekend_estimate: 200000000
  total_domestic_estimate: 800000000
  confidence: high
  source: "synthetic test"
  as_of: 2026-05-03
  notes: "do not commit"
```

Run: `uv run python -m summer_movie_wager.render.build --local`
Expected: the fake movie appears at or near the top of the projection table; leaderboard win odds shift (FAKE BLOCKBUSTER is no one's pick, so adding it should hurt everyone's odds roughly equally).

Revert: remove the fake entry from the YAML before committing.

- [ ] **Step 6: Final commit & push**

```bash
git status     # confirm only docs/ and data/ history files are dirty
git add docs data
git commit -m "build: refreshed docs after end-to-end verification"
git push origin main
```

---

## Self-Review Notes

The following spec requirements are addressed by the above tasks:

| Spec section | Implementing task(s) |
| --- | --- |
| Wager scoring rules (canonical) | Task 3 |
| Architecture stage 1 — Ingest (scrape) | Task 7 (fixture), Task 8 (scraper) |
| Architecture stage 1 — Picks-drift guard | Task 9 |
| Architecture stage 2 — Normalize (Pydantic models, overrides) | Task 2 (types), Task 11 step 1 (overrides file), Task 11 (`_normalize_movies`) |
| Architecture stage 3 — Mode A (decay) | Task 5 |
| Architecture stage 3 — Mode B (preopening) | Task 4 |
| Architecture stage 3 — Fallback (zero, badge) | Task 11 (`_project_all` + `_build_movie_rows`) |
| Architecture stage 4 — Score & simulate | Task 6 (sim), Task 11 (`_validate_against_site`) |
| Architecture stage 5 — Render | Task 10 (page), Task 11 (glue) |
| Output 3a — Leaderboard | Task 10 template + Task 11 `_build_leaderboard` |
| Output 3b — Movie table | Task 10 template + Task 11 `_build_movie_rows` |
| Output 3c — Per-player detail | Task 10 template + Task 11 `_build_player_details` |
| Repo layout | Tasks 1, 2, 3, 4, 5, 6, 8, 9, 10, 11 |
| Stack (Python 3.12, uv, deps) | Task 1 |
| Tests — scoring | Task 3 |
| Tests — decay | Task 5 |
| Tests — preopening | Task 4 |
| Tests — render snapshot | Task 10 |
| Live validation hook | Task 11 (`_validate_against_site`) |
| Scraper offline fixture | Task 7, Task 8 |
| Operations — workflow_dispatch only | Task 13 |
| Verification — end-to-end | Task 14 |

**Known soft spots to watch during implementation:**

1. **Scraper selectors (Task 8) are derived from a single 2026-05-03 fixture.** The HTML is lightly-styled PHP output, not a CMS — likely stable, but the implementation hooks for `_extract_picks_from_section` and `_parse_cumulative_grosses` may need adjustment after inspecting the actual fixture.
2. **Live-validation strictness (Task 11 `_validate_against_site`) is set to "warn, don't fail" intentionally** because at 2026-05-03 only ~3 movies have meaningful gross — our reconstructed top 10 will be incomplete. Tighten to a hard `raise` once the season has at least 10 movies with cumulative gross > 0 (around mid-June).
3. **`_pick_detail` imports `_ranked_pick_points` directly from `score.rules`.** It's prefixed with `_` because nothing outside the scoring module needed it before. Acceptable for now; if reused more, promote to a public function.
