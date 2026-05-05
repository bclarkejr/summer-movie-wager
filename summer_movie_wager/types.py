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


class MovieRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str
    release_date: date
    status: MovieStatus
    category: Category = Category.WIDE
    cumulative_gross_in_window: float = 0.0
    source: str = "scrape"


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


class SiteSnapshot(BaseModel):
    """One scrape of the play-along URL."""

    model_config = ConfigDict(frozen=True)

    captured_at: date
    players: dict[str, PlayerPicks]
    cumulative_grosses: dict[str, float]
    site_reported_points: dict[str, int]
