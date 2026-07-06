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
"""

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

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
    print("usage: python -m svdeck.require dump [card_id ...] | load <requires.json> | list")
    sys.exit(1)


if __name__ == "__main__":
    main()
