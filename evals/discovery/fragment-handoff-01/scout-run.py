"""Experimental shared fragment collection; no proposal, ranking, or review is produced.

python scout-run.py SOURCE OUTPUT --codex PATH --seconds 300
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import sqlite3
import sys
from typing import Any
import uuid

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from svdeck import discovery, worker
from svdeck.discovery_evidence import read_object, write_new
from svdeck.discovery_inquiry import inquiry_finish_evidence
from svdeck.discovery_read import packet_summary
from svdeck.discovery_run import check_finish, check_unchanged, copy_session, manifest, poll_finish
from svdeck.worker_journal import RunJournal


PURPOSE = '固定資料から、役割または副作用の異なる未完成な着想を最大3件だけ、出典付きで集める。'
INSTRUCTION = '''新規探索の共通前段を担当します。完成案を選ぶ前の未完成な着想を最大3件だけ集めてください。
カード名や答えは指定しません。固定カード本文・両側の注記・出典を公開入口から必要な範囲で読んでください。
各着想は次の5項目でanswer.mdに保存します。
1. ID: 機械的な識別子（例: fragment-1）。番号は順位ではありません。
2. 出典付き効果: カードID・field・実際のquoteを添え、取得本文と自分の解釈を分ける。
3. 効果の後に残る/減るもの: 対象集合や使える時点の変化も含め、二重計上しない。
4. 使えそうな役割: この構築で何を担当できそうか。強さの採点はしない。
5. 今は困る条件一つ: 今の構築では役に立たない条件と根拠。未知なら未知と書く。
役割や副作用の異なる着想を残し、完成案・順位・採否・優劣・強さの採点は付けません。
3件に届かなくても創作で埋めず、0〜3件の実数と未確認事項を残します。出典のない効果を作りません。
正式な案や評価を提出せず、カード・元資料・固定入力・実装を書き換えません。
資料の保存成功と着想の正しさ・有用性は別です。内容の判断は後続工程へ渡します。'''


def run(source: Path, output: Path, codex: Path, seconds: float,
        journal_root: Path | None = None, experiment_id: str | None = None,
        stage_id: str | None = None) -> dict[str, Any]:
    # AI_NOTE: 正式案のない入力だけを複製し、断片収集は既存の公開資料提出・停止検査へ接続する。
    source, output, codex = source.resolve(), output.resolve(), codex.resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('元探索と出力先は互いの内側へ置けません')
    if not codex.is_file() or not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('実行ファイルと有限の正の制限秒数が必要です')
    if any(x is not None for x in (journal_root, experiment_id, stage_id)) and not all((journal_root, experiment_id, stage_id)):
        raise ValueError('journal-root・experiment-id・stage-idは一緒に指定してください')
    original = manifest(source)
    prior = discovery.report(source)
    if prior['revisions'] or list(source.glob('revision-*.json')) or list(source.glob('review-*.json')):
        raise ValueError('正式改訂・正式評価が0件の新規探索だけが対象です')
    output.mkdir(parents=True, exist_ok=False)
    result: dict[str, Any] = {
        'status': 'preparing', 'started_at': datetime.now(timezone.utc).isoformat(), 'ended_at': None,
        'run_id': uuid.uuid4().hex, 'source': str(source), 'output': str(output), 'seconds': seconds,
        'source_manifest': original, 'runtime_manifest': None, 'run': None, 'submission': None,
        'limits': '実験用の共通前段。最大3件・項目・出典の意味的な充足は別途点検する。保存成功は着想の正しさ・有用性ではない。'}
    try:
        runtime = output / 'runtime'
        shutil.copytree(Path(discovery.__file__).resolve().parent, runtime / 'svdeck',
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        result['runtime_manifest'] = manifest(runtime)
        work = output / 'inquiry'
        copy_session(source, work / 'session')
        baseline = discovery.packet(work / 'session', 0, 'develop')['data']
        location = f"experiment-fragments:{result['run_id']}"
        data = {**baseline, 'stage': 'inquiry', 'instruction': INSTRUCTION, 'proposal': None,
                'previous_reviews': [], 'review_contexts': [],
                'inquiry_focus': {'question': PURPOSE, 'origin': 'experiment-fragments'},
                'response_example': {'file': 'answer.md', 'kind': 'inquiry-result', 'location': location,
                                     'content': '実数0〜3件。各件はID・出典付き効果・残る/減るもの・使えそうな役割・今は困る条件一つ。順位・採否なし。'}}
        envelope = discovery._envelope(data)
        write_new(work / 'session/packets' / (envelope['sha256'] + '.json'), envelope)
        config = {'stage': 'inquiry', 'revision': 0, 'packet_hash': envelope['sha256'],
                  'author': f"worker:{result['run_id']}:inquiry", 'report_kind': 'inquiry-result',
                  'report_location': location, 'explicit_finish': True}
        write_new(work / 'public-config.json', config)
        write_new(work / 'input-summary.json', packet_summary(work / 'session', envelope['sha256']))
        (work / 'public.py').write_text('import sys\nsys.dont_write_bytecode = True\nfrom pathlib import Path\nsys.path.insert(0, '
                                      + repr(str(runtime)) + ')\nfrom svdeck.discovery_run import public_main\nraise SystemExit(public_main(Path(__file__).resolve().parent))\n')
        prompt = f'''{INSTRUCTION}

今回の目的: {PURPOSE}
担当ID: {config['author']}。経過{seconds:g}秒までです。待ち時間と公開保存・終了操作を含みます。
残り秒: {sys.executable} -c "import os,time; print(float(os.environ['SVDECK_DEADLINE_MONOTONIC']) - time.monotonic())"
作業先外・親会話・別探索・実装・私的stdoutやJSONLや思考ログは読みません。入力は直接開かず公開入口で読みます。
{sys.executable} public.py packet --summary
{sys.executable} public.py read {envelope['sha256']} SECTION --offset 0 --limit 20
カードはcards、原則はprinciples、既存資料はsources、目的はpacket_metadataで読めます。必要範囲はoffset/limitで分けます。
追加の出典は公開attach又はattach-fileで保持します。取得本文と解釈、未確認を分け、内部の思考過程を転記しません。
0〜3件の着想と実件数を作業先のanswer.mdへUTF-8で書き、次を実行します。
{sys.executable} public.py attach-file answer.md --title '共通前段の未完成な着想' --kind inquiry-result --location {location}
{sys.executable} public.py packet --summary
新版の識別値のsourcesをreadし、添付したanswer.mdの全文を読み直してください。全資料の再読は不要です。
全ての出典と報告を保存し終えてから最後にreportを実行します。後から資料を追加したらreportを再実行してください。
{sys.executable} public.py report
公開添付・新版からの全文再読・最新reportを終え、保存内容をこれ以上変えない段階で次を実行してください。
{sys.executable} public.py finish
受付後は保存内容を変えません。監視側が停止と再検査を行います。提出できなければ代理提出を求めず未完了の事実を残します。
'''
        (work / 'prompt.md').write_text(prompt)
        fixed = manifest(work)
        contract: dict[str, Any] = {'fixed': fixed, 'protected': {str(source): original, str(runtime): result['runtime_manifest']}}
        write_new(work / 'finish-config.json', contract)
        (work / '.public.lock').touch()
        contract = {**contract, 'fixed': manifest(work)}
        result.update(status='running', work=str(work), packet_hash=envelope['sha256'], author=config['author'])
        worker.save_record(output / 'result.json', result)
        journal = RunJournal(journal_root, experiment_id, stage_id) if journal_root and experiment_id and stage_id else None
        command = [str(codex), '--search', 'exec', '--ephemeral', '--sandbox', 'workspace-write', '--skip-git-repo-check',
                   '--cd', str(work), '--json', '--output-last-message', str(work / 'final-message.md'), '-']
        code, execution = worker.run(command, output / 'inquiry-run', seconds, 2, work, work / 'prompt.md',
                                     'elapsed', journal, lambda: poll_finish(work, contract))
        result.update(run=execution, returncode=code)
        check_unchanged(source, original, exact=True)
        check_unchanged(runtime, result['runtime_manifest'], exact=True)
        check_unchanged(work, contract['fixed'])
        if code != 0 or execution['status'] not in {'completed', 'finished_by_request'}:
            result.update(status=execution['status'] if code != 0 and execution['status'] not in {'completed', 'finished_by_request'} else 'failed',
                          failure='担当の実行が完了していないため資料を完成出力へ移しません')
            return result
        if list((work / 'session').glob('revision-*.json')) or list((work / 'session').glob('review-*.json')):
            raise ValueError('共通前段は正式な案・評価を追加できません')
        finished = check_finish(work, contract)
        if execution['status'] == 'finished_by_request' and finished is None:
            raise ValueError('監視側が受理した終了要求が見つかりません')
        if not (work / 'answer.md').is_file():
            result.update(status='missing', failure='担当は終了しましたがanswer.mdがありません')
            return result
        pinned = read_object(work / 'finish-request.json') if finished is not None else None
        evidence = inquiry_finish_evidence(work, contract, pinned)
        result.update(submission=evidence['submission'], evidence=evidence)
        destination = output / 'session'
        copy_session(work / 'session', destination)
        check_unchanged(destination, evidence['session_manifest'], exact=True)
        report = discovery.report(destination)
        if report['revisions']:
            raise ValueError('共通前段の完成出力へ正式案を含められません')
        write_new(output / 'report.json', report)
        # AI_NOTE: 成果の複製後も終了時の同じ証拠で確認し、保存操作の存在だけで完了へ進めない。
        if inquiry_finish_evidence(work, contract, evidence) != evidence or check_finish(work, contract) != finished:
            raise ValueError('完成出力の保存中に終了証拠が変更されました')
        result.update(status='completed', session=str(destination), report=report, source_unchanged=True,
                      formal_revisions=0, formal_reviews=0)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        result.update(status='failed', failure=str(exc))
    except BaseException as exc:
        result.update(status='failed', failure=f'{type(exc).__name__}: {exc}')
        raise
    finally:
        result['ended_at'] = datetime.now(timezone.utc).isoformat()
        worker.save_record(output / 'result.json', result)
    return result


def main(argv: list[str] | None = None) -> int:
    # AI_NOTE: 実験用入口の保存先と制限だけを受け、台帳接続を指定する場合は一組で検査する。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--codex', type=Path, required=True)
    parser.add_argument('--seconds', type=float, required=True)
    parser.add_argument('--journal-root', type=Path)
    parser.add_argument('--experiment-id')
    parser.add_argument('--stage-id')
    args = parser.parse_args(argv)
    try:
        result = run(args.source, args.output, args.codex, args.seconds, args.journal_root, args.experiment_id, args.stage_id)
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        parser.error(str(exc))
    print(json.dumps({k: v for k, v in result.items() if k not in {'run', 'source_manifest', 'runtime_manifest', 'report', 'evidence'}}, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'completed' else 2


if __name__ == '__main__':
    sys.exit(main())
