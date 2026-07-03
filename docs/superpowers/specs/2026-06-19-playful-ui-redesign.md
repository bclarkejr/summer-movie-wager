# Summer Movie Wager 2026 — Playful UI Redesign

**Status:** Approved 2026-06-19

## Context

The site launched with a minimal system-font stylesheet prioritising readability over personality. After reviewing five aesthetic mockups saved in `docs/previews/`, the **playful/colorful** style was selected as the preferred look for the production site. The redesign should make the wager feel more like a fun group activity and less like a data dump, while keeping all existing information and page structure intact.

Five mockups were evaluated at `docs/previews/`:
- `style-0-current.html` — the existing look (baseline)
- `style-1-playful.html` — **selected winner** (Nunito font, card layout, coral/teal/yellow palette, dark mode)
- `style-2-minimal.html` — Inter, white space, all-caps headings
- `style-3-bold.html` — dark bg, Oswald headers, electric orange
- `style-4-warm.html` — Lora serif, cream/earth tones

## What changes

This is a **CSS and template-structure-only change**. No data, logic, scoring, or pipeline code is modified.

### Visual design

- **Font:** Nunito (Google Fonts, weights 400/600/700/800) — rounded, friendly, legible
- **Palette:** coral `#ff6b6b`, sky teal `#4ecdc4`, sunny yellow `#ffe66d`, purple `#a855f7`
- **H1:** large gradient text (coral → peach → yellow → teal) via `background-clip: text`
- **H2:** teal uppercase, heavy weight; leaderboard heading coral; player section heading purple
- **Cards:** each `<section>` becomes a white rounded card with a subtle drop shadow
- **Tables:** gradient-tinted `<thead>` rows (per-section palette), alternating even-row tint, hover highlight
- **Badges:** pill-shaped with rounded corners (radius 20px); purple/blue for pre-release, green for in theaters, gray for no projection / won't score
- **Leaderboard medals:** 🥇🥈🥉 prepended to the top three rows via CSS `::before` — no template change needed
- **Player details:** expand/collapse with a custom `▶` arrow that rotates on open; purple border on open state
- **Dark horse label:** coral, uppercase, small — prefixed with 🐴

### Dark mode

A fixed pill-shaped toggle button (🌙 / ☀️) sits in the top-right corner and persists the user's preference to `localStorage`. On first load, the site auto-detects `prefers-color-scheme: dark`. Theme is controlled by a `[data-theme]` attribute on `<html>` so CSS custom properties handle all color switching with a 0.25s transition.

Light-mode and dark-mode token sets are both defined in `style.css`. The dark palette uses a deep purple-indigo background (`#12101f`) with soft purple-tinted text (`#f0eeff`), keeping accent colors (coral, teal, yellow) at full saturation.

## Architecture

Two files change. Everything else is untouched.

```
summer_movie_wager/render/static/style.css          — complete replacement
summer_movie_wager/render/templates/index.html.j2   — targeted additions
```

`page.py` continues to read `style.css` and inject it as `{{ inline_css | safe }}` — no change needed there. The Google Fonts `<link>` tags are added to the Jinja2 template `<head>` (not to the CSS, since they are HTML elements, not CSS).

### `style.css` structure

1. CSS custom properties on `:root` (light defaults)
2. `[data-theme="dark"]` overrides
3. `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) { … } }` for OS auto-detection
4. Layout, typography, component styles (all using `var(--token)` for colors)
5. Responsive breakpoint at 600px

### `index.html.j2` changes

| Location | Change |
| --- | --- |
| `<head>`, before `<style>` | Add three `<link>` tags for Google Fonts (Nunito) |
| Top of `<body>`, before `<header>` | Add `.theme-toggle` button + inline `<script>` for dark mode init/toggle |
| Each `<section>` tag | Add `card` class |
| Each `<h2>` | Prepend emoji (🏆 leaderboard, 🎥 movies, 🎭 per-player) |
| `<p class="dark-horse-label">` | Prepend 🐴 |

All Jinja2 loops, conditionals, and data interpolations remain unchanged.

## Source of truth

The reference implementation is `docs/previews/style-1-playful.html` — specifically the `<style>` block and `<body>` structure as of 2026-06-19. The production CSS is a direct extraction of that block, restructured to use CSS custom properties throughout.

## Out of scope

- No changes to Python pipeline, scoring, scraping, or data files
- No new JavaScript beyond the 20-line dark mode init/toggle snippet
- No JS framework, build tool, or bundler introduced
- The preview files in `docs/previews/` are kept as-is for reference; they are not served by GitHub Pages

## Testing

1. Run `uv run python -m summer_movie_wager.render.build` to regenerate `docs/index.html`
2. Open `docs/index.html` in a browser — must visually match `docs/previews/style-1-playful.html`
3. Click the 🌙 toggle — dark mode applies, label flips to ☀️
4. Refresh — dark mode preference persists
5. Set OS to dark mode in a fresh private window — auto-applies without a click
6. Run `uv run pytest` — all tests pass (no logic changes, so only render snapshot test may need fixture update)
