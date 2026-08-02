# Winning Scenarios View — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tabbed per-player "how you win" grid to the site that shows, for each player, the most-likely actual top-10 finish in which they win the wager — computed from the existing 10k Monte Carlo trials, not from a placeholder reshuffle.

**Architecture:** The simulator already produces, per trial, an actual top-10 ordering (`top_10_indices`) and a winner (`is_top`). We retain those, and for each player take the **medoid** of their strict-win trials (the most representative real winning finish) under an L1/Spearman-footrule rank distance. Each scenario emits the finish order, every player's per-rank point breakdown, totals, win %, and margin. These flow through `build.py` → `data.json` and into a new standalone `scenarios.html` page (linked from the leaderboard), where the committed mockup's tab/grid JS drives the view. Gated on the existing `forecast_available` flag.

**Tech Stack:** Python 3, Pydantic v2, NumPy, Jinja2, pytest, `uv`. Front-end is vanilla JS + CSS reusing the existing theme tokens.

**Spec:** `docs/superpowers/specs/2026-06-29-winning-scenarios-view-design.md`

**Design reference (approved mockup):** `docs/previews/winning-scenarios.html` — the target look, tab behavior, and the exact tab/grid render JS to reuse.

## Global Constraints

- Scenario source is the **medoid** of a player's strict-win trials. **Never** the mockup's nearest-reorder flip. The medoid is an actual sampled trial.
- Rank distance between two top-10 finishes = Spearman footrule with out-of-list rank `11`, which equals the **L1 distance between rank vectors** (movies absent from both contribute 0). Medoid = trial minimizing summed distance to the other win trials; ties break to the **lowest trial index**.
- `MEDOID_SAMPLE_CAP = 1500`: if a player has more win trials than this, medoid runs over a seeded random subsample of that size (still a real trial). Mark with a `ponytail:` comment naming the cap.
- `sum(score_breakdown(picks, top)) == score_player(picks, top)` must always hold; `score_player` is refactored to delegate to `score_breakdown`.
- Strict wins only (a trial counts for a player iff `is_top[player] & (n_winners_per_trial == 1)`) — identical to how `win_prob` is defined.
- Determinism: fixed `seed` ⇒ identical scenarios. Build runs with `seed=20260907`, `n_trials=10_000`.
- Forecast gate: scenarios computed only when `forecast_available` (≥ 25 non-zero projections). Otherwise emit `{username: None}` for every player, mirroring the existing null branch for `win_prob`.
- Run tests with `uv run pytest`; run the pipeline with `uv run python -m summer_movie_wager.render.build --local`.

---

## File Structure

```
summer_movie_wager/score/rules.py                  — add score_breakdown(); score_player delegates to it
summer_movie_wager/types.py                         — add WinningScenario model
summer_movie_wager/model/simulate.py                — keep per-trial orderings/winners; medoid; build winning_scenarios
summer_movie_wager/render/build.py                     — thread winning_scenarios into raw dict (+ null branch)
summer_movie_wager/render/page.py                      — inline shared theme.css into both pages; render scenarios.html
summer_movie_wager/render/static/theme.css             — NEW shared theme tokens (extracted from style.css), used by both pages
summer_movie_wager/render/static/style.css             — token blocks removed (now in theme.css)
summer_movie_wager/render/templates/scenarios.html.j2  — NEW standalone Winning Scenarios page (from the mockup), consumes theme.css
summer_movie_wager/render/templates/index.html.j2      — gated nav link to scenarios.html
tests/test_score.py                                    — score_breakdown invariants
tests/test_simulate.py                                 — medoid scenarios: none-when-no-win, structure, consistency
tests/test_build.py                                    — raw["winning_scenarios"] present/null
tests/test_render_snapshot.py                          — scenarios.html has grid + const; index links to it (gated)
```

---

## Task 1: `score_breakdown` — per-rank points decomposition

**Files:**
- Modify: `summer_movie_wager/score/rules.py` (add `score_breakdown`; rewrite `score_player` body, replacing the `# TODO BAC 2026-06-19` block)
- Test: `tests/test_score.py`

**Interfaces:**
- Produces: `score_breakdown(picks: PlayerPicks, top_titles: list[str]) -> list[int]` — points each actual finisher contributes for `picks`, indexed by actual position (`len == len(top_titles)`), including the `+1` dark-horse bonus on the rank where a dark horse lands.
- Produces: `score_player(picks, top_titles) -> int` unchanged signature; now `== sum(score_breakdown(...))`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_score.py`:

```python
from summer_movie_wager.score.rules import score_breakdown, score_player
from summer_movie_wager.types import PlayerPicks


def _picks() -> PlayerPicks:
    return PlayerPicks(
        username="t",
        ranked=[f"R{i}" for i in range(1, 11)],   # R1..R10 predicted #1..#10
        dark_horses=["D1", "D2", "D3"],
    )


def test_breakdown_sums_to_score_player():
    picks = _picks()
    # actual top 10: R1 exact #1, R3 at #2 (off by 1), a dark horse D2 at #5, rest unknowns
    top = ["R1", "R3", "X", "X4", "D2", "X6", "X7", "X8", "X9", "X10"]
    b = score_breakdown(picks, top)
    assert len(b) == len(top)
    assert sum(b) == score_player(picks, top)
    assert b[0] == 13          # R1 exact at endpoint #1
    assert b[1] == 7           # R3 predicted #3, actual #2 -> off by 1
    assert b[4] == 1           # dark horse D2 landed at #5


def test_breakdown_zero_for_absent_picks():
    picks = _picks()
    top = ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7", "Z8", "Z9", "Z10"]
    b = score_breakdown(picks, top)
    assert b == [0] * 10
    assert score_player(picks, top) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_score.py::test_breakdown_sums_to_score_player -v`
Expected: FAIL — `ImportError`/`AttributeError`: `score_breakdown` does not exist.

- [ ] **Step 3: Implement `score_breakdown` and delegate `score_player`**

In `summer_movie_wager/score/rules.py`, add `score_breakdown` and replace the body of `score_player` (delete the `# TODO BAC 2026-06-19` block and the manual loop):

```python
def score_breakdown(picks: PlayerPicks, top_titles: list[str]) -> list[int]:
    """Points each actual finisher contributes for `picks`, indexed by actual
    position. len == len(top_titles). Includes the +1 dark-horse bonus on the
    rank where a dark horse lands. sum(...) == score_player(picks, top_titles)."""
    if len(top_titles) > 10:
        raise ValueError(f"top_titles must have at most 10 entries, got {len(top_titles)}")
    actual_position = {title: i + 1 for i, title in enumerate(top_titles)}
    breakdown = [0] * len(top_titles)
    for predicted_index, title in enumerate(picks.ranked, start=1):
        pos = actual_position.get(title, 0)
        if pos:
            breakdown[pos - 1] += ranked_pick_points(predicted_index, pos)
    for dh in picks.dark_horses:
        pos = actual_position.get(dh, 0)
        if pos:
            breakdown[pos - 1] += 1
    return breakdown


def score_player(picks: PlayerPicks, top_titles: list[str]) -> int:
    """Total wager points for a player given the (partial or complete) top finalists."""
    return sum(score_breakdown(picks, top_titles))
```

> Keep the existing module docstring and `ranked_pick_points` exactly as-is.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_score.py -v`
Expected: PASS, including any pre-existing `score_player` tests (behavior is unchanged).

- [ ] **Step 5: Commit**

```bash
git add summer_movie_wager/score/rules.py tests/test_score.py
git commit -m "feat(score): add score_breakdown; score_player delegates to it"
```

---

## Task 2: `WinningScenario` model + `SimulationResult` field

**Files:**
- Modify: `summer_movie_wager/types.py` (add `WinningScenario` after `Projection`)
- Modify: `summer_movie_wager/model/simulate.py` (add field to `SimulationResult` dataclass only)
- Test: `tests/test_types.py`

**Interfaces:**
- Produces: `WinningScenario(films: list[str], grid: dict[str, list[int]], totals: dict[str, int], win_pct: float, margin: int)` — frozen Pydantic model.
- Produces: `SimulationResult.winning_scenarios: dict[str, WinningScenario | None]`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_types.py`:

```python
def test_winning_scenario_model():
    from summer_movie_wager.types import WinningScenario
    s = WinningScenario(
        films=[f"F{i}" for i in range(10)],
        grid={"a": [1] * 10, "b": [0] * 10},
        totals={"a": 10, "b": 0},
        win_pct=33.6,
        margin=1,
    )
    assert s.films[0] == "F0"
    assert s.totals["a"] == 10
    assert s.margin == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_types.py::test_winning_scenario_model -v`
Expected: FAIL — `ImportError`: cannot import `WinningScenario`.

- [ ] **Step 3: Add the model**

In `summer_movie_wager/types.py`, after the `Projection` class:

```python
class WinningScenario(BaseModel):
    """The most-likely actual top-10 finish in which a given player wins.

    films:  10 actual titles in finish order #1..#10.
    grid:   username -> per-rank points (len 10) for this finish.
    totals: username -> total points for this finish.
    win_pct: the player's overall win probability, as a percent (0..100).
    margin:  winner total minus runner-up total (>= 1)."""

    model_config = ConfigDict(frozen=True)

    films: list[str]
    grid: dict[str, list[int]]
    totals: dict[str, int]
    win_pct: float
    margin: int
```

- [ ] **Step 4: Add the field to `SimulationResult`**

In `summer_movie_wager/model/simulate.py`, import the model and extend the dataclass:

```python
from summer_movie_wager.types import PlayerPicks, Projection, WinningScenario
```

```python
@dataclass(frozen=True)
class SimulationResult:
    win_prob: dict[str, float]
    tie_prob: dict[str, float]
    median_final_pts: dict[str, float]
    p10_final_pts: dict[str, float]
    p90_final_pts: dict[str, float]
    winning_scenarios: dict[str, "WinningScenario | None"]
```

> Do not yet populate it in `simulate_season` — Task 3 does that. The build does not call `SimulationResult(...)` directly, so no other construction site needs touching until Task 3 fills the field.

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_types.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add summer_movie_wager/types.py summer_movie_wager/model/simulate.py tests/test_types.py
git commit -m "feat(types): add WinningScenario model and SimulationResult field"
```

---

## Task 3: Compute winning scenarios via medoid of win trials

**Files:**
- Modify: `summer_movie_wager/model/simulate.py` (keep `top_10_indices`; add `_most_likely_win_trial` helper; populate `winning_scenarios`)
- Test: `tests/test_simulate.py`

**Interfaces:**
- Consumes: `score_breakdown` (Task 1), `WinningScenario` (Task 2), and the simulator's existing `top_10_indices` (n_trials × 10 movie indices), `is_top` (n_players × n_trials bool), `n_winners_per_trial`, `score_matrix` (n_players × n_trials).
- Produces: `SimulationResult.winning_scenarios` populated; `simulate_season` signature unchanged.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_simulate.py`:

```python
def _ten_projections(seed_offset=0):
    from summer_movie_wager.types import Projection
    # Strongly separated medians so the top-10 order is stable across trials.
    return [
        Projection(movie_title=f"M{i}", median_in_window_gross=float((20 - i) * 10_000_000), sigma=0.15)
        for i in range(12)
    ]


def test_winning_scenarios_structure_and_consistency():
    from summer_movie_wager.model.simulate import simulate_season
    from summer_movie_wager.types import PlayerPicks, WinningScenario

    titles = [f"M{i}" for i in range(12)]
    # winner predicts the dominant order exactly; loser predicts it reversed
    winner = PlayerPicks(username="win", ranked=titles[:10], dark_horses=["M10", "M11", "Mz"])
    loser = PlayerPicks(username="lose", ranked=titles[:10][::-1], dark_horses=["Mx", "My", "Mz"])

    res = simulate_season([winner, loser], _ten_projections(), n_trials=3_000, seed=42)

    s = res.winning_scenarios["win"]
    assert isinstance(s, WinningScenario)
    assert len(s.films) == 10
    # winner is the strict leader by margin >= 1
    assert s.totals["win"] == max(s.totals.values())
    assert s.margin >= 1
    # grid columns sum to totals
    for user, col in s.grid.items():
        assert sum(col) == s.totals[user]
    # win_pct matches win_prob (percent form)
    assert abs(s.win_pct - round(res.win_prob["win"] * 100, 1)) < 1e-9


def test_no_scenario_when_player_never_wins():
    from summer_movie_wager.model.simulate import simulate_season
    from summer_movie_wager.types import PlayerPicks

    titles = [f"M{i}" for i in range(12)]
    strong = PlayerPicks(username="strong", ranked=titles[:10], dark_horses=["M10", "M11", "Mz"])
    # 'weak' predicts only films that essentially never reach the top 10
    weak = PlayerPicks(username="weak", ranked=titles[2:12], dark_horses=["Ma", "Mb", "Mc"])

    res = simulate_season([strong, weak], _ten_projections(), n_trials=3_000, seed=7)
    # strong dominates; weak should have win_prob 0 and therefore no scenario
    if res.win_prob["weak"] == 0.0:
        assert res.winning_scenarios["weak"] is None
    # strong always has a scenario
    assert res.winning_scenarios["strong"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_simulate.py::test_winning_scenarios_structure_and_consistency -v`
Expected: FAIL — `winning_scenarios` is currently unset/`{}` (or `TypeError` for missing dataclass arg).

- [ ] **Step 3: Add the medoid helper**

In `summer_movie_wager/model/simulate.py`, add a module-level constant and helper:

```python
MEDOID_SAMPLE_CAP = 1500


def _most_likely_win_trial(
    top_10_indices: np.ndarray,   # (n_trials, 10) movie indices, finish order
    win_trials: np.ndarray,       # 1-D indices of this player's strict-win trials
    n_movies: int,
    rng: np.random.Generator,
) -> int:
    """Return the trial index that is the medoid of `win_trials` under the
    Spearman-footrule (== L1 of rank vectors) distance between top-10 finishes.
    Movies outside a trial's top-10 are assigned rank 11, so absent-in-both pairs
    contribute 0 and the footrule equals the L1 distance over all movies."""
    # ponytail: cap the medoid search at MEDOID_SAMPLE_CAP trials (O(W^2)); the
    # medoid is still a real winning trial. Lift the cap / vectorize per-column
    # only if build time becomes a problem.
    if win_trials.size > MEDOID_SAMPLE_CAP:
        win_trials = np.sort(rng.choice(win_trials, MEDOID_SAMPLE_CAP, replace=False))
    if win_trials.size == 1:
        return int(win_trials[0])

    w = win_trials.size
    # rank matrix R[k, movie] = position 1..10 in trial win_trials[k], else 11
    R = np.full((w, n_movies), 11, dtype=np.int32)
    rows = np.repeat(np.arange(w), 10)
    cols = top_10_indices[win_trials].reshape(-1)
    R[rows, cols] = np.tile(np.arange(1, 11), w)

    # summed L1 distance from each trial to all others, accumulated per movie
    # column to avoid a (w, w, n_movies) temporary.
    cost = np.zeros(w, dtype=np.float64)
    for m in range(n_movies):
        col = R[:, m]
        cost += np.abs(col[:, None] - col[None, :]).sum(axis=1)
    return int(win_trials[int(cost.argmin())])  # argmin ties -> lowest index
```

- [ ] **Step 4: Populate `winning_scenarios` in `simulate_season`**

`top_10_indices` is already computed (`np.argsort(-samples, axis=1)[:, :10]`). Keep it. After the existing per-player aggregation loop (after `win_prob`/`tie_prob`/percentiles are filled), and before `return SimulationResult(...)`, add:

```python
    from summer_movie_wager.score import score_breakdown

    winning_scenarios: dict[str, "WinningScenario | None"] = {}
    for i, player in enumerate(players):
        win_trials = np.nonzero(is_top[i] & (n_winners_per_trial == 1))[0]
        if win_trials.size == 0:
            winning_scenarios[player.username] = None
            continue
        sub_rng = np.random.default_rng(None if seed is None else seed ^ (i + 1))
        medoid = _most_likely_win_trial(top_10_indices, win_trials, n_movies, sub_rng)
        films = [movie_titles[j] for j in top_10_indices[medoid]]
        grid = {p.username: score_breakdown(p, films) for p in players}
        totals = {u: sum(col) for u, col in grid.items()}
        winner_total = totals[player.username]
        runner_up = max(t for u, t in totals.items() if u != player.username)
        winning_scenarios[player.username] = WinningScenario(
            films=films,
            grid=grid,
            totals=totals,
            win_pct=round(win_prob[player.username] * 100, 1),
            margin=int(winner_total - runner_up),
        )
```

Add `winning_scenarios=winning_scenarios` to the `SimulationResult(...)` constructor call.

> Import note: `score_breakdown` is imported from `summer_movie_wager.score` (re-exported there alongside `score_player`). If it is not yet re-exported, add `from summer_movie_wager.score.rules import score_breakdown` and export it in `summer_movie_wager/score/__init__.py` next to `score_player`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_simulate.py -v`
Expected: PASS. Pre-existing simulate tests still pass (they ignore `winning_scenarios`).

- [ ] **Step 6: Commit**

```bash
git add summer_movie_wager/model/simulate.py summer_movie_wager/score/__init__.py tests/test_simulate.py
git commit -m "feat(simulate): compute per-player winning scenarios via medoid of win trials"
```

---

## Task 4: Thread `winning_scenarios` into `data.json`

**Files:**
- Modify: `summer_movie_wager/render/build.py` (the `raw` dict assembly and its forecast-unavailable null branch, ~lines 123-144)
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: `sim.winning_scenarios` (Task 3).
- Produces: `raw["winning_scenarios"]`: `{username: WinningScenario-as-dict | None}` when forecast available; `{username: None}` for all players otherwise.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_build.py` (follow the file's existing pattern for invoking the build / inspecting `raw`; if the suite already builds `raw` via a helper, reuse it):

```python
def test_raw_has_winning_scenarios_when_forecast_available(built_raw_forecast_on):
    raw = built_raw_forecast_on  # existing fixture or helper producing the raw dict with forecast on
    assert "winning_scenarios" in raw
    ws = raw["winning_scenarios"]
    # every player key present; entries are dict or None
    for username, entry in ws.items():
        assert entry is None or {"films", "grid", "totals", "win_pct", "margin"} <= set(entry)


def test_raw_winning_scenarios_all_null_when_forecast_off(built_raw_forecast_off):
    raw = built_raw_forecast_off  # existing fixture/helper with < 25 non-zero projections
    assert set(raw["winning_scenarios"].values()) == {None}
```

> If `tests/test_build.py` has no such fixtures, add minimal ones mirroring how the file already constructs `raw` for the existing `win_prob` assertions; the two states differ only by whether ≥ 25 projections are non-zero.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_build.py -k winning_scenarios -v`
Expected: FAIL — `KeyError: 'winning_scenarios'`.

- [ ] **Step 3: Populate the raw dict**

In `summer_movie_wager/render/build.py`, in the `if forecast_available and sim is not None:` block (after the `p90_final_pts` line):

```python
        raw["winning_scenarios"] = {
            u: (s.model_dump() if s is not None else None)
            for u, s in sim.winning_scenarios.items()
        }
```

In the `else:` null branch (after the existing null assignments):

```python
        raw["winning_scenarios"] = {u: None for u in snapshot.players}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_build.py -k winning_scenarios -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add summer_movie_wager/render/build.py tests/test_build.py
git commit -m "feat(build): emit winning_scenarios into data.json"
```

---

## Task 5: Shared theme stylesheet + standalone `scenarios.html` page

**Files:**
- Create: `summer_movie_wager/render/static/theme.css` (shared theme tokens, extracted from `style.css` + scenario tokens)
- Modify: `summer_movie_wager/render/static/style.css` (remove the token blocks; they move to `theme.css`)
- Create: `summer_movie_wager/render/templates/scenarios.html.j2` (from the committed mockup, consuming the shared tokens)
- Modify: `summer_movie_wager/render/page.py` (`render`: inline `theme.css` into both pages; render `scenarios.html`)
- Modify: `summer_movie_wager/render/templates/index.html.j2` (gated nav link)
- Test: `tests/test_render_snapshot.py`

**Interfaces:**
- Consumes: `data.raw_snapshot["winning_scenarios"]`, `data.raw_snapshot["win_prob"]`, `data.forecast_available`.
- Produces: `out_dir/scenarios.html` containing the grid markup, the shared theme tokens, and `const DATA = {...}`; `out_dir/index.html` containing the shared theme tokens and a `href="scenarios.html"` link when `forecast_available`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_render_snapshot.py`:

```python
def _render_pages(tmp_path, forecast_available):
    from datetime import datetime, timezone
    from summer_movie_wager.render.page import LeaderboardRow, RenderInput, render

    leaderboard = [
        LeaderboardRow(username="a", current_pts=10, median_pts=10.0,
                       p10_pts=5.0, p90_pts=15.0, win_prob=0.5, tie_prob=0.0),
        LeaderboardRow(username="b", current_pts=5, median_pts=5.0,
                       p10_pts=1.0, p90_pts=9.0, win_prob=0.0, tie_prob=0.0),
    ]
    scenarios = {
        "a": {"films": [f"F{i}" for i in range(10)],
              "grid": {"a": [1] * 10, "b": [0] * 10},
              "totals": {"a": 10, "b": 0}, "win_pct": 50.0, "margin": 10},
        "b": None,
    }
    raw = {
        "win_prob": {"a": 0.5, "b": 0.0},
        "winning_scenarios": scenarios if forecast_available else {"a": None, "b": None},
    }
    render(tmp_path, RenderInput(
        generated_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
        leaderboard=leaderboard, movies=[], player_details=[],
        raw_snapshot=raw, forecast_available=forecast_available,
        forecast_unavailable_reason="" if forecast_available else "only 3 movies projected",
    ))
    return (tmp_path / "index.html").read_text(), (tmp_path / "scenarios.html").read_text()


def test_shared_theme_tokens_inlined_into_both_pages(tmp_path):
    index, scenarios = _render_pages(tmp_path, True)
    # the shared token set (base + scenario tokens) is present on both pages
    for css in (index, scenarios):
        assert "--bg-card:" in css       # existing shared token
        assert "--accent:" in css        # scenario token, now shared
        assert "--win-bg:" in css


def test_scenarios_page_and_link_when_forecast_on(tmp_path):
    index, scenarios = _render_pages(tmp_path, True)
    assert 'id="view"' in scenarios            # grid view markup present
    assert "const DATA =" in scenarios          # scenarios embedded
    assert "const FORECAST_AVAILABLE = true" in scenarios
    assert 'href="scenarios.html"' in index     # leaderboard links to the page


def test_scenarios_gated_and_unlinked_when_forecast_off(tmp_path):
    index, scenarios = _render_pages(tmp_path, False)
    assert "const FORECAST_AVAILABLE = false" in scenarios  # page shows gated notice
    assert 'href="scenarios.html"' not in index             # link hidden
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_render_snapshot.py -k "scenarios or theme" -v`
Expected: FAIL — `scenarios.html` is not written (`FileNotFoundError`).

- [ ] **Step 3: Extract a shared `theme.css`**

Create `summer_movie_wager/render/static/theme.css`. Move the three theme-token
blocks **verbatim** out of `style.css` — the `:root { … }`, the
`[data-theme="dark"] { … }`, and the
`@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { … } }`
blocks (currently `style.css` lines ~1–76). Then add these scenario tokens to
each block (light values in `:root`; dark values in both the `[data-theme="dark"]`
block and the `prefers-color-scheme` block):

```css
/* add to the light :root block */
  --accent:        #6c3fcf;
  --accent-soft:   #e0d9ff;
  --accent-soft-2: #efeaff;
  --win-bg:        #c9f7e8;
  --win-color:     #1a7a54;
  --zero:          #bdbdbd;
```

```css
/* add to BOTH dark blocks */
  --accent:        #c4b0ff;
  --accent-soft:   #3a2a6a;
  --accent-soft-2: #2a2150;
  --win-bg:        #0d3d28;
  --win-color:     #4ecdc4;
  --zero:          #4a4266;
```

- [ ] **Step 4: Trim `style.css` and inline both sheets in `page.py`**

In `summer_movie_wager/render/static/style.css`, **delete** the three token
blocks now living in `theme.css` (everything above `* { box-sizing: border-box; }`).
`style.css` now contains only base + component rules that reference the tokens.

In `summer_movie_wager/render/page.py`, change the CSS read so the shared tokens
are inlined ahead of the component styles (the `index.html.j2` template still
reads `{{ inline_css | safe }}`, unchanged):

```python
    theme_css = (_STATIC / "theme.css").read_text()
    inline_css = theme_css + "\n" + (_STATIC / "style.css").read_text()
```

- [ ] **Step 5: Create the standalone page template**

Create `summer_movie_wager/render/templates/scenarios.html.j2` from the committed
mockup `docs/previews/winning-scenarios.html` with exactly these edits (the
tab/grid render JS and dark-mode toggle are kept verbatim):

1. **Use the shared tokens instead of the mockup's own.** Delete the mockup's
   three token blocks from its `<style>` (the `:root`, `[data-theme="dark"]`, and
   `@media (prefers-color-scheme: dark)` blocks). Immediately before the
   remaining `<style>` (which keeps the base `body` + scenario layout rules:
   `.tabs`, `.tab`, `.scenario-caption`, `.grid-wrap`, table, `.col-sel`,
   `tfoot`, `.gated`, `.theme-toggle`, …), add a first style element that inlines
   the shared tokens:
   ```jinja
   <style>{{ theme_css | safe }}</style>
   ```
2. In the `<script>` data block, replace the entire embedded literal
   `const DATA = {...};` with:
   ```js
   const DATA = {{ scenario_json | safe }};
   ```
3. Replace the hardcoded toggle line `const FORECAST_AVAILABLE=true;` with:
   ```js
   const FORECAST_AVAILABLE = {{ 'true' if forecast_available else 'false' }};
   ```
4. In the gated notice `<div class="gated" id="gated">`, append the reason:
   ```jinja
   ⏳ Not enough films are in theaters yet to simulate win probabilities{% if forecast_unavailable_reason %} — {{ forecast_unavailable_reason }}{% endif %}. This view unlocks once the forecast is live.
   ```
5. Remove the `<span class="mock-flag">mockup</span>` from the `<h1>` and drop the
   "Static mockup ·" wording in the `<footer>`, replacing the footer with:
   ```jinja
   <p><a href="index.html">← Back to the leaderboard</a></p>
   Refreshed {{ generated_at }}.
   ```

> The mockup already structures the page this way (`#view` vs `#gated` toggled by
> `FORECAST_AVAILABLE`, its own `localStorage` dark-mode toggle). With the token
> blocks removed, both pages now draw their palette from the single shared
> `theme.css` — no duplicated token values.

- [ ] **Step 6: Render the page in `page.py`**

In `summer_movie_wager/render/page.py`, inside `render`, after `index.html` is
written, build the payload and render the second page (`env`, `theme_css`, and
`json` are already in scope):

```python
    scenario_payload = {
        "standing": [row.username for row in data.leaderboard],  # current-points order
        "win_prob": data.raw_snapshot.get("win_prob", {}),
        "scenarios": data.raw_snapshot.get("winning_scenarios", {}),
    }
    scenarios_html = env.get_template("scenarios.html.j2").render(
        generated_at = data.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        theme_css = theme_css,
        scenario_json = json.dumps(scenario_payload, default=str),
        forecast_available = data.forecast_available,
        forecast_unavailable_reason = data.forecast_unavailable_reason,
    )
    (out_dir / "scenarios.html").write_text(scenarios_html)
```

> The payload shape `{standing, win_prob, scenarios}` is exactly what the mockup
> JS expects (`DATA.standing`, `DATA.win_prob`, `DATA.scenarios`).

- [ ] **Step 7: Add the gated nav link to the leaderboard**

In `summer_movie_wager/render/templates/index.html.j2`, inside the header block
near the `<p class="meta">Window …</p>` line, add:

```jinja
{% if forecast_available %}
<p class="meta"><a class="scenarios-link" href="scenarios.html">🏆 See each player's winning scenarios →</a></p>
{% endif %}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_render_snapshot.py -k "scenarios or theme" -v`
Expected: PASS. If the file keeps a full-page golden snapshot of `index.html`,
inspect the diff; the only changes should be the added link line and the
token-block source moving from `style.css` to the inlined `theme.css` (the
rendered token values are unchanged). Update the golden fixture per the file's
existing update convention. Re-run until green.

- [ ] **Step 9: Commit**

```bash
git add summer_movie_wager/render/static/theme.css \
        summer_movie_wager/render/static/style.css \
        summer_movie_wager/render/page.py \
        summer_movie_wager/render/templates/scenarios.html.j2 \
        summer_movie_wager/render/templates/index.html.j2 \
        tests/test_render_snapshot.py
git commit -m "feat(render): shared theme.css + standalone scenarios.html page"
```

---

## Task 6: End-to-end verification

**Files:** No source changes — verification only.

- [ ] **Step 1: Full test suite**

Run: `uv run pytest`
Expected: all green.

- [ ] **Step 2: Run the pipeline locally**

Run: `uv run python -m summer_movie_wager.render.build --local`
Expected: exits 0; writes `docs/index.html` and `docs/data.json`.

- [ ] **Step 3: Verify `data.json` scenarios are real**

Inspect `docs/data.json` → `winning_scenarios`:
- every player with `win_prob > 0` has a non-null entry; `films` has 10 titles; `totals` make that player the strict max with `margin >= 1`; each `grid` column sums to its `totals` value;
- every player with `win_prob == 0` (currently `radhadr`) is `null`;
- **finishes differ between players and margins vary** (not a uniform 1-pt flip) — confirming the medoid path, not the mockup heuristic.

- [ ] **Step 4: Verify the rendered view**

Open `docs/index.html`: confirm the "Winning Scenarios" link appears, and follow it to `docs/scenarios.html`. On that page: tabs are ordered by win % with zero-chance players grayed/disabled; clicking a tab swaps the grid and re-sorts columns so the selected player is the crowned (👑), left-most column; the "← Back to the leaderboard" link returns to `index.html`. Confirm light/dark toggle and mobile horizontal scroll behave as in the mockup.

- [ ] **Step 5: Commit any artifact churn**

```bash
git add -A
git commit -m "chore: rebuild site with winning-scenarios view"
```

---

## Self-Review

- **Spec coverage:**
  - "What the view shows" (tabs by likelihood, per-scenario column sort, grayed no-win, gating) → Task 5 (standalone `scenarios.html` from the mockup, reusing `tabOrder` + totals sort) + Task 4/5 gating on `forecast_available` (page shows gated notice; leaderboard link hidden).
  - "Page" (separate `scenarios.html`, linked from `index.html`, shared theme tokens + own toggle) → Task 5 (new `theme.css` inlined into both pages, new `scenarios.html.j2`, `page.py` renders it, gated link in `index.html.j2`).
  - Medoid algorithm + footrule/L1 distance + cap + "not nearest-reorder flip" → Task 3 (helper, constant, ponytail comment) + verified real in Task 6 Step 3.
  - `score_breakdown` helper + `score_player` delegation → Task 1.
  - `WinningScenario` model + `SimulationResult` field → Task 2.
  - `data.json` schema (+ null branch when forecast off) → Task 4.
  - Edge cases (no win trials → null; ties excluded; single win trial; forecast off) → Task 3 (`win_trials.size == 0`, strict-win mask, `size == 1`) and Task 4 (null branch).
  - Testing/verification sections → Tasks 1-6 tests + Task 6.
- **Placeholder scan:** none — every code step gives concrete code; the one "lift verbatim from the mockup" instruction names the exact source file, the exact block, and the exact substitutions (the source is committed in-repo, so this is a real, resolvable reference, not a TODO).
- **Type consistency:** `score_breakdown(picks, top_titles) -> list[int]` used identically in Tasks 1 and 3; `WinningScenario(films, grid, totals, win_pct, margin)` identical across Tasks 2, 3, 4; `winning_scenarios: dict[str, WinningScenario | None]` consistent across Tasks 2-4; payload shape `{standing, win_prob, scenarios}` matches the mockup JS consumed in Task 5.
