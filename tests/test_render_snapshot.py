from datetime import UTC, datetime
from pathlib import Path

import pytest

from summer_movie_wager.render.page import (
    LeaderboardRow,
    MovieRow,
    PickDetail,
    PlayerDetail,
    RenderInput,
    render,
)

EXPECTED = Path(__file__).parent / "fixtures" / "expected_index.html"


def _fixture_input() -> RenderInput:
    return RenderInput(
        generated_at=datetime(2026, 5, 3, 14, 22, 0),
        leaderboard=[
            LeaderboardRow(
                username="vivrad",
                current_pts=3,
                median_pts=91.0,
                p10_pts=62.0,
                p90_pts=134.0,
                win_prob=0.28,
                tie_prob=0.04,
            ),
            LeaderboardRow(
                username="bclarke",
                current_pts=3,
                median_pts=85.0,
                p10_pts=58.0,
                p90_pts=128.0,
                win_prob=0.19,
                tie_prob=0.05,
            ),
        ],
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
        raw_snapshot={"placeholder": True},
    )


def test_render_matches_expected_snapshot(tmp_path: Path):
    render(tmp_path, _fixture_input())
    actual = (tmp_path / "index.html").read_text()
    if not EXPECTED.exists():
        EXPECTED.write_text(actual)
        pytest.fail(
            "expected_index.html did not exist — wrote it now from this run. "
            "Inspect it visually, then re-run the test to lock the snapshot."
        )
    expected = EXPECTED.read_text()
    assert actual == expected, (
        "Render output drifted from snapshot. If intentional, delete "
        "tests/fixtures/expected_index.html and re-run to regenerate."
    )


def test_render_writes_data_json(tmp_path: Path):
    render(tmp_path, _fixture_input())
    assert (tmp_path / "data.json").exists()


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


def test_per_player_table_shows_diff_arrows(tmp_path: Path):
    # Diff = pick position - projected rank. vivrad's list covers all three cases.
    render(tmp_path, _fixture_input())
    html = (tmp_path / "index.html").read_text()
    detail = html.split('<details data-player="vivrad">')[1].split("</details>")[0]
    assert 'class="diff-down">▼ 1</td>' in detail  # pick 1 projects #2
    assert 'class="diff-up">▲ 1</td>' in detail  # pick 2 projects #1
    assert 'class="diff-flat">–</td>' in detail  # pick 3 projects #3  # noqa: RUF001


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


def _render_pages(tmp_path, forecast_available):
    from datetime import datetime

    from summer_movie_wager.render.page import LeaderboardRow, RenderInput, render

    leaderboard = [
        LeaderboardRow(
            username="a",
            current_pts=10,
            median_pts=10.0,
            p10_pts=5.0,
            p90_pts=15.0,
            win_prob=0.5,
            tie_prob=0.0,
        ),
        LeaderboardRow(
            username="b",
            current_pts=5,
            median_pts=5.0,
            p10_pts=1.0,
            p90_pts=9.0,
            win_prob=0.0,
            tie_prob=0.0,
        ),
    ]
    scenarios = {
        "a": {
            "films": [f"F{i}" for i in range(10)],
            "grid": {"a": [1] * 10, "b": [0] * 10},
            "totals": {"a": 10, "b": 0},
            "win_pct": 50.0,
            "margin": 10,
        },
        "b": None,
    }
    raw = {
        "win_prob": {"a": 0.5, "b": 0.0},
        "winning_scenarios": scenarios if forecast_available else {"a": None, "b": None},
    }
    render(
        tmp_path,
        RenderInput(
            generated_at=datetime(2026, 6, 29, tzinfo=UTC),
            leaderboard=leaderboard,
            movies=[],
            player_details=[],
            raw_snapshot=raw,
            forecast_available=forecast_available,
            forecast_unavailable_reason="" if forecast_available else "only 3 movies projected",
        ),
    )
    return (
        (tmp_path / "index.html").read_text(),
        (tmp_path / "scenarios.html").read_text(),
        (tmp_path / "whatif.html").read_text(),
    )


def test_nav_on_both_existing_pages(tmp_path):
    index, scenarios, _whatif = _render_pages(tmp_path, True)
    for page in (index, scenarios):
        assert 'class="site-nav"' in page
        assert 'href="index.html"' in page
    assert 'href="scenarios.html"' in index
    # active pill matches the page
    assert 'nav-pill is-active" href="index.html"' in index or "is-active" in index


def test_shared_theme_tokens_inlined_into_both_pages(tmp_path):
    index, scenarios, _whatif = _render_pages(tmp_path, True)
    # the shared token set (base + scenario tokens) is present on both pages
    for css in (index, scenarios):
        assert "--bg-card:" in css  # existing shared token
        assert "--accent:" in css  # scenario token, now shared
        assert "--win-bg:" in css


def test_scenarios_page_and_link_when_forecast_on(tmp_path):
    index, scenarios, _whatif = _render_pages(tmp_path, True)
    assert 'id="view"' in scenarios  # grid view markup present
    assert "const DATA =" in scenarios  # scenarios embedded
    assert "const FORECAST_AVAILABLE = true" in scenarios
    assert 'href="scenarios.html"' in index  # leaderboard links to the page


def test_scenarios_gated_and_unlinked_when_forecast_off(tmp_path):
    index, scenarios, _whatif = _render_pages(tmp_path, False)
    assert "const FORECAST_AVAILABLE = false" in scenarios  # page shows gated notice
    assert 'href="scenarios.html"' not in index  # link hidden


def test_whatif_page_rendered(tmp_path):
    index, _scenarios, whatif = _render_pages(tmp_path, True)
    assert "const DATA =" in whatif
    assert 'id="finish"' in whatif
    assert "Sortable" in whatif
    assert 'class="site-nav"' in whatif
    assert "const FORECAST_AVAILABLE = true" in whatif
    assert 'href="whatif.html"' in index


def test_whatif_gated_when_forecast_off(tmp_path):
    index, _scenarios, whatif = _render_pages(tmp_path, False)
    assert "const FORECAST_AVAILABLE = false" in whatif
    assert 'href="whatif.html"' not in index


def test_whatif_has_no_cdn_dependency(tmp_path):
    _index, _scenarios, whatif = _render_pages(tmp_path, True)
    assert "jsdelivr" not in whatif
    assert "cdn." not in whatif
    assert "new Sortable(" in whatif  # library consumer still present
    assert "This fork of Sortable" in whatif or "Sortable 1.15.6" in whatif or "MIT" in whatif


def test_whatif_payload_top15_in_projected_order_with_picks(tmp_path):
    # 17 movies, one zero-gross → payload holds exactly the first 15 non-zero
    # titles in RenderInput.movies order (== the index table's projected order),
    # with no gross figures; player picks present in pick order.
    from datetime import datetime

    from summer_movie_wager.render.page import (
        LeaderboardRow,
        MovieRow,
        PickDetail,
        PlayerDetail,
        RenderInput,
        render,
    )

    movies = [
        MovieRow(
            title=f"M{i}",
            release_date="2026-06-01",
            status="in_theaters",
            status_label="in theaters",
            median_in_window_gross=float(1000 - i),
            p10=0,
            p90=0,
            cumulative_to_date=None,
            source="t",
        )
        for i in range(16)
    ]
    movies.append(
        MovieRow(
            title="ZeroGross",
            release_date="2026-06-01",
            status="pre_release",
            status_label="pre-release",
            median_in_window_gross=0,
            p10=0,
            p90=0,
            cumulative_to_date=None,
            source="t",
        )
    )
    player = PlayerDetail(
        username="a",
        median_pts=1.0,
        current_pts=1,
        ranked=[
            PickDetail(title=f"M{i}", projected_rank=None, projected_gross=0, projected_pts=0)
            for i in range(10)
        ],
        dark_horses=[
            PickDetail(title=f"D{i}", projected_rank=None, projected_gross=0, projected_pts=0)
            for i in range(3)
        ],
    )
    render(
        tmp_path,
        RenderInput(
            generated_at=datetime(2026, 7, 3, tzinfo=UTC),
            leaderboard=[
                LeaderboardRow(
                    username="a",
                    current_pts=1,
                    median_pts=1.0,
                    p10_pts=0.0,
                    p90_pts=2.0,
                    win_prob=1.0,
                    tie_prob=0.0,
                )
            ],
            movies=movies,
            player_details=[player],
            raw_snapshot={"win_prob": {}, "winning_scenarios": {}},
        ),
    )
    whatif = (tmp_path / "whatif.html").read_text()
    import json as _json
    import re

    payload = _json.loads(re.search(r"const DATA = (.*?);\n", whatif).group(1))
    assert payload["movies"] == [f"M{i}" for i in range(15)]  # 15, ordered, no M15/ZeroGross
    assert payload["players"][0]["ranked"] == [f"M{i}" for i in range(10)]
    assert payload["players"][0]["dark_horses"] == ["D0", "D1", "D2"]


def test_scenario_json_script_safe(tmp_path):
    from datetime import datetime

    from summer_movie_wager.render.page import LeaderboardRow, RenderInput, render

    hostile = "</script><script>alert(1)</script>"
    raw = {
        "win_prob": {"a": 1.0},
        "winning_scenarios": {
            "a": {
                "films": [hostile] + [f"F{i}" for i in range(9)],
                "grid": {"a": [1] * 10},
                "totals": {"a": 10},
                "win_pct": 100.0,
                "margin": 10,
            },
        },
    }
    render(
        tmp_path,
        RenderInput(
            generated_at=datetime(2026, 7, 3, tzinfo=UTC),
            leaderboard=[
                LeaderboardRow(
                    username="a",
                    current_pts=1,
                    median_pts=1.0,
                    p10_pts=0.0,
                    p90_pts=2.0,
                    win_prob=1.0,
                    tie_prob=0.0,
                )
            ],
            movies=[],
            player_details=[],
            raw_snapshot=raw,
        ),
    )
    scenarios = (tmp_path / "scenarios.html").read_text()
    assert hostile not in scenarios  # literal </script> must not appear in the payload
    assert "\\u003c/script" in scenarios  # escaped form does


def test_render_escapes_html_in_scraped_fields(tmp_path: Path):
    # Movie titles/sources are externally-scraped strings. Autoescape must escape
    # any embedded HTML; otherwise a hostile feed could inject script tags.
    hostile = "<script>alert(1)</script>"
    data = RenderInput(
        generated_at=datetime(2026, 5, 3, 14, 22, 0),
        leaderboard=[],
        movies=[
            MovieRow(
                title=hostile,
                release_date="2026-05-01",
                status="in_theaters",
                status_label="in theaters",
                median_in_window_gross=1.0,
                p10=1.0,
                p90=1.0,
                cumulative_to_date=None,
                source=hostile,
            )
        ],
        player_details=[],
        raw_snapshot={},
    )
    render(tmp_path, data)
    rendered = (tmp_path / "index.html").read_text()
    assert hostile not in rendered, "raw <script> tag leaked through autoescape"
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered


def test_scenario_tabs_are_plain_buttons_with_pressed_state(tmp_path):
    _index, scenarios, _whatif = _render_pages(tmp_path, True)
    assert 'role="tablist"' not in scenarios
    assert '"role","tab"' not in scenarios  # the buildTabs setAttribute call
    assert "aria-pressed" in scenarios
    assert "b.disabled = true" in scenarios  # no-scenario players are truly disabled


def test_whatif_rows_have_keyboard_move_buttons(tmp_path):
    _index, _scenarios, whatif = _render_pages(tmp_path, True)
    assert 'class="move-btn"' in whatif
    assert "Move ${esc(t)} up" in whatif  # aria-label template literal in the page JS
    assert 'filter: ".move-btn"' in whatif  # buttons never start a drag


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
