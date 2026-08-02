# Post-Review Enhancements — Odds History Page, Vendored SortableJS, Keyboard Reordering, Tabs A11y

**Status:** Approved 2026-07-05

## Context

The 2026-07-05 code review closed out its correctness fixes and simplification
cleanups in-session, leaving four approved enhancements. They are bundled into
one project because they touch the same small surface (the render layer and the
two JS pages) and none is large enough to justify its own spec:

1. **Win-odds-over-time chart** — `data/forecast_history.jsonl` has accumulated
   one row per player per production refresh since 2026-05-04, specifically to
   enable this. Nothing reads it yet.
2. **Vendor SortableJS** — the What If? page loads its only external script from
   jsDelivr. If the CDN is down or blocked, the page silently renders an empty
   finish list.
3. **Keyboard-accessible reordering** — drag is currently the only way to reorder
   the What If? finish list, which excludes keyboard and most screen-reader users.
4. **Scenario tabs ARIA cleanup** — the Winning Scenarios player tabs carry
   `role="tablist"`/`role="tab"` without the rest of the ARIA tab pattern
   (`aria-selected`, arrow-key navigation). A half-implemented pattern is worse
   for assistive tech than plain buttons.

No game rules, scoring, modeling, or data formats change.

## 1. Win-odds-over-time — a new "Odds Over Time" page

### Decisions (made with the user)

- A **new 4th page**, `docs/history.html`, with its own nav pill — not a section
  on the leaderboard. It follows the scenarios/whatif pattern exactly: Jinja
  template, JSON payload embedded via `_json_for_script`, inline vanilla JS,
  `theme_css`/`nav_css`/`shared_css` inlined.
- The chart shows **win odds only** (one line per player, y = P(win)). Median
  points, p10/p90 exist in the history file but are out of scope; they can be a
  later metric toggle if ever wanted.

### Data flow

`build.py` gains `_build_forecast_history_payload(path) -> dict`, mirroring the
shape of `_load_history`:

- Reads `data/forecast_history.jsonl` rows
  (`{date, player, win_prob, median_final_pts, p10, p90}`).
- **Dedupes by `(date, player)`, last row wins** — a same-day re-run supersedes.
- Emits `{"dates": [sorted ISO dates], "series": [{"player": u, "win_prob":
  [float|null per date]}, ...]}` with `null` where a player has no row for a
  date, so lines gap rather than interpolate through missing data.
- **Series are emitted in sorted-username order and stay that way.** Color slot
  N is bound to the Nth username alphabetically for the whole season — color
  follows the entity, never its rank, so a refresh never repaints anyone's line.

The payload rides on a new `RenderInput.history` field (default `{}`) and is
embedded into the page like the whatif payload.

### Chart design (dataviz method)

Hand-rolled inline SVG in vanilla JS — no chart library. A dependency was
rejected for the same reason SortableJS is being vendored: this site's pages are
self-contained artifacts, and a line chart over ≤ 20 points × 8 series is ~120
lines of SVG code.

- **Form:** single line chart, one y-axis (0 → a decile ceiling above the max
  observed win prob), x = refresh dates. Never dual-axis.
- **Marks:** 2 px lines, 8 px (r=4) point markers, hairline gridlines in the
  site's `--border-row`, axis/tick text in `--text-muted`. Value text never
  wears a series color.
- **Color:** the 8 players take the 8 categorical slots of the validated
  reference palette (dataviz skill). Both modes were **validated with
  `validate_palette.js` against this site's real card surfaces** — light
  `#ffffff`: all checks pass (3 slots sub-3:1 → the relief rule applies, see
  below); dark `#1e1830`: all checks pass with CVD in the 8–12 floor band →
  **secondary encoding is mandatory**, satisfied by direct labels + legend +
  table view. Slots are CSS vars `--s1…--s8` with `[data-theme="dark"]` and
  `prefers-color-scheme` overrides, same dual mechanism as `theme.css`.

  | Slot | Light | Dark | | Slot | Light | Dark |
  |---|---|---|---|---|---|---|
  | 1 | `#2a78d6` | `#3987e5` | | 5 | `#4a3aa7` | `#9085e9` |
  | 2 | `#1baf7a` | `#199e70` | | 6 | `#e34948` | `#e66767` |
  | 3 | `#eda100` | `#c98500` | | 7 | `#e87ba4` | `#d55181` |
  | 4 | `#008300` | `#008300` | | 8 | `#eb6834` | `#d95926` |

- **Identity is never color-alone:** a legend (all 8 players, colored chip +
  name + latest %, ordered by latest odds), **direct labels for the top 4**
  lines at the right edge (text in `--text` ink next to a colored dash, pushed
  apart ≥ 14 px to avoid collisions), and a **"View as table" `<details>`**
  fallback rendering the full dates × players grid with the shared table styles.
- **Hover layer:** crosshair on the nearest date + a tooltip listing that date's
  win % for every player, sorted descending, each with its colored chip.
- **Gated state:** when the payload has zero dates, hide the chart and show the
  site's existing `.gated` message pattern ("No forecast history yet — run a
  production refresh"). A single date renders as markers without line segments,
  which is correct as-is.

### Nav

`_nav.html.j2` gains a 4th entry `("history.html", "📈 Odds Over Time",
"history")`. Unlike scenarios/whatif, the pill is **not gated on
`forecast_available`** — history is valid even on a day the current forecast is
off. The gate condition becomes `key in ("index", "history") or
forecast_available`.

## 2. Vendor SortableJS

Commit `Sortable.min.js` **1.15.6** (MIT, ~44 KB) to
`summer_movie_wager/render/static/vendor/Sortable.min.js`, keeping its license
banner. `render/page.py` reads it like the CSS files and inlines it into
`whatif.html.j2` via `<script>{{ sortable_js | safe }}</script>`, replacing the
jsDelivr `<script src>` tag entirely.

- The downloaded file must hash to the SRI value the page already pins:
  `sha384-HZZ/fukV+9G8gwTNjN7zQDG0Sp7MsZy5DDN6VfY3Be7V9dvQpEpR2jF2HlyFUUjU`
  (verified against the CDN on 2026-07-05).
- Rejected alternative: copying the file into `docs/` as a separate asset. Every
  other asset on this site is inlined at build time; a second mechanism isn't
  worth it, and inlining removes even the same-origin request.
- After this change the pages' only external requests are Google Fonts.

## 3. Keyboard-accessible reordering on What If?

Each finish-list row gains ▲/▼ buttons after the title (pushed right with
`margin-left:auto`; the `<li>` is already flex):

- `aria-label="Move <title> up"` / `"Move <title> down"` per button.
- One delegated click handler on the list moves the `<li>` one slot and calls
  the existing `rescore()`; the clicked button keeps focus so repeated presses
  walk a film up or down the board. First row's ▲ and last row's ▼ are no-ops.
- Sortable gets `filter: ".move-btn", preventOnFilter: false` so pressing a
  button can never start a drag. Drag behavior is otherwise unchanged.
- The live standings panel already has `aria-live="polite"`, so screen readers
  announce the recomputed standings after each move.
- Rejected alternative: making rows focusable with arrow-key handlers — more
  JS, invisible affordance, and worse touch ergonomics than visible buttons.

## 4. Scenario tabs: plain buttons, honest state

In `scenarios.html.j2`:

- Remove `role="tablist"` from the container and `role="tab"` from the buttons.
- Convey selection with `aria-pressed="true|false"` (a toggle-button group is
  what this UI actually is; the panels aren't ARIA tabpanels).
- Players with no winning scenario get the native `disabled` attribute instead
  of being click-inert styled buttons. (Known tradeoff: disabled buttons don't
  show their `title` tooltip in most browsers; the visual treatment and the
  caption already communicate "no path to winning".)
- Rejected alternative: completing the full ARIA tab pattern
  (`aria-selected`, roving tabindex, arrow keys) — more code for no real gain
  over correctly-stated buttons on a page with one interactive cluster.

## Architecture

```
summer_movie_wager/render/build.py          — _build_forecast_history_payload(); wire into RenderInput
summer_movie_wager/render/page.py           — RenderInput.history field; render history.html; inline sortable_js
summer_movie_wager/render/templates/history.html.j2   — NEW: odds-over-time page (SVG chart, legend, table view)
summer_movie_wager/render/templates/_nav.html.j2      — 4th pill, history not forecast-gated
summer_movie_wager/render/templates/whatif.html.j2    — inline vendored Sortable; move buttons
summer_movie_wager/render/templates/scenarios.html.j2 — role removal, aria-pressed, disabled
summer_movie_wager/render/static/vendor/Sortable.min.js — NEW: vendored 1.15.6
README.md                                   — three pages → four; pages table row
tests/test_build.py, tests/test_render_snapshot.py    — new coverage; refreshed index snapshot
```

## Edge cases

- **Empty/missing history file** → payload `{"dates": [], "series": []}` →
  gated message; the nav pill still renders (an empty page beats a dead link
  mid-bootstrap).
- **Single refresh date** → markers only, no line segments; x-position centered.
- **Duplicate `(date, player)` rows** (same-day re-runs) → last row wins.
- **A player missing from early dates** (e.g. history predating a payload
  change) → `null` gaps; the line breaks rather than interpolating.
- **Dates are unevenly spaced** and plotted at equal intervals (ordinal x-axis).
  With a near-weekly manual cadence this is the honest default; a time-scaled
  axis is not worth the code until the cadence actually varies.
- **`aria-pressed` + `disabled`** never coexist on the same tab: disabled tabs
  omit `aria-pressed` (an unpressable toggle has no pressed state).

## Testing

- `tests/test_build.py` — `_build_forecast_history_payload`: dedupe keeps the
  last same-day row; missing dates become `None`; series sorted by username;
  missing file → empty payload.
- `tests/test_render_snapshot.py` (reusing its `_render_pages` helper):
  - history.html renders, embeds `const DATA =`, and is linked from the nav on
    every page **including when `forecast_available` is false**.
  - whatif.html contains no `jsdelivr` reference and does contain the vendored
    Sortable source; contains `move-btn` markup with the `Move … up` aria-label
    template and the `filter: ".move-btn"` Sortable option.
  - scenarios.html contains no `role="tablist"` / `"role","tab"` and does
    contain `aria-pressed`.
  - `expected_index.html` snapshot refreshed once via its built-in bootstrap
    flow (the nav change alters every page).

## Verification

1. `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .` — all green.
2. `uv run python -m summer_movie_wager.render.build --local`, then in a browser:
   - History page: 8 lines with stable colors in light **and** dark mode,
     legend order = current odds order, crosshair tooltip on hover, table view
     opens, gated message when `data/forecast_history.jsonl` is renamed away.
   - What If?: reorder a film top-to-bottom **using only the keyboard**; scores
     and standings update; drag still works; page loads with network access to
     jsDelivr blocked (only Google Fonts should be requested).
   - Winning Scenarios: tab switching still works; disabled players are
     unclickable; inspect a tab in devtools for `aria-pressed`.
