"""Finite roles budgets, exact seat selection, and reproducible evaluation output."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from svdeck.battle import battle_training as training
from svdeck.battle.battle import Battle, replay

Json = dict[str, Any]


def test_jobs_keep_legacy_grid_and_allow_exact_pair() -> None:
    # AI_NOTE: 新しい組合せ選択は、指定しなかった既存評価の6試合を減らさない。
    assert len(training.jobs([1], 'search', 'greedy')) == 6
    tasks = training.jobs([93001], 'roles', 'search', decks=training.DECKS, seats=(1,), options={'role_k': 3})
    assert len(tasks) == 1
    assert tasks[0]['decks'] == list(training.DECKS)
    assert tasks[0]['seat'] == 1 and tasks[0]['options'] == {'role_k': 3}


def test_game_forwards_only_relevant_budgets_and_records_measurements(monkeypatch: pytest.MonkeyPatch) -> None:
    # AI_NOTE: 入力配線は小さな合法対戦で検査し、役割探索の戦術精度とは切り分ける。
    calls: list[Json] = []

    class Player:
        def __init__(self, cards: Json, policy: str, weights: Json | None = None, **options: Any) -> None:
            # AI_NOTE: 選手境界で受け取った予算を記録して、既存方式への意図しない変更を検出する。
            self.policy = policy
            self.weights: Json = {}
            calls.append({'policy': policy, **options})

        def choose(self, observation: Json) -> Json:
            # AI_NOTE: 通常エンジンの合法手を使い、判断とリプレイの保存を最小ケースで検査する。
            return {'action': {'type': 'end_turn'}, 'policy': self.policy, 'nodes': 7, 'depth': 1,
                    'depth_unit': 'turns', 'elapsed_ms': 0, 'limited': True, 'cutoffs': {'nodes': 1},
                    'role_search': {'available': True, 'role_k': 3, 'coverage_exact': '2/3',
                                    'goals': ['defense'], 'candidates': [{'roles': ['defense']}]}}

    monkeypatch.setattr(training, 'Player', Player)
    monkeypatch.setattr(training, 'new_match', lambda *args, **kwargs: Battle({'players': [{'deck': ['test-body']*3}, {'deck': ['test-body']*3}]}))
    result = training.game({'seed': 1, 'decks': list(training.DECKS), 'seat': 0, 'policy': 'roles', 'opponent': 'search',
                            'max_actions': 1, 'record': True,
                            'options': {'role_k': 3, 'turns': 2, 'seconds': .1, 'max_nodes': 20}})
    assert calls == [{'policy': 'roles', 'seed': 20, 'role_k': 3, 'turns': 2, 'seconds': .1, 'max_nodes': 20},
                     {'policy': 'search', 'seed': 21}]
    assert result['result'] == 'unfinished' and not result['completed']
    assert result['stop_reason'] == 'max_actions'
    assert result['nodes'] == 7 and result['actual_depth']['turns']['max'] == 1
    assert result['cutoffs'] == {'nodes': 1}
    assert result['peak_rss_bytes'] > 0 and result['memory_scope']
    assert result['decisions'][0]['wall_ms'] >= 0
    assert result['role_coverage'][0]['coverage_exact'] == '2/3'
    assert result['record']['frames'][0]['decision'] == result['decisions'][0]['decision']
    assert replay(result['record']).state['winner'] is None


def test_cli_selects_roles_pair_and_saves_replays(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    # AI_NOTE: CLIの全組合せを実行せず、明示したデッキ・両席・予算が保存処理まで届くことを検査する。
    received: list[Json] = []

    def run(tasks: list[Json], workers: int) -> list[Json]:
        # AI_NOTE: CLI境界の出力だけを固定し、高価なAI対戦をこの配線検査から除く。
        received.extend(tasks)
        return [task | {'result': 'unfinished', 'winner': None, 'mean_decision_ms': 0, 'record': Battle({}).export()}
                for task in tasks]

    output = tmp_path/'evaluation.json'
    monkeypatch.setattr(training, 'run_jobs', run)
    monkeypatch.setattr(sys, 'argv', ['battle_training', 'evaluate', '--output', str(output), '--seeds', '1',
                                   '--seed', '93001', '--policy', 'roles', '--opponent', 'search',
                                   '--decks', *training.DECKS, '--seat', 'both', '--role-k', '3', '--turns', '2',
                                   '--seconds', '.1', '--max-nodes', '20', '--replay-dir', str(tmp_path/'replays')])
    training.main()
    assert len(received) == 2 and [row['seat'] for row in received] == [0, 1]
    assert all(row['options'] == {'role_k': 3, 'turns': 2, 'seconds': .1, 'max_nodes': 20} for row in received)
    saved = json.loads(output.read_text(encoding='utf-8'))
    assert saved['summary']['unfinished'] == 2 and saved['summary']['win'] == 0
    assert saved['command_seconds'] >= 0 and saved['command_timing_scope']
    for row in saved['games']:
        assert replay(json.loads(Path(row['replay']).read_text(encoding='utf-8'))).state['winner'] is None


@pytest.mark.parametrize('arguments', [['--role-k', '0'], ['--role-k', '21'], ['--turns', '6'],
                                    ['--max-nodes', '0'], ['--seconds', 'nan'], ['--max-actions', '0']])
def test_cli_rejects_invalid_budgets(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, arguments: list[str]) -> None:
    # AI_NOTE: 不正予算で子プロセスや対戦を開始する前にCLI境界で停止する。
    monkeypatch.setattr(sys, 'argv', ['battle_training', 'evaluate', '--output', str(tmp_path/'unused.json'), *arguments])
    with pytest.raises(SystemExit) as error:
        training.main()
    assert error.value.code == 2


def test_real_roles_game_replays_with_saved_decisions() -> None:
    # AI_NOTE: 本物の新方式を既存のゲーム関数から呼び、操作上限でも保存判断と状態を失わない。
    result = training.game({'seed': 93001, 'decks': list(training.DECKS), 'seat': 0, 'policy': 'roles',
                            'opponent': 'search', 'record': True, 'max_actions': 2,
                            'options': {'role_k': 3, 'turns': 1, 'max_nodes': 30, 'seconds': .1}})
    assert result['actions'] == 2
    assert any(row['decision']['policy'] == 'roles' for row in result['decisions'])
    restored = replay(result['record'])
    assert restored.state['winner'] == result['winner']
    assert [frame['decision'] for frame in restored.frames] == [row['decision'] for row in result['decisions']]
