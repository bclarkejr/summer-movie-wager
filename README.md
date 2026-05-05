# summer-movie-wager

A tracker and forecaster for the 2026 Summer Movie Wager — a competition among 8 friends picking which movies will gross the most domestic box office between 2026-04-30 and 2026-09-07.

The official site ([thesummermoviewager.com](https://thesummermoviewager.com/index.php?year=2026&addPlayer=bclarke%2Cvivrad%2Czmeister%2Cbrettfern%2Ccarleigh%2Cradhadr%2Cemsullivan%2Cmhartje&playAlongOnly=)) shows current standings but nothing forward-looking. This project adds what the site doesn't: projected final scores and per-player win probabilities, refreshed on demand.

**Players:** bclarke, vivrad, zmeister, brettfern, carleigh, radhadr, emsullivan, mhartje

## Scoring rules

Each player submits 10 ranked picks and 3 dark horses before the season. At the end of the window the top 10 domestic grossers (within window) are ranked 1–10.

| Ranked pick outcome | Points |
|---|---|
| Exact match at #1 or #10 | 13 |
| Exact match at #2–#9 | 10 |
| In top 10, off by 1 position | 7 |
| In top 10, off by 2 positions | 5 |
| In top 10, off by 3+ positions | 3 |
| Not in top 10 | 0 |

Dark horses score 1 point each if they land in the top 10, 0 otherwise. The player with the most total points wins; ties share the placement (no tiebreaker).

## Pipeline overview

```
fetch_snapshot()          ← scrape thesummermoviewager.com
     ↓
picks_guard               ← assert picks haven't drifted from locked snapshot
     ↓
_normalize_movies()       ← build typed MovieRecord for every tracked title
     ↓
_project_all()            ← Mode A (decay) or Mode B (analyst) per movie
     ↓
simulate_season()         ← 10,000-trial Monte Carlo → win odds + score distributions
     ↓
render()                  ← Jinja2 → docs/index.html + docs/data.json
     ↓
_append_history()         ← append to box_office_history.jsonl + forecast_history.jsonl
```

## Projection logic

### Mode A — in-theaters (weekly-decay model)

Used for movies where `status == in_theaters` (have a positive cumulative gross).

1. **Determine week-over-week (WoW) multiplier.** Default is 0.55 for wide releases and 0.65 for animated/family. Once `data/box_office_history.jsonl` has ≥2 snapshots for the movie, the model blends observed WoW (geometric mean of consecutive gross increments) with the default. Weight shifts linearly from 50/50 at 2 data points to full observed weight at 6+ snapshots.

2. **Back-calibrate week_1_gross.** Given the scraped cumulative gross to date and the WoW multiplier, solve for the week-1 gross that would produce exactly that cumulative total under the geometric-decay model. This anchors projections to actual earnings rather than forecasts.

3. **Project remaining weeks.** Sum modeled weekly grosses from today through 2026-09-07, handling partial weeks at both the current point and the window end. Add to the existing cumulative total.

4. **Sigma (uncertainty).** Ranges from 0.30 (just opened, ≤0 weeks observed) down to 0.10 (≥6 weeks observed), interpolated linearly.

### Mode B — pre-release (analyst estimates)

Used for movies where `status == pre_release` and an entry exists in `data/preopening_projections.yaml`.

1. **Back out implied WoW.** From `opening_weekend_estimate` and `total_domestic_estimate`, compute the implied WoW multiplier via the formula `wow = 1 - (opening / total)`. This is the ratio at which a geometric series with week-1 = opening converges to the analyst's total. If the result is outside (0, 1), fall back to the category default (0.55/0.65).

2. **Sum grosses within window.** Run the same weekly summation as Mode A but starting at `release_date` and running through 2026-09-07. Capped at `total_domestic_estimate`. Returns 0 if the movie releases after the window ends.

3. **Sigma by confidence.** `high` → 0.20, `med` → 0.30, `low` → 0.45.

Movies that are `pre_release` but missing from `preopening_projections.yaml` get `projected_gross = 0` and a "no projection" badge. No comparable-titles fallback is used — if there's no analyst data, there's no projection.

### Monte Carlo simulation

Given a `(median_in_window_gross, sigma)` pair for every tracked movie, the simulator:

1. Draws 10,000 independent samples per movie from `LogNormal(ln(median), sigma)`.
2. For each trial: ranks movies by simulated gross, takes the top 10, applies scoring rules to every player's picks.
3. Aggregates across trials to produce: median final points, p10/p90 (80% prediction interval), P(strictly highest score), P(tied for highest score).

The simulation requires at least 10 non-zero projections to run. If fewer are available, the site shows current standings only with a warning.

## Running the pipeline

### Prerequisites

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync
```

### Local build (no commit, no network write)

```bash
uv run python -m summer_movie_wager.render.build --local
```

This scrapes the live site, runs the full pipeline, and writes `docs/index.html` and `docs/data.json`. It does **not** append to the history files. Open `docs/index.html` in a browser to review.

### Production build (appends history)

```bash
uv run python -m summer_movie_wager.render.build
```

Same as above but also appends today's grosses to `data/box_office_history.jsonl` and today's win-odds snapshot to `data/forecast_history.jsonl`. This is what the GitHub Action runs.

### Tests

```bash
uv run pytest
```

Tests cover: scoring rules, decay model math, pre-release converter, scraper (against an offline HTML fixture), and a snapshot test for the rendered HTML.

### Linting

```bash
uv run ruff check .
uv run ruff format --check .
```

## Updating projections

### Adding or updating a pre-release movie

Edit `data/preopening_projections.yaml`. Each entry follows this schema:

```yaml
"Movie Title":
  release_date: YYYY-MM-DD
  opening_weekend_estimate: 95000000   # dollars
  total_domestic_estimate: 220000000   # dollars
  confidence: high | med | low
  source: "Source name + date"
  as_of: YYYY-MM-DD
  notes: "Freeform context"
```

The file already contains commented-out placeholder blocks for all 26 unreleased picks. To activate one:
1. Uncomment the block.
2. Replace the `TODO` numbers with analyst estimates from Box Office Pro, Deadline, or another source.
3. Set `confidence` appropriately: `high` if the tracking range is tight, `med` if there's moderate spread, `low` if it's a rough guess.
4. Update `source` and `as_of`.
5. Run `uv run python -m summer_movie_wager.render.build --local` and check that the movie appears in the projections table.

**Where to find estimates:** Box Office Theory ([boxofficetheory.com](https://boxofficetheory.com)) is the primary source. Deadline and The Numbers often publish tracking. If no professional tracking exists, use your own judgment and set `confidence: low`.

### Fixing a title mismatch or wrong category

If the scraper returns a different title than what's in `preopening_projections.yaml`, or a movie should be treated as `animated_family` rather than `wide`, edit `data/movies_overrides.yaml`:

```yaml
"Toy Story 5":
  category: animated_family

"Variant Title From Scraper":
  alias_of: "Canonical Title"

"Title With Known Bad Release Date":
  release_date: 2026-07-10
  status: pre_release
```

The `alias_of` key merges a scraper variant into the canonical title so projections and grosses stay unified.

### History-based calibration (box_office_history.jsonl)

Once a movie has been in theaters for a couple weeks, the decay model blends the default WoW with the observed one. This file is append-only and grows automatically each time the production build runs (without `--local`). You don't need to touch it manually.

## Triggering a refresh

The GitHub Action at `.github/workflows/refresh.yml` is `workflow_dispatch`-only (no cron). To refresh the live site:

1. Go to the repo on GitHub → **Actions** → **Refresh site** → **Run workflow**.
2. The workflow: installs dependencies via `uv`, runs tests, runs the build, and commits any changes to `docs/` and `data/` back to `main`.
3. GitHub Pages serves from `docs/` on `main`; the updated site is live within ~2 minutes of the commit.

## Data files

| File | Purpose |
|---|---|
| `data/picks_snapshot_2026.yaml` | Locked season picks, committed on first run. Every subsequent run validates the scrape against this — any drift fails loudly. |
| `data/preopening_projections.yaml` | Hand-curated analyst estimates for unreleased movies. The main file to maintain through the season. |
| `data/movies_overrides.yaml` | Patch file for title variants, wrong categories, and bad release dates from the scraper. |
| `data/box_office_history.jsonl` | Append-only log of `{movie, date, cumulative_gross}` from each production run. Feeds observed-WoW blending in Mode A. |
| `data/forecast_history.jsonl` | Append-only log of `{date, player, win_prob, median_final_pts, p10, p90}` from each production run. Available for a future "win odds over time" chart. |

## Output files

| File | Purpose |
|---|---|
| `docs/index.html` | The public GitHub Pages site — leaderboard, movie projections, per-player pick details. |
| `docs/data.json` | Full pipeline snapshot: all inputs, projections, scores, and simulation results in JSON. Useful for debugging and future enhancements. |

## Source layout

```
summer_movie_wager/
  ingest/
    scraper.py          # fetch + parse thesummermoviewager.com
    picks_guard.py      # snapshot-vs-scrape drift detection
  model/
    decay.py            # Mode A: weekly-decay projection for in-theaters movies
    preopening.py       # Mode B: analyst-estimate projection for pre-release movies
    simulate.py         # Monte Carlo → win probabilities + score distributions
  score/
    rules.py            # wager scoring engine
  render/
    build.py            # end-to-end pipeline glue
    page.py             # Jinja2 render helpers and data classes
    templates/
      index.html.j2     # single-page site template
    static/
      style.css         # inlined into the page at build time
  types.py              # shared Pydantic models
data/                   # see Data files above
docs/                   # see Output files above
tests/
  fixtures/
    playalong.html      # committed HTML fixture for offline scraper tests
```

## Picks-drift guard

On the first-ever run, the scraper's output is written to `data/picks_snapshot_2026.yaml` and committed. Every run after that compares the freshly-scraped picks to the snapshot. Any difference — a pick changed on the site, a username missing, a title renamed — fails the build with a clear error message. This protects against both upstream site changes and silent scraper regressions.

If a legitimate picks change occurs (unlikely mid-season), delete `data/picks_snapshot_2026.yaml` and re-run to rebootstrap.

## Wager window

`2026-04-30` through `2026-09-07` (inclusive). Movies releasing after 2026-09-07 are shown with a "won't score" badge and get `projected_gross = 0`.
