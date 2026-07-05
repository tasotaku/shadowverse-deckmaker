"""アトム(供給/要求)抽出結果の入出力CLI。

派生層(card_atom / atom_tag)への入出力を担う。抽出そのものはLLMが docs/extraction-prompt.md に
従って行い、このモジュールは入力用JSONの書き出し(dump)と抽出結果JSONの取り込み(load)だけを行う。

実行:
  python -m svdeck.atoms dump [card_id ...] > cards.json   # 省略時は全カード
  python -m svdeck.atoms load extracted.json
"""

import json
import sys
from pathlib import Path
from typing import Any

from svdeck.db import connect

DUMP_COLUMNS = "card_id, name, class_name, type_category, cost, atk, life, skill_text"


def dump(card_ids: list[int]) -> str:
    # AI_NOTE: 抽出のLLM入力となるカード情報をJSON文字列で返す。card_ids省略時は全カード。
    conn = connect()
    try:
        if card_ids:
            marks = ",".join("?" * len(card_ids))
            cursor = conn.execute(f"SELECT {DUMP_COLUMNS} FROM card WHERE card_id IN ({marks})", card_ids)
        else:
            cursor = conn.execute(f"SELECT {DUMP_COLUMNS} FROM card")
        columns = [d[0] for d in cursor.description]
        cards = [dict(zip(columns, row)) for row in cursor]
    finally:
        conn.close()
    return json.dumps(cards, ensure_ascii=False, indent=1)


def load(path: Path) -> tuple[int, int]:
    # AI_NOTE: 抽出結果JSON(配列)を派生層へ取り込み、(カード数, タグ数)を返す。同じcard_idの既存行は
    # 消してから入れ直す(派生層は再抽出で作り直してよい層のため、ミラー層と違いinsert-onlyにしない)。
    results: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    conn = connect()
    try:
        known = {row[0] for row in conn.execute("SELECT card_id FROM card")}
        tag_count = 0
        for result in results:
            card_id = int(result["card_id"])
            if card_id not in known:
                raise ValueError(f"card_id {card_id} はcardテーブルに存在しない")
            conn.execute("DELETE FROM card_atom WHERE card_id = ?", (card_id,))
            conn.execute("DELETE FROM atom_tag WHERE card_id = ?", (card_id,))
            conn.execute(
                "INSERT INTO card_atom (card_id, atoms_json, model, extracted_at) VALUES (?, ?, ?, datetime('now'))",
                (card_id, json.dumps(result, ensure_ascii=False), result.get("model", "unknown")),
            )
            for kind, key in (("supply", "supply_tags"), ("require", "require_tags")):
                for tag in dict.fromkeys(result.get(key) or []):
                    conn.execute("INSERT INTO atom_tag (card_id, kind, tag) VALUES (?, ?, ?)", (card_id, kind, tag))
                    tag_count += 1
        conn.commit()
        return len(results), tag_count
    finally:
        conn.close()


def main() -> None:
    # AI_NOTE: 人手が触るCLI入口なので、引数不正は例外でなくusage表示で終了する。
    args = sys.argv[1:]
    if args and args[0] == "dump":
        print(dump([int(a) for a in args[1:]]))
        return
    if len(args) == 2 and args[0] == "load":
        cards, tags = load(Path(args[1]))
        print(f"[atoms] 取り込み: {cards}枚 / タグ{tags}件")
        return
    print("usage: python -m svdeck.atoms dump [card_id ...] | load <extracted.json>")
    sys.exit(1)


if __name__ == "__main__":
    main()
