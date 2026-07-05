"""カード用途メモ(抽象検索用の自由文1行)を派生層から生成する。

タグ(離散・厳密)では引けない抽象クエリ(「回復を無意味化できるカード」等)のために、
抽出済み card_atom の効果・天井・備考を1カード1行のテキストに整形する。全カード分でも
約100KBに収まり、LLMが1回で全readして意味検索できる。再抽出後に再実行して作り直す。

実行: python -m svdeck.memo  (data/card_memo.txt を出力)
"""

import json
import re
from pathlib import Path

from svdeck.db import DB_PATH, connect

MEMO_PATH = DB_PATH.parent / "card_memo.txt"


def build_memo(atoms_json: str) -> str:
    # AI_NOTE: 効果文・天井・備考を「;」「/」で繋いだ1行に潰す。空要素はスキップし300字で打ち切る。
    d = json.loads(atoms_json)
    effects = "; ".join(str(a.get("effect") or "") for a in d.get("atoms", []) if a.get("effect"))
    headroom = d.get("headroom") or {}
    parts = [effects]
    if headroom.get("max") and headroom.get("rank") not in ("ゼロ", None):
        parts.append(f"天井:{headroom['max']}")
    if d.get("notes"):
        parts.append(f"備考:{str(d['notes'])[:80]}")
    return re.sub(r"\s+", " ", " / ".join(p for p in parts if p).strip())[:300]


def run() -> None:
    conn = connect()
    try:
        lines = [
            f"{cid}|{cls}|{cost}|{name}|{build_memo(aj)}"
            for cid, name, cls, cost, aj in conn.execute(
                "SELECT c.card_id, c.name, c.class_name, c.cost, a.atoms_json "
                "FROM card c JOIN card_atom a USING(card_id) WHERE c.is_token=0 ORDER BY c.card_id"
            )
        ]
    finally:
        conn.close()
    MEMO_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"[memo] {len(lines)}枚 → {MEMO_PATH}")


if __name__ == "__main__":
    run()
