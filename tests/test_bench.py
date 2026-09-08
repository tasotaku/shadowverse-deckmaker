"""探索用PP基準がルールの境界を越えないことを確認する。"""

import pytest

from svdeck.bench import DEADLINE_CUM_PP, DEADLINE_TURN, cumulative_pp_for_turn


@pytest.mark.parametrize(('turn', 'expected'), [(1, 2), (5, 16), (6, 23), (10, 57), (11, 67)])
def test_cumulative_pp_obeys_extra_window_and_maximum(turn: int, expected: int) -> None:
    assert cumulative_pp_for_turn(turn) == expected


def test_existing_eighth_turn_benchmark_is_unchanged() -> None:
    assert cumulative_pp_for_turn(DEADLINE_TURN) == DEADLINE_CUM_PP == 38


@pytest.mark.parametrize('turn', [0, -1])
def test_nonpositive_deadline_rejected(turn: int) -> None:
    with pytest.raises(ValueError, match='1以上'):
        cumulative_pp_for_turn(turn)
