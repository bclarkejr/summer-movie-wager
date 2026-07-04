# What If? Sandbox — Drag-and-Drop Top-10 Explorer

**Status:** Approved 2026-07-03

## Context

The leaderboard answers "who is winning now" and the Winning Scenarios page
answers "what single finish crowns player X." Neither lets a visitor *explore*:
*"if the top 10 landed in **this** order, who would win?"*

This feature adds a **What If?** sandbox: a third page where a visitor drags the
**top 15 projected movies** into any hypothetical **top-10 finish order** and
watches every player's score and standing update in real time. Fifteen movies —
not ten — because a film projected 11th–15th could overperform its way into the
top 10, and swapping it in can change the outcome of the wager.

The site now has three pages, so this work also replaces the single ad-hoc
cross-link with a **shared pill nav bar** on all three pages.

A working, theme-matched mockup of the target UI exists at
`docs/previews/whatif-sandbox.html` and is the approved design reference. It
embeds real data (top-15 projections + actual picks as of 2026-07-03), and its
drag/scoring/standings/grid JS is production-shape — the JS scoring port in it
has been verified to match `score_player` exactly. The production page differs
only in: payload embedded at build time via `_json_for_script`, theme/nav CSS
injected from the shared static files, the SRI hash on the Sortable script tag,
the `FORECAST_AVAILABLE` gating branch, and no "mockup" flag.

### The wager, in one paragraph

Each player submits a **ranked top-10 prediction** plus 3 dark horses. Scoring
(`score/rules.py`) compares each ranked pick's predicted position to the film's
*actual* finishing position in the season's top 10: exact = 13 pts at the
endpoints (#1/#10) else 10, off-by-1 = 7, off-by-2 = 5, in-top-10-but-off-by-3+
= 3, absent = 0; each dark horse that lands in the top 10 = +1. Every player
scores against the **same** actual top 10, so a hypothetical finish order fully
determines every score. Ties share the placement (no tiebreaker).

## What the view shows

- **A single sortable list of 15 film cards**, pre-populated in the **current
  projected finish order** — exactly the order of the "Movies (projected window
  gross)" table on `index.html` (both derive from the same
  `RenderInput.movies` array, so they match by construction). Cards show only
  the slot number and the film title — **no projected gross, no ranges** — the
  sandbox is about *orders*, not dollar forecasts.
- **A visual divider after slot 10** ("below this line doesn't score") drawn
  purely in CSS on the 10th list item; slots 11–15 render dimmed. Dragging a
  card across the divider is an ordinary reorder — numbering, dimming, and the
  line all follow automatically.
- **Drag and drop** via SortableJS (CDN, version-pinned with an SRI hash) —
  touch-friendly (hold-to-drag on mobile so flick-scrolling still works).
- **Live standings panel** — re-scored and re-sorted on every drop: place,
  username, total points, 👑 on the leader(s), and a movement delta (▲n/▼n/–)
  relative to the baseline standings computed from the initial projected order.
  Tied scores share a place (competition ranking: 1, 1, 3); all co-leaders get
  the crown.
- **Films-by-players points grid** — same visual language as the Winning
  Scenarios grid: rows = the current hypothetical top 10 in order, columns =
  players sorted by hypothetical score (leader leftmost), cells = points each
  film contributes to each player (0 dimmed as `·`), Total row with 👑.
- **Reset button** — restores the projected order and re-scores.
- **Gating** — identical to scenarios: when `forecast_available` is false the
  page shows the "not enough films" notice instead of the sandbox. The gate
  (≥ 25 non-zero projections) also guarantees a full 15-film list whenever the
  page is live.
- **Shared nav bar** — pill-style nav on all three pages (🏆 Leaderboard ·
  🔮 Winning Scenarios · 🎬 What If?), active page highlighted. When the
  forecast is off, the scenarios and what-if pills render as disabled spans
  (no `href`), preserving the existing "unlinked when gated" behavior.

## How it works

### Data (embedded at build time, scenarios-page pattern)

`page.py` builds a payload and embeds it as `const DATA = {...};` in the new
template. No `build.py` changes — everything needed is already in `RenderInput`:

```json
{
  "movies":  ["Spider-Man: Brand New Day", "…up to 15 titles…"],
  "players": [{"username": "vivrad", "ranked": ["…10…"], "dark_horses": ["…3…"]}]
}
```

- `movies`: `[m.title for m in data.movies if m.median_in_window_gross > 0][:15]`
  — already in projected-finish order (build.py sorts `movies` by projected
  gross desc), which is the index table's order.
- `players`: iterate `data.leaderboard` (standings order), join to
  `player_details` by username; ranked titles preserve pick order
  (`predicted_rank = index + 1`).

### Client-side scoring (exact JS port of `score/rules.py`)

`rankedPickPoints(predicted, actual)`, `scoreBreakdown(player, topTitles)`, and
`scorePlayer` mirror the Python functions line-for-line. `scoreBreakdown`
returns per-rank contributions, feeding both the grid cells and (summed) the
standings — the same invariant the Python side keeps
(`sum(score_breakdown(...)) == score_player(...)`).

On every drop, the current top 10 is read back from DOM order (cards carry a
`data-i` index into `DATA.movies`; title strings never round-trip through
HTML), all 8 players are re-scored (8 × 13 picks — trivially fast, no
debouncing), and the standings + grid re-render. Baseline points for the
movement deltas are computed once at page load from the initial order.

### Script-safety (XSS)

Movie titles come from an external scrape. Two layers:

1. A new `_json_for_script()` helper in `page.py` — `json.dumps` +
   `<`-escaping of `<` — so a hostile `</script>` inside a title cannot
   close the script tag. The existing `scenario_json` embedding is switched to
   the same helper (it has this latent gap today).
2. All titles rendered into `innerHTML` on the page pass through an `esc()`
   entity-escaping helper (or are set via `textContent`).

## Architecture

```
summer_movie_wager/render/templates/whatif.html.j2  — NEW standalone What If? page
summer_movie_wager/render/templates/_nav.html.j2    — NEW shared nav include
summer_movie_wager/render/static/nav.css            — NEW nav pill styles (theme-token based)
summer_movie_wager/render/page.py                   — _json_for_script(); what-if payload;
                                                       render whatif.html; wire nav_css + active
summer_movie_wager/render/templates/index.html.j2   — nav include replaces the scenarios-link line
summer_movie_wager/render/templates/scenarios.html.j2 — nav include + nav_css style tag
```

`build.py`, the models, the simulator, and the scoring engine are untouched.

Nav CSS delivery: index inlines `theme_css + nav_css + style_css` as its
existing single `inline_css` variable; scenarios and whatif add a
`<style>{{ nav_css | safe }}</style>` tag after their theme style tag. Every
`template.render(...)` gains `active="index" | "scenarios" | "whatif"`.

The page reuses the existing theme system (`theme.css` tokens + the same
localStorage `smw-theme` dark-mode toggle script as scenarios.html) and copies
the scenarios grid CSS block (matching the repo's existing per-page style
duplication pattern).

## Edge cases

- **Fewer than 15 non-zero projections:** the slice is defensive; the JS renders
  however many arrive, and the `nth-child(10)` / `nth-child(n+11)` divider rules
  are inert on shorter lists. In practice the forecast gate (≥ 25 non-zero)
  guarantees 15.
- **Picks outside the top 15:** they score 0 in every arrangement and cannot be
  dragged in — accepted. Including every picked title would balloon the list to
  30+ cards and wreck the drag UX, and a film projected below #15 realistically
  cannot crack the top 10. A one-line footnote under the list says so.
- **Ties in standings:** competition ranking; tied players share a place, the
  next place skips; every player at place 1 gets 👑.
- **Hostile titles:** `_json_for_script` for the payload; `esc()`/`textContent`
  in the DOM; Jinja autoescape for anything the template renders directly.
- **Empty fixtures:** the payload code tolerates empty `movies`/`player_details`
  (existing render tests pass empty lists).
- **Forecast off:** gated notice; nav pills for scenarios/what-if render as
  disabled spans so `index.html` contains no `href` to gated pages (existing
  test contract).

## Testing

- **`tests/test_render_snapshot.py`** —
  - `_render_pages` extended to also return `whatif.html`;
  - what-if page rendered with `const DATA =`, the pinned Sortable CDN script
    tag, `id="finish"`, the nav, and `const FORECAST_AVAILABLE = true`;
  - gated variant: `FORECAST_AVAILABLE = false` and no `href="whatif.html"` in
    index;
  - nav present on all three pages with the correct `is-active` pill;
  - payload correctness: 17 input movies (one zero-gross) → exactly 15 titles
    in payload order; player ranked/dark-horse titles present in pick order;
  - script-safety: hostile `</script>` title never appears literally inside the
    embedded payload (covers scenarios' payload too);
  - the index golden snapshot (`expected_index.html`) is regenerated once for
    the nav change, per that test's documented procedure.
- **JS scoring port** — verified manually (see Verification #4); no Node
  toolchain is added for this.

## Verification

1. `uv run pytest` — all green (after the one-time snapshot regeneration).
2. `uv run python -m summer_movie_wager.render.build --local` — exits 0; writes
   `docs/whatif.html` alongside `index.html`/`scenarios.html`; no history files
   touched.
3. Open `docs/whatif.html`: the 15 cards match the index "Movies (projected
   window gross)" table order top-to-bottom; cards show titles only; initial
   standings match scoring the projected top 10; drag film #11 above the
   divider → standings, deltas, and grid update instantly; Reset restores the
   projected order; dark mode and mobile (hold-to-drag, flick still scrolls)
   behave; nav pills highlight the right page on all three pages.
4. Hand-check the scoring port: move a player's #1 pick from projected rank 3
   to rank 1 → its contribution goes from 5 pts (off-by-2) to 13 pts (exact at
   endpoint #1); its dark-horse landings add exactly +1 each.
