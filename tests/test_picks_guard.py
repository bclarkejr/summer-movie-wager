from pathlib import Path

import pytest
import yaml

from summer_movie_wager.ingest.picks_guard import (
    PicksDriftError,
    bootstrap_or_validate,
)
from summer_movie_wager.types import PlayerPicks


def _picks(username: str, ranked: list[str], dark_horses: list[str]) -> PlayerPicks:
    return PlayerPicks(username=username, ranked=ranked, dark_horses=dark_horses)


def test_bootstrap_writes_snapshot_when_missing(tmp_path: Path):
    snapshot_path = tmp_path / "picks_snapshot_2026.yaml"
    scraped = {"bclarke": _picks("bclarke", [f"M{i}" for i in range(1, 11)], ["DH1", "DH2", "DH3"])}
    bootstrap_or_validate(scraped, snapshot_path)
    assert snapshot_path.exists()
    written = yaml.safe_load(snapshot_path.read_text())
    assert "bclarke" in written
    assert written["bclarke"]["ranked"][0] == "M1"


def test_validate_passes_on_match(tmp_path: Path):
    snapshot_path = tmp_path / "picks_snapshot_2026.yaml"
    scraped = {"bclarke": _picks("bclarke", [f"M{i}" for i in range(1, 11)], ["DH1", "DH2", "DH3"])}
    bootstrap_or_validate(scraped, snapshot_path)
    bootstrap_or_validate(scraped, snapshot_path)


def test_validate_raises_on_drift(tmp_path: Path):
    snapshot_path = tmp_path / "picks_snapshot_2026.yaml"
    original = {
        "bclarke": _picks("bclarke", [f"M{i}" for i in range(1, 11)], ["DH1", "DH2", "DH3"])
    }
    bootstrap_or_validate(original, snapshot_path)

    drifted = {
        "bclarke": _picks(
            "bclarke",
            ["DIFFERENT"] + [f"M{i}" for i in range(2, 11)],
            ["DH1", "DH2", "DH3"],
        )
    }
    with pytest.raises(PicksDriftError):
        bootstrap_or_validate(drifted, snapshot_path)


def test_validate_raises_on_missing_player(tmp_path: Path):
    snapshot_path = tmp_path / "picks_snapshot_2026.yaml"
    original = {
        "bclarke": _picks("bclarke", [f"M{i}" for i in range(1, 11)], ["DH1", "DH2", "DH3"]),
        "vivrad": _picks("vivrad", [f"V{i}" for i in range(1, 11)], ["VD1", "VD2", "VD3"]),
    }
    bootstrap_or_validate(original, snapshot_path)

    drifted = {"bclarke": original["bclarke"]}
    with pytest.raises(PicksDriftError):
        bootstrap_or_validate(drifted, snapshot_path)


def test_validate_passes_when_dark_horses_reordered(tmp_path: Path):
    snapshot_path = tmp_path / "picks_snapshot_2026.yaml"
    original = {
        "bclarke": _picks("bclarke", [f"M{i}" for i in range(1, 11)], ["DH1", "DH2", "DH3"])
    }
    bootstrap_or_validate(original, snapshot_path)

    reordered = {
        "bclarke": _picks("bclarke", [f"M{i}" for i in range(1, 11)], ["DH3", "DH1", "DH2"])
    }
    # Dark horses are unordered — reorder must not trigger drift.
    bootstrap_or_validate(reordered, snapshot_path)
