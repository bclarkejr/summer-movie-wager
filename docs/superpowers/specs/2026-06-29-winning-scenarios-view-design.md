# Winning Scenarios View — Per-Player "How You Win" Grid

**Status:** Approved 2026-06-29

## Context

The leaderboard answers "who is winning *now*" and "what is each player's chance
of winning." It does not answer the question players actually argue about:
*"What has to happen for **me** to win?"*

This feature adds a **Winning Scenarios** view: a tabbed grid that, for each
player, shows the single most-likely **actual top-10 box-office finish order**
in which that player wins the wager — and exactly how every player's predictions
score against that finish.

A static, theme-matched mockup of the target UI already exists at
`docs/previews/winning-scenarios.html` and is the approved design reference. This
spec covers turning that mockup into a real, data-driven view fed by the Monte
Carlo simulator.

### The wager, in one paragraph

Each player submits a **ranked top-10 prediction** plus 3 dark horses. Scoring
(`score/rules.py`) compares each ranked pick's predicted position to the film's
*actual* finishing position in the season's top 10: exact = 13 pts at the
endpoints (#1/#10) else 10, off-by-1 = 7, off-by-2 = 5, in-top-10-but-off-by-3+
= 3, absent = 0; each dark horse that lands in the top 10 = +1. Every player
scores against the **same** actual top 10. So a "scenario in which player X
wins" is fully described by **one specific actual top-10 finish order** — the one
that makes X's predictions out-score everyone else's.

## What the view shows

- **Tab bar** — one tab per player, ordered by **win likelihood** (highest
  `win_prob` first). Each tab shows the player's win %. A player with no winning
  scenario (`win_prob == 0` → zero winning trials) renders **grayed/disabled**.
- **Per-player grid** (swaps on tab click; every player's differs):
  - **Rows** = the 10 films of that player's most-likely winning finish, in
    actual order #1 → #10.
  - **Columns** = all players, ordered by **that scenario's** final points
    (winner leftmost). Columns re-sort per scenario.
  - **Cells** = the points that player earns from the film at that rank (0 shown
    dimmed). A **Total** row crowns the winner (👑), who is always the selected
    player and the left-most column.
  - The selected player's column is highlighted.
- **Gating** — scenarios exist only when the forecast is available
  (`forecast_available == True`, i.e. ≥ 25 non-zero projections — the same gate
  that governs whether `win_prob` exists at all). Until then the scenarios page
  shows a "not enough films in theaters yet" notice and the leaderboard hides its
  link to the page.
- **Page** — the view is its **own page**, `docs/scenarios.html`, reached from a
  nav link on the main leaderboard (`index.html`). It is a self-contained
  standalone page (its own `<head>`, styles, and dark-mode toggle) reusing the
  same Nunito + purple light/dark theme. It is **not** a section inside
  `index.html`.

## How a scenario is computed — the core of this work

> **Explicit non-goal.** The mockup fabricates scenarios with a *nearest-reorder
> flip*: it starts from the projected box-office order and applies the smallest
> reshuffle that tips a chosen player into the lead. That heuristic exists only
> to populate the mockup and **must not** ship. It does not reflect the
> probability mass of real outcomes — it manufactures a uniform 1-point win for
> everyone regardless of how plausible that finish actually is.

The real scenario comes from the **10,000 Monte Carlo trials already run** in
`simulate_season`. Each trial samples every film's in-window gross, ranks them,
and yields a concrete actual top-10 ordering plus a winner. The algorithm:

1. **Subset to the player's winning trials.** For player X, take the trials
   where X is the *strict* winner (`is_top[X] & (n_winners_per_trial == 1)`).
   If that set is empty, X has **no scenario** (tab disabled, value `null`).
2. **Pick the most representative winning finish (the medoid).** Among X's
   winning trials, choose the trial whose actual top-10 ordering is *most
   central* to the rest — the **medoid** under a rank-distance metric:
   - Distance between two top-10 orderings = **Spearman footrule** over the
     union of their titles, with a title absent from one list assigned rank 11
     (a fixed out-of-list penalty). This handles the fact that different winning
     trials can contain different films.
   - The medoid is the winning trial minimizing the summed distance to all other
     winning trials. It is an **actual sampled outcome**, so it is internally
     consistent: a real ordering, with a real winner (X), and real per-player
     scores. "Most likely top-10 in which X wins" = the center of X's winning
     region, not a synthetic construction.
3. **Emit the scenario** from that medoid trial:
   - `films`: the 10 actual titles in finish order.
   - `grid`: for every player, the per-rank points they earn against this finish
     (length-10 list), via a scoring **breakdown** helper (below).
   - `totals`: every player's total for this finish (the breakdown sums, which
     equal the simulator's recorded trial scores for that trial).
   - `win_pct`: X's overall `win_prob` (for the tab and caption).
   - `margin`: X's total minus the runner-up's total in this finish.

### Why medoid, not mode or mean-rank

- **Exact-ordering mode fails:** with continuous samples, top-10 orderings are
  effectively unique, so the most-frequent exact ordering has a count of ~1 and
  is meaningless.
- **Per-rank marginal (most-frequent film per position) is incoherent:** it can
  place the same film in two positions or omit a film entirely, producing a
  "finish" that never occurred in any trial.
- **Medoid is a real trial** that is maximally typical of the winning set — the
  honest reading of "the most likely finish in which the player wins," and it
  hands the grid a consistent ordering + scores for free.

### Scoring breakdown helper

The grid needs each player's points **per film/rank**, which `score_player`
(returning only a total) does not expose. Add a sibling in `score/rules.py`:

```python
def score_breakdown(picks: PlayerPicks, top_titles: list[str]) -> list[int]:
    """Points each ranked finisher contributes for `picks`, indexed by actual
    position (len == len(top_titles)). Includes the +1 dark-horse bonus on the
    rank where a dark horse lands. sum(score_breakdown(...)) == score_player(...)."""
```

`score_player` should be refactored to delegate to (or be cross-checked against)
`score_breakdown` so the two can never drift.

### Cost bound

The medoid is O(W²·10) in the number of winning trials W (up to ~3,400 for the
current front-runner). To keep the build fast, if `W` exceeds a cap
(`MEDOID_SAMPLE_CAP = 1500`), compute the medoid over a **seeded random
subsample** of that size; the chosen medoid is still a real winning trial. This
is a deterministic, documented approximation — note it with a `ponytail:`
comment naming the cap and the upgrade path (full pairwise if it ever matters).

## Architecture

```
summer_movie_wager/score/rules.py        — add score_breakdown(); reuse it in score_player
summer_movie_wager/types.py              — add WinningScenario model
summer_movie_wager/model/simulate.py     — retain per-trial orderings + winners;
                                            compute winning_scenarios per player
summer_movie_wager/render/build.py                     — thread scenarios into data.json + RenderInput
summer_movie_wager/render/page.py                      — render the new page; write docs/scenarios.html
summer_movie_wager/render/templates/scenarios.html.j2  — NEW standalone Winning Scenarios page (from the mockup)
summer_movie_wager/render/templates/index.html.j2      — add a gated nav link to scenarios.html
```

`decay.py`, `preopening.py`, and the uncertainty-floor logic are untouched.

### Data flow

`SimulationResult` gains one field:

```python
winning_scenarios: dict[str, WinningScenario | None]
```

`WinningScenario` (new, frozen):

```python
class WinningScenario(BaseModel):
    films: list[str]                 # 10 actual titles, finish order #1..#10
    grid: dict[str, list[int]]       # username -> per-rank points (len 10)
    totals: dict[str, int]           # username -> total for this finish
    win_pct: float                   # X's overall win probability (0..100)
    margin: int                      # X total - runner-up total (>= 1)
```

`simulate_season` already builds `top_10_indices` (n_trials × 10) and `is_top`
(n_players × n_trials). Today both are discarded after aggregation; the change
**keeps** them long enough to run the medoid per player and assemble
`winning_scenarios`. No new sampling, no extra trials — pure post-processing of
data already in memory.

`build.py` adds `winning_scenarios` to the `raw` dict (→ `docs/data.json`) and to
`RenderInput`, exactly mirroring how `win_prob` is plumbed today, including the
"forecast unavailable" branch that emits explicit nulls.

The new `scenarios.html.j2` page embeds the scenarios as a JS const (same shape
the mockup's `DATA` uses: `{standing, win_prob, scenarios}`) and reuses the
mockup's tab/grid render logic and dark-mode toggle. `page.py` renders it to
`docs/scenarios.html` on every build. The page is self-contained — to avoid
fragile partial token-sharing it keeps the mockup's full inline `<style>`
(the theme tokens are duplicated from the main stylesheet, as they already are in
the committed mockup; a deliberate `ponytail:` simplification for a static
generated page). When `forecast_available` is false the page renders the gated
notice instead of the grid, and `index.html` omits the link to it.

### data.json schema addition

```json
"winning_scenarios": {
  "emsullivan": {
    "films": ["...", "... 10 titles in finish order ..."],
    "grid": {"emsullivan": [5,0,7,...], "carleigh": [...], "...": []},
    "totals": {"emsullivan": 63, "carleigh": 62, "...": 0},
    "win_pct": 33.6,
    "margin": 1
  },
  "radhadr": null
}
```

When `forecast_available` is false, emit `winning_scenarios` as
`{username: null}` for every player (consistent with the existing null-emitting
branch for `win_prob` et al.).

## Edge cases

- **No winning trials** (player's `win_prob == 0`): scenario is `null`; tab
  grayed/disabled; clicking is a no-op.
- **Ties for the win** in a trial are excluded from the winning subset (strict
  wins only), matching how `win_prob` is defined. A player who only ever *ties*
  (never strictly wins) has no scenario.
- **Forecast unavailable** (< 25 non-zero projections): no simulation runs, so no
  scenarios; the view shows the gated notice. `data.json` carries explicit nulls.
- **Single winning trial**: the medoid is that trial (distance set is empty); no
  special-casing needed.
- **Fewer than 10 films present**: cannot happen here — the simulator already
  raises below 10 projected movies, and the forecast gate (≥ 25) is stricter.

## Testing

- **`tests/test_score.py`** — `score_breakdown` sums to `score_player` across
  several fixtures (exact hits, off-by-k, dark-horse landing, picks absent from
  the top 10); breakdown length equals the actual-top-10 length.
- **`tests/test_simulate.py`** — with a small, hand-rigged set of players and
  projections and a fixed seed:
  - a player who can never win gets `winning_scenarios[user] is None`;
  - a player who can win gets a scenario whose `films` is length 10, whose
    `totals` make that player the strict max (`margin >= 1`), and whose `grid`
    rows sum (per player, down the column) to that player's `totals` value;
  - the medoid trial's per-player `totals` equal the scores the simulator
    recorded for that trial (internal consistency).
- **`tests/test_build.py`** — `raw["winning_scenarios"]` is present and
  well-formed when `forecast_available`, and is all-null when not.
- **`tests/test_render_snapshot.py`** — when forecast is available, `render`
  writes `scenarios.html` containing the grid markup and the embedded scenarios
  const, and `index.html` contains the `scenarios.html` link; when unavailable,
  `scenarios.html` shows the gated notice and `index.html` omits the link.
- **Determinism** — same seed ⇒ identical scenarios (medoid tie-break is
  deterministic: lowest trial index wins a distance tie).

## Verification

1. `uv run pytest` — all green.
2. `uv run python -m summer_movie_wager.render.build --local` — exits 0; inspect
   `docs/data.json`:
   - every player with `win_prob > 0` has a non-null `winning_scenarios` entry
     whose `films` has 10 titles and whose `totals` make that player the strict
     leader by `margin >= 1`;
   - every player with `win_prob == 0` (currently `radhadr`) has `null`;
   - per-player `grid` columns sum to the matching `totals`.
3. Open `docs/index.html`: confirm the "Winning Scenarios" link appears; follow
   it to `docs/scenarios.html`. There, tabs are ordered by win % with zero-chance
   players grayed; clicking a tab swaps the grid and re-sorts columns so the
   selected player is the crowned, left-most column. Confirm light/dark and
   mobile horizontal-scroll behave as in the mockup.
4. Confirm the rendered scenarios are **real** finishes (films vary per player,
   margins vary — *not* a uniform 1-point flip), demonstrating the medoid path
   replaced the mockup's placeholder heuristic.
