"""Preserve each submitted intermediate report and prepare identical finalization instructions."""
from pathlib import Path
import ast
import gzip
import json
import shutil
import subprocess
import sys
import tarfile
from svdeck import discovery
from svdeck.discovery_run import check_finish, check_unchanged, copy_session, manifest
from svdeck.journal_store import Journal, now

root = Path(__file__).resolve().parents[3]
folder = Path(__file__).resolve().parent
protocol = json.loads((folder / 'protocol.json').read_text())
module_path = Path(discovery.__file__).resolve()
module = module_path.read_text()
tails = [ast.literal_eval(n.value) for n in ast.parse(module).body if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and n.target.id == 'DEVELOP']
assert len(tails) == 1
instruction = discovery.FINISH + '\n' + tails[0] + '\n指定した中間報告1件を根拠から点検して正式案へまとめます。役割の接続工程を新しく繰り返す必要はありません。未解決を隠さず、既存の提出形式で正式案1件にします。\n'
prepared = {'started_at': now(), 'instruction': instruction, 'arms': {}, 'limits': '両側は同じ正式化指示。前段の中間報告が異なるので入力全体の同一性を主張しない。本文の選択入口は両側へ同じ新実装を適用。'}
for arm in ('A', 'B'):
    run = Path('/tmp/fragment-handoff-02-' + arm.lower() + '-intermediate')
    result = json.loads((run / 'result.json').read_text())
    assert result['status'] == 'completed'
    check_unchanged(Path(protocol['source']), protocol['source_manifest'], exact=True)
    check_unchanged(run / 'runtime', result['runtime_manifest'], exact=True)
    contract = json.loads((run / 'inquiry/finish-config.json').read_text())
    assert check_finish(run / 'inquiry', contract) == result['run']['finish_evidence']
    out = folder / (arm.lower() + '-intermediate')
    out.mkdir(exist_ok=False)
    for name in ('answer.md', 'prompt.md', 'public-config.json', 'finish-config.json', 'finish-request.json', 'input-summary.json', 'final-message.md'):
        if (run / 'inquiry' / name).is_file():
            shutil.copyfile(run / 'inquiry' / name, out / name)
    for src, name in ((run / 'result.json', 'result.json'), (run / 'inquiry-run/run.json', 'run.json')):
        shutil.copyfile(src, out / name)
    ops = sorted([json.loads(p.read_text()) for p in (run / 'inquiry/operations').glob('*.json')], key=lambda x: x['started_at'])
    with gzip.open(out / 'public-operations.json.gz', 'wt', encoding='utf-8') as stream:
        json.dump(ops, stream, ensure_ascii=False)
    source = root / ('data/discovery/fragment-handoff-02-' + arm.lower() + '-intermediate')
    assert not source.exists()
    copy_session(run / 'session', source)
    check_unchanged(source, result['evidence']['session_manifest'], exact=True)
    with tarfile.open(out / 'session.tar.gz', 'w:gz') as archive:
        archive.add(source, arcname='session')
    key = result['submission']['source_hash']
    runtime = Path('/tmp/fragment-handoff-02-' + arm.lower() + '-final-runtime')
    shutil.copytree(module_path.parent, runtime / 'svdeck', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    wrapper = 'FINISH = ' + repr(instruction) + '\n_fragment_packet = packet\n\ndef packet(session: Path, revision: int | None, stage: str, finish_from_source: str | None = None) -> JSONDict:\n    if stage == "develop":\n        if finish_from_source not in (None, ' + repr(key) + '):\n            raise ValueError("固定した中間報告だけを使います")\n        finish_from_source = ' + repr(key) + '\n    return _fragment_packet(session, revision, stage, finish_from_source)\n\n'
    marker = 'if __name__ == "__main__":'
    assert module.count(marker) == 1
    (runtime / 'svdeck/discovery.py').write_text(module.replace(marker, wrapper + marker))
    probe = Path('/tmp/fragment-handoff-02-' + arm.lower() + '-final-probe')
    copy_session(source, probe)
    command = 'from pathlib import Path; from svdeck import discovery as d; import sys,json; p=d.packet(Path(sys.argv[1]),0,"develop"); print(json.dumps({"hash":p["sha256"],"key":p["data"]["finish_from_source"],"instruction":p["data"]["instruction"],"review":d.REVIEW}))'
    tested = subprocess.run([sys.executable, '-c', command, str(probe)], env={'PYTHONPATH': str(runtime), 'PYTHONDONTWRITEBYTECODE': '1'}, capture_output=True, text=True, check=True)
    actual = json.loads(tested.stdout)
    assert actual['key'] == key and actual['instruction'] == instruction and actual['review'] == discovery.REVIEW
    prepared['arms'][arm] = {'source': str(source), 'source_manifest': manifest(source), 'runtime': str(runtime), 'runtime_manifest': manifest(runtime), 'finish_from_source': key, 'probe_hash': actual['hash'], 'output': '/tmp/fragment-handoff-02-' + arm.lower() + '-final-live', 'intermediate_seconds': result['run']['elapsed_seconds']}
prepared['ended_at'] = now()
(folder / 'final-input.json').write_text(json.dumps(prepared, ensure_ascii=False, indent=2) + '\n')
journal = Journal(root)
e = journal.get(folder.name)
r = e['record']
r['summary'] = '両側とも5分以内に中間報告1件を公開保存。各報告から同じ指示で正式案→別評価へ進む。'
for arm in ('a', 'b'):
    for phase, title, budget in (('whole', '正式化から別評価・最終保存まで', 20), ('develop', '中間報告1件を正式案へまとめる', 10), ('review', '正式案を通常指示で別評価', 10)):
        r['stages'].append({'id': arm + '-' + phase, 'title': arm.upper() + '：' + title, 'status': 'planned', 'started_at': None, 'ended_at': None, 'note': '同じ正式化・評価指示。前段で保存した中間報告を固定。', 'budget_minutes': budget})
r['evidence_paths'] = [p.relative_to(root).as_posix() for p in folder.rglob('*') if p.is_file() and p.name not in ('journal-record.json', 'delivery-check.json')]
e = journal.save(r, e['revision'], 'codex', '両方式の中間報告を保存して正式化へ進む')
(folder / 'journal-record.json').write_text(json.dumps(e, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({a: {'key': v['finish_from_source'], 'seconds': v['intermediate_seconds']} for a, v in prepared['arms'].items()}))
