"""公式APIからカードを取得してローカルDB(ミラー層)へ保存する。

2つのユースケースを card テーブルの有無で自動分岐する:
  - DBが空: 全カードを取得(全件クロール)
  - DBがある: APIのパック一覧と手元カードを比べ、新弾パックだけ取得

保存はミラー層のみ。カードは新規だけINSERT(既存は書き換えない)、名称辞書は毎回作り直す。

実行: python -m svdeck.fetch
"""

import json
import sqlite3
import time
import urllib.request
from typing import Any

from svdeck.db import DB_PATH, connect
from svdeck.effects import run as effects_run

API_URL = "https://shadowverse-wb.com/web/CardList/cardList"
USER_AGENT = "Mozilla/5.0"
REQUEST_INTERVAL_SEC = 0.35
# offsetは真の行インデックスで、1回に約31〜33件の窓を返す。窓の最小幅(約31)より小さい
# 固定ステップで重ねて取りdedupすることで、窓幅のブレによる取りこぼしを防ぐ。
CRAWL_STEP = 25

CLASS_NAMES: dict[int, str] = {
    0: "ニュートラル",
    1: "エルフ",
    2: "ロイヤル",
    3: "ウィッチ",
    4: "ドラゴン",
    5: "ナイトメア",
    6: "ビショップ",
    7: "ネメシス",
}

RARITY_NAMES: dict[int, str] = {
    1: "ブロンズ",
    2: "シルバー",
    3: "ゴールド",
    4: "レジェンド",
}

TYPE_CATEGORIES: dict[int, str] = {
    1: "follower",
    2: "amulet",
    3: "amulet",
    4: "spell",
}


def _get_page(offset: int, card_set: int | None = None) -> dict[str, Any]:
    # AI_NOTE: 単一offsetのAPI応答dataを返すHTTP境界。card_setを渡すとそのパックだけに絞る。
    # 例外は握りつぶさず呼び出し元へ伝播させる。
    url = f"{API_URL}?lang=ja&offset={offset}&include_token=1"
    if card_set is not None:
        url += f"&card_set={card_set}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data: dict[str, Any] = payload["data"]
    return data


def crawl(card_set: int | None = None) -> dict[str, Any]:
    # AI_NOTE: CRAWL_STEPずつoffsetを重ねてカードを収集する。card_set=None なら全件、指定すればそのパック分。
    # offsetがcountを越えるまで回して末尾まで覆い、窓の重なり+dedupで隙間なく取り切る(取りこぼし対策の要)。
    card_details: dict[str, Any] = {}
    card_set_names: dict[str, Any] = {}
    skill_names: dict[str, Any] = {}
    tribe_names: dict[str, Any] = {}
    offset = 0
    total_count: int | None = None

    while total_count is None or offset < total_count:
        data = _get_page(offset, card_set)
        if total_count is None:
            total_count = data["count"]
        card_set_names.update(data.get("card_set_names", {}))
        skill_names.update(data.get("skill_names", {}))
        tribe_names.update(data.get("tribe_names", {}))

        # 空ページのcard_detailsは[]で返るためdictのみ採用する
        page_details = data.get("card_details")
        if isinstance(page_details, dict):
            card_details.update(page_details)

        offset += CRAWL_STEP
        time.sleep(REQUEST_INTERVAL_SEC)

    return {
        "card_details": card_details,
        "card_set_names": card_set_names,
        "skill_names": skill_names,
        "tribe_names": tribe_names,
        "count": total_count,
    }


def _to_row(card_id: int, common: dict[str, Any], evo: list[Any], style: list[Any]) -> dict[str, Any]:
    class_id = common.get("class")
    rarity_id = common.get("rarity")
    type_id = common.get("type")
    return {
        "card_id": card_id,
        "name": common.get("name"),
        "name_ruby": common.get("name_ruby"),
        "skill_text": common.get("skill_text"),
        "flavour_text": common.get("flavour_text"),
        "cost": common.get("cost"),
        "atk": common.get("atk"),
        "life": common.get("life"),
        "class": class_id,
        "class_name": CLASS_NAMES.get(class_id) if class_id is not None else None,
        "type": type_id,
        "type_category": TYPE_CATEGORIES.get(type_id) if type_id is not None else None,
        "rarity": rarity_id,
        "rarity_name": RARITY_NAMES.get(rarity_id) if rarity_id is not None else None,
        "card_set_id": common.get("card_set_id"),
        "is_token": int(bool(common.get("is_token"))),
        "deck_enabled_num": common.get("deck_enabled_num"),
        "is_include_rotation": int(bool(common.get("is_include_rotation"))),
        "base_card_id": common.get("base_card_id"),
        "original_card_id": common.get("original_card_id"),
        "evo_json": json.dumps(evo, ensure_ascii=False),
        "style_json": json.dumps(style, ensure_ascii=False),
        "common_json": json.dumps(common, ensure_ascii=False),
    }


def rebuild_dicts(conn: sqlite3.Connection, raw: dict[str, Any]) -> None:
    # AI_NOTE: 名称辞書(card_set/skill_name/tribe)を作り直す。小さくAPIが毎回全件くれるので、差分を取る
    # より DELETE→全INSERT の方が単純。どのfetch応答も辞書は全件なので部分取得でも取りこぼさない。
    for table, key in (("card_set", "card_set_names"), ("skill_name", "skill_names"), ("tribe", "tribe_names")):
        conn.execute(f"DELETE FROM {table}")
        conn.executemany(
            f"INSERT INTO {table} (id, name) VALUES (?, ?)",
            [(int(id_str), name) for id_str, name in raw[key].items()],
        )


def insert_new_cards(conn: sqlite3.Connection, raw: dict[str, Any]) -> int:
    # AI_NOTE: 自分のDBに無い新規カードだけINSERTし、その枚数を返す。既存カードの能力値は書き換えない
    # (公式の後追い更新は追わない方針)。ユーザレイヤ(card_note/card_tag/card_flag)には触れない。
    existing_ids = {row[0] for row in conn.execute("SELECT card_id FROM card")}
    added = 0
    for card_id_str, detail in raw["card_details"].items():
        card_id = int(card_id_str)
        if card_id in existing_ids:
            continue
        common = detail["common"]
        row = _to_row(card_id, common, detail.get("evo", []), detail.get("style_card_list", []))
        columns = list(row.keys())
        placeholders = ", ".join(f":{col}" for col in columns)
        conn.execute(f"INSERT INTO card ({', '.join(columns)}) VALUES ({placeholders})", row)
        for tribe_id in common.get("tribes", []) or []:
            conn.execute(
                "INSERT INTO card_tribe (card_id, tribe_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
                (card_id, tribe_id),
            )
        added += 1
    return added


def find_new_packs(conn: sqlite3.Connection, card_set_names: dict[str, Any]) -> list[int]:
    # AI_NOTE: 「APIにあって手元cardが持っていないパックID」を新弾とみなす。判定基準は毎回作り直す
    # card_setテーブルでなく、実際に所有するカードの DISTINCT card_set_id(消えない・新規追加のみ)。
    # これなら辞書を作り直しても、全件取得が途中で落ちても取り損ねたパックを次回拾い直せる。
    have = {row[0] for row in conn.execute("SELECT DISTINCT card_set_id FROM card")}
    return [int(pid) for pid in card_set_names if int(pid) not in have]


def run() -> None:
    # AI_NOTE: エントリポイント。cardが空なら全件取得、あれば新弾だけ検出して追加、と自動分岐する(ユーザ入力不要)。
    # 取得ごとに辞書を作り直し、新規カードだけ保存する。DB書き込みは1トランザクションでまとめてcommit。
    conn = connect()
    try:
        before = conn.execute("SELECT COUNT(*) FROM card").fetchone()[0]
        if before == 0:
            print("[fetch] DBが空 → 全カードを新規取得")
            raw = crawl()
            rebuild_dicts(conn, raw)
            insert_new_cards(conn, raw)
        else:
            names = _get_page(0)["card_set_names"]
            new_packs = find_new_packs(conn, names)
            if not new_packs:
                print("[fetch] 新弾なし（DBは最新）")
                return
            print(f"[fetch] 新弾を検出: {new_packs}")
            for pack_id in new_packs:
                raw = crawl(card_set=pack_id)
                rebuild_dicts(conn, raw)
                insert_new_cards(conn, raw)

        after = conn.execute("SELECT COUNT(*) FROM card").fetchone()[0]
        conn.commit()
        print(f"[fetch] 完了: 追加={after - before}枚 / DB総数={after}枚 / {DB_PATH}")

        # AI_NOTE: 新カードのクレスト/結晶/アクセラレート/信仰は一覧APIに無いため、追加分だけ
        # 単体カードAPIを増分クロールする(effect_crawled_at記録済みはスキップされる)。
        if after > before:
            effects_run(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    run()
