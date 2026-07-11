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
        ],
        player_details=[
            PlayerDetail(
                username="bclarke",
                median_pts=85.0,
                current_pts=3,
                ranked=[
                    PickDetail(
                        title="Toy Story 5",
                        projected_rank=2,
                        projected_gross=290_000_000,
                        projected_pts=10,
                    ),
                ],
                dark_horses=[
                    PickDetail(
                        title="Backrooms", projected_rank=None, projected_gross=0, projected_pts=0
                    ),
                ],
            )
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
    assert "Sortable.min.js" in whatif
    assert 'class="site-nav"' in whatif
    assert "const FORECAST_AVAILABLE = true" in whatif
    assert 'href="whatif.html"' in index


def test_whatif_gated_when_forecast_off(tmp_path):
    index, _scenarios, whatif = _render_pages(tmp_path, False)
    assert "const FORECAST_AVAILABLE = false" in whatif
    assert 'href="whatif.html"' not in index


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
