"""Monte Carlo season simulator → per-player win probabilities + score percentiles."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from summer_movie_wager.score import score_player
from summer_movie_wager.types import PlayerPicks, Projection, WinningScenario


@dataclass(frozen=True)
class SimulationResult:
    win_prob: dict[str, float]
    tie_prob: dict[str, float]
    median_final_pts: dict[str, float]
    p10_final_pts: dict[str, float]
    p90_final_pts: dict[str, float]
    winning_scenarios: dict[str, "WinningScenario | None"] = field(default_factory=dict)


def simulate_season(
    players: list[PlayerPicks],
    projections: list[Projection],
    *,
    n_trials: int = 10_000,
    seed: int | None = None,
) -> SimulationResult:
    """
    Run Monte Carlo over per-movie lognormal samples.

    For each trial: sample each movie's gross, rank top 10, score every player, record outcome.
    """
    rng = np.random.default_rng(seed)
    movie_titles = [p.movie_title for p in projections]
    n_movies = len(movie_titles)
    if n_movies < 10:
        raise ValueError(f"need at least 10 projected movies, got {n_movies}")

    medians = np.array([p.median_in_window_gross for p in projections], dtype=float)
    sigmas = np.array([p.sigma for p in projections], dtype=float)
    floors = np.array([p.floor for p in projections], dtype=float)
    remaining = np.maximum(0.0, medians - floors)

    # Uncertainty applies only to the unbanked (remaining) gross:
    #   total = floor + remaining * exp(sigma * Z)
    # exp() is always positive, so a sample can never fall below the banked floor.
    # Pre-release titles have floor=0, recovering the plain lognormal draw.
    samples = np.zeros((n_trials, n_movies), dtype=float)
    draw = remaining > 0
    if draw.any():
        z = rng.standard_normal((n_trials, int(draw.sum())))
        samples[:, draw] = remaining[draw] * np.exp(sigmas[draw] * z)
    samples += floors

    # Rank each row, take top-10 indices descending by gross
    # argsort ascending; reverse and slice first 10
    top_10_indices = np.argsort(-samples, axis=1)[:, :10]

    # Score each player against each trial's top-10
    pts_per_player: dict[str, np.ndarray] = {}
    for player in players:
        scores = np.empty(n_trials, dtype=int)
        for trial in range(n_trials):
            top_titles = [movie_titles[i] for i in top_10_indices[trial]]
            scores[trial] = score_player(player, top_titles)
        pts_per_player[player.username] = scores

    # Aggregate outcomes per player
    # Effectively each row is a player and each column is a trial.  We want to know for each player how many trials they won, tied, and their score percentiles.
    # It's a 2D array / matrix that we can then quickly figure out how many trials each player won, tied, and their score percentiles.
    score_matrix = np.stack([pts_per_player[p.username] for p in players])  # (n_players, n_trials)
    max_per_trial = score_matrix.max(axis=0)
    # When comparing arrays, this produces a boolean array of the same shape as score_matrix, where each element is True if that player's score equals the max score for that trial.
    is_top = score_matrix == max_per_trial
    n_winners_per_trial = is_top.sum(axis=0)

    win_prob: dict[str, float] = {}
    tie_prob: dict[str, float] = {}
    median_pts: dict[str, float] = {}
    p10_pts: dict[str, float] = {}
    p90_pts: dict[str, float] = {}

    for i, player in enumerate(players):
        is_top_player = is_top[i]
        strict_wins = (is_top_player & (n_winners_per_trial == 1)).sum()
        ties = (is_top_player & (n_winners_per_trial > 1)).sum()
        win_prob[player.username] = float(strict_wins) / n_trials
        tie_prob[player.username] = float(ties) / n_trials
        s = score_matrix[i]
        median_pts[player.username] = float(np.median(s))
        p10_pts[player.username] = float(np.percentile(s, 10))
        p90_pts[player.username] = float(np.percentile(s, 90))

    return SimulationResult(
        win_prob=win_prob,
        tie_prob=tie_prob,
        median_final_pts=median_pts,
        p10_final_pts=p10_pts,
        p90_final_pts=p90_pts,
    )
