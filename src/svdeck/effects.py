"""specific_effect(クレスト/結晶/アクセラレート/信仰)を単体カードAPIから収集する。

カード一覧API(cardList)は『クレスト：〜』等の参照先効果テキストを含まない。単体カードAPI
/web/CardList/card は specific_effect_card_info としてそれを返すため、全カードを1枚ずつ
叩いて specific_effect テーブル(ミラー層・作り直し可)に保存する。

実行: python -m svdeck.effects
"""

import json
import sqlite3
import time
import urllib.request
from typing import Any

from svdeck.db import connect

API_URL = "https://shadowverse-wb.com/web/CardList/card"
USER_AGENT = "Mozilla/5.0"
REQUEST_INTERVAL_SEC = 0.35


def fetch_card(card_id: int) -> dict[str, Any]:
    # AI_NOTE: 単体カードAPIのHTTP境界。specific_effect_card_info を含む data を返す。例外は伝播。
    url = f"{API_URL}?card_id={card_id}&lang=ja"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data: dict[str, Any] = payload["data"]
    return data


def save_effects(conn: sqlite3.Connection, card_id: int, data: dict[str, Any]) -> int:
    # AI_NOTE: 1カード分の specific_effect を upsert して件数を返す。type名はAPI同梱の辞書から引く。
    info = data.get("specific_effect_card_info") or {}
    type_names = data.get("specific_effect_type_names") or {}
    for effect_id_str, effect in info.items():
        effect_type = effect.get("specific_effect_type")
        conn.execute(
            "INSERT OR REPLACE INTO specific_effect "
            "(effect_card_id, card_id, effect_type, effect_type_name, cost, skill_text, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            (int(effect_id_str), card_id, effect_type,
             type_names.get(str(effect_type)), effect.get("cost"), effect.get("skill_text")),
        )
    return len(info)


def run() -> None:
    # AI_NOTE: 全カードを対象に単体APIを周回する。既取得カードはスキップしないと再実行が重いので、
    # specific_effectに親として登場済みのcard_idは飛ばす(全作り直しは滅多に不要・必要ならDROPして再実行)。
    conn = connect()
    try:
        done = {row[0] for row in conn.execute("SELECT DISTINCT card_id FROM specific_effect")}
        targets = [row[0] for row in conn.execute("SELECT card_id FROM card ORDER BY card_id")]
        total_effects = 0
        for i, card_id in enumerate(targets):
            if card_id in done:
                continue
            total_effects += save_effects(conn, card_id, fetch_card(card_id))
            if i % 50 == 0:
                conn.commit()
                print(f"[effects] {i}/{len(targets)}枚 走査 / 効果{total_effects}件")
            time.sleep(REQUEST_INTERVAL_SEC)
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM specific_effect").fetchone()[0]
        print(f"[effects] 完了: specific_effect 総数 {count}件")
    finally:
        conn.close()


if __name__ == "__main__":
    run()
