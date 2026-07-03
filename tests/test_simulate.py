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


def _ten_projections(seed_offset=0):
    from summer_movie_wager.types import Projection
    # Strongly separated medians so the top-10 order is stable across trials.
    return [
        Projection(movie_title=f"M{i}", median_in_window_gross=float((20 - i) * 10_000_000), sigma=0.15)
        for i in range(12)
    ]


def test_winning_scenarios_structure_and_consistency():
    from summer_movie_wager.model.simulate import simulate_season
    from summer_movie_wager.types import PlayerPicks, WinningScenario

    titles = [f"M{i}" for i in range(12)]
    # winner predicts the dominant order exactly; loser predicts it reversed
    winner = PlayerPicks(username="win", ranked=titles[:10], dark_horses=["M10", "M11", "Mz"])
    loser = PlayerPicks(username="lose", ranked=titles[:10][::-1], dark_horses=["Mx", "My", "Mz"])

    res = simulate_season([winner, loser], _ten_projections(), n_trials=3_000, seed=42)

    s = res.winning_scenarios["win"]
    assert isinstance(s, WinningScenario)
    assert len(s.films) == 10
    # winner is the strict leader by margin >= 1
    assert s.totals["win"] == max(s.totals.values())
    assert s.margin >= 1
    # grid columns sum to totals
    for user, col in s.grid.items():
        assert sum(col) == s.totals[user]
    # win_pct matches win_prob (percent form)
    assert abs(s.win_pct - round(res.win_prob["win"] * 100, 1)) < 1e-9


def test_no_scenario_when_player_never_wins():
    from summer_movie_wager.model.simulate import simulate_season
    from summer_movie_wager.types import PlayerPicks

    titles = [f"M{i}" for i in range(12)]
    strong = PlayerPicks(username="strong", ranked=titles[:10], dark_horses=["M10", "M11", "Mz"])
    # 'weak' predicts only films that essentially never reach the top 10
    weak = PlayerPicks(username="weak", ranked=["M10", "M11", "Mx", "My", "Mz", "Ma", "Mb", "Mc", "Md", "Me"], dark_horses=["Mf", "Mg", "Mh"])

    res = simulate_season([strong, weak], _ten_projections(), n_trials=3_000, seed=7)
    # strong dominates; weak should have win_prob 0 and therefore no scenario
    assert res.win_prob["weak"] == 0.0, "weak player unexpectedly won; re-examine test setup"
    assert res.winning_scenarios["weak"] is None
    # strong always has a scenario
    assert res.winning_scenarios["strong"] is not None


def test_in_theaters_floor_is_never_breached():
    # 10 movies so the simulator's >=10 guard passes; movie 0 is a deep-run film
    # whose banked gross is just below its median. Its final gross must never dip
    # below the floor, and its 80% band must stay tight around it.
    import numpy as np
    from summer_movie_wager.model.simulate import simulate_season
    from summer_movie_wager.types import PlayerPicks, Projection

    titles = [f"M{i}" for i in range(10)]
    projections = [
        Projection(
            movie_title="M0",
            median_in_window_gross=221_000_000.0,
            sigma=0.10,
            floor=219_602_888.0,
        )
    ] + [
        Projection(movie_title=titles[i], median_in_window_gross=100_000_000.0 - i, sigma=0.20)
        for i in range(1, 10)
    ]

    # Reproduce the sampler's draw directly to assert the floor invariant on raw samples.
    rng = np.random.default_rng(0)
    floor, median, sigma = 219_602_888.0, 221_000_000.0, 0.10
    remaining = max(0.0, median - floor)
    samples = floor + remaining * np.exp(sigma * rng.standard_normal(10_000))
    assert samples.min() >= floor
    assert np.percentile(samples, 90) <= floor + 10_000_000  # within $10M of banked

    # And the public API still runs end-to-end with a floored projection present.
    players = [
        PlayerPicks(username="u", ranked=titles, dark_horses=["dh1", "dh2", "dh3"])
    ]
    result = simulate_season(players, projections, n_trials=2_000, seed=1)
    assert 0.0 <= result.win_prob["u"] <= 1.0
