"""Correctness and failure accounting of the public benchmark runner."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from svdeck.battle import combat_benchmark as bench
from svdeck.battle.battle import Json
from svdeck.battle.battle_combat import analyze


def test_real_memory_and_independent_answer() -> None:
    # AI_NOTE: OSメモリ値を実測し、単純な盤面の独立正解と再生確認を照合する。
    case = json.loads(bench.CATALOG.read_text(encoding='utf-8'))[0]
    reference = bench.oracle(bench.make_battle(case), case['mode'])
    actual = bench.measure(case, 'grouped', 50000)
    assert set(reference['expected']) == set(actual['signatures'])
    assert actual['status'] == 'PASS'
    assert actual['peak_rss_bytes'] >= actual['baseline_peak_rss_bytes'] > 0
    assert actual['elapsed_ms'] > 0 and actual['replay_checked'] > 0


def test_record_missing_answer_timeout_and_unverified(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AI_NOTE: 正解欠落・タイムアウト・正解未検証を意図的に作り、成功扱いしないことを検査する。
    cases = [{'id': 'wrong', 'description': 'wrong', 'oracle': True},
             {'id': 'timeout', 'description': 'timeout', 'oracle': True},
             {'id': 'large', 'description': 'large', 'oracle': False}]
    def fake(job: Json, timeout: float) -> Json:
        if job['kind'] == 'oracle':
            return {'status': 'PASS', 'expected': ['expected']}
        if job['case']['id'] == 'timeout':
            return {'status': 'TIMEOUT'}
        return {'status': 'PASS', 'signatures': ['wrong'], 'complete': True,
                'elapsed_ms': 2.0, 'peak_rss_bytes': 1024}
    monkeypatch.setattr(bench, 'isolated', fake)
    target = tmp_path/'results'
    report = bench.run(cases, target, 2, ['grouped'], 1.0, 50000)
    assert report['status'] == 'FAIL'
    assert [c['runs'][0]['correctness'] for c in report['cases']] == ['FAIL', 'UNKNOWN', 'UNVERIFIED']
    assert report['cases'][0]['runs'][0]['answer_diff']['missing_count'] == 1
    assert 'peak_rss_bytes' not in report['cases'][1]['runs'][0]
    assert json.loads((target/'report.json').read_text(encoding='utf-8')) == report
    assert 'UNVERIFIED' in (target/'report.md').read_text(encoding='utf-8')
    with pytest.raises(FileExistsError):
        bench.run(cases, target, 1, ['grouped'], 1.0, 50000)


def test_real_worker_timeout() -> None:
    # AI_NOTE: 実際の子プロセスを短い制限で終了し、時間切れを値ゼロの成功に変換しない。
    case = json.loads(bench.CATALOG.read_text(encoding='utf-8'))[0]
    result = bench.isolated({'kind': 'measure', 'case': case, 'strategy': 'grouped', 'max_states': 50000}, 0.000001)
    assert result['status'] == 'TIMEOUT'
    assert 'elapsed_ms' not in result and 'peak_rss_bytes' not in result


def test_illegal_answer_keeps_measurements(monkeypatch: pytest.MonkeyPatch) -> None:
    # AI_NOTE: 存在しない個体を攻撃させる誤回答を与え、再生の不正をFAILとして数値と一緒に保存する。
    case = json.loads(bench.CATALOG.read_text(encoding='utf-8'))[0]
    result = analyze(bench.make_battle(case), case['mode'])
    result['candidates'][0]['actions'] = [{'type': 'attack', 'source': 'missing', 'target': 'leader:1'}]
    monkeypatch.setattr(bench, 'analyze', lambda *args, **kwargs: result)
    measured = bench.measure(case, 'grouped', 50000)
    assert measured['status'] == 'FAIL'
    assert any('illegal replay' in error for error in measured['errors'])
    assert measured['peak_rss_bytes'] > 0 and measured['elapsed_ms'] >= 0


def test_interrupted_record_preserves_last_complete_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AI_NOTE: 置換前の書き込みが失敗しても、直前の完全な計測記録を失わない。
    destination = tmp_path/'result.json'
    bench.save_result(destination, {'status': 'RUNNING', 'peak_rss_bytes': 123})
    def fail_replace(self: Path, target: Path) -> Path:
        raise OSError('simulated interruption before atomic replace')
    monkeypatch.setattr(Path, 'replace', fail_replace)
    with pytest.raises(OSError):
        bench.save_result(destination, {'status': 'PASS'})
    assert json.loads(destination.read_text(encoding='utf-8')) == {'status': 'RUNNING', 'peak_rss_bytes': 123}


def test_certificate_rejects_stale_inputs_and_incomplete_reference(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # AI_NOTE: 名前が同じでも入力変更・未完了・正解差替えがあれば、独立正解の認証を通さない。
    case = json.loads(bench.CATALOG.read_text(encoding='utf-8'))[0]
    expected = bench.oracle(bench.make_battle(case), case['mode'])['expected']
    entry = {'id': case['id'], 'status': 'PASS', 'complete': True, 'expected': expected,
             'case_sha256': hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest(),
             'expected_sha256': hashlib.sha256(json.dumps(expected).encode()).hexdigest()}
    data = {'status': 'PASS', 'complete': True, 'cases': [entry],
            'engine_sha256': hashlib.sha256(Path(bench.__file__).with_name('battle.py').read_bytes()).hexdigest()}
    path = tmp_path/'reference.json'
    bench.save_result(path, data)
    assert bench.certified_references(path, [case])[case['id']]['expected'] == expected
    monkeypatch.setattr(bench, 'isolated', lambda *_: {'status': 'PASS', 'complete': True, 'signatures': expected})
    recorded = bench.run([case], tmp_path/'run', 1, ['grouped'], 60, 50000, path)
    assert recorded['measurement']['reference'] == 'independent precomputed certificate supplied with --reference-file'
    with pytest.raises(ValueError, match='ケース入力'):
        bench.certified_references(path, [{**case, 'face': 1}])
    entry['complete'] = False
    bench.save_result(path, data)
    with pytest.raises(ValueError, match='未完了'):
        bench.certified_references(path, [case])
    entry['complete'] = True
    entry['expected'] = ['forged']
    bench.save_result(path, data)
    with pytest.raises(ValueError, match='ハッシュ'):
        bench.certified_references(path, [case])


@pytest.mark.parametrize('case_id', ['varied-5v5', 'allocation-5v5', 'timing-finisher-5v5'])
def test_hard_frontiers_match_independently_certified_answers(case_id: str) -> None:
    # AI_NOTE: 生産実装を使わず作成した固定全解と、標準予算での結果を双方向に照合する。
    fixtures = Path(__file__).parent/'fixtures'
    cases = json.loads((fixtures/'combat_hard_cases.json').read_text(encoding='utf-8'))
    case = next(value for value in cases if value['id'] == case_id)
    reference = bench.certified_references(fixtures/'combat_hard_answers.json', [case])[case_id]
    result = analyze(bench.make_battle(case), case['mode'])
    assert result['complete'] is True
    actual = {bench.signature(candidate) for candidate in result['candidates']}
    assert actual == set(reference['expected'])
