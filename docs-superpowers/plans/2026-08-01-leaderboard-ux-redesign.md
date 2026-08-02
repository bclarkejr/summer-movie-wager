# Leaderboard UX Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `index.html` leaderboard table with a movie × player scoring matrix, a full picks grid, and per-player tables that show how each pick is trending — matching `docs/previews/index-option-1.html` exactly.

**Architecture:** A Python batch pipeline renders four static HTML pages into `docs/` with CSS inlined at build time. There is no server and no frontend build step. All work here is in the render layer (`summer_movie_wager/render/`): two small data changes in `build.py`/`page.py`, a rewritten `index.html.j2`, and a rewritten `static/style.css`. The projection and simulation models are untouched.

**Tech Stack:** Python 3.12+, uv, Jinja2, pytest, ruff. No JS frameworks; the only JS on this page is the existing inline theme toggle.

## Global Constraints

- **Reference UX:** `docs/previews/index-option-1.html` is the exact target. When this plan and the preview disagree about markup, the preview wins — except for the `.option-tag` span ("Option 1 · Faithful Recreation"), which is a mockup label and must not be ported.
- **No new dependencies.** Everything needed is already installed.
- **No new external requests.** The page's only outbound request stays the Google Fonts link already in `<head>`.
- **Jinja autoescape stays forced on** in `page.py` — movie titles and sources come from external scrapes.
- **All CSS stays inlined at build time.** `page.py` concatenates `theme.css + nav.css + style.css` for the index. Do not copy the preview's duplicated theme/nav blocks into `style.css`.
- **Line length 100** (`[tool.ruff] line-length = 100`). `uv run ruff check .` and `uv run ruff format --check .` must both pass before every commit.
- **Every command runs under `uv run`.** Never invoke bare `python`/`pytest`.
- **Never run the build without `--local`.** A production run appends a duplicate same-day row to `data/box_office_history.jsonl` and skews the decay model.
- **Commit messages follow the repo's existing style:** short imperative sentence case, no `feat:`/`fix:` prefixes (see `git log`: "Odds over time page (#2)", "Update web source for box office returns (#3)"). End every commit message with:
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`
- **Work on a feature branch,** not `main`. Create it before Task 1: `git checkout -b leaderboard-ux-redesign`. Note the working tree already has uncommitted edits to `docs/*.html`, `docs/data.json`, and `_nav.html.j2` — leave them alone; they come along on the branch.
- **The HTML snapshot test self-heals.** `tests/fixtures/expected_index.html` is a byte-exact snapshot. Any task that changes rendered markup must delete it, run pytest once (it rewrites the fixture and fails by design), then run pytest again to lock it. Both runs are written out explicitly in the tasks that need them.

---

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `summer_movie_wager/render/build.py` | Pipeline; assembles `RenderInput` | `_build_player_details` gains `movie_rows`; `_pick_detail` reads rank + gross from the movie catalog; `PlayerDetail` gets `win_prob` |
| `summer_movie_wager/render/page.py` | Render dataclasses; renders templates to files | `PlayerDetail.win_prob` field; two derived lookups passed to the index template |
| `summer_movie_wager/render/templates/index.html.j2` | Index markup | Body rewritten into four sections |
| `summer_movie_wager/render/static/style.css` | Index-only styling | Rewritten to the preview's rules |
| `summer_movie_wager/render/static/theme.css` | Theme tokens, shared by all four pages | One token added |
| `tests/test_build.py` | `build.py` helper tests | Two new tests + one shared fixture helper |
| `tests/test_render_snapshot.py` | Render output tests | Fixture gains a second player; five new tests |
| `tests/fixtures/expected_index.html` | Byte-exact snapshot | Regenerated |

Untouched: `nav.css`, `shared.css`, `_nav.html.j2`, `_theme.html.j2`, `scenarios.html.j2`, `whatif.html.j2`, `history.html.j2`, and every model/ingest module.

---

### Task 1: `projected_rank` becomes a catalog rank

Today `PickDetail.projected_rank` is a film's position *within the projected top 10*, and `None` for everything else. The new per-player table shows ranks like `#31` and `#37` — position across the whole catalog, the same number the Movies table prints. Repurpose the field rather than adding a second one, so exactly one notion of "projected rank" exists.

While we're here, `_pick_detail` starts reading the projected gross from the same catalog too, so the dollar figure in a player's table is guaranteed to equal the one in the Movies table.

**Scoring is not touched.** Points still come from `median_position`, which is still derived from `projections`.

**Files:**
- Modify: `summer_movie_wager/render/build.py` (`_build_player_details` ~line 887, `_pick_detail` ~line 943, call site ~line 212)
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `_build_player_details(snapshot, projections, current_pts, sim, movie_rows) -> list[PlayerDetail]` — `movie_rows: list[MovieRow]` appended as the fifth positional parameter.
  - `_pick_detail(title, predicted_rank, catalog, median_position, *, kind) -> PickDetail` — `catalog: dict[str, tuple[int, float]]` mapping title → `(catalog_rank, median_gross)`, replacing the old `proj_by_title` parameter.
  - `PickDetail.projected_rank` now means catalog rank (1-based index into `movie_rows`), `None` only if the title is absent from the catalog.
  - Test helper `_catalog_for(titles) -> tuple[list[Projection], list[MovieRow]]` in `tests/test_build.py`, reused by Task 2.

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/test_build.py`:

```python
def _catalog_for(titles):
    """A projected catalog for `titles`, grossing strictly descending in list order.

    Returns (projections, movie_rows) — the same pair main() hands to
    _build_player_details, so film N in `titles` lands at catalog rank N+1.
    """
    from summer_movie_wager.render.build import _build_movie_rows

    movies = {
        t: {
            "title": t,
            "release_date": date(2026, 6, 1),
            "status": MovieStatus.IN_THEATERS,
            "category": Category.WIDE,
            "cumulative": 0.0,
        }
        for t in titles
    }
    projections = [
        Projection(movie_title=t, median_in_window_gross=float(1300 - 100 * i), sigma=0.1)
        for i, t in enumerate(titles)
    ]
    return projections, _build_movie_rows(movies, projections)


def test_projected_rank_covers_films_outside_the_top_10():
    # projected_rank is the film's row number in the Movies table, not its
    # position inside the projected top 10. A pick that misses the top 10 scores
    # nothing but still carries a rank, so the per-player table can show "#11".
    from summer_movie_wager.render.build import _build_player_details

    snap = _snapshot(_THIRTEEN)
    projections, movie_rows = _catalog_for(_THIRTEEN)

    details = _build_player_details(snap, projections, {"bclarke": 0}, None, movie_rows)

    assert [p.projected_rank for p in details[0].ranked] == list(range(1, 11))
    # Film 10 is the first dark horse and finishes 11th — outside the top 10.
    dh = details[0].dark_horses[0]
    assert dh.projected_rank == 11
    assert dh.projected_pts == 0


def test_pick_gross_matches_the_movie_catalog():
    # The dollar figure in a player's table must be the same number the Movies
    # table prints for that film — both now come from movie_rows.
    from summer_movie_wager.render.build import _build_player_details

    snap = _snapshot(_THIRTEEN)
    projections, movie_rows = _catalog_for(_THIRTEEN)

    details = _build_player_details(snap, projections, {"bclarke": 0}, None, movie_rows)

    by_title = {row.title: row.median_in_window_gross for row in movie_rows}
    for pick in details[0].ranked + details[0].dark_horses:
        assert pick.projected_gross == by_title[pick.title]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_build.py -k "projected_rank_covers or pick_gross_matches" -v`

Expected: FAIL. `_build_player_details()` takes 4 positional arguments but 5 were given.

- [ ] **Step 3: Change `_build_player_details` to build and pass the catalog**

In `summer_movie_wager/render/build.py`, change the signature and add the catalog. Replace the `def` line and the docstring's final paragraph:

```python
def _build_player_details(
    snapshot: SiteSnapshot,
    projections: list[Projection],
    current_pts: dict[str, int],
    sim: Any | None,
    movie_rows: list[MovieRow],
) -> list[PlayerDetail]:
```

Immediately after the docstring, before the existing `proj_by_title = ...` line, insert:

```python
    # Rank and gross both come from movie_rows, which is what the Movies table
    # renders — so a pick's "#12 · $92,883,017" is always the same row the
    # catalog shows. median_position below stays keyed off `projections`
    # because it decides POINTS, and re-deriving it here would change scoring
    # behaviour for exactly-tied grosses. The two orderings agree everywhere
    # else.
    catalog = {
        row.title: (i + 1, row.median_in_window_gross) for i, row in enumerate(movie_rows)
    }
```

Then change the two `_pick_detail` calls in the same function to pass `catalog` instead of `proj_by_title`:

```python
        ranked_details = [
            _pick_detail(title, idx + 1, catalog, median_position, kind="ranked")
            for idx, title in enumerate(picks.ranked)
        ]
        dh_details = [
            _pick_detail(title, None, catalog, median_position, kind="dark_horse")
            for title in picks.dark_horses
        ]
```

- [ ] **Step 4: Change `_pick_detail` to read from the catalog**

Replace `_pick_detail` (~line 943) with:

```python
def _pick_detail(
    title: str,
    predicted_rank: int | None,
    catalog: dict[str, tuple[int, float]],
    median_position: dict[str, int],
    *,
    kind: str,
) -> PickDetail:
    """
    For a given pick, determine the pick's projected rank, projected gross, and projected points.

    `catalog` maps every projected film to (catalog rank, median gross) — its row in the
    Movies table. `median_position` holds only the projected top 10, which is what scores.
    """

    catalog_rank, median_gross = catalog.get(title, (None, 0.0))

    # This is the key.  Based on the picks projected gross (and all other movies' projected
    # grosses), we can determine the pick's projected rank and projected points.
    # This allows us to project the points for each pick and by extension, the player's total
    # projected points at the end of the wager.
    actual_rank = median_position.get(title, 0)

    if kind == "ranked" and actual_rank > 0 and predicted_rank is not None:
        pts = ranked_pick_points(predicted_rank, actual_rank)
    elif kind == "dark_horse" and actual_rank > 0:
        pts = 1
    else:
        pts = 0
    return PickDetail(
        title=title,
        projected_rank=catalog_rank,
        projected_gross=median_gross,
        projected_pts=pts,
    )
```

- [ ] **Step 5: Update the call site in `main()`**

At ~line 212 in `build.py`, `movie_rows` is already built one line above the `player_details` call. Change:

```python
    player_details = _build_player_details(snapshot, projections, current_pts, sim, movie_rows)
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_build.py -v`

Expected: PASS, all tests in the file.

- [ ] **Step 7: Run the full suite**

Run: `uv run pytest`

Expected: PASS. `tests/test_render_snapshot.py` is unaffected — it constructs `PickDetail` directly and never calls `_pick_detail`.

- [ ] **Step 8: Lint and commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add summer_movie_wager/render/build.py tests/test_build.py
git commit -m "Projected rank spans the whole movie catalog

The per-player table needs a film's row number in the Movies table, not its
position inside the projected top 10. Rank and gross now both come from
movie_rows; scoring still keys off the top-10 position map.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `PlayerDetail` carries win odds

Win odds live only on `LeaderboardRow` today. The redesigned index needs them per player, and putting them on `PlayerDetail` lets the index template iterate exactly one ordered list — the matrix columns, the picks grid, and the accordion then cannot fall out of order with each other. `leaderboard` stays exactly as it is, feeding the scenarios, whatif, and history payloads.

**Files:**
- Modify: `summer_movie_wager/render/page.py:55-62` (`PlayerDetail`)
- Modify: `summer_movie_wager/render/build.py` (`_build_player_details`, the `PlayerDetail(...)` construction)
- Test: `tests/test_build.py`

**Interfaces:**
- Consumes: `_catalog_for(titles)` and `_build_player_details(..., movie_rows)` from Task 1.
- Produces: `PlayerDetail.win_prob: float | None = None` — defaulted, so the existing test constructions that omit it keep working.

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/test_build.py`:

```python
def test_player_detail_carries_win_prob_from_the_sim():
    # The index reads win odds off PlayerDetail so every player-facing section
    # can iterate one list instead of joining against the leaderboard.
    from types import SimpleNamespace

    from summer_movie_wager.render.build import _build_player_details

    snap = _snapshot(_THIRTEEN)
    projections, movie_rows = _catalog_for(_THIRTEEN)
    sim = SimpleNamespace(
        median_final_pts={"bclarke": 42.0},
        win_prob={"bclarke": 0.25},
    )

    details = _build_player_details(snap, projections, {"bclarke": 7}, sim, movie_rows)

    assert details[0].win_prob == 0.25
    assert details[0].median_pts == 42.0


def test_player_detail_win_prob_is_none_without_a_sim():
    from summer_movie_wager.render.build import _build_player_details

    snap = _snapshot(_THIRTEEN)
    projections, movie_rows = _catalog_for(_THIRTEEN)

    details = _build_player_details(snap, projections, {"bclarke": 7}, None, movie_rows)

    assert details[0].win_prob is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_build.py -k win_prob -v`

Expected: FAIL with `AttributeError: 'PlayerDetail' object has no attribute 'win_prob'`.

- [ ] **Step 3: Add the field**

In `summer_movie_wager/render/page.py`, replace the `PlayerDetail` dataclass:

```python
@dataclass(frozen=True)
class PlayerDetail:
    username: str
    median_pts: float | None
    current_pts: int
    ranked: list[PickDetail]
    dark_horses: list[PickDetail]
    win_prob: float | None = None
```

- [ ] **Step 4: Populate it**

In `build.py`, in `_build_player_details`, change the `PlayerDetail(...)` construction:

```python
        out.append(
            PlayerDetail(
                username=username,
                median_pts=sim.median_final_pts[username] if sim is not None else None,
                current_pts=current_pts.get(username, 0),
                ranked=ranked_details,
                dark_horses=dh_details,
                win_prob=sim.win_prob[username] if sim is not None else None,
            )
        )
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_build.py -k win_prob -v`

Expected: PASS (2 tests).

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest`

Expected: PASS. The defaulted field keeps `tests/test_render_snapshot.py`'s existing `PlayerDetail(...)` constructions valid.

- [ ] **Step 7: Lint and commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add summer_movie_wager/render/page.py summer_movie_wager/render/build.py tests/test_build.py
git commit -m "Carry win odds on PlayerDetail

Lets the index template drive every player-facing section from one ordered
list instead of joining player details against the leaderboard.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: The Projected Standings matrix

Replace the leaderboard table with the movie × player matrix. This is the largest single change: it adds two derived lookups in `page.py`, rewrites the first section of the template, and rebuilds the snapshot fixture so it actually has two player columns to compare.

**Files:**
- Modify: `summer_movie_wager/render/page.py` (`render()`, ~line 106-121)
- Modify: `summer_movie_wager/render/templates/index.html.j2` (replace the `<section class="leaderboard card">` block)
- Modify: `tests/test_render_snapshot.py` (`_fixture_input`, new tests)
- Regenerate: `tests/fixtures/expected_index.html`

**Interfaces:**
- Consumes: `PlayerDetail.win_prob` (Task 2), `PickDetail.projected_rank` as catalog rank (Task 1).
- Produces, into the index template's context:
  - `pts_by_player: dict[str, dict[str, int]]` — username → {movie title → projected points}. A title absent from the inner dict means that player didn't pick it.
  - `projected_totals: dict[str, int]` — username → sum of that player's pick points.
  - Template-local `{% set n = player_details | length %}`, used for divider colspans in Tasks 3 and 4.

- [ ] **Step 1: Rebuild the snapshot fixture input**

The current `_fixture_input()` has two `LeaderboardRow`s but one `PlayerDetail`, which would render a one-column matrix and prove nothing. Replace the `player_details=[...]` block and the `movies=[...]` block in `tests/test_render_snapshot.py::_fixture_input` with the following. The new third movie gives us a film that scores nothing, and bclarke picking neither of the last two gives us em-dash cells.

```python
        movies=[
            MovieRow(
                title="Spider-Man: Brand New Day",
                release_date="2026-07-31",
                status="pre_release",
                status_label="pre-release",
                median_in_window_gross=380_000_000,
                p10=290_000_000,
                p90=470_000_000,
                cumulative_to_date=None,
                source="Box Office Pro · high",
            ),
            MovieRow(
                title="The Devil Wears Prada 2",
                release_date="2026-05-01",
                status="in_theaters",
                status_label="in theaters",
                median_in_window_gross=170_000_000,
                p10=140_000_000,
                p90=210_000_000,
                cumulative_to_date=32_500_000,
                source="decay model · 1 wk",
            ),
            MovieRow(
                title="Coyote vs. Acme",
                release_date="2026-08-28",
                status="no_projection",
                status_label="no projection",
                median_in_window_gross=0,
                p10=0,
                p90=0,
                cumulative_to_date=None,
                source="no analyst entry",
            ),
        ],
        player_details=[
            # vivrad's three ranked picks cover all three Diff arrows: pick 1
            # projects #2 (down), pick 2 projects #1 (up), pick 3 projects #3 (flat).
            PlayerDetail(
                username="vivrad",
                median_pts=91.0,
                current_pts=3,
                win_prob=0.28,
                ranked=[
                    PickDetail(
                        title="The Devil Wears Prada 2",
                        projected_rank=2,
                        projected_gross=170_000_000,
                        projected_pts=7,
                    ),
                    PickDetail(
                        title="Spider-Man: Brand New Day",
                        projected_rank=1,
                        projected_gross=380_000_000,
                        projected_pts=7,
                    ),
                    PickDetail(
                        title="Coyote vs. Acme",
                        projected_rank=3,
                        projected_gross=0,
                        projected_pts=0,
                    ),
                ],
                dark_horses=[
                    PickDetail(
                        title="Toy Story 5", projected_rank=None, projected_gross=0, projected_pts=0
                    ),
                ],
            ),
            # bclarke picked neither Prada nor Coyote, so those cells are em-dashes,
            # and their column totals 13 against vivrad's 14.
            PlayerDetail(
                username="bclarke",
                median_pts=85.0,
                current_pts=3,
                win_prob=0.19,
                ranked=[
                    PickDetail(
                        title="Spider-Man: Brand New Day",
                        projected_rank=1,
                        projected_gross=380_000_000,
                        projected_pts=13,
                    ),
                ],
                dark_horses=[
                    PickDetail(
                        title="Backrooms", projected_rank=None, projected_gross=0, projected_pts=0
                    ),
                ],
            ),
        ],
```

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_render_snapshot.py`, after `test_render_writes_data_json`:

```python
def test_matrix_dashes_movies_a_player_did_not_pick(tmp_path: Path):
    # bclarke picked neither The Devil Wears Prada 2 nor Coyote vs. Acme. Those
    # cells must read "—", not "0" — a zero would claim they bet and lost.
    render(tmp_path, _fixture_input())
    html = (tmp_path / "index.html").read_text()
    matrix = html.split('<section class="matrix card">')[1].split("</section>")[0]
    assert matrix.count('<td class="muted" style="text-align:center;">—</td>') == 2
    # vivrad picked Coyote, which projects nothing: a grey zero, not a dash.
    assert '<td style="text-align:center;" class="pt0">0</td>' in matrix


def test_matrix_footer_sums_the_column_not_the_sim_median(tmp_path: Path):
    # With the components sitting directly above it, the total has to add up.
    # vivrad 7+7+0+0 = 14, bclarke 13+0 = 13 — not the sim medians (91, 85).
    render(tmp_path, _fixture_input())
    html = (tmp_path / "index.html").read_text()
    footer = html.split("<tfoot>")[1].split("</tfoot>")[0]
    assert ">14</td>" in footer
    assert ">13</td>" in footer
    assert ">91</td>" not in footer
    assert ">85</td>" not in footer
    assert ">28%</td>" in footer  # vivrad's win odds


def test_matrix_shows_at_most_fifteen_movies(tmp_path: Path):
    # The matrix is the top 15 with a divider after #10; the Movies section
    # below it is the place to see everything.
    data = _fixture_input()
    many = list(data.movies) * 9  # 27 rows
    data = RenderInput(
        generated_at=data.generated_at,
        leaderboard=data.leaderboard,
        movies=many,
        player_details=data.player_details,
        raw_snapshot=data.raw_snapshot,
    )
    render(tmp_path, data)
    html = (tmp_path / "index.html").read_text()
    matrix = html.split('<section class="matrix card">')[1].split("</section>")[0]
    assert "Outside the top 10" in matrix
    assert "<td>15</td>" in matrix
    assert "<td>16</td>" not in matrix


def test_matrix_divider_is_omitted_when_nothing_follows_it(tmp_path: Path):
    # Three movies: a "top 10" divider with no rows under it would be nonsense.
    render(tmp_path, _fixture_input())
    html = (tmp_path / "index.html").read_text()
    assert "Outside the top 10" not in html
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run pytest tests/test_render_snapshot.py -k matrix -v`

Expected: FAIL with `IndexError: list index out of range` — the string `<section class="matrix card">` does not exist yet.

- [ ] **Step 4: Add the derived lookups to `page.py`**

In `render()`, immediately before `html = template.render(`, insert:

```python
    # Two lookups the index matrix needs. pts_by_player is keyed title-by-title
    # so a missing key means "didn't pick it" (renders "—") and a present zero
    # means "picked it, projects nothing" (renders a grey 0).
    pts_by_player = {
        p.username: {d.title: d.projected_pts for d in p.ranked + p.dark_horses}
        for p in data.player_details
    }
    # The projected total shown on the page is the sum of a player's own picks --
    # the same cells printed above it in the matrix, so the column adds up. This
    # is deliberately NOT sim.median_final_pts, which is a distribution median and
    # can differ by a point. Column ORDER still follows the sim median (that is
    # what win odds are derived from, and what scenarios.html/whatif.html use), so
    # a column can occasionally out-total the one to its left.
    projected_totals = {
        p.username: sum(d.projected_pts for d in p.ranked + p.dark_horses)
        for p in data.player_details
    }
```

Then add both to the `template.render(...)` call for the index (leave the other three page renders alone):

```python
    html = template.render(
        generated_at=data.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        leaderboard=data.leaderboard,
        movies=data.movies,
        player_details=data.player_details,
        pts_by_player=pts_by_player,
        projected_totals=projected_totals,
        inline_css=inline_css,
        active="index",
        forecast_available=data.forecast_available,
        forecast_unavailable_reason=data.forecast_unavailable_reason,
    )
```

- [ ] **Step 5: Replace the leaderboard section in the template**

In `templates/index.html.j2`, insert the `n` binding after the `</header>` line, then replace the whole `<section class="leaderboard card"> … </section>` block (lines 20-41) with the matrix. The `forecast-unavailable` notice moves here.

```jinja
{% set n = player_details | length %}

<section class="matrix card">
  <h2>🏆 Projected Standings</h2>
  {% if not forecast_available %}
  <p class="meta forecast-unavailable">Forecast unavailable — {{ forecast_unavailable_reason }}. Showing current points only.</p>
  {% endif %}
  <table>
    <thead>
      <tr><th>#</th><th>Movie</th><th>Projected median</th>{% for p in player_details %}<th style="text-align:center;">{{ p.username }}</th>{% endfor %}</tr>
    </thead>
    <tbody>
    {% for movie in movies[:15] %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>{{ movie.title }}</td>
        <td>${{ '{:,.0f}'.format(movie.median_in_window_gross) }}</td>
        {%- for p in player_details %}
        {%- set pts = pts_by_player[p.username].get(movie.title) %}
        {% if pts is none %}<td class="muted" style="text-align:center;">—</td>{% else %}<td style="text-align:center;" class="{{ 'ptpos' if pts else 'pt0' }}">{{ pts }}</td>{% endif %}
        {%- endfor %}
      </tr>
      {% if loop.index == 10 and not loop.last %}
      <tr class="tier-divider"><td colspan="{{ n + 3 }}">Outside the top 10</td></tr>
      {% endif %}
    {% endfor %}
    </tbody>
    <tfoot>
      <tr class="matrix-footer"><td colspan="3">Projected pts</td>{% for p in player_details %}<td style="text-align:center;">{{ projected_totals[p.username] }}</td>{% endfor %}</tr>
      <tr class="matrix-footer"><td colspan="3">Win odds</td>{% for p in player_details %}<td style="text-align:center;">{% if p.win_prob is none %}—{% else %}{{ '%.0f'|format(p.win_prob * 100) }}%{% endif %}</td>{% endfor %}</tr>
    </tfoot>
  </table>
</section>
```

Two details that matter:
- `movies[:15]` means `loop.last` refers to the *slice*, so with exactly 10 movies the divider is correctly skipped.
- The `{%-` whitespace-trim markers keep each `<td>` on its own line without leading spaces, which is what the `matrix.count(...)` assertion in Step 2 relies on.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `uv run pytest tests/test_render_snapshot.py -k matrix -v`

Expected: PASS (4 tests).

- [ ] **Step 7: Regenerate the snapshot**

```bash
rm -f tests/fixtures/expected_index.html
uv run pytest tests/test_render_snapshot.py::test_render_matches_expected_snapshot
uv run pytest tests/test_render_snapshot.py::test_render_matches_expected_snapshot
```

Expected: the first run FAILS with "expected_index.html did not exist — wrote it now from this run"; the second run PASSES.

- [ ] **Step 8: Run the full suite**

Run: `uv run pytest`

Expected: PASS. `test_render_escapes_html_in_scraped_fields` still passes — it renders with `player_details=[]`, and the matrix's per-player loops are simply empty.

- [ ] **Step 9: Lint and commit**

```bash
uv run ruff check . && uv run ruff format --check .
git add summer_movie_wager/render/page.py summer_movie_wager/render/templates/index.html.j2 tests/test_render_snapshot.py tests/fixtures/expected_index.html
git commit -m "Replace the leaderboard table with a scoring matrix

Films are rows, players are columns, and each cell is what that film is worth
to that player. The footer totals the column rather than reporting the
simulated median, so the table adds up.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: All Players' Lists

A new section: every player's 10 ranked picks and 3 dark horses side by side, no clicking. The picks are public and locked, so there is nothing to hide.

**Files:**
- Modify: `summer_movie_wager/render/templates/index.html.j2` (new section after the matrix)
- Modify: `tests/test_render_snapshot.py`
- Regenerate: `tests/fixtures/expected_index.html`

**Interfaces:**
- Consumes: `player_details` and template-local `n` from Task 3.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_render_snapshot.py`:

```python
def test_picks_grid_lists_every_player_side_by_side(tmp_path: Path):
    render(tmp_path, _fixture_input())
    html = (tmp_path / "index.html").read_text()
    picks = html.split('<section class="picks card">')[1].split("</section>")[0]
    # Row count comes from the longest list: vivrad has three ranked picks.
    assert ">Pick 1</td>" in picks
    assert ">Pick 3</td>" in picks
    assert ">Pick 4</td>" not in picks
    assert "🐴 Dark Horse 1" in picks
    assert "Coyote vs. Acme" in picks  # vivrad's third pick
    assert "Backrooms" in picks  # bclarke's dark horse
    # bclarke has one ranked pick, so their pick-2 and pick-3 cells are blank.
    assert picks.count("<td></td>") == 2


def test_picks_grid_survives_having_no_players(tmp_path: Path):
    # The row count uses a max filter, which returns Undefined on an empty
    # sequence. Without the default the build would die here.
    index, _scenarios, _whatif = _render_pages(tmp_path, True)
    assert '<section class="picks card">' in index
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_render_snapshot.py -k picks_grid -v`

Expected: FAIL with `IndexError: list index out of range` — the picks section does not exist yet.

- [ ] **Step 3: Add the section**

In `templates/index.html.j2`, insert immediately after the closing `</section>` of the matrix:

```jinja
{# `| max` returns Undefined on an empty sequence, so `| default(0)` is what
   keeps a player-less render (see the nav/theme tests) from dying here. #}
{% set n_ranked = player_details | map(attribute='ranked') | map('length') | max | default(0) %}
{% set n_dh = player_details | map(attribute='dark_horses') | map('length') | max | default(0) %}

<section class="picks card">
  <h2>📋 All Players' Lists</h2>
  <table>
    <thead>
      <tr><th></th>{% for p in player_details %}<th style="text-align:center;">{{ p.username }}</th>{% endfor %}</tr>
    </thead>
    <tbody>
    {% for i in range(n_ranked) %}
      <tr><td class="muted">Pick {{ i + 1 }}</td>{% for p in player_details %}<td>{% if i < p.ranked | length %}{{ p.ranked[i].title }}{% endif %}</td>{% endfor %}</tr>
    {% endfor %}
    {% if n_dh %}
      <tr class="tier-divider"><td colspan="{{ n + 1 }}">Dark Horses</td></tr>
      {% for i in range(n_dh) %}
      <tr><td class="muted">🐴 Dark Horse {{ i + 1 }}</td>{% for p in player_details %}<td>{% if i < p.dark_horses | length %}{{ p.dark_horses[i].title }}{% endif %}</td>{% endfor %}</tr>
      {% endfor %}
    {% endif %}
    </tbody>
  </table>
</section>
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_render_snapshot.py -k picks_grid -v`

Expected: PASS (2 tests).

- [ ] **Step 5: Regenerate the snapshot**

```bash
rm -f tests/fixtures/expected_index.html
uv run pytest tests/test_render_snapshot.py::test_render_matches_expected_snapshot
uv run pytest tests/test_render_snapshot.py::test_render_matches_expected_snapshot
```

Expected: first run FAILS and writes the fixture; second run PASSES.

- [ ] **Step 6: Run the full suite and commit**

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
git add summer_movie_wager/render/templates/index.html.j2 tests/test_render_snapshot.py tests/fixtures/expected_index.html
git commit -m "Show every player's picks side by side

The lists are public and locked, so there is no reason to make people expand
an accordion to compare them.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Per-player detail tables

Turn each player's bullet lists into a table with the new **Diff** column — how far the projection has moved a film from where the player ranked it. Dark horses become divider-separated rows inside the same table.

**Files:**
- Modify: `summer_movie_wager/render/templates/index.html.j2` (replace the `<section class="players card">` block)
- Modify: `tests/test_render_snapshot.py`
- Regenerate: `tests/fixtures/expected_index.html`

**Interfaces:**
- Consumes: `projected_totals` (Task 3), `PlayerDetail.win_prob` (Task 2), `PickDetail.projected_rank` as catalog rank (Task 1).
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_render_snapshot.py`:

```python
def test_per_player_table_shows_diff_arrows(tmp_path: Path):
    # Diff = pick position - projected rank. vivrad's list covers all three cases.
    render(tmp_path, _fixture_input())
    html = (tmp_path / "index.html").read_text()
    detail = html.split('<details data-player="vivrad">')[1].split("</details>")[0]
    assert 'class="diff-down">▼ 1</td>' in detail  # pick 1 projects #2
    assert 'class="diff-up">▲ 1</td>' in detail  # pick 2 projects #1
    assert 'class="diff-flat">–</td>' in detail  # pick 3 projects #3


def test_per_player_stats_line_matches_the_matrix_footer(tmp_path: Path):
    # The two places a player's projected score appears must agree.
    render(tmp_path, _fixture_input())
    html = (tmp_path / "index.html").read_text()
    detail = html.split('<details data-player="vivrad">')[1].split("</details>")[0]
    assert "<strong>14 pts</strong> projected" in detail
    assert "3 pts current" in detail
    assert "28% win" in detail


def test_per_player_dark_horses_have_a_divider_and_no_diff(tmp_path: Path):
    # A dark horse has no predicted position, so there is nothing to diff against.
    render(tmp_path, _fixture_input())
    html = (tmp_path / "index.html").read_text()
    detail = html.split('<details data-player="bclarke">')[1].split("</details>")[0]
    assert '<tr class="dh-divider"><td colspan="6">Dark Horses</td></tr>' in detail
    assert "<td>🐴</td>" in detail
    # Backrooms is not in the movie catalog: rank and diff both fall back to "—".
    assert '<td style="text-align:center;">—</td>' in detail
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_render_snapshot.py -k per_player -v`

Expected: FAIL — `diff-down` and the stats line do not exist; the old template renders `<ol class="ranked-picks">`.

- [ ] **Step 3: Replace the players section**

In `templates/index.html.j2`, replace the whole `<section class="players card"> … </section>` block with:

```jinja
<section class="players card">
  <h2>🎭 Per-player detail</h2>
  {% for player in player_details %}
  <details data-player="{{ player.username }}">
    <summary>{{ player.username }}</summary>
    <p class="player-stats"><strong>{{ projected_totals[player.username] }} pts</strong> projected &nbsp;·&nbsp; {{ player.current_pts }} pts current &nbsp;·&nbsp; {% if player.win_prob is none %}—{% else %}{{ '%.0f'|format(player.win_prob * 100) }}%{% endif %} win</p>
    <table class="player-table">
      <thead><tr><th>#</th><th>Movie</th><th>Projected rank</th><th>Diff</th><th>Projected gross</th><th>Pts</th></tr></thead>
      <tbody>
      {% for pick in player.ranked %}
        <tr>
          <td>{{ loop.index }}</td>
          <td>{{ pick.title }}</td>
          <td style="text-align:center;">{% if pick.projected_rank is none %}—{% else %}#{{ pick.projected_rank }}{% endif %}</td>
          {%- if pick.projected_rank is none %}
          <td style="text-align:center;">—</td>
          {%- else %}
          {%- set d = loop.index - pick.projected_rank %}
          {% if d > 0 %}<td style="text-align:center;" class="diff-up">▲ {{ d }}</td>{% elif d < 0 %}<td style="text-align:center;" class="diff-down">▼ {{ -d }}</td>{% else %}<td style="text-align:center;" class="diff-flat">–</td>{% endif %}
          {%- endif %}
          <td>${{ '{:,.0f}'.format(pick.projected_gross) }}</td>
          <td style="text-align:center;" class="{{ 'ptpos' if pick.projected_pts else 'pt0' }}">{{ pick.projected_pts }}</td>
        </tr>
      {% endfor %}
      {% if player.dark_horses %}
        <tr class="dh-divider"><td colspan="6">Dark Horses</td></tr>
        {% for dh in player.dark_horses %}
        <tr>
          <td>🐴</td>
          <td>{{ dh.title }}</td>
          <td style="text-align:center;">{% if dh.projected_rank is none %}—{% else %}#{{ dh.projected_rank }}{% endif %}</td>
          <td style="text-align:center;">—</td>
          <td>${{ '{:,.0f}'.format(dh.projected_gross) }}</td>
          <td style="text-align:center;" class="{{ 'ptpos' if dh.projected_pts else 'pt0' }}">{{ dh.projected_pts }}</td>
        </tr>
        {% endfor %}
      {% endif %}
      </tbody>
    </table>
  </details>
  {% endfor %}
</section>
```

A pick whose title is missing from the movie catalog has `projected_rank is none`, so the Diff arithmetic is skipped rather than raising. `_normalize_movies` unions every player's picks into the catalog, so this should never fire in production — but the fixture's off-catalog dark horses exercise it.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_render_snapshot.py -k per_player -v`

Expected: PASS (3 tests).

- [ ] **Step 5: Regenerate the snapshot**

```bash
rm -f tests/fixtures/expected_index.html
uv run pytest tests/test_render_snapshot.py::test_render_matches_expected_snapshot
uv run pytest tests/test_render_snapshot.py::test_render_matches_expected_snapshot
```

Expected: first run FAILS and writes the fixture; second run PASSES.

- [ ] **Step 6: Run the full suite and commit**

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
git add summer_movie_wager/render/templates/index.html.j2 tests/test_render_snapshot.py tests/fixtures/expected_index.html
git commit -m "Per-player picks become a table with a Diff column

Shows how far the projection has moved each film from where the player ranked
it, which a bullet list could not.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Collapse and number the Movies section

Same content, now numbered and behind a `<details>` toggle. Thirty-seven always-expanded rows were burying the per-player section underneath them.

**Files:**
- Modify: `summer_movie_wager/render/templates/index.html.j2` (replace the `<section class="movies card">` block)
- Modify: `tests/test_render_snapshot.py`
- Regenerate: `tests/fixtures/expected_index.html`

**Interfaces:**
- Consumes: `movies` (unchanged from before this plan).
- Produces: the `details.movies-toggle` markup that Task 7's CSS styles.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_render_snapshot.py`:

```python
def test_movies_section_is_collapsible_and_numbered(tmp_path: Path):
    render(tmp_path, _fixture_input())
    html = (tmp_path / "index.html").read_text()
    assert '<details class="movies card movies-toggle">' in html
    assert "<summary><h2>🎥 Movies (projected window gross)</h2></summary>" in html
    movies = html.split('<details class="movies card movies-toggle">')[1]
    assert "<th>#</th>" in movies
    assert "<td>3</td>" in movies  # all three movies, not just the matrix's 15
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_render_snapshot.py -k movies_section -v`

Expected: FAIL — the section is still `<section class="movies card">`.

- [ ] **Step 3: Replace the movies section**

In `templates/index.html.j2`, replace the whole `<section class="movies card"> … </section>` block with:

```jinja
<details class="movies card movies-toggle">
  <summary><h2>🎥 Movies (projected window gross)</h2></summary>
  <table>
    <thead>
      <tr><th>#</th><th>Movie</th><th>Released</th><th>Status</th><th>Projected median</th><th>80% range</th><th>Cumulative</th><th>Source</th></tr>
    </thead>
    <tbody>
    {% for movie in movies %}
      <tr>
        <td>{{ loop.index }}</td>
        <td>{{ movie.title }}</td>
        <td>{{ movie.release_date }}</td>
        <td><span class="badge badge-{{ movie.status }}">{{ movie.status_label }}</span></td>
        <td>${{ '{:,.0f}'.format(movie.median_in_window_gross) }}</td>
        <td>[${{ '{:,.0f}'.format(movie.p10) }} – ${{ '{:,.0f}'.format(movie.p90) }}]</td>
        <td>{% if movie.cumulative_to_date %}${{ '{:,.0f}'.format(movie.cumulative_to_date) }}{% else %}—{% endif %}</td>
        <td class="source">{{ movie.source }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
</details>
```

Note the section order in the finished template: header → matrix → picks → players → movies → footer. The movies block moves *below* the players section; make sure the old one is deleted, not duplicated.

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_render_snapshot.py -k movies_section -v`

Expected: PASS.

- [ ] **Step 5: Regenerate the snapshot**

```bash
rm -f tests/fixtures/expected_index.html
uv run pytest tests/test_render_snapshot.py::test_render_matches_expected_snapshot
uv run pytest tests/test_render_snapshot.py::test_render_matches_expected_snapshot
```

Expected: first run FAILS and writes the fixture; second run PASSES.

- [ ] **Step 6: Run the full suite and commit**

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
git add summer_movie_wager/render/templates/index.html.j2 tests/test_render_snapshot.py tests/fixtures/expected_index.html
git commit -m "Collapse the movies table behind a toggle

Reference data, not the headline — 37 expanded rows were burying the
per-player section under them.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: Styling

Port the preview's index-specific CSS. `page.py` already inlines `theme.css + nav.css + style.css` for this page, so only the index-specific rules go into `style.css` — do not copy the preview's duplicated theme and nav blocks.

**Deviation from the spec, deliberate:** the spec says two tokens are added to `theme.css`. Only `--pos-color` gets added. The preview also declares `--pos-bg`, but nothing in the preview ever references it; an unused token is dead weight.

**Files:**
- Modify: `summer_movie_wager/render/static/theme.css` (three token blocks)
- Rewrite: `summer_movie_wager/render/static/style.css`
- Modify: `tests/test_render_snapshot.py`
- Regenerate: `tests/fixtures/expected_index.html`

**Interfaces:**
- Consumes: class names emitted in Tasks 3-6 — `.matrix`, `.picks`, `.players`, `.movies`, `.ptpos`, `.pt0`, `tr.tier-divider`, `.matrix-footer`, `table.player-table`, `tr.dh-divider`, `.player-stats`, `.diff-up`, `.diff-down`, `.diff-flat`, `details.movies-toggle`.
- Produces: nothing later tasks depend on.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_render_snapshot.py`:

```python
def test_index_css_covers_the_new_sections(tmp_path: Path):
    index, _scenarios, _whatif = _render_pages(tmp_path, True)
    assert "--pos-color:" in index  # new token, all three theme blocks
    assert ".ptpos" in index
    assert "tr.tier-divider" in index
    assert "table.player-table" in index
    assert "details.movies-toggle" in index
    assert ".forecast-unavailable" in index  # notice still styled
    # Rules for markup that no longer exists must go, not linger.
    assert ".player-row" not in index  # the medal ::before rules
    assert ".ranked-picks" not in index
    assert ".dark-horse-label" not in index
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_render_snapshot.py -k index_css -v`

Expected: FAIL on `assert "--pos-color:" in index`.

- [ ] **Step 3: Add the token to `theme.css`**

`theme.css` declares the same token set three times: `:root`, `[data-theme="dark"]`, and the `@media (prefers-color-scheme: dark)` block. Add `--pos-color` to all three, next to the existing `--zero` line.

In `:root`:

```css
  --zero:          #bdbdbd;
  --pos-color:     #128a5e;
```

In **both** `[data-theme="dark"]` and the `prefers-color-scheme` block (indented one more level in the latter, matching its neighbours):

```css
  --zero:          #4a4266;
  --pos-color:     #4ecdc4;
```

- [ ] **Step 4: Rewrite `style.css`**

Replace the entire contents of `summer_movie_wager/render/static/style.css` with:

```css
* { box-sizing: border-box; }

body {
  font-family: 'Nunito', sans-serif;
  font-size: 15px;
  line-height: 1.5;
  max-width: 1360px;
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
  overflow-x: auto;
  transition: background 0.25s, box-shadow 0.25s;
}

.matrix h2  { color: #ff6b6b; }
.picks h2   { color: #a855f7; }
.players h2 { color: #a855f7; }
.movies h2  { color: #4ecdc4; }

/* ── Tables ── */
table {
  width: 100%;
  border-collapse: collapse;
  font-variant-numeric: tabular-nums;
}

.matrix thead tr,
.picks thead tr  { background: linear-gradient(90deg, #ff6b6b22, #f7c59f22); }
.movies thead tr { background: linear-gradient(90deg, #4ecdc422, #ffe66d22); }

th {
  font-weight: 700;
  font-size: 0.78em;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 0.7em 0.7em;
  color: var(--th-color);
  border-bottom: 2px solid var(--border);
  white-space: nowrap;
}

td {
  padding: 0.55em 0.7em;
  border-bottom: 1px solid var(--border-row);
}

td:first-child { font-weight: 700; }

tbody tr:nth-child(even) { background: var(--bg-row-alt); }
tbody tr:hover           { background: var(--bg-hover); }

/* Points cells: a scored value reads positive, a zero recedes. */
.pt0   { color: var(--zero); }
.ptpos { color: var(--pos-color); font-weight: 700; }

/* "Outside the top 10" in the matrix, "Dark Horses" in the picks grid. */
tr.tier-divider td {
  padding: 0.4em 0.7em;
  text-align: center;
  font-size: 0.75em;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  background: var(--bg-row-alt);
  border-top: 2px dashed var(--border);
  border-bottom: 2px dashed var(--border);
}

.matrix-footer td {
  font-weight: 800;
  border-top: 2px solid var(--border);
  border-bottom: none;
  background: var(--bg-row-alt);
}

.picks td:first-child,
.picks th:first-child { white-space: nowrap; }

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

.player-stats {
  margin: 0 0 0.8em;
  padding-left: 1.75em;
  color: var(--text-muted);
  font-size: 0.88em;
}

table.player-table { font-size: 0.92em; }
table.player-table th,
table.player-table td { padding: 0.45em 0.7em; }

tr.dh-divider td {
  font-weight: 800;
  font-size: 0.78em;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #ff6b6b;
  background: var(--bg-row-alt);
  padding: 0.5em 0.7em 0.3em;
}

.diff-up   { color: var(--pos-color); font-weight: 700; }
.diff-down { color: #e0575b; font-weight: 700; }
.diff-flat { color: var(--zero); }

/* ── Movies: a card that is also a collapsible ── */
details.movies-toggle { border: none; }
details.movies-toggle > summary {
  padding: 0;
  margin: 0 0 0.8em;
  background: none;
  cursor: pointer;
}
details.movies-toggle > summary::before { display: none; }
details.movies-toggle > summary h2 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin: 0;
  width: 100%;
}
details.movies-toggle > summary h2::after {
  content: "▶ show";
  font-size: 0.6em;
  color: var(--accent);
  text-transform: none;
  letter-spacing: 0;
  font-weight: 700;
}
details.movies-toggle[open] > summary h2::after { content: "▼ hide"; }

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
@media (max-width: 700px) {
  body { font-size: 13px; padding: 1em 0.8em 3em; }
  th, td { padding: 0.35em 0.5em; }
  .theme-toggle { top: 0.6em; right: 0.6em; padding: 0.25em 0.6em; font-size: 0.78em; }
  h1 { font-size: 1.8em; }
}
```

What is deliberately gone from the old file: `.leaderboard h2`, the `.player-row:first-child/:nth-child(2)/:nth-child(3)` medal `::before` rules, `.ranked-picks`, `.dark-horses`, `.dark-horse-label`, and `tbody tr:last-child td { border-bottom: none; }` (wrong now that the matrix has a `<tfoot>`). `.movies { overflow-x: auto }` folds into `.card`, which every section now needs.

- [ ] **Step 4a: Confirm `shared.css` was not touched**

Run: `git diff --stat summer_movie_wager/render/static/shared.css summer_movie_wager/render/static/nav.css`

Expected: empty output. The scenarios/whatif/history pages keep their 1000px shell and their nav pills, including `.nav-pill.is-disabled`.

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run pytest tests/test_render_snapshot.py -k index_css -v`

Expected: PASS.

- [ ] **Step 6: Regenerate the snapshot**

```bash
rm -f tests/fixtures/expected_index.html
uv run pytest tests/test_render_snapshot.py::test_render_matches_expected_snapshot
uv run pytest tests/test_render_snapshot.py::test_render_matches_expected_snapshot
```

Expected: first run FAILS and writes the fixture; second run PASSES.

- [ ] **Step 7: Run the full suite and commit**

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
git add summer_movie_wager/render/static/style.css summer_movie_wager/render/static/theme.css tests/test_render_snapshot.py tests/fixtures/expected_index.html
git commit -m "Style the redesigned leaderboard page

Ports the preview's index rules; drops the CSS for the leaderboard table and
bullet lists that no longer exist.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: Build against live data and verify against the preview

Every test so far has run on a three-movie fixture. This task is the one that proves the page works with 37 films and 8 players, and it is the only place the design is checked with human eyes.

**Files:**
- Regenerate: `docs/index.html`, `docs/data.json`, `docs/scenarios.html`, `docs/whatif.html`, `docs/history.html`
- Modify: `README.md` (test count)

**Interfaces:**
- Consumes: everything from Tasks 1-7.
- Produces: the shipped page.

- [ ] **Step 1: Check what the build is about to overwrite**

Run: `git status --short docs/`

The working tree had uncommitted edits to `docs/*.html` and `docs/data.json` before this branch started. The build overwrites all of them. Confirm nothing there needs saving before continuing.

- [ ] **Step 2: Build with live data**

Run: `uv run python -m summer_movie_wager.render.build --local`

Expected: `[build] wrote .../docs/index.html` on stderr and exit 0. **The `--local` flag is mandatory** — without it the run appends a duplicate same-day row to `data/box_office_history.jsonl` and skews the decay model.

If the build fails on the network scrape rather than on this branch's code, the failure is unrelated to this work; note it and stop rather than working around it.

- [ ] **Step 3: Serve and compare against the preview**

```bash
python3 -m http.server -d docs 8000
```

Open `http://localhost:8000/index.html` and `http://localhost:8000/previews/index-option-1.html` side by side. Check, in order:

1. **Matrix cells** — a scored film shows a green number, a picked-but-unscoring film a grey `0`, an unpicked film a muted `—`. Spot-check one column against that player's own detail table.
2. **The divider** sits after row 10 and there are five rows below it.
3. **Footer totals add up** — pick a column, sum the cells above it, confirm it matches. Confirm the same number appears in that player's stats line.
4. **Diff arrows** — green ▲ where the projection beats the pick position, red ▼ below, `–` on exact.
5. **Picks grid** — 10 pick rows, a Dark Horses divider, 3 dark horse rows, 8 player columns.
6. **Movies section** collapsed by default; the toggle reads "▶ show" / "▼ hide"; the `#` column matches the ranks in the per-player tables.
7. **Theme toggle** — both light and dark, then reload to confirm the choice sticks.
8. **Narrow viewport** — resize below 700px; the page must not scroll horizontally as a whole, only the tables inside their cards.
9. **Nav** — all four pills present, Leaderboard active, and the other three pages still render correctly (they should be untouched).

- [ ] **Step 4: Update the README test count**

`README.md` says "141 tests". Run `uv run pytest` and update the number to what it reports. The descriptive list after it ("scoring, decay math, scraper…") stays as-is.

- [ ] **Step 5: Final verification**

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Expected: all tests pass, no lint or format diagnostics.

- [ ] **Step 6: Commit**

```bash
git add docs/ README.md
git commit -m "Rebuild the site on the new leaderboard layout

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage.** Every section of the spec maps to a task: the matrix and its top-15 slice and column-sum footer (Task 3), the picks grid (Task 4), the per-player tables and Diff column (Task 5), the collapsed Movies section (Task 6), catalog ranks (Task 1), `win_prob` on `PlayerDetail` (Task 2), the CSS including dropped medals (Task 7), and the live build with visual comparison (Task 8). Every edge case in the spec's error-handling section has a test: no forecast (`_render_pages(tmp_path, False)`, existing), empty `player_details` (Task 4 Step 1), fewer than 10 movies (Task 3 Step 2), a pick missing from the catalog (Task 5 Step 1), hostile scraped strings (existing `test_render_escapes_html_in_scraped_fields`).

**One deliberate deviation from the spec**, flagged in Task 7: only `--pos-color` is added to `theme.css`, not `--pos-bg`. The preview declares `--pos-bg` but never references it.

**One risk the spec called out and this plan carries forward** as a code comment rather than a behaviour change (Task 1 Step 3, Task 3 Step 4): `catalog` and `median_position` are derived from different sorts, so they could theoretically disagree on exactly-tied grosses. Re-deriving `median_position` from `movie_rows` would fix that but would change scoring behaviour, which is out of scope here.

**Type consistency.** `_build_player_details(snapshot, projections, current_pts, sim, movie_rows)` and `_pick_detail(title, predicted_rank, catalog, median_position, *, kind)` are used with those exact signatures in Tasks 1 and 2. `pts_by_player` and `projected_totals` are defined in Task 3 Step 4 and consumed under those names in Tasks 3, 4, and 5. The template-local `n`, `n_ranked`, and `n_dh` are bound in Tasks 3 and 4 and used only after binding. `PlayerDetail.win_prob` is defaulted, so the existing constructions in `tests/test_render_snapshot.py` that omit it stay valid.
