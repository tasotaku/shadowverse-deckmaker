"""Prepare isolated A/B runtimes from one completed shared scout; never launch AI.

python prepare-arms.py SOURCE OUTPUT [--scout-result RESULT] [--protocol PROTOCOL]
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / 'src'))
from svdeck import discovery
from svdeck.discovery_evidence import digest, read_object, write_new
from svdeck.discovery_inquiry import inquiry_finish_evidence
from svdeck.discovery_run import check_finish, check_unchanged, copy_session, manifest
from svdeck.discovery_sources import load_sources


BRIDGE = '''不足を引き受ける接続を一度行ったら、変更前/引受/変更後/代償/選択を作業先のbridge.mdへ根拠付きで書いてください。
引受側の必要札・条件への到達経路・失う用途も代償へ残します。役立つ接続がなければ不成立と通常選択へ戻った事実を残します。
正式提出前に public.py attach-file bridge.md --title '着想の不足を引き受けた記録' --kind experiment-bridge --location fragment-handoff:bridge で公開保存してください。
その後public.py packetで新版を取得し、同じfinish_from_sourceの下で正式案1件へまとめます。'''


def prepare(source: Path, output: Path, scout_result: Path, protocol_path: Path) -> dict[str, Any]:
    # AI_NOTE: 共通収集の最終証拠で入力を固定し、実験の指示差だけを隔離runtimeへ追加する。
    source, output = source.resolve(), output.resolve()
    scout_result, protocol_path = scout_result.resolve(), protocol_path.resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('共通入力と出力先は互いの内側へ置けません')
    original = manifest(source)
    saved = read_object(scout_result)
    if (saved.get('status') != 'completed' or saved.get('returncode') != 0
            or saved.get('formal_revisions') != 0 or saved.get('formal_reviews') != 0
            or saved.get('run', {}).get('status') not in {'completed', 'finished_by_request'}):
        raise ValueError('完了済みで正式案・評価0件の共通収集resultとsessionが必要です')
    completed_source = Path(saved['session']).resolve()
    if manifest(completed_source) != saved['evidence']['session_manifest'] or discovery.report(completed_source) != saved['report']:
        raise ValueError('共通sessionが収集完了時の証拠と一致しません')
    # AI_NOTE: 収集完了版を保持した別コピーへ参考資料を追記しても、着想報告と固定入力は取り替えない。
    check_unchanged(source, saved['evidence']['session_manifest'])
    added_paths = set(original) - set(saved['evidence']['session_manifest'])
    if (any(Path(name).parts[0] not in {'sources', 'packets'} for name in added_paths)
            or discovery.report(source)['revisions'] or list(source.glob('review-*.json'))):
        raise ValueError('共有sourceへ追加できるのは資料とそのpacketだけです')
    work = Path(saved['work'])
    contract = read_object(work / 'finish-config.json')
    if inquiry_finish_evidence(work, contract, saved['evidence']) != saved['evidence']:
        raise ValueError('共通収集の公開提出証拠が一致しません')
    finished = check_finish(work, contract)
    if saved['run']['status'] == 'finished_by_request' and finished is None:
        raise ValueError('共通収集の終了要求が失われています')
    if saved['submission'] != saved['evidence']['submission']:
        raise ValueError('共通報告の識別値が完了時の公開提出証拠と一致しません')
    key = saved['submission']['source_hash']
    selected = [s for s in load_sources(source) if s['source_hash'] == key and s['kind'] == 'inquiry-result'
                and s['location'] == f"experiment-fragments:{saved['run_id']}"]
    if len(selected) != 1:
        raise ValueError('今回の収集完了が指す最新のinquiry-resultが1件必要です')
    protocol = read_object(protocol_path)
    if protocol['id'] != 'fragment-handoff-01' or set(protocol['arms']) != {'A', 'B'}:
        raise ValueError('fragment-handoff-01のA/B条件が必要です')
    module_path = Path(discovery.__file__).resolve()
    module = module_path.read_text()
    tails = [ast.literal_eval(node.value) for node in ast.parse(module).body
             if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name) and node.target.id == 'DEVELOP'
             and isinstance(node.op, ast.Add) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)]
    if len(tails) != 1 or not discovery.DEVELOP.endswith(tails[0]) or '同じ終点' not in tails[0]:
        raise ValueError('現行DEVELOP末尾の同状態比較文を一意に確認できません')
    comparison = tails[0]
    common = discovery.FINISH + '\n' + comparison + '\n' + protocol['arms']['A'] + '\n'
    instructions = {'A': common, 'B': common + protocol['arms']['B'] + '\n' + BRIDGE + '\n'}
    marker = 'if __name__ == "__main__":'
    if module.count(marker) != 1:
        raise ValueError('discoveryの公開入口の挿入位置が一意ではありません')
    output.mkdir(parents=True, exist_ok=False)
    launch: dict[str, Any] = {'status': 'preparing', 'started_at': datetime.now(timezone.utc).isoformat(),
        'source': str(source), 'source_manifest': original, 'scout_result': str(scout_result),
        'completed_scout_session': str(completed_source), 'additional_input_files': sorted(added_paths),
        'scout_result_sha256': hashlib.sha256(scout_result.read_bytes()).hexdigest(), 'finish_from_source': key,
        'protocol': str(protocol_path), 'protocol_hash': digest(protocol), 'comparison': comparison,
        'original_review': discovery.REVIEW, 'arms': {}}
    try:
        packets: dict[str, Any] = {}
        runtimes: dict[str, dict[str, str]] = {}
        for arm, instruction in instructions.items():
            folder = output / arm
            arm_source = folder / 'source'
            copy_session(source, arm_source)
            check_unchanged(arm_source, original, exact=True)
            runtime = folder / 'runtime'
            shutil.copytree(module_path.parent, runtime / 'svdeck', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            wrapper = f'''# AI_NOTE: 実験用の考案だけ資料を固定し、通常の評価とその指示は変更しない。
FINISH = {instruction!r}
_fragment_original_packet = packet

def _fragment_packet(session: Path, revision: int | None, stage: str, finish_from_source: str | None = None) -> JSONDict:
    if stage == "develop":
        if finish_from_source not in (None, {key!r}):
            raise ValueError("実験用のfinish_from_sourceは共通資料に固定されています")
        finish_from_source = {key!r}
    return _fragment_original_packet(session, revision, stage, finish_from_source)

packet = _fragment_packet

'''
            (runtime / 'svdeck/discovery.py').write_text(module.replace(marker, wrapper + marker))
            runtimes[arm] = manifest(runtime)
            check_session = folder / 'check-session'
            copy_session(source, check_session)
            environment = {'PYTHONPATH': str(runtime), 'PYTHONDONTWRITEBYTECODE': '1'}
            probe = 'from pathlib import Path; import json,sys; from svdeck import discovery as d; print(json.dumps({"packet":d.packet(Path(sys.argv[1]),0,"develop"),"review":d.REVIEW},ensure_ascii=False))'
            checked = subprocess.run([sys.executable, '-c', probe, str(check_session)], cwd=folder,
                                     env={**os.environ, **environment}, capture_output=True, text=True, check=True)
            observed = json.loads(checked.stdout)
            packet = observed['packet']
            if observed['review'] != discovery.REVIEW or packet['data']['instruction'] != instruction or packet['data']['finish_from_source'] != key:
                raise ValueError('実packetの指示・固定資料・通常評価が準備条件と一致しません')
            packets[arm] = packet
            launch['arms'][arm] = {'source': str(arm_source), 'runtime': str(runtime), 'output': str(folder / 'run'),
                'environment': environment, 'runtime_manifest': runtimes[arm], 'instruction': instruction,
                'checked_packet_hash': packet['sha256'], 'command': [sys.executable, '-m', 'svdeck.discovery_run',
                    str(arm_source), str(folder / 'run'), '--codex', 'CODEX_PATH',
                    '--develop-seconds', str(protocol['develop_seconds_each']), '--review-seconds', str(protocol['review_seconds_each']), '--explicit-finish']}
        if {k: v for k, v in packets['A']['data'].items() if k != 'instruction'} != {k: v for k, v in packets['B']['data'].items() if k != 'instruction'}:
            raise ValueError('A/Bの実packetに意図した指示以外の差があります')
        if {k: v for k, v in runtimes['A'].items() if k != 'svdeck/discovery.py'} != {k: v for k, v in runtimes['B'].items() if k != 'svdeck/discovery.py'}:
            raise ValueError('A/Bの実装に意図した変更以外の差があります')
        a = (output / 'A/runtime/svdeck/discovery.py').read_text()
        b = (output / 'B/runtime/svdeck/discovery.py').read_text()
        if a.replace(repr(instructions['A']), 'FRAGMENT_INSTRUCTION', 1) != b.replace(repr(instructions['B']), 'FRAGMENT_INSTRUCTION', 1):
            raise ValueError('A/Bの実装差が指示文だけではありません')
        check_unchanged(source, original, exact=True)
        for arm in instructions:
            check_unchanged(output / arm / 'source', original, exact=True)
            check_unchanged(output / arm / 'runtime', runtimes[arm], exact=True)
        launch.update(status='prepared', assertions={'same_source': True, 'packet_difference_only_instruction': True,
            'runtime_difference_only_instruction': True, 'normal_review_unchanged': True},
            limits='準備と合成検査のみ。実AIは起動していない。内容の有用性・方法の優位は別検証。')
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        launch.update(status='failed', failure=str(exc))
    finally:
        launch['ended_at'] = datetime.now(timezone.utc).isoformat()
        write_new(output / 'launch.json', launch)
    return launch


def main(argv: list[str] | None = None) -> int:
    # AI_NOTE: 収集resultを既定でSOURCEの親から取り、指定時も保存sessionとの対応を検査する。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--scout-result', type=Path)
    parser.add_argument('--protocol', type=Path, default=Path(__file__).with_name('protocol.json'))
    args = parser.parse_args(argv)
    try:
        result = prepare(args.source, args.output, args.scout_result or args.source.parent / 'result.json', args.protocol)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps({k: v for k, v in result.items() if k not in {'arms', 'source_manifest', 'comparison', 'original_review'}}, ensure_ascii=False, indent=2))
    return 0 if result['status'] == 'prepared' else 2


if __name__ == '__main__':
    sys.exit(main())
