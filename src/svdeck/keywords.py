"""公式のキーワード用語辞書(abilityKeywordList)を取得してローカルDB(ミラー層)へ保存する。

ability_keyword は用語の正準定義。推論・目利きでキーワードの挙動に迷ったらこのテーブルを引く。

小さなマスタ(約2.6KB)なので、fetch.pyの名称辞書(card_set/skill_name/tribe)と同じ扱いで
毎回 DELETE→全INSERT で作り直す。

実行: python -m svdeck.keywords
"""

import json
import urllib.request
from typing import Any

from svdeck.db import connect

API_URL = "https://shadowverse-wb.com/web/System/abilityKeywordList"
USER_AGENT = "Mozilla/5.0"


def _get_json(url: str) -> dict[str, Any]:
    # AI_NOTE: HTTP境界。取得失敗は握りつぶさず呼び出し元へ伝播させる(meta.py/fetch.pyと同じ作法)。
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response:
        payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    return payload


def fetch_keywords() -> list[tuple[str, str]]:
    # AI_NOTE: 応答はdata.ability_key_word_listの{title, text}リスト。lang=jaで日本語版を取る。
    payload = _get_json(f"{API_URL}?lang=ja")
    items = payload["data"]["ability_key_word_list"]
    return [(item["title"], item["text"]) for item in items]


def run() -> None:
    # AI_NOTE: エントリポイント。ability_keywordを毎回作り直す(名称辞書と同じくDELETE→全INSERT)。
    conn = connect()
    try:
        keywords = fetch_keywords()
        conn.execute("DELETE FROM ability_keyword")
        conn.executemany(
            "INSERT INTO ability_keyword (title, text, fetched_at) VALUES (?, ?, datetime('now'))",
            keywords,
        )
        conn.commit()
        print(f"[keywords] 完了: {len(keywords)}件")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
