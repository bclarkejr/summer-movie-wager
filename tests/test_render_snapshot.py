from datetime import datetime
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
                username="vivrad", current_pts=3, median_pts=91.0,
                p10_pts=62.0, p90_pts=134.0, win_prob=0.28, tie_prob=0.04,
            ),
            LeaderboardRow(
                username="bclarke", current_pts=3, median_pts=85.0,
                p10_pts=58.0, p90_pts=128.0, win_prob=0.19, tie_prob=0.05,
            ),
        ],
        movies=[
            MovieRow(
                title="Spider-Man: Brand New Day", release_date="2026-07-31",
                status="pre_release", status_label="pre-release",
                median_in_window_gross=380_000_000, p10=290_000_000, p90=470_000_000,
                cumulative_to_date=None, source="Box Office Pro · high",
            ),
            MovieRow(
                title="The Devil Wears Prada 2", release_date="2026-05-01",
                status="in_theaters", status_label="in theaters",
                median_in_window_gross=170_000_000, p10=140_000_000, p90=210_000_000,
                cumulative_to_date=32_500_000, source="decay model · 1 wk",
            ),
        ],
        player_details=[
            PlayerDetail(
                username="bclarke", median_pts=85.0, current_pts=3,
                ranked=[
                    PickDetail(title="Toy Story 5", projected_rank=2, projected_gross=290_000_000, projected_pts=10),
                ],
                dark_horses=[
                    PickDetail(title="Backrooms", projected_rank=None, projected_gross=0, projected_pts=0),
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


def test_render_escapes_html_in_scraped_fields(tmp_path: Path):
    # Movie titles/sources are externally-scraped strings. Autoescape must escape
    # any embedded HTML; otherwise a hostile feed could inject script tags.
    hostile = "<script>alert(1)</script>"
    data = RenderInput(
        generated_at=datetime(2026, 5, 3, 14, 22, 0),
        leaderboard=[],
        movies=[
            MovieRow(
                title=hostile, release_date="2026-05-01",
                status="in_theaters", status_label="in theaters",
                median_in_window_gross=1.0, p10=1.0, p90=1.0,
                cumulative_to_date=None, source=hostile,
            )
        ],
        player_details=[],
        raw_snapshot={},
    )
    render(tmp_path, data)
    rendered = (tmp_path / "index.html").read_text()
    assert hostile not in rendered, "raw <script> tag leaked through autoescape"
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
