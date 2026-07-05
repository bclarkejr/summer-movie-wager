"""Render the static site from pipeline outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

_TEMPLATES = Path(__file__).parent / "templates"
_STATIC = Path(__file__).parent / "static"


def _json_for_script(obj: Any) -> str:
    """JSON for embedding inside a <script> tag: \\u003c-escape '<' so a hostile
    '</script>' in scraped data can't close the tag."""
    return json.dumps(obj, default=str).replace("<", "\\u003c")


@dataclass(frozen=True)
class LeaderboardRow:
    username: str
    current_pts: int
    median_pts: float | None
    p10_pts: float | None
    p90_pts: float | None
    win_prob: float | None
    tie_prob: float | None


@dataclass(frozen=True)
class MovieRow:
    title: str
    release_date: str
    status: str  # machine value (pre_release, in_theaters, won't_score, no_projection)
    status_label: str  # human label
    median_in_window_gross: float
    p10: float
    p90: float
    cumulative_to_date: float | None
    source: str


@dataclass(frozen=True)
class PickDetail:
    title: str
    projected_rank: int | None
    projected_gross: float
    projected_pts: int


@dataclass(frozen=True)
class PlayerDetail:
    username: str
    median_pts: float | None
    current_pts: int
    ranked: list[PickDetail]
    dark_horses: list[PickDetail]


@dataclass(frozen=True)
class RenderInput:
    generated_at: datetime
    leaderboard: list[LeaderboardRow]
    movies: list[MovieRow]
    player_details: list[PlayerDetail]
    raw_snapshot: dict[str, Any] = field(default_factory=dict)
    forecast_available: bool = True
    forecast_unavailable_reason: str = ""


def render(out_dir: Path, data: RenderInput) -> None:
    """
    Render index.html, scenarios.html, whatif.html, and data.json into out_dir.

    index.html has three sections:

    1. Leaderboard: A table of all players and their current points, projected points,
       and win/tie probabilities.
    2. Movie projections: A table of all movies and their projected gross/points, plus
       some metadata like release date and status.
    3. Per-player details: For each player, an expandable section showing their picks
       and the projected points for each pick.

    scenarios.html shows each player's most-likely winning finish order. whatif.html lets a
    visitor drag the top-15 projected movies into a hypothetical top-10 finish and see every
    player's score update live.

    Note that all sections rely on the arrays to already be sorted appropriately.  We want
    to show which movies and players are at the top of the leaderboard, but render will not
    do any sorting itself.

    The HTML is generated from Jinja2 templates. The CSS is inlined into each page for simplicity.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES)),
        # select_autoescape misses .j2 suffixes; force escaping unconditionally
        # since movie titles and other fields originate from external scrapes.
        autoescape=True,
    )
    template = env.get_template("index.html.j2")
    theme_css = (_STATIC / "theme.css").read_text()
    nav_css = (_STATIC / "nav.css").read_text()
    shared_css = (_STATIC / "shared.css").read_text()
    inline_css = theme_css + "\n" + nav_css + "\n" + (_STATIC / "style.css").read_text()
    html = template.render(
        generated_at=data.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        leaderboard=data.leaderboard,
        movies=data.movies,
        player_details=data.player_details,
        inline_css=inline_css,
        active="index",
        forecast_available=data.forecast_available,
        forecast_unavailable_reason=data.forecast_unavailable_reason,
    )
    (out_dir / "index.html").write_text(html)
    (out_dir / "data.json").write_text(json.dumps(data.raw_snapshot, indent=2, default=str))

    scenario_payload = {
        "standing": [row.username for row in data.leaderboard],
        "win_prob": data.raw_snapshot.get("win_prob", {}),
        "scenarios": data.raw_snapshot.get("winning_scenarios", {}),
    }
    scenarios_html = env.get_template("scenarios.html.j2").render(
        generated_at=data.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        theme_css=theme_css,
        nav_css=nav_css,
        shared_css=shared_css,
        active="scenarios",
        scenario_json=_json_for_script(scenario_payload),
        forecast_available=data.forecast_available,
        forecast_unavailable_reason=data.forecast_unavailable_reason,
    )
    (out_dir / "scenarios.html").write_text(scenarios_html)

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
        generated_at=data.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        theme_css=theme_css,
        nav_css=nav_css,
        shared_css=shared_css,
        active="whatif",
        whatif_json=_json_for_script(whatif_payload),
        forecast_available=data.forecast_available,
        forecast_unavailable_reason=data.forecast_unavailable_reason,
    )
    (out_dir / "whatif.html").write_text(whatif_html)
