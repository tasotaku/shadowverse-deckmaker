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
from svdeck.discovery_run import check_packet, check_unchanged, copy_session, manifest
from svdeck.discovery_sources import load_sources
from svdeck.worker_journal import RunJournal


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


def verify_report(work: Path, config: dict[str, Any]) -> dict[str, Any]:
    # AI_NOTE: 報告ファイルだけで完了にせず、公開添付・新版への反映・全本文の再読を保存物と照合する。
    session = work / 'session'
    raw = (work / 'answer.md').read_bytes()
    matches = [s for s in load_sources(session) if s['kind'] == config['report_kind'] and s['location'] == config['report_location']]
    if len(matches) != 1 or matches[0]['content'] != raw.decode('utf-8'):
        raise ValueError('answer.mdと一致する正式な調査・照合資料が1件必要です')
    source = matches[0]
    operations = sorted((read_object(p) for p in (work / 'operations').glob('*.json')), key=lambda x: x['started_at'])
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
            if value['section'] != 'sources':
                continue
            packet = discovery._read_envelope(session / 'packets' / (value['sha256'] + '.json'))
            fixed = discovery._read_envelope(session / 'packets' / (config['packet_hash'] + '.json'))
            check_packet(session, packet, fixed)
            if source not in packet['sources']:
                continue
            observed = read_packet(session, value['sha256'], 'sources', value['offset'], value['limit'])
            if value != observed:
                raise ValueError('公開再読の記録が保存本文と一致しません')
            seen = covered.setdefault(value['sha256'], set())
            seen.update(range(value['offset'], value['offset'] + len(value['content'])))
            # sourcesは整形JSONの行。対象資料の範囲だけを必須にし、全資料の再読は強制しない。
            lines = json.dumps([{**s, 'content': s['content'].splitlines(keepends=True)} for s in packet['sources']], ensure_ascii=False, indent=2).splitlines(keepends=True)
            start = sum(len(json.dumps({**s, 'content': s['content'].splitlines(keepends=True)}, ensure_ascii=False, indent=2).splitlines()) for s in packet['sources'][:packet['sources'].index(source)]) + 1
            length = len(json.dumps({**source, 'content': source['content'].splitlines(keepends=True)}, ensure_ascii=False, indent=2).splitlines())
            if start + length > len(lines):
                raise ValueError('再読範囲の計算が資料の行数を超えています')
            if set(range(start, start + length)) <= seen:
                covered['complete'] = {1}
    if not attached or not reports or not covered.get('complete'):
        raise ValueError('answer.mdの公開添付、新しい資料版からの全文再読、report確認が必要です')
    return {'source_hash': source['source_hash'], 'file_sha256': hashlib.sha256(raw).hexdigest(),
            'public_attachment': True, 'public_reread': True, 'report_read': True}


def run(source: Path, output: Path, codex: Path, revision: int, review_hash: str, question_index: int,
        research_seconds: float, inspect_seconds: float, journal_root: Path | None = None,
        experiment_id: str | None = None, stage_prefix: str = 'live',
        inspect_source: str | None = None) -> dict[str, Any]:
    # AI_NOTE: 調査と照合を資料提出としてつなぎ、元案・旧評価は最終出力まで保持する。
    source, output, codex = source.resolve(), output.resolve(), codex.resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('元探索と出力先は互いの内側へ置けません')
    if not codex.is_file() or any(not math.isfinite(n) or n <= 0 for n in (research_seconds, inspect_seconds)):
        raise ValueError('実行ファイルと有限の正の制限秒数が必要です')
    if bool(journal_root) != bool(experiment_id):
        raise ValueError('journal-rootとexperiment-idは一緒に指定してください')
    original = manifest(source)
    prior = discovery.report(source)
    if inspect_source is not None and not any(s['source_hash'] == inspect_source and s['kind'] == 'inquiry-result' for s in load_sources(source)):
        raise ValueError('照合だけを行う場合は保存済みの調査報告の識別値が必要です')
    selected = [r for r in discovery._reviews(source, revision) if digest(r) == review_hash]
    if len(selected) != 1 or type(question_index) is not int or not 0 <= question_index < len(selected[0]['next_questions']):
        raise ValueError('対象改訂の評価識別値と範囲内の問い位置が必要です')
    review = selected[0]
    focus = {'revision': revision, 'proposal_hash': review['proposal_hash'], 'review_hash': review_hash,
             'input_packet_hash': review['packet_hash'], 'question_index': question_index,
             'question': review['next_questions'][question_index]}
    output.mkdir(parents=True, exist_ok=False)
    result: dict[str, Any] = {'status': 'preparing', 'run_id': uuid.uuid4().hex, 'started_at': datetime.now(timezone.utc).isoformat(),
                              'source': str(source), 'output': str(output), 'focus': focus, 'stages': [], 'original_manifest': original,
                              'inspect_source': inspect_source,
                              'limits': '資料保存と問いの解決・種の有用性は別。公開操作の記録はOS全体の監査ではない。履歴本文に転記された過去判断までは自動除去しない。'}
    try:
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
                      'author': f"worker:{result['run_id']}:{stage}", 'report_kind': kind, 'report_location': location}
            write_new(work / 'public-config.json', config)
            write_new(work / 'input-summary.json', packet_summary(work / 'session', envelope['sha256']))
            (work / 'public.py').write_text('import sys\nsys.dont_write_bytecode = True\nfrom pathlib import Path\nsys.path.insert(0, ' + repr(str(runtime)) + ')\nfrom svdeck.discovery_run import public_main\nraise SystemExit(public_main(Path(__file__).resolve().parent))\n')
            prompt = f'''{data['instruction']}

今回の問い: {focus['question']}
今回照合する保存済み報告の識別値: {inspect_source or 'この実行の調査工程が保存した報告'}。
参照元: 改訂{revision} / 評価{review_hash} / 問い位置{question_index}（0始まり）。
今回は{stage}を1回だけ、待ち時間込みの経過{seconds:g}秒まで行います。担当ID: {config['author']}。
作業先外、親会話、実装、別探索、私的な実行ログは読みません。入力は直接開かず公開入口で読んでください。
{sys.executable} public.py packet --summary
{sys.executable} public.py read {envelope['sha256']} SECTION --offset 0 --limit 20
案はproposal、カードはcards、問いはpacket_metadata、既存資料はsourcesで読めます。資料は保存内容であり、正しさの保証ではありません。
必要な出典はattach又はattach-fileで保存してください。検索語とURL・確認時刻・実際に見た内容を公開資料へ残し、内部の思考過程は転記しません。
最後の結論を作業先のanswer.mdにUTF-8で書き、次の形式で資料へ保存します。観察時刻や限界は実際に合わせて追記できます。
{sys.executable} public.py attach-file answer.md --title '指定した問いへの報告' --kind {kind} --location {location}
保存後にpacket --summaryを再実行し、新しい識別値のsourcesから自分の報告の全文をreadで読み直してください。offsetとlimitで必要範囲を分けられます。全資料の再読は不要です。
{sys.executable} public.py report
正式改訂・評価の提出は行いません。報告を保存できなかった場合は代理提出を求めず、final-messageに未完了の事実を記してください。
調査報告の保存と問いを解決できたかは別です。最終回答は保存資料の識別値と結論・未確認だけを短く記してください。
'''
            (work / 'prompt.md').write_text(prompt)
            fixed = manifest(work)
            result['status'] = stage
            worker.save_record(output / 'result.json', result)
            journal = RunJournal(journal_root, experiment_id, f'{stage_prefix}-{stage}') if journal_root and experiment_id else None
            command = [str(codex), '--search', 'exec', '--ephemeral', '--sandbox', 'workspace-write', '--skip-git-repo-check',
                       '--cd', str(work), '--json', '--output-last-message', str(work / 'final-message.md'), '-']
            code, execution = worker.run(command, output / (stage + '-run'), seconds, 2, work, work / 'prompt.md', 'elapsed', journal)
            result['stages'].append({'stage': stage, 'author': config['author'], 'returncode': code, 'run': execution})
            check_unchanged(source, original, exact=True)
            check_unchanged(base, input_before, exact=True)
            check_unchanged(runtime, runtime_before, exact=True)
            check_unchanged(work, fixed)
            if code != 0 or execution['status'] != 'completed':
                result.update(status=stage + '_failed', failure='担当が完了していないため次へ進みません')
                break
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
    finally:
        result['ended_at'] = datetime.now(timezone.utc).isoformat()
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
    parser.add_argument('--question-index', type=int, required=True)
    parser.add_argument('--research-seconds', type=float, required=True)
    parser.add_argument('--inspect-seconds', type=float, required=True)
    parser.add_argument('--journal-root', type=Path)
    parser.add_argument('--experiment-id')
    parser.add_argument('--stage-prefix', default='live')
    parser.add_argument('--inspect-source', help='保存済みinquiry-result資料を指定し、調査を再実行せず照合だけを行う')
    args = parser.parse_args(argv)
    try:
        result = run(args.session, args.output, args.codex, args.revision, args.review_hash, args.question_index,
                     args.research_seconds, args.inspect_seconds, args.journal_root, args.experiment_id, args.stage_prefix,
                     args.inspect_source)
    except (OSError, ValueError, KeyError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps({k: v for k, v in result.items() if k not in {'stages', 'original_manifest'}}, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'completed' else 2


if __name__ == '__main__':
    sys.exit(main())
