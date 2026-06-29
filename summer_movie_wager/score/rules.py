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


def score_breakdown(picks: PlayerPicks, top_titles: list[str]) -> list[int]:
    """Points each actual finisher contributes for `picks`, indexed by actual
    position. len == len(top_titles). Includes the +1 dark-horse bonus on the
    rank where a dark horse lands. sum(...) == score_player(picks, top_titles)."""
    if len(top_titles) > 10:
        raise ValueError(f"top_titles must have at most 10 entries, got {len(top_titles)}")
    actual_position = {title: i + 1 for i, title in enumerate(top_titles)}
    breakdown = [0] * len(top_titles)
    for predicted_index, title in enumerate(picks.ranked, start=1):
        pos = actual_position.get(title, 0)
        if pos:
            breakdown[pos - 1] += ranked_pick_points(predicted_index, pos)
    for dh in picks.dark_horses:
        pos = actual_position.get(dh, 0)
        if pos:
            breakdown[pos - 1] += 1
    return breakdown


def score_player(picks: PlayerPicks, top_titles: list[str]) -> int:
    """
    Compute the wager points a player earns given the (partial or complete) top finalists.

    `top_titles` is the rank-ordered list of the current/projected top finalists, length 0 to 10.
    Lengths above 10 are rejected. Lengths below 10 score every pick whose title matches one of
    the present ranks; absent ranks contribute 0 to the score.
    """
    return sum(score_breakdown(picks, top_titles))
