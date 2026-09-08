"""Local experiment journal. Run `python -m svdeck.experiments --help`."""

from __future__ import annotations

import argparse
import gzip
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import secrets
import shutil
import sqlite3
import sys
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

from .journal_store import Conflict, Journal, STATES, now, template

ASSETS = Path(__file__).with_name('journal_web')


def load_json(path: Path) -> Any:
    # AI_NOTE: CLI入力はUTF-8のJSONとして一度だけ読み、構文エラーを利用者へ返す。
    return json.loads(path.read_text(encoding='utf-8'))


def source_page(journal: Journal, identifier: str, revision: int, path: str) -> str:
    # AI_NOTE: 保存した原文をHTMLとして実行せず、文書内の相対リンクだけ保存版へつなぐ。
    content = journal.source(identifier, revision, path)
    if path.endswith('.gz'):
        with gzip.GzipFile(fileobj=io.BytesIO(content)) as stream:
            content = stream.read(10_000_001)
        if len(content) > 10_000_000:
            raise ValueError('展開後の資料が10MBを超えています')
    text = content.decode('utf-8', errors='replace')
    if path.endswith(('.json', '.json.gz')):
        text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
    escaped = html.escape(text)
    item = journal.get(identifier, revision)
    links = ''.join(f'<li><a href="/source?{source_query(identifier, revision, e["path"])}">{html.escape(e["path"])}</a></li>' for e in item['evidence'])
    return f'''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>{html.escape(path)} — 保存資料</title><link rel="stylesheet" href="/style.css">
    <body><main class="source"><a href="/#experiment/{quote(identifier)}">← 試行の詳細</a>
    <h1>保存した根拠資料</h1><p>{html.escape(path)} · 報告 第{revision}版</p>
    <p>この報告を保存した時点の原文です。原本の後日の変更は混ざりません。</p>
    <pre>{escaped}</pre><details><summary>同じ報告に保存した資料</summary><ul>{links}</ul></details></main></body></html>'''


def source_query(identifier: str, revision: int, path: str) -> str:
    # AI_NOTE: 資料へのリンクはID・版・相対パスを明示して同じ保存版を再表示する。
    return f'id={quote(identifier)}&revision={revision}&path={quote(path)}'


def make_server(journal: Journal, port: int) -> ThreadingHTTPServer:
    # AI_NOTE: ループバックのみへ公開し、外部サイトからの読出し・書込みを拒否する。
    token = secrets.token_urlsafe(32)
    server_port = port

    class Handler(BaseHTTPRequestHandler):
        def respond(self, status: int, content: bytes, kind: str) -> None:
            # AI_NOTE: キャッシュから古い進捗を返さず、文書のスクリプト実行を制限する。
            self.send_response(status)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(content)

        def json(self, status: int, data: Any) -> None:
            # AI_NOTE: APIと画面は同じ保存処理の結果を受け取る。
            self.respond(status, json.dumps(data, ensure_ascii=False).encode(), 'application/json; charset=utf-8')

        def allowed(self, write: bool = False) -> bool:
            # AI_NOTE: Host検査はDNS再割当て、Originとtoken検査は外部ページ経由の更新を防ぐ。
            port = server_port
            hosts = {f'127.0.0.1:{port}', f'localhost:{port}'}
            if self.headers.get('Host') not in hosts:
                return False
            origin = self.headers.get('Origin')
            if origin and origin not in {f'http://{host}' for host in hosts}:
                return False
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                return False
            return not write or self.headers.get('X-Journal-Token') == token

        def do_GET(self) -> None:
            # AI_NOTE: 任意ファイル配信はせず、固定UI・保存資料・台帳の入口だけ提供する。
            if not self.allowed():
                self.json(403, {'error': 'このローカル画面からアクセスしてください'})
                return
            url = urlsplit(self.path)
            query = parse_qs(url.query)
            try:
                if url.path == '/api/experiments':
                    items = journal.all()
                    for item in items:
                        item['source_changes'] = journal.changes(item)
                    self.json(200, {'items': items, 'token': token, 'root': str(journal.root), 'store': str(journal.path), 'checked_at': now()})
                elif url.path.startswith('/api/experiments/'):
                    identifier = url.path.split('/')[-1]
                    revision = int(query['revision'][0]) if 'revision' in query else None
                    item = journal.get(identifier, revision)
                    item['history'] = journal.history(identifier)
                    item['source_changes'] = journal.changes(item)
                    self.json(200, item)
                elif url.path == '/source':
                    self.respond(200, source_page(journal, query['id'][0], int(query['revision'][0]), query['path'][0]).encode(), 'text/html; charset=utf-8')
                elif url.path in {'/', '/app.js', '/style.css'}:
                    name = {'/': 'index.html', '/app.js': 'app.js', '/style.css': 'style.css'}[url.path]
                    kind = {'/': 'text/html', '/app.js': 'text/javascript', '/style.css': 'text/css'}[url.path]
                    self.respond(200, (ASSETS / name).read_bytes(), kind + '; charset=utf-8')
                else:
                    self.json(404, {'error': 'ページがありません'})
            except KeyError as exc:
                self.json(404, {'error': str(exc)})
            except (ValueError, OSError) as exc:
                self.json(400, {'error': str(exc)})

        def do_POST(self) -> None:
            # AI_NOTE: 更新理由と編集中の版番号を必須にして、二重更新による履歴喪失を防ぐ。
            if not self.allowed(write=True):
                self.json(403, {'error': 'この画面を再読込してから保存してください'})
                return
            if self.path != '/api/experiments':
                self.json(404, {'error': '保存入口がありません'})
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 1_000_000 or self.headers.get_content_type() != 'application/json':
                    raise ValueError('1MB以下のJSONが必要です')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict) or not isinstance(data.get('record'), dict):
                    raise ValueError('record を含むJSONオブジェクトが必要です')
                item = journal.save(data['record'], data['expected_revision'], data['actor'], data['reason'])
                self.json(200, item)
            except Conflict as exc:
                self.json(409, {'error': str(exc)})
            except (ValueError, KeyError, TypeError, OSError) as exc:
                self.json(400, {'error': str(exc)})
            except sqlite3.Error as exc:
                self.json(503, {'error': f'保存できませんでした。入力を保持して再試行してください: {exc}'})

        def log_message(self, format: str, *args: Any) -> None:
            # AI_NOTE: 通常のHTTPログを残し、入力本文はログへ出さない。
            super().log_message(format, *args)

    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server_port = server.server_port
    return server


def main() -> None:
    # AI_NOTE: 画面と作業担当のCLIを同じ保存処理へ接続する。
    parser = argparse.ArgumentParser(description='探索手法の試行・工程・採否を永続記録するローカル台帳')
    parser.add_argument('--root', type=Path, default=Path.cwd(), help='共通の本体リポジトリ。別作業コピーでは明示する')
    parser.add_argument('--store', type=Path, help='台帳の保存先。既定は root/data/experiments.sqlite3')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('list')
    sub.add_parser('template')
    show = sub.add_parser('show')
    show.add_argument('id')
    show.add_argument('--revision', type=int)
    show.add_argument('--record-only', action='store_true')
    init = sub.add_parser('init')
    init.add_argument('--catalog', type=Path, default=Path(__file__).with_name('data') / 'experiment_catalog.json')
    serve = sub.add_parser('serve')
    serve.add_argument('--port', type=int, default=8765)
    for command in ('create', 'update'):
        write = sub.add_parser(command)
        write.add_argument('file', type=Path)
        write.add_argument('--expect', type=int, default=0 if command == 'create' else None, required=command == 'update')
        write.add_argument('--actor', required=True)
        write.add_argument('--reason', required=True)
    stage = sub.add_parser('stage')
    stage.add_argument('id')
    stage.add_argument('stage_id', help='新しい工程区間には新しいIDを使う')
    stage.add_argument('--title')
    stage.add_argument('--status', choices=sorted(STATES), required=True)
    stage.add_argument('--at', help='この状態になった実施日時。未記録なら省略。now は今実施した場合のみ')
    stage.add_argument('--note', required=True)
    stage.add_argument('--budget-minutes', type=float)
    stage.add_argument('--experiment-status', choices=sorted(STATES), help='同時に試行全体の状態を更新')
    stage.add_argument('--expect', type=int, required=True)
    stage.add_argument('--actor', required=True)
    stage.add_argument('--reason', required=True)
    backup = sub.add_parser('backup')
    backup.add_argument('destination', type=Path)
    restore = sub.add_parser('restore')
    restore.add_argument('source', type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'template':
            output: Any = template()
        elif args.command == 'restore':
            destination = (args.store or args.root / 'data' / 'experiments.sqlite3').resolve()
            with sqlite3.connect(f'file:{quote(str(args.source.resolve()))}?mode=ro', uri=True) as db:
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise ValueError('バックアップの整合性検査に失敗しました')
                db.execute('SELECT id,revision,record,evidence FROM revisions LIMIT 1')
                db.execute('SELECT sha256,content FROM blobs LIMIT 1')
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as target, args.source.open('rb') as source:
                shutil.copyfileobj(source, target)
            output = {'restored': str(destination)}
        else:
            journal = Journal(args.root, args.store)
            if args.command == 'init':
                output = []
                existing = {item['id'] for item in journal.all()}
                for record in load_json(args.catalog):
                    if record['id'] not in existing:
                        output.append(journal.save(record, 0, '初期資料取込', '既存の検証記録を初期登録。過去の未記録時刻は補完していない'))
            elif args.command == 'list':
                output = journal.all()
            elif args.command == 'show':
                output = journal.get(args.id, args.revision)
                if args.record_only:
                    output = output['record']
            elif args.command in {'create', 'update'}:
                output = journal.save(load_json(args.file), args.expect, args.actor, args.reason)
            elif args.command == 'stage':
                item = journal.get(args.id)
                record = item['record']
                stage_record = next((s for s in record['stages'] if s['id'] == args.stage_id), None)
                if stage_record is None:
                    stage_record = {'id': args.stage_id, 'title': args.title or args.stage_id, 'status': 'planned',
                                    'started_at': None, 'ended_at': None, 'note': args.note, 'budget_minutes': args.budget_minutes}
                    record['stages'].append(stage_record)
                elif stage_record['status'] in {'completed', 'interrupted'} and args.status in {'running', 'waiting'}:
                    raise ValueError('再開は新しい工程IDを使ってください。訂正は update で理由とともに保存できます')
                at = now() if args.at == 'now' else args.at
                if at:
                    key = 'ended_at' if args.status in {'completed', 'interrupted'} else 'started_at'
                    if stage_record[key] and stage_record[key] != at:
                        raise ValueError('記録済み時刻の訂正は update で理由とともに保存してください')
                    stage_record[key] = at
                stage_record.update(status=args.status, note=args.note)
                if args.title:
                    stage_record['title'] = args.title
                if args.budget_minutes is not None:
                    stage_record['budget_minutes'] = args.budget_minutes
                if args.experiment_status:
                    record['status'] = args.experiment_status
                output = journal.save(record, args.expect, args.actor, args.reason)
            elif args.command == 'backup':
                journal.backup(args.destination)
                output = {'backup': str(args.destination.resolve())}
            else:
                server = make_server(journal, args.port)
                print(f'実験記録: http://127.0.0.1:{server.server_port}/\n台帳: {journal.path}\n原本: {journal.root}', flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
                finally:
                    server.server_close()
                return
        print(json.dumps(output, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError, sqlite3.Error) as exc:
        print(f'記録できませんでした: {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
