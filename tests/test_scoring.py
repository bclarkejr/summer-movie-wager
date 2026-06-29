import pytest

from summer_movie_wager.score import score_player
from summer_movie_wager.score.rules import score_breakdown
from summer_movie_wager.types import PlayerPicks


def make_picks(ranked: list[str], dark_horses: list[str] | None = None) -> PlayerPicks:
    if dark_horses is None:
        dark_horses = ["DH1", "DH2", "DH3"]
    # Pad ranked to 10 with disposable titles if caller passed fewer
    padded = list(ranked)
    i = 0
    while len(padded) < 10:
        padded.append(f"_filler_{i}")
        i += 1
    return PlayerPicks(username="t", ranked=padded[:10], dark_horses=dark_horses)


def test_correct_number_one_scores_13():
    picks = make_picks(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"])
    top_10 = ["A", "X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9"]
    assert score_player(picks, top_10) == 13  # A in #1 = 13; rest of picks miss top 10


def test_correct_number_ten_scores_13():
    picks = make_picks(["X", "Y", "Z", "Q", "R", "S", "T", "U", "V", "W"])
    top_10 = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "W"]  # W is in #10
    assert score_player(picks, top_10) == 13


def test_correct_middle_position_scores_10():
    picks = make_picks(["X", "X2", "X3", "X4", "TARGET", "X5", "X6", "X7", "X8", "X9"])
    top_10 = ["A1", "A2", "A3", "A4", "TARGET", "A6", "A7", "A8", "A9", "A10"]
    assert score_player(picks, top_10) == 10


def test_off_by_one_scores_7():
    # TARGET picked at #5, actual #6 → off by 1
    picks = make_picks(["X", "X2", "X3", "X4", "TARGET", "X5", "X6", "X7", "X8", "X9"])
    top_10 = ["A1", "A2", "A3", "A4", "A5", "TARGET", "A7", "A8", "A9", "A10"]
    assert score_player(picks, top_10) == 7


def test_off_by_two_scores_5():
    picks = make_picks(["X", "X2", "X3", "TARGET", "X4", "X5", "X6", "X7", "X8", "X9"])
    top_10 = ["A1", "A2", "A3", "A4", "A5", "TARGET", "A7", "A8", "A9", "A10"]
    assert score_player(picks, top_10) == 5


def test_in_top_ten_off_by_three_scores_3():
    picks = make_picks(["TARGET", "X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9"])
    top_10 = ["A1", "A2", "A3", "TARGET", "A5", "A6", "A7", "A8", "A9", "A10"]
    assert score_player(picks, top_10) == 3


def test_missed_top_ten_scores_zero():
    picks = make_picks(["TARGET", "X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9"])
    top_10 = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10"]
    assert score_player(picks, top_10) == 0


def test_dark_horse_in_top_ten_scores_1():
    picks = make_picks(
        ["X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9", "X10"],
        dark_horses=["DARK", "DH2", "DH3"],
    )
    top_10 = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "DARK"]
    assert score_player(picks, top_10) == 1


def test_dark_horse_outside_top_ten_scores_zero():
    picks = make_picks(
        ["X1", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9", "X10"],
        dark_horses=["DARK", "DH2", "DH3"],
    )
    top_10 = ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "A10"]
    assert score_player(picks, top_10) == 0


def test_combined_realistic_scenario():
    # Picks: #1 perfect, #4 off by 1, #6 in top 10 off by 4, #9 missed; one dark horse hits.
    picks = make_picks(
        [
            "PERFECT_1",
            "X2",
            "X3",
            "OFF_BY_ONE",
            "X5",
            "TOP10_BUT_FAR",
            "X7",
            "X8",
            "MISSED",
            "X10",
        ],
        dark_horses=["DARK_HIT", "DH2", "DH3"],
    )
    top_10 = [
        "PERFECT_1",   # picked #1, actual #1 → 13
        "TOP10_BUT_FAR",  # picked #6, actual #2 → in top 10 off by 4 → 3
        "A3",
        "A4",
        "OFF_BY_ONE",  # picked #4, actual #5 → off by 1 → 7
        "A6",
        "A7",
        "A8",
        "A9",
        "DARK_HIT",  # dark horse in top 10 → 1
    ]
    # MISSED isn't in top 10 → 0
    assert score_player(picks, top_10) == 13 + 3 + 7 + 1


def test_top_titles_more_than_ten_raises():
    picks = make_picks(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"])
    with pytest.raises(ValueError):
        score_player(picks, [f"X{i}" for i in range(11)])


def test_partial_top_titles_scores_only_present_ranks():
    # Only 3 finalists known: only those ranks count.
    # Picks: TARGET at #1 (matches actual #1 → 13). Other picks would-be-actual ranks
    # are unknown, so they score 0.
    picks = make_picks(["TARGET", "X2", "X3", "X4", "X5", "X6", "X7", "X8", "X9", "X10"])
    assert score_player(picks, ["TARGET", "B", "C"]) == 13


def test_empty_top_titles_scores_zero():
    picks = make_picks(["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"])
    assert score_player(picks, []) == 0


def _picks_for_breakdown() -> PlayerPicks:
    return PlayerPicks(
        username="t",
        ranked=[f"R{i}" for i in range(1, 11)],   # R1..R10 predicted #1..#10
        dark_horses=["D1", "D2", "D3"],
    )


def test_breakdown_sums_to_score_player():
    picks = _picks_for_breakdown()
    # actual top 10: R1 exact #1, R3 at #2 (off by 1), a dark horse D2 at #5, rest unknowns
    top = ["R1", "R3", "X", "X4", "D2", "X6", "X7", "X8", "X9", "X10"]
    b = score_breakdown(picks, top)
    assert len(b) == len(top)
    assert sum(b) == score_player(picks, top)
    assert b[0] == 13          # R1 exact at endpoint #1
    assert b[1] == 7           # R3 predicted #3, actual #2 -> off by 1
    assert b[4] == 1           # dark horse D2 landed at #5


def test_breakdown_zero_for_absent_picks():
    picks = _picks_for_breakdown()
    top = ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7", "Z8", "Z9", "Z10"]
    b = score_breakdown(picks, top)
    assert b == [0] * 10
    assert score_player(picks, top) == 0
