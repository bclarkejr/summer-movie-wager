# What If? Sandbox — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third page, `docs/whatif.html`, where a visitor drags the top 15 projected movies into a hypothetical top-10 finish order and sees every player's score and standing update live — plus a shared pill nav bar across all three pages.

**Architecture:** Follows the scenarios-page pattern: `page.py` embeds a JSON payload (`const DATA = {...}`) into a new standalone template; vanilla JS ports the scoring rules and re-scores all players on every SortableJS drop. The 15 cards pre-populate in the current projected order (the same `RenderInput.movies` array that drives the index "Movies (projected window gross)" table) and show **titles only — no grosses, no ranges**. A CSS-only divider after slot 10 marks the scoring cutoff. A shared `_nav.html.j2` include + `nav.css` replace the ad-hoc cross-link on all three pages. No `build.py`, model, or scoring-engine changes.

**Tech Stack:** Python 3, Jinja2, pytest, `uv`. Front-end is vanilla JS + CSS on the existing theme tokens, plus SortableJS 1.15.6 from the jsDelivr CDN (version-pinned, SRI hash).

**Spec:** `docs/superpowers/specs/2026-07-03-whatif-sandbox-design.md`

**Design reference (approved mockup):** `docs/previews/whatif-sandbox.html` — the target look and the exact list/standings/grid render JS to reuse in Task 3 (its scoring port is verified against `score_player`).

## Global Constraints

- The card list pre-populates in **projected-finish order** — `[m.title for m in data.movies if m.median_in_window_gross > 0][:15]` — which is by construction the order of the index movies table. Cards display slot number + title **only** (no projected gross, no range, no dollar figures anywhere on the page).
- The JS scoring functions must mirror `score/rules.py` exactly: exact = 13 at #1/#10 else 10; off-by-1 = 7; off-by-2 = 5; off-by-3+ = 3; absent = 0; dark horse in top 10 = +1. Standings ties share a place (competition ranking: 1, 1, 3); all co-leaders get 👑.
- Titles are externally scraped: embed payloads via a `_json_for_script()` helper (`json.dumps` + `<`-escaping of `<`); every title rendered into `innerHTML` passes through an `esc()` entity-escaper (or use `textContent`). Cards carry `data-i` indices into `DATA.movies` — title strings never round-trip through HTML.
- The divider lives in CSS only (`#finish li:nth-child(10)` border + label, `nth-child(n+11)` dimming) — never as a DOM element inside the Sortable list.
- Gating mirrors scenarios: `const FORECAST_AVAILABLE = {{ ... }}`; gated notice when false. Nav pills for scenarios/what-if render as **disabled `<span>`s (no href)** when the forecast is off — `test_scenarios_gated_and_unlinked_when_forecast_off` must stay green.
- The index golden snapshot (`tests/fixtures/expected_index.html`) is regenerated exactly once, for the nav change, per the procedure documented in `test_render_matches_expected_snapshot`.
- Run tests with `uv run pytest`; run the pipeline with `uv run python -m summer_movie_wager.render.build --local`; lint with `uv run ruff check . && uv run ruff format --check .`.

---

## File Structure

```
summer_movie_wager/render/page.py                     — _json_for_script(); nav_css wiring; what-if payload; render whatif.html
summer_movie_wager/render/templates/_nav.html.j2      — NEW shared nav include
summer_movie_wager/render/static/nav.css              — NEW nav pill styles (theme tokens)
summer_movie_wager/render/templates/index.html.j2     — nav include replaces the scenarios-link line
summer_movie_wager/render/templates/scenarios.html.j2 — nav include + nav_css style tag; footer back-link removed
summer_movie_wager/render/templates/whatif.html.j2    — NEW standalone What If? page
tests/test_render_snapshot.py                         — extended _render_pages; nav, what-if, payload, script-safety tests
tests/fixtures/expected_index.html                    — regenerated once (nav)
```

---

## Task 1: `_json_for_script` — script-safe payload embedding

**Files:**
- Modify: `summer_movie_wager/render/page.py` (add helper; switch `scenario_json` to it)
- Test: `tests/test_render_snapshot.py`

**Interfaces:**
- Produces: `_json_for_script(obj) -> str` — `json.dumps(obj, default=str)` with `<` replaced by `<`, so a hostile `</script>` inside scraped data cannot close the inline script tag.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_render_snapshot.py` (reuse the `_render_pages` helper's structure — pass a hostile film title through the scenarios payload):

```python
def test_scenario_json_script_safe(tmp_path):
    from datetime import datetime, timezone
    from summer_movie_wager.render.page import LeaderboardRow, RenderInput, render

    hostile = "</script><script>alert(1)</script>"
    raw = {
        "win_prob": {"a": 1.0},
        "winning_scenarios": {
            "a": {"films": [hostile] + [f"F{i}" for i in range(9)],
                  "grid": {"a": [1] * 10}, "totals": {"a": 10},
                  "win_pct": 100.0, "margin": 10},
        },
    }
    render(tmp_path, RenderInput(
        generated_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
        leaderboard=[LeaderboardRow(username="a", current_pts=1, median_pts=1.0,
                                    p10_pts=0.0, p90_pts=2.0, win_prob=1.0, tie_prob=0.0)],
        movies=[], player_details=[], raw_snapshot=raw,
    ))
    scenarios = (tmp_path / "scenarios.html").read_text()
    assert hostile not in scenarios          # literal </script> must not appear in the payload
    assert "\\u003c/script" in scenarios     # escaped form does
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_render_snapshot.py::test_scenario_json_script_safe -v`
Expected: FAIL — the literal `</script>` currently passes through `json.dumps` + `| safe`.

- [ ] **Step 3: Implement the helper and switch scenarios to it**

In `summer_movie_wager/render/page.py` (module level, near the top):

```python
def _json_for_script(obj: Any) -> str:
    """JSON for embedding inside a <script> tag: \\u003c-escape '<' so a hostile
    '</script>' in scraped data can't close the tag."""
    return json.dumps(obj, default=str).replace("<", "\\u003c")
```

In `render()`, change `scenario_json = json.dumps(scenario_payload, default=str)` to `scenario_json = _json_for_script(scenario_payload)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_render_snapshot.py -v`
Expected: PASS (all existing render tests unchanged).

- [ ] **Step 5: Commit**

```bash
git add summer_movie_wager/render/page.py tests/test_render_snapshot.py
git commit -m "fix(render): escape '<' in embedded script payloads"
```

---

## Task 2: Shared nav include on all three pages

**Files:**
- Create: `summer_movie_wager/render/templates/_nav.html.j2`
- Create: `summer_movie_wager/render/static/nav.css`
- Modify: `summer_movie_wager/render/page.py` (load `nav_css`, wire into both pages, pass `active`)
- Modify: `summer_movie_wager/render/templates/index.html.j2` (include replaces the scenarios-link block, lines 39-41)
- Modify: `summer_movie_wager/render/templates/scenarios.html.j2` (include + nav_css style tag; drop the footer back-link)
- Modify: `tests/fixtures/expected_index.html` (regenerate once)
- Test: `tests/test_render_snapshot.py`

**Interfaces:**
- Produces: `_nav.html.j2` consuming `active` (`"index" | "scenarios" | "whatif"`) and `forecast_available`; emits `<nav class="site-nav">` with `.nav-pill` links, `is-active` on the current page, and disabled `<span>` pills (no href) for gated pages when the forecast is off.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_render_snapshot.py`:

```python
def test_nav_on_both_existing_pages(tmp_path):
    index, scenarios = _render_pages(tmp_path, True)
    for page in (index, scenarios):
        assert 'class="site-nav"' in page
        assert 'href="index.html"' in page
    assert 'href="scenarios.html"' in index
    # active pill matches the page
    assert 'nav-pill is-active" href="index.html"' in index or "is-active" in index
```

(Keep the existing `test_scenarios_gated_and_unlinked_when_forecast_off` untouched — the disabled-span design satisfies it.)

- [ ] **Step 2: Run tests to verify the new one fails**

Run: `uv run pytest tests/test_render_snapshot.py -k nav -v`
Expected: FAIL — no `site-nav` markup exists.

- [ ] **Step 3: Create the include and stylesheet**

`summer_movie_wager/render/templates/_nav.html.j2`:

```jinja
<nav class="site-nav" aria-label="Site pages">
  {% for href, label, key in [("index.html", "🏆 Leaderboard", "index"),
                              ("scenarios.html", "🔮 Winning Scenarios", "scenarios"),
                              ("whatif.html", "🎬 What If?", "whatif")] %}
    {% if key == "index" or forecast_available %}
      <a class="nav-pill{{ ' is-active' if active == key }}" href="{{ href }}"
         {% if active == key %}aria-current="page"{% endif %}>{{ label }}</a>
    {% else %}
      <span class="nav-pill is-disabled" title="Unlocks once the forecast is live">{{ label }}</span>
    {% endif %}
  {% endfor %}
</nav>
```

`summer_movie_wager/render/static/nav.css` — clone the pill aesthetic from scenarios' `.tab` rules (border-radius 50px, `var(--bg-card)`, 2px `var(--border)`, active = `var(--accent-soft)` bg / `var(--accent)` text+border, disabled = `var(--zero)` at reduced opacity, `flex` + `gap` layout, centered, wraps on mobile).

> The what-if pill links to a page that doesn't exist until Task 3. That's fine — nothing dereferences it in tests, and Task 3 lands before any production build.

- [ ] **Step 4: Wire into page.py and both templates**

In `render()`: `nav_css = (_STATIC / "nav.css").read_text()`; change `inline_css = theme_css + "\n" + nav_css + "\n" + style_css`; add `active="index"` to the index render call and `active="scenarios"`, `nav_css=nav_css` to the scenarios call (index already receives `forecast_available`; the include picks it up from template context).

`index.html.j2`: replace the `{% if forecast_available %}...scenarios-link...{% endif %}` block (lines 39-41) with `{% include "_nav.html.j2" %}` placed at the top of `<header>`.

`scenarios.html.j2`: add `<style>{{ nav_css | safe }}</style>` after the theme style tag; add `{% include "_nav.html.j2" %}` right after `<body>`'s theme-toggle button; remove the footer's `← Back to the leaderboard` line.

- [ ] **Step 5: Regenerate the index snapshot and run tests**

Run: `uv run pytest tests/test_render_snapshot.py -v` → the golden-snapshot test fails (expected).
Delete `tests/fixtures/expected_index.html`, re-run (regenerates + instructs inspection), **visually inspect the fixture** (nav present; nothing else drifted), re-run to green.

- [ ] **Step 6: Commit**

```bash
git add summer_movie_wager/render/templates/_nav.html.j2 \
        summer_movie_wager/render/static/nav.css \
        summer_movie_wager/render/page.py \
        summer_movie_wager/render/templates/index.html.j2 \
        summer_movie_wager/render/templates/scenarios.html.j2 \
        tests/test_render_snapshot.py tests/fixtures/expected_index.html
git commit -m "feat(render): shared pill nav bar across pages"
```

---

## Task 3: What-if payload + `whatif.html.j2` page

**Files:**
- Create: `summer_movie_wager/render/templates/whatif.html.j2`
- Modify: `summer_movie_wager/render/page.py` (payload + render call)
- Test: `tests/test_render_snapshot.py`

**Interfaces:**
- Produces: `out_dir/whatif.html` containing the nav, `const DATA = {...}` (shape below), the sortable list markup, standings panel, points grid, and `const FORECAST_AVAILABLE`.
- Payload shape:
  ```json
  {"movies": ["Title1", "…≤15 titles, projected order…"],
   "players": [{"username": "u", "ranked": ["…10…"], "dark_horses": ["…3…"]}]}
  ```

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_render_snapshot.py` (and extend `_render_pages` to also return `(tmp_path / "whatif.html").read_text()`):

```python
def test_whatif_page_rendered(tmp_path):
    index, scenarios, whatif = _render_pages(tmp_path, True)
    assert "const DATA =" in whatif
    assert 'id="finish"' in whatif
    assert "Sortable.min.js" in whatif
    assert 'class="site-nav"' in whatif
    assert "const FORECAST_AVAILABLE = true" in whatif
    assert 'href="whatif.html"' in index


def test_whatif_gated_when_forecast_off(tmp_path):
    index, scenarios, whatif = _render_pages(tmp_path, False)
    assert "const FORECAST_AVAILABLE = false" in whatif
    assert 'href="whatif.html"' not in index


def test_whatif_payload_top15_in_projected_order_with_picks(tmp_path):
    # 17 movies, one zero-gross → payload holds exactly the first 15 non-zero
    # titles in RenderInput.movies order (== the index table's projected order),
    # with no gross figures; player picks present in pick order.
    from datetime import datetime, timezone
    from summer_movie_wager.render.page import (LeaderboardRow, MovieRow,
                                                PickDetail, PlayerDetail,
                                                RenderInput, render)
    movies = [MovieRow(title=f"M{i}", release_date="2026-06-01",
                       status="in_theaters", status_label="in theaters",
                       median_in_window_gross=float(1000 - i), p10=0, p90=0,
                       cumulative_to_date=None, source="t") for i in range(16)]
    movies.append(MovieRow(title="ZeroGross", release_date="2026-06-01",
                           status="pre_release", status_label="pre-release",
                           median_in_window_gross=0, p10=0, p90=0,
                           cumulative_to_date=None, source="t"))
    player = PlayerDetail(
        username="a", median_pts=1.0, current_pts=1,
        ranked=[PickDetail(title=f"M{i}", projected_rank=None,
                           projected_gross=0, projected_pts=0) for i in range(10)],
        dark_horses=[PickDetail(title=f"D{i}", projected_rank=None,
                                projected_gross=0, projected_pts=0) for i in range(3)])
    render(tmp_path, RenderInput(
        generated_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
        leaderboard=[LeaderboardRow(username="a", current_pts=1, median_pts=1.0,
                                    p10_pts=0.0, p90_pts=2.0, win_prob=1.0, tie_prob=0.0)],
        movies=movies, player_details=[player],
        raw_snapshot={"win_prob": {}, "winning_scenarios": {}}))
    whatif = (tmp_path / "whatif.html").read_text()
    import json as _json, re
    payload = _json.loads(re.search(r"const DATA = (.*?);\n", whatif).group(1))
    assert payload["movies"] == [f"M{i}" for i in range(15)]   # 15, ordered, no M15/ZeroGross
    assert payload["players"][0]["ranked"] == [f"M{i}" for i in range(10)]
    assert payload["players"][0]["dark_horses"] == ["D0", "D1", "D2"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_render_snapshot.py -k whatif -v`
Expected: FAIL — `whatif.html` is not written (`FileNotFoundError`).

- [ ] **Step 3: Build the payload and render call in `page.py`**

In `render()`, after the scenarios block:

```python
    details_by_user = {p.username: p for p in data.player_details}
    whatif_payload = {
        "movies": [m.title for m in data.movies if m.median_in_window_gross > 0][:15],
        "players": [
            {
                "username": row.username,
                "ranked": [pd.title for pd in details_by_user[row.username].ranked],
                "dark_horses": [pd.title for pd in details_by_user[row.username].dark_horses],
            }
            for row in data.leaderboard
            if row.username in details_by_user
        ],
    }
    whatif_html = env.get_template("whatif.html.j2").render(
        generated_at = data.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        theme_css = theme_css,
        nav_css = nav_css,
        active = "whatif",
        whatif_json = _json_for_script(whatif_payload),
        forecast_available = data.forecast_available,
        forecast_unavailable_reason = data.forecast_unavailable_reason,
    )
    (out_dir / "whatif.html").write_text(whatif_html)
```

Update `render()`'s docstring to mention the third page.

- [ ] **Step 4: Create `whatif.html.j2`**

Modeled on `scenarios.html.j2` (same head, theme style tag + nav style tag, theme-toggle button + script, gated `#view`/`#gated` switch, footer with `generated_at`). Body:

```html
{% include "_nav.html.j2" %}
<h1>🎬 What If?</h1>
<p class="subtitle">Drag the top-15 projected films into any finish order and watch
  every player's score update. Only the top 10 score — the dashed line marks the cutoff.</p>
<div class="gated" id="gated">⏳ …same notice pattern as scenarios…</div>
<div id="view">
  <div class="sandbox-controls"><button class="reset-btn" id="reset">↺ Reset to projected order</button></div>
  <div class="whatif-layout">
    <ol id="finish" class="finish-list"></ol>       <!-- built by JS from DATA.movies -->
    <aside class="standings card" id="standings"></aside>
  </div>
  <p class="muted footnote">Films outside the projected top 15 can't be dragged in and score 0.</p>
  <div class="grid-wrap"><table id="grid">
    <thead><tr id="head"></tr></thead><tbody id="body"></tbody><tfoot><tr id="foot"></tr></tfoot>
  </table></div>
</div>
```

Cards (built in JS): `<li data-i="N"><span class="grip">⠿</span><span class="film-title">…esc(title)…</span></li>` — **slot number via CSS counter, title only; no gross, no range, no badges**.

Style block (in-template, like scenarios): copy the grid CSS from `scenarios.html.j2` verbatim; add list/card rules:

```css
#finish { list-style:none; counter-reset:slot; padding:0; }
#finish li { counter-increment:slot; display:flex; align-items:center; gap:.6em;
  background:var(--bg-card); border:2px solid var(--border); border-radius:12px;
  padding:.5em .8em; margin:.35em 0; cursor:grab; }
#finish li::before { content:counter(slot); font-weight:800; width:1.6em;
  text-align:right; color:var(--text-muted); }
#finish li:nth-child(10) { border-bottom:3px dashed var(--accent); margin-bottom:1.8em; position:relative; }
#finish li:nth-child(10)::after { content:"▼ below this line doesn't score";
  position:absolute; left:0; bottom:-1.5em; font-size:.75em; font-weight:700; color:var(--accent); }
#finish li:nth-child(n+11) { opacity:.55; }
#finish li.ghost { opacity:.3; } #finish li.chosen { border-color:var(--accent); }
.whatif-layout { display:grid; grid-template-columns:1fr 320px; gap:1.2em; align-items:start; }
@media (max-width:700px) { .whatif-layout { grid-template-columns:1fr; } }
```

Script block:

```html
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js"
        integrity="sha384-<COMPUTE-AT-IMPLEMENTATION>" crossorigin="anonymous"></script>
```

Compute the hash with: `curl -sL https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js | openssl dgst -sha384 -binary | openssl base64 -A`

```js
const DATA = {{ whatif_json | safe }};
const esc = s => s.replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

/* — scoring: exact port of score/rules.py — */
function rankedPickPoints(predicted, actual) {          // actual 0 = missed
  if (actual === 0) return 0;
  const d = Math.abs(predicted - actual);
  if (d === 0) return (actual === 1 || actual === 10) ? 13 : 10;
  if (d === 1) return 7;
  if (d === 2) return 5;
  return 3;
}
function scoreBreakdown(player, topTitles) {
  const pos = new Map(topTitles.map((t, i) => [t, i + 1]));
  const out = new Array(topTitles.length).fill(0);
  player.ranked.forEach((t, i) => { const p = pos.get(t) || 0; if (p) out[p-1] += rankedPickPoints(i+1, p); });
  player.dark_horses.forEach(t => { const p = pos.get(t) || 0; if (p) out[p-1] += 1; });
  return out;
}
const scorePlayer = (p, top) => scoreBreakdown(p, top).reduce((a, b) => a + b, 0);

/* competition ranking: tied points share a place (1,1,3) */
function places(rows) {                                  // rows sorted by pts desc
  let place = 0, prev = null;
  return rows.map((r, i) => { if (r.pts !== prev) { place = i + 1; prev = r.pts; } return place; });
}

const finishEl = document.getElementById("finish");
function buildList() {
  finishEl.innerHTML = DATA.movies.map((t, i) =>
    `<li data-i="${i}"><span class="grip">⠿</span><span class="film-title">${esc(t)}</span></li>`).join("");
}
const currentTop10 = () => [...finishEl.children].slice(0, 10).map(li => DATA.movies[+li.dataset.i]);

const baselinePlaces = (() => {                          // from initial projected order
  const top = DATA.movies.slice(0, 10);
  const rows = DATA.players.map(p => ({u: p.username, pts: scorePlayer(p, top)}))
                           .sort((a, b) => b.pts - a.pts);
  const pl = places(rows);
  return Object.fromEntries(rows.map((r, i) => [r.u, pl[i]]));
})();

function rescore() {
  const top10 = currentTop10();
  const rows = DATA.players.map(p => ({u: p.username, pts: scorePlayer(p, top10),
                                       grid: scoreBreakdown(p, top10)}))
                           .sort((a, b) => b.pts - a.pts);
  renderStandings(rows); renderGrid(rows, top10);
}
```

`renderStandings(rows)`: place (via `places`), 👑 for every place-1 row, `esc(username)`, points, delta = `baselinePlaces[u] − place` rendered ▲n / ▼n / –, leader row(s) highlighted with `--win-bg`/`--win-color`. `renderGrid(rows, top10)`: same innerHTML structure and CSS classes as scenarios' `render()` — film rows with rank spans (`esc(film)`), player columns in `rows` order, `·` + `.zero` for 0, tfoot totals with 👑 on place-1 columns.

Wiring:

```js
new Sortable(finishEl, { animation: 150, ghostClass: "ghost", chosenClass: "chosen",
  delay: 150, delayOnTouchOnly: true, touchStartThreshold: 4, onEnd: rescore });
document.getElementById("reset").onclick = () => { buildList(); rescore(); };
const FORECAST_AVAILABLE = {{ 'true' if forecast_available else 'false' }};
if (!FORECAST_AVAILABLE) { view.style.display = "none"; gated.style.display = "block"; }
else { buildList(); rescore(); }
```

> Note: `new Sortable(...)` binds to the `<ol>` element once; `buildList()` replacing the `<li>` children (Reset) does not require re-binding.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_render_snapshot.py -v`
Expected: PASS (including the Task 2 nav tests — the what-if pill's target now exists).

- [ ] **Step 6: Commit**

```bash
git add summer_movie_wager/render/page.py \
        summer_movie_wager/render/templates/whatif.html.j2 \
        tests/test_render_snapshot.py
git commit -m "feat(render): What If? drag-and-drop top-10 sandbox page"
```

---

## Task 4: End-to-end verification

**Files:** No source changes — verification only.

- [ ] **Step 1: Full suite + lint**

Run: `uv run pytest` and `uv run ruff check . && uv run ruff format --check .`
Expected: all green.

- [ ] **Step 2: Run the pipeline locally**

Run: `uv run python -m summer_movie_wager.render.build --local`
Expected: exits 0; writes `docs/whatif.html` alongside `docs/index.html` / `docs/scenarios.html`; no history files touched.

- [ ] **Step 3: Verify the page**

Open `docs/whatif.html` (`open docs/whatif.html`):
- the 15 cards match the index "Movies (projected window gross)" table order top-to-bottom, and show **titles only** (no dollar figures anywhere);
- initial standings equal scoring everyone against the projected top 10;
- drag film #11 above the dashed divider → standings, movement deltas, and the grid update instantly; slot numbers renumber; below-the-line cards are dimmed;
- Reset restores the projected order and the baseline standings (all deltas –);
- hand-check the port: move a player's #1 pick from projected slot 3 to slot 1 → its grid cell goes 5 → 13; a dark horse dragged into the top 10 adds exactly 1;
- ties: contrive an order where two players tie for the lead → both show the same place and 👑;
- dark-mode toggle restyles the page; on a phone-width viewport hold-to-drag works and flick-scrolling still scrolls;
- nav pills: correct pill highlighted on each of the three pages; with devtools, confirm the gated state (`FORECAST_AVAILABLE = false` path) hides the view and shows the notice.

- [ ] **Step 4: Commit artifact churn**

```bash
git add -A
git commit -m "chore: rebuild site with What If? sandbox page"
```

---

## Self-Review

- **Spec coverage:**
  - Pre-populated **current projected order matching the index movies table** → Task 3 payload (`data.movies` order, the same array the index table renders) + Task 4 Step 3 visual check.
  - **Titles only — no grosses/ranges** on the sandbox → Task 3 card markup (slot counter + title span only) + Global Constraints + Task 4 check.
  - Single 15-card list, CSS-only divider after slot 10, dimmed 11–15 → Task 3 CSS.
  - SortableJS CDN, pinned + SRI, touch-friendly → Task 3 script tag + Sortable options.
  - Live standings (crown, competition-ranking ties, movement deltas vs baseline) → Task 3 `places`/`baselinePlaces`/`renderStandings`.
  - Films-by-players grid in scenarios' visual language → Task 3 `renderGrid` + copied grid CSS.
  - Reset → Task 3 wiring.
  - Shared nav with gated disabled pills → Task 2 (keeps `test_scenarios_gated_and_unlinked_when_forecast_off` green).
  - Forecast gating of the page → Task 3 (`FORECAST_AVAILABLE` switch) + tests.
  - XSS: `_json_for_script` (Task 1, also fixes scenarios) + `esc()`/`data-i` (Task 3).
  - Edge cases (≤15 projections, out-of-list picks footnote, empty fixtures) → Task 3 payload slice/footnote; payload test uses fixture-shaped data.
- **Placeholder scan:** one deliberate placeholder — the SRI hash marked `<COMPUTE-AT-IMPLEMENTATION>` with the exact command to produce it (Task 3 Step 4). Everything else is concrete code or names an exact in-repo source to copy (scenarios' grid CSS/JS structure).
- **Type consistency:** payload `{movies: list[str], players: [{username, ranked, dark_horses}]}` identical in Task 3 Step 1 (test), Step 3 (builder), and Step 4 (JS consumer); `scoreBreakdown` length always equals `topTitles.length`, matching the Python invariant.
