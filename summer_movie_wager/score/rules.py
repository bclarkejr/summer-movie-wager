"""Wager scoring rules per https://thesummermoviewager.com/help.php."""

from summer_movie_wager.types import PlayerPicks


def _ranked_pick_points(predicted_position: int, actual_position: int) -> int:
    """Points for a single ranked pick. Positions are 1-indexed; actual_position is 0 for missed."""
    if actual_position == 0:  # not in top 10
        return 0
    distance = abs(predicted_position - actual_position)
    if distance == 0:
        # 13 if at endpoints (#1 or #10), 10 otherwise
        return 13 if actual_position in (1, 10) else 10
    if distance == 1:
        return 7
    if distance == 2:
        return 5
    return 3  # in top 10 but off by 3+


def score_player(picks: PlayerPicks, top_10: list[str]) -> int:
    """Compute the wager points a player earns given the final top 10 (rank-ordered)."""
    if len(top_10) != 10:
        raise ValueError(f"top_10 must have exactly 10 entries, got {len(top_10)}")

    actual_position: dict[str, int] = {title: i + 1 for i, title in enumerate(top_10)}

    total = 0
    for predicted_index, title in enumerate(picks.ranked, start=1):
        total += _ranked_pick_points(predicted_index, actual_position.get(title, 0))
    for dh in picks.dark_horses:
        if dh in actual_position:
            total += 1
    return total
