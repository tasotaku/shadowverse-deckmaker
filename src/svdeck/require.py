"""アンカーの「要求コンパイル」結果(anchor_require)の入出力CLI。

design.md §8-7 自己改善ループ③「要求の永続化とイベント駆動再コンパイル」の基盤。
アンカーごとに「何が来たら天井が開くか」をDBへ構造化保存し、新ルール確定・新弾・語彙昇格の
たびに再コンパイル差分を出せるようにする。requirement(検索可能な短文)がupsertの一意キーで、
同じcard_id+requirementの再loadはINSERTでなくnote/statusの更新になる(atoms.pyと違い派生層の
作り直しではなく永続台帳のため、既存行は消さず更新する)。

実行:
  python -m svdeck.require dump [card_id ...] > requires.json   # 省略時は全アンカー(card_tag='anchor')
  python -m svdeck.require load requires.json
  python -m svdeck.require list
  python -m svdeck.require recheck   # 供給の再検索レポート(DBは変更しない・新弾取得後の運用)
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, NamedTuple

from svdeck.bench import CategoryLookup, FulfillmentMap, Tag, _matches, load_fulfillment_map, parse_tag
from svdeck.db import connect

DUMP_COLUMNS = "id, card_id, req_type, requirement, req_tag, deadline_turn, source, status, note, updated_at"


def _anchor_card_ids(conn: sqlite3.Connection) -> list[int]:
    return [row[0] for row in conn.execute("SELECT card_id FROM card_tag WHERE tag = 'anchor'")]


def dump(card_ids: list[int]) -> str:
    # AI_NOTE: card_ids省略時は全アンカー(card_tag='anchor')を対象にする。指定時はそのcard_idのみ。
    conn = connect()
    try:
        target_ids = card_ids or _anchor_card_ids(conn)
        if not target_ids:
            return json.dumps([], ensure_ascii=False, indent=1)
        marks = ",".join("?" * len(target_ids))
        cursor = conn.execute(
            f"SELECT {DUMP_COLUMNS} FROM anchor_require WHERE card_id IN ({marks}) ORDER BY card_id, id",
            target_ids,
        )
        columns = [d[0] for d in cursor.description]
        rows = [dict(zip(columns, row)) for row in cursor]
    finally:
        conn.close()
    return json.dumps(rows, ensure_ascii=False, indent=1)


def load(path: Path) -> tuple[int, int]:
    # AI_NOTE: 要求JSON(配列)を一括upsertし、(新規件数, 更新件数)を返す。一意キーはcard_id+requirement。
    # 既存行があればnote/statusのみ更新(source/req_type/req_tag/deadline_turnは初回値を保持し続ける
    # ="由来"の意味が変わらないようにする)。無ければ全カラムでINSERT。
    entries: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    conn = connect()
    try:
        known = {row[0] for row in conn.execute("SELECT card_id FROM card")}
        inserted = 0
        updated = 0
        for entry in entries:
            card_id = int(entry["card_id"])
            if card_id not in known:
                raise ValueError(f"card_id {card_id} はcardテーブルに存在しない")
            requirement = str(entry["requirement"])
            existing = conn.execute(
                "SELECT id FROM anchor_require WHERE card_id = ? AND requirement = ?",
                (card_id, requirement),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE anchor_require SET status = ?, note = ?, updated_at = datetime('now') WHERE id = ?",
                    (entry.get("status", "active"), entry.get("note"), existing[0]),
                )
                updated += 1
            else:
                conn.execute(
                    """
                    INSERT INTO anchor_require
                        (card_id, req_type, requirement, req_tag, deadline_turn, source, status, note, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
                    """,
                    (
                        card_id,
                        entry["req_type"],
                        requirement,
                        entry.get("req_tag"),
                        entry.get("deadline_turn"),
                        entry["source"],
                        entry.get("status", "active"),
                        entry.get("note"),
                    ),
                )
                inserted += 1
        conn.commit()
        return inserted, updated
    finally:
        conn.close()


def list_requires() -> str:
    # AI_NOTE: アンカー別の要求一覧を人が読める形で整形する。card_noteを併記し「蓄積の最大活用」
    # (design.md §8-6)に沿って過去の判定根拠を毎回目に入るようにする。
    conn = connect()
    try:
        rows = conn.execute(
            """
            SELECT c.card_id, c.name, cn.note, r.req_type, r.requirement, r.deadline_turn,
                   r.status, r.source, r.note
            FROM anchor_require r
            JOIN card c ON c.card_id = r.card_id
            LEFT JOIN card_note cn ON cn.card_id = c.card_id
            ORDER BY c.card_id, r.id
            """
        ).fetchall()
    finally:
        conn.close()

    lines: list[str] = []
    current_card_id: int | None = None
    for card_id, name, card_note, req_type, requirement, deadline_turn, status, source, note in rows:
        if card_id != current_card_id:
            lines.append(f"\n[{card_id}] {name}")
            if card_note:
                lines.append(f"  card_note: {card_note}")
            current_card_id = card_id
        deadline = f" deadline=T{deadline_turn}" if deadline_turn is not None else ""
        line = f"  - ({req_type}/{status}) {requirement}{deadline} source={source}"
        if note:
            line += f"\n      note: {note}"
        lines.append(line)
    return "\n".join(lines).lstrip("\n") + "\n"


class RecheckRow(NamedTuple):
    anchor_id: int
    card_id: int
    card_name: str
    class_name: str
    requirement: str
    status: str
    outcome: str  # "supply_found"(供給あり) / "no_supply"(供給なし) / "manual"(タグ文法非合致)


def _requirement_tag(req_tag: str | None, requirement: str) -> Tag:
    # AI_NOTE: req_tag列が埋まっていればそちらを正とする(将来req_tagが構造化データとして
    # 埋まった場合の前方互換)。現状は全行req_tag空のためrequirement自由文をそのままparse_tagにかける。
    return parse_tag(req_tag if req_tag else requirement)


def _class_filtered_supply_tags(
    conn: sqlite3.Connection, class_name: str
) -> list[Tag]:
    # AI_NOTE: design.md§6.1「クラス固有キーワードはそのクラス内でのみ意味を持つ」に沿い、
    # 供給候補の列挙は常に「同クラス+ニュートラル」に絞る(試作v0でAIがこの違反を出したため明文化済み)。
    rows = conn.execute(
        "SELECT at.tag FROM atom_tag at JOIN card c ON c.card_id = at.card_id "
        "WHERE at.kind = 'supply' AND c.class_name IN (?, 'ニュートラル')",
        (class_name,),
    ).fetchall()
    return [parse_tag(row[0]) for row in rows]


def recheck() -> list[RecheckRow]:
    # AI_NOTE: design.md§8-7運用「新弾取得後はrecheckを回す」の実体。anchor_requireのdead/active
    # 各行についてrequirement/req_tagをタグ語彙(fulfillment_map)経由で再解釈し、同クラス+
    # ニュートラルの全カードの現在の供給タグから充足候補を探す。判断(status変更)はしない・
    # レポートのみ返す(呼び出し元がDB変更しない・人とメインセッションが読んで判断する仕様)。
    conn = connect()
    try:
        fmap = load_fulfillment_map()
        category_lookup = CategoryLookup(conn)
        rows = conn.execute(
            """
            SELECT r.id, c.card_id, c.name, c.class_name, r.requirement, r.req_tag, r.status
            FROM anchor_require r
            JOIN card c ON c.card_id = r.card_id
            WHERE r.status IN ('dead', 'active')
            ORDER BY c.card_id, r.id
            """
        ).fetchall()

        supply_cache: dict[str, list[Tag]] = {}
        results: list[RecheckRow] = []
        for anchor_id, card_id, card_name, class_name, requirement, req_tag, status in rows:
            tag = _requirement_tag(req_tag, requirement)
            category = fmap.classify(tag)
            if category in ("unclassified",):
                results.append(
                    RecheckRow(anchor_id, card_id, card_name, class_name, requirement, status, "manual")
                )
                continue
            if category in ("auto", "auto_or_supply", "construction"):
                # AI_NOTE: 常時充足/カード単位で閉じない種別は「供給の再検索」という問いに馴染まないため
                # manual同様に判断対象外として件数のみ表示する(ロジックはmanualと別カウント)。
                results.append(
                    RecheckRow(anchor_id, card_id, card_name, class_name, requirement, status, "no_supply")
                )
                continue

            if category == "natural":
                rule = fmap.natural_rule_for(tag)
                allowed = rule.supplies if rule is not None else []
                use_category = False
            else:
                allowed = fmap.supplies_for(tag)
                use_category = fmap.category_resolution_for(tag)

            if class_name not in supply_cache:
                supply_cache[class_name] = _class_filtered_supply_tags(conn, class_name)
            supply_tags = supply_cache[class_name]

            found = _matches(tag, supply_tags, allowed, category_lookup if use_category else None)
            outcome = "supply_found" if found else "no_supply"
            results.append(RecheckRow(anchor_id, card_id, card_name, class_name, requirement, status, outcome))
        return results
    finally:
        conn.close()


def format_recheck_report(rows: list[RecheckRow]) -> str:
    # AI_NOTE: 主目的は「前回dead判定だが今は供給が存在する」復活候補の洗い出し。それ以外は
    # 参考情報として件数のみ出す(design.md§8-7「変更せずレポートだけ出す」)。
    lines: list[str] = []
    lines.append("=== require recheck: 要求の供給再検索レポート ===")

    revived = [r for r in rows if r.status == "dead" and r.outcome == "supply_found"]
    manual = [r for r in rows if r.outcome == "manual"]
    dead_total = sum(1 for r in rows if r.status == "dead")
    active_total = sum(1 for r in rows if r.status == "active")

    lines.append(f"総計: dead {dead_total}件 / active {active_total}件 / manual(自由文・件数のみ) {len(manual)}件")
    lines.append("")

    lines.append(f"=== 復活候補(前回dead判定・今は供給が存在する) {len(revived)}件 ===")
    if not revived:
        lines.append("(なし)")
    for r in revived:
        lines.append(f"- [{r.card_id}] {r.card_name} ({r.class_name}) anchor_require id={r.anchor_id}")
        lines.append(f"    requirement: {r.requirement}")
    lines.append("")

    lines.append("=== manual(requirementがタグ文法に合致しない自由文・LLM再コンパイル待ち) ===")
    lines.append(f"件数: {len(manual)}件(内訳はdump/listで参照)")
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> None:
    # AI_NOTE: 人手が触るCLI入口なので、引数不正は例外でなくusage表示で終了する。
    args = sys.argv[1:]
    if args and args[0] == "dump":
        print(dump([int(a) for a in args[1:]]))
        return
    if len(args) == 2 and args[0] == "load":
        inserted, updated = load(Path(args[1]))
        print(f"[require] 取り込み: 新規{inserted}件 / 更新{updated}件")
        return
    if args == ["list"]:
        print(list_requires())
        return
    if args == ["recheck"]:
        print(format_recheck_report(recheck()))
        return
    print("usage: python -m svdeck.require dump [card_id ...] | load <requires.json> | list | recheck")
    sys.exit(1)


if __name__ == "__main__":
    main()
