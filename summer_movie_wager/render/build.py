"""End-to-end pipeline: ingest → project → simulate → render."""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

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
from summer_movie_wager.score import score_player
from summer_movie_wager.score.rules import _ranked_pick_points
from summer_movie_wager.types import (
    Category,
    Confidence,
    MovieStatus,
    PlayerPicks,
    PreopeningEntry,
    Projection,
    SiteSnapshot,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
DOCS_DIR = REPO_ROOT / "docs"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh the Summer Movie Wager site")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Run pipeline locally; do not append to history files.",
    )
    args = parser.parse_args(argv)

    today = date.today()
    print(f"[build] fetching site snapshot ({today})", file=sys.stderr)
    snapshot = fetch_snapshot(captured_at=today)

    print("[build] validating picks against snapshot", file=sys.stderr)
    bootstrap_or_validate(snapshot.players, DATA_DIR / "picks_snapshot_2026.yaml")

    overrides = _load_yaml(DATA_DIR / "movies_overrides.yaml")
    preopening_raw = _load_yaml(DATA_DIR / "preopening_projections.yaml")
    preopening = _parse_preopening(preopening_raw)

    movies = _normalize_movies(snapshot, overrides, preopening, today=today)
    projections = _project_all(movies, preopening, snapshot, overrides, today=today)

    sim = simulate_season(
        list(snapshot.players.values()),
        projections,
        n_trials=10_000,
        seed=20260907,
    )

    current_top10 = _current_top_10(snapshot.cumulative_grosses)
    current_pts = {
        username: score_player(picks, current_top10)
        for username, picks in snapshot.players.items()
    }
    _validate_against_site(current_pts, snapshot.site_reported_points)

    leaderboard = _build_leaderboard(snapshot, sim, current_pts)
    movie_rows = _build_movie_rows(movies, projections, snapshot, sim, current_top10)
    player_details = _build_player_details(snapshot, projections, current_pts, sim)

    raw = {
        "captured_at": str(snapshot.captured_at),
        "site_reported_points": snapshot.site_reported_points,
        "computed_current_points": current_pts,
        "win_prob": sim.win_prob,
        "tie_prob": sim.tie_prob,
        "median_final_pts": sim.median_final_pts,
        "p10_final_pts": sim.p10_final_pts,
        "p90_final_pts": sim.p90_final_pts,
        "projections": [p.model_dump() for p in projections],
    }

    render(
        DOCS_DIR,
        RenderInput(
            generated_at=datetime.now(timezone.utc),
            leaderboard=leaderboard,
            movies=movie_rows,
            player_details=player_details,
            raw_snapshot=raw,
        ),
    )

    if not args.local:
        _append_history(snapshot, sim, today=today)

    print(f"[build] wrote {DOCS_DIR}/index.html", file=sys.stderr)
    return 0


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _parse_preopening(raw: dict[str, Any]) -> dict[str, PreopeningEntry]:
    out: dict[str, PreopeningEntry] = {}
    for title, entry in raw.items():
        out[title] = PreopeningEntry(
            release_date=date.fromisoformat(str(entry["release_date"])),
            opening_weekend_estimate=float(entry["opening_weekend_estimate"]),
            total_domestic_estimate=float(entry["total_domestic_estimate"]),
            confidence=Confidence(entry["confidence"]),
            source=str(entry["source"]),
            as_of=date.fromisoformat(str(entry["as_of"])),
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
    movies: dict[str, dict[str, Any]] = {}
    candidates: set[str] = set()
    for picks in snapshot.players.values():
        candidates.update(picks.ranked + picks.dark_horses)
    candidates.update(preopening.keys())
    candidates.update(snapshot.cumulative_grosses.keys())

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


def _project_all(
    movies: dict[str, dict[str, Any]],
    preopening: dict[str, PreopeningEntry],
    snapshot: SiteSnapshot,
    overrides: dict[str, Any],
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
        elif m["status"] == MovieStatus.PRE_RELEASE and title in preopening:
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
        projections.append(
            Projection(movie_title=title, median_in_window_gross=gross, sigma=sigma)
        )
    return projections


def _load_history() -> dict[str, list[tuple[date, float]]]:
    path = DATA_DIR / "box_office_history.jsonl"
    if not path.exists():
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


def _current_top_10(grosses: dict[str, float]) -> list[str]:
    """Return up to 10 titles ranked by gross (descending). Pads with empty strings if fewer."""
    ranked = [
        title
        for title, _ in sorted(grosses.items(), key=lambda kv: kv[1], reverse=True)
    ][:10]
    while len(ranked) < 10:
        # score_player requires exactly 10 entries; pad with sentinels that no pick will match.
        ranked.append(f"__no_movie_{len(ranked)}__")
    return ranked


def _validate_against_site(
    computed: dict[str, int],
    site: dict[str, int],
) -> None:
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
    sim: Any,
    current_pts: dict[str, int],
) -> list[LeaderboardRow]:
    rows: list[LeaderboardRow] = []
    for username in snapshot.players:
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
    rows.sort(key=lambda r: r.median_pts, reverse=True)
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
    snapshot: SiteSnapshot,
    sim: Any,
    current_top10: list[str],
) -> list[MovieRow]:
    proj_by_title = {p.movie_title: p for p in projections}
    rows: list[MovieRow] = []
    for title, m in movies.items():
        proj = proj_by_title.get(title)
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
        median = proj.median_in_window_gross
        p10 = median * math.exp(-1.2816 * proj.sigma)
        p90 = median * math.exp(1.2816 * proj.sigma)
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
    rows.sort(key=lambda r: r.median_in_window_gross, reverse=True)
    return rows


def _build_player_details(
    snapshot: SiteSnapshot,
    projections: list[Projection],
    current_pts: dict[str, int],
    sim: Any,
) -> list[PlayerDetail]:
    proj_by_title = {p.movie_title: p for p in projections}
    median_top_10 = sorted(
        proj_by_title.values(),
        key=lambda p: p.median_in_window_gross,
        reverse=True,
    )[:10]
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
                median_pts=sim.median_final_pts[username],
                current_pts=current_pts.get(username, 0),
                ranked=ranked_details,
                dark_horses=dh_details,
            )
        )
    out.sort(key=lambda p: p.median_pts, reverse=True)
    return out


def _pick_detail(
    title: str,
    predicted_rank: int | None,
    proj_by_title: dict[str, Projection],
    median_position: dict[str, int],
    *,
    kind: str,
) -> PickDetail:
    proj = proj_by_title.get(title)
    median_gross = proj.median_in_window_gross if proj else 0.0
    actual_rank = median_position.get(title, 0)
    if kind == "ranked" and actual_rank > 0 and predicted_rank is not None:
        pts = _ranked_pick_points(predicted_rank, actual_rank)
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


def _append_history(snapshot: SiteSnapshot, sim: Any, *, today: date) -> None:
    box_path = DATA_DIR / "box_office_history.jsonl"
    forecast_path = DATA_DIR / "forecast_history.jsonl"
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
