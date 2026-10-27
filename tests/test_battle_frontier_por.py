"""Exact reachability and conservative deterministic commutation tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from svdeck.battle_env.battle import Battle, Json
from svdeck.battle_env.battle_frontier_fast import Kernel, eligible
from svdeck.battle_env.battle_frontier_por import Independence, enumerate_states
from test_battle_frontier_fast import scenario

CASES = json.loads((Path(__file__).parent/'fixtures/turn_frontier_cases.json').read_text(encoding='utf-8'))


def compare(battle: Battle) -> None:
    # AI_NOTE: 全状態・全確率分岐を枝刈りなしと照合し、代表経路を根から再生する。
    kernel = Kernel(battle)
    expected = enumerate_states(kernel, por=False)
    actual = enumerate_states(kernel, por=True)
    assert expected.complete and actual.complete
    assert actual.states == expected.states
    assert actual.chance == expected.chance
    for final in actual.states:
        state = final
        path = []
        while state != kernel.initial:
            parent, action, tape = actual.witnesses[state]
            path.append((action, tape))
            state = parent
        for action, tape in reversed(path):
            state = next(child for child, _, draws in kernel.outcomes(state, dict(action)) if draws == tape)
        assert state == final


@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_fixed_cases(case: Json) -> None:
    # AI_NOTE: 固定8例のうち閉じたkernel対象外は明示し、汎用エンジンへ無断で近似しない。
    battle = Battle(case['state'], case['cards'])
    if not eligible(battle):
        pytest.skip('This POR prototype only supports fixed-slot kernel cases')
    compare(battle)


@pytest.mark.parametrize('seed', range(48))
def test_generated_cases(seed: int) -> None:
    # AI_NOTE: バリア・必殺・守護・進化・生成・ランダムを含む全prefixを48入力で照合する。
    compare(scenario(seed))


@pytest.mark.parametrize('seed', range(16))
def test_claimed_independence_is_diamond(seed: int) -> None:
    # AI_NOTE: 可換と判定した操作は両順で合法かつ同一結果になることを全到達点で確認する。
    kernel = Kernel(scenario(seed))
    graph = enumerate_states(kernel, por=False)
    checker = Independence(kernel)
    for state in graph.states:
        actions = kernel.actions(state)
        keys = [checker.register(state, action) for action in actions]
        for index, left in enumerate(actions):
            for j in range(index):
                if not checker.commutes(state, keys[index], keys[j]):
                    continue
                right = actions[j]
                first = kernel.outcomes(state, left)
                other = kernel.outcomes(state, right)
                assert len(first) == len(other) == 1
                assert right in kernel.actions(first[0][0])
                assert left in kernel.actions(other[0][0])
                assert kernel.outcomes(first[0][0], right) == kernel.outcomes(other[0][0], left)


def test_interrupted_result_is_not_complete() -> None:
    # AI_NOTE: 時間制限で停止したprefixを完全列挙と誤表示しない。
    kernel = Kernel(scenario(0))
    result = enumerate_states(kernel, por=True, seconds=0)
    assert not result.complete
    assert result.states == {kernel.initial}
    assert result.transitions == 0
