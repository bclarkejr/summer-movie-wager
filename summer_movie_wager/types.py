"""Typed records used across the pipeline."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MovieStatus(StrEnum):
    PRE_RELEASE = "pre_release"
    IN_THEATERS = "in_theaters"
    CLOSED = "closed"


class Category(StrEnum):
    WIDE = "wide"
    ANIMATED_FAMILY = "animated_family"


class Confidence(StrEnum):
    HIGH = "high"
    MED = "med"
    LOW = "low"


class PlayerPicks(BaseModel):
    """A player is defined by three properties - their username, their ranked top 10 picks, and
    their dark horse picks."""

    model_config = ConfigDict(frozen=True)

    username: str
    ranked: list[str] = Field(min_length=10, max_length=10)
    dark_horses: list[str] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def _no_duplicate_titles(self) -> PlayerPicks:
        all_titles = self.ranked + self.dark_horses
        if len(set(all_titles)) != len(all_titles):
            raise ValueError("a player's 13 picks must all be distinct movie titles")
        return self


class PreopeningEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    release_date: date
    opening_weekend_estimate: float | None = None
    total_domestic_estimate: float | None = None
    confidence: Confidence | None = None
    source: str | None = None
    as_of: date | None = None
    notes: str = ""


class Projection(BaseModel):
    model_config = ConfigDict(frozen=True)

    movie_title: str
    median_in_window_gross: float
    sigma: float
    floor: float = 0.0


class WinningScenario(BaseModel):
    """The most-likely actual top-10 finish in which a given player wins.

    films:  10 actual titles in finish order #1..#10.
    grid:   username -> per-rank points (len 10) for this finish.
    totals: username -> total points for this finish.
    win_pct: the player's overall win probability, as a percent (0..100).
    margin:  winner total minus runner-up total (>= 1)."""

    model_config = ConfigDict(frozen=True)

    films: list[str]
    grid: dict[str, list[int]]
    totals: dict[str, int]
    win_pct: float
    margin: int


class SiteSnapshot(BaseModel):
    """
    This site snapshot comes from thesummermoviewager.com and is used to validate the pipeline's
    calculations against the site's reported points.
    The direct link to the snapshot is at:
    https://thesummermoviewager.com/index.php?year=2026&addPlayer=bclarke%2Cvivrad%2Czmeister%2Cbrettfern%2Ccarleigh%2Cradhadr%2Cemsullivan%2Cmhartje%2CAverageJoe&playAlongOnly=

    The snapshot creates three dictionaries that we use to confirm our calculations are correct. The
    three dictionaries are:
    1. players:  A dictionary of player usernames to their picks (PlayerPicks), validating the picks
    match what we have in data/picks_snapshot_2026.yaml.
    2. cumulative_grosses:  A dictionary of movie titles to their cumulative grosses, which we use
    to calculate what _we_ think the points should be for each player.
    3. site_reported_points:  A dictionary of player usernames to their points, as reported by
    thesummermoviewager.com.  We use this to validate our own calculations against the site.
    """

    model_config = ConfigDict(frozen=True)

    captured_at: date
    players: dict[str, PlayerPicks]
    cumulative_grosses: dict[str, float]
    site_reported_points: dict[str, int]
