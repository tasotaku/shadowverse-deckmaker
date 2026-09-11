"""Run discovery and review, then revise once only when the formal review asks for development.

python -m svdeck.discovery_cycle SESSION OUTPUT --codex PATH --develop-seconds 1800 --review-seconds 900
The copied implementation runs every round. Existing sessions and judgments remain unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import sys
from types import FrameType
from typing import Any

from svdeck import discovery, discovery_inquiry as inquiry, discovery_run as engine, worker
from svdeck.discovery_evidence import digest, read_object, write_new


def prepare(source: Path, output: Path, codex: Path, develop_seconds: float, review_seconds: float,
            journal_root: Path | None = None, experiment_id: str | None = None,
            stage_prefix: str = 'cycle', research_seconds: float | None = None,
            inspect_seconds: float | None = None) -> Path:
    # AI_NOTE: 開始時の実装と入力を一度固定し、後の改訂へ別版のコードを混ぜない。
    source, output, codex = source.resolve(), output.resolve(), codex.resolve()
    if source.is_relative_to(output) or output.is_relative_to(source):
        raise ValueError('元探索と出力先は互いの内側へ置けません')
    if not codex.is_file() or any(not math.isfinite(n) or n <= 0 for n in (develop_seconds, review_seconds)):
        raise ValueError('実行ファイルと有限の正の制限秒数が必要です')
    if bool(journal_root) != bool(experiment_id) or not stage_prefix.strip():
        raise ValueError('journal-rootとexperiment-idは一緒に指定し、stage-prefixは空にしないでください')
    if ((research_seconds is None) != (inspect_seconds is None)
            or any(n is not None and (not math.isfinite(n) or n <= 0) for n in (research_seconds, inspect_seconds))):
        raise ValueError('追加の調査・照合には両方の有限の正の制限秒数が必要です')
    original = engine.manifest(source)
    discovery.report(source)
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    worker.save_record(output / 'result.json', {'status': 'preparing', 'started_at': started})
    try:
        runtime = output / 'runtime'
        shutil.copytree(Path(__file__).resolve().parent, runtime / 'svdeck',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        engine.copy_session(source, output / 'input')
        engine.check_unchanged(source, original, exact=True)
        config = {'source': str(source), 'original_manifest': original, 'started_at': started,
                  'input_manifest': engine.manifest(output / 'input'), 'runtime_manifest': engine.manifest(runtime),
                  'codex': str(codex), 'develop_seconds': develop_seconds, 'review_seconds': review_seconds,
                  'journal_root': str(journal_root.resolve()) if journal_root else None,
                  'experiment_id': experiment_id, 'stage_prefix': stage_prefix,
                  'research_seconds': research_seconds, 'inspect_seconds': inspect_seconds}
        write_new(output / 'config.json', config)
        return output
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        worker.save_record(output / 'result.json', {'status': 'failed', 'started_at': started,
                           'ended_at': datetime.now(timezone.utc).isoformat(), 'failure': str(exc)})
        raise


def next_step(session: Path, expected_revision: int, round_number: int) -> dict[str, Any]:
    # AI_NOTE: 当該正式評価の値と問いだけで分岐し、問いの存在を有用性や成功へ読み替えない。
    report = discovery.report(session)
    if not report['revisions'] or report['revisions'][-1]['revision'] != expected_revision:
        raise ValueError('今回の正式改訂が最新の履歴と一致しません')
    reviews = report['revisions'][-1]['reviews']
    if len(reviews) != 1:
        raise ValueError('今回の改訂に対応する正式評価1件が必要です')
    engine.verify_submission(session, 'develop', expected_revision)
    engine.verify_submission(session, 'review', expected_revision)
    review = reviews[0]
    reason = ('round_limit' if round_number == 2 else
              'value_' + review['value'] if review['value'] != 'develop' else
              'no_next_questions' if not review['next_questions'] else 'revise_once')
    return {'at': datetime.now(timezone.utc).isoformat(), 'round': round_number,
            'revision': expected_revision, 'proposal_hash': review['proposal_hash'], 'review_hash': digest(review),
            'judgment': {k: review[k] for k in ('procedure', 'value', 'novelty')},
            'next_questions': review['next_questions'], 'action': 'continue' if reason == 'revise_once' else 'stop',
            'reason': reason}


def run_prepared(output: Path) -> int:
    # AI_NOTE: 固定版の既存実行入口を順番に呼び、失敗時には次の担当を起動しない。
    output = output.resolve()
    if read_object(output / 'result.json')['status'] != 'preparing':
        raise ValueError('開始済みの記録は再実行・上書きできません')
    config = read_object(output / 'config.json')
    config_before = (output / 'config.json').read_bytes()
    source = Path(config['source'])
    current = output / 'input'
    result: dict[str, Any] = {'status': 'running', 'started_at': config['started_at'], 'rounds': [],
                              'verified_revisions': 0, 'verified_reviews': 0,
                              'limits': '実行補助。問いの価値・発見力・実戦の強さ・方法の採用を自動認定しない。最大2回で停止する。'}
    protected = [(source, config['original_manifest']), (current, config['input_manifest']),
                 (output / 'runtime', config['runtime_manifest'])]

    def interrupt(signum: int, frame: FrameType | None) -> None:
        # AI_NOTE: 担当間の中断も記録する。担当中の停止と子の回収は既存workerが引き受ける。
        raise KeyboardInterrupt

    previous = {sig: signal.signal(sig, interrupt) for sig in (signal.SIGINT, signal.SIGTERM)}
    try:
        worker.save_record(output / 'result.json', result)
        for number in (1, 2):
            for folder, before in protected:
                engine.check_unchanged(folder, before, exact=True)
            if (output / 'config.json').read_bytes() != config_before:
                raise ValueError('実行条件が変更されました')
            prior = discovery.report(current)
            latest = max((r['revision'] for r in prior['revisions']), default=0)
            round_output = output / f'round-{number}'
            round_record: dict[str, Any] = {'round': number, 'source': str(current), 'output': str(round_output),
                                           'started_at': datetime.now(timezone.utc).isoformat()}
            result['rounds'].append(round_record)
            worker.save_record(output / 'result.json', result)
            execution = engine.run(current, round_output, Path(config['codex']), config['develop_seconds'],
                                   config['review_seconds'], latest,
                                   Path(config['journal_root']) if config['journal_root'] else None,
                                   config['experiment_id'], f"{config['stage_prefix']}-{number}")
            round_record.update(ended_at=datetime.now(timezone.utc).isoformat(), result=execution)
            for folder, before in protected:
                engine.check_unchanged(folder, before, exact=True)
            if (output / 'config.json').read_bytes() != config_before:
                raise ValueError('実行条件が変更されました')
            if execution['status'] != 'completed':
                result.update(status='round_failed', stop_reason=execution['status'])
                break
            engine.check_unchanged(round_output / 'runtime', config['runtime_manifest'], exact=True)
            destination = round_output / 'session'
            if execution.get('session') != str(destination) or execution.get('formal_revisions') != 1 or execution.get('formal_reviews') != 1:
                raise ValueError('実行結果の正式件数または保存先が一致しません')
            engine.check_unchanged(destination, engine.manifest(current))
            decision = next_step(destination, latest + 1, number)
            write_new(round_output / 'decision.json', decision)
            for folder, before in protected:
                engine.check_unchanged(folder, before, exact=True)
            if (output / 'config.json').read_bytes() != config_before:
                raise ValueError('実行条件が変更されました')
            round_record['decision'] = decision
            result['verified_revisions'] += 1
            result['verified_reviews'] += 1
            protected.append((destination, engine.manifest(destination)))
            current = destination
            if decision['action'] == 'stop':
                # AI_NOTE: 追加予算を明示した試用・独自性未確認だけを調査へ渡し、元の採点は保持する。
                if config.get('research_seconds') is not None:
                    eligible = decision['judgment']['value'] == 'test' and decision['judgment']['novelty'] == 'unconfirmed'
                    result['followup'] = {'status': 'pending' if eligible else 'skipped',
                                          'reason': 'test_unconfirmed' if eligible else 'judgment_not_eligible',
                                          'review_hash': decision['review_hash']}
                    worker.save_record(output / 'result.json', result)
                    if eligible:
                        followup_output = output / 'novelty'
                        followup = inquiry.run(current, followup_output, Path(config['codex']), latest + 1,
                                               decision['review_hash'], None, config['research_seconds'], config['inspect_seconds'],
                                               Path(config['journal_root']) if config['journal_root'] else None,
                                               config['experiment_id'], f"{config['stage_prefix']}-novelty")
                        result['followup']['result'] = followup
                        result['followup']['status'] = followup['status']
                        for folder, before in protected:
                            engine.check_unchanged(folder, before, exact=True)
                        if (output / 'config.json').read_bytes() != config_before:
                            raise ValueError('実行条件が変更されました')
                        if followup['status'] != 'completed':
                            result.update(status='followup_failed', stop_reason=followup['status'])
                            break
                        engine.check_unchanged(followup_output / 'runtime', config['runtime_manifest'], exact=True)
                        if (followup.get('session') != str(followup_output / 'session')
                                or followup.get('formal_revisions') != 0 or followup.get('formal_reviews') != 0):
                            raise ValueError('追加調査が元の正式案・評価の件数または保存先を変更しました')
                        engine.check_unchanged(followup_output / 'session', engine.manifest(current))
                        current = followup_output / 'session'
                engine.copy_session(current, output / 'session')
                engine.check_unchanged(output / 'session', engine.manifest(current), exact=True)
                write_new(output / 'report.json', discovery.report(output / 'session'))
                result.update(status='completed', stop_reason=decision['reason'], session=str(output / 'session'),
                              judgment=decision['judgment'], source_unchanged=True)
                break
            worker.save_record(output / 'result.json', result)
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        result.update(status='failed', failure=str(exc))
    except KeyboardInterrupt:
        result.update(status='interrupted', stop_reason='external_interrupt')
    finally:
        result['ended_at'] = datetime.now(timezone.utc).isoformat()
        worker.save_record(output / 'result.json', result)
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    print(json.dumps({k: v for k, v in result.items() if k != 'rounds'}, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'completed' else 2


def main(argv: list[str] | None = None) -> int:
    # AI_NOTE: 実装を固定した後に同じプロセスを置き換え、全工程をその保存版から読み込む。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--codex', type=Path, required=True)
    parser.add_argument('--develop-seconds', type=float, required=True)
    parser.add_argument('--review-seconds', type=float, required=True)
    parser.add_argument('--research-seconds', type=float, help='最終test/unconfirmedだけに追加する調査の上限秒数')
    parser.add_argument('--inspect-seconds', type=float, help='追加調査を別担当が照合する上限秒数。research-secondsと一緒に指定')
    parser.add_argument('--journal-root', type=Path)
    parser.add_argument('--experiment-id')
    parser.add_argument('--stage-prefix', default='cycle')
    args = parser.parse_args(argv)
    try:
        output = prepare(args.session, args.output, args.codex, args.develop_seconds, args.review_seconds,
                         args.journal_root, args.experiment_id, args.stage_prefix, args.research_seconds, args.inspect_seconds)
        script = ('import sys; from pathlib import Path; sys.path.insert(0, sys.argv[1]); '
                  'from svdeck.discovery_cycle import run_prepared; raise SystemExit(run_prepared(Path(sys.argv[2])))')
        os.execv(sys.executable, [sys.executable, '-B', '-c', script, str(output / 'runtime'), str(output)])
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        parser.error(str(exc))
    return 2


if __name__ == '__main__':
    sys.exit(main())
