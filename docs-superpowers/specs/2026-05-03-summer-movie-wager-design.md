# Summer Movie Wager 2026 — Tracker & Forecaster — Design

**Status:** Approved 2026-05-03

## Context

Eight friends — `bclarke`, `vivrad`, `zmeister`, `brettfern`, `carleigh`, `radhadr`, `emsullivan`, `mhartje` — are playing the Summer Movie Wager (rules: <https://thesummermoviewager.com/help.php>) for the 2026 summer window: **2026-04-30 through 2026-09-07**. Each player has locked in 10 ranked picks and 3 dark horses. All picks for the group are publicly visible at the play-along URL on `thesummermoviewager.com`, which also computes current standings from cumulative domestic box office to date.

**Why build a separate app:** the published site shows *current* points but not *projected final* points or *win probability*. This project's value-add is forecasting — projecting each picked movie's domestic gross during the wager window (using a weekly decay model for in-theaters movies and human-curated analyst estimates for pre-release movies) and running a Monte Carlo simulation to produce per-player win odds and prediction intervals.

**Outcome:** A static GitHub Pages site, refreshed on-demand via a manually-triggered GitHub Action. Friends bookmark a URL; `bclarke` clicks "Run workflow" to refresh. No accounts, no database, no server.

## Wager scoring rules (canonical)

For each of a player's 10 ranked picks vs. the final top-10-by-domestic-gross-in-window:

| Outcome | Points |
| --- | --- |
| Correct #1 or #10 placement | 13 |
| Correct #2–#9 placement | 10 |
| Off by 1 position | 7 |
| Off by 2 positions | 5 |
| In top 10 but off by 3+ | 3 |
| Not in top 10 | 0 |

For each of a player's 3 dark horses:

| Outcome | Points |
| --- | --- |
| In top 10 | 1 |
| Not in top 10 | 0 |

Winner = highest total. Ties share the placement (no tiebreaker).

## Architecture

A Python package builds a static site. Pipeline stages, each independently runnable:

### 1. Ingest

Scrape `https://thesummermoviewager.com/index.php?year=2026&addPlayer=bclarke,vivrad,zmeister,brettfern,carleigh,radhadr,emsullivan,mhartje&playAlongOnly=` once per run. Parse out:

- All 8 players' picks (10 ranked + 3 dark horses each), keyed by stable anchor IDs of the form `id="a_<username>"`.
- Per-movie cumulative in-window box office to date.
- The site's reported per-player current points (used to validate our scoring engine — divergence fails the run).

**Picks-drift guard.** On the very first run of the season, scraped picks are persisted to `data/picks_snapshot_2026.yaml` and committed. On every subsequent run, the freshly-scraped picks are compared against the snapshot — any divergence (someone's picks changed on the site, or our parser broke) fails the run loudly. The snapshot is the canonical source of truth for the season; the scrape is validation.

Resilience: persist a committed HTML fixture (`tests/fixtures/playalong.html`) for offline parser tests; refresh the fixture whenever the parser is updated.

### 2. Normalize

Each movie becomes a typed Pydantic record: `title`, `release_date`, `status` (`pre_release` | `in_theaters` | `closed`), `category` (`wide` | `animated_family`, default `wide`), `cumulative_gross_in_window`, `source`. A `data/movies_overrides.yaml` file lets `bclarke` patch scraper drift (renamed titles, shifted release dates) and tag movies into the `animated_family` bucket — anything not listed defaults to `wide`. `category` is the single switch that selects between the wide and animated-family parameters used in Mode A (decay multiplier) and Mode B (first-weekend ratio).

### 3. Project

Two modes that produce the same output shape — `(median_in_window_gross, sigma)` per movie:

**Mode A — In-theaters (weekly-decay model).** For movies with `status == in_theaters`:

- Default week-over-week multipliers: **0.55** for wide live-action releases, **0.65** for animated/family. (Empirically these hold up better mid-summer than a single global value.)
- Calibrate `week_1_gross` so the modeled cumulative-to-date matches the scraped cumulative-to-date.
- Once `data/box_office_history.jsonl` accumulates ≥2 snapshots for a movie, blend the default WoW multiplier with the observed WoW. Shrinkage rule: 50/50 weight at 2 data points, shifting linearly toward observed as more snapshots arrive (full observed weight at 6+ snapshots).
- Sum modeled weekly grosses from today through 2026-09-07; add to cumulative-to-date for the projected total in-window gross.
- σ ranges from **0.10** (≥6 weeks observed) to **0.30** (just opened), interpolated linearly.

**Mode B — Pre-release (analyst estimate).** For movies with `status == pre_release`, a hand-curated `data/preopening_projections.yaml` file:

```yaml
spider_man_brand_new_day:
  release_date: 2026-07-31
  opening_weekend_estimate: 145000000
  total_domestic_estimate: 410000000
  confidence: high          # high | med | low
  source: "Box Office Pro long-range, 2026-04-15"
  as_of: 2026-04-15
  notes: "Trending up after CinemaCon footage."
```

Conversion to `projected_in_window_gross`:

1. From `opening_weekend_estimate` and a default first-weekend-to-total ratio (~28% wide, ~22% animated/family), back out an implied weekly schedule consistent with `total_domestic_estimate`.
2. Sum modeled weekly grosses falling between `release_date` and 2026-09-07 (truncates correctly for late-August openings).
3. If `release_date > 2026-09-07`: `projected_in_window_gross = 0`, with a UI badge ("won't score — delayed past window").

σ by `confidence`: high → 0.20, med → 0.30, low → 0.45.

**Fallback for missing entries.** Any picked movie that is `pre_release` and missing from `preopening_projections.yaml` gets `projected_in_window_gross = 0` and a "no projection — assumed not to score" badge. *No comparable-titles modeling — explicitly excluded as too hand-wavy.*

### 4. Score & simulate

Given per-movie `(median, sigma)` for every tracked movie:

- **Current scoring:** apply the wager rules to current actuals (top 10 sorted by `cumulative_gross_in_window`). Output: per-player current points. Validate against the site's reported standings.
- **Monte Carlo:** draw **10,000** samples per movie from `Lognormal(ln(median), sigma)`. For each sample-universe: rank movies by simulated in-window gross, take the top 10, apply wager rules to each player's picks. Aggregate across trials → per player: median final points, p10/p90 (80% prediction interval), `P(strictly highest score)`, `P(tied for highest score)`. The two probabilities are reported separately to honor the no-tiebreaker rule.

10k × 30 movies × 8 players is sub-second in NumPy; no optimization needed.

### 5. Render

Jinja2 templates → static HTML/CSS into `docs/`:

- `docs/index.html` — the single page.
- `docs/data.json` — full snapshot (every input, every projection, every score) so anyone can inspect raw numbers and so the file can drive future client-side enhancements.

Each run also appends rows to:

- `data/box_office_history.jsonl` — `{movie, date, cumulative_gross}`. Powers the calibration in Mode A.
- `data/forecast_history.jsonl` — `{date, player, win_prob, median_final_pts, p10, p90}`. Enables a future "win odds over time" chart without pipeline changes.

## Output / UI

Single page, no nav. Three stacked sections, top-to-bottom; the headline section fits above the fold on a phone.

### 3a — Headline leaderboard

Ranked by **projected median final score**. One row per player. Columns:

- Current points
- Projected median final score
- 80% range `[p10 – p90]`
- Win odds (% chance of strictly highest) with a tooltip showing tie odds

### 3b — Movie-by-movie projection table

Sorted by projected median in-window gross descending. One row per tracked movie. Columns:

- Title, release date, status badge (`in theaters` / `pre-release` / `won't score` / `no projection`)
- Projected median in-window gross + 80% range
- Cumulative actual to date (if applicable)
- Source-of-projection chip (e.g., `decay model · 4 wks observed` or `Box Office Pro 2026-04-15 · high confidence`)
- A row of 8 dots — one per player — showing where each player ranked the movie. Special marker for dark horses. Lets you scan and see "Spider-Man: Brand New Day projected #1, picked #1 by 6 players, #2 by 1, #3 by 1."

### 3c — Per-player detail (collapsible cards)

Click a leaderboard row → expand to show:

- All 13 picks (10 ranked + 3 dark horses), each with: projected final ranking, projected in-window gross, current points contribution, projected median points contribution.
- "Single biggest swing" — the pick whose outcome will move the player's final score the most (highest variance × scoring sensitivity).

### Visual treatment

Plain HTML + minimal CSS, no JS framework. One small inline `<script>` for click-to-expand on the player rows; everything else server-rendered Jinja2. Monospace numbers, dense tables, dark-mode-friendly defaults. Mobile-first.

## Repo layout

```
summer_movie_wager/
  ingest/                             # site scraper (httpx + selectolax)
  model/                              # decay model + Monte Carlo (numpy)
  score/                              # wager rules engine
  render/                             # Jinja2 templates → docs/
data/
  picks_snapshot_2026.yaml            # locked picks (committed once, validated each run)
  preopening_projections.yaml         # human-curated analyst estimates
  movies_overrides.yaml               # manual scraper-drift corrections
  box_office_history.jsonl            # append-only per-run snapshots
  forecast_history.jsonl              # append-only win-odds snapshots
docs/
  index.html                          # GitHub Pages entry point
  data.json                           # full snapshot for inspection
  superpowers/
    specs/
      2026-05-03-summer-movie-wager-design.md   # this file
.github/workflows/refresh.yml         # workflow_dispatch only — no cron
tests/
  fixtures/
    playalong.html                    # offline scraper fixture
pyproject.toml                        # uv-managed
```

## Stack

- **Python 3.12+** managed with **uv**.
- Dependencies: `httpx` (HTTP), `selectolax` (HTML parsing — faster than BeautifulSoup), `pydantic` (typed models), `numpy` (Monte Carlo), `jinja2` (templates), `pytest`, `ruff`.
- No web framework, no database, no JavaScript framework.

## Critical files (to be created during implementation)

- `summer_movie_wager/ingest/scraper.py` — fetch + parse the play-along URL into typed picks, per-movie cumulative gross, and site-reported standings.
- `summer_movie_wager/model/decay.py` — Mode A weekly-decay projection.
- `summer_movie_wager/model/preopening.py` — Mode B analyst-estimate projection.
- `summer_movie_wager/model/simulate.py` — Monte Carlo orchestrator; returns per-player distributions and win odds.
- `summer_movie_wager/score/rules.py` — wager scoring engine (single function: `score_player(picks, top_10) -> int`).
- `summer_movie_wager/render/build.py` — pipeline glue; calls ingest → normalize → project → simulate → render.
- `summer_movie_wager/render/templates/index.html.j2`.
- `data/picks_snapshot_2026.yaml`, `data/preopening_projections.yaml`, `data/movies_overrides.yaml`.
- `.github/workflows/refresh.yml`.
- `tests/test_scoring.py`, `tests/test_decay.py`, `tests/test_preopening.py`, `tests/test_scraper.py`, `tests/test_render_snapshot.py`.

## Testing

- **Scoring engine:** unit tests against hand-constructed player/top-10 scenarios covering every rule branch (13 / 10 / 7 / 5 / 3 / 0 / 1).
- **Decay model:** given a known cumulative-to-date and release date, modeled remaining-window gross matches a hand-computed value within 1%.
- **Pre-release converter:** sum of modeled weekly grosses equals `total_domestic_estimate` within rounding.
- **Render:** snapshot test diffing the rendered HTML against a fixed fixture.
- **Live validation (most important):** every workflow run, scrape current standings from the site and assert our scoring engine produces the same per-player current points. Mismatch fails the run loudly. This is the single best regression check we have.
- **Scraper offline:** parse a committed `tests/fixtures/playalong.html` so CI doesn't require network access.

## Verification (end-to-end)

1. `uv run pytest` — all green; live-standings validation passes against a freshly scraped page.
2. `uv run python -m summer_movie_wager.render.build --local` — produces `docs/index.html` and `docs/data.json` locally without committing.
3. Open `docs/index.html` in a browser. The "current points" column must match the site's reported current standings exactly. Projected medians ordering should roughly match intuition (Spider-Man: Brand New Day, Toy Story 5, Moana, The Odyssey leading).
4. Push to `main`; trigger `.github/workflows/refresh.yml` via GitHub UI ("Run workflow"). Confirm `docs/` is updated and GitHub Pages serves the new content within ~2 minutes.
5. Add a fake entry to `data/preopening_projections.yaml` with an absurdly high `total_domestic_estimate`; rerun build; confirm the leaderboard and projection table reflect the change. Revert.

## Operations

- `.github/workflows/refresh.yml` — `on: workflow_dispatch` only (no cron). Steps: install via `uv` → ingest → score+project → render → commit `docs/` if changed → push. GitHub Pages serves from `docs/` on `main`.
- No secrets required initially (the site is public).
- Local development: `uv run python -m summer_movie_wager.render.build --local` runs the full pipeline against the local filesystem with no commit. Fast inner loop.
- History files (`box_office_history.jsonl`, `forecast_history.jsonl`) are committed each run. Worst case after 130 days these files are still measured in kilobytes — no concern.

## Out of scope (deliberate, per YAGNI)

- No accounts, auth, or per-friend logins (read-only public site).
- No editing picks in-app (picks are scraped from the play-along URL each run).
- No comparable-titles fallback for unknown movies (explicitly cut for being too hand-wavy).
- No notifications, no historical season re-analysis, no chart UI in v1. (`forecast_history.jsonl` exists so a "win odds over time" chart can be added later without pipeline changes.)
- No real-time refresh — explicitly `workflow_dispatch`-only.
