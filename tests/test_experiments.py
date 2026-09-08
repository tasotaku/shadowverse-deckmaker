"""Journal persistence, evidence integrity, truthful time boundaries, and public HTTP/CLI paths."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from svdeck.experiments import make_server
from svdeck.journal_store import Conflict, Journal, template


def record() -> dict[str, Any]:
    # AI_NOTE: 架空データは分離したテスト台帳だけへ書き、本番の初期記録には入れない。
    item = template('persistence-check')
    item.update(title='記録機能の検証用', summary='保存確認', method='記録の保存を確認',
                procedure='保存→再接続→読出し', inputs='テスト用入力', criteria='原文と履歴が一致する')
    return item


@pytest.fixture
def journal(tmp_path: Path) -> Journal:
    # AI_NOTE: ゲームDBに依存せず、別ディレクトリで永続化の境界を確認する。
    (tmp_path / 'evals' / 'trial').mkdir(parents=True)
    (tmp_path / 'evals' / 'trial' / 'README.md').write_text('最初の原文', encoding='utf-8')
    return Journal(tmp_path)


def test_revision_sources_and_restart(journal: Journal) -> None:
    # AI_NOTE: 更新した原本と保存済み原文を混同しないことを再接続後まで検査する。
    r = record()
    r['evidence_paths'] = ['evals/trial']
    first = journal.save(r, 0, '検証担当', '初回')
    source = journal.root / 'evals/trial/README.md'
    source.write_text('改訂した原文', encoding='utf-8')
    (source.parent / 'new.json').write_text('{}', encoding='utf-8')
    assert journal.changes(first)['paths'] == ['evals/trial/README.md', 'evals/trial/new.json']
    r['result'].update(outcome='fail', summary='成立しなかった')
    r['decision'].update(status='deferred', reason='別の入力で追加検証する')
    second = journal.save(r, 1, '別担当', '結果を追記。方式は保留')
    reloaded = Journal(journal.root)
    assert reloaded.get(r['id']) == second
    assert reloaded.get(r['id'], 1)['record']['result']['outcome'] == 'unassessed'
    assert reloaded.source(r['id'], 1, 'evals/trial/README.md').decode() == '最初の原文'
    assert reloaded.source(r['id'], 2, 'evals/trial/README.md').decode() == '改訂した原文'
    assert reloaded.get(r['id'])['record']['decision']['status'] == 'deferred'
    assert len(reloaded.history(r['id'])) == 2
    source.unlink()
    assert reloaded.source(r['id'], 1, 'evals/trial/README.md')


def test_conflict_and_transaction(journal: Journal) -> None:
    # AI_NOTE: 同時更新の片方だけが保存され、古い版での上書きは失敗する。
    r = record()
    journal.save(r, 0, 'a', '開始')
    def write(actor: str) -> str:
        try:
            journal.save(deepcopy(r), 1, actor, '同時更新')
            return 'saved'
        except Conflict:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(write, ['a', 'b'])) == ['conflict', 'saved']
    assert len(journal.history(r['id'])) == 2
    with journal.connect() as db, pytest.raises(sqlite3.IntegrityError, match='immutable'):
        db.execute('DELETE FROM revisions')


@pytest.mark.parametrize('mutation', [
    {'started_at': '2026-01-01T00:00:00'},
    {'started_at': '2026-02-01T00:00:00Z', 'ended_at': '2026-01-01T00:00:00Z', 'status': 'completed'},
    {'started_at': '2999-01-01T00:00:00Z', 'status': 'running'},
    {'evidence_paths': ['../secret']},
    {'evidence_paths': ['.']},
    {'evidence_paths': ['/etc/passwd']},
    {'evidence_paths': ['evals/missing']},
    {'decision': {'status': 'adopted', 'reason': ''}},
    {'result': {'outcome': 'pass', 'summary': '', 'limitations': '未記録'}},
])
def test_invalid_inputs_do_not_save(journal: Journal, mutation: dict[str, Any]) -> None:
    # AI_NOTE: 入力エラー時は不完全な記録を1件も残さない。
    r = record()
    r.update(mutation)
    with pytest.raises(ValueError):
        journal.save(r, 0, 'a', '誤入力')
    assert journal.all() == []


def test_time_facts_and_corrections(journal: Journal) -> None:
    # AI_NOTE: 不明時刻を許し、並行工程の期間を保持し、訂正前の値も残す。
    r = record()
    r.update(status='running')
    r['stages'] = [dict(id=i, title=i, status='completed', started_at='2026-09-01T09:00:00+09:00',
                        ended_at='2026-09-01T09:10:00+09:00', note='同時実施の明示記録', budget_minutes=5) for i in ['a', 'b']]
    r['stages'].append(dict(id='c', title='独立評価', status='running', started_at=None, ended_at=None, note='開始時刻は未記録', budget_minutes=None))
    journal.save(r, 0, 'a', '過去資料取込')
    assert journal.get(r['id'])['record']['started_at'] is None
    r['stages'][0]['ended_at'] = '2026-09-01T09:12:00+09:00'
    journal.save(r, 1, 'a', '工程aの終了時刻を原ログに合わせ訂正')
    assert journal.get(r['id'], 1)['record']['stages'][0]['ended_at'].endswith('09:10:00+09:00')
    r['status'] = 'completed'
    with pytest.raises(ValueError, match='試行終了'):
        journal.save(r, 2, 'a', '終了')
    r['stages'][2]['status'] = 'completed'
    journal.save(r, 2, 'a', '実施完了。過去の時刻は未記録')
    assert journal.get(r['id'])['record']['ended_at'] is None


def test_backup_and_restore_cli(journal: Journal, tmp_path: Path) -> None:
    # AI_NOTE: 別PC相当の場所へ復元し、資料と旧版が元のディレクトリなしで読める。
    r = record()
    r['evidence_paths'] = ['evals/trial']
    journal.save(r, 0, 'a', '初回')
    backup = tmp_path / 'backup.sqlite3'
    journal.backup(backup)
    with pytest.raises(FileExistsError):
        journal.backup(backup)
    target = tmp_path / 'other-pc'
    result = subprocess.run([sys.executable, '-m', 'svdeck.experiments', '--root', str(target), 'restore', str(backup)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    restored = Journal(target)
    assert restored.get(r['id'])['record'] == r
    assert restored.source(r['id'], 1, 'evals/trial/README.md').decode() == '最初の原文'
    assert restored.changes(restored.get(r['id']))['error']


def test_public_cli_lifecycle(journal: Journal, tmp_path: Path) -> None:
    # AI_NOTE: 作業担当の公開コマンドで開始・工程・採否・終了までを往復する。
    def cli(*args: str) -> dict[str, Any]:
        result = subprocess.run([sys.executable, '-m', 'svdeck.experiments', '--root', str(journal.root), *args], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)
    r = record()
    path = tmp_path / 'record.json'
    path.write_text(json.dumps(r), encoding='utf-8')
    assert cli('create', str(path), '--actor', 'a', '--reason', '登録')['revision'] == 1
    started = cli('stage', r['id'], 'run', '--title', '試行', '--status', 'running', '--at', '2026-09-01T09:00:00+09:00', '--note', '開始', '--experiment-status', 'running', '--expect', '1', '--actor', 'a', '--reason', '開始を記録')
    assert started['record']['stages'][0]['started_at'] == '2026-09-01T09:00:00+09:00'
    cli('stage', r['id'], 'run', '--status', 'completed', '--at', '2026-09-01T09:10:00+09:00', '--note', '終了', '--expect', '2', '--actor', 'a', '--reason', '終了を記録')
    r = cli('show', r['id'], '--record-only')
    r['status'] = 'completed'
    r['result'].update(outcome='fail', summary='出力価値を確認できず')
    r['decision'].update(status='rejected', reason='固定した有用性基準を満たさない')
    path.write_text(json.dumps(r), encoding='utf-8')
    assert cli('update', str(path), '--expect', '3', '--actor', 'a', '--reason', '最終評価')['revision'] == 4


def test_http_write_restart_and_source(journal: Journal) -> None:
    # AI_NOTE: UIが使うHTTP境界で保存・原文配信・外部からの更新拒否を確かめる。
    server = make_server(journal, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    try:
        with urlopen(url + '/api/experiments') as response:
            token = json.load(response)['token']
        r = record()
        r['evidence_paths'] = ['evals/trial']
        payload = json.dumps(dict(record=r, expected_revision=0, actor='UI', reason='HTTPから保存')).encode()
        request = Request(url + '/api/experiments', data=payload, headers={'Content-Type': 'application/json', 'X-Journal-Token': token})
        with urlopen(request) as response:
            assert json.load(response)['revision'] == 1
        with urlopen(url + '/source?id=persistence-check&revision=1&path=evals/trial/README.md') as response:
            assert '最初の原文' in response.read().decode()
        request.add_header('Origin', 'https://untrusted.example')
        with pytest.raises(HTTPError) as forbidden:
            urlopen(request)
        assert forbidden.value.code == 403
        with pytest.raises(HTTPError):
            urlopen(Request(url + '/api/experiments', data=payload, headers={'Content-Type': 'application/json'}))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert Journal(journal.root).get(r['id'])['revision'] == 1
