from datetime import date

import pytest

from summer_movie_wager.types import (
    Category,
    Confidence,
    MovieStatus,
    PlayerPicks,
    Projection,
    SiteSnapshot,
)


def test_player_picks_validates_counts():
    picks = PlayerPicks(
        username="bclarke",
        ranked=["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
        dark_horses=["K", "L", "M"],
    )
    assert picks.username == "bclarke"
    assert len(picks.ranked) == 10
    assert len(picks.dark_horses) == 3


def test_player_picks_rejects_wrong_ranked_count():
    with pytest.raises(ValueError):
        PlayerPicks(username="x", ranked=["A"] * 9, dark_horses=["K", "L", "M"])


def test_player_picks_rejects_wrong_dark_horse_count():
    with pytest.raises(ValueError):
        PlayerPicks(username="x", ranked=["A"] * 10, dark_horses=["K", "L"])


def test_player_picks_rejects_duplicate_titles():
    with pytest.raises(ValueError):
        PlayerPicks(
            username="x",
            ranked=["A", "A", "B", "C", "D", "E", "F", "G", "H", "I"],
            dark_horses=["J", "K", "L"],
        )


def test_projection_records_median_and_sigma():
    p = Projection(movie_title="Toy Story 5", median_in_window_gross=180_000_000.0, sigma=0.30)
    assert p.median_in_window_gross == 180_000_000.0
    assert p.sigma == 0.30


def test_projection_floor_defaults_to_zero():
    p = Projection(movie_title="Toy Story 5", median_in_window_gross=180_000_000.0, sigma=0.30)
    assert p.floor == 0.0


def test_projection_floor_can_be_set():
    p = Projection(
        movie_title="The Devil Wears Prada 2",
        median_in_window_gross=221_000_000.0,
        sigma=0.10,
        floor=219_602_888.0,
    )
    assert p.floor == 219_602_888.0


def test_confidence_values():
    assert Confidence.HIGH.value == "high"
    assert Confidence.MED.value == "med"
    assert Confidence.LOW.value == "low"


def test_site_snapshot_holds_picks_and_grosses():
    snapshot = SiteSnapshot(
        captured_at=date(2026, 5, 3),
        players={
            "bclarke": PlayerPicks(
                username="bclarke",
                ranked=["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
                dark_horses=["K", "L", "M"],
            ),
        },
        cumulative_grosses={"A": 32_500_000.0},
        site_reported_points={"bclarke": 3},
    )
    assert snapshot.players["bclarke"].ranked[0] == "A"
    assert snapshot.cumulative_grosses["A"] == 32_500_000.0
    assert snapshot.site_reported_points["bclarke"] == 3
