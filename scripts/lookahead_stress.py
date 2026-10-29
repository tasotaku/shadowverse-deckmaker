"""Reproducible independent turn-search comparisons and per-process measurements."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from pathlib import Path
from time import perf_counter
from typing import Any

from svdeck.battle.battle import Battle, Json
from svdeck.battle.battle_ai import Player
from svdeck.battle.battle_lookahead import analyze, verify_policy
from svdeck.battle.combat_benchmark import peak_memory


def write(path: Path, data: Any) -> None:
    # AI_NOTE: 各子プロセスの測定・正解・比較を別ファイルに保存し、打切りも後から追跡できるようにする。
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def compare(result: Json, reference: Json) -> Json:
    # AI_NOTE: 推薦一手だけでなく全初手の勝敗確率を独立参照と照合し、未完了は正解扱いにしない。
    if not result['complete']:
        return {'status': 'INCOMPLETE', 'reasons': result['cutoffs']}
    errors = []
    actual_value = [result['win_probability_exact'], str(-Fraction(result['loss_probability_exact']))]
    if actual_value != reference['value']:
        errors.append('root probabilities differ')
    if result['recommended_action'] not in reference['optimal_first_actions']:
        errors.append('recommendation is not reference optimal')
    def encode(action: Json) -> str:
        # AI_NOTE: JSONのキー順だけを無視し、対象やカードが異なる初手は同一視しない。
        return json.dumps(action, sort_keys=True)
    expected = {encode(row['action']): row['value'] for row in reference['actions']}
    actual = {encode(row['action']): [row['win_probability_exact'], str(-Fraction(row['loss_probability_exact']))]
              for row in result['candidates']}
    if expected != actual:
        errors.append('initial action set or action probabilities differ')
    if result['verification']['status'] != 'PASS':
        errors.append('policy replay failed')
    return {'status': 'FAIL' if errors else 'PASS', 'errors': errors, 'initial_actions_checked': len(expected)}


def worker(args: argparse.Namespace) -> None:
    # AI_NOTE: 製品と参照を別プロセスにして、製品のメモリ値へ参照探索のメモリを混ぜない。
    case = json.loads(args.case_file.read_text(encoding='utf-8'))
    started = perf_counter()
    if args.worker == 'reference':
        from scripts.lookahead_reference import solve
        reference = solve(case)
        memory, method = peak_memory()
        reference['stats'] = {'elapsed_ms': (perf_counter()-started)*1000, 'peak_rss_bytes': memory,
                              'memory_method': method, 'memory_scope': 'reference process lifetime peak'}
        write(args.output/'reference.json', reference)
        return
    battle = Battle(case['state'], case['cards'])
    before = battle.export()
    if args.worker == 'runtime':
        decision = Player(battle.cards, policy='lookahead', turns=case['n_turns']).choose(battle.observation(battle.state['active_player']))
        assert decision['action'] in battle.legal_actions() and battle.export() == before
        memory, method = peak_memory()
        write(args.output/'runtime.json', {'decision': decision, 'legal_recommendation': True, 'input_unchanged': True,
              'peak_rss_bytes': memory, 'memory_method': method, 'memory_scope': 'runtime process lifetime peak',
              'elapsed_ms': (perf_counter()-started)*1000})
        return
    result = analyze(battle, turns=case['n_turns'], max_states=args.max_states, seconds=args.seconds)
    legal = result['recommended_action'] in battle.legal_actions()
    assert legal and before == battle.export()
    compact = {key: val for key, val in result.items() if key not in {'policy', 'record'}}
    compact['legal_recommendation'] = legal
    compact['input_unchanged'] = True
    compact['policy_nodes'] = len(result['policy'])
    compact['chance_nodes'] = sum(len(n['outcomes']) > 1 for n in result['policy'])
    compact['turns_remaining_seen'] = sorted({n['turns_remaining'] for n in result['policy']})
    compact['verification'] = {'status': 'NOT_RUN'}
    write(args.output/'production.json', compact)
    compact['verification'] = verify_policy(result) if result['complete'] else {'status': 'NOT_RUN', 'reason': 'incomplete policy'}
    compact['worker_elapsed_ms'] = (perf_counter()-started)*1000
    write(args.output/'production.json', compact)


def run_process(command: list[str], folder: Path, label: str, seconds: float) -> Json:
    # AI_NOTE: 外側の期限でも子プロセス群を確実に停止し、参照の暴走やWindowsのvenv子の残留を防ぐ。
    started = perf_counter()
    with (folder/f'{label}.stdout.txt').open('w', encoding='utf-8') as stdout, (folder/f'{label}.stderr.txt').open('w', encoding='utf-8') as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr)
        timed_out = False
        try:
            process.wait(timeout=seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, check=False)
            else:
                process.kill()
            process.wait(timeout=10)
    return {'status': 'TIMEOUT' if timed_out else 'OK' if process.returncode == 0 else 'ERROR',
            'returncode': process.returncode, 'pid': process.pid, 'elapsed_seconds': perf_counter()-started,
            'deadline_seconds': seconds, 'process_exited': process.poll() is not None}


def run_case(case: Json, args: argparse.Namespace) -> Json:
    # AI_NOTE: 予め固定した全局面を実行し、失敗局面を除外して分母を小さくしない。
    folder = args.output/case['id']
    folder.mkdir()
    write(folder/'case.json', case)
    command = [sys.executable, '-X', 'utf8', '-m', 'scripts.lookahead_stress', '--case-file', str(folder/'case.json'),
               '--output', str(folder), '--seconds', str(args.seconds), '--max-states', str(args.max_states)]
    result: Json = {'id': case['id'], 'classification': case.get('classification', 'exact'), 'turns': case['n_turns']}
    result['production_process'] = run_process(command+['--worker', 'production'], folder, 'production', args.seconds+15)
    if result['production_process']['status'] != 'OK':
        result['status'] = 'ERROR'
    else:
        production = json.loads((folder/'production.json').read_text(encoding='utf-8'))
        result['production'] = {key: production[key] for key in ('complete', 'optimal', 'cutoffs', 'stats', 'policy_nodes', 'chance_nodes', 'legal_recommendation', 'verification')}
        if result['classification'] == 'stress':
            result['status'] = 'COMPLETED_UNVERIFIED' if production['complete'] else 'INCOMPLETE'
            result['correctness'] = 'NOT_CHECKED: branching stress, no independent solution'
            result['runtime_process'] = run_process(command+['--worker', 'runtime'], folder, 'runtime', 17)
            if result['runtime_process']['status'] == 'OK':
                runtime = json.loads((folder/'runtime.json').read_text(encoding='utf-8'))
                result['runtime'] = {key: runtime[key] for key in ('legal_recommendation', 'peak_rss_bytes', 'elapsed_ms')}
                result['runtime'].update({key: runtime['decision'][key] for key in ('depth', 'turns_requested', 'limited', 'cutoffs', 'fallback', 'fallback_evaluated')})
            else:
                result['status'] = 'ERROR'
        else:
            result['reference_process'] = run_process(command+['--worker', 'reference'], folder, 'reference', args.reference_seconds)
            if result['reference_process']['status'] != 'OK':
                result['status'] = 'REFERENCE_'+result['reference_process']['status']
            else:
                reference = json.loads((folder/'reference.json').read_text(encoding='utf-8'))
                result['reference_stats'] = reference['stats'] | {'states': reference['states']}
                result.update(compare(production, reference))
    write(folder/'check.json', result)
    return result


def main() -> None:
    # AI_NOTE: 同じ入力群と予算で再実行できる入口。既存の測定記録を上書きしない。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, action='append', default=[])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--worker', choices=['production', 'reference', 'runtime'])
    parser.add_argument('--case-file', type=Path)
    parser.add_argument('--seconds', type=float, default=10)
    parser.add_argument('--max-states', type=int, default=10000)
    parser.add_argument('--reference-seconds', type=float, default=30)
    parser.add_argument('--workers', type=int, default=2, choices=range(1, 5))
    args = parser.parse_args()
    if args.worker:
        worker(args)
        return
    if not args.cases or args.output.exists():
        parser.error('inputs are required and output must not exist')
    cases = [case for path in args.cases for case in json.loads(path.read_text(encoding='utf-8'))]
    if len({case['id'] for case in cases}) != len(cases):
        parser.error('case ids must be unique')
    args.output.mkdir(parents=True)
    started = perf_counter()
    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for result in pool.map(lambda case: run_case(case, args), cases):
            rows.append(result)
            write(args.output/'progress.json', rows)
            print(result['id'], result['status'], flush=True)
    counts = {status: sum(row['status'] == status for row in rows) for status in sorted({row['status'] for row in rows})}
    exact = [row for row in rows if row['classification'] == 'exact']
    report = {'counts': counts, 'total': len(rows), 'exact_cases': len(exact),
              'exact_complete_and_correct': sum(row['status'] == 'PASS' for row in exact),
              'elapsed_seconds': perf_counter()-started, 'settings': {'max_states': args.max_states, 'seconds': args.seconds,
                  'reference_seconds': args.reference_seconds, 'workers': args.workers}, 'cases': rows}
    write(args.output/'summary.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}, ensure_ascii=False), flush=True)
    if any(row['status'] in {'FAIL', 'ERROR', 'REFERENCE_ERROR'} for row in rows):
        raise SystemExit(1)
    if any(row['status'] != 'PASS' for row in exact):
        raise SystemExit(2)


if __name__ == '__main__':
    main()
