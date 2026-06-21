# Playful UI Redesign — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the minimal stylesheet with the playful Nunito-based design (cards, gradient h1, teal/coral/purple palette, pill badges) and add a dark mode toggle that auto-detects `prefers-color-scheme` and persists preference to `localStorage`.

**Architecture:** Two files change. No Python, no logic, no data changes.

**Tech Stack:** CSS custom properties, Google Fonts (CDN), 20-line vanilla JS snippet for dark mode. No build step.

**Spec:** `docs/superpowers/specs/2026-06-19-playful-ui-redesign.md`

**Reference implementation:** `docs/previews/style-1-playful.html` — the approved mockup.

---

## File Structure

Files modified during this plan:

```
summer_movie_wager/render/static/style.css          — complete replacement
summer_movie_wager/render/templates/index.html.j2   — targeted additions
```

No new files. `docs/previews/` files are read-only reference; do not modify them.

---

## Task 1: Replace `style.css` with the new playful stylesheet

**Goal:** Swap the 20-line minimal CSS for a full themed stylesheet using CSS custom properties for light/dark mode. The rendered HTML will look broken until Task 2 adds the Google Fonts `<link>` and the card classes — that's expected.

**Files:**
- Modify: `summer_movie_wager/render/static/style.css`

- [ ] **Step 1: Overwrite `style.css` with the full new stylesheet**

Replace the entire contents of `summer_movie_wager/render/static/style.css` with:

```css
/* ── Theme tokens ── */
:root {
  --bg:             #f9f7ff;
  --bg-card:        #ffffff;
  --bg-hover:       #f9f7ff;
  --bg-row-alt:     transparent;
  --bg-summary:     #f9f7ff;
  --text:           #2d2d3a;
  --text-muted:     #999;
  --text-source:    #aaa;
  --border:         #f0eeff;
  --border-row:     #f3f3f3;
  --th-color:       #555;
  --shadow:         rgba(0,0,0,0.07);
  --badge-np-bg:    #eee;
  --badge-np-color: #888;
  --badge-pre-bg:   #e0d9ff;
  --badge-pre-color:#6c3fcf;
  --badge-it-bg:    #c9f7e8;
  --badge-it-color: #1a7a54;
  --forecast-bg:    #fff8e0;
  --forecast-border:#ffe66d;
  --forecast-color: #7a6200;
  --footer-color:   #aaa;
}

[data-theme="dark"] {
  --bg:             #12101f;
  --bg-card:        #1e1830;
  --bg-hover:       #271f3d;
  --bg-row-alt:     #1a1428;
  --bg-summary:     #1e1830;
  --text:           #f0eeff;
  --text-muted:     #8878bb;
  --text-source:    #6a5a99;
  --border:         #2e2550;
  --border-row:     #261e3d;
  --th-color:       #9988cc;
  --shadow:         rgba(0,0,0,0.35);
  --badge-np-bg:    #231c3a;
  --badge-np-color: #6a5a99;
  --badge-pre-bg:   #3a2a6a;
  --badge-pre-color:#c4b0ff;
  --badge-it-bg:    #0d3d28;
  --badge-it-color: #4ecdc4;
  --forecast-bg:    #1e1a10;
  --forecast-border:#7a6200;
  --forecast-color: #d4a820;
  --footer-color:   #6a5a99;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg:             #12101f;
    --bg-card:        #1e1830;
    --bg-hover:       #271f3d;
    --bg-row-alt:     #1a1428;
    --bg-summary:     #1e1830;
    --text:           #f0eeff;
    --text-muted:     #8878bb;
    --text-source:    #6a5a99;
    --border:         #2e2550;
    --border-row:     #261e3d;
    --th-color:       #9988cc;
    --shadow:         rgba(0,0,0,0.35);
    --badge-np-bg:    #231c3a;
    --badge-np-color: #6a5a99;
    --badge-pre-bg:   #3a2a6a;
    --badge-pre-color:#c4b0ff;
    --badge-it-bg:    #0d3d28;
    --badge-it-color: #4ecdc4;
    --forecast-bg:    #1e1a10;
    --forecast-border:#7a6200;
    --forecast-color: #d4a820;
    --footer-color:   #6a5a99;
  }
}

* { box-sizing: border-box; }

body {
  font-family: 'Nunito', sans-serif;
  font-size: 15px;
  line-height: 1.5;
  max-width: 1000px;
  margin: 0 auto;
  padding: 1.5em 1.2em 3em;
  background: var(--bg);
  color: var(--text);
  transition: background 0.25s, color 0.25s;
}

/* ── Dark mode toggle button (fixed, top-right) ── */
.theme-toggle {
  position: fixed;
  top: 1em;
  right: 1em;
  z-index: 100;
  background: var(--bg-card);
  border: 2px solid var(--border);
  border-radius: 50px;
  padding: 0.35em 0.9em;
  font-family: 'Nunito', sans-serif;
  font-size: 0.85em;
  font-weight: 700;
  color: var(--text);
  cursor: pointer;
  box-shadow: 0 2px 12px var(--shadow);
  transition: background 0.25s, border-color 0.25s, color 0.25s, transform 0.1s;
  display: flex;
  align-items: center;
  gap: 0.4em;
}
.theme-toggle:hover { transform: scale(1.05); }
.theme-toggle .icon { font-size: 1.1em; }

header {
  text-align: center;
  padding: 2em 0 1.5em;
}

h1 {
  font-size: 2.4em;
  font-weight: 800;
  margin: 0 0 0.2em;
  background: linear-gradient(135deg, #ff6b6b, #f7c59f, #ffe66d, #4ecdc4);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

h2 {
  font-size: 1.2em;
  font-weight: 800;
  margin: 0 0 0.8em;
  color: #4ecdc4;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.meta {
  color: var(--text-muted);
  font-size: 0.9em;
}

/* ── Cards ── */
.card {
  background: var(--bg-card);
  border-radius: 16px;
  padding: 1.5em;
  margin-bottom: 1.5em;
  box-shadow: 0 4px 20px var(--shadow);
  transition: background 0.25s, box-shadow 0.25s;
}

.leaderboard h2 { color: #ff6b6b; }
.players h2     { color: #a855f7; }

/* ── Tables ── */
table {
  width: 100%;
  border-collapse: collapse;
  font-variant-numeric: tabular-nums;
}

.leaderboard thead tr { background: linear-gradient(90deg, #ff6b6b22, #f7c59f22); }
.movies thead tr      { background: linear-gradient(90deg, #4ecdc422, #ffe66d22); }

th {
  font-weight: 700;
  font-size: 0.82em;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 0.7em 0.8em;
  color: var(--th-color);
  border-bottom: 2px solid var(--border);
}

td {
  padding: 0.55em 0.8em;
  border-bottom: 1px solid var(--border-row);
}

td:first-child { font-weight: 700; }

tbody tr:nth-child(even)  { background: var(--bg-row-alt); }
tbody tr:hover            { background: var(--bg-hover); }
tbody tr:last-child td    { border-bottom: none; }

/* Leaderboard rank medals via CSS */
.player-row:first-child  td:first-child::before { content: "🥇 "; }
.player-row:nth-child(2) td:first-child::before { content: "🥈 "; }
.player-row:nth-child(3) td:first-child::before { content: "🥉 "; }

/* ── Badges ── */
.badge {
  font-size: 0.75em;
  font-weight: 700;
  padding: 0.2em 0.7em;
  border-radius: 20px;
  white-space: nowrap;
  display: inline-block;
}

.badge-pre_release  { background: var(--badge-pre-bg);  color: var(--badge-pre-color); }
.badge-in_theaters  { background: var(--badge-it-bg);   color: var(--badge-it-color);  }
.badge-closed,
.badge-wont_score,
.badge-no_projection { background: var(--badge-np-bg); color: var(--badge-np-color); }

.muted  { color: var(--text-muted);  font-size: 0.88em; }
.source { color: var(--text-source); font-size: 0.82em; }

/* ── Per-player details ── */
details {
  margin: 0.5em 0;
  border-radius: 12px;
  overflow: hidden;
  border: 2px solid var(--border);
  transition: border-color 0.2s, background 0.25s;
}
details[open] { border-color: #a855f7; }

summary {
  cursor: pointer;
  padding: 0.75em 1em;
  font-weight: 700;
  font-size: 1em;
  background: var(--bg-summary);
  list-style: none;
  display: flex;
  align-items: center;
  gap: 0.5em;
  transition: background 0.25s;
}
summary::before { content: "▶"; font-size: 0.7em; color: #a855f7; transition: transform 0.2s; }
details[open] summary::before { transform: rotate(90deg); }
summary::-webkit-details-marker { display: none; }

.ranked-picks,
.dark-horses {
  margin: 0.5em 0 0.5em 1em;
  padding: 0 1em;
}
.ranked-picks li,
.dark-horses li { padding: 0.3em 0; }

.dark-horse-label {
  font-weight: 800;
  margin: 0.8em 1em 0.2em;
  font-size: 0.9em;
  color: #ff6b6b;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

/* ── Footer ── */
footer {
  text-align: center;
  margin-top: 2em;
  color: var(--footer-color);
  font-size: 0.85em;
}
footer a { color: #4ecdc4; }

/* ── Forecast unavailable notice ── */
.forecast-unavailable {
  background: var(--forecast-bg);
  border: 2px solid var(--forecast-border);
  border-radius: 10px;
  padding: 0.6em 1em;
  margin-bottom: 1em;
  font-size: 0.88em;
  color: var(--forecast-color);
}

/* ── Responsive ── */
@media (max-width: 600px) {
  body { font-size: 13px; padding: 1em 0.8em 3em; }
  th, td { padding: 0.3em 0.5em; }
  .theme-toggle { top: 0.6em; right: 0.6em; padding: 0.25em 0.6em; font-size: 0.78em; }
  h1 { font-size: 1.8em; }
}
```

- [ ] **Step 2: Verify the file was written correctly**

Run: `wc -l summer_movie_wager/render/static/style.css`
Expected: approximately 170–185 lines.

Run: `grep -c 'var(--' summer_movie_wager/render/static/style.css`
Expected: ≥ 20 (confirms custom properties are in use throughout).

- [ ] **Step 3: Commit**

```bash
git add summer_movie_wager/render/static/style.css
git commit -m "feat(ui): replace minimal stylesheet with playful Nunito design + dark mode tokens"
```

---

## Task 2: Update `index.html.j2` with Google Fonts, dark mode toggle, card classes, and emoji headings

**Goal:** Wire up the template so the new CSS is fully functional — Nunito loads from CDN, the dark mode button appears, sections become cards, and headings carry their emoji decorators.

**Files:**
- Modify: `summer_movie_wager/render/templates/index.html.j2`

- [ ] **Step 1: Add Google Fonts `<link>` tags to `<head>`**

In `index.html.j2`, locate the line:
```html
<style>{{ inline_css | safe }}</style>
```

Insert the following **immediately before** that line:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Nunito:wght@400;600;700;800&display=swap" rel="stylesheet">
```

- [ ] **Step 2: Add the dark mode button and init script at the top of `<body>`**

Locate:
```html
<body>
<header>
```

Replace with:
```html
<body>
<button class="theme-toggle" id="themeBtn" onclick="toggleTheme()" aria-label="Toggle dark mode">
  <span class="icon" id="themeIcon">🌙</span>
  <span id="themeLabel">Dark mode</span>
</button>
<script>
(function() {
  var prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  var saved = localStorage.getItem('smw-theme');
  var isDark = saved ? saved === 'dark' : prefersDark;
  if (isDark) document.documentElement.setAttribute('data-theme', 'dark');
  window.toggleTheme = function() {
    var goingDark = document.documentElement.getAttribute('data-theme') !== 'dark';
    document.documentElement.setAttribute('data-theme', goingDark ? 'dark' : 'light');
    document.getElementById('themeIcon').textContent = goingDark ? '☀️' : '🌙';
    document.getElementById('themeLabel').textContent = goingDark ? 'Light mode' : 'Dark mode';
    localStorage.setItem('smw-theme', goingDark ? 'dark' : 'light');
  };
  document.addEventListener('DOMContentLoaded', function() {
    var dark = document.documentElement.getAttribute('data-theme') === 'dark';
    document.getElementById('themeIcon').textContent = dark ? '☀️' : '🌙';
    document.getElementById('themeLabel').textContent = dark ? 'Light mode' : 'Dark mode';
  });
})();
</script>
<header>
```

**Note on emoji encoding:** The script uses Unicode escapes (`☀️` = ☀️, `🌙` = 🌙) to avoid Jinja2 template encoding issues with multi-byte emoji in inline script blocks. The button markup itself uses literal emoji since Jinja2 autoescape does not affect them inside `aria-label` or text nodes.

- [ ] **Step 3: Add `card` class to each `<section>`**

Make the following three replacements:

Replace:
```html
<section class="leaderboard">
```
With:
```html
<section class="leaderboard card">
```

Replace:
```html
<section class="movies">
```
With:
```html
<section class="movies card">
```

Replace:
```html
<section class="players">
```
With:
```html
<section class="players card">
```

- [ ] **Step 4: Add emoji prefixes to section headings**

Replace:
```html
  <h2>Leaderboard</h2>
```
With:
```html
  <h2>🏆 Leaderboard</h2>
```

Replace:
```html
  <h2>Movies (projected window gross)</h2>
```
With:
```html
  <h2>🎥 Movies (projected window gross)</h2>
```

Replace:
```html
  <h2>Per-player detail</h2>
```
With:
```html
  <h2>🎭 Per-player detail</h2>
```

- [ ] **Step 5: Add emoji to the dark horse label**

Replace:
```html
    <p class="dark-horse-label">Dark horses</p>
```
With:
```html
    <p class="dark-horse-label">🐴 Dark horses</p>
```

- [ ] **Step 6: Verify the template looks correct**

Run: `grep -n 'Nunito\|theme-toggle\|card\|🏆\|🎥\|🎭\|🐴' summer_movie_wager/render/templates/index.html.j2`

Expected output should show lines containing each of these strings, confirming all five edits landed.

- [ ] **Step 7: Commit**

```bash
git add summer_movie_wager/render/templates/index.html.j2
git commit -m "feat(ui): add Nunito font, dark mode toggle, card sections, and emoji headings to template"
```

---

## Task 3: Regenerate `docs/index.html` and verify visually

**Goal:** Run the build pipeline to produce a fresh `docs/index.html`, confirm it matches the approved mockup, and test dark mode behavior.

**Files:**
- Regenerated (not committed yet): `docs/index.html`

- [ ] **Step 1: Run the build pipeline**

```bash
uv run python -m summer_movie_wager.render.build
```

Expected: completes without error; `docs/index.html` and `docs/data.json` are updated.

If the build requires network access (to scrape live data) and you're offline, try any `--local` or `--dry-run` flag the pipeline supports, or temporarily use the last committed data. The CSS and template changes do not depend on fresh data.

- [ ] **Step 2: Open the generated page**

```bash
open docs/index.html
```

Visually verify against `docs/previews/style-1-playful.html` (open side-by-side):

- [ ] Body background is `#f9f7ff` (light lavender), not white
- [ ] H1 renders as a coral→peach→yellow→teal gradient
- [ ] Leaderboard section has a white card with rounded corners and subtle shadow
- [ ] Movies section has a white card
- [ ] Per-player section has a white card
- [ ] `🌙 Dark mode` button is visible in the top-right corner
- [ ] Section headings show 🏆 / 🎥 / 🎭 emojis
- [ ] Top 3 leaderboard rows show 🥇 🥈 🥉 medals
- [ ] Badges are pill-shaped (rounded, not square)

- [ ] **Step 3: Test dark mode toggle**

- Click the 🌙 button → background shifts to deep purple `#12101f`, label becomes "☀️ Light mode"
- Click again → reverts to light mode
- Refresh the page in dark mode → dark mode persists (localStorage)
- Open a fresh private/incognito window with OS dark mode enabled → auto-applies dark mode without clicking

- [ ] **Step 4: Run the test suite**

```bash
uv run pytest -v
```

Expected: all tests pass. If `tests/test_render_snapshot.py` fails (render snapshot mismatch), regenerate the fixture:

```bash
cp docs/index.html tests/fixtures/expected_index.html
uv run pytest tests/test_render_snapshot.py -v
```

Expected after fixture update: pass.

- [ ] **Step 5: Commit `docs/` and any fixture update**

```bash
git add docs/index.html docs/data.json
# If fixture was regenerated:
git add tests/fixtures/expected_index.html
git commit -m "feat(ui): regenerate docs with playful redesign"
```

---

## Self-Review

**Spec coverage:**
- ✅ Nunito font loaded via Google Fonts `<link>` (Task 2, Step 1)
- ✅ CSS custom properties for light + dark tokens (Task 1, Step 1)
- ✅ `[data-theme="dark"]` + `prefers-color-scheme` auto-detection (Task 1, Step 1)
- ✅ Dark mode toggle button with localStorage persistence (Task 2, Step 2)
- ✅ Card sections with rounded corners and shadows (Task 1 CSS + Task 2 Step 3)
- ✅ Gradient h1, colored h2s by section (Task 1, Step 1)
- ✅ Pill-shaped badges, all three badge states themed (Task 1, Step 1)
- ✅ Emoji headings: 🏆 🎥 🎭 🐴 (Task 2, Steps 4–5)
- ✅ Medal emoji for leaderboard top-3 via CSS `::before` (Task 1, Step 1)
- ✅ Responsive breakpoint at 600px (Task 1, Step 1)
- ✅ Visual verification against approved mockup (Task 3)
- ✅ No Python, no data, no logic files changed
