"""Experiment reports: immutable revisions and content-addressed evidence, separate from cards.db."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterator

STATES = {'planned', 'running', 'waiting', 'completed', 'interrupted'}
RECORD_FIELDS = {'id', 'title', 'category', 'status', 'summary', 'method', 'procedure',
                 'inputs', 'criteria', 'result', 'decision', 'started_at', 'ended_at',
                 'stages', 'evidence_paths'}


class Conflict(ValueError):
    """Another writer already saved a revision."""


def now() -> str:
    # AI_NOTE: 保存時刻はサーバー側で採番し、実施時刻へ転用しない。
    return datetime.now(timezone.utc).isoformat()


def instant(value: Any) -> datetime | None:
    # AI_NOTE: タイムゾーンのない日時を推測して補わない。
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError('日時はタイムゾーン付き ISO 8601 文字列か null にしてください')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})', value):
        raise ValueError('日時は YYYY-MM-DDTHH:MM:SS[.小数]+09:00 または Z の形式にしてください')
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError as exc:
        raise ValueError('日時はタイムゾーン付き ISO 8601 形式にしてください') from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('日時のタイムゾーンが必要です（例: +09:00）')
    return result


def time_range(item: dict[str, Any]) -> None:
    # AI_NOTE: 欠けた過去時刻は許容するが、逆転・未来の実施記録は拒否する。
    start, end = instant(item.get('started_at')), instant(item.get('ended_at'))
    if start and end and end < start:
        raise ValueError('終了日時は開始日時以後にしてください')
    if any(t and t > datetime.now(timezone.utc) for t in (start, end)):
        raise ValueError('実施日時には未来を指定できません')
    if item['status'] in {'running', 'waiting', 'planned'} and end:
        raise ValueError('進行中・待機・未着手には終了日時を指定できません。終了した工程は完了または中断にしてください')
    if item['status'] == 'planned' and start:
        raise ValueError('未着手には開始日時を指定できません')


def require_text(item: dict[str, Any], keys: set[str], *, empty: bool = False) -> None:
    # AI_NOTE: 人が書き込む境界で、欠損と空欄を明示的に検査する。
    for key in keys:
        if not isinstance(item.get(key), str) or (not empty and not item[key].strip()):
            raise ValueError(f'{key}: 文字列を入力してください。未記録の場合は「未記録」と記してください')


def validate(record: dict[str, Any]) -> None:
    # AI_NOTE: 結果と採否は別々の値として検査し、成功から採用を自動生成しない。
    if set(record) != RECORD_FIELDS:
        raise ValueError(f'記録項目が一致しません。不足: {sorted(RECORD_FIELDS-set(record))} / 不明: {sorted(set(record)-RECORD_FIELDS)}')
    require_text(record, {'id', 'title', 'summary', 'method', 'procedure', 'inputs', 'criteria', 'status', 'category'})
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,79}', record['id']):
        raise ValueError('id は英小文字・数字・ハイフンで80文字以内にしてください')
    if record['status'] not in STATES or record['category'] not in {'method', 'infrastructure'}:
        raise ValueError('状態または分類が不正です')
    time_range(record)
    result, decision = record['result'], record['decision']
    if not isinstance(result, dict) or set(result) != {'outcome', 'summary', 'limitations'}:
        raise ValueError('result は outcome / summary / limitations が必要です')
    require_text(result, {'outcome', 'summary', 'limitations'})
    if result['outcome'] not in {'unassessed', 'mixed', 'pass', 'fail'}:
        raise ValueError('試行結果が不正です')
    if not isinstance(decision, dict) or set(decision) != {'status', 'reason'}:
        raise ValueError('decision は status / reason が必要です')
    require_text(decision, {'status', 'reason'})
    if decision['status'] not in {'unassessed', 'adopted', 'rejected', 'deferred'}:
        raise ValueError('採否が不正です')
    stages = record['stages']
    if not isinstance(stages, list) or not all(isinstance(s, dict) for s in stages):
        raise ValueError('stages は工程の配列にしてください')
    seen: set[str] = set()
    for stage in stages:
        if set(stage) != {'id', 'title', 'status', 'started_at', 'ended_at', 'note', 'budget_minutes'}:
            raise ValueError('工程項目は id/title/status/started_at/ended_at/note/budget_minutes です')
        require_text(stage, {'id', 'title', 'note', 'status'})
        if stage['id'] in seen or stage['status'] not in STATES:
            raise ValueError('工程IDの重複または状態が不正です')
        seen.add(stage['id'])
        budget = stage['budget_minutes']
        if budget is not None and (type(budget) not in (int, float) or not 0 < budget <= 525600):
            raise ValueError('目安時間は正の分数か null にしてください')
        time_range(stage)
        if record['status'] in {'completed', 'interrupted'} and stage['status'] in {'running', 'waiting'}:
            raise ValueError('試行終了の前に作業中・待機中の工程を完了または中断にしてください')
        if record['status'] == 'completed' and stage['status'] == 'planned':
            raise ValueError('試行終了の前に未着手の工程を完了または中断にしてください')
        if record['status'] == 'planned' and stage['status'] != 'planned':
            raise ValueError('開始済みの工程があります。試行全体の状態も更新してください')
        for key in ('started_at', 'ended_at'):
            value = instant(stage[key])
            start, end = instant(record['started_at']), instant(record['ended_at'])
            if value and ((start and value < start) or (end and value > end)):
                raise ValueError('工程日時が試行全体の実施期間外です')
    paths = record['evidence_paths']
    if not isinstance(paths, list) or not all(isinstance(p, str) and p for p in paths):
        raise ValueError('evidence_paths は資料の相対パスの配列にしてください')


def template(identifier: str = '') -> dict[str, Any]:
    # AI_NOTE: 入力ひな形は未判定で始め、例示の成功データは混ぜない。
    return {'id': identifier, 'title': '', 'category': 'method', 'status': 'planned',
            'summary': '', 'method': '', 'procedure': '', 'inputs': '', 'criteria': '',
            'result': {'outcome': 'unassessed', 'summary': '未判定', 'limitations': '未記録'},
            'decision': {'status': 'unassessed', 'reason': '未判定'},
            'started_at': None, 'ended_at': None, 'stages': [], 'evidence_paths': []}


class Journal:
    def __init__(self, root: Path, path: Path | None = None) -> None:
        # AI_NOTE: カードDBから完全に分離し、rootを共有すれば別作業コピーでも同じ記録を使える。
        self.root = root.resolve()
        self.path = (path or self.root / 'data' / 'experiments.sqlite3').resolve()
        if self.path.name == 'cards.db':
            raise ValueError('カードDBは保存先に使えません')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS revisions (
                    id TEXT NOT NULL, revision INTEGER NOT NULL, saved_at TEXT NOT NULL,
                    actor TEXT NOT NULL, reason TEXT NOT NULL, record TEXT NOT NULL,
                    evidence TEXT NOT NULL, PRIMARY KEY(id, revision));
                CREATE TABLE IF NOT EXISTS blobs (sha256 TEXT PRIMARY KEY, content BLOB NOT NULL);
                CREATE TRIGGER IF NOT EXISTS revisions_no_update BEFORE UPDATE ON revisions
                    BEGIN SELECT RAISE(ABORT, 'immutable revision'); END;
                CREATE TRIGGER IF NOT EXISTS revisions_no_delete BEFORE DELETE ON revisions
                    BEGIN SELECT RAISE(ABORT, 'immutable revision'); END;
                CREATE TRIGGER IF NOT EXISTS blobs_no_update BEFORE UPDATE ON blobs
                    BEGIN SELECT RAISE(ABORT, 'immutable evidence'); END;
                CREATE TRIGGER IF NOT EXISTS blobs_no_delete BEFORE DELETE ON blobs
                    BEGIN SELECT RAISE(ABORT, 'immutable evidence'); END;
            ''')

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        # AI_NOTE: 書込みは一つの取引として確定し、例外時には根拠の追加も一緒に取り消す。
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def evidence(self, paths: list[str]) -> tuple[list[dict[str, Any]], dict[str, bytes]]:
        # AI_NOTE: 許可した資料領域だけ読み、保存当時の内容をハッシュと一緒に保持する。
        files: set[Path] = set()
        for name in paths:
            relative = Path(name)
            path = (self.root / relative).resolve()
            allowed = ('evals/', 'docs/', 'tests/fixtures/')
            if not relative.parts or relative.is_absolute() or not path.is_relative_to(self.root):
                raise ValueError(f'資料は root 内の evals/・docs/・tests/fixtures/・README.md に限定しています: {name}')
            canonical = path.relative_to(self.root).as_posix()
            if not (canonical == 'README.md' or any(canonical == p.rstrip('/') or canonical.startswith(p) for p in allowed)):
                raise ValueError('資料領域外へのリンクは保存できません')
            if not path.exists():
                raise ValueError(f'資料がありません: {name}')
            files.update(p for p in path.rglob('*') if p.is_file()) if path.is_dir() else files.add(path)
        evidence: list[dict[str, Any]] = []
        blobs: dict[str, bytes] = {}
        total = 0
        for path in sorted(files):
            if not path.resolve().is_relative_to(self.root) or path.is_symlink():
                raise ValueError('資料領域外へのリンクは保存できません')
            if path.suffix in {'.db', '.sqlite', '.sqlite3'} or path.stat().st_size > 10_000_000:
                raise ValueError(f'資料は10MB以下の文書にしてください: {path.name}')
            content = path.read_bytes()
            total += len(content)
            if total > 50_000_000:
                raise ValueError('1試行の根拠資料は合計50MB以内にしてください')
            digest = hashlib.sha256(content).hexdigest()
            blobs[digest] = content
            evidence.append({'path': path.relative_to(self.root).as_posix(), 'sha256': digest, 'size': len(content)})
        return evidence, blobs

    def save(self, record: dict[str, Any], expected: int, actor: str, reason: str) -> dict[str, Any]:
        # AI_NOTE: 版番号が一致しない更新は拒否し、他担当の訂正を黙って上書きしない。
        validate(record)
        if type(expected) is not int or expected < 0:
            raise ValueError('expected_revision は0以上の整数が必要です')
        if not isinstance(actor, str) or not actor.strip() or not isinstance(reason, str) or not reason.strip():
            raise ValueError('記録者と更新・訂正理由を入力してください')
        evidence, blobs = self.evidence(record['evidence_paths'])
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            current = db.execute('SELECT COALESCE(MAX(revision), 0) FROM revisions WHERE id=?', (record['id'],)).fetchone()[0]
            if current != expected:
                raise Conflict(f'別の更新があります（現在の版: {current}、編集開始時: {expected}）。最新を開いて変更を合わせてください')
            db.executemany('INSERT OR IGNORE INTO blobs VALUES (?,?)', blobs.items())
            db.execute('INSERT INTO revisions VALUES (?,?,?,?,?,?,?)',
                       (record['id'], current + 1, now(), actor.strip(), reason.strip(),
                        json.dumps(record, ensure_ascii=False, allow_nan=False), json.dumps(evidence)))
        return self.get(record['id'], current + 1)

    def get(self, identifier: str, revision: int | None = None) -> dict[str, Any]:
        # AI_NOTE: 旧版も当時の根拠との組で返し、現在の原本で書き換えない。
        with self.connect() as db:
            row = db.execute('SELECT * FROM revisions WHERE id=? AND (? IS NULL OR revision=?) ORDER BY revision DESC LIMIT 1',
                             (identifier, revision, revision)).fetchone()
        if row is None:
            raise KeyError('試行または版が見つかりません')
        return {**dict(row), 'record': json.loads(row['record']), 'evidence': json.loads(row['evidence'])}

    def all(self) -> list[dict[str, Any]]:
        # AI_NOTE: 各試行の最新版を保存日時順で一覧にする。
        with self.connect() as db:
            identifiers = [row[0] for row in db.execute('SELECT id FROM revisions GROUP BY id ORDER BY MAX(saved_at) DESC')]
        return [self.get(identifier) for identifier in identifiers]

    def history(self, identifier: str) -> list[dict[str, Any]]:
        # AI_NOTE: 何をいつ訂正したかを、全版の保存情報から辿れるようにする。
        with self.connect() as db:
            return [dict(row) for row in db.execute('SELECT revision,saved_at,actor,reason FROM revisions WHERE id=? ORDER BY revision DESC', (identifier,))]

    def changes(self, item: dict[str, Any]) -> dict[str, Any]:
        # AI_NOTE: 原本の更新は内容で検出する。mtimeを実施日時として使わない。
        try:
            evidence, _ = self.evidence(item['record']['evidence_paths'])
        except (OSError, ValueError) as exc:
            return {'error': str(exc), 'paths': []}
        old = {e['path']: e['sha256'] for e in item['evidence']}
        new = {e['path']: e['sha256'] for e in evidence}
        return {'error': None, 'paths': sorted(p for p in old.keys() | new.keys() if old.get(p) != new.get(p))}

    def source(self, identifier: str, revision: int, path: str) -> bytes:
        # AI_NOTE: 画面からはその版で保存した資料だけ読み出せる。
        item = self.get(identifier, revision)
        evidence = next((e for e in item['evidence'] if e['path'] == path), None)
        if evidence is None:
            raise KeyError('この版に保存されていない資料です')
        with self.connect() as db:
            content: bytes = db.execute('SELECT content FROM blobs WHERE sha256=?', (evidence['sha256'],)).fetchone()[0]
        if hashlib.sha256(content).hexdigest() != evidence['sha256']:
            raise ValueError('保存資料の内容が識別値と一致しません')
        return content

    def backup(self, destination: Path) -> None:
        # AI_NOTE: 更新と並行しても整合した台帳全体を退避し、既存バックアップは上書きしない。
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open('xb'):
            pass
        with self.connect() as source, sqlite3.connect(destination) as target:
            source.backup(target)
