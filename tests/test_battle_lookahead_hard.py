"""Frozen independent mixed-ability oracles and the comparison failure paths."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from scripts.lookahead_generated_cases import generate_cases
from scripts.lookahead_stress import compare
from svdeck.battle import Battle, Json
from svdeck.battle_lookahead import analyze, verify_policy

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT/'tests/fixtures'
GENERATED: list[Json] = json.loads((FIXTURES/'battle_lookahead_generated.json').read_text(encoding='utf-8'))
EXPECTED: dict[str, Json] = json.loads((FIXTURES/'battle_lookahead_generated_expected.json').read_text(encoding='utf-8'))


def test_generated_population_is_frozen_and_reproducible() -> None:
    # AI_NOTE: 成功したseedだけ残す選別を防ぎ、同じ128入力を将来も再生する。
    assert GENERATED == generate_cases()
    assert [case['seed'] for case in GENERATED] == list(range(128))
    assert set(EXPECTED) == {case['id'] for case in GENERATED}
    assert sum(case['n_turns'] == 3 for case in GENERATED) == 80


@pytest.mark.parametrize('case', GENERATED, ids=[case['id'] for case in GENERATED])
def test_generated_all_initial_actions_match_independent_oracle(case: Json) -> None:
    # AI_NOTE: 正解は別プロセスの公開Battle総当たりで保存済み。製品の推奨だけでなく全初手を検査する。
    battle = Battle(case['state'], case['cards'])
    before = battle.export()
    result = analyze(battle, turns=case['n_turns'])
    result['verification'] = verify_policy(result)
    checked = compare(result, EXPECTED[case['id']])
    assert checked['status'] == 'PASS', checked
    assert battle.export() == before


def test_comparison_detects_wrong_values_missing_actions_and_incomplete_results() -> None:
    # AI_NOTE: 壊れた出力を正解と扱わないことを、独立正解のある実局面の出力から故障を注入して確認する。
    case = GENERATED[1]
    original = analyze(Battle(case['state'], case['cards']), turns=case['n_turns'])
    original['verification'] = verify_policy(original)
    reference = EXPECTED[case['id']]
    assert compare(original, reference)['status'] == 'PASS'
    wrong = copy.deepcopy(original)
    wrong['candidates'][0]['win_probability_exact'] = '123/7'
    assert compare(wrong, reference)['status'] == 'FAIL'
    missing = copy.deepcopy(original)
    missing['candidates'].pop()
    assert compare(missing, reference)['status'] == 'FAIL'
    partial = original | {'complete': False, 'cutoffs': ['states']}
    assert compare(partial, reference)['status'] == 'INCOMPLETE'
