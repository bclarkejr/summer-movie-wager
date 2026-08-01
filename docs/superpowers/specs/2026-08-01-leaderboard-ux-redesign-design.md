# Leaderboard page UX redesign

**Date:** 2026-08-01
**Status:** Approved design, ready for implementation planning
**Scope:** `docs/index.html` (the "Leaderboard" page) and the code that renders it

## Problem

The current `index.html` answers "who is winning" but not "why." It has three sections:

1. A leaderboard table — one row per player: current points, projected median, 80% range, win odds.
2. A movies table — every projected film, always expanded, ~37 rows of scrolling.
3. Per-player detail — an accordion of `<ol>`/`<ul>` bullet lists.

The gap: nothing shows *which film is earning whom what*. To learn that Spider-Man is worth 13
points to five players and 3 to another, a reader has to open six accordions and hold the numbers
in their head. The bullet lists don't align, so nothing can be compared across players. And a
player can't see anyone else's list without expanding it.

`docs/previews/index-option-1.html` is a hand-built mockup, populated with real 2026-08-01 data,
that fixes this. It is the exact specification for the target UX. This document describes what has
to change behind it.

## The target UX

Four sections, in order.

### 1. Projected Standings (`.matrix`)

A movie × player matrix. Rows are the top 15 projected films (rank, title, projected median
gross); columns are players in standing order. Each cell is what that film contributes to that
player's score:

- a green value when it scores,
- a grey `0` when the film is on their list but projects outside the top 10,
- a muted `—` when they didn't pick it at all.

A dashed `Outside the top 10` divider sits after row 10, so the scoring boundary is visible. Two
footer rows carry each player's projected points and win odds.

This replaces the old leaderboard table outright. Current points and the 80% range move out of the
top-level view — current points reappear in the per-player stats line, the range is dropped.

**Why top 15, fixed:** the divider needs rows on both sides to mean anything, and 15 gives five
films of "just missed" context. Showing every film any player picked would push the table past 22
rows today and make its height wobble week to week. Deep picks (radhadr's Animal Farm at #31) stay
visible in that player's own detail table. This is the same slice the What If? page already takes.

### 2. All Players' Lists (`.picks`)

New section. A pick-position × player grid: rows `Pick 1`–`Pick 10`, a `Dark Horses` divider, then
`🐴 Dark Horse 1`–`3`. Every player's full list, side by side, no clicking. The picks are public
and locked, so there is nothing to hide.

### 3. Per-player detail (`.players`)

The same accordion, but each player's bullet lists become a table: `#`, `Movie`,
`Projected rank`, `Diff`, `Projected gross`, `Pts`. Dark horses follow a `Dark Horses` divider row
inside the same table.

**Diff** is the new information: `pick position − projected rank`, rendered `▲ 2` (green) when the
projection has moved a film above where the player ranked it, `▼ 2` (red) below, `–` when it landed
exactly. It turns a static list into a read on how each player's bet is moving.

A stats line under each summary carries `N pts projected · N pts current · N% win`.

### 4. Movies (`.movies`)

Same content, now numbered and collapsed behind a `<details>` toggle. It is reference data, not
the headline, and 37 always-expanded rows were burying section 3.

## Design decisions

### Projected points = the sum of the column

The footer `Projected pts` row is the arithmetic sum of the cells above it, not the Monte Carlo
median the old leaderboard showed. These disagree — emsullivan's simulated median is 62 while the
median-scenario cells sum to 63, because a distribution median is not the median scenario's score.

That discrepancy was invisible when the two numbers lived in different sections. With the
components sitting directly above the total, a table that doesn't add up reads as a bug. The
column sum wins.

The same total appears in each player's stats line, so the two places a player's projected score
appears always agree.

Consequence, accepted: columns stay ordered by the *simulated* median (the ranking the win odds are
derived from, and the ordering scenarios.html and whatif.html already use), so a column can rarely
display a total a point higher than the column to its left. Re-sorting by the displayed total would
desync index ordering from the other two pages — a worse inconsistency for a rarer payoff. This
gets a one-line comment at the site where the total is computed.

### Ranks are catalog ranks

`PickDetail.projected_rank` is currently the film's position within the projected top 10, and
`None` for everything else. The new per-player table shows `#31` and `#37`, i.e. position across
all projected films — the same number the Movies table prints in its `#` column.

The field is repurposed rather than joined by a second one, so exactly one notion of "projected
rank" exists in the codebase. Scoring is untouched: points still come from the top-10 position map.

### Medals are dropped

The 🥇🥈🥉 that CSS attached to the top three leaderboard rows go away with the table they
decorated. Standing is legible from left-to-right column order.

## Architecture

No change to the shape of the system: a Python batch pipeline renders static HTML into `docs/`,
CSS inlined at build time, no server and no frontend build step. The projection and simulation
models are not touched. The work is confined to the render layer.

### Components

| Unit | Responsibility | Changes |
|---|---|---|
| `build.py` | Pipeline; assembles `RenderInput` from model output | Rank semantics, one new field |
| `page.py` | Owns the render dataclasses; renders templates to files | One new field, one derived lookup |
| `templates/index.html.j2` | Index markup | Rewritten body |
| `static/style.css` | Index-only styling | Rewritten to the preview's rules |
| `static/theme.css` | Shared theme tokens (all four pages) | Two tokens added |

`nav.css`, `shared.css`, `_nav.html.j2`, `_theme.html.j2`, and the scenarios/whatif/history
templates are untouched. `shared.css` keeps its 1000px page shell; only the index widens to 1360px
to fit the matrix.

### Data flow

```
projections ─┐
             ├─> _build_movie_rows ──> movie_rows ─┬─> RenderInput.movies ──> matrix rows,
snapshot ────┘                                     │                          movies table
                                                   │
                                                   └─> catalog_rank {title: N}
                                                            │
snapshot.players ──> _build_player_details <────────────────┘
                            │
                            └─> PlayerDetail[] ──> RenderInput.player_details
                                                        │
                                    ┌───────────────────┼───────────────────┐
                                    v                   v                   v
                            matrix columns        picks grid        per-player tables
                                    │
                            page.py: pts_by_player
                            {username: {title: pts}}
```

Three properties this shape buys:

**One ordered list drives every player-facing section.** The matrix columns, the picks grid, and
the accordion all iterate `player_details`. They cannot fall out of order with each other. This
requires `win_prob` on `PlayerDetail` (today it lives only on `LeaderboardRow`); adding it lets the
index template stop reading `leaderboard` entirely. `leaderboard` stays exactly as it is, feeding
the scenarios, whatif, and history payloads.

**Ranks are derived, never recomputed.** `catalog_rank` comes from the already-built `movie_rows`
list, so the rank in a player's detail table is the same integer the Movies table prints. There is
no second sort that could drift from the first.

**The matrix needs one derived structure.** `page.py` builds
`{username: {title: projected_pts}}` from each `PlayerDetail`'s picks. Cell rendering is then a
dictionary lookup: present and positive → scoring, present and zero → grey, absent → `—`.

## Error handling and edge cases

The render layer's failure mode is a page that silently renders wrong, so the cases that matter are
degenerate inputs rather than exceptions.

- **No forecast.** When fewer than 25 films have non-zero projections, `sim` is `None`, so
  `win_prob` and `median_pts` are `None` and the existing `forecast-unavailable` notice must render
  — it moves from the old leaderboard section into the matrix section. Win-odds cells show `—`. The
  matrix itself still works: projected grosses exist regardless of the simulation.
- **Empty `player_details`.** Two existing tests render with no players. The picks grid computes
  its row count with a `max` filter over player lists, which raises on an empty sequence — it must
  be guarded so the section renders empty rather than blowing up the build.
- **Fewer than 10 movies.** The `Outside the top 10` divider is emitted only when rows follow it.
- **A pick missing from the movie catalog.** `_normalize_movies` guarantees every picked title
  appears in `movies`, so `catalog_rank` should always hit — but the Diff cell arithmetic would
  fail on a `None` rank, so it renders a muted `—` in that case rather than trusting the invariant.
- **Hostile scraped strings.** Jinja autoescape is forced on unconditionally in `page.py` because
  titles and sources come from external scrapes. The new sections render the same scraped fields
  and inherit this; the existing escaping test must keep passing.

## Testing

The page is verified by a byte-exact snapshot (`tests/fixtures/expected_index.html`) plus targeted
assertions. The snapshot must be regenerated, which is a deliberate step, not a formality: delete
it, run pytest once (it rewrites the fixture and fails by design), **open the result in a browser
and compare it against the preview**, then re-run to lock it.

- The snapshot fixture currently has two leaderboard rows but one `PlayerDetail`, which would
  render a single-column matrix and prove nothing. Add a second player, with picks overlapping the
  fixture's movies, so the snapshot covers a scored cell, a zero cell, and a `—` cell.
- New assertions: a movie no player picked renders `—`; the footer `Projected pts` cell equals the
  sum of that player's `projected_pts`.
- The existing escaping, nav, theme-token, scenarios, whatif, and history tests must all still pass
  — several of them render the index with empty player lists, which is the degenerate-input check.

End-to-end verification is a real build against live data:

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run python -m summer_movie_wager.render.build --local
python3 -m http.server -d docs 8000
```

Then compare `docs/index.html` against `docs/previews/index-option-1.html` side by side: cell
values and `—`s, the divider position, footer totals adding up, Diff arrows and colors, the
collapsed Movies section, both themes via the toggle, and the ~700px breakpoint.

Two operational notes: `docs/*.html` and `docs/data.json` have uncommitted local edits that the
build overwrites, and the build must use `--local` — a production run appends a duplicate same-day
row to `data/box_office_history.jsonl` and skews the decay model.

## Out of scope

`scenarios.html`, `whatif.html`, `history.html`; the projection and simulation models; the scraper;
and the mockups in `docs/previews/`, which stay until their author says otherwise.
