"""Isolated combat timings/memory and independent engine answer checks."""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from itertools import permutations
from pathlib import Path
from time import perf_counter

from .battle import Battle, Json, replay
from .battle_combat import analyze

CATALOG = Path(__file__).parent / 'data' / 'combat_benchmark_cases.json'


def save_result(path: Path, value: Json) -> None:
    # AI_NOTE: 子プロセスを記録中に止めても、親が半分だけのJSONを読まないよう完成後に置き換える。
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)


def peak_memory() -> tuple[int, str]:
    # AI_NOTE: Python割当だけでなく、OSが記録する子プロセス全体の常駐メモリ最大値を読む。
    if sys.platform == 'win32':
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ('peak', 'working', 'paged_peak', 'paged',
                                                   'nonpaged_peak', 'nonpaged', 'pagefile', 'pagefile_peak')]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(counters.peak), 'Windows PeakWorkingSetSize'
    import resource
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(peak if sys.platform == 'darwin' else peak*1024), 'getrusage ru_maxrss'


def make_battle(case: Json) -> Battle:
    # AI_NOTE: フォロワー数値と攻撃権を固定した、能力のない入力を公開エンジンで構築する。
    players = []
    for side, zone in enumerate(('own', 'enemy')):
        board = []
        for i, raw in enumerate(case[zone]):
            values = {'attack': raw[0], 'health': raw[1]} if isinstance(raw, list) else raw
            board.append({**values, 'card_id': 'body', 'id': f'{side}-{i}'})
        players.append({'board': board, 'turn': case.get('turn', 7), 'health': case.get('face', 20),
                        'max_health': max(20, case.get('face', 20)), 'ep': case.get('ep', 2),
                        'sep': case.get('sep', 2), 'evolved_this_turn': case.get('used', False)})
    owner = case.get('owner', 0)
    if owner:
        players.reverse()
    return Battle({'players': players, 'active_player': owner},
                  {'body': {'kind': 'follower', 'name': '検証体', 'cost': 1, 'attack': 1, 'health': 1}})


def outcome(battle: Battle) -> Json:
    # AI_NOTE: エンジンの実状態から、宣言した終了盤面の比較軸だけを取得する。
    owner = battle.state['active_player']
    own, enemy = (battle.state['players'][i] for i in (owner, 1-owner))
    return {'own_board': own['board'], 'enemy_board': enemy['board'], 'enemy_health': enemy['health'],
            'ep': own['ep'], 'sep': own['sep'], 'win': battle.state['winner'] == owner}


def signature(value: Json) -> str:
    # AI_NOTE: 同じ勝利は一件とし、非勝利は個体IDや左右位置に依存せず比較する。
    if value['win']:
        return 'WIN'
    boards = [sorted([b[k] for k in ('attack', 'health', 'max_health', 'evolved')] for b in value[zone])
              for zone in ('own_board', 'enemy_board')]
    return json.dumps([*boards, value['enemy_health'], value['ep'], value['sep']], separators=(',', ':'))


def no_worse(a: Json, b: Json) -> bool:
    # AI_NOTE: 候補生成側の比較関数を呼ばず、個体の全対応付けから独立に下位互換を判定する。
    if a['win'] or b['win']:
        return bool(a['win'])
    if a['enemy_health'] > b['enemy_health'] or a['ep'] < b['ep'] or a['sep'] < b['sep']:
        return False
    for larger, smaller in ((a['own_board'], b['own_board']), (b['enemy_board'], a['enemy_board'])):
        if not any(all(x['evolved'] == y['evolved'] and all(x[k] >= y[k] for k in
                   ('attack', 'health', 'max_health')) for x, y in zip(arrangement, smaller))
                   for arrangement in permutations(larger, len(smaller))):
            return False
    return True


def oracle(battle: Battle, mode: str) -> Json:
    # AI_NOTE: 小盤面で合法な全操作列をエンジンに実行させる。候補生成の状態遷移・枝刈りは共有しない。
    allowed = {'attack'} | ({'evolve'} if mode != 'attack' else set()) | ({'super_evolve'} if mode == 'super' else set())
    states: dict[str, Json] = {}
    pending = [battle]
    sequences = 0
    while pending:
        current = pending.pop()
        value = outcome(current)
        states[signature(value)] = value
        sequences += 1
        for action in current.legal_actions():
            if action['type'] in allowed:
                child = Battle(current.state, current.cards, record=False)
                child.step(action)
                pending.append(child)
    expected = [key for key, b in states.items() if not any(key != other and no_worse(a, b)
                                                        for other, a in states.items())]
    return {'status': 'PASS', 'expected': sorted(expected), 'sequences': sequences, 'endpoints': len(states)}


def measure(case: Json, strategy: str, max_states: int, checkpoint: Path | None = None) -> Json:
    # AI_NOTE: メモリ・時間を解析直後に確定し、再生検査のコストは測定値へ含めない。
    battle = make_battle(case)
    original = battle.export()
    before, method = peak_memory()
    started = perf_counter()
    result = analyze(battle, case['mode'], max_states=max_states, strategy=strategy)
    elapsed = (perf_counter()-started)*1000
    peak, _ = peak_memory()
    metrics = {'elapsed_ms': elapsed, 'peak_rss_bytes': peak, 'baseline_peak_rss_bytes': before,
               'memory_method': method, 'complete': result['complete'], 'stats': result['stats'],
               'candidate_count': len(result['candidates'])}
    if checkpoint is not None:
        save_result(checkpoint, {**metrics, 'status': 'RUNNING', 'phase': 'replay_check'})
    errors = []
    candidates = result['candidates']
    signatures = [signature(candidate) for candidate in candidates]
    checked_indices = list(range(len(candidates))) if case['oracle'] or len(candidates) <= 32 else [
        i*(len(candidates)-1)//31 for i in range(32)]
    for index in checked_indices:
        candidate = candidates[index]
        try:
            actual = replay({**result['record'], 'actions': candidate['actions'], 'frames': []})
        except (ValueError, TypeError, KeyError, IndexError) as error:
            errors.append(f'candidate {index}: illegal replay: {error}')
            continue
        state = outcome(actual)
        if any(state[k] != candidate[k] for k in ('enemy_health', 'ep', 'sep', 'win')):
            errors.append(f'candidate {index}: replay mismatch')
        for zone in ('own_board', 'enemy_board'):
            fields = ('id', 'attack', 'health', 'max_health', 'evolved')
            if [[b[k] for k in fields] for b in state[zone]] != [[b[k] for k in fields] for b in candidate[zone]]:
                errors.append(f'candidate {index}: {zone} mismatch')
    shapes = {json.dumps(sorted([[b['attack'], b['health']] for b in c['own_board']]))
              for c in result['candidates'] if not c['enemy_board']}
    for required in case.get('required_clear_survivors', []):
        if json.dumps(sorted(required)) not in shapes:
            errors.append(f'missing required survivors: {required}')
    if battle.export() != original:
        errors.append('input mutated')
    return {**metrics, 'status': 'PASS' if not errors else 'FAIL', 'phase': 'finished', 'signatures': sorted(set(signatures)),
            'replay_checked': len(checked_indices), 'replay_indices': checked_indices,
            'replay_coverage': 'all' if len(checked_indices) == len(candidates) else 'sample', 'errors': errors}


def isolated(job: Json, timeout: float) -> Json:
    # AI_NOTE: 各試行を新しい子プロセスに隔離。タイムアウト時はその子のツリーだけを終了し結果を残す。
    with tempfile.TemporaryDirectory(prefix='combat-benchmark-') as folder:
        request, response = Path(folder)/'request.json', Path(folder)/'response.json'
        request.write_text(json.dumps(job), encoding='utf-8')
        command = [sys.executable, '-X', 'utf8', '-m', 'svdeck.combat_benchmark', '--worker', str(request), str(response)]
        environment = {**os.environ, 'PYTHONPATH': os.pathsep.join(sys.path)}
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   encoding='utf-8', env=environment,
                                   creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        try:
            _, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if sys.platform == 'win32':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, check=False)
            else:
                process.kill()
            process.communicate()
            partial = json.loads(response.read_text(encoding='utf-8')) if response.exists() else {'phase': job['kind']}
            return {**partial, 'status': 'TIMEOUT', 'timeout_seconds': timeout}
        if process.returncode != 0 or not response.exists():
            partial = json.loads(response.read_text(encoding='utf-8')) if response.exists() else {}
            return {**partial, 'status': 'ERROR', 'returncode': process.returncode, 'error': stderr[-4000:]}
        return dict(json.loads(response.read_text(encoding='utf-8')))


def markdown(report: Json) -> str:
    # AI_NOTE: 正解未検証・打切りをPASSと混ぜず、繰り返しの中央値と最大メモリを読める形で残す。
    lines = ['# 盤面アルゴリズム検証', '', f"実行日時: {report['created_at']}",
             f"総合判定: {report['status']}", '',
             '各測定は新しい子プロセス。時間は解析のみ。メモリは解析終了までのプロセス全体の最大常駐量（Python本体・入力・キャッシュ込み）。',
             '正解作成・再生確認は測定外。UNVERIFIEDは正解集合との一致を未確認。', '',
             '| ケース | 方式 | 実行 | 正解判定 | 時間中央値 ms | 最大メモリ MiB | 完了回数 |',
             '|---|---|---|---|---:|---:|---:|']
    for case in report['cases']:
        for strategy in case['strategies']:
            rows = [r for r in case['runs'] if r['strategy'] == strategy]
            timed = [r['elapsed_ms'] for r in rows if 'elapsed_ms' in r]
            memory = [r['peak_rss_bytes'] for r in rows if 'peak_rss_bytes' in r]
            timing = f'{statistics.median(timed):.3f}' if timed else '—'
            peak = f'{max(memory)/1048576:.2f}' if memory else '—'
            verdict = '/'.join(sorted({r['correctness'] for r in rows}))
            execution = '/'.join(sorted({r['status'] for r in rows}))
            lines.append(f"| {case['id']} | {strategy} | {execution} | {verdict} | {timing} | {peak} | "
                         f"{sum(bool(r.get('complete')) for r in rows)}/{len(rows)} |")
    return '\n'.join(lines)+'\n'


def run(cases: list[Json], output: Path, repeat: int, strategies: list[str], timeout: float, max_states: int) -> Json:
    # AI_NOTE: 途中結果をケースごとに保存し、不正解やタイムアウトがあっても後続ケースの測定を続ける。
    output.mkdir(parents=True, exist_ok=False)
    report: Json = {'schema_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
                    'environment': {'python': sys.version, 'platform': platform.platform(), 'machine': platform.machine(),
                                    'processor': platform.processor(), 'cpu_count': os.cpu_count()},
                    'repeat': repeat, 'timeout_seconds': timeout, 'max_states': max_states, 'cases': [], 'status': 'RUNNING',
                    'measurement': {'isolation': 'new child process for each run', 'time': 'analyze only; milliseconds',
                                    'memory': 'process peak resident bytes captured before replay verification',
                                    'reference': 'independent Battle legal-action enumeration in separate process',
                                    'timeout': 'whole child including startup and replay; phase identifies interrupted work'},
                    'source_sha256': hashlib.sha256(Path(__file__).with_name('battle_combat.py').read_bytes()).hexdigest(),
                    'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                    'cases_sha256': hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest()}
    (output/'cases.json').write_text(json.dumps(cases, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    for case in cases:
        reference = isolated({'kind': 'oracle', 'case': case}, timeout) if case['oracle'] else {'status': 'NOT_REQUESTED'}
        rows = []
        for strategy in strategies:
            for iteration in range(repeat):
                result = isolated({'kind': 'measure', 'case': case, 'strategy': strategy, 'max_states': max_states}, timeout)
                correct = 'UNKNOWN'
                if result['status'] == 'FAIL':
                    correct = 'FAIL'
                elif result['status'] == 'PASS':
                    if reference['status'] == 'PASS':
                        expected, actual = set(reference['expected']), set(result['signatures'])
                        missing, extra = sorted(expected-actual), sorted(actual-expected)
                        result['answer_diff'] = {'missing_count': len(missing), 'extra_count': len(extra),
                                                'missing_samples': missing[:10], 'extra_samples': extra[:10]}
                        correct = 'PASS' if not missing and not extra and result['complete'] else 'FAIL' if result['complete'] else 'INCOMPLETE'
                    else:
                        correct = 'UNVERIFIED' if not case['oracle'] else 'UNKNOWN'
                if 'signatures' in result:
                    answers = result.pop('signatures')
                    result['answers_sha256'] = hashlib.sha256(json.dumps(answers).encode()).hexdigest()
                    result['answer_samples'] = answers[:10]
                rows.append({**result, 'strategy': strategy, 'iteration': iteration+1, 'correctness': correct})
        report['cases'].append({'id': case['id'], 'description': case['description'], 'reference': reference,
                                'strategies': strategies, 'runs': rows})
        print(f"{case['id']}: {', '.join(r['correctness'] for r in rows)}", flush=True)
        (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    verdicts = [r['correctness'] for c in report['cases'] for r in c['runs']]
    report['status'] = 'FAIL' if any(v in ('FAIL', 'UNKNOWN') for v in verdicts) else (
        'PASS' if all(v == 'PASS' for v in verdicts) else 'PARTIAL')
    (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    (output/'report.md').write_text(markdown(report), encoding='utf-8')
    return report


def main() -> None:
    # AI_NOTE: 既存の測定記録を上書きせず、入力ミスは実行前に拒否する。
    parser = argparse.ArgumentParser(description='盤面候補の正解・時間・最大常駐メモリを記録')
    parser.add_argument('--worker', nargs=2, help=argparse.SUPPRESS)
    parser.add_argument('--cases', type=Path, default=CATALOG)
    parser.add_argument('--list-cases', action='store_true')
    parser.add_argument('--case', action='append', default=[])
    parser.add_argument('--output', type=Path, help='新しい保存先。report.json / report.md / cases.json を作成')
    parser.add_argument('--repeat', type=int, default=3)
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--max-states', type=int, default=50000)
    parser.add_argument('--strategy', action='append', choices=['grouped', 'exhaustive'])
    args = parser.parse_args()
    if args.worker:
        request, response = map(Path, args.worker)
        job = json.loads(request.read_text(encoding='utf-8'))
        result = oracle(make_battle(job['case']), job['case']['mode']) if job['kind'] == 'oracle' else measure(
            job['case'], job['strategy'], job['max_states'], response)
        save_result(response, result)
        return
    try:
        cases = json.loads(args.cases.read_text(encoding='utf-8'))
        if not isinstance(cases, list) or not cases:
            raise ValueError('ケース一覧は空でない配列にしてください')
        ids = [c['id'] for c in cases]
        if len(ids) != len(set(ids)) or any(not isinstance(i, str) or not i for i in ids):
            raise ValueError('ケースIDは重複しない文字列にしてください')
        for case in cases:
            if case['mode'] not in ('attack', 'evolve', 'super') or not isinstance(case['oracle'], bool):
                raise ValueError('mode / oracle が不正です')
            if not isinstance(case['description'], str):
                raise ValueError('description は文字列にしてください')
            make_battle(case)
        if set(args.case)-set(ids):
            raise ValueError(f'存在しないケース: {sorted(set(args.case)-set(ids))}')
        if args.repeat < 1 or not 0 < args.timeout < float('inf') or not 1 <= args.max_states <= 200000:
            raise ValueError('repeat・timeoutは正数、max-statesは1〜200000にしてください')
        if args.list_cases:
            print('\n'.join(f"{c['id']}: {c['description']}" for c in cases))
            return
        if args.output is None or args.output.exists():
            raise ValueError('--output に新しい保存先ディレクトリを指定してください')
        selected = [c for c in cases if not args.case or c['id'] in args.case]
        report = run(selected, args.output, args.repeat, list(dict.fromkeys(args.strategy or ['grouped'])), args.timeout, args.max_states)
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        parser.error(str(error))
    print(f"JSON: {(args.output/'report.json').resolve()}\nMarkdown: {(args.output/'report.md').resolve()}")
    raise SystemExit(1 if report['status'] == 'FAIL' else 0)


if __name__ == '__main__':
    main()
