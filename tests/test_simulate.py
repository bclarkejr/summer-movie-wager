import pytest

from summer_movie_wager.model.simulate import simulate_season
from summer_movie_wager.types import PlayerPicks, Projection


def _picks(username: str, ranked: list[str]) -> PlayerPicks:
    return PlayerPicks(
        username=username,
        ranked=ranked,
        dark_horses=["DH1", "DH2", "DH3"],
    )


def test_certain_winner_has_high_win_prob():
    # Player A picks the 10 movies guaranteed to be top 10 (sigma 0). Should win every sim.
    movie_titles = [f"M{i}" for i in range(1, 11)]
    projections = [
        Projection(movie_title=t, median_in_window_gross=1_000_000_000 - i * 1_000_000, sigma=0.001)
        for i, t in enumerate(movie_titles)
    ]
    players = [
        _picks("perfect", movie_titles),
        _picks("bad", [f"X{i}" for i in range(1, 11)]),
    ]
    result = simulate_season(players, projections, n_trials=2000, seed=42)
    assert result.win_prob["perfect"] > 0.95
    assert result.win_prob["bad"] < 0.05
    # tie + win must be ≤ 1.0 per player; sum across all players ≥ 1
    # (some sim has a winner each time)
    for username in ["perfect", "bad"]:
        assert 0.0 <= result.win_prob[username] <= 1.0
        assert 0.0 <= result.tie_prob[username] <= 1.0


def test_prediction_intervals_make_sense():
    movie_titles = [f"M{i}" for i in range(1, 11)]
    projections = [
        Projection(movie_title=t, median_in_window_gross=200_000_000 - i * 5_000_000, sigma=0.30)
        for i, t in enumerate(movie_titles)
    ]
    players = [_picks("a", movie_titles)]
    result = simulate_season(players, projections, n_trials=5000, seed=1)
    p10 = result.p10_final_pts["a"]
    median = result.median_final_pts["a"]
    p90 = result.p90_final_pts["a"]
    assert p10 <= median <= p90


def test_deterministic_with_seed():
    movie_titles = [f"M{i}" for i in range(1, 11)]
    projections = [
        Projection(movie_title=t, median_in_window_gross=100_000_000, sigma=0.20)
        for t in movie_titles
    ]
    players = [_picks("a", movie_titles), _picks("b", list(reversed(movie_titles)))]
    r1 = simulate_season(players, projections, n_trials=500, seed=99)
    r2 = simulate_season(players, projections, n_trials=500, seed=99)
    assert r1.win_prob == r2.win_prob


def test_win_and_tie_probs_sum_to_one_across_players():
    # Across all players: P(win) + P(tied with anyone) sum to ~total trials worth of outcomes.
    # Simpler invariant: sum(win_prob[p]) + max(tie_prob[p]) >= 1 - epsilon
    # when there is always a winner.
    movie_titles = [f"M{i}" for i in range(1, 11)]
    projections = [
        Projection(movie_title=t, median_in_window_gross=100_000_000, sigma=0.20)
        for t in movie_titles
    ]
    players = [_picks(f"p{i}", movie_titles) for i in range(3)]
    result = simulate_season(players, projections, n_trials=1000, seed=7)
    total_outcomes = sum(result.win_prob[p.username] for p in players) + max(
        result.tie_prob[p.username] for p in players
    )
    assert total_outcomes == pytest.approx(1.0, abs=0.05)


def test_zero_sigma_movies_make_outcome_deterministic():
    # All projections have sigma=0; result should be a single deterministic ranking per sim.
    movie_titles = [f"M{i}" for i in range(1, 11)]
    projections = [
        Projection(movie_title=t, median_in_window_gross=100_000_000 - i * 1_000_000, sigma=0.0)
        for i, t in enumerate(movie_titles)
    ]
    players = [_picks("a", movie_titles), _picks("b", list(reversed(movie_titles)))]
    result = simulate_season(players, projections, n_trials=500, seed=3)
    # Either a wins all or b wins all (depending on actual scoring) — but no variance.
    assert (
        result.win_prob["a"] in (0.0, 1.0) or result.win_prob["b"] in (0.0, 1.0)
        or abs(result.win_prob["a"] - result.win_prob["b"]) > 0.5
    )
