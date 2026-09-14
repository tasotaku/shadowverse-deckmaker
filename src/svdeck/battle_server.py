"""Local browser interface for reproducible battle experiments."""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .battle import Battle, catalog, default_state, demo_state, load_cases, replay, run_case

MAX_BODY = 4 * 1024 * 1024
WEB_ROOT = Path(__file__).with_name("battle_web")


def snapshot(battle: Battle, cursor: int | None = None) -> dict[str, Any]:
    # AI_NOTE: 同じエンジンから画面と保存用の記録を返し、画面独自の対戦処理を持たせない。
    record = battle.export()
    frames = record.get("frames", [])
    return {"state": battle.state, "record": record,
            "legal_actions": battle.legal_actions(),
            "cursor": len(record["actions"]) if cursor is None else cursor,
            "events": frames[-1].get("events", []) if frames else []}


class BattleHandler(BaseHTTPRequestHandler):
    """No shared battle session: each request carries its own replay."""

    server: ThreadingHTTPServer

    def send_data(self, data: bytes, status: int = 200,
                  mime: str = "application/json; charset=utf-8") -> None:
        # AI_NOTE: 外部埋め込み・キャッシュを禁止し、再読み込みで古い画面が残ることを防ぐ。
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
        self.end_headers()
        self.wfile.write(data)

    def send_json(self, data: object, status: int = 200) -> None:
        # AI_NOTE: ユーザー入力をHTMLへ埋め込まずJSON境界で返す。
        self.send_data(json.dumps(data, ensure_ascii=False, allow_nan=False).encode(), status)

    def valid_host(self) -> bool:
        # AI_NOTE: DNS rebindingで別サイトからローカルサービスへ到達させない。
        host = self.headers.get("Host", "")
        port = self.server.server_port
        return host in {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

    def do_GET(self) -> None:
        # AI_NOTE: 許可した静的ファイルだけを配信し、任意パスの読み取りを許さない。
        if not self.valid_host():
            self.send_json({"error": "ローカルのURLから開いてください。"}, 403)
            return
        path = urlsplit(self.path).path
        if path == "/api/bootstrap":
            presets: list[dict[str, Any]] = []
            preset_error: str | None = None
            try:
                presets.append({"id": "elf-game", "title": "アンリミテッド・エルフ40枚同士", "initial": demo_state(),
                                "description": "対応済みカードで構成したエルフ40枚同士の対戦。アンリミテッド。"})
            except ValueError as error:
                preset_error = str(error)
            self.send_json({"state": default_state(), "cards": catalog(), "cases": load_cases(),
                            "presets": presets, "preset_error": preset_error})
            return
        if path == "/favicon.ico":
            self.send_data(b"", status=204)
            return
        assets = {"/": ("index.html", "text/html"),
                  "/app.js": ("app.js", "text/javascript"),
                  "/style.css": ("style.css", "text/css")}
        if path not in assets:
            self.send_json({"error": "見つかりません。"}, 404)
            return
        name, mime = assets[path]
        self.send_data((WEB_ROOT / name).read_bytes(), mime=f"{mime}; charset=utf-8")

    def do_POST(self) -> None:
        # AI_NOTE: 記録はリクエスト内に閉じるため、別タブや同時操作が他の対戦を上書きしない。
        origin = self.headers.get("Origin")
        if (not self.valid_host() or (origin is not None and
                origin != "http://" + self.headers.get("Host", "")) or
                self.headers.get("Sec-Fetch-Site") == "cross-site"):
            self.send_json({"error": "同じ画面からの操作のみ受け付けます。"}, 403)
            return
        try:
            if self.headers.get_content_type() != "application/json":
                raise ValueError("JSON形式で送信してください。")
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_BODY:
                raise ValueError("入力は4MB以内のJSONにしてください。")
            self.connection.settimeout(10)
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict):
                raise ValueError("入力はJSONオブジェクトにしてください。")
            path = urlsplit(self.path).path
            if path == "/api/start":
                if not isinstance(body.get("state"), dict):
                    raise ValueError("開始状態が必要です。")
                self.send_json(snapshot(Battle(body["state"], cards=body.get("cards"))))
            elif path in {"/api/replay", "/api/step"}:
                record = body.get("record")
                if not isinstance(record, dict) or not isinstance(record.get("actions"), list):
                    raise ValueError("対戦記録が必要です。")
                if len(record["actions"]) > 2000:
                    raise ValueError("画面で扱う記録は2000操作以内にしてください。")
                cursor = body.get("cursor", len(record["actions"]))
                if isinstance(cursor, bool) or not isinstance(cursor, int) or not 0 <= cursor <= len(record["actions"]):
                    raise ValueError("再生位置が不正です。")
                battle = replay(record, cursor=cursor)
                if path == "/api/step":
                    if not isinstance(body.get("action"), dict):
                        raise ValueError("操作が必要です。")
                    battle.step(body["action"])
                    self.send_json(snapshot(battle))
                else:
                    result = snapshot(battle, cursor)
                    # AI_NOTE: 表示中の処理履歴は再計算結果を使い、読み込んだ説明文を正解とみなさない。
                    result["record"] = {**record, "frames": [
                        *result["record"].get("frames", []),
                        *record.get("frames", [])[cursor:]]}
                    self.send_json(result)
            elif path == "/api/test":
                if not isinstance(body.get("case"), dict):
                    raise ValueError("試験ケースが必要です。")
                self.send_json(run_case(body["case"]))
            else:
                self.send_json({"error": "見つかりません。"}, 404)
        except (ValueError, TypeError, KeyError, IndexError, AttributeError, OSError, RecursionError) as error:
            self.send_json({"error": str(error)}, 400)


def create_server(host: str = "127.0.0.1", port: int = 8767) -> ThreadingHTTPServer:
    # AI_NOTE: 対戦状態を外部へ公開しないようループバック接続だけに制限する。
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("host must be 127.0.0.1 or localhost")
    return ThreadingHTTPServer((host, port), BattleHandler)


def main() -> None:
    # AI_NOTE: Ctrl+Cで待受けを閉じ、対戦記録の保存はブラウザ側に任せる。
    parser = argparse.ArgumentParser(description="AI対戦・コンボ検証画面")
    parser.add_argument("--port", type=int, default=8767)
    args = parser.parse_args()
    server = create_server(port=args.port)
    print(f"対戦検証: http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
