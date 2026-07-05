# summer-movie-wager

A tracker and forecaster for the 2026 **Summer Movie Wager** — a competition among 8 friends to predict which movies will gross the most at the domestic box office between **2026-04-30 and 2026-09-07**.

The official site ([thesummermoviewager.com](https://thesummermoviewager.com/index.php?year=2026&addPlayer=bclarke%2Cvivrad%2Czmeister%2Cbrettfern%2Ccarleigh%2Cradhadr%2Cemsullivan%2Cmhartje&playAlongOnly=)) shows current standings but nothing forward-looking. This project adds what the site doesn't: **projected final scores and per-player win probabilities**, refreshed on demand.

**Players:** bclarke, vivrad, zmeister, brettfern, carleigh, radhadr, emsullivan, mhartje

## What this is, architecturally

There is no server and no frontend build step. A Python batch pipeline scrapes the official site, projects each movie's final gross, runs a Monte Carlo simulation of the season, and renders three **static HTML pages** into `docs/`. GitHub Pages serves `docs/` directly from the `main` branch. The only JavaScript is small vanilla scripts inlined into the pages (theme toggle, and the interactive What If? sandbox); all CSS is inlined at build time too. The pages' only external requests are Google Fonts and, on the What If? page, the SortableJS drag-and-drop library from a CDN (pinned with an integrity hash).

## The game & scoring rules

Each player submits 10 ranked picks and 3 dark horses before the season. At the end of the window the top 10 domestic grossers (within the window) are ranked 1–10.

| Ranked pick outcome | Points |
|---|---|
| Exact match at #1 or #10 | 13 |
| Exact match at #2–#9 | 10 |
| In top 10, off by 1 position | 7 |
| In top 10, off by 2 positions | 5 |
| In top 10, off by 3+ positions | 3 |
| Not in top 10 | 0 |

Dark horses score 1 point each if they land in the top 10, 0 otherwise. The player with the most total points wins; ties share the placement (no tiebreaker).

## Quick start

This project uses [uv](https://docs.astral.sh/uv/), a fast Python package and environment manager that replaces the usual `pip` + `venv` workflow. `uv sync` creates a virtualenv in `.venv/` and installs the exact locked dependency versions from `uv.lock`; `uv run <cmd>` runs a command inside that environment without your having to activate anything.

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies (Python 3.12+, pinned in .python-version)
uv sync

# Build the site locally — scrapes the live wager site, runs the full
# pipeline, writes docs/*.html and docs/data.json. Does NOT append to
# the history files in data/.
uv run python -m summer_movie_wager.render.build --local

# View the result: open docs/index.html directly, or serve the folder
python3 -m http.server -d docs 8000   # → http://localhost:8000
```

The pages are plain static files, so opening `docs/index.html` straight from the filesystem works fine; the local server is only nicer for clicking between pages.

**Production build** (what the GitHub Action runs) is the same command without `--local`. The only difference: it also appends today's grosses to `data/box_office_history.jsonl` and today's forecast to `data/forecast_history.jsonl`. Don't run it casually — duplicate same-day history rows will skew the decay model's observed week-over-week calculation.

### Tests and linting

```bash
uv run pytest                 # 87 tests: scoring, decay math, scraper (offline
                              # fixture), simulator, HTML snapshot test
uv run ruff check .           # lint
uv run ruff format --check .  # formatting
```

## How the pipeline works

`summer_movie_wager/render/build.py` is the entry point and glue. One run does:

1. **Scrape** — `ingest/scraper.py` fetches the play-along page with [httpx](https://www.python-httpx.org/) (a modern requests-style HTTP client) and parses it with [selectolax](https://github.com/rushter/selectolax) (a fast HTML parser; think BeautifulSoup with less API and more speed). Produces a `SiteSnapshot`: every player's picks, each movie's cumulative gross so far, and the site's own reported points.

2. **Picks-drift guard** — `ingest/picks_guard.py` compares the freshly-scraped picks against the locked snapshot in `data/picks_snapshot_2026.yaml`. Any difference — a changed pick, a missing username, a renamed title — fails the build loudly. This protects against both upstream site changes and silent scraper regressions. (On the first-ever run the snapshot is bootstrapped from the scrape; to legitimately re-lock, delete the file and re-run.)

3. **Normalize** — `build.py` merges the scrape with `data/movies_overrides.yaml` (title aliases, category fixes, release-date corrections) into one typed `MovieRecord` per tracked title. All shared data models live in `types.py` as [pydantic](https://docs.pydantic.dev/) models — dataclass-style classes that validate their fields at runtime, so bad scraped data fails at the boundary instead of deep in the math.

4. **Project** — each movie gets a `(median_in_window_gross, sigma)` estimate from one of two models (details below): `model/decay.py` for movies already in theaters, `model/preopening.py` for unreleased movies with analyst estimates. Unreleased movies *without* analyst data get a projection of 0 and a "no projection" badge — there is deliberately no comparable-titles fallback; if there's no real data, there's no projection.

5. **Simulate** — `model/simulate.py` runs a 10,000-trial Monte Carlo season using [numpy](https://numpy.org/) (all trials vectorized as arrays; no Python-level loop over trials). Requires at least 25 movies with non-zero projections; below that the site shows current standings only, with a warning.

6. **Validate scoring** — the pipeline recomputes every player's *current* points with its own scoring engine (`score/rules.py`) and compares against the points the official site reports. A mismatch prints a loud warning — a free correctness check on every run.

7. **Render** — `render/page.py` renders three pages with [Jinja2](https://jinja.palletsprojects.com/) (HTML templating: templates in `render/templates/`, data in, HTML out). The shared nav bar and theme toggle (`_nav.html.j2`, `_theme.html.j2`) and the CSS files in `render/static/` (`style.css`, `nav.css`, `theme.css`, `shared.css`) are inlined into each page. Also writes `docs/data.json`, the full pipeline state as JSON.

8. **Append history** — production runs append one line per movie to `data/box_office_history.jsonl` and one line per player to `data/forecast_history.jsonl` (JSONL = one JSON object per line, append-only).

## The three pages

| Page | What it shows | Client-side JS |
|---|---|---|
| `docs/index.html` (Leaderboard) | Current standings, projected final points with 80% intervals, win odds, per-movie projections, every player's picks | Theme toggle only |
| `docs/scenarios.html` (Winning Scenarios) | For each player, the *most representative* season finish order in which they win — the medoid of their winning Monte Carlo trials under Spearman-footrule distance (i.e., the winning trial most similar to all their other winning trials) | Theme toggle only |
| `docs/whatif.html` (What If? sandbox) | A drag-to-reorder list of the top 15 projected movies; scores for all 8 players recompute live as you rearrange the hypothetical finish order | The scoring rules reimplemented in ~140 lines of vanilla JS, with the movie list and all picks embedded as JSON at build time |

## Projection models

### Mode A — in theaters (weekly-decay model)

For movies with a positive cumulative gross:

1. **Week-over-week (WoW) multiplier.** Default 0.55 for wide releases, 0.65 for animated/family. Once `data/box_office_history.jsonl` has ≥3 snapshots for a movie (enough for two week-over-week increments), the model blends the observed WoW (geometric mean of consecutive increment ratios) with the default, weighting the observed value more as snapshots accumulate — fully observed at 6 snapshots.
2. **Back-calibrate week-1 gross.** Solve for the week-1 gross that reproduces the actual cumulative total under geometric decay, anchoring projections to real earnings.
3. **Project remaining weeks** through 2026-09-07, handling partial weeks at both ends.
4. **Sigma (uncertainty)**: 0.30 just after opening, tapering linearly to 0.10 at ≥6 observed weeks.

### Mode B — pre-release (analyst estimates)

For unreleased movies with an entry in `data/preopening_projections.yaml`:

1. **Back out the implied WoW** from the analyst's opening-weekend and total-domestic estimates: `wow = 1 - (opening / total)` (the ratio at which a geometric series starting at the opening converges to the total). Falls back to the category default if outside (0, 1).
2. **Sum weekly grosses within the window**, from `release_date` through 2026-09-07, capped at the analyst total. Movies releasing after the window score 0 and get a "won't score" badge.
3. **Sigma by stated confidence**: `high` → 0.20, `med` → 0.30, `low` → 0.45.

### Monte Carlo simulation

Given `(median, sigma)` per movie, each of the 10,000 trials draws every movie's gross from `LogNormal(ln(median), sigma)`, ranks the top 10, and scores all players. Aggregated outputs: median final points, p10/p90 (an 80% prediction interval), P(strict win), P(tie for first), and each player's representative winning scenario.

## Repository layout

```
summer_movie_wager/            # the Python package
  types.py                     # shared pydantic models (SiteSnapshot, MovieRecord, ...)
  ingest/
    scraper.py                 # fetch + parse thesummermoviewager.com
    picks_guard.py             # snapshot-vs-scrape drift detection
  model/
    decay.py                   # Mode A: weekly-decay projection
    preopening.py              # Mode B: analyst-estimate projection
    simulate.py                # Monte Carlo → win odds, intervals, winning scenarios
  score/
    rules.py                   # the wager scoring engine
  render/
    build.py                   # entry point: end-to-end pipeline glue
    page.py                    # Jinja2 rendering of all three pages + data.json
    templates/                 # index / scenarios / whatif + shared _nav/_theme partials
    static/                    # style.css, nav.css, theme.css, shared.css — inlined at build time
data/                          # pipeline inputs + append-only history (see below)
docs/                          # BUILD OUTPUT, served by GitHub Pages — don't hand-edit
  index.html, scenarios.html, whatif.html, data.json
  superpowers/specs/, superpowers/plans/   # design docs for each feature, by date
  previews/                    # one-off styling mockups from the UI redesign
  .nojekyll                    # tells GitHub Pages to serve files as-is (no Jekyll)
tests/                         # pytest suite; fixtures/ holds a committed copy of the
                               # play-along page HTML so scraper tests run offline
```

Generated pages under `docs/` are committed on purpose — that's how GitHub Pages picks them up. Edit templates/CSS under `summer_movie_wager/render/` and rebuild; never edit `docs/*.html` directly.

## Data files

| File | Purpose |
|---|---|
| `data/picks_snapshot_2026.yaml` | Locked season picks, committed on first run. Every subsequent run validates the scrape against this — any drift fails loudly. |
| `data/preopening_projections.yaml` | Hand-curated analyst estimates for unreleased movies. **The main file to maintain through the season.** |
| `data/movies_overrides.yaml` | Patch file for title variants, wrong categories, and bad release dates from the scraper. |
| `data/box_office_history.jsonl` | Append-only log of `{movie, date, cumulative_gross}` per production run. Feeds observed-WoW blending in Mode A. |
| `data/forecast_history.jsonl` | Append-only log of per-player forecasts per production run. Available for a future "win odds over time" chart. |

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

The file contains commented-out placeholder blocks for the unreleased picks. To activate one: uncomment it, replace the `TODO` numbers with analyst estimates, set `confidence` (`high` = tight tracking range, `med` = moderate spread, `low` = rough guess), update `source`/`as_of`, then run a `--local` build and confirm the movie shows up in the projections table.

**Where to find estimates:** [Box Office Theory](https://boxofficetheory.com) is the primary source; Deadline and The Numbers also publish tracking. No professional tracking → use your own judgment with `confidence: low`.

### Fixing a title mismatch or wrong category

Edit `data/movies_overrides.yaml`:

```yaml
"Toy Story 5":
  category: animated_family        # use the family WoW default (0.65)

"Variant Title From Scraper":
  alias_of: "Canonical Title"      # merge a scraper variant into one title

"Title With Known Bad Release Date":
  release_date: 2026-07-10
  status: pre_release
```

## Deploying / refreshing the live site

The GitHub Action (`.github/workflows/refresh.yml`) is `workflow_dispatch`-only — no cron; refreshes are manual by design:

1. On GitHub: **Actions → Refresh site → Run workflow**.
2. The workflow installs dependencies with `uv sync --frozen`, runs the test suite, runs the production build, and commits any changes under `docs/` and `data/` back to `main`.
3. GitHub Pages serves `docs/` from `main`; the updated site is live within a couple of minutes.

## Conventions

- **Python 3.12+** (`.python-version` pins 3.12; `uv` installs it automatically).
- **Formatting/linting**: [ruff](https://docs.astral.sh/ruff/) (both linter and formatter — a faster replacement for flake8 + isort + black), line length 100, rule sets `E, F, I, B, UP, RUF` in `pyproject.toml`.
- **Types**: pydantic models for anything that crosses a module boundary; enums for statuses/categories.
- **Tests**: plain pytest. The scraper is tested against a committed HTML fixture (no network in tests), and the rendered leaderboard has a hand-rolled snapshot test that diffs the full HTML output against `tests/fixtures/expected_index.html` (bootstrapped from the first run, byte-compared thereafter).
- **Modeling philosophy**: honest defaults over speculation. No projection is invented for a movie without either real box-office data or a sourced analyst estimate.

## Wager window

`2026-04-30` through `2026-09-07` (inclusive). Movies releasing after 2026-09-07 are shown with a "won't score" badge and get `projected_gross = 0`.
