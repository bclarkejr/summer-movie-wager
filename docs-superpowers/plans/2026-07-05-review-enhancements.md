# Post-Review Enhancements — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the four enhancements left open by the 2026-07-05 code review: scenario-tab ARIA cleanup, keyboard reordering on What If?, a vendored SortableJS, and a new Odds Over Time page charting each player's win probability across production refreshes.

**Architecture:** All changes live in the render layer. Two template-only fixes (Tasks 1–2), one asset-vendoring change through `page.py` (Task 3), then the history feature: a payload builder in `build.py` (Task 4) feeding a new `history.html.j2` page with a hand-rolled SVG line chart, plus a 4th nav pill (Task 5). No modeling, scoring, or data-format changes.

**Tech Stack:** Python 3.12, Jinja2, vanilla JS/SVG, SortableJS 1.15.6 (vendored), pytest, `uv`.

**Spec:** `docs/superpowers/specs/2026-07-05-review-enhancements-design.md`

## Global Constraints

- Run tests with `uv run pytest`; lint with `uv run ruff check .`; format-check with `uv run ruff format --check .` — all three must be green at every commit.
- Build the site with `uv run python -m summer_movie_wager.render.build --local` (never omit `--local` during development — the bare command appends to history files).
- `tests/fixtures/expected_index.html` must be regenerated exactly once (Task 5, because the nav change alters index output): delete the fixture, run the snapshot test twice (first run rewrites it and fails by design; second run passes), and inspect the diff — only the nav markup may change.
- Chart work (Task 5): **load the `dataviz` skill before writing or modifying any chart code.** The palette below is already validated against this site's surfaces (`#ffffff` light / `#1e1830` dark card) — do not substitute colors without re-running `validate_palette.js`.
- Series color slots are bound to sorted-username order and must never be reordered by rank ("color follows the entity").
- The two render-page test files use the existing `_render_pages` helper in `tests/test_render_snapshot.py` — extend, don't duplicate.

---

## File Structure

```
summer_movie_wager/render/templates/scenarios.html.j2  — Task 1: roles → aria-pressed/disabled
summer_movie_wager/render/templates/whatif.html.j2     — Task 2: ▲/▼ move buttons; Task 3: inline vendored Sortable
summer_movie_wager/render/static/vendor/Sortable.min.js — Task 3: NEW vendored asset
summer_movie_wager/render/page.py                      — Task 3: sortable_js; Task 5: history field + page render
summer_movie_wager/render/build.py                     — Task 4: _build_forecast_history_payload + wiring
summer_movie_wager/render/templates/history.html.j2    — Task 5: NEW odds-over-time page
summer_movie_wager/render/templates/_nav.html.j2       — Task 5: 4th pill
README.md                                              — Task 6: three pages → four
tests/test_build.py                                    — Task 4 tests
tests/test_render_snapshot.py                          — Tasks 1,2,3,5 tests + snapshot refresh
```

---

## Task 1: Scenario tabs — plain buttons with honest state

**Files:**
- Modify: `summer_movie_wager/render/templates/scenarios.html.j2` (the `#tabs` div and `buildTabs()`)
- Test: `tests/test_render_snapshot.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing other tasks rely on.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_render_snapshot.py`:

```python
def test_scenario_tabs_are_plain_buttons_with_pressed_state(tmp_path):
    _index, scenarios, _whatif = _render_pages(tmp_path, True)
    assert 'role="tablist"' not in scenarios
    assert '"role","tab"' not in scenarios  # the buildTabs setAttribute call
    assert "aria-pressed" in scenarios
    assert "b.disabled = true" in scenarios  # no-scenario players are truly disabled
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_render_snapshot.py::test_scenario_tabs_are_plain_buttons_with_pressed_state -v`
Expected: FAIL — `role="tablist"` is present, `aria-pressed` absent.

- [ ] **Step 3: Edit the template**

In `scenarios.html.j2`, change the tabs container:

```html
  <div class="tabs" id="tabs"></div>
```

and replace the body of `buildTabs()`'s forEach with:

```js
    const sc=DATA.scenarios[p];
    const b=document.createElement("button");
    b.className="tab"+(p===selected?" is-active":"")+(sc?"":" is-disabled");
    if(sc){
      b.setAttribute("aria-pressed", p===selected ? "true" : "false");
      b.innerHTML=`${esc(p)}<span class="pct">${sc.win_pct}%</span>`;
      b.onclick=()=>{selected=p;render();};
    }else{
      b.disabled = true;
      b.innerHTML=`${esc(p)}<span class="pct">0%</span>`;
      b.title="No winning scenario — can't catch the field";
    }
    tabsEl.appendChild(b);
```

(The only changes vs. current code: the `b.setAttribute("role","tab")` line is deleted, `aria-pressed` is set in the enabled branch, and `b.disabled = true` is added in the disabled branch.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_render_snapshot.py -v`
Expected: new test PASSES; all existing tests still pass.

- [ ] **Step 5: Commit**

```bash
git add summer_movie_wager/render/templates/scenarios.html.j2 tests/test_render_snapshot.py
git commit -m "fix(scenarios): replace half-implemented ARIA tab roles with aria-pressed buttons"
```

---

## Task 2: Keyboard-accessible reordering on What If?

**Files:**
- Modify: `summer_movie_wager/render/templates/whatif.html.j2` (`buildList()`, the `new Sortable(...)` options, list-item CSS)
- Test: `tests/test_render_snapshot.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: the `.move-btn` class and `filter: ".move-btn"` Sortable option that Task 3's inlined Sortable must not break.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_render_snapshot.py`:

```python
def test_whatif_rows_have_keyboard_move_buttons(tmp_path):
    _index, _scenarios, whatif = _render_pages(tmp_path, True)
    assert 'class="move-btn"' in whatif
    assert "Move ${esc(t)} up" in whatif  # aria-label template literal in the page JS
    assert 'filter: ".move-btn"' in whatif  # buttons never start a drag
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_render_snapshot.py::test_whatif_rows_have_keyboard_move_buttons -v`
Expected: FAIL — no `move-btn` in the rendered page.

- [ ] **Step 3: Edit the template**

In `whatif.html.j2`, replace `buildList()`:

```js
function buildList() {
  finishEl.innerHTML = DATA.movies.map((t, i) =>
    `<li data-i="${i}"><span class="grip">⠿</span><span class="film-title">${esc(t)}</span>
      <span class="row-move">
        <button class="move-btn" data-dir="-1" aria-label="Move ${esc(t)} up">▲</button>
        <button class="move-btn" data-dir="1" aria-label="Move ${esc(t)} down">▼</button>
      </span></li>`
  ).join("");
}
```

Add a delegated handler directly after the `new Sortable(...)` block:

```js
finishEl.addEventListener("click", e => {
  const btn = e.target.closest(".move-btn");
  if (!btn) return;
  const li = btn.closest("li");
  const target = +btn.dataset.dir < 0 ? li.previousElementSibling : li.nextElementSibling;
  if (!target) return;                       // ▲ on first row / ▼ on last row: no-op
  if (+btn.dataset.dir < 0) finishEl.insertBefore(li, target);
  else finishEl.insertBefore(target, li);
  btn.focus();                               // repeated presses keep walking the film
  rescore();
});
```

Add the two options to the `new Sortable(finishEl, {...})` call, after `touchStartThreshold: 4,`:

```js
  filter: ".move-btn", preventOnFilter: false,
```

Add CSS to the page's `<style>` block, after the `.finish-list li .film-title` rule:

```css
.finish-list li .row-move { margin-left:auto; display:flex; gap:.2em; }
.move-btn {
  font-family:'Nunito',sans-serif; font-size:.8em; font-weight:700; line-height:1;
  color:var(--text-muted); background:transparent;
  border:2px solid var(--border); border-radius:8px;
  padding:.25em .45em; cursor:pointer;
}
.move-btn:hover { color:var(--text); background:var(--bg-hover); }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_render_snapshot.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add summer_movie_wager/render/templates/whatif.html.j2 tests/test_render_snapshot.py
git commit -m "feat(whatif): keyboard-accessible move up/down buttons on the finish list"
```

---

## Task 3: Vendor SortableJS

**Files:**
- Create: `summer_movie_wager/render/static/vendor/Sortable.min.js`
- Modify: `summer_movie_wager/render/page.py` (render()), `summer_movie_wager/render/templates/whatif.html.j2` (the CDN `<script>` tag)
- Test: `tests/test_render_snapshot.py` (update `test_whatif_page_rendered`, add CDN-absence test)

**Interfaces:**
- Consumes: the whatif template from Task 2 (unchanged Sortable API usage).
- Produces: `sortable_js` template variable rendered inside `<script>{{ sortable_js | safe }}</script>`.

- [ ] **Step 1: Download and verify the asset**

```bash
mkdir -p summer_movie_wager/render/static/vendor
curl -sL https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js \
  -o summer_movie_wager/render/static/vendor/Sortable.min.js
openssl dgst -sha384 -binary summer_movie_wager/render/static/vendor/Sortable.min.js | openssl base64 -A
```

Expected hash output (must match the SRI value the page pins today, verified 2026-07-05):
`HZZ/fukV+9G8gwTNjN7zQDG0Sp7MsZy5DDN6VfY3Be7V9dvQpEpR2jF2HlyFUUjU`
If it differs, **stop** — do not commit an unverified asset. Confirm the MIT license banner is present at the top of the file.

- [ ] **Step 2: Write the failing test**

Append to `tests/test_render_snapshot.py`, and in the existing `test_whatif_page_rendered` replace the line `assert "Sortable.min.js" in whatif` with `assert "Sortable" in whatif`:

```python
def test_whatif_has_no_cdn_dependency(tmp_path):
    _index, _scenarios, whatif = _render_pages(tmp_path, True)
    assert "jsdelivr" not in whatif
    assert "cdn." not in whatif
    assert "new Sortable(" in whatif          # library consumer still present
    assert "This fork of Sortable" in whatif or "Sortable 1.15.6" in whatif or "MIT" in whatif
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_render_snapshot.py::test_whatif_has_no_cdn_dependency -v`
Expected: FAIL — `jsdelivr` is present in the rendered page.

- [ ] **Step 4: Inline the asset**

In `render/page.py`, next to the other static reads in `render()`:

```python
    sortable_js = (_STATIC / "vendor" / "Sortable.min.js").read_text()
```

and pass `sortable_js=sortable_js,` in the `whatif.html.j2` render call (alongside `shared_css=shared_css,`).

In `whatif.html.j2`, replace the two-line CDN tag:

```html
<script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/Sortable.min.js"
        integrity="sha384-HZZ/fukV+9G8gwTNjN7zQDG0Sp7MsZy5DDN6VfY3Be7V9dvQpEpR2jF2HlyFUUjU" crossorigin="anonymous"></script>
```

with:

```html
<script>{{ sortable_js | safe }}</script>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_render_snapshot.py -v`
Expected: PASS (including the updated `test_whatif_page_rendered`).

- [ ] **Step 6: Commit**

```bash
git add summer_movie_wager/render/static/vendor/Sortable.min.js summer_movie_wager/render/page.py \
        summer_movie_wager/render/templates/whatif.html.j2 tests/test_render_snapshot.py
git commit -m "feat(whatif): vendor SortableJS 1.15.6, drop the jsDelivr CDN dependency"
```

---

## Task 4: Forecast-history payload builder

**Files:**
- Modify: `summer_movie_wager/render/build.py` (new helper next to `_load_history`, ~line 380)
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: `data/forecast_history.jsonl` rows: `{"date": ISO str, "player": str, "win_prob": float, "median_final_pts": float, "p10": float, "p90": float}`.
- Produces: `_build_forecast_history_payload(path: Path) -> dict[str, Any]` returning `{"dates": list[str], "series": [{"player": str, "win_prob": list[float | None]}]}` — series sorted by username. Task 5 embeds this dict as the history page's `DATA`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_build.py`:

```python
def test_forecast_history_payload_dedupes_and_gaps(tmp_path):
    from summer_movie_wager.render.build import _build_forecast_history_payload

    p = tmp_path / "forecast_history.jsonl"
    rows = [
        '{"date": "2026-05-11", "player": "alice", "win_prob": 0.10, "median_final_pts": 50, "p10": 40, "p90": 60}',
        '{"date": "2026-05-11", "player": "alice", "win_prob": 0.20, "median_final_pts": 50, "p10": 40, "p90": 60}',
        '{"date": "2026-05-11", "player": "bob", "win_prob": 0.30, "median_final_pts": 50, "p10": 40, "p90": 60}',
        '{"date": "2026-05-18", "player": "bob", "win_prob": 0.40, "median_final_pts": 50, "p10": 40, "p90": 60}',
    ]
    p.write_text("\n".join(rows) + "\n")
    payload = _build_forecast_history_payload(p)
    assert payload["dates"] == ["2026-05-11", "2026-05-18"]
    # same-day re-run wins; alice has no 05-18 row so her line gaps with None
    assert payload["series"][0] == {"player": "alice", "win_prob": [0.20, None]}
    assert payload["series"][1] == {"player": "bob", "win_prob": [0.30, 0.40]}


def test_forecast_history_payload_empty_when_file_missing(tmp_path):
    from summer_movie_wager.render.build import _build_forecast_history_payload

    assert _build_forecast_history_payload(tmp_path / "nope.jsonl") == {"dates": [], "series": []}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_build.py::test_forecast_history_payload_dedupes_and_gaps -v`
Expected: FAIL — ImportError, `_build_forecast_history_payload` does not exist.

- [ ] **Step 3: Implement the helper**

In `build.py`, directly below `_load_history`:

```python
def _build_forecast_history_payload(path: Path) -> dict[str, Any]:
    """Payload for the Odds Over Time page: one win-prob series per player.

    Dedupes by (date, player) keeping the LAST row, so a same-day production
    re-run supersedes the earlier one. Dates a player has no row for become
    None so the chart line gaps instead of interpolating. Series are sorted by
    username — color slot N stays bound to the same player across rebuilds.
    """
    rows: dict[tuple[str, str], float] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            rows[(row["date"], row["player"])] = row["win_prob"]
    dates = sorted({d for d, _ in rows})
    players = sorted({p for _, p in rows})
    return {
        "dates": dates,
        "series": [
            {"player": p, "win_prob": [rows.get((d, p)) for d in dates]} for p in players
        ],
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_build.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add summer_movie_wager/render/build.py tests/test_build.py
git commit -m "feat(build): forecast-history payload builder for the odds-over-time page"
```

---

## Task 5: The Odds Over Time page

**Files:**
- Create: `summer_movie_wager/render/templates/history.html.j2`
- Modify: `summer_movie_wager/render/page.py` (`RenderInput`, `render()`), `summer_movie_wager/render/templates/_nav.html.j2`, `summer_movie_wager/render/build.py` (`main()` wiring)
- Test: `tests/test_render_snapshot.py` (+ snapshot refresh)

**Interfaces:**
- Consumes: `_build_forecast_history_payload` from Task 4; `_json_for_script` in `page.py`; `theme_css`/`nav_css`/`shared_css` variables already read in `render()`.
- Produces: `RenderInput.history: dict[str, Any] = field(default_factory=dict)`; `docs/history.html`; a 4th nav pill on every page.

> **Before writing any chart code in this task, load the `dataviz` skill.** The palette below is pre-validated for this site's surfaces; keep slot order fixed.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_render_snapshot.py`:

```python
def test_history_page_rendered_and_always_linked(tmp_path):
    index_on, _s, _w = _render_pages(tmp_path, True)
    history = (tmp_path / "history.html").read_text()
    assert "const DATA =" in history
    assert "Odds Over Time" in history
    assert 'class="site-nav"' in history
    assert 'href="history.html"' in index_on

    index_off, _s2, _w2 = _render_pages(tmp_path, False)
    # unlike scenarios/whatif, history stays linked when the forecast is off
    assert 'href="history.html"' in index_off
    assert 'href="scenarios.html"' not in index_off


def test_history_payload_embedded(tmp_path):
    import json as _json
    import re

    data = _fixture_input()
    data = RenderInput(
        generated_at=data.generated_at,
        leaderboard=data.leaderboard,
        movies=data.movies,
        player_details=data.player_details,
        raw_snapshot=data.raw_snapshot,
        history={
            "dates": ["2026-05-11"],
            "series": [{"player": "bclarke", "win_prob": [0.19]}],
        },
    )
    render(tmp_path, data)
    history = (tmp_path / "history.html").read_text()
    payload = _json.loads(re.search(r"const DATA = (.*?);\n", history).group(1))
    assert payload["dates"] == ["2026-05-11"]
    assert payload["series"][0]["player"] == "bclarke"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_render_snapshot.py::test_history_page_rendered_and_always_linked -v`
Expected: FAIL — `history.html` does not exist.

- [ ] **Step 3: Add the `history` field and render block**

In `render/page.py`, add to `RenderInput`:

```python
    history: dict[str, Any] = field(default_factory=dict)
```

and at the end of `render()`, after the whatif block:

```python
    history_html = env.get_template("history.html.j2").render(
        generated_at=data.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        theme_css=theme_css,
        nav_css=nav_css,
        shared_css=shared_css,
        active="history",
        history_json=_json_for_script(
            data.history if data.history else {"dates": [], "series": []}
        ),
        forecast_available=data.forecast_available,
    )
    (out_dir / "history.html").write_text(history_html)
```

- [ ] **Step 4: Add the nav pill**

Replace the loop header and gate in `_nav.html.j2`:

```jinja
<nav class="site-nav" aria-label="Site pages">
  {% for href, label, key in [("index.html", "🏆 Leaderboard", "index"),
                              ("scenarios.html", "🔮 Winning Scenarios", "scenarios"),
                              ("whatif.html", "🎬 What If?", "whatif"),
                              ("history.html", "📈 Odds Over Time", "history")] %}
    {% if key in ("index", "history") or forecast_available %}
      <a class="nav-pill{{ ' is-active' if active == key }}" href="{{ href }}"
         {% if active == key %}aria-current="page"{% endif %}>{{ label }}</a>
    {% else %}
      <span class="nav-pill is-disabled" title="Unlocks once the forecast is live">{{ label }}</span>
    {% endif %}
  {% endfor %}
</nav>
```

- [ ] **Step 5: Create `history.html.j2`**

Full file content:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Odds Over Time — Summer Movie Wager 2026</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap" rel="stylesheet">
<style>{{ theme_css | safe }}</style>
<style>{{ nav_css | safe }}</style>
<style>{{ shared_css | safe }}</style>
<style>
/* ── Series palette: validated (dataviz validate_palette.js) against #ffffff / #1e1830.
     Slot N is bound to the Nth username alphabetically — never reorder by rank. ── */
:root {
  --s1:#2a78d6; --s2:#1baf7a; --s3:#eda100; --s4:#008300;
  --s5:#4a3aa7; --s6:#e34948; --s7:#e87ba4; --s8:#eb6834;
}
[data-theme="dark"] {
  --s1:#3987e5; --s2:#199e70; --s3:#c98500; --s4:#008300;
  --s5:#9085e9; --s6:#e66767; --s7:#d55181; --s8:#d95926;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --s1:#3987e5; --s2:#199e70; --s3:#c98500; --s4:#008300;
    --s5:#9085e9; --s6:#e66767; --s7:#d55181; --s8:#d95926;
  }
}

.chart-card {
  position:relative; background:var(--bg-card); border-radius:14px;
  padding:1em 1em .6em; box-shadow:0 2px 16px var(--shadow);
}
.chart-card svg { display:block; width:100%; height:auto; font-family:'Nunito',sans-serif; }
.tick { fill:var(--text-muted); font-size:11px; }
.dlabel { fill:var(--text); font-size:12px; font-weight:700; }

.legend { display:flex; flex-wrap:wrap; gap:.4em 1.1em; margin:.9em .2em 0; }
.legend .key { display:inline-flex; align-items:center; gap:.45em; font-size:.9em; font-weight:600; }
.legend .key i { width:12px; height:12px; border-radius:3px; display:inline-block; }
.legend .key b { font-weight:800; }

.tip {
  position:absolute; pointer-events:none; z-index:10;
  background:var(--bg-card); border:2px solid var(--border); border-radius:10px;
  padding:.5em .7em; font-size:.85em; box-shadow:0 2px 12px var(--shadow);
}
.tip .tip-date { font-weight:800; margin-bottom:.25em; }
.tip div i { width:10px; height:10px; border-radius:2px; display:inline-block; margin-right:.4em; }
.tip div b { float:right; margin-left:.8em; }

.table-view { margin-top:1.2em; }
.table-view summary { cursor:pointer; font-weight:700; color:var(--text-muted); }
.table-view .grid-wrap { margin-top:.6em; }
</style>
</head>
<body>
{% include "_theme.html.j2" %}
{% include "_nav.html.j2" %}

<h1>📈 Odds Over Time</h1>
<p class="subtitle">Each player's simulated win probability at every site refresh.
  Lines gap where a refresh produced no forecast for a player.</p>

<div class="gated" id="gated">
  ⏳ No forecast history yet — this chart fills in after the first production refresh.
</div>

<div id="view">
  <div class="chart-card" id="card">
    <svg id="chart" viewBox="0 0 920 440" role="img" aria-label="Win odds over time, one line per player"></svg>
    <div class="tip" id="tip" hidden></div>
  </div>
  <div class="legend" id="legend"></div>
  <details class="table-view">
    <summary>View as table</summary>
    <div class="grid-wrap"><table id="dataTable"></table></div>
  </details>
</div>

<footer>
  Refreshed {{ generated_at }}.
</footer>

<script>
const DATA = {{ history_json | safe }};

const esc = s => s.replace(/[&<>"']/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));

const svg = document.getElementById("chart");
const tip = document.getElementById("tip");
const card = document.getElementById("card");
const NS = "http://www.w3.org/2000/svg";
const W = 920, H = 440, M = { top: 16, right: 150, bottom: 36, left: 48 };
const IW = W - M.left - M.right, IH = H - M.top - M.bottom;

const last = s => [...s.win_prob].reverse().find(v => v != null) ?? 0;
const byLatest = [...DATA.series].sort((a, b) => last(b) - last(a));
// color follows the entity: slot index comes from the payload's fixed order
const colorOf = p => `var(--s${DATA.series.findIndex(s => s.player === p) + 1})`;
const pct = v => Math.round(v * 100) + "%";

function el(name, attrs, parent) {
  const node = document.createElementNS(NS, name);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  (parent || svg).appendChild(node);
  return node;
}

const n = DATA.dates.length;
const yMax = Math.max(0.1, ...DATA.series.flatMap(s => s.win_prob.filter(v => v != null)));
const yTop = Math.min(1, Math.ceil(yMax * 10 + 1) / 10);   // next decile above the max
const x = i => M.left + (n === 1 ? IW / 2 : (i / (n - 1)) * IW);
const y = v => M.top + IH - (v / yTop) * IH;

function draw() {
  // gridlines + y ticks (every 10 points of probability)
  for (let t = 0; t <= yTop + 1e-9; t += 0.1) {
    el("line", { x1: M.left, x2: M.left + IW, y1: y(t), y2: y(t),
                 stroke: "var(--border-row)", "stroke-width": 1 });
    const lbl = el("text", { x: M.left - 8, y: y(t) + 4, "text-anchor": "end", class: "tick" });
    lbl.textContent = pct(t);
  }
  // x ticks, thinned to at most 8 labels
  const step = Math.max(1, Math.ceil(n / 8));
  DATA.dates.forEach((d, i) => {
    if (i % step && i !== n - 1) return;
    const lbl = el("text", { x: x(i), y: M.top + IH + 22, "text-anchor": "middle", class: "tick" });
    lbl.textContent = d.slice(5);            // MM-DD
  });

  // one 2px line + 8px markers per player; null values break the path
  for (const s of DATA.series) {
    let d = "", pen = false;
    s.win_prob.forEach((v, i) => {
      if (v == null) { pen = false; return; }
      d += (pen ? " L" : " M") + x(i).toFixed(1) + " " + y(v).toFixed(1);
      pen = true;
    });
    if (d.includes("L")) el("path", { d, fill: "none", stroke: colorOf(s.player),
      "stroke-width": 2, "stroke-linejoin": "round", "stroke-linecap": "round" });
    s.win_prob.forEach((v, i) => {
      if (v != null) el("circle", { cx: x(i), cy: y(v), r: 4, fill: colorOf(s.player) });
    });
  }

  // direct labels for the top 4 (text in ink, colored dash carries identity)
  const labels = byLatest.slice(0, 4).map(s => ({ p: s.player, v: last(s) }))
    .sort((a, b) => y(a.v) - y(b.v));
  let prev = -Infinity;
  for (const L of labels) {
    const ly = Math.max(y(L.v), prev + 14);
    prev = ly;
    el("line", { x1: M.left + IW + 6, x2: M.left + IW + 16, y1: ly, y2: ly,
                 stroke: colorOf(L.p), "stroke-width": 3 });
    const t = el("text", { x: M.left + IW + 20, y: ly + 4, class: "dlabel" });
    t.textContent = L.p;
  }

  // legend: all players, ordered by latest odds, color chip + name + latest %
  document.getElementById("legend").innerHTML = byLatest.map(s =>
    `<span class="key"><i style="background:${colorOf(s.player)}"></i>${esc(s.player)} <b>${pct(last(s))}</b></span>`
  ).join("");

  // table view (relief for sub-3:1 slots + screen readers)
  document.getElementById("dataTable").innerHTML =
    `<thead><tr><th class="film-col">Date</th>${byLatest.map(s => `<th>${esc(s.player)}</th>`).join("")}</tr></thead>` +
    `<tbody>${DATA.dates.map((d, i) =>
      `<tr><td class="film-col">${esc(d)}</td>${byLatest.map(s => {
        const v = s.win_prob[i];
        return `<td>${v == null ? "·" : pct(v)}</td>`;
      }).join("")}</tr>`).join("")}</tbody>`;

  // crosshair + tooltip
  const hover = el("line", { y1: M.top, y2: M.top + IH, stroke: "var(--text-muted)",
    "stroke-width": 1, "stroke-dasharray": "3 3", visibility: "hidden" });
  svg.addEventListener("mousemove", e => {
    const r = svg.getBoundingClientRect();
    const px = (e.clientX - r.left) * (W / r.width);
    const i = Math.max(0, Math.min(n - 1, Math.round((px - M.left) / (n === 1 ? IW : IW / (n - 1)))));
    hover.setAttribute("x1", x(i)); hover.setAttribute("x2", x(i));
    hover.setAttribute("visibility", "visible");
    tip.innerHTML = `<div class="tip-date">${esc(DATA.dates[i])}</div>` + byLatest
      .map(s => ({ p: s.player, v: s.win_prob[i] }))
      .filter(o => o.v != null)
      .sort((a, b) => b.v - a.v)
      .map(o => `<div><i style="background:${colorOf(o.p)}"></i>${esc(o.p)}<b>${pct(o.v)}</b></div>`)
      .join("");
    tip.hidden = false;
    const cw = card.clientWidth, tx = (x(i) / W) * cw;
    tip.style.left = Math.max(8, Math.min(cw - tip.offsetWidth - 8, tx + 14)) + "px";
    tip.style.top = "20px";
  });
  svg.addEventListener("mouseleave", () => {
    hover.setAttribute("visibility", "hidden");
    tip.hidden = true;
  });
}

if (n === 0) {
  document.getElementById("view").style.display = "none";
  document.getElementById("gated").style.display = "block";
} else {
  draw();
}
</script>
</body>
</html>
```

- [ ] **Step 6: Wire the payload in `build.py`**

In `main()`, pass the history payload into `RenderInput` (add one line to the existing constructor call):

```python
            history=_build_forecast_history_payload(DATA_DIR / "forecast_history.jsonl"),
```

- [ ] **Step 7: Run tests; refresh the index snapshot**

Run: `uv run pytest tests/test_render_snapshot.py -v`
Expected: the two new tests PASS; `test_render_matches_expected_snapshot` FAILS (nav changed).

```bash
cp tests/fixtures/expected_index.html /tmp/old_expected_index.html
rm tests/fixtures/expected_index.html
uv run pytest tests/test_render_snapshot.py -q   # first run rewrites the fixture and fails by design
uv run pytest tests/test_render_snapshot.py -q   # second run must pass
diff /tmp/old_expected_index.html tests/fixtures/expected_index.html
```

Expected diff: **only** the added `href="history.html"` nav pill. Anything else is a regression — stop and investigate.

- [ ] **Step 8: Full suite + lint**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check .`
Expected: all green.

- [ ] **Step 9: Commit**

```bash
git add summer_movie_wager/render/templates/history.html.j2 summer_movie_wager/render/templates/_nav.html.j2 \
        summer_movie_wager/render/page.py summer_movie_wager/render/build.py \
        tests/test_render_snapshot.py tests/fixtures/expected_index.html
git commit -m "feat(history): Odds Over Time page charting win probability per refresh"
```

---

## Task 6: README + end-to-end verification

**Files:**
- Modify: `README.md`
- No other source changes. Verification only.

- [ ] **Step 1: Update the README**

Three edits:
1. In "What this is, architecturally": change "renders three **static HTML pages**" to "renders four **static HTML pages**", and update the external-requests sentence — SortableJS is now vendored, so it reads: "The pages' only external request is Google Fonts."
2. In "The three pages" section: retitle to "The four pages" and add a row to the table:
   `| docs/history.html (Odds Over Time) | Each player's win probability at every production refresh, as an SVG line chart with a table fallback | Inline vanilla JS renders the chart from an embedded JSON payload |`
3. In the repository-layout tree, extend the templates line to `# index / scenarios / whatif / history + shared _nav/_theme partials` and add `vendor/Sortable.min.js` under `static/`.

- [ ] **Step 2: Rebuild and inspect in a browser**

```bash
uv run python -m summer_movie_wager.render.build --local
python3 -m http.server -d docs 8000
```

Check, in light **and** dark mode:
- **history.html** — 8 lines with distinct colors; legend ordered by current odds; hovering shows the crosshair + per-date tooltip; "View as table" opens the full grid; top-4 direct labels don't collide.
- Temporarily rename `data/forecast_history.jsonl` and rebuild → gated message; rename it back and rebuild.
- **whatif.html** — with devtools network blocking on `cdn.jsdelivr.net`: page fully works. Reorder a film using only Tab + Enter on the ▲/▼ buttons; standings and grid update; drag still works and never starts from a button.
- **scenarios.html** — tabs switch; a disabled player's tab is unclickable; devtools shows `aria-pressed="true"` on the active tab and no `role="tab"` anywhere.
- Nav on all four pages: Odds Over Time pill present and active-highlighted on its page.

- [ ] **Step 3: Final gates**

Run: `uv run pytest && uv run ruff check . && uv run ruff format --check .`
Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add README.md docs
git commit -m "docs: four-page site — add Odds Over Time to README and rebuilt pages"
```

---

## Self-Review

- **Spec coverage:** tabs cleanup → Task 1; keyboard reordering → Task 2;
  vendored Sortable + hash verification → Task 3; payload with dedupe/gaps/
  fixed series order → Task 4; page, chart, palette, legend, direct labels,
  table view, crosshair, gated state, ungated nav pill → Task 5; README +
  browser verification incl. dark mode, keyboard-only, CDN-blocked → Task 6.
  All spec sections have a task.
- **Placeholders:** none — every code step shows the exact code, every command
  its expected outcome.
- **Type consistency:** `_build_forecast_history_payload` returns
  `{"dates", "series"}` (Task 4) and Task 5's `RenderInput.history`, template
  `DATA.dates`/`DATA.series[].player`/`DATA.series[].win_prob`, and both new
  tests consume exactly that shape; `sortable_js` name matches between
  `page.py` and `whatif.html.j2`.
