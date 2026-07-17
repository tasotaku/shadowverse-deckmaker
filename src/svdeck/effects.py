"""参照先効果(クレスト/結晶/アクセラレート/信仰)を単体カードAPIから収集する。

カード一覧API(cardList)は『クレスト：〜』等の参照先効果テキストを含まない。単体カードAPI
/web/CardList/card は specific_effect_card_info としてそれを返すため、全カードを1枚ずつ
叩いて card 表の ref_effect_text 列(ミラー層・作り直し可)に保存する。走査済みかどうかは
effect_crawled_at 列(NULL=未走査)で判定し、再実行・新弾追加時は増分クロールになる。

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
    # AI_NOTE: 1カード分の参照先効果を「種別名(コスト): 本文」の見出し付きで card.ref_effect_text に
    # 保存し件数を返す。コスト0(クレスト/信仰)は数値に意味が無いので見出しから省く。種別名はAPI同梱の
    # 辞書から引く。db.py の _migrate_ref_effect と同じ見出し形式。
    info = data.get("specific_effect_card_info") or {}
    type_names = data.get("specific_effect_type_names") or {}
    parts = []
    for effect_id_str, effect in info.items():
        # AI_NOTE: APIは参照先(随伴トークン・相方カード)の効果も同梱する。effect_card_idは
        # 持ち主カードの末尾違いID(card_id+2)なので、基底一致する「本人の効果」だけ保存する。
        # 他人の効果を保存すると別カードの効果を自分の本文に混ぜてしまう(2026-07-17のバグ)。
        if int(effect_id_str) // 10 != card_id // 10:
            continue
        name = type_names.get(str(effect.get("specific_effect_type"))) or "参照先効果"
        cost = effect.get("cost")
        heading = f"{name}({cost}): " if cost else f"{name}: "
        parts.append(heading + (effect.get("skill_text") or ""))
    if parts:
        conn.execute(
            "UPDATE card SET ref_effect_text = ? WHERE card_id = ?",
            ("\n".join(parts), card_id),
        )
    return len(parts)


def run(conn: sqlite3.Connection | None = None) -> None:
    # AI_NOTE: 未走査(effect_crawled_at IS NULL)のカードだけ単体APIを周回する。効果の有無に関わらず
    # 走査日時を記録することで再実行・新弾追加時の増分クロールになる(結晶/アクセラレートはskill_textに
    # 現れないためテキストフィルタでは対象を絞れず、走査記録方式にしている)。fetch.pyから接続を受け取れる。
    own_conn = conn is None
    conn = conn or connect()
    try:
        targets = [
            row[0] for row in conn.execute(
                "SELECT card_id FROM card WHERE effect_crawled_at IS NULL ORDER BY card_id"
            )
        ]
        if not targets:
            print("[effects] 未走査のカードなし")
            return
        total_effects = 0
        for i, card_id in enumerate(targets):
            total_effects += save_effects(conn, card_id, fetch_card(card_id))
            conn.execute("UPDATE card SET effect_crawled_at = datetime('now') WHERE card_id = ?", (card_id,))
            if i % 50 == 0:
                conn.commit()
                print(f"[effects] {i}/{len(targets)}枚 走査 / 効果{total_effects}件")
            time.sleep(REQUEST_INTERVAL_SEC)
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM card WHERE ref_effect_text IS NOT NULL").fetchone()[0]
        print(f"[effects] 完了: 新規走査{len(targets)}枚 / 参照先効果持ち {count}枚")
    finally:
        if own_conn:
            conn.close()


if __name__ == "__main__":
    run()
