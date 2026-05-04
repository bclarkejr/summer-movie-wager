"""Wager scoring rules per https://thesummermoviewager.com/help.php."""

from summer_movie_wager.types import PlayerPicks


def ranked_pick_points(predicted_position: int, actual_position: int) -> int:
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


# Backwards-compatible alias for the previously-private helper.
_ranked_pick_points = ranked_pick_points


def score_player(picks: PlayerPicks, top_titles: list[str]) -> int:
    """Compute the wager points a player earns given the (partial or complete) top finalists.

    `top_titles` is the rank-ordered list of the current/projected top finalists, length 0 to 10.
    Lengths above 10 are rejected. Lengths below 10 score every pick whose title matches one of
    the present ranks; absent ranks contribute 0 to the score.
    """
    if len(top_titles) > 10:
        raise ValueError(f"top_titles must have at most 10 entries, got {len(top_titles)}")

    actual_position: dict[str, int] = {title: i + 1 for i, title in enumerate(top_titles)}

    total = 0
    for predicted_index, title in enumerate(picks.ranked, start=1):
        total += ranked_pick_points(predicted_index, actual_position.get(title, 0))
    for dh in picks.dark_horses:
        if dh in actual_position:
            total += 1
    return total
