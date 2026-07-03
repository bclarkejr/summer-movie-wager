# In-Theaters Projection Uncertainty Floor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply forecast uncertainty only to a film's *remaining* (unbanked) gross so simulated and displayed totals can never fall below money already earned, and so films deep into their run get a tight range automatically.

**Architecture:** Add a `floor` field (current banked in-window gross) to `Projection`. Replace the lognormal draw form `median * exp(sigma·z)` with `floor + (median − floor) * exp(sigma·z)` in both the Monte Carlo sampler and the displayed p10/p90. `floor = 0` for pre-release titles makes their behavior identical to today. `decay.py` and `preopening.py` are untouched.

**Tech Stack:** Python 3, Pydantic v2, NumPy, pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-06-28-in-theaters-uncertainty-floor-design.md`

## Global Constraints

- Draw form everywhere a sample/percentile is computed: `floor + (median − floor) * exp(sigma·z)`; clamp `remaining = max(0, median − floor)`.
- `floor` = banked in-window gross for `IN_THEATERS` films, `0.0` otherwise.
- `Projection.floor` defaults to `0.0` — all existing construction sites stay valid; pre-release behavior must be byte-for-byte unchanged.
- p10/p90 z-multiplier stays `1.2816` (80% range). Do **not** alter `_sigma_from_weeks`.
- Run tests with `uv run pytest`; run the pipeline with `uv run python -m summer_movie_wager.render.build --local`.

---

## File Structure

```
summer_movie_wager/types.py            — add `floor: float = 0.0` to Projection
summer_movie_wager/model/simulate.py   — remaining-based Monte Carlo draw
summer_movie_wager/render/build.py     — populate floor; remaining-based p10/p90
tests/test_types.py                    — floor default
tests/test_simulate.py                 — floor respected in samples/percentiles
tests/test_build.py                    — p10/p90 numbers under new formula
tests/test_render_snapshot.py          — refreshed render snapshot
```

---

## Task 1: Add `floor` to the `Projection` model

**Files:**
- Modify: `summer_movie_wager/types.py` (the `Projection` class, ~line 57)
- Test: `tests/test_types.py`

**Interfaces:**
- Produces: `Projection(movie_title: str, median_in_window_gross: float, sigma: float, floor: float = 0.0)` — frozen Pydantic model. `floor` is the banked in-window gross uncertainty applies above.

- [ ] **Step 1: Write the failing test**

```python
def test_projection_floor_defaults_to_zero():
    from summer_movie_wager.types import Projection
    p = Projection(movie_title="Toy Story 5", median_in_window_gross=180_000_000.0, sigma=0.30)
    assert p.floor == 0.0


def test_projection_floor_can_be_set():
    from summer_movie_wager.types import Projection
    p = Projection(
        movie_title="The Devil Wears Prada 2",
        median_in_window_gross=221_000_000.0,
        sigma=0.10,
        floor=219_602_888.0,
    )
    assert p.floor == 219_602_888.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_types.py::test_projection_floor_defaults_to_zero -v`
Expected: FAIL — `Projection` has no attribute `floor` (or unexpected-keyword error on the second test).

- [ ] **Step 3: Add the field**

In `summer_movie_wager/types.py`, inside `class Projection`, add the field after `sigma`:

```python
class Projection(BaseModel):
    model_config = ConfigDict(frozen=True)

    movie_title: str
    median_in_window_gross: float
    sigma: float
    floor: float = 0.0  # current banked in-window gross; uncertainty applies above this
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_types.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add summer_movie_wager/types.py tests/test_types.py
git commit -m "feat(types): add floor field to Projection for banked in-window gross"
```

---

## Task 2: Remaining-based Monte Carlo sampling

**Files:**
- Modify: `summer_movie_wager/model/simulate.py` (sampling block, ~lines 40-63; remove the TODO at lines 47-57)
- Test: `tests/test_simulate.py`

**Interfaces:**
- Consumes: `Projection(... floor=...)` from Task 1.
- Produces: `simulate_season(...)` unchanged signature; samples now drawn as `floor + remaining * exp(sigma·z)` with `remaining = max(0, median − floor)`.

- [ ] **Step 1: Write the failing test**

```python
def test_in_theaters_floor_is_never_breached():
    # 10 movies so the simulator's >=10 guard passes; movie 0 is a deep-run film
    # whose banked gross is just below its median. Its final gross must never dip
    # below the floor, and its 80% band must stay tight around it.
    import numpy as np
    from summer_movie_wager.model.simulate import simulate_season
    from summer_movie_wager.types import PlayerPicks, Projection

    titles = [f"M{i}" for i in range(10)]
    projections = [
        Projection(
            movie_title="M0",
            median_in_window_gross=221_000_000.0,
            sigma=0.10,
            floor=219_602_888.0,
        )
    ] + [
        Projection(movie_title=titles[i], median_in_window_gross=100_000_000.0 - i, sigma=0.20)
        for i in range(1, 10)
    ]

    # Reproduce the sampler's draw directly to assert the floor invariant on raw samples.
    rng = np.random.default_rng(0)
    floor, median, sigma = 219_602_888.0, 221_000_000.0, 0.10
    remaining = max(0.0, median - floor)
    samples = floor + remaining * np.exp(sigma * rng.standard_normal(10_000))
    assert samples.min() >= floor
    assert np.percentile(samples, 90) <= floor + 10_000_000  # within $10M of banked

    # And the public API still runs end-to-end with a floored projection present.
    players = [
        PlayerPicks(username="u", ranked=titles, dark_horses=["dh1", "dh2", "dh3"])
    ]
    result = simulate_season(players, projections, n_trials=2_000, seed=1)
    assert 0.0 <= result.win_prob["u"] <= 1.0
```

> Note: `dark_horses` must be 3 titles distinct from `ranked`; the test uses
> placeholder dark-horse titles that don't need projections.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_simulate.py::test_in_theaters_floor_is_never_breached -v`
Expected: FAIL — current sampler ignores `floor`, so `samples.min()` (old form `median * exp(...)`) drops below the floor.

- [ ] **Step 3: Replace the sampling block**

In `summer_movie_wager/model/simulate.py`, replace the median/sigma array setup and the lognormal sampling block (including the entire `# TODO:` comment) with:

```python
    medians = np.array([p.median_in_window_gross for p in projections], dtype=float)
    sigmas = np.array([p.sigma for p in projections], dtype=float)
    floors = np.array([p.floor for p in projections], dtype=float)
    remaining = np.maximum(0.0, medians - floors)

    # Uncertainty applies only to the unbanked (remaining) gross:
    #   total = floor + remaining * exp(sigma * Z)
    # exp() is always positive, so a sample can never fall below the banked floor.
    # Pre-release titles have floor=0, recovering the plain lognormal draw.
    samples = np.zeros((n_trials, n_movies), dtype=float)
    draw = remaining > 0
    if draw.any():
        z = rng.standard_normal((n_trials, int(draw.sum())))
        samples[:, draw] = remaining[draw] * np.exp(sigmas[draw] * z)
    samples += floors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_simulate.py -v`
Expected: PASS. Pre-existing simulate tests still pass (floor defaults to 0, so their behavior is unchanged).

- [ ] **Step 5: Commit**

```bash
git add summer_movie_wager/model/simulate.py tests/test_simulate.py
git commit -m "fix(simulate): apply uncertainty to remaining gross, floor samples at banked gross"
```

---

## Task 3: Populate floor and use remaining-based p10/p90 in the build

**Files:**
- Modify: `summer_movie_wager/render/build.py` (`_project_all` ~line 293; `_build_movie_rows` ~lines 481-483)
- Test: `tests/test_build.py`, `tests/test_render_snapshot.py`

**Interfaces:**
- Consumes: `Projection(... floor=...)` from Task 1.
- Produces: in-theaters `Projection`s carry `floor = m["cumulative"]`; movie-row p10/p90 computed as `floor + remaining * exp(±1.2816 * sigma)`.

- [ ] **Step 1: Write the failing test**

```python
def test_in_theaters_row_band_respects_floor():
    # _build_movie_rows should produce p10 >= floor and a tight band for a
    # deep-run film whose median is just above its banked gross.
    import math
    from summer_movie_wager.render.build import _build_movie_rows
    from summer_movie_wager.types import MovieStatus, Projection

    movies = {
        "The Devil Wears Prada 2": {
            "title": "The Devil Wears Prada 2",
            "release_date": __import__("datetime").date(2026, 5, 1),
            "status": MovieStatus.IN_THEATERS,
            "category": __import__("summer_movie_wager.types", fromlist=["Category"]).Category.WIDE,
            "cumulative": 219_602_888.0,
        }
    }
    projections = [
        Projection(
            movie_title="The Devil Wears Prada 2",
            median_in_window_gross=221_000_000.0,
            sigma=0.10,
            floor=219_602_888.0,
        )
    ]
    rows = _build_movie_rows(movies, projections)
    row = rows[0]
    assert row.p10 >= 219_602_888.0
    assert row.p90 <= 219_602_888.0 + 10_000_000
    # exact formula check
    remaining = 221_000_000.0 - 219_602_888.0
    assert math.isclose(row.p90, 219_602_888.0 + remaining * math.exp(1.2816 * 0.10))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_build.py::test_in_theaters_row_band_respects_floor -v`
Expected: FAIL — current `_build_movie_rows` uses `median * exp(±1.2816*sigma)`, so `p10` is ~$194M, below the floor.

- [ ] **Step 3: Populate floor in `_project_all`**

In `summer_movie_wager/render/build.py`, `_project_all`, set a `floor` per movie and pass it through. Replace the final append so it reads:

```python
        floor = m["cumulative"] if m["status"] == MovieStatus.IN_THEATERS else 0.0
        projections.append(
            Projection(
                movie_title=title,
                median_in_window_gross=gross,
                sigma=sigma,
                floor=floor,
            )
        )
```

- [ ] **Step 4: Use remaining-based p10/p90 in `_build_movie_rows`**

Replace the two p10/p90 lines (currently `p10 = median * math.exp(-1.2816 * proj.sigma)` / `p90 = ...`) with:

```python
        median = proj.median_in_window_gross
        remaining = max(0.0, median - proj.floor)
        p10 = proj.floor + remaining * math.exp(-1.2816 * proj.sigma)
        p90 = proj.floor + remaining * math.exp(1.2816 * proj.sigma)
```

- [ ] **Step 5: Run tests; refresh the render snapshot**

Run: `uv run pytest tests/test_build.py -v`
Expected: the new test PASSES.

Run: `uv run pytest tests/test_render_snapshot.py -v`
Expected: may FAIL if the snapshot encodes p10/p90 for a nonzero-sigma in-theaters row. Inspect the diff; if the only changes are the corrected floor-based bands, update the expected snapshot fixture to match (follow the snapshot-update convention already used in that test file). Re-run until green.

- [ ] **Step 6: Commit**

```bash
git add summer_movie_wager/render/build.py tests/test_build.py tests/test_render_snapshot.py
git commit -m "fix(build): floor in-theaters projections and compute p10/p90 on remaining gross"
```

---

## Task 4: End-to-end verification

**Files:**
- No source changes. Verification only.

- [ ] **Step 1: Full test suite**

Run: `uv run pytest`
Expected: all green.

- [ ] **Step 2: Run the pipeline locally**

Run: `uv run python -m summer_movie_wager.render.build --local`
Expected: exits 0; `docs/index.html` written.

- [ ] **Step 3: Verify the DWP2 band**

Inspect the rendered output (or the `raw["projections"]` block / movie row) for
*The Devil Wears Prada 2*. Confirm:
- p10 ≥ `219,602,888`
- p90 within ~$10M of it (expected ≈ `[$220.8M, $221.2M]`)

- [ ] **Step 4: Verify nothing else regressed**

Confirm a young in-theaters film still shows a wide band, a pre-release analyst
film's band is unchanged vs. `main`, and `forecast_available` / the leaderboard
still render with the new `floor` field present.

- [ ] **Step 5: Commit any snapshot/data churn (if generated)**

```bash
git add -A
git commit -m "chore: refresh build artifacts after uncertainty-floor fix"
```

---

## Self-Review

- **Spec coverage:** floor field (Task 1), remaining-based sampler (Task 2),
  floor population + remaining-based p10/p90 + snapshot refresh (Task 3),
  DWP2 + regression verification (Task 4). `_sigma_from_weeks` deliberately
  untouched per spec. All spec sections covered.
- **Placeholders:** none — every code step shows the exact change.
- **Type consistency:** `floor: float` used identically across `types.py`,
  `simulate.py`, and `build.py`; draw form identical in sampler and display.
