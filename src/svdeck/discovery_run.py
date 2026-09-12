"""Run one proposal/revision and an independent review through the existing public commands.

python -m svdeck.discovery_run SESSION OUTPUT --codex PATH --develop-seconds 1200 --review-seconds 900
python -m svdeck.discovery_run SESSION OUTPUT --codex PATH --review-only --revision N --review-seconds 600
The source session is read-only. OUTPUT/session retains the resulting formal records.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import hashlib
import fcntl
import io
import json
import math
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
from typing import Any
import uuid

from svdeck import discovery, worker
from svdeck.discovery_evidence import digest, read_object, write_new
from svdeck.discovery_sources import load_sources
from svdeck.discovery_read import packet_summary
from svdeck.worker_journal import RunJournal


def manifest(folder: Path) -> dict[str, str]:
    # AI_NOTE: 保存版の破損・書換えを検出し、未観測の成功を次の工程へ渡さない。
    result = {}
    for path in sorted(folder.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'共有リンクは複製対象にできません: {path}')
        if path.is_file():
            result[str(path.relative_to(folder))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def check_unchanged(folder: Path, before: dict[str, str], exact: bool = False) -> None:
    # AI_NOTE: 元の保存物は完全一致、追記可能な探索先は開始前の全ファイルの保持を要求する。
    after = manifest(folder)
    changed = [name for name, key in before.items() if after.get(name) != key]
    if changed or (exact and after != before):
        raise ValueError(f'固定ファイルが変更されました: {folder}: {changed or "追加ファイル"}')


def copy_session(source: Path, destination: Path, for_review: bool = False) -> None:
    # AI_NOTE: 私的な実行ログは複製せず、別評価には古い評価と考案用packetを物理的に渡さない。
    destination.mkdir(parents=True)
    for path in source.rglob('*'):
        relative = path.relative_to(source)
        first = relative.parts[0]
        formal = first in {'context.json', 'snapshot.db', 'sources', 'packets'} or first.startswith(('revision-', 'review-'))
        if not formal or (for_review and (first == 'packets' or first.startswith('review-'))):
            continue
        if path.is_symlink():
            raise ValueError(f'共有リンクは複製対象にできません: {path}')
        if path.is_file():
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    (destination / 'packets').mkdir(exist_ok=True)



def check_packet(session: Path, data: dict[str, Any], fixed: dict[str, Any]) -> None:
    # AI_NOTE: 新しい資料版でも親案・本文・指示・履歴をすり替えず、保存済み資料の追記だけを許す。
    mutable = {'sources', 'review_contexts'}
    if {k: v for k, v in data.items() if k not in mutable} != {k: v for k, v in fixed.items() if k not in mutable}:
        raise ValueError('提出資料の固定項目が初期資料と一致しません')
    sources = discovery._objects(data.get('sources'), 'sources')
    saved = {s['source_hash']: s for s in load_sources(session)}
    keys = {s['source_hash'] for s in sources}
    if len(keys) != len(sources) or not {s['source_hash'] for s in fixed['sources']} <= keys or any(saved.get(s['source_hash']) != s for s in sources):
        raise ValueError('提出資料の追加資料が保存済み本文と一致しません')
    if data.get('review_contexts') != discovery._review_contexts(session, data['previous_reviews'], sources, data['context_hash']):
        raise ValueError('提出資料の過去評価との対応が一致しません')

def public_main(work: Path, argv: list[str] | None = None) -> int:
    # AI_NOTE: 明示終了を使う工程だけ公開操作を直列化し、受付後の追加保存を拒む。
    if not read_object(work / 'public-config.json').get('explicit_finish'):
        return public_operation(work, argv)
    with (work / '.public.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return public_operation(work, argv)


def public_operation(work: Path, argv: list[str] | None = None) -> int:
    # AI_NOTE: 自分の工程だけを公開し、入口で拒んだ操作も開始終了と共に保存する。
    args = list(sys.argv[1:] if argv is None else argv)
    config = read_object(work / 'public-config.json')
    stage, revision = config['stage'], config['revision']
    session = work / 'session'
    operation: dict[str, Any] = {'args': args, 'started_at': datetime.now(timezone.utc).isoformat()}
    stdout, stderr = io.StringIO(), io.StringIO()
    code = 2
    request: dict[str, Any] | None = None
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            if not args or args in (['--help'], ['help']):
                print('Use: public.py packet [--summary] | read HASH SECTION [--offset N --limit N] | report')
                print('For develop: submit FILE | attach FILE | attach-file FILE OPTIONS | compare BEFORE AFTER')
                print('For review: review FILE. For inquiry/inspect: attach FILE | attach-file FILE OPTIONS.')
                print('Session and stage are fixed. Read inputs only through this entry.')
                if config.get('explicit_finish'):
                    print('After submission and report: finish. This seals saved work and asks the supervisor to stop this worker.')
                code = 0
            else:
                command, rest = args[0], args[1:]
                stage_commands = {'develop': {'submit', 'attach', 'attach-file', 'compare'}, 'review': {'review'},
                                  'inquiry': {'attach', 'attach-file'}, 'inspect': {'attach', 'attach-file'}}
                allowed = {'packet', 'read', 'report'} | stage_commands[stage]
                if config.get('explicit_finish') and stage in {'develop', 'review'}:
                    allowed.add('finish')
                if (work / 'finish-request.json').exists() and command not in {'finish', 'read'}:
                    raise ValueError('終了要求後は保存内容を変更できません')
                if command not in allowed:
                    raise ValueError('この工程では許可されていない操作です')
                help_only = rest == ['--help']
                if command == 'packet' and not help_only:
                    if rest not in ([], ['--summary']):
                        raise ValueError('packetの工程・改訂番号は固定です')
                    rest = ['--revision', str(revision), '--stage', stage, *rest]
                if command == 'read' and not help_only:
                    if len(rest) < 2 or len(rest[0]) != 64 or any(c not in '0123456789abcdef' for c in rest[0]):
                        raise ValueError('この工程のpacket識別値と区分が必要です')
                    data = discovery._read_envelope(session / 'packets' / (rest[0] + '.json'))
                    if data['stage'] != stage or data['revision'] != revision:
                        raise ValueError('別の工程・改訂のpacketは読めません')
                    if stage in {'inquiry', 'inspect'}:
                        check_packet(session, data, discovery._read_envelope(session / 'packets' / (config['packet_hash'] + '.json')))
                if command in {'submit', 'review', 'attach', 'attach-file'} and not help_only:
                    if not rest:
                        raise ValueError('自分の作業先の入力ファイルが必要です')
                    content = (work / rest[0]).resolve()
                    if not content.is_relative_to(work.resolve()):
                        raise ValueError('作業先の外のファイルは読み込めません')
                    if command in {'submit', 'review'}:
                        if len(rest) != 1:
                            raise ValueError('提出には回答ファイル1件だけを指定してください')
                        response = read_object(content)
                        # AI_NOTE: 名乗りの一致で別プロセスを誤拒否せず、元回答と割当担当を両方残す。
                        operation['submission'] = {'input': str(content.relative_to(work.resolve())),
                                                   'response': response, 'assigned_author': config['author']}
                        response = {**response, 'author': config['author']}
                        data = discovery._response_packet(session, response, stage)
                        if data['revision'] != revision:
                            raise ValueError('固定した改訂への回答ではありません')
                        fixed = discovery._read_envelope(session / 'packets' / (config['packet_hash'] + '.json'))
                        if stage == 'review' and response['packet_hash'] != config['packet_hash']:
                            raise ValueError('評価は今回の固定資料だけを使います')
                        check_packet(session, data, fixed)
                    rest[0] = str(content)
                if command == 'finish' and help_only:
                    print('finish: 正式提出と提出後reportを確認して終了を要求します。追加引数はありません。ヘルプでは終了を要求しません。')
                    code = 0
                elif command == 'finish':
                    if rest:
                        raise ValueError('finishには追加引数を指定しません')
                    contract = read_object(work / 'finish-config.json')
                    if (work / 'finish-request.json').exists():
                        check_finish(work, contract)
                    else:
                        request = finish_evidence(work, contract)
                    print(json.dumps({'status': 'finish_requested', 'completion': '監視側の停止と再検査は未完了'}, ensure_ascii=False))
                    code = 0
                elif command in {'submit', 'review'} and not help_only:
                    value = discovery.submit(session, response) if command == 'submit' else discovery.review(session, response)
                    print(json.dumps({**value, 'author': config['author']}, ensure_ascii=False, indent=2))
                    code = 0
                elif command == 'packet' and stage in {'inquiry', 'inspect'} and not help_only:
                    # AI_NOTE: 調査では案の再提出を要求せず、固定した問いへ追加資料だけを反映する。
                    from svdeck.discovery_inquiry import refresh_packet
                    envelope = refresh_packet(session, config['packet_hash'])
                    value = packet_summary(session, envelope['sha256']) if args[1:] == ['--summary'] else envelope
                    print(json.dumps(value, ensure_ascii=False, indent=2))
                    code = 0
                elif command == 'packet' and stage == 'review' and not help_only:
                    key = config['packet_hash']
                    value = packet_summary(session, key) if args[1:] == ['--summary'] else read_object(session / 'packets' / (key + '.json'))
                    print(json.dumps(value, ensure_ascii=False, indent=2))
                    code = 0
                else:
                    code = discovery.main([command, str(session), *rest])
        except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
            print(str(exc), file=sys.stderr)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    operation.update(ended_at=datetime.now(timezone.utc).isoformat(), exit_code=code,
                     stdout=stdout.getvalue(), stderr=stderr.getvalue())
    logs = work / 'operations'
    logs.mkdir(exist_ok=True)
    operation_path = logs / (uuid.uuid4().hex + '.json')
    write_new(operation_path, operation)
    if request is not None and code == 0:
        request.update(operation=operation_path.name, operation_hash=digest(operation))
        worker.save_record(work / 'finish-request.json', request)
    sys.stdout.write(stdout.getvalue())
    sys.stderr.write(stderr.getvalue())
    return code



def verify_submission(session: Path, stage: str, revision: int) -> None:
    # AI_NOTE: ファイルの存在だけを信用せず、正式保存入口の全検査を一時複製で再実行する。
    paths = list(session.glob(f'review-{revision:04d}-*.json')) if stage == 'review' else [session / f'revision-{revision:04d}.json']
    if len(paths) != 1:
        raise ValueError('検査する正式保存物が1件ではありません')
    payload = discovery._read_envelope(paths[0])
    with tempfile.TemporaryDirectory(prefix='svdeck-verify-') as temporary:
        copy = Path(temporary) / 'session'
        copy_session(session, copy)
        (copy / paths[0].name).unlink()
        if stage == 'develop':
            discovery.submit(copy, payload)
        else:
            discovery.review(copy, payload)
        if (copy / paths[0].name).read_bytes() != paths[0].read_bytes():
            raise ValueError('正式入口で再保存した内容が一致しません')

class MissingSubmission(ValueError):
    """A naturally completed worker did not save the assigned formal record."""


def validate_stage(work: Path, contract: dict[str, Any]) -> dict[str, Any]:
    # AI_NOTE: 自然終了と明示終了に同じ正式保存・固定入力検査を適用する。
    for folder, before in contract['protected'].items():
        check_unchanged(Path(folder), before, exact=True)
    fixed = contract['fixed']
    check_unchanged(work, fixed)
    config = read_object(work / 'public-config.json')
    stage, author = config['stage'], config['author']
    expected, parent, review_only = contract['expected'], contract['parent'], contract['review_only']
    envelope = read_object(work / 'session/packets' / (config['packet_hash'] + '.json'))
    report = discovery.report(work / 'session')
    if stage == 'develop':
        initial_reviews = {name for name in fixed if name.startswith('session/review-')}
        current_reviews = {'session/' + path.name for path in (work / 'session').glob('review-*.json')}
        if current_reviews != initial_reviews:
            raise ValueError('考案担当は評価ファイルを追加できません')
        proposals = report['revisions']
        if len(proposals) == contract['prior_count']:
            raise MissingSubmission('正式改訂がありません')
        if len(proposals) != contract['prior_count'] + 1 or proposals[-1]['revision'] != expected or proposals[-1]['parent_revision'] != parent or proposals[-1]['reviews']:
            raise ValueError('今回の親に対応する正式改訂1件だけが必要です')
        current = discovery._revision(work / 'session', expected)
        assert current is not None
        if current['author'] != author:
            raise ValueError('正式改訂の担当IDが起動時の割当と一致しません')
        discovery._validate_proposal(current, envelope['data']['context'], load_sources(work / 'session'))
        referenced = discovery._response_packet(work / 'session', current, 'develop')
        check_packet(work / 'session', referenced, envelope['data'])
    else:
        reviews = report['revisions'][-1]['reviews']
        if not reviews and not list((work / 'session').glob('review-*.json')):
            raise MissingSubmission('正式な別評価がありません')
        if len(list((work / 'session').glob('review-*.json'))) != 1 or len(reviews) != 1 or any(p['reviews'] for p in report['revisions'][:-1]) or len(report['revisions']) != contract['prior_count'] + (0 if review_only else 1):
            raise ValueError('今回の改訂への正式な別評価1件だけが必要です')
        stored = reviews[0]
        if stored['author'] != author:
            raise ValueError('正式評価の担当IDが起動時の割当と一致しません')
        discovery._response_packet(work / 'session', stored, 'review')
        if stored['packet_hash'] != envelope['sha256']:
            raise ValueError('別評価が今回の固定資料を参照していません')
        proposal = envelope['data']['proposal']
        if stored['author'] == proposal['author'] or stored['proposal_hash'] != digest(proposal):
            raise ValueError('別担当と提案の対応が一致しません')
    verify_submission(work / 'session', stage, expected)
    return report


def finish_evidence(work: Path, contract: dict[str, Any], pinned: dict[str, Any] | None = None) -> dict[str, Any]:
    # AI_NOTE: 今回の提出後reportと正式保存を結び、資料保存だけを完了にしない。
    before = manifest(work / 'session')
    report = validate_stage(work, contract)
    config = read_object(work / 'public-config.json')
    command = 'submit' if config['stage'] == 'develop' else 'review'
    if pinned is None:
        paths = list((work / 'operations').glob('*.json'))
    else:
        names = [pinned['submission_operation'], pinned['report_operation']]
        if any(not isinstance(name, str) or Path(name).name != name for name in names):
            raise ValueError('公開操作の識別値が不正です')
        paths = [work / 'operations' / name for name in names]
    operations = [(p.name, read_object(p)) for p in paths]
    submitted = [(name, op) for name, op in operations if op.get('exit_code') == 0 and isinstance(op.get('submission'), dict) and op.get('args', [])[:1] == [command]]
    if len(submitted) != 1:
        raise ValueError('今回の公開正式提出1件が必要です')
    submission_name, submission = submitted[0]
    stored = discovery._revision(work / 'session', contract['expected']) if command == 'submit' else report['revisions'][-1]['reviews'][0]
    raw = submission['submission']
    if raw['assigned_author'] != config['author'] or stored is None or any(stored.get(k) != v for k, v in raw['response'].items() if k != 'author'):
        raise ValueError('公開提出と正式保存の内容が一致しません')
    reports = [(name, op) for name, op in operations if op.get('args') == ['report'] and op.get('exit_code') == 0
               and op['started_at'] >= submission['ended_at'] and json.loads(op['stdout']) == report]
    if not reports:
        raise ValueError('正式提出後の現在内容に一致する公開reportが必要です')
    report_name, reported = max(reports, key=lambda item: item[1]['ended_at'])
    check_unchanged(work / 'session', before, exact=True)
    return {'config_hash': digest(config), 'session_manifest': before, 'report_hash': digest(report),
            'submission_operation': submission_name, 'submission_hash': digest(submission),
            'report_operation': report_name, 'report_operation_hash': digest(reported)}


def check_finish(work: Path, contract: dict[str, Any]) -> dict[str, Any] | None:
    # AI_NOTE: 要求は合図だけとし、監視側の固定値と停止前後の同じ保存物で再検査する。
    path = work / 'finish-request.json'
    if not path.exists():
        return None
    request = read_object(path)
    if not isinstance(request.get('operation'), str) or Path(request['operation']).name != request['operation']:
        raise ValueError('終了操作の識別値が不正です')
    operation = read_object(work / 'operations' / request['operation'])
    if operation.get('args') != ['finish'] or operation.get('exit_code') != 0 or digest(operation) != request['operation_hash']:
        raise ValueError('終了要求の公開操作記録が一致しません')
    evidence = finish_evidence(work, contract, request)
    if request != {**evidence, 'operation': request['operation'], 'operation_hash': request['operation_hash']}:
        raise ValueError('終了要求後の保存内容が変わっています')
    return {'request_hash': digest(request), 'report_hash': request['report_hash']}


def poll_finish(work: Path, contract: dict[str, Any]) -> dict[str, Any] | None:
    # AI_NOTE: 公開操作の書込み中は待ち、途中の操作記録を壊れた要求と誤認しない。
    with (work / '.public.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return None
        return check_finish(work, contract)


def run(source: Path, output: Path, codex: Path, develop_seconds: float | None, review_seconds: float,
        revision: int | None = None, journal_root: Path | None = None,
        experiment_id: str | None = None, stage_prefix: str = 'live', review_only: bool = False, explicit_finish: bool = False) -> dict[str, Any]:
    # AI_NOTE: 別評価のみなら最新の保存案を再検査し、再考案せず旧評価を隔離して渡す。
    source, output, codex = source.resolve(), output.resolve(), codex.resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('元探索と出力先は互いの内側へ置けません')
    if review_only and (develop_seconds is not None or revision is None or revision <= 0):
        raise ValueError('review-onlyには最新の正のrevisionを指定し、develop-secondsは省いてください')
    if not review_only and develop_seconds is None:
        raise ValueError('通常実行にはdevelop-secondsが必要です')
    limits = [review_seconds] if develop_seconds is None else [develop_seconds, review_seconds]
    if not codex.is_file() or any(not math.isfinite(n) or n <= 0 for n in limits):
        raise ValueError('実行ファイルと有限の正の制限秒数が必要です')
    if bool(journal_root) != bool(experiment_id):
        raise ValueError('journal-rootとexperiment-idは一緒に指定してください')
    original = manifest(source)
    output.mkdir(parents=True, exist_ok=False)
    result: dict[str, Any] = {'status': 'preparing', 'run_id': uuid.uuid4().hex, 'started_at': datetime.now(timezone.utc).isoformat(),
                              'source': str(source), 'output': str(output), 'stages': [], 'review_only': review_only, 'explicit_finish': explicit_finish,
                              'limits': '実行完了は試行推薦や発見力の証明ではない。公開入口の制約と固定入力の照合はOS全体の行動監査ではない。追加資料に旧判断を書き写したかは意味の点検が必要。'}
    try:
        runtime = output / 'runtime'
        shutil.copytree(Path(__file__).resolve().parent, runtime / 'svdeck', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        runtime_before = manifest(runtime)
        work = output / ('prepare' if review_only else 'develop')
        copy_session(source, work / 'session')
        prepared = work / 'session'
        prior = discovery.report(work / 'session')
        latest = max((p['revision'] for p in prior['revisions']), default=0)
        parent = latest if revision is None else revision
        expected = latest if review_only else latest + 1
        result.update(parent_revision=parent, expected_revision=expected, original_manifest=original)
        if review_only:
            if revision != latest:
                raise ValueError('review-onlyのrevisionは最新の保存済み正式改訂を指定してください')
            verify_submission(prepared, 'develop', expected)
        stages = [('review', review_seconds, expected)]
        if not review_only:
            assert develop_seconds is not None
            stages.insert(0, ('develop', develop_seconds, parent))
        for stage, limit, target in stages:
            author = f"worker:{result['run_id']}:{stage}"
            if stage == 'review':
                work = output / 'review'
                envelope = discovery.packet(prepared, target, stage)
                copy_session(prepared, work / 'session', for_review=True)
                write_new(work / 'session/packets' / (envelope['sha256'] + '.json'), envelope)
                prepared_before = manifest(prepared)
            else:
                envelope = discovery.packet(work / 'session', target, stage)
            summary = packet_summary(work / 'session', envelope['sha256'])
            write_new(work / 'input-summary.json', summary)
            write_new(work / 'public-config.json', {'stage': stage, 'revision': target, 'packet_hash': envelope['sha256'], 'author': author, 'explicit_finish': explicit_finish})
            (work / 'public.py').write_text('import sys\nsys.dont_write_bytecode = True\nfrom pathlib import Path\nsys.path.insert(0, ' + repr(str(runtime)) + ')\nfrom svdeck.discovery_run import public_main\nraise SystemExit(public_main(Path(__file__).resolve().parent))\n')
            instruction = envelope['data']['instruction']
            reading = 'カード本文、注記、生成先、資料、履歴' + ('、直前評価' if stage == 'develop' else '')
            # AI_NOTE: 担当も監視側と同じ時計を参照できるようにし、UTC時刻差を別の期限にしない。
            prompt = f'''{instruction}

実行条件: {stage} 工程を今回1回だけ行います。制限は経過 {limit:g} 秒です。待ち時間も含みます。
上限は監視側の経過時計で判定します。残り秒は次で確認できます: {sys.executable} -c "import os,time; print(float(os.environ['SVDECK_DEADLINE_MONOTONIC']) - time.monotonic())"
UTCの開始・終了も記録しますが、その時刻差だけで期限切れと判定しません。PC休止等の扱いはOSに依存し、時計差があれば両方の値と未確認の原因を報告します。終了前に提出・保存を済ませてください。
この工程の担当IDは {author} です。公開提出はauthorだけをこのIDへ結び、元の申告名と回答本文を公開操作記録に保持します。名乗りを推測する必要はありません。判断・手順・根拠は変更しません。
{reading}は公開入口から読みます。作業先の外・親会話・実装・別探索・過去の私的実行ログを読まないでください。
input-summary.jsonには今回の資料識別値と回答形式があります。入力の実体は直接開かず、次の公開コマンドで必要な範囲を読んでください。
{sys.executable} public.py --help
{sys.executable} public.py packet --summary
{sys.executable} public.py read {envelope['sha256']} SECTION --offset 0 --limit 20
自分の作業先にproposal.json又はreview.jsonを保存して公開submit又はreviewで正式提出し、reportで保存内容を確認してください。今回の正式提出は1件までです。
追加調査をした考案担当は必要な資料をattach又はattach-fileで保存し、packetを再取得してから正式提出してください。評価担当は旧採否を探さず、今回の固定資料から評価します。
カード・既存案・評価・入力設定を書き換えず、足りない情報を推測で埋めません。提出できなければその事実をfinal-messageに残してください。
結論と残った問題を短くfinal-messageに記してください。私的な思考過程は保存資料へ転記しません。
'''
            if explicit_finish:
                prompt += f'正式提出とreport確認を終え、これ以上保存内容を変えない段階で {sys.executable} public.py finish を実行してください。受付後は保存内容を変更できません。監視側が停止と再検査を行い、正式資料から成果を回収します。\n'
            (work / 'prompt.md').write_text(prompt)
            fixed = manifest(work)
            protected = {str(source): original, str(runtime): runtime_before}
            if stage == 'review':
                protected[str(prepared)] = prepared_before
            contract = {'fixed': fixed, 'protected': protected, 'expected': expected, 'parent': parent,
                        'prior_count': len(prior['revisions']), 'review_only': review_only}
            if explicit_finish:
                write_new(work / 'finish-config.json', contract)
                (work / '.public.lock').touch()
                fixed = manifest(work)
                contract = {**contract, 'fixed': fixed}
            result['status'] = stage
            worker.save_record(output / 'result.json', result)
            journal = RunJournal(journal_root, experiment_id, f'{stage_prefix}-{stage}') if journal_root and experiment_id else None
            command = [str(codex), '--search', 'exec', '--ephemeral', '--sandbox', 'workspace-write',
                       '--skip-git-repo-check', '--cd', str(work), '--json', '--output-last-message', str(work / 'final-message.md'), '-']
            if explicit_finish:
                code, execution = worker.run(command, output / (stage + '-run'), limit, 2, work,
                                             work / 'prompt.md', 'elapsed', journal, lambda: poll_finish(work, contract))
            else:
                code, execution = worker.run(command, output / (stage + '-run'), limit, 2, work,
                                             work / 'prompt.md', 'elapsed', journal)
            result['stages'].append({'stage': stage, 'author': author, 'returncode': code, 'run': execution})
            check_unchanged(source, original, exact=True)
            check_unchanged(runtime, runtime_before, exact=True)
            check_unchanged(work, fixed)
            if stage == 'review':
                check_unchanged(prepared, prepared_before, exact=True)
            if code != 0 or execution['status'] not in ({'completed', 'finished_by_request'} if explicit_finish else {'completed'}):
                result.update(status=stage + '_failed', failure='担当の実行が完了していないため次へ進みません')
                break
            try:
                if explicit_finish:
                    check_finish(work, contract)
                report = validate_stage(work, contract)
            except MissingSubmission as exc:
                result.update(status=stage + '_missing', failure=str(exc))
                break
            if stage == 'review':
                stored = report['revisions'][-1]['reviews'][0]
                result['judgment'] = {key: stored[key] for key in ('procedure', 'value', 'novelty')}
            write_new(output / (stage + '-report.json'), report)
        if result['status'] == 'review':
            destination = output / 'session'
            copy_session(prepared, destination)
            for path in (output / 'review/session').glob('review-*.json'):
                write_new(destination / path.name, read_object(path))
            review_packet = output / 'review/session/packets' / (stored['packet_hash'] + '.json')
            final_packet = destination / 'packets' / review_packet.name
            if final_packet.exists():
                if final_packet.read_bytes() != review_packet.read_bytes():
                    raise ValueError('評価資料の同じ識別値に異なる内容があります')
            else:
                write_new(final_packet, read_object(review_packet))
            write_new(output / 'report.json', discovery.report(destination))
            result.update(status='completed', session=str(destination), source_unchanged=True,
                          formal_revisions=0 if review_only else 1, formal_reviews=1)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        result.update(status='failed', failure=str(exc))
    finally:
        result['ended_at'] = datetime.now(timezone.utc).isoformat()
        worker.save_record(output / 'result.json', result)
    return result


def main(argv: list[str] | None = None) -> int:
    # AI_NOTE: 評価再開では考案予算を要求せず、対象の明示と通常実行との指定違いを検査する。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--codex', type=Path, required=True)
    parser.add_argument('--develop-seconds', type=float)
    parser.add_argument('--review-seconds', type=float, required=True)
    parser.add_argument('--revision', type=int)
    parser.add_argument('--review-only', action='store_true', help='最新の保存済み正式改訂を再考案せず別評価する。revision必須、develop-secondsは指定不可。')
    parser.add_argument('--explicit-finish', action='store_true', help='担当のfinish操作と保存再検査で監視側が終了させる任意方式')
    parser.add_argument('--journal-root', type=Path)
    parser.add_argument('--experiment-id')
    parser.add_argument('--stage-prefix', default='live')
    args = parser.parse_args(argv)
    try:
        result = run(args.session, args.output, args.codex, args.develop_seconds, args.review_seconds,
                     args.revision, args.journal_root, args.experiment_id, args.stage_prefix, args.review_only, args.explicit_finish)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps({key: value for key, value in result.items() if key not in {'stages', 'original_manifest'}}, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'completed' else 2


if __name__ == '__main__':
    sys.exit(main())
