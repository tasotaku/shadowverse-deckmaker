"""Public candidate artifacts and conditional follow-up semantics."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from svdeck.battle_env.battle import Battle
from svdeck.battle_env.battle_practical import replay_branch
from svdeck.battle_env.battle_frontier_compare import digest, expand_state, kernel_key, run_worker, semantic_key, summarize
from svdeck.battle_env.battle_frontier_fast import Kernel
from svdeck.battle_env.battle_frontier import freeze
from test_battle_frontier import action_signature, enumerate_turn, signature  # type: ignore[attr-defined]
from test_battle_frontier_fast import scenario

CASES = json.loads((Path(__file__).resolve().parents[1]/'docs/evidence/turn-search-compare/independent-small-cases.v1.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('seed', range(16))
def test_kernel_candidate_key_matches_public_state(seed: int) -> None:
    # AI_NOTE: 小さい内部番号を意味hashへ戻す処理を、完全stateの公開比較と独立に照合する。
    kernel = Kernel(scenario(seed))
    state = kernel.initial
    hands = [digest(freeze(dict(entity, keywords=sorted(entity['keywords'])))) for entity in kernel.hand]
    for _ in range(6):
        key = kernel_key(kernel, state, {}, hands)
        assert digest(key) == digest(semantic_key(Battle(kernel.state(state), kernel.battle.cards)))
        actions = kernel.actions(state)
        if not actions:
            break
        state = kernel.outcomes(state, actions[-1])[0][0]


@pytest.mark.parametrize('algorithm', ['baseline', 'cache', 'native'])
@pytest.mark.parametrize('case', CASES, ids=lambda case: case['id'])
def test_saved_debug_states_and_chance_match_oracle(tmp_path: Path, algorithm: str, case: dict[str, object]) -> None:
    # AI_NOTE: workerの標準JSONを読み直し、独立oracleの全状態・全操作・確率tapeへ照合する。
    source = tmp_path/'cases.json'
    source.write_text(json.dumps([case]), encoding='utf-8')
    run_worker(argparse.Namespace(cases=source, case=case['id'], output=tmp_path, algorithm=algorithm,
                                 max_states=10000, seconds=30, debug_threshold=1000, witness_samples=100))
    result = json.loads((tmp_path/'result.json').read_text(encoding='utf-8'))
    reference = enumerate_turn(case['state'], case['cards'])
    expected = {key: signature(state) for key, state in reference.states.items()}
    assert result['complete']
    assert {signature(node['state']) for node in result['debug_nodes']} == set(expected.values())
    actual = set()
    for node in result['debug_nodes']:
        assert signature(replay_branch(result['record'], node['witness'])['state']) == signature(node['state'])
        for choice in node['conditional']:
            assert sum(Fraction(branch['probability']) for branch in choice['outcomes']) == 1
            for branch in choice['outcomes']:
                actual.add((signature(node['state']), action_signature(choice['action']), signature(branch['state']),
                            tuple(branch['draws']), Fraction(branch['probability'])))
    assert actual == {(expected[edge.source], edge.action, expected[edge.target], edge.choices, edge.probability)
                      for edge in reference.edges}


def test_tiny_budget_is_not_ranked_complete(tmp_path: Path) -> None:
    # AI_NOTE: 途中停止の候補hashがあっても完走方式として選出しない。
    source = tmp_path/'cases.json'
    source.write_text(json.dumps(CASES[:1]), encoding='utf-8')
    run_worker(argparse.Namespace(cases=source, case=CASES[0]['id'], output=tmp_path, algorithm='baseline',
                                 max_states=1, seconds=30, debug_threshold=1000, witness_samples=100))
    report = json.loads((tmp_path/'report.json').read_text(encoding='utf-8'))
    assert not report['complete'] and report['cutoffs']
    summary = summarize([report], ['baseline'], [CASES[0]['id']])
    assert summary['selection']['algorithm'] is None
    assert summary['selection']['status'] == 'incomplete'


def test_public_cli_and_lazy_continuation(tmp_path: Path) -> None:
    # AI_NOTE: 内部importを不要にする公開CLIを実行し、保存結果から合法な条件付き分岐を得る。
    source = tmp_path/'cases.json'
    source.write_text(json.dumps(CASES[:1]), encoding='utf-8')
    output = tmp_path/'comparison'
    subprocess.run([sys.executable, '-X', 'utf8', '-m', 'svdeck.battle_env.battle_frontier_compare', '--cases', str(source),
                    '--output', str(output), '--algorithms', 'baseline', '--trials', '1'], check=True, capture_output=True)
    summary = json.loads((output/'summary.json').read_text(encoding='utf-8'))
    row = summary['groups'][0]['trials'][0]
    assert row['complete'] and row['process_wall_seconds'] >= row['timings']['compute_seconds']
    expanded = tmp_path/'expanded.json'
    subprocess.run([sys.executable, '-X', 'utf8', '-m', 'svdeck.battle_env.battle_frontier_compare', '--expand',
                    str(output/row['result_path']), '--output', str(expanded)], check=True, capture_output=True)
    result = json.loads(expanded.read_text(encoding='utf-8'))
    assert result['conditional'] and result['stop']
    assert result['choices']
    assert all(choice['action']['type'] != 'end_turn' for choice in result['choices'])


def test_conditional_followup_changes_after_random_observation() -> None:
    # AI_NOTE: 抽選結果ごとに別の残存対象を選べることを、全結果を条件付きに分けて確認する。
    battle = Battle({'players': [{'turn': 3, 'ep': 0, 'sep': 0, 'pp': 2, 'max_pp': 2,
                                'hand': [{'id': 'random', 'card_id': 'random'}, {'id': 'kill', 'card_id': 'kill'}]},
                               {'board': [{'id': 'a', 'card_id': 'body'}, {'id': 'b', 'card_id': 'body'}]}]},
                    {'body': {'name': 'Body', 'kind': 'follower', 'cost': 1, 'attack': 1, 'health': 1},
                     'random': {'name': 'Random', 'kind': 'spell', 'cost': 1,
                                'effects': [{'op': 'damage', 'target': 'random_enemy', 'amount': 1}]},
                     'kill': {'name': 'Kill', 'kind': 'spell', 'cost': 1,
                              'effects': [{'op': 'destroy', 'target': 'chosen_enemy'}]}})
    record = battle.export()
    initial = expand_state(record, battle.state)
    choice = next(item for item in initial['choices'] if item['action'].get('card') == 'random')
    assert [branch['probability'] for branch in choice['outcomes']] == ['1/2', '1/2']
    targets = set()
    for branch in choice['outcomes']:
        followup = expand_state(record, branch['state'])
        actions = [item['action'] for item in followup['choices'] if item['action'].get('card') == 'kill']
        assert len(actions) == 1
        targets.add(actions[0]['target'])
    assert targets == {'a', 'b'}


def test_mismatched_candidate_sets_never_become_timing_tie() -> None:
    # AI_NOTE: 時間範囲が重なっても意味不一致の不合格を速度の引分けで上書きしない。
    rows = [{'case_id': 'case', 'algorithm': algorithm, 'complete': True, 'candidate_semantic_sha256': algorithm,
             'peak_rss_bytes': 1, 'timings': {'compute_seconds': 1, 'serialization_seconds': 0}}
            for algorithm in ('baseline', 'cache')]
    result = summarize(rows, ['baseline', 'cache'], ['case'])
    assert result['selection']['status'] == 'candidate_mismatch'
    assert result['selection']['algorithm'] is None
