"""公式APIからカードを取得してローカルDB(ミラー層)へ保存する。

役割分担: 一覧API(cardList)はカードIDの列挙・名称辞書・新弾検出だけに使い、カードの中身
(本文・能力値・参照先効果)は単体API(card)から1枚=1リクエストで取り込む。一覧のcard_details
にも中身は入っている(単体と完全一致を確認済み)が、クレスト/結晶/アクセラレート/信仰の
参照先効果だけは単体APIにしか無いため、出どころを単体API1本に寄せて2段取得の縫い合わせを
無くしている(2026-07-17開発者決定)。

2つのユースケースを card テーブルの有無で自動分岐する:
  - DBが空: 全カードを取得(全件クロール)
  - DBがある: APIのパック一覧と手元カードを比べ、新弾パックだけ取得

保存はミラー層のみ。通常取得ではカードは新規だけINSERTし、名称辞書は毎回作り直す。
公式の能力変更を取り込むときは --refresh で全件を突き合わせ、変わった既存カードだけ更新する。

実行: python -m svdeck.fetch [--refresh]
"""

import json
import sqlite3
import sys
import time
import urllib.request
from typing import Any

from svdeck.db import DB_PATH, connect

LIST_API_URL = "https://shadowverse-wb.com/web/CardList/cardList"
CARD_API_URL = "https://shadowverse-wb.com/web/CardList/card"
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
    # AI_NOTE: 一覧APIの単一offsetの応答dataを返すHTTP境界。card_setを渡すとそのパックだけに絞る。
    # 例外は握りつぶさず呼び出し元へ伝播させる。
    url = f"{LIST_API_URL}?lang=ja&offset={offset}&include_token=1"
    if card_set is not None:
        url += f"&card_set={card_set}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data: dict[str, Any] = payload["data"]
    return data


def fetch_card(card_id: int) -> dict[str, Any]:
    # AI_NOTE: 単体カードAPIのHTTP境界。card_details(中身)と specific_effect_card_info(参照先効果)を
    # 含む data を返す。例外は伝播。
    url = f"{CARD_API_URL}?card_id={card_id}&lang=ja"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data: dict[str, Any] = payload["data"]
    return data


def crawl(card_set: int | None = None) -> dict[str, Any]:
    # AI_NOTE: CRAWL_STEPずつoffsetを重ねてカードIDと名称辞書を収集する。card_set=None なら全件、
    # 指定すればそのパック分。offsetがcountを越えるまで回して末尾まで覆い、窓の重なり+dedupで
    # 隙間なく取り切る(取りこぼし対策の要)。カードの中身はここでは取らない(単体APIの仕事)。
    card_ids: set[int] = set()
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
            card_ids.update(int(id_str) for id_str in page_details)
            card_details.update(page_details)

        offset += CRAWL_STEP
        time.sleep(REQUEST_INTERVAL_SEC)

    return {
        "card_ids": sorted(card_ids),
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


def _ref_effect_text(card_id: int, data: dict[str, Any]) -> str | None:
    # AI_NOTE: 単体API応答から参照先効果を「種別名(コスト): 本文」の見出し付きで組み立てる。
    # コスト0(クレスト/信仰のAPI埋め草)は数値に意味が無いので見出しから省く。db.pyの
    # _migrate_ref_effect と同じ見出し形式。種別名はAPI同梱の辞書から引く。
    info = data.get("specific_effect_card_info") or {}
    type_names = data.get("specific_effect_type_names") or {}
    parts = []
    for effect_id_str, effect in info.items():
        # AI_NOTE: APIは参照先(随伴トークン・相方カード)の効果も同梱する。effect_card_idは
        # 持ち主カードの末尾違いID(card_id+2)なので、基底一致する「本人の効果」だけ採用する。
        # 他人の効果を混ぜると別カードの効果を自分の本文に帰属させてしまう(2026-07-17のバグ)。
        if int(effect_id_str) // 10 != card_id // 10:
            continue
        name = type_names.get(str(effect.get("specific_effect_type"))) or "参照先効果"
        cost = effect.get("cost")
        heading = f"{name}({cost}): " if cost else f"{name}: "
        parts.append(heading + (effect.get("skill_text") or ""))
    return "\n".join(parts) if parts else None


def insert_card(conn: sqlite3.Connection, card_id: int, data: dict[str, Any]) -> None:
    # AI_NOTE: 単体API応答1枚分をcard(+card_tribe)へINSERTする。本文・能力値と参照先効果が
    # 同じ応答から同時に入るので、一覧と単体の縫い合わせは発生しない。既存行の書き換えはしない
    # 前提(呼び出し元が新規IDだけ渡す)。ユーザレイヤには触れない。
    detail = data["card_details"][str(card_id)]
    common = detail["common"]
    row = _to_row(card_id, common, detail.get("evo", []), detail.get("style_card_list", []))
    row["ref_effect_text"] = _ref_effect_text(card_id, data)
    columns = list(row.keys())
    placeholders = ", ".join(f":{col}" for col in columns)
    conn.execute(f"INSERT INTO card ({', '.join(columns)}) VALUES ({placeholders})", row)
    for tribe_id in common.get("tribes", []) or []:
        conn.execute(
            "INSERT INTO card_tribe (card_id, tribe_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
            (card_id, tribe_id),
        )


def _same_value(column: str, old: Any, new: Any) -> bool:
    # AI_NOTE: JSON列はAPI内部のキー順だけが変わっても変更扱いにしない。壊れた既存JSONは
    # 隠さず例外にして、誤った「変更なし」を作らない。
    if column.endswith("_json") and isinstance(old, str) and isinstance(new, str):
        return bool(json.loads(old) == json.loads(new))
    return bool(old == new)


def find_changed_card_ids(conn: sqlite3.Connection, raw: dict[str, Any]) -> list[int]:
    # AI_NOTE: 一覧APIは参照先効果を持たないため、まず共通情報だけで変更候補を安く絞る。
    # 候補の完全な更新値は後段で単体APIから取得し、取得元を新規カードと統一する。
    changed: list[int] = []
    for card_id_str, detail in raw["card_details"].items():
        card_id = int(card_id_str)
        common = detail["common"]
        row = _to_row(card_id, common, detail.get("evo", []), detail.get("style_card_list", []))
        columns = [column for column in row if column != "card_id"]
        old = conn.execute(
            f"SELECT {', '.join(columns)} FROM card WHERE card_id = ?", (card_id,)
        ).fetchone()
        if old is None:
            continue
        if any(not _same_value(column, old_value, row[column]) for column, old_value in zip(columns, old)):
            changed.append(card_id)
    return changed


REPORT_COLUMNS = ("skill_text", "cost", "atk", "life", "deck_enabled_num", "is_include_rotation", "ref_effect_text")
EFFECT_COLUMNS = {"skill_text", "cost", "atk", "life", "ref_effect_text"}


def _effect_changed(diffs: dict[str, tuple[Any, Any]]) -> bool:
    # AI_NOTE: evo_jsonには能力と無関係な台詞・画像情報も入る。再分析対象にするのは進化後能力本文が
    # 変わった時だけに絞り、台詞の表記修正を「効果変更」と誤報しない。
    if EFFECT_COLUMNS.intersection(diffs):
        return True
    if "evo_json" not in diffs:
        return False
    old_evo, new_evo = diffs["evo_json"]
    if not isinstance(old_evo, str) or not isinstance(new_evo, str):
        return True
    old_detail = json.loads(old_evo)
    new_detail = json.loads(new_evo)
    if not isinstance(old_detail, dict) or not isinstance(new_detail, dict):
        return bool(old_detail != new_detail)
    return bool(old_detail.get("skill_text") != new_detail.get("skill_text"))


def update_card(conn: sqlite3.Connection, card_id: int, data: dict[str, Any]) -> tuple[dict[str, tuple[Any, Any]], bool]:
    # AI_NOTE: 公式ミラー層の既存1行だけを単体APIの完全な値で更新する。利用者が付けたメモ・タグ・
    # 旗は別表なので保持し、効果分析も勝手に消さず「古くなった」ことを呼び出し元へ返す。
    detail = data["card_details"][str(card_id)]
    common = detail["common"]
    row = _to_row(card_id, common, detail.get("evo", []), detail.get("style_card_list", []))
    row["ref_effect_text"] = _ref_effect_text(card_id, data)
    columns = [column for column in row if column != "card_id"]
    old_row = conn.execute(
        f"SELECT {', '.join(columns)} FROM card WHERE card_id = ?", (card_id,)
    ).fetchone()
    if old_row is None:
        raise ValueError(f"card_id {card_id} はcardテーブルに存在しない")
    diffs = {
        column: (old_value, row[column])
        for column, old_value in zip(columns, old_row)
        if not _same_value(column, old_value, row[column])
    }
    assignments = ", ".join(f"{column} = :{column}" for column in columns)
    conn.execute(f"UPDATE card SET {assignments} WHERE card_id = :card_id", row)
    conn.execute("DELETE FROM card_tribe WHERE card_id = ?", (card_id,))
    conn.executemany(
        "INSERT INTO card_tribe (card_id, tribe_id) VALUES (?, ?) ON CONFLICT DO NOTHING",
        [(card_id, tribe_id) for tribe_id in common.get("tribes", []) or []],
    )
    return diffs, _effect_changed(diffs)


def fetch_new_cards(conn: sqlite3.Connection, card_ids: list[int]) -> int:
    # AI_NOTE: DBに無いIDだけ単体APIを周回してINSERTし、追加枚数を返す。commitは呼び出し元の仕事
    # (パック単位・全件単位の途中半端な状態を確定させないため。card行の有無が取得済み判定なので、
    # 中途半端に確定すると新弾検出〔パック単位〕がすり抜ける)。
    existing = {r[0] for r in conn.execute("SELECT card_id FROM card")}
    targets = [cid for cid in card_ids if cid not in existing]
    for i, card_id in enumerate(targets):
        insert_card(conn, card_id, fetch_card(card_id))
        if i % 50 == 0:
            print(f"[fetch] {i}/{len(targets)}枚 取得")
        time.sleep(REQUEST_INTERVAL_SEC)
    return len(targets)


def rebuild_dicts(conn: sqlite3.Connection, raw: dict[str, Any]) -> None:
    # AI_NOTE: 名称辞書(card_set/skill_name/tribe)を作り直す。小さく一覧APIが毎回全件くれるので、
    # 差分を取るより DELETE→全INSERT の方が単純。どの応答も辞書は全件なので部分取得でも取りこぼさない。
    for table, key in (("card_set", "card_set_names"), ("skill_name", "skill_names"), ("tribe", "tribe_names")):
        conn.execute(f"DELETE FROM {table}")
        conn.executemany(
            f"INSERT INTO {table} (id, name) VALUES (?, ?)",
            [(int(id_str), name) for id_str, name in raw[key].items()],
        )


def find_new_packs(conn: sqlite3.Connection, card_set_names: dict[str, Any]) -> list[int]:
    # AI_NOTE: 「APIにあって手元cardが持っていないパックID」を新弾とみなす。判定基準は毎回作り直す
    # card_setテーブルでなく、実際に所有するカードの DISTINCT card_set_id(消えない・新規追加のみ)。
    # これなら辞書を作り直しても、取得が途中で落ちても取り損ねたパックを次回拾い直せる。
    have = {row[0] for row in conn.execute("SELECT DISTINCT card_set_id FROM card")}
    return [int(pid) for pid in card_set_names if int(pid) not in have]


def run(refresh: bool = False) -> None:
    # AI_NOTE: エントリポイント。cardが空なら全件取得、あれば新弾だけ検出して追加、と自動分岐する
    # (ユーザ入力不要)。--refresh時は一覧APIで全件を突き合わせ、変更候補だけ単体APIで更新する。
    # commitの単位=初回/refreshは全件で1回・新弾はパック完了ごとに1回。
    conn = connect()
    try:
        before = conn.execute("SELECT COUNT(*) FROM card").fetchone()[0]
        added = 0
        updated = 0
        stale_ids: list[int] = []
        if before == 0:
            print("[fetch] DBが空 → 全カードを新規取得")
            raw = crawl()
            rebuild_dicts(conn, raw)
            added = fetch_new_cards(conn, raw["card_ids"])
            conn.commit()
        elif refresh:
            print("[fetch] --refresh → 全カードを再確認")
            raw = crawl()
            rebuild_dicts(conn, raw)
            changed_ids = find_changed_card_ids(conn, raw)
            added = fetch_new_cards(conn, raw["card_ids"])
            for card_id in changed_ids:
                diffs, stale = update_card(conn, card_id, fetch_card(card_id))
                updated += 1
                name = conn.execute("SELECT name FROM card WHERE card_id = ?", (card_id,)).fetchone()[0]
                print(f"[refresh] 変更: {card_id} {name}")
                for column in REPORT_COLUMNS:
                    if column in diffs:
                        print(f"  {column}: {diffs[column][0]!r} → {diffs[column][1]!r}")
                if stale:
                    stale_ids.append(card_id)
                time.sleep(REQUEST_INTERVAL_SEC)
            conn.commit()
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
                added += fetch_new_cards(conn, raw["card_ids"])
                conn.commit()

        after = conn.execute("SELECT COUNT(*) FROM card").fetchone()[0]
        updated_note = f" / 更新={updated}枚" if refresh else ""
        print(f"[fetch] 完了: 追加={added}枚{updated_note} / DB総数={after}枚 / {DB_PATH}")
        if stale_ids:
            ids_text = " ".join(str(card_id) for card_id in stale_ids)
            print(f"[refresh] 効果分析の再作成が必要: {ids_text}")
            print(f"  python -m svdeck.atoms dump {ids_text}")
            print(f"  python -m svdeck.vectorize dump {ids_text}")
    finally:
        conn.close()


if __name__ == "__main__":
    # AI_NOTE: 引数の打ち間違いを通常更新として実行しない。許可する形を2つに限定する。
    args = sys.argv[1:]
    if args not in ([], ["--refresh"]):
        print("usage: python -m svdeck.fetch [--refresh]")
        sys.exit(1)
    run(refresh=bool(args))
