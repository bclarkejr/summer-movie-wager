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
    Render index.html and data.json into out_dir.

    Pretty straightforward. There are three sections on the HTML page:

    1. Leaderboard: A table of all players and their current points, projected points, and win/tie probabilities.
    2. Movie projections: A table of all movies and their projected gross/points, plus some metadata like release date and status.
    3. Per-player details: For each player, an expandable section showing their picks and the projected points for each pick.
    
    Note that all three sections rely on the arrays to already be sorted appropriately.  We want to show which movies and players are
    at the top of the leaderboard, but render will not do any sorting itself.

    The HTML is generated from a Jinja2 template. The CSS is inlined into the HTML for simplicity.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    env = Environment(
        loader = FileSystemLoader(str(_TEMPLATES)),
        # select_autoescape misses .j2 suffixes; force escaping unconditionally
        # since movie titles and other fields originate from external scrapes.
        autoescape = True,
    )
    template = env.get_template("index.html.j2")
    theme_css = (_STATIC / "theme.css").read_text()
    inline_css = theme_css + "\n" + (_STATIC / "style.css").read_text()
    html = template.render(
        generated_at = data.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        leaderboard = data.leaderboard,
        movies = data.movies,
        player_details = data.player_details,
        inline_css = inline_css,
        forecast_available = data.forecast_available,
        forecast_unavailable_reason = data.forecast_unavailable_reason,
    )
    (out_dir / "index.html").write_text(html)
    (out_dir / "data.json").write_text(json.dumps(data.raw_snapshot, indent=2, default=str))

    scenario_payload = {
        "standing": [row.username for row in data.leaderboard],
        "win_prob": data.raw_snapshot.get("win_prob", {}),
        "scenarios": data.raw_snapshot.get("winning_scenarios", {}),
    }
    scenarios_html = env.get_template("scenarios.html.j2").render(
        generated_at = data.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
        theme_css = theme_css,
        scenario_json = json.dumps(scenario_payload, default=str),
        forecast_available = data.forecast_available,
        forecast_unavailable_reason = data.forecast_unavailable_reason,
    )
    (out_dir / "scenarios.html").write_text(scenarios_html)
