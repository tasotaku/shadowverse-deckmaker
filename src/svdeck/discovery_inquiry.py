"""Run a saved review question through research, source storage, and independent inspection.

python -m svdeck.discovery_inquiry SESSION OUTPUT --codex PATH --revision 1 \
    --review-hash HASH --question-index 0 --research-seconds 900 --inspect-seconds 600
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any
import uuid

from svdeck import discovery, worker
from svdeck.discovery_evidence import digest, read_object, write_new
from svdeck.discovery_read import packet_summary, read_packet
from svdeck.discovery_run import check_finish, check_packet, check_unchanged, copy_session, manifest, poll_finish, verify_submission
from svdeck.discovery_sources import load_sources
from svdeck.worker_journal import RunJournal
from svdeck.inquiry_journal import InquiryJournal


RESEARCH = """保存済みの案に残った問いを調べる担当です。inquiry_focusの問いを調査し、根拠と結論を追加資料として保存してください。
元案の再改訂・採点はしません。カード本文・両側の注記・既存資料を必要な範囲で読み、問いを解くために必要な調査を行います。
先行例はカード名だけでなく、使い方・条件・構築で担う役割を照合してください。誰かが試しただけで一般的に広まっているとは扱いません。
実際の検索語・検索範囲・URL・観察日時、取得本文と自分の解釈、用途の一致と相違、取得不能・未確認を分けて残します。
見つからないことを未発見の証明にせず、調べて分かったことと残る問いを書いてください。勝率や実機観察を作りません。
参照した資料はattach-file等で保持し、結論をanswer.mdへまとめて指定の位置へ保存します。元案・評価・DBを書き換えません。"""

INSPECT = """調査担当とは別の資料照合担当です。inquiry_focusの問いと、渡された調査報告・追加資料を読んでください。
報告が出典の内容に支えられ、問いに何を答えたかを点検します。必要なら実際の出典を再確認し、確認できない範囲を分けます。
カード名の同居と同用途、同用途の例と一般的な普及、取得本文と調査担当の解釈を区別してください。
資料件数・報告の存在・過去の採点だけで問いの解決を認定しません。案の改訂や強さの再採点は行いません。
answer.mdへ、照合できた主張と根拠、誤り・根拠不足、問いに新しく答えられた範囲、未確認をまとめ、指定の位置へ資料として保存してください。"""

NOVELTY_QUESTION = """対象案のフォーマット、具体的な使い方、構築で担う役割について、同じ用途の先例と一般的な普及を外部出典で調べてください。
カード名の同居だけで同じ用途とせず、誰かが試した例だけで一般に広まっているとしません。検索語・調査範囲・URL・確認日時・実際に取得した内容と解釈を分けて残してください。
検索で見つからないことを独自性の証明にせず、分かったこと・判断できない範囲を示してください。元の案の改訂、採点の変更、自動棄却は行いません。"""


def refresh_packet(session: Path, packet_hash: str) -> dict[str, Any]:
    # AI_NOTE: 元の問いと資料本文を保持し、資料を添付した後も同じ入口から新版を読み直せるようにする。
    fixed = discovery._read_envelope(session / 'packets' / (packet_hash + '.json'))
    if fixed['stage'] not in {'inquiry', 'inspect'}:
        raise ValueError('調査・照合の固定資料が必要です')
    data = {**fixed, 'sources': load_sources(session)}
    check_packet(session, data, fixed)
    envelope = discovery._envelope(data)
    path = session / 'packets' / (envelope['sha256'] + '.json')
    if not path.exists():
        write_new(path, envelope)
    return envelope


def verify_report(work: Path, config: dict[str, Any], operation_paths: list[Path] | None = None) -> dict[str, Any]:
    # AI_NOTE: 報告ファイルだけで完了にせず、公開添付・新版への反映・全本文の再読を保存物と照合する。
    session = work / 'session'
    raw = (work / 'answer.md').read_bytes()
    matches = [s for s in load_sources(session) if s['kind'] == config['report_kind'] and s['location'] == config['report_location']]
    if len(matches) != 1 or matches[0]['content'] != raw.decode('utf-8'):
        raise ValueError('answer.mdと一致する正式な調査・照合資料が1件必要です')
    source = matches[0]
    # AI_NOTE: 終了後は受付時に固定した操作だけで同じ検査を再現し、後から増えた読出しを根拠へ足さない。
    paths = (work / 'operations').glob('*.json') if operation_paths is None else operation_paths
    operations = sorted((read_object(p) for p in paths), key=lambda x: x['started_at'])
    attached = False
    reports = False
    covered: dict[str, set[int]] = {}
    for op in operations:
        args = op['args']
        if op['exit_code'] != 0 or not args or '--help' in args or '-h' in args:
            continue
        if args[0] == 'attach-file':
            value = json.loads(op['stdout'])
            item = value.get('input_file', {})
            if (item.get('path') == str((work / 'answer.md').resolve()) and item.get('sha256') == hashlib.sha256(raw).hexdigest()
                    and source['source_hash'] in value.get('added', []) + value.get('existing', [])):
                attached = True
        elif attached and args == ['report']:
            reports = json.loads(op['stdout']) == discovery.report(session)
        elif attached and args[0] == 'read':
            value = json.loads(op['stdout'])
            if value['section'] not in {'sources', 'source:' + source['source_hash']}:
                continue
            packet = discovery._read_envelope(session / 'packets' / (value['sha256'] + '.json'))
            fixed = discovery._read_envelope(session / 'packets' / (config['packet_hash'] + '.json'))
            check_packet(session, packet, fixed)
            if source not in packet['sources']:
                continue
            observed = read_packet(session, value['sha256'], value['section'], value['offset'], value['limit'])
            if value != observed:
                raise ValueError('公開再読の記録が保存本文と一致しません')
            # AI_NOTE: 単一本文と資料全体では行番号が違うため、同じ版でも再読範囲を混ぜない。
            seen = covered.setdefault(value['sha256'] + ':' + value['section'], set())
            seen.update(range(value['offset'], value['offset'] + len(value['content'])))
            if value['section'].startswith('source:'):
                if set(range(value['total'])) <= seen:
                    covered['complete'] = {1}
                continue
            # sourcesは整形JSONの行。対象資料の範囲だけを必須にし、全資料の再読は強制しない。
            lines = json.dumps([{**s, 'content': s['content'].splitlines(keepends=True)} for s in packet['sources']], ensure_ascii=False, indent=2).splitlines(keepends=True)
            start = sum(len(json.dumps({**s, 'content': s['content'].splitlines(keepends=True)}, ensure_ascii=False, indent=2).splitlines()) for s in packet['sources'][:packet['sources'].index(source)]) + 1
            length = len(json.dumps({**source, 'content': source['content'].splitlines(keepends=True)}, ensure_ascii=False, indent=2).splitlines())
            if start + length > len(lines):
                raise ValueError('再読範囲の計算が資料の行数を超えています')
            if set(range(start, start + length)) <= seen:
                covered['complete'] = {1}
    if not attached:
        raise ValueError('answer.mdの公開添付が必要です')
    if not covered.get('complete'):
        raise ValueError('新しい資料版からanswer.mdの全文再読が必要です')
    if not reports:
        raise ValueError('最新の保存状態と一致するreportが必要です。資料の追加後にreportを再実行してください')
    return {'source_hash': source['source_hash'], 'file_sha256': hashlib.sha256(raw).hexdigest(),
            'public_attachment': True, 'public_reread': True, 'report_read': True}


def inquiry_finish_evidence(work: Path, contract: dict[str, Any], pinned: dict[str, Any] | None = None) -> dict[str, Any]:
    # AI_NOTE: 担当・固定資料・元案を保持した資料提出だけを閉じ、受付時の公開操作そのものも固定する。
    for folder, before in contract['protected'].items():
        check_unchanged(Path(folder), before, exact=True)
    fixed = contract['fixed']
    check_unchanged(work, fixed)
    config = read_object(work / 'public-config.json')
    if not config.get('explicit_finish') or config['stage'] not in {'inquiry', 'inspect'}:
        raise ValueError('調査・照合の明示終了が選択されていません')
    session = work / 'session'
    before = manifest(session)
    packet = discovery._read_envelope(session / 'packets' / (config['packet_hash'] + '.json'))
    if packet['stage'] != config['stage'] or packet['revision'] != config['revision']:
        raise ValueError('終了対象の工程・改訂が固定資料と一致しません')
    expected = {name for name in fixed if name.startswith('session/revision-')}
    actual = {'session/' + path.name for path in session.glob('revision-*.json')}
    if actual != expected or list(session.glob('review-*.json')):
        raise ValueError('調査担当は案の改訂・正式評価を追加できません')
    if pinned is None:
        operation_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in (work / 'operations').glob('*.json')}
    else:
        operation_hashes = pinned['operation_manifest']
        if not isinstance(operation_hashes, dict) or any(not isinstance(name, str) or Path(name).name != name
                                                        or not name.endswith('.json') for name in operation_hashes):
            raise ValueError('公開操作の識別値が不正です')
    check_unchanged(work / 'operations', operation_hashes)
    submission = verify_report(work, config, [work / 'operations' / name for name in operation_hashes])
    report = discovery.report(session)
    check_unchanged(session, before, exact=True)
    check_unchanged(work / 'operations', operation_hashes)
    return {'config_hash': digest(config), 'session_manifest': before, 'report_hash': digest(report),
            'answer_sha256': submission['file_sha256'], 'submission': submission, 'operation_manifest': operation_hashes}


def run(source: Path, output: Path, codex: Path, revision: int, review_hash: str, question_index: int | None,
        research_seconds: float, inspect_seconds: float, journal_root: Path | None = None,
        experiment_id: str | None = None, stage_prefix: str = 'live',
        inspect_source: str | None = None, journal_run_stage: str | None = None, explicit_finish: bool = False) -> dict[str, Any]:
    # AI_NOTE: 調査と照合を資料提出としてつなぎ、元案・旧評価は最終出力まで保持する。
    source, output, codex = source.resolve(), output.resolve(), codex.resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('元探索と出力先は互いの内側へ置けません')
    if not codex.is_file() or any(not math.isfinite(n) or n <= 0 for n in (research_seconds, inspect_seconds)):
        raise ValueError('実行ファイルと有限の正の制限秒数が必要です')
    if bool(journal_root) != bool(experiment_id):
        raise ValueError('journal-rootとexperiment-idは一緒に指定してください')
    if journal_run_stage is not None and (not journal_root or not experiment_id or not journal_run_stage):
        raise ValueError('journal-run-stageにはjournal-rootとexperiment-idが必要です')
    if journal_run_stage in {f'{stage_prefix}-inquiry', f'{stage_prefix}-inspect'}:
        raise ValueError('調査全体の工程IDは担当ごとの工程IDと分けてください')
    original = manifest(source)
    prior = discovery.report(source)
    if inspect_source is not None and not any(s['source_hash'] == inspect_source and s['kind'] == 'inquiry-result' for s in load_sources(source)):
        raise ValueError('照合だけを行う場合は保存済みの調査報告の識別値が必要です')
    selected = [r for r in discovery._reviews(source, revision) if digest(r) == review_hash]
    if len(selected) != 1:
        raise ValueError('対象改訂に対応する正式評価の識別値が必要です')
    review = selected[0]
    # AI_NOTE: 独自性調査の目的は判定条件から固定し、自由文の問いを文字列検索で選ばない。
    if question_index is None:
        if (revision != prior['revisions'][-1]['revision'] or review['value'] != 'test'
                or review['novelty'] not in {'unconfirmed', 'known'}):
            raise ValueError('独自性調査は最新の正式案のtestで、noveltyがunconfirmedまたはknownの評価が対象です')
        verify_submission(source, 'develop', revision)
        verify_submission(source, 'review', revision)
        question = NOVELTY_QUESTION
    else:
        if type(question_index) is not int or not 0 <= question_index < len(review['next_questions']):
            raise ValueError('範囲内の問い位置が必要です')
        question = review['next_questions'][question_index]
    focus = {'revision': revision, 'proposal_hash': review['proposal_hash'], 'review_hash': review_hash,
             'input_packet_hash': review['packet_hash'], 'question_index': question_index,
             'question': question}
    if question_index is None:
        # AI_NOTE: 先例ありの評価を未確認へ書き換えず、明示調査の出発点を区別する。
        focus['origin'] = 'known-use-prevalence' if review['novelty'] == 'known' else 'unconfirmed-novelty'
    output.mkdir(parents=True, exist_ok=False)
    result: dict[str, Any] = {'status': 'preparing', 'run_id': uuid.uuid4().hex, 'started_at': datetime.now(timezone.utc).isoformat(),
                              'source': str(source), 'output': str(output), 'focus': focus, 'stages': [], 'original_manifest': original,
                              'inspect_source': inspect_source, 'explicit_finish': explicit_finish,
                              'limits': '資料保存と問いの解決・種の有用性は別。公開操作の記録はOS全体の監査ではない。履歴本文に転記された過去判断までは自動除去しない。'}
    run_journal = InquiryJournal(journal_root, experiment_id, journal_run_stage) if journal_root and experiment_id and journal_run_stage else None
    try:
        if run_journal:
            try:
                result['journal_sync'] = run_journal.begin(result)
            except Exception as exc:
                result['journal_sync'] = {**result.get('journal_sync', run_journal.identity()),
                                          'status': 'failed', 'error': str(exc)}
                raise
        runtime = output / 'runtime'
        shutil.copytree(Path(__file__).resolve().parent, runtime / 'svdeck', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        runtime_before = manifest(runtime)
        base = output / 'input'
        copy_session(source, base)
        baseline = discovery.packet(base, revision, 'review')['data']
        input_before = manifest(base)
        previous = base
        # AI_NOTE: 保存済み資料からの照合は明示指定時だけ行い、調査を重複実行しない。
        stages = [('inspect', inspect_seconds)] if inspect_source is not None else [('inquiry', research_seconds), ('inspect', inspect_seconds)]
        for stage, seconds in stages:
            work = output / stage
            copy_session(previous, work / 'session', for_review=True)
            location = f"inquiry:{result['run_id']}:{stage}"
            kind = 'inquiry-result' if stage == 'inquiry' else 'inquiry-inspection'
            data = {**baseline, 'stage': stage, 'instruction': RESEARCH if stage == 'inquiry' else INSPECT,
                    'inquiry_focus': focus, 'inspect_source': inspect_source,
                    'sources': load_sources(work / 'session'), 'search': [],
                    'response_example': {'file': 'answer.md', 'kind': kind, 'location': location,
                                         'content': '問い・結論・実際の調査範囲/検索語・出典/確認時刻・取得本文と解釈・一致/相違・未確認'}}
            envelope = discovery._envelope(data)
            write_new(work / 'session/packets' / (envelope['sha256'] + '.json'), envelope)
            config = {'stage': stage, 'revision': revision, 'packet_hash': envelope['sha256'],
                      'author': f"worker:{result['run_id']}:{stage}", 'report_kind': kind, 'report_location': location,
                      'explicit_finish': explicit_finish}
            write_new(work / 'public-config.json', config)
            write_new(work / 'input-summary.json', packet_summary(work / 'session', envelope['sha256']))
            (work / 'public.py').write_text('import sys\nsys.dont_write_bytecode = True\nfrom pathlib import Path\nsys.path.insert(0, ' + repr(str(runtime)) + ')\nfrom svdeck.discovery_run import public_main\nraise SystemExit(public_main(Path(__file__).resolve().parent))\n')
            # AI_NOTE: 調査担当にも監視側と同じ残り時間の確認方法を示し、UTC差との混同を避ける。
            prompt = f'''{data['instruction']}

今回の問い: {focus['question']}
今回照合する保存済み報告の識別値: {inspect_source or 'この実行の調査工程が保存した報告'}。
参照元: 改訂{revision} / 評価{review_hash} / {f'問い位置{question_index}（0始まり）' if question_index is not None else '同用途の先例ありとされた試用評価から設定した固定の調査目的' if review['novelty'] == 'known' else '独自性未確認の試用評価から設定した固定の調査目的'}。
今回は{stage}を1回だけ、待ち時間込みの経過{seconds:g}秒まで行います。担当ID: {config['author']}。
上限は監視側の経過時計で判定します。残り秒は次で確認できます: {sys.executable} -c "import os,time; print(float(os.environ['SVDECK_DEADLINE_MONOTONIC']) - time.monotonic())"
UTCの開始・終了も記録しますが、その時刻差だけで期限切れと判定しません。PC休止等の扱いはOSに依存し、時計差があれば両方の値と未確認の原因を報告します。終了前に提出・保存を済ませてください。
作業先外、親会話、実装、別探索、私的な実行ログは読みません。入力は直接開かず公開入口で読んでください。
{sys.executable} public.py packet --summary
{sys.executable} public.py read {envelope['sha256']} SECTION --offset 0 --limit 20
案はproposal、カードはcards、問いはpacket_metadataで読めます。既存資料は最初にsource_indexで必要な資料の場所を選び、示されたsource:HASHで本文だけを読んでください。資料は保存内容であり、正しさの保証ではありません。
必要な出典はattach又はattach-fileで保存してください。検索語とURL・確認時刻・実際に見た内容を公開資料へ残し、内部の思考過程は転記しません。
最後の結論を作業先のanswer.mdにUTF-8で書き、次の形式で資料へ保存します。観察時刻や限界は実際に合わせて追記できます。
{sys.executable} public.py attach-file answer.md --title '指定した問いへの報告' --kind {kind} --location {location}
保存後にpacket --summaryを再実行し、新しい識別値のsource_indexで報告の資料HASHを確認して、そのsource:HASHだけをreadで全文読み直してください。offsetとlimitで必要範囲を分けられます。
全ての追加資料を保存し終えてから、最後にreportを実行してください。その後に資料を追加保存した場合はreportを再実行してください。
{sys.executable} public.py report
正式改訂・評価の提出は行いません。報告を保存できなかった場合は代理提出を求めず、final-messageに未完了の事実を記してください。
調査報告の保存と問いを解決できたかは別です。最終回答は保存資料の識別値と結論・未確認だけを短く記してください。
'''
            if explicit_finish:
                prompt += f'answer.mdの公開添付・新版からの全文再読・最新reportを終え、これ以上保存内容を変えない段階で {sys.executable} public.py finish を実行してください。受付後は保存内容を変更できません。監視側が停止と再検査を行い、公開資料から成果を回収します。\n'
            (work / 'prompt.md').write_text(prompt)
            fixed = manifest(work)
            if explicit_finish:
                protected = {str(source): original, str(base): input_before, str(runtime): runtime_before}
                if previous != base:
                    protected[str(previous)] = manifest(previous)
                contract: dict[str, Any] = {'fixed': fixed, 'protected': protected}
                write_new(work / 'finish-config.json', contract)
                (work / '.public.lock').touch()
                fixed = manifest(work)
                contract = {**contract, 'fixed': fixed}
            result['status'] = stage
            worker.save_record(output / 'result.json', result)
            journal = RunJournal(journal_root, experiment_id, f'{stage_prefix}-{stage}') if journal_root and experiment_id else None
            command = [str(codex), '--search', 'exec', '--ephemeral', '--sandbox', 'workspace-write', '--skip-git-repo-check',
                       '--cd', str(work), '--json', '--output-last-message', str(work / 'final-message.md'), '-']
            if explicit_finish:
                code, execution = worker.run(command, output / (stage + '-run'), seconds, 2, work,
                                             work / 'prompt.md', 'elapsed', journal, lambda: poll_finish(work, contract))
            else:
                code, execution = worker.run(command, output / (stage + '-run'), seconds, 2, work, work / 'prompt.md', 'elapsed', journal)
            result['stages'].append({'stage': stage, 'author': config['author'], 'returncode': code, 'run': execution})
            check_unchanged(source, original, exact=True)
            check_unchanged(base, input_before, exact=True)
            check_unchanged(runtime, runtime_before, exact=True)
            check_unchanged(work, fixed)
            if explicit_finish and previous != base:
                # AI_NOTE: 次担当がfinishなしで自然終了しても、完了済み調査の資料を封じたまま保持する。
                check_unchanged(previous, contract['protected'][str(previous)], exact=True)
            if code != 0 or execution['status'] not in ({'completed', 'finished_by_request'} if explicit_finish else {'completed'}):
                result.update(status=stage + '_failed', failure='担当が完了していないため次へ進みません')
                break
            if explicit_finish:
                finished = check_finish(work, contract)
                if execution['status'] == 'finished_by_request' and finished is None:
                    raise ValueError('監視側が受理した終了要求が見つかりません')
            expected_revisions = {name for name in fixed if name.startswith('session/revision-')}
            actual_revisions = {'session/' + p.name for p in (work / 'session').glob('revision-*.json')}
            if actual_revisions != expected_revisions or list((work / 'session').glob('review-*.json')):
                raise ValueError('調査担当は案の改訂・正式評価を追加できません')
            if not (work / 'answer.md').is_file():
                result.update(status=stage + '_missing', failure='担当は終了しましたがanswer.mdがありません')
                break
            result['stages'][-1]['submission'] = verify_report(work, config)
            write_new(output / (stage + '-report.json'), discovery.report(work / 'session'))
            previous = work / 'session'
        if result['status'] == 'inspect':
            destination = output / 'session'
            copy_session(base, destination)
            for path in previous.rglob('*.json'):
                relative = path.relative_to(previous)
                if relative.parts[0] not in {'sources', 'packets'}:
                    continue
                target = destination / relative
                if target.exists():
                    if target.read_bytes() != path.read_bytes():
                        raise ValueError('同じ名前の保存資料が異なります')
                else:
                    target.parent.mkdir(exist_ok=True)
                    shutil.copyfile(path, target)
            check_unchanged(destination, input_before)
            report = discovery.report(destination)
            if report['revisions'] != prior['revisions']:
                # 追加資料により変わる評価資料との差分だけは許し、判断本文は保持する。
                for before, after in zip(prior['revisions'], report['revisions'], strict=True):
                    if {k: v for k, v in before.items() if k != 'review_contexts'} != {k: v for k, v in after.items() if k != 'review_contexts'}:
                        raise ValueError('元案・旧評価の本文が変更されました')
            write_new(output / 'report.json', report)
            result.update(status='completed', session=str(destination), source_unchanged=True,
                          formal_revisions=0, formal_reviews=0, additional_sources=len(report['sources']) - len(prior['sources']))
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        result.update(status='failed', failure=str(exc))
    except BaseException as exc:
        if run_journal:
            result.update(status='failed', failure=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        result['ended_at'] = datetime.now(timezone.utc).isoformat()
        if run_journal and result.get('journal_sync', {}).get('claimed_stage'):
            try:
                result['journal_sync'] = run_journal.finish(result)
            except Exception as exc:
                result['journal_sync'] = {**result['journal_sync'], 'status': 'failed', 'error': str(exc)}
        worker.save_record(output / 'result.json', result)
    return result


def main(argv: list[str] | None = None) -> int:
    # AI_NOTE: 問いと各工程の制限を明示指定し、失敗結果も保存先から追えるようにする。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--codex', type=Path, required=True)
    parser.add_argument('--revision', type=int, required=True)
    parser.add_argument('--review-hash', required=True)
    focus = parser.add_mutually_exclusive_group(required=True)
    focus.add_argument('--question-index', type=int)
    focus.add_argument('--novelty', action='store_true', help='最新改訂のtest評価（unconfirmedまたはknown）から、使い方の先例と普及を調査する')
    parser.add_argument('--research-seconds', type=float, required=True)
    parser.add_argument('--inspect-seconds', type=float, required=True)
    parser.add_argument('--journal-root', type=Path)
    parser.add_argument('--experiment-id')
    parser.add_argument('--stage-prefix', default='live')
    parser.add_argument('--journal-run-stage', help='最終提出検査までの全実行を記録する、事前登録済みの未着手工程ID')
    parser.add_argument('--inspect-source', help='保存済みinquiry-result資料を指定し、調査を再実行せず照合だけを行う')
    parser.add_argument('--explicit-finish', action='store_true', help='公開添付・全文再読・最新report後のfinishを監視側が検査して終了させる任意方式')
    args = parser.parse_args(argv)
    try:
        result = run(args.session, args.output, args.codex, args.revision, args.review_hash, args.question_index,
                     args.research_seconds, args.inspect_seconds, args.journal_root, args.experiment_id, args.stage_prefix,
                     args.inspect_source, args.journal_run_stage, explicit_finish=args.explicit_finish)
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps({k: v for k, v in result.items() if k not in {'stages', 'original_manifest'}}, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'completed' and result.get('journal_sync', {}).get('status') != 'failed' else 2


if __name__ == '__main__':
    sys.exit(main())
