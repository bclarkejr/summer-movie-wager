from datetime import date
from pathlib import Path

import pytest

from summer_movie_wager.ingest.scraper import parse_snapshot

FIXTURE = Path(__file__).parent / "fixtures" / "playalong.html"
EXPECTED_USERNAMES = {
    "bclarke", "vivrad", "zmeister", "brettfern",
    "carleigh", "radhadr", "emsullivan", "mhartje",
}


@pytest.fixture
def snapshot():
    html = FIXTURE.read_text(encoding="utf-8")
    return parse_snapshot(html, captured_at=date(2026, 5, 3))


def test_all_eight_players_parsed(snapshot):
    assert set(snapshot.players.keys()) == EXPECTED_USERNAMES


def test_each_player_has_ten_ranked_and_three_dark_horses(snapshot):
    for username, picks in snapshot.players.items():
        assert len(picks.ranked) == 10, f"{username} ranked count wrong"
        assert len(picks.dark_horses) == 3, f"{username} dark horse count wrong"


def test_known_pick_present(snapshot):
    # bclarke's #1 pick is Toy Story 5 (verified by hand at /index.php inspection time)
    assert snapshot.players["bclarke"].ranked[0] == "Toy Story 5"


def test_cumulative_grosses_include_known_movie(snapshot):
    # The Devil Wears Prada 2 had ~$32.5M cumulative at 2026-05-03 capture
    keys_lower = {k.lower(): v for k, v in snapshot.cumulative_grosses.items()}
    matched = [
        v for k, v in keys_lower.items() if "devil wears prada" in k
    ]
    assert matched, "Devil Wears Prada 2 not found in cumulative_grosses"
    assert max(matched) > 1_000_000  # any reasonable post-opening number


def test_site_reported_points_present_for_all_players(snapshot):
    assert set(snapshot.site_reported_points.keys()) == EXPECTED_USERNAMES
    for v in snapshot.site_reported_points.values():
        assert isinstance(v, int)
        assert v >= 0
