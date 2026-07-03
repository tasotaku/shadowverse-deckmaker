"""公式Deck Portal APIから全カードを取得し、原本保存 -> 差分検出 -> ミラーupsertを行う。

実行: python -m svdeck.fetch
"""

import json
import sqlite3
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from svdeck.db import DB_PATH, connect

API_URL = "https://shadowverse-wb.com/web/CardList/cardList"
USER_AGENT = "Mozilla/5.0"
REQUEST_INTERVAL_SEC = 0.35
# offsetは真の行インデックスで、1回に約31〜33件の窓を返す。窓の最小幅(約31)より小さい
# 固定ステップで重ねて取りdedupすることで、窓幅のブレによる取りこぼしを防ぐ。
CRAWL_STEP = 25
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

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

# card_change で監視する項目（差分が出たら履歴に残す）
WATCHED_FIELDS = ("skill_text", "atk", "life", "cost", "deck_enabled_num", "rarity", "card_set_id")


def _get_page(offset: int) -> dict[str, Any]:
    # AI_NOTE: 単一offsetのAPI応答dataを返すHTTP境界。例外は握りつぶさず呼び出し元へ伝播させる。
    url = f"{API_URL}?lang=ja&offset={offset}&include_token=1"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data: dict[str, Any] = payload["data"]
    return data


def fetch_all_cards() -> dict[str, Any]:
    # AI_NOTE: CRAWL_STEPずつoffsetを重ねて全カードを収集する。offsetがcountを越えるまで回すことで
    # 末尾まで確実に覆い、窓の重なり+dedupで隙間なく全件を得る（取りこぼし対策の要）。
    card_details: dict[str, Any] = {}
    card_set_names: dict[str, Any] = {}
    skill_names: dict[str, Any] = {}
    tribe_names: dict[str, Any] = {}
    offset = 0
    total_count: int | None = None

    while total_count is None or offset < total_count:
        data = _get_page(offset)
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


def save_raw_snapshot(raw: dict[str, Any], today: str) -> Path:
    # AI_NOTE: API応答の無加工ダンプを日付ディレクトリに保存する（一次情報の原本）。
    snapshot_dir = DATA_DIR / "snapshots" / today
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    raw_path = snapshot_dir / "cards_raw.json"
    raw_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return raw_path


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


def detect_changes(conn: sqlite3.Connection, raw: dict[str, Any], today: str) -> int:
    # AI_NOTE: 既存cardテーブルと今回取得を比較し、監視対象フィールドの変化・新規card_idをcard_changeへ記録する。
    # DB書き込みはこの関数内で完結させ、呼び出し元がcommitする。
    existing_rows = conn.execute(
        f"SELECT card_id, {', '.join(WATCHED_FIELDS)} FROM card"
    ).fetchall()
    existing: dict[int, dict[str, Any]] = {
        row[0]: dict(zip(WATCHED_FIELDS, row[1:])) for row in existing_rows
    }

    change_count = 0
    for card_id_str, detail in raw["card_details"].items():
        card_id = int(card_id_str)
        new_row = _to_row(card_id, detail["common"], detail.get("evo", []), detail.get("style_card_list", []))

        if card_id not in existing:
            conn.execute(
                "INSERT INTO card_change (snapshot_date, card_id, field, old_value, new_value) VALUES (?, ?, ?, ?, ?)",
                (today, card_id, "__new__", None, "new card"),
            )
            change_count += 1
            continue

        old = existing[card_id]
        for field in WATCHED_FIELDS:
            old_value = old[field]
            new_value = new_row[field]
            if str(old_value) != str(new_value):
                conn.execute(
                    "INSERT INTO card_change (snapshot_date, card_id, field, old_value, new_value) VALUES (?, ?, ?, ?, ?)",
                    (today, card_id, field, str(old_value), str(new_value)),
                )
                change_count += 1

    return change_count


def upsert_mirror(conn: sqlite3.Connection, raw: dict[str, Any]) -> None:
    # AI_NOTE: card/card_set/skill_name/tribe/card_tribeをupsertする。ユーザレイヤ(card_note/card_tag/card_flag)には一切触れない。
    for id_str, name in raw["card_set_names"].items():
        conn.execute(
            "INSERT INTO card_set (id, name) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET name = excluded.name",
            (int(id_str), name),
        )
    for id_str, name in raw["skill_names"].items():
        conn.execute(
            "INSERT INTO skill_name (id, name) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET name = excluded.name",
            (int(id_str), name),
        )
    for id_str, name in raw["tribe_names"].items():
        conn.execute(
            "INSERT INTO tribe (id, name) VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET name = excluded.name",
            (int(id_str), name),
        )

    for card_id_str, detail in raw["card_details"].items():
        card_id = int(card_id_str)
        common = detail["common"]
        row = _to_row(card_id, common, detail.get("evo", []), detail.get("style_card_list", []))
        columns = list(row.keys())
        placeholders = ", ".join(f":{col}" for col in columns)
        update_clause = ", ".join(f"{col} = excluded.{col}" for col in columns if col != "card_id")
        conn.execute(
            f"INSERT INTO card ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT(card_id) DO UPDATE SET {update_clause}",
            row,
        )

        conn.execute("DELETE FROM card_tribe WHERE card_id = ?", (card_id,))
        for tribe_id in common.get("tribes", []) or []:
            conn.execute(
                "INSERT INTO card_tribe (card_id, tribe_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
                (card_id, tribe_id),
            )


def run() -> None:
    # AI_NOTE: fetch.pyのエントリポイント。全体の流れ(取得->原本保存->差分検出->upsert->snapshot記録->サマリ出力)を統括する。
    today = datetime.now(timezone.utc).astimezone().date().isoformat()
    fetched_at = datetime.now(timezone.utc).astimezone().isoformat()

    print(f"[fetch] APIから取得中... (today={today})")
    raw = fetch_all_cards()
    fetched_count = len(raw["card_details"])
    print(f"[fetch] 取得完了: {fetched_count}枚 (API count={raw['count']})")

    raw_path = save_raw_snapshot(raw, today)
    print(f"[fetch] 原本保存: {raw_path}")

    conn = connect()
    try:
        change_count = detect_changes(conn, raw, today)
        upsert_mirror(conn, raw)
        conn.execute(
            "INSERT INTO snapshot (date, fetched_at, card_count) VALUES (?, ?, ?) "
            "ON CONFLICT(date) DO UPDATE SET fetched_at = excluded.fetched_at, card_count = excluded.card_count",
            (today, fetched_at, fetched_count),
        )
        conn.commit()
    finally:
        conn.close()

    print(
        f"[fetch] 完了: 取得={fetched_count}枚 / API総count={raw['count']} / "
        f"新規・変更={change_count}件 / DB={DB_PATH}"
    )


if __name__ == "__main__":
    run()
