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
    saved = 0
    for effect_id_str, effect in info.items():
        # AI_NOTE: APIは参照先(随伴トークン・相方カード)の効果も同梱する。effect_card_idは
        # 持ち主カードの末尾違いID(card_id+2)なので、基底一致する「本人の効果」だけ保存する。
        # 他人の効果を保存すると INSERT OR REPLACE で正しい帰属行を横取りする(2026-07-17のバグ)。
        if int(effect_id_str) // 10 != card_id // 10:
            continue
        effect_type = effect.get("specific_effect_type")
        conn.execute(
            "INSERT OR REPLACE INTO specific_effect "
            "(effect_card_id, card_id, effect_type, effect_type_name, cost, skill_text, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            (int(effect_id_str), card_id, effect_type,
             type_names.get(str(effect_type)), effect.get("cost"), effect.get("skill_text")),
        )
        saved += 1
    return saved


def run(conn: sqlite3.Connection | None = None) -> None:
    # AI_NOTE: 未クロールのカードだけ単体APIを周回する。効果の有無に関わらず effect_crawl に記録する
    # ことで再実行・新弾追加時の増分クロールになる(結晶/アクセラレートはskill_textに現れないため
    # テキストフィルタでは対象を絞れず、クロール記録方式にしている)。fetch.pyから接続を受け取れる。
    own_conn = conn is None
    conn = conn or connect()
    try:
        targets = [
            row[0] for row in conn.execute(
                "SELECT card_id FROM card WHERE card_id NOT IN (SELECT card_id FROM effect_crawl) ORDER BY card_id"
            )
        ]
        if not targets:
            print("[effects] 未クロールのカードなし")
            return
        total_effects = 0
        for i, card_id in enumerate(targets):
            total_effects += save_effects(conn, card_id, fetch_card(card_id))
            conn.execute("INSERT OR REPLACE INTO effect_crawl (card_id, fetched_at) VALUES (?, datetime('now'))", (card_id,))
            if i % 50 == 0:
                conn.commit()
                print(f"[effects] {i}/{len(targets)}枚 走査 / 効果{total_effects}件")
            time.sleep(REQUEST_INTERVAL_SEC)
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM specific_effect").fetchone()[0]
        print(f"[effects] 完了: 新規走査{len(targets)}枚 / specific_effect 総数 {count}件")
    finally:
        if own_conn:
            conn.close()


if __name__ == "__main__":
    run()
