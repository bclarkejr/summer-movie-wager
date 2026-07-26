"""End-to-end pipeline: ingest → project → simulate → render."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import yaml

from summer_movie_wager.ingest.boxoffice import BoxOfficeRow
from summer_movie_wager.ingest.picks_guard import bootstrap_or_validate
from summer_movie_wager.ingest.scraper import fetch_snapshot
from summer_movie_wager.model.decay import project_decay
from summer_movie_wager.model.preopening import WINDOW_END, project_preopening
from summer_movie_wager.model.simulate import simulate_season
from summer_movie_wager.render.page import (
    LeaderboardRow,
    MovieRow,
    PickDetail,
    PlayerDetail,
    RenderInput,
    render,
)
from summer_movie_wager.score import ranked_pick_points, score_player
from summer_movie_wager.types import (
    Category,
    Confidence,
    MovieStatus,
    PreopeningEntry,
    Projection,
    SiteSnapshot,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DOCS_DIR = REPO_ROOT / "docs"


def _build_raw_sim_fields(
    raw: dict[str, Any],
    sim: Any | None,
    snapshot_players: dict[str, Any],
    forecast_available: bool,
    forecast_unavailable_reason: str,
) -> None:
    """Populate sim-dependent keys into `raw`. Extracted so tests can call it directly."""
    if forecast_available and sim is not None:
        raw["win_prob"] = sim.win_prob
        raw["tie_prob"] = sim.tie_prob
        raw["median_final_pts"] = sim.median_final_pts
        raw["p10_final_pts"] = sim.p10_final_pts
        raw["p90_final_pts"] = sim.p90_final_pts
        raw["winning_scenarios"] = {
            u: (s.model_dump() if s is not None else None) for u, s in sim.winning_scenarios.items()
        }
    else:
        raw["forecast_unavailable_reason"] = forecast_unavailable_reason
        # Emit explicit nulls so consumers don't confuse "no forecast" with "missing key".
        raw["win_prob"] = {u: None for u in snapshot_players}
        raw["tie_prob"] = {u: None for u in snapshot_players}
        raw["median_final_pts"] = {u: None for u in snapshot_players}
        raw["p10_final_pts"] = {u: None for u in snapshot_players}
        raw["p90_final_pts"] = {u: None for u in snapshot_players}
        raw["winning_scenarios"] = {u: None for u in snapshot_players}


def main(argv: list[str] | None = None) -> int:
    """
    Run the full pipeline to refresh the site.  There are 8 steps to the pipeline:

    1. fetch_snapshot:  Scrape thesummermoviewager.com to get the current state of the game (picks,
    cumulative grosses, and reported points).
    2. bootstrap_or_validate:  Validate that the picks we have in data/picks_snapshot_2026.yaml
    match what we scraped from the site.
    3. _normalize_movies:  Normalize the movie data from the snapshot, overrides,
         and preopening projections into a single dictionary of movies with their release dates,
         status, category, and cumulative gross.
    4. _project_all:  For each movie, project its in-window gross and uncertainty (sigma) based on
    its status and available data.
         For IN_THEATERS movies, use the decay model.  For PRE_RELEASE movies with an analyst entry,
         use the preopening projection model.
         For other PRE_RELEASE movies, project zero gross.
    5. simulate_season:  If there are at least 25 movies with non-zero projections, simulate the
    season 10,000 times to estimate each player's win probability and final points distribution.
    6. _validate_against_site:  Compare our computed current points against the site's reported
    points to ensure our scoring engine is correct.
    7. render:  Render the HTML page using the leaderboard, movie rows, and player details.
    8. _append_box_office_history and _append_forecast_history:  Append the current box office and
    forecast data to history files for future reference.
    """

    # If --local is passed, we don't append to history files.  This is useful for testing the
    # pipeline without causing issues with our decay model.
    parser = argparse.ArgumentParser(description="Refresh the Summer Movie Wager site")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run pipeline locally; do not append to history files.",
    )
    args = parser.parse_args(argv)

    # Code hits thesummermoviewager.com to scrape the current state of the game.  This is used to
    # validate our scoring engine and to get the current cumulative grosses for each movie.
    today = date.today()
    print(f"[build] fetching site snapshot ({today})", file=sys.stderr)
    snapshot = fetch_snapshot(captured_at=today)

    # Confirms that our picks_snapshot_2026.yaml match what thesummermoviewager.com reports.
    print("[build] validating picks against snapshot", file=sys.stderr)
    bootstrap_or_validate(snapshot.players, DATA_DIR / "picks_snapshot_2026.yaml")

    # This is the real value-add of the pipeline.  Using the week-over-week decay model and
    # preopening projections, we can start to guess what each film will gross in the wager window.
    # Once we have 25 projections (i.e., once we have an industry projection for Spider-Man: Brand
    # New Day), we simulate the season and estimate each player's win probability and final points
    # distribution.
    overrides = _load_yaml(DATA_DIR / "movies_overrides.yaml")
    preopening_raw = _load_yaml(DATA_DIR / "preopening_projections.yaml")
    preopening = _parse_preopening(preopening_raw)

    movies = _normalize_movies(snapshot, overrides, preopening, today=today)
    projections = _project_all(movies, preopening, today=today)
    _warn_missing_projections(movies, preopening, today=today)

    # We don't similuate until we have at least 25 projections.
    non_zero = _count_non_zero_projections(projections)
    forecast_available = non_zero >= 25
    forecast_unavailable_reason = ""
    sim: Any | None = None
    if forecast_available:
        sim = simulate_season(
            list(snapshot.players.values()),
            projections,
            n_trials=10_000,
            seed=20260907,
        )
    else:
        forecast_unavailable_reason = (
            f"only {non_zero} movie(s) have non-zero projections "
            f"(need 25 for an honest top-10 ranking)"
        )
        print(
            f"[build] WARNING: skipping simulation — {forecast_unavailable_reason}",
            file=sys.stderr,
        )

    # Calculate the current points for each player based on the current top 10 movies and validate
    # against thesummermoviewager.com reported points.
    current_top10 = _current_top_10(snapshot.cumulative_grosses)
    current_pts = {
        username: score_player(picks, current_top10) for username, picks in snapshot.players.items()
    }
    _validate_against_site(current_pts, snapshot.site_reported_points)

    # Build the leaderboard, movie rows, and player details for rendering the HTML page.
    leaderboard = _build_leaderboard(snapshot, sim, current_pts)
    movie_rows = _build_movie_rows(movies, projections)
    player_details = _build_player_details(snapshot, projections, current_pts, sim)

    raw: dict[str, Any] = {
        "captured_at": str(snapshot.captured_at),
        "site_reported_points": snapshot.site_reported_points,
        "computed_current_points": current_pts,
        "forecast_available": forecast_available,
        "non_zero_projections": non_zero,
        "projections": [p.model_dump() for p in projections],
    }
    _build_raw_sim_fields(
        raw, sim, snapshot.players, forecast_available, forecast_unavailable_reason
    )

    render(
        DOCS_DIR,
        RenderInput(
            generated_at=datetime.now(UTC),
            leaderboard=leaderboard,
            movies=movie_rows,
            player_details=player_details,
            raw_snapshot=raw,
            forecast_available=forecast_available,
            forecast_unavailable_reason=forecast_unavailable_reason,
            history=_build_forecast_history_payload(DATA_DIR / "forecast_history.jsonl"),
        ),
    )

    # Last step: append the current box office and forecast data to history files for future
    # reference.
    # This ensures our decay model has historical information to see week-over-week trends.
    # It is skipped if --local is passed.
    if not args.local:
        _append_box_office_history(snapshot, today=today)
        if sim is not None:
            _append_forecast_history(snapshot, sim, today=today)

    print(f"[build] wrote {DOCS_DIR}/index.html", file=sys.stderr)
    return 0


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _parse_preopening(raw: dict[str, Any]) -> dict[str, PreopeningEntry]:
    """
    After parsing the `preopening_projections.yaml` file, we need to convert the raw dictionary into
    a dictionary of PreopeningEntry objects.
    This function handles the conversion and validation of the data.
    """

    out: dict[str, PreopeningEntry] = {}
    for title, entry in raw.items():
        ow = entry.get("opening_weekend_estimate")
        td = entry.get("total_domestic_estimate")
        conf = entry.get("confidence")
        src = entry.get("source")
        as_of = entry.get("as_of")
        out[title] = PreopeningEntry(
            release_date=date.fromisoformat(str(entry["release_date"])),
            opening_weekend_estimate=float(ow) if ow is not None else None,
            total_domestic_estimate=float(td) if td is not None else None,
            confidence=Confidence(conf) if conf is not None else None,
            source=str(src) if src is not None else None,
            as_of=date.fromisoformat(str(as_of)) if as_of is not None else None,
            notes=str(entry.get("notes", "")),
        )
    return out


def _normalize_movies(
    snapshot: SiteSnapshot,
    overrides: dict[str, Any],
    preopening: dict[str, PreopeningEntry],
    *,
    today: date,
) -> dict[str, dict[str, Any]]:
    """
    Given three sources of movie data (snapshot, overrides, and preopening projections), insert all
    distinct movies into a single dictionary of movies.
    The dictionary is then populated with their canonical title, release date, status, category, and
    cumulative gross.
    Cumulative gross is taken from the snapshot.  The cumulative gross will be zero for movies that
    have not yet been released or have no reported gross.
    """

    # Build a set of all "candidate movie titles" from the snapshot, preopening projections, and
    # overrides.
    # Candidates are any movie that is either picked by a player, has a preopening projection, or
    # has a cumulative gross reported by the site.
    # Candidates are not all movies that have been released, just movies that are relevant to the
    # wager.
    movies: dict[str, dict[str, Any]] = {}
    candidates: set[str] = set()
    for picks in snapshot.players.values():
        candidates.update(picks.ranked + picks.dark_horses)
    candidates.update(preopening.keys())
    candidates.update(snapshot.cumulative_grosses.keys())

    # For each movie that might score, determine its canonical title, release date, status,
    # category, and (most importantly) cumulative gross.
    for title in candidates:
        ov = overrides.get(title, {}) or {}
        canonical = ov.get("alias_of", title)
        category = Category(ov.get("category", "wide"))
        cumulative = snapshot.cumulative_grosses.get(canonical, 0.0)

        if "release_date" in ov:
            release = date.fromisoformat(str(ov["release_date"]))
        elif canonical in preopening:
            release = preopening[canonical].release_date
        elif cumulative > 0:
            release = today
        else:
            release = WINDOW_END

        if "status" in ov:
            status = MovieStatus(ov["status"])
        elif release > today:
            status = MovieStatus.PRE_RELEASE
        elif cumulative > 0:
            status = MovieStatus.IN_THEATERS
        else:
            status = MovieStatus.PRE_RELEASE

        movies[canonical] = {
            "title": canonical,
            "release_date": release,
            "status": status,
            "category": category,
            "cumulative": cumulative,
        }
    return movies


def _has_complete_estimate(entry: PreopeningEntry) -> bool:
    """All three model inputs must be present to project; a partial entry (e.g. a
    placeholder with only an opening estimate) is treated as no projection."""
    return (
        entry.opening_weekend_estimate is not None
        and entry.total_domestic_estimate is not None
        and entry.confidence is not None
    )


def _project_all(
    movies: dict[str, dict[str, Any]],
    preopening: dict[str, PreopeningEntry],
    *,
    today: date,
) -> list[Projection]:
    projections: list[Projection] = []
    history = _load_history()
    for title, m in movies.items():
        if m["status"] == MovieStatus.IN_THEATERS:
            obs = history.get(title, [])
            gross, sigma = project_decay(
                release_date=m["release_date"],
                today=today,
                cumulative_gross_to_date=m["cumulative"],
                category=m["category"],
                observed_history=obs,
            )
        elif (
            m["status"] == MovieStatus.PRE_RELEASE
            and title in preopening
            and _has_complete_estimate(preopening[title])
        ):
            entry = preopening[title]
            gross, sigma = project_preopening(
                release_date=entry.release_date,
                opening_weekend_estimate=entry.opening_weekend_estimate,
                total_domestic_estimate=entry.total_domestic_estimate,
                confidence=entry.confidence,
                category=m["category"],
            )
        else:
            gross, sigma = 0.0, 0.0
        floor = m["cumulative"] if m["status"] == MovieStatus.IN_THEATERS else 0.0
        projections.append(
            Projection(
                movie_title=title,
                median_in_window_gross=gross,
                sigma=sigma,
                floor=floor,
            )
        )
    return projections


def _count_non_zero_projections(projections: list[Projection]) -> int:
    return sum(1 for p in projections if p.median_in_window_gross > 0)


def _warn_missing_projections(
    movies: dict[str, dict[str, Any]],
    preopening: dict[str, PreopeningEntry],
    *,
    today: date,
) -> None:
    """Warn about picked PRE_RELEASE movies with no analyst entry that would otherwise score."""
    missing: list[str] = []
    for title, m in movies.items():
        if m["status"] != MovieStatus.PRE_RELEASE:
            continue
        if title in preopening and _has_complete_estimate(preopening[title]):
            continue
        if m["release_date"] > WINDOW_END:
            # Legitimately won't score — no analyst entry needed.
            continue
        missing.append(title)
    if missing:
        bullet_lines = "\n  - ".join(sorted(missing))
        print(
            f"[build] WARNING: {len(missing)} picks have no projection "
            f"(add to data/preopening_projections.yaml):\n  - {bullet_lines}",
            file=sys.stderr,
        )


def _load_history() -> dict[str, list[tuple[date, float]]]:
    """
    To keep the decay model honest, we need to maintain a history of cumulative grosses for each
    movie.  This allows the decay model to see week-over-week trends and adjust its projections
    accordingly.
    We store the history weekly in `data/box_office_history.jsonl`.  This function loads the history
    from `data/box_office_history.jsonl`.
    """

    path = DATA_DIR / "box_office_history.jsonl"
    if not path.exists():
        print(
            f"[build] WARNING: Unable to load history file at {path}.  "
            "The decay model will not have historical data to inform its projections.",
            file=sys.stderr,
        )
        return {}

    history: dict[str, list[tuple[date, float]]] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        history.setdefault(row["movie"], []).append(
            (date.fromisoformat(row["date"]), float(row["cumulative_gross"]))
        )
    return history


def _resolve_grosses(
    chart: dict[str, BoxOfficeRow],
    history: dict[str, list[tuple[date, float]]],
    *,
    today: date,
) -> tuple[dict[str, float], set[str]]:
    """Merge the live Box Office Mojo chart with recorded history.

    Returns `(grosses, carried_titles)`.

    Two things history gives us that a single chart read cannot:

    1. A film that has fallen off the 200-row chart keeps its last observed gross
       instead of collapsing to 0. Grosses only go up, so we take the highest
       gross observed on or before the cutoff -- which also absorbs a downward
       revision on Box Office Mojo's side, regardless of which date it was
       recorded on.
    2. After Labor Day the chart keeps accumulating gross the wager doesn't count.
       The chart reports through *yesterday*, so it is still exactly right when run
       on WINDOW_END + 1 and wrong from WINDOW_END + 2 onward; past that we fall
       back to the last observation recorded on or before WINDOW_END.

    `carried_titles` is the set of resolved titles absent from `chart` -- true
    regardless of whether the chart's values were usable this run, since `chart`
    (the mapping's keys) is always passed in; only its VALUES get ignored after
    the freeze. Callers surface it as a warning: a title carried forward while
    the film is plainly still playing means the chart title drifted from ours.
    """

    cutoff = min(today, WINDOW_END)
    # The chart reflects data through yesterday, so it is usable while that day
    # is still inside the window.
    chart_usable = (today - timedelta(days=1)) <= WINDOW_END

    grosses: dict[str, float] = {}
    for title, obs in history.items():
        in_range = [g for d, g in obs if d <= cutoff]
        if in_range:
            grosses[title] = max(in_range)

    if chart_usable:
        for title, row in chart.items():
            grosses[title] = max(row.cumulative_gross, grosses.get(title, 0.0))

    carried = {title for title in grosses if title not in chart}
    return grosses, carried


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
        "series": [{"player": p, "win_prob": [rows.get((d, p)) for d in dates]} for p in players],
    }


def _current_top_10(grosses: dict[str, float]) -> list[str]:
    """Return up to 10 titles ranked by gross (descending). Excludes zero-gross movies.

    May return fewer than 10 titles if fewer than 10 movies have positive cumulative gross.
    `score_player` accepts partial top-titles lists.
    """
    return [
        title
        for title, gross in sorted(grosses.items(), key=lambda kv: kv[1], reverse=True)
        if gross > 0
    ][:10]


def _validate_against_site(
    computed: dict[str, int],
    site: dict[str, int],
) -> None:
    """Compare our computed current points against thesummermoviewager.com reported points to ensure
    our scoring engine is correct."""

    diffs = []
    for username, site_score in site.items():
        ours = computed.get(username, 0)
        if ours != site_score:
            diffs.append(f"{username}: site={site_score}, ours={ours}")
    if diffs:
        print(
            "[build] WARNING: scoring engine disagrees with site standings:\n  - "
            + "\n  - ".join(diffs),
            file=sys.stderr,
        )


def _build_leaderboard(
    snapshot: SiteSnapshot,
    sim: Any | None,
    current_pts: dict[str, int],
) -> list[LeaderboardRow]:
    """
    Build the leaderboard rows for rendering the HTML page.  If a simulation is available, use the
    median points from the simulation to rank and sort players.
    If no simulation is available, fall back to the current points.
    """

    rows: list[LeaderboardRow] = []
    for username in snapshot.players:
        if sim is None:
            rows.append(
                LeaderboardRow(
                    username=username,
                    current_pts=current_pts.get(username, 0),
                    median_pts=None,
                    p10_pts=None,
                    p90_pts=None,
                    win_prob=None,
                    tie_prob=None,
                )
            )
        else:
            rows.append(
                LeaderboardRow(
                    username=username,
                    current_pts=current_pts.get(username, 0),
                    median_pts=sim.median_final_pts[username],
                    p10_pts=sim.p10_final_pts[username],
                    p90_pts=sim.p90_final_pts[username],
                    win_prob=sim.win_prob[username],
                    tie_prob=sim.tie_prob[username],
                )
            )

    if sim is None:
        # No forecast → fall back to current points order.
        rows.sort(key=lambda r: r.current_pts, reverse=True)
    else:
        rows.sort(key=lambda r: r.median_pts or 0, reverse=True)
    return rows


_STATUS_LABELS = {
    "pre_release": "pre-release",
    "in_theaters": "in theaters",
    "closed": "closed",
    "wont_score": "won't score",
    "no_projection": "no projection",
}


def _build_movie_rows(
    movies: dict[str, dict[str, Any]],
    projections: list[Projection],
) -> list[MovieRow]:
    """
    Build the movie rows for rendering the HTML page.  Each row contains the movie title, release
    date, status, projected gross (median, p10, p90), cumulative gross to date, and source of the
    projection.
    Movies are ordered by their projected gross (highest first), then by release date (earliest
    first).  Movies with no projection (median=0) will be sorted by release date.
    """

    proj_by_title = {p.movie_title: p for p in projections}
    rows: list[MovieRow] = []
    for title, m in movies.items():
        proj = proj_by_title.get(title)

        # If no projection, then just add the movie and continue
        if proj is None or proj.median_in_window_gross == 0:
            if m["status"] == MovieStatus.PRE_RELEASE and m["release_date"] > WINDOW_END:
                status_key = "wont_score"
                src = "release after window"
            elif m["status"] == MovieStatus.PRE_RELEASE:
                status_key = "no_projection"
                src = "no analyst entry"
            else:
                status_key = m["status"].value
                src = "—"
            rows.append(
                MovieRow(
                    title=title,
                    release_date=m["release_date"].isoformat(),
                    status=status_key,
                    status_label=_STATUS_LABELS[status_key],
                    median_in_window_gross=0,
                    p10=0,
                    p90=0,
                    cumulative_to_date=m["cumulative"] or None,
                    source=src,
                )
            )
            continue

        # If there's a projection, then calculate the p10 and p90 values and add the movie row
        median = proj.median_in_window_gross
        remaining = max(0.0, median - proj.floor)
        p10 = proj.floor + remaining * math.exp(-1.2816 * proj.sigma)
        p90 = proj.floor + remaining * math.exp(1.2816 * proj.sigma)
        status_key = m["status"].value
        src = "decay model" if m["status"] == MovieStatus.IN_THEATERS else "analyst estimate"
        rows.append(
            MovieRow(
                title=title,
                release_date=m["release_date"].isoformat(),
                status=status_key,
                status_label=_STATUS_LABELS[status_key],
                median_in_window_gross=median,
                p10=p10,
                p90=p90,
                cumulative_to_date=m["cumulative"] or None,
                source=src,
            )
        )

    # The second sort takes precedence, so movies are primarily sorted by projected gross (highest
    # first) and secondarily by release date (soonest first).
    rows.sort(key=lambda r: r.release_date)
    rows.sort(key=lambda r: r.median_in_window_gross, reverse=True)
    return rows


def _build_player_details(
    snapshot: SiteSnapshot,
    projections: list[Projection],
    current_pts: dict[str, int],
    sim: Any | None,
) -> list[PlayerDetail]:
    """
    Each player detail contains the player's username, their ranked picks with projection details,
    and their dark horse picks with projection details.
    If a simulation is available, then the player's median points from the simulation is included.
    If no simulation is available, median points is None.
    The player's ranked and dark horse picks include the pick's projected rank and projected gross,
    and the user's projected points for the pick.
    Players are ordered by their median points if a simulation is available, otherwise by their
    current points.
    """

    proj_by_title = {p.movie_title: p for p in projections}
    median_top_10 = [
        p
        for p in sorted(
            proj_by_title.values(),
            key=lambda p: p.median_in_window_gross,
            reverse=True,
        )
        if p.median_in_window_gross > 0
    ][:10]
    median_top_titles = [p.movie_title for p in median_top_10]
    median_position = {t: i + 1 for i, t in enumerate(median_top_titles)}

    out: list[PlayerDetail] = []
    for username, picks in snapshot.players.items():
        ranked_details = [
            _pick_detail(title, idx + 1, proj_by_title, median_position, kind="ranked")
            for idx, title in enumerate(picks.ranked)
        ]
        dh_details = [
            _pick_detail(title, None, proj_by_title, median_position, kind="dark_horse")
            for title in picks.dark_horses
        ]
        out.append(
            PlayerDetail(
                username=username,
                median_pts=sim.median_final_pts[username] if sim is not None else None,
                current_pts=current_pts.get(username, 0),
                ranked=ranked_details,
                dark_horses=dh_details,
            )
        )
    if sim is None:
        out.sort(key=lambda p: p.current_pts, reverse=True)
    else:
        out.sort(key=lambda p: p.median_pts or 0, reverse=True)
    return out


def _pick_detail(
    title: str,
    predicted_rank: int | None,
    proj_by_title: dict[str, Projection],
    median_position: dict[str, int],
    *,
    kind: str,
) -> PickDetail:
    """
    For a given pick, determine the pick's projected rank, projected gross, and projected points.
    """

    proj = proj_by_title.get(title)

    # This is the key.  Based on the picks projected gross (and all other movies' projected
    # grosses), we can determine the pick's projected rank and projected points.
    # This allows us to project the points for each pick and by extension, the player's total
    # projected points at the end of the wager.
    median_gross = proj.median_in_window_gross if proj else 0.0
    actual_rank = median_position.get(title, 0)

    if kind == "ranked" and actual_rank > 0 and predicted_rank is not None:
        pts = ranked_pick_points(predicted_rank, actual_rank)
    elif kind == "dark_horse" and actual_rank > 0:
        pts = 1
    else:
        pts = 0
    return PickDetail(
        title=title,
        projected_rank=actual_rank or None,
        projected_gross=median_gross,
        projected_pts=pts,
    )


def _append_box_office_history(snapshot: SiteSnapshot, *, today: date) -> None:
    """
    Append the current box office data to history files for future reference.  This ensures our
    decay model has historical information to see week-over-week trends.
    It is skipped if --local is passed.
    """

    box_path = DATA_DIR / "box_office_history.jsonl"
    with box_path.open("a") as f:
        for movie, gross in snapshot.cumulative_grosses.items():
            f.write(
                json.dumps(
                    {
                        "movie": movie,
                        "date": today.isoformat(),
                        "cumulative_gross": gross,
                    }
                )
                + "\n"
            )


def _append_forecast_history(snapshot: SiteSnapshot, sim: Any, *, today: date) -> None:
    """
    Append the current forecast data to history files for future reference.  This allows us to see
    how our forecasts have changed over time and who was predicted to win at any given point in the
    season.
    It is skipped if --local is passed.
    """

    forecast_path = DATA_DIR / "forecast_history.jsonl"
    with forecast_path.open("a") as f:
        for username in snapshot.players:
            f.write(
                json.dumps(
                    {
                        "date": today.isoformat(),
                        "player": username,
                        "win_prob": sim.win_prob[username],
                        "median_final_pts": sim.median_final_pts[username],
                        "p10": sim.p10_final_pts[username],
                        "p90": sim.p90_final_pts[username],
                    }
                )
                + "\n"
            )


if __name__ == "__main__":
    raise SystemExit(main())
